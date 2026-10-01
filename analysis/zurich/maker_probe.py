#!/usr/bin/env python3
"""MAKER PROBE - the only untested structure (spec analysis/v/maker2/MAKER_PROBE_SPEC.md; owner
"Okay test it", 09-30 ~12:5x UTC, relayed by V).

WHAT IT IS FOR. M5/M10 died of adverse fills: a passive bid gets hit precisely when the world has
just moved against it. Every simulation of that is a guess, because we cannot know from a tape
whether OUR order would have been the one lifted. This posts real 5-share bids and cancels them on a
Binance move, so the adverse-fill share is MEASURED rather than assumed.

WHAT IT IS NOT. It is not a strategy, not an EF engine, not a lane. It shares nothing with the 8787
engine but the wallet: its own process, its own database, its own enable flag, its own stops.

THE FIVE SAFETY PROPERTIES, each with a unit test in test_maker_probe.py:
  1. it never crosses           post_only=True on the signed order AND a local price < best ask check
  2. it cancels on a 2 bps move Binance spot, last 1 s, against our side
  3. it cancels at 180 s        and at the candle's end
  4. one open order at a time   and at most one FILL per candle
  5. both hard stops bind       -$10 realised in a UTC day -> off for the day; -$20 lifetime -> off for good

AND THE ONE THAT IS NOT IN THE SPEC BUT MATTERS MORE THAN ANY OF THEM:
  6. it NEVER calls cancel_all() or cancel_market_orders(). Zurich and London share ONE wallet and
     the 8787 engine has its own resting orders on it. A wallet-wide cancel from a probe would reach
     into another engine's orders. Only cancel_order(order_id=...), only ids this process created.
     There is a test that greps this module for those two SDK names.

DEFAULT OFF. ENABLED_FLAG must contain "1" and the process must be started without --dry-run before a
single order can be signed. This module never writes that flag; the owner does.
"""
import argparse, asyncio, collections, json, math, os, re, sqlite3, sys, time

sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
from poly_fav import FavBrain, VOL_CUT          # the FROZEN calm gate; not re-derived here

# ---- frozen from the spec; nothing here is tuned ------------------------------------------------
BID_LO, BID_HI   = 0.60, 0.80    # favourite = side whose best BID is in this band
SEC_LO, SEC_HI   = 60, 180       # post window; 180 s is also the hard cancel
SHARES           = 5.0           # ~$3 a bid
ADVERSE_BPS      = 2.0           # cancel if Binance moves this far against us over the last 1 s
ADVERSE_WINDOW_S = 1.0
DAY_STOP         = -10.0         # realised $ in a UTC day -> off for the day
LIFE_STOP        = -20.0         # realised $ lifetime     -> off for good
POST_ONLY        = True
MAX_POSTS_PER_CANDLE = 3   # 09-30: the 17:00 candle took 34 posts and got 0 fills. Hard ceiling.
MIN_LOCK_SHARES  = 1.0     # owner 10-01: a fill below this does not close the candle (dust)
FILL_CHECK_S     = 1.0     # how often a resting order is checked against the venue tape
TICK             = 0.01

HOME        = '/home/ubuntu/maker_probe'
DB_PATH     = HOME + '/maker_probe.sqlite3'
ENABLED_FLAG= HOME + '/ENABLED'
GAMMA_DB    = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
LOGFILE     = '/home/ubuntu/claude-work/repo/analysis/zurich/MAKER_PROBE.txt'
POLY_WS     = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
NUM         = re.compile(r'[-+]?\d*\.?\d+')   # collapses numbers so the gate funnel aggregates
BN_WS       = 'wss://data-stream.binance.vision/ws/btcusdt@aggTrade'


# =================================================================================================
# Pure logic. Everything below this line up to Probe is synchronous and unit-tested with no network.
# =================================================================================================

class Mover:
    """Binance spot ticks, ms resolution, and the adverse-move test.

    Keeps ~5 s of (ts_ms, px). adverse_bps returns the signed move over the last ADVERSE_WINDOW_S
    expressed as "basis points AGAINST the given side", so a positive return is always bad news for
    us whichever side we are on. That sign convention is the whole point: it makes the caller's test
    a single `>= ADVERSE_BPS` and removes the chance of getting the direction backwards for DOWN.
    """
    def __init__(self, keep_s=5.0):
        self.keep_ms = keep_s * 1000.0
        self.ticks = collections.deque()   # (ts_ms, px)

    def add(self, ts_ms, px):
        px = float(px)
        if not (math.isfinite(px) and px > 0): return
        self.ticks.append((float(ts_ms), px))
        cut = float(ts_ms) - self.keep_ms
        while self.ticks and self.ticks[0][0] < cut: self.ticks.popleft()

    def last(self):
        return self.ticks[-1][1] if self.ticks else None

    def adverse_bps(self, side, now_ms=None, window_s=ADVERSE_WINDOW_S):
        """bps of movement AGAINST `side` over the last window. None when we cannot tell."""
        if len(self.ticks) < 2: return None
        now_ms = self.ticks[-1][0] if now_ms is None else float(now_ms)
        cut = now_ms - window_s * 1000.0
        old = None
        for ts, px in self.ticks:            # oldest tick still inside the window
            if ts >= cut: old = px; break
        if old is None or old <= 0: return None
        new = self.ticks[-1][1]
        move = (new / old - 1.0) * 1e4       # + = price up
        return -move if side == 'UP' else move


class Guard:
    """The enable flag and the two hard stops. Every question a caller can ask about 'may I trade'
    goes through here, so there is exactly one place where trading can be switched off."""
    def __init__(self, db, flag_path=ENABLED_FLAG, dry_run=True):
        self.db, self.flag_path, self.dry_run = db, flag_path, dry_run
        self.off_reason = ''

    def flag_on(self):
        try:
            with open(self.flag_path) as f: return f.read().strip() == '1'
        except OSError:
            return False

    def realised(self, day=None):
        """Realised $ over settled fills. day=None -> lifetime; else a 'YYYY-MM-DD' UTC day."""
        q = 'select coalesce(sum(pnl),0) from fills where pnl is not null'
        a = ()
        if day is not None: q += ' and utc_day=?'; a = (day,)
        return float(self.db.execute(q, a).fetchone()[0])

    def may_trade(self, now=None):
        """(bool, reason). Checked before EVERY post, not once at startup."""
        now = time.time() if now is None else now
        day = time.strftime('%Y-%m-%d', time.gmtime(now))
        if self.dry_run:
            self.off_reason = 'DRY-RUN'; return False, self.off_reason
        if not self.flag_on():
            self.off_reason = 'flag off'; return False, self.off_reason
        life = self.realised()
        if life <= LIFE_STOP:
            self.off_reason = f'LIFETIME STOP {life:+.2f} <= {LIFE_STOP}'; return False, self.off_reason
        today = self.realised(day)
        if today <= DAY_STOP:
            self.off_reason = f'DAY STOP {today:+.2f} <= {DAY_STOP} on {day}'; return False, self.off_reason
        self.off_reason = ''
        return True, ''


class Quoter:
    """The rule, as a pure function of the state it is given. No clock, no network, no I/O.

    decide() returns ('post'|'cancel'|'hold'|'none', side, price, reason).

    09-30, AFTER THE FIRST LIVE CANDLE: the original version re-posted whenever the best bid moved
    by a tick. On the 17:00 candle that produced 34 orders in ~2 minutes and ZERO fills - we chased
    the book and were never still long enough to be hit. V's fix, and it is now the rule:
    ONCE POSTED, THE ORDER RESTS. There are exactly four reasons to pull it, and a bid that merely
    moved is not one of them:
        1. Binance moved >= 2 bps against our side over the last second
        2. sec > 180 (or the candle ended, which the loop handles)
        3. our price is no longer <= the best bid - i.e. we would now be the crosser
        4. the best bid has run >= 2 ticks away from us, so we are no longer near the touch
    Plus at most MAX_POSTS_PER_CANDLE posts in one candle, so even a pathological book cannot turn
    this into an order-spam loop again.
    """
    def __init__(self, bid_lo=BID_LO, bid_hi=BID_HI, sec_lo=SEC_LO, sec_hi=SEC_HI):
        self.bid_lo, self.bid_hi, self.sec_lo, self.sec_hi = bid_lo, bid_hi, sec_lo, sec_hi

    @staticmethod
    def favourite(up_bid, dn_bid):
        """Side whose best BID is higher; None if we cannot tell."""
        if up_bid is None or dn_bid is None: return None, None
        if up_bid == dn_bid: return None, None
        return ('UP', float(up_bid)) if up_bid > dn_bid else ('DOWN', float(dn_bid))

    def decide(self, *, sec, up_bid, dn_bid, up_ask, dn_ask, vol, resting, adverse,
               filled_this_candle, posts_this_candle=0, book_fresh=True):
        if filled_this_candle:
            return ('cancel', None, None, 'already filled this candle') if resting else \
                   ('none', None, None, 'already filled this candle')

        # ---------- a resting order: the ONLY TWO reasons to pull it ----------
        # OWNER, 09-30, option A: back to the original spec. The order rests until Binance moves
        # >= 2 bps against us, or 180 s. Nothing about the Polymarket book pulls a resting order.
        #
        # What was removed and why it is safe:
        #   - "bid ran >= 2 ticks away": on the live books this fired constantly. All four calm
        #     candles on 21:00-21:20 hit the 3-post cap, 10 of 12 exits were this rule, and in every
        #     case the new bid was exactly our price + 0.02. These books walk up a tick at a time, so
        #     a 2-tick tolerance is cleared within seconds and we were still chasing, just rate-
        #     limited. Total book time ~10% of the window, 0 fills in 12 orders.
        #   - "our price no longer <= best bid" (V's rule 3): not in the original spec's cancel list,
        #     and now redundant. It could only fire once our order had LEFT the book, and the case
        #     that actually matters there - it left because it FILLED - is caught properly by the
        #     fill check that now runs on every pass and before every cancel. Detecting a fill by
        #     cancelling a resting order was always the wrong instrument.
        # Being alone at the top of the book, the favourite flipping, the bid leaving the band: none
        # of these pull the order. A maker's edge IS sitting still; the 2 bps Binance test is the
        # risk control, and it is faster than anything the book can tell us.
        if resting:
            rs, rp = resting['side'], float(resting['price'])
            if adverse is not None and adverse >= ADVERSE_BPS:
                return 'cancel', rs, rp, f'adverse {adverse:.2f}bps'
            if sec > self.sec_hi or sec < self.sec_lo:
                return 'cancel', rs, rp, f'sec {sec} outside {self.sec_lo}-{self.sec_hi}'
            return 'hold', rs, rp, f'resting {rp:.2f}, sec {sec}'

        # ---------- nothing resting: may we post? ----------
        if sec < self.sec_lo: return 'none', None, None, f'sec {sec} < {self.sec_lo}'
        if sec > self.sec_hi: return 'none', None, None, f'sec {sec} > {self.sec_hi}'
        if posts_this_candle >= MAX_POSTS_PER_CANDLE:
            return 'none', None, None, f'{posts_this_candle} posts this candle (max {MAX_POSTS_PER_CANDLE})'
        if not book_fresh:
            # 09-30 fix (3): after a post-only rejection we do not fire again off the same book read.
            return 'none', None, None, 'awaiting a fresh book after a post-only reject'
        if vol is None: return 'none', None, None, 'vol unavailable'
        if vol >= VOL_CUT: return 'none', None, None, f'vol {vol:.3f} >= {VOL_CUT} (not calm)'
        side, bid = self.favourite(up_bid, dn_bid)
        if side is None: return 'none', None, None, 'no favourite'
        if not (self.bid_lo <= bid <= self.bid_hi):
            return 'none', None, None, f'bid {bid:.2f} outside {self.bid_lo}-{self.bid_hi}'
        ask = up_ask if side == 'UP' else dn_ask
        # NEVER CROSS. post_only is the venue's guarantee; this is ours. The 17:00 candle proved both
        # are needed: 5 of 34 passed this check on our book and were still refused by the venue.
        if ask is None or not (bid < float(ask)):
            return 'none', None, None, f'would cross (bid {bid} >= ask {ask})'
        if adverse is not None and adverse >= ADVERSE_BPS:
            return 'none', None, None, f'adverse {adverse:.2f}bps'
        return 'post', side, bid, f'calm {vol:.3f} fav {side} bid {bid:.2f} sec {sec}'


# =================================================================================================
def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    db.executescript("""
    create table if not exists orders(
      id integer primary key, epoch integer, side text, token text, price real, shares real,
      post_ts_ms integer, venue_order_id text, cancel_ts_ms integer, cancel_reason text,
      status text, dry integer, note text);
    create table if not exists fills(
      id integer primary key, order_row integer, epoch integer, utc_day text, side text,
      fill_ts_ms integer, price real, shares real, spent real,
      bn_before_bps real, bn_after_bps real, outcome text, pnl real);
    create table if not exists decisions(
      id integer primary key, ts_ms integer, epoch integer, sec integer, action text,
      side text, price real, reason text, vol real, up_bid real, dn_bid real,
      up_ask real, dn_ask real, adverse real);
    create index if not exists ix_fills_day on fills(utc_day);
    """)
    db.commit(); return db


def tokens_for(epoch, gamma_db=GAMMA_DB):
    try:
        c = sqlite3.connect(f'file:{gamma_db}?mode=ro', uri=True)
        r = c.execute('select tok_up, tok_dn from mkt where epoch=? and tok_up is not null', (epoch,)).fetchone()
        c.close()
        return (str(r[0]), str(r[1])) if r else (None, None)
    except Exception:
        return None, None


def outcome_for(epoch, gamma_db=GAMMA_DB):
    try:
        c = sqlite3.connect(f'file:{gamma_db}?mode=ro', uri=True)
        r = c.execute('select outcome from mkt where epoch=?', (epoch,)).fetchone()
        c.close()
        return r[0] if r and r[0] else None
    except Exception:
        return None


def settle(db, gamma_db=GAMMA_DB):
    """Attach the venue's own resolution and the realised $ to every filled, unsettled row.

    A maker BUY pays `price` per share and no fee (Polymarket charges the taker). A winning share
    redeems at 1.00. So pnl = shares*(1 - price) on a win and -shares*price on a loss. Settlement is
    the VENUE's resolution, never a Binance close - that is the standing rule for every test here.
    """
    n = 0
    for r in db.execute('select id, epoch, side, price, shares from fills where pnl is null').fetchall():
        o = outcome_for(r['epoch'], gamma_db)
        if not o: continue
        pnl = r['shares'] * (1.0 - r['price']) if o == r['side'] else -r['shares'] * r['price']
        db.execute('update fills set outcome=?, pnl=? where id=?', (o, round(pnl, 6), r['id']))
        n += 1
    if n: db.commit()
    return n


def log(path, line):
    """path first, and always explicit: the tests used to append real rows to the committed
    MAKER_PROBE.txt because log() defaulted to it."""
    with open(path, 'a') as f: f.write(line.rstrip() + '\n')


# =================================================================================================
class Probe:
    """Feeds, orders, and the loop. All decisions come from Quoter; all permission from Guard."""
    def __init__(self, dry_run=True, db=None, gamma_db=GAMMA_DB):
        self.dry_run = dry_run
        self.db = db if db is not None else connect()
        self.gamma_db = gamma_db
        self.guard = Guard(self.db, dry_run=dry_run)
        self.quoter = Quoter()
        self.mover = Mover()
        self.fav = FavBrain()               # only for vol_before_open - the frozen calm definition
        self.books = {}                     # token -> dict(bids=[(px,sz)], asks=[(px,sz)], ts)
        self.resting = None                 # dict(side, price, token, order_id, post_ts_ms, row)
        self.filled_epochs = set()
        self.posts_per_epoch = collections.Counter()   # hard ceiling per candle
        self.stale_book_token = None                   # set by a post-only reject
        self.stale_book_ts = None
        self.reject_lock_s = None                      # (b) integer second of the last post-only reject
        self._last_fill_check = 0.0
        self.broker = None
        self.logfile = LOGFILE   # per-instance so tests never write the committed report
        self.counts = collections.Counter()
        self.funnel = collections.Counter()   # every pass by gate reason, so '0 posts' is explainable
        self.stopped = ''

    # ---- books -------------------------------------------------------------------------------
    def apply_book(self, e):
        t = str(e.get('asset_id') or '')
        if not t: return
        k = e.get('event_type')
        if k == 'book':
            lv = lambda xs: sorted(((float(x['price']), float(x['size'])) for x in (xs or [])),
                                   reverse=True)
            self.books[t] = dict(bids=lv(e.get('bids')), asks=sorted(
                ((float(x['price']), float(x['size'])) for x in (e.get('asks') or []))), ts=time.time())
        elif k == 'price_change':
            b = self.books.get(t)
            if not b: return
            for ch in (e.get('changes') or e.get('price_changes') or []):
                try: px, sz, sd = float(ch['price']), float(ch['size']), str(ch['side']).upper()
                except (KeyError, TypeError, ValueError): continue
                arr = b['bids'] if sd in ('BUY', 'BID') else b['asks']
                arr[:] = [x for x in arr if abs(x[0] - px) > 1e-12]
                if sz > 0: arr.append((px, sz))
                arr.sort(reverse=(arr is b['bids']))
            b['ts'] = time.time()

    def book_fresh(self, token):
        """False only while we are still looking at the very book read that a post-only reject
        came from. Any newer book event on that token clears it."""
        if self.stale_book_token != token: return True
        ts = (self.books.get(token) or {}).get('ts')
        if ts is None: return False
        if self.stale_book_ts is None or ts > self.stale_book_ts:
            self.stale_book_token = self.stale_book_ts = None
            return True
        return False

    def best(self, token):
        b = self.books.get(token)
        if not b: return None, None
        bid = b['bids'][0][0] if b['bids'] else None
        ask = b['asks'][0][0] if b['asks'] else None
        return bid, ask

    # ---- orders ------------------------------------------------------------------------------
    async def place(self, epoch, side, token, price):
        """Sign and post ONE post-only limit BUY. Returns the venue order id, or None."""
        now_ms = int(time.time() * 1000)
        cur = self.db.execute(
            'insert into orders(epoch,side,token,price,shares,post_ts_ms,status,dry) '
            'values(?,?,?,?,?,?,?,?)',
            (epoch, side, token, price, SHARES, now_ms, 'PENDING', int(self.dry_run)))
        self.db.commit(); row = cur.lastrowid
        self.posts_per_epoch[epoch] += 1
        if self.dry_run:
            self.db.execute("update orders set status='DRY' where id=?", (row,)); self.db.commit()
            self.counts['dry_post'] += 1
            return None, row
        signed = await self.broker.client.create_limit_order(
            token_id=token, price=str(price), size=str(SHARES), side='BUY', post_only=POST_ONLY)
        # Belt and braces: the signed object must still be a BUY of our size at our price.
        mk, tk = float(signed.maker_amount), float(signed.taker_amount)
        if tk <= 0 or mk / tk > price + 1e-9:
            self.db.execute("update orders set status='ABORT_PRICE' where id=?", (row,)); self.db.commit()
            raise RuntimeError(f'signed price {mk/tk if tk else 0} exceeds {price}')
        try:
            r = await self.broker.client.post_order(signed)
        except Exception as e:
            # 09-30: a venue rejection used to propagate and leave the row PENDING forever, so the
            # ledger showed orders in an unknown state - which on a shared wallet is indistinguishable
            # from an order that might be resting. It is a REJECTED order and it is recorded as one.
            msg = f'{type(e).__name__}: {e}'
            self.db.execute('update orders set status=?, note=? where id=?', ('REJECTED', msg[:300], row))
            self.db.commit(); self.counts['reject'] += 1
            if 'post-only' in msg or 'crosses book' in msg:
                # (3) do not fire again off the same book read that just produced a crossing price.
                self.stale_book_token = token
                self.stale_book_ts = (self.books.get(token) or {}).get('ts')
                # (b) V: "do not re-post in the same second". The book-freshness test alone is not
                # enough - these books publish many events a second, so it clears instantly. Live
                # proof: two rejects at 21:06:05, same second, same price 0.70.
                self.reject_lock_s = int(time.time())
                self.counts['postonly_reject'] += 1
            log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] REJECTED epoch {epoch} {side} {price} :: {msg[:200]}')
            return None, row
        oid = str(getattr(r, 'order_id', '') or '')
        ok = bool(getattr(r, 'ok', False)) and oid
        self.db.execute('update orders set venue_order_id=?, status=? where id=?',
                        (oid or None, 'OPEN' if ok else 'REJECTED', row))
        self.db.commit()
        self.counts['post' if ok else 'reject'] += 1
        return (oid if ok else None), row

    async def cancel(self, reason):
        """Cancel OUR resting order by id. Never cancel_all - the wallet is shared with 8787."""
        r = self.resting
        if not r: return
        self.resting = None
        now_ms = int(time.time() * 1000)
        self.db.execute('update orders set cancel_ts_ms=?, cancel_reason=?, status=? where id=?',
                        (now_ms, reason, 'CANCELLED', r['row']))
        self.db.commit(); self.counts['cancel'] += 1
        if self.dry_run or not r.get('order_id'): return
        try:
            await self.broker.client.cancel_order(order_id=r['order_id'])
        except Exception as e:
            self.db.execute('update orders set note=? where id=?',
                            (f'cancel raised {type(e).__name__}', r['row']))
            self.db.commit()
            log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] CANCEL ERROR {type(e).__name__} '
                f'order {r["order_id"]} reason {reason}')

    def record_decision(self, epoch, sec, action, side, price, reason, vol, ub, dbid, ua, da, adv):
        self.db.execute('insert into decisions(ts_ms,epoch,sec,action,side,price,reason,vol,'
                        'up_bid,dn_bid,up_ask,dn_ask,adverse) values(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (int(time.time() * 1000), epoch, sec, action, side, price, reason, vol,
                         ub, dbid, ua, da, adv))
        self.db.commit(); self.counts['decision_' + action] += 1

    @staticmethod
    def trade_dead(trade):
        """True if this trade did not stand. TradeStatus is an enum, so str() of it is
        'TradeStatus.FAILED' - which is in no ('FAILED', ...) tuple. Compare on .value."""
        st = getattr(trade, 'status', '')
        st = str(getattr(st, 'value', st)).upper()
        return 'FAIL' in st or 'CANCEL' in st

    @staticmethod
    def matched_by(trade, order_id):
        """(shares, price) OUR order_id got out of one venue trade; (0.0, None) if nothing.

        A trade names the TAKER in `taker_order_id`. When we are the maker - which a post-only
        probe is BY CONSTRUCTION, every time - our order appears only as an entry inside
        `maker_orders[]`. polymarket-client 0.10.0's ClobTrade has no `maker_order_id` field at
        all (models/clob/account.py:132-157), so the old compare against
        getattr(t, 'maker_order_id', '') was '' != our id on every trade on the tape, and not one
        maker fill could ever be seen. It never raised and never logged: check_fill just returned
        False forever. Both hard stops are computed FROM the fills table, so this did not merely
        lose rows - it held the stops open. Found 10-01 after London read 4 buys on the shared
        wallet at 23:46 / 23:51 / 00:26 / 00:31 that match our orders 81 / 82 / 89 / 90 to the
        second, the side, the price and the 5-share size, while this probe recorded 0 fills.
        Both sides are read here so the answer never depends on which side we turned out to be."""
        if Probe.trade_dead(trade): return 0.0, None
        if str(getattr(trade, 'taker_order_id', '')) == order_id:
            return float(trade.size), float(trade.price)
        shares, price = 0.0, None
        for mo in getattr(trade, 'maker_orders', None) or ():
            if str(getattr(mo, 'order_id', '')) != order_id: continue
            shares += float(mo.matched_amount); price = float(mo.price)
        return shares, price

    @staticmethod
    def trade_ts_ms(trade, default_ms):
        """Venue match time in ms. 0.10.0 parses the wire's `match_time` INTO `matched_at`, a
        datetime; the old code read `match_time` off the model, got 0, and fell back to the local
        clock for every fill - the same clock bn_before_bps is then measured against."""
        for name in ('matched_at', 'match_time'):
            v = getattr(trade, name, None)
            if v is None: continue
            if hasattr(v, 'timestamp'):
                try: return int(v.timestamp() * 1000)
                except Exception: continue
            try: return int(float(v) * 1000)
            except (TypeError, ValueError): continue
        return default_ms

    async def scan_tape(self, token, order_id, now_ms):
        """(shares, price, first_match_ts_ms) that order_id has matched on the account tape.

        One 5-share order can arrive as several trades - the owner's app shows our 00:31 order as
        'Buy 2 Down @ 64c' then 'Buy 3 Down @ 64c' - so every trade naming it is summed, and trade
        ids are de-duplicated in case a page repeats one. Raises; the caller records the failure."""
        matched, price, ts_ms, seen = 0.0, None, None, set()
        async for page in self.broker.client.list_account_trades(token_id=token):
            for t in getattr(page, 'items', ()):
                tid = str(getattr(t, 'id', '')) or None
                if tid is not None and tid in seen: continue
                sh, px = self.matched_by(t, order_id)
                if sh <= 0: continue
                if tid is not None: seen.add(tid)
                matched += sh
                if px is not None: price = px
                ts = self.trade_ts_ms(t, now_ms)
                ts_ms = ts if ts_ms is None else min(ts_ms, ts)   # the FIRST match is the fill
            break                                    # newest page only; the tape is newest-first
        return matched, price, ts_ms

    async def check_fill(self, epoch):
        """Has our resting order matched? Venue truth only: the account trade tape."""
        r = self.resting
        if not r or self.dry_run or not r.get('order_id'): return False
        now_ms = int(time.time() * 1000)
        try:
            matched, price, ts_ms = await self.scan_tape(r['token'], r['order_id'], now_ms)
        except Exception as e:
            self.db.execute('update orders set note=? where id=?',
                            (f'fill check {type(e).__name__}', r['row'])); self.db.commit()
            return False
        if matched <= 0: return False
        ts_ms = ts_ms or now_ms
        before = self.mover.adverse_bps(r['side'], now_ms=ts_ms)          # the 1 s BEFORE the fill
        self.db.execute('update orders set status=? where id=?', ('FILLED', r['row'])); self.db.commit()
        self.db.execute('insert into fills(order_row,epoch,utc_day,side,fill_ts_ms,price,shares,spent,'
                        'bn_before_bps) values(?,?,?,?,?,?,?,?,?)',
                        (r['row'], epoch, time.strftime('%Y-%m-%d', time.gmtime(ts_ms / 1000)),
                         r['side'], ts_ms, price, matched, matched * (price or 0), before))
        self.db.commit()
        fill_id = self.db.execute('select max(id) from fills').fetchone()[0]
        # A partial fill leaves the REST of our order live at the venue. Clearing self.resting
        # without pulling it would orphan it: cancel() only ever reaches what self.resting holds,
        # so nothing would cancel it at 180 s, at the candle's end, or at shutdown.
        if SHARES - matched > 1e-9 and r.get('order_id'):
            try:
                await self.broker.client.cancel_order(order_id=r['order_id'])
                self.db.execute('update orders set cancel_ts_ms=?, cancel_reason=? where id=?',
                                (int(time.time() * 1000), f'remainder {SHARES - matched:g}sh after partial fill',
                                 r['row'])); self.db.commit()
            except Exception as e:
                self.db.execute('update orders set note=? where id=?',
                                (f'remainder cancel raised {type(e).__name__}', r['row'])); self.db.commit()
                log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] CANCEL ERROR '
                    f'{type(e).__name__} remainder of order {r["order_id"]}')
            # That cancel can lose a race: the rest of our order may have matched between the scan
            # and the cancel landing - which is exactly the 2-then-3 shape the owner's app showed.
            # Re-read the tape once and amend, whether the cancel raised or not. Without this the
            # extra shares are invisible to the stops in the same way the maker fills were.
            try:
                m2, px2, ts2 = await self.scan_tape(r['token'], r['order_id'], now_ms)
            except Exception as e:
                m2 = 0.0
                log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] AMEND ERROR '
                    f'{type(e).__name__} re-reading tape for order {r["order_id"]}')
            if m2 > matched + 1e-9:
                price = px2 if px2 is not None else price
                ts_ms = min(ts_ms, ts2) if ts2 else ts_ms
                self.db.execute('update fills set shares=?, spent=?, price=?, fill_ts_ms=?, '
                                'utc_day=? where id=?',
                                (m2, m2 * (price or 0), price, ts_ms,
                                 time.strftime('%Y-%m-%d', time.gmtime(ts_ms / 1000)), fill_id))
                self.db.commit()
                log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] FILL AMENDED epoch '
                    f'{epoch} {matched:g}sh -> {m2:g}sh @ {price} (raced the remainder cancel)')
                matched = m2
        # OWNER APPROVED 10-01 11:5x ("I approve, send it to Zurich"): a fill UNDER 1.0 share does
        # NOT set filled-this-candle. Its ledger row and pnl stay, and it still counts toward both
        # stops - the ONLY thing it no longer does is burn the candle.
        # Why: on 10-01 11:40 a 0.01-share fill - seven tenths of a cent - locked a whole candle and
        # blocked 11 passes. One-fill-per-candle exists to cap EXPOSURE, and dust is not exposure;
        # letting it close a candle biased the two things this probe measures, the fill RATE (every
        # dust fill burns a candle that could have produced a real one) and the adverse-fill series
        # (a 0.01-share outcome is noise whichever way it lands).
        # Exposure bound is unchanged in spirit and stated: with max 3 posts a candle the worst case
        # is 2 x 0.99 + 5 shares, because only a sub-1-share fill declines to lock.
        if matched >= MIN_LOCK_SHARES:
            self.filled_epochs.add(epoch)
        self.resting = None; self.counts['fill'] += 1
        self.counts['dust_fill' if matched < MIN_LOCK_SHARES else 'lock_fill'] += 1
        log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] FILL epoch {epoch} {r["side"]} '
            f'{matched:g}sh @ {price} bn_before {before if before is None else round(before,2)}bps'
            + ('' if matched >= MIN_LOCK_SHARES else f' DUST (<{MIN_LOCK_SHARES}sh): candle stays open'))
        # the 1 s AFTER the fill is the adverse-fill measurement; recorded a second later
        asyncio.ensure_future(self._after(epoch, r['side'], ts_ms))
        return True

    async def _after(self, epoch, side, fill_ts_ms):
        await asyncio.sleep(1.2)
        a = self.mover.adverse_bps(side, window_s=ADVERSE_WINDOW_S)
        self.db.execute('update fills set bn_after_bps=? where epoch=? and bn_after_bps is null',
                        (a, epoch)); self.db.commit()

    # ---- feeds -------------------------------------------------------------------------------
    async def binance_loop(self):
        import websockets
        while True:
            try:
                async with websockets.connect(BN_WS, ping_interval=20, max_size=2 ** 20) as w:
                    while True:
                        j = json.loads(await asyncio.wait_for(w.recv(), 30))
                        if 'p' in j and 'T' in j: self.mover.add(int(j['T']), float(j['p']))
            except Exception:
                await asyncio.sleep(1)

    async def book_loop(self):
        import websockets
        while True:
            ep = int(time.time() // 300) * 300
            nxt = tokens_for(ep + 300, self.gamma_db)
            toks = [t for t in tokens_for(ep, self.gamma_db) + nxt if t]
            if not toks:
                await asyncio.sleep(2); continue
            # The gamma mirror often does not carry the NEXT candle yet, so this subscription may hold
            # only the current pair. If so, hold it until the roll and resubscribe at once - otherwise
            # the old ep+345 bound leaves us with stale tokens for the first 45 s of the next candle.
            # That is outside the 60-180 s window today, but it is exactly the kind of silent blindness
            # that becomes a bug the moment the window widens.
            deadline = ep + 345 if all(nxt) else ep + 300
            try:
                async with websockets.connect(POLY_WS, ping_interval=None, max_size=2 ** 23) as w:
                    await w.send(json.dumps({'assets_ids': toks, 'type': 'market'}))
                    async def ping():
                        while True: await asyncio.sleep(5); await w.send('PING')
                    task = asyncio.ensure_future(ping())
                    try:
                        while time.time() < deadline:
                            m = await asyncio.wait_for(w.recv(), 15)
                            if isinstance(m, (bytes, bytearray)): m = m.decode('utf-8', 'replace')
                            if not str(m).strip() or m == 'PONG': continue
                            try: d = json.loads(m)
                            except ValueError: continue
                            for e in (d if isinstance(d, list) else [d]):
                                if isinstance(e, dict): self.apply_book(e)
                    finally:
                        task.cancel(); await asyncio.gather(task, return_exceptions=True)
            except Exception:
                await asyncio.sleep(1)

    # ---- the loop ----------------------------------------------------------------------------
    async def trade_loop(self, until=None):
        while until is None or time.time() < until:
            await asyncio.sleep(0.2)
            try:
                await self.one_pass()
            except Exception as e:
                log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] PASS ERROR {type(e).__name__}: {e}')
                self.counts['error'] += 1
                await asyncio.sleep(1)

    async def one_pass(self, now=None):
        # `now` is injectable so the post path can be tested at a chosen second in the candle.
        # The 30 min dry run never saw a calm candle, so without this the posting path would be
        # covered only by tests that skip whenever the wall clock sits outside 60-180 s.
        now = time.time() if now is None else now
        ep = int(now // 300) * 300; sec = int(now - ep)
        # (a) SEE EVERY FILL. Both hard stops are computed FROM the fills table, so a fill that is
        # never recorded does not merely lose a row - it disables the stops. check_fill used to run
        # only on a 'hold', which meant a fill followed by a cancel on the same pass vanished.
        # Checked here, before any decision is acted on, and again unconditionally before a cancel.
        # Throttled to FILL_CHECK_S while resting because check_fill is a venue REST call and the
        # loop runs 5x a second; the pre-cancel check ignores the throttle, so no cancel can ever
        # discard a fill however recently we last looked.
        if self.resting and not self.dry_run and (now - self._last_fill_check) >= FILL_CHECK_S:
            self._last_fill_check = now
            if await self.check_fill(ep):
                self.record_decision(ep, sec, 'fill', None, None, 'fill seen on routine check',
                                     None, None, None, None, None, None)
                return
        # A resting order never survives its own candle.
        if self.resting and self.resting['epoch'] != ep:
            if not self.dry_run and await self.check_fill(ep): return
            await self.cancel('candle_end')
        tok_up, tok_dn = tokens_for(ep, self.gamma_db)
        if not tok_up or not tok_dn: return
        ub, ua = self.best(tok_up); dbid, da = self.best(tok_dn)
        vol = self.fav.vol_before_open(ep)
        side_r = self.resting['side'] if self.resting else None
        adv = self.mover.adverse_bps(side_r) if side_r else None
        # (The dry-mode hack that injected our virtual order as the best bid is gone with the
        # bid-based resting checks it existed to model - no resting decision reads the book now.)
        fav_side, _ = Quoter.favourite(ub, dbid)
        fresh = self.book_fresh(tok_up if fav_side == 'UP' else tok_dn) if fav_side else True
        if self.reject_lock_s is not None:
            if int(now) <= self.reject_lock_s: fresh = False        # (b) same-second lockout
            else: self.reject_lock_s = None
        act, side, price, reason = self.quoter.decide(
            sec=sec, up_bid=ub, dn_bid=dbid, up_ask=ua, dn_ask=da, vol=vol,
            resting=self.resting, adverse=adv, filled_this_candle=(ep in self.filled_epochs),
            posts_this_candle=self.posts_per_epoch[ep], book_fresh=fresh)
        self.funnel[NUM.sub('N', reason)] += 1
        if act == 'cancel':
            # Unconditional, throttle or no throttle: a cancel must never be able to discard a fill.
            if not self.dry_run and await self.check_fill(ep):
                self.record_decision(ep, sec, 'fill', side, price,
                                     f'filled before cancel ({reason})', vol, ub, dbid, ua, da, adv)
                return
            self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
            await self.cancel(reason); return
        if act == 'post':
            if self.dry_run:
                # A dry run must SHOW the decision it would have made. Routing it through
                # guard.may_trade() would only ever record "BLOCKED: DRY-RUN" and tell us nothing
                # about the rule. place() is still the only thing that can sign, and it returns a
                # DRY row without touching the broker (self.broker is None in a dry run).
                self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
                tokd = tok_up if side == 'UP' else tok_dn
                _, rowd = await self.place(ep, side, tokd, price)
                # Keep a VIRTUAL resting order (order_id None, so cancel()/check_fill() never reach
                # the venue). Without this nothing rests, every pass re-posts, and a dry run measures
                # the per-candle cap instead of the no-chase rule it exists to test.
                self.resting = dict(epoch=ep, side=side, price=price, token=tokd,
                                    order_id=None, post_ts_ms=int(now * 1000), row=rowd)
                return
            ok, why = self.guard.may_trade(now)
            if not ok:
                self.record_decision(ep, sec, 'blocked', side, price, f'{reason} | BLOCKED: {why}',
                                     vol, ub, dbid, ua, da, adv)
                if why.startswith(('DAY STOP', 'LIFETIME STOP')) and self.stopped != why:
                    self.stopped = why
                    log(self.logfile, f'[{time.strftime("%F %T", time.gmtime())}] HARD STOP: {why}')
                return
            self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
            tok = tok_up if side == 'UP' else tok_dn
            oid, row = await self.place(ep, side, tok, price)
            if oid or self.dry_run:
                # A dry run keeps a VIRTUAL resting order (order_id None, so cancel() and
                # check_fill() never touch the venue). Without it nothing ever rests, every pass
                # re-posts, and a dry run measures only the per-candle cap instead of the no-chase
                # rule it is supposed to be testing. Found 09-30 when the first post-fix dry run
                # reported exactly 3 posts on all 3 calm candles - the cap, not the rule.
                self.resting = dict(epoch=ep, side=side, price=price, token=tok,
                                    order_id=oid, post_ts_ms=int(now * 1000), row=row)
            return
        if act == 'hold' and not self.dry_run and (now - self._last_fill_check) >= FILL_CHECK_S:
            self._last_fill_check = now
            if await self.check_fill(ep): return
        if self.counts['pass'] % 50 == 0:
            self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
        self.counts['pass'] += 1

    async def run(self, dry_seconds=None):
        if not self.dry_run:
            from poly_live import LiveBroker
            self.broker = LiveBroker(None); await self.broker.open()
        until = (time.time() + dry_seconds) if dry_seconds else None
        tasks = [asyncio.ensure_future(self.binance_loop()),
                 asyncio.ensure_future(self.book_loop()),
                 asyncio.ensure_future(self.trade_loop(until))]
        try:
            await tasks[-1]
        finally:
            if self.resting: await self.cancel('shutdown')
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def summarise(db):
    d = dict(db.execute('select action, count(*) from decisions group by action').fetchall())
    o = dict(db.execute('select status, count(*) from orders group by status').fetchall())
    f = db.execute('select count(*), coalesce(sum(pnl),0) from fills').fetchone()
    return d, o, f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--minutes', type=float, default=None)
    ap.add_argument('--settle', action='store_true')
    ap.add_argument('--status', action='store_true')
    a = ap.parse_args()
    db = connect()
    if a.settle:
        print('settled', settle(db)); return
    if a.status:
        d, o, f = summarise(db)
        print('decisions', d); print('orders', o); print('fills', f[0], 'pnl', round(f[1], 4))
        g = Guard(db, dry_run=False)
        print('flag_on', g.flag_on(), '| may_trade', g.may_trade()); return
    p = Probe(dry_run=a.dry_run)
    if not a.dry_run:
        ok, why = p.guard.may_trade()
        if not ok:
            print(f'REFUSING TO START LIVE: {why}'); sys.exit(1)
    asyncio.run(p.run(dry_seconds=(a.minutes * 60) if a.minutes else None))
    d, o, f = summarise(db)
    print('decisions', d); print('orders', o); print('counts', dict(p.counts))
    print('FUNNEL (every pass, numbers collapsed to N):')
    for k, v in p.funnel.most_common(): print(f'   {v:7d}  {k}')


if __name__ == '__main__':
    main()
