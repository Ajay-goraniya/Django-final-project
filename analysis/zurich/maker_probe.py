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

    decide() returns one of:
      ('post',   side, price, reason)   - no order resting, conditions hold
      ('cancel', side, price, reason)   - an order is resting and must come off NOW
      ('hold',   None, None, reason)    - resting order stays where it is
      ('none',   None, None, reason)    - nothing to do
    Re-joining a risen bid is expressed as a cancel with reason 'bid_moved'; the next pass posts
    again. That keeps "one open order at a time" true by construction rather than by care.
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
               filled_this_candle):
        if filled_this_candle:
            return ('cancel', None, None, 'already filled this candle') if resting else \
                   ('none', None, None, 'already filled this candle')
        # --- reasons to pull an order that is already resting, strongest first ---
        if resting:
            if adverse is not None and adverse >= ADVERSE_BPS:
                return 'cancel', resting['side'], resting['price'], f'adverse {adverse:.2f}bps'
            if sec > self.sec_hi:
                return 'cancel', resting['side'], resting['price'], f'sec {sec} > {self.sec_hi}'
        if sec < self.sec_lo:
            return ('cancel', resting['side'], resting['price'], f'sec {sec} < {self.sec_lo}') if resting \
                   else ('none', None, None, f'sec {sec} < {self.sec_lo}')
        if sec > self.sec_hi:
            return 'none', None, None, f'sec {sec} > {self.sec_hi}'
        if vol is None:
            return ('cancel', resting['side'], resting['price'], 'vol unavailable') if resting \
                   else ('none', None, None, 'vol unavailable')
        if vol >= VOL_CUT:
            return ('cancel', resting['side'], resting['price'], f'vol {vol:.3f} >= {VOL_CUT}') if resting \
                   else ('none', None, None, f'vol {vol:.3f} >= {VOL_CUT} (not calm)')
        side, bid = self.favourite(up_bid, dn_bid)
        if side is None:
            return ('cancel', resting['side'], resting['price'], 'no favourite') if resting \
                   else ('none', None, None, 'no favourite')
        if not (self.bid_lo <= bid <= self.bid_hi):
            return ('cancel', resting['side'], resting['price'], f'bid {bid:.2f} outside band') if resting \
                   else ('none', None, None, f'bid {bid:.2f} outside {self.bid_lo}-{self.bid_hi}')
        ask = up_ask if side == 'UP' else dn_ask
        # NEVER CROSS. post_only on the signed order is the venue's guarantee; this is ours, and it
        # is the one that also catches a book we have misread rather than only a book that moved.
        if ask is None or not (bid < float(ask)):
            return ('cancel', resting['side'], resting['price'], 'would cross') if resting \
                   else ('none', None, None, f'would cross (bid {bid} >= ask {ask})')
        if adverse is not None and adverse >= ADVERSE_BPS:
            return ('cancel', resting['side'], resting['price'], f'adverse {adverse:.2f}bps') if resting \
                   else ('none', None, None, f'adverse {adverse:.2f}bps')
        if resting:
            if resting['side'] != side:
                return 'cancel', resting['side'], resting['price'], 'favourite flipped'
            if abs(resting['price'] - bid) > 1e-9:
                return 'cancel', resting['side'], resting['price'], 'bid_moved'
            return 'hold', side, bid, 'resting at best bid'
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


def log(line, path=LOGFILE):
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
        self.broker = None
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
        r = await self.broker.client.post_order(signed)
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
            log(f'[{time.strftime("%F %T", time.gmtime())}] CANCEL ERROR {type(e).__name__} '
                f'order {r["order_id"]} reason {reason}')

    def record_decision(self, epoch, sec, action, side, price, reason, vol, ub, dbid, ua, da, adv):
        self.db.execute('insert into decisions(ts_ms,epoch,sec,action,side,price,reason,vol,'
                        'up_bid,dn_bid,up_ask,dn_ask,adverse) values(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (int(time.time() * 1000), epoch, sec, action, side, price, reason, vol,
                         ub, dbid, ua, da, adv))
        self.db.commit(); self.counts['decision_' + action] += 1

    async def check_fill(self, epoch):
        """Has our resting order matched? Venue truth only: the account trade tape, then get_order."""
        r = self.resting
        if not r or self.dry_run or not r.get('order_id'): return False
        matched, price, ts_ms = 0.0, None, None
        try:
            async for page in self.broker.client.list_account_trades(token_id=r['token']):
                for t in getattr(page, 'items', ()):
                    if str(getattr(t, 'maker_order_id', '')) != r['order_id']: continue
                    if str(getattr(t, 'status', '')).upper() in ('FAILED', 'CANCELLED', 'CANCELED'): continue
                    matched += float(t.size); price = float(t.price)
                    ts_ms = int(float(getattr(t, 'match_time', 0) or time.time()) * 1000)
                break                                    # newest page only; a 5-share fill is one trade
        except Exception as e:
            self.db.execute('update orders set note=? where id=?',
                            (f'fill check {type(e).__name__}', r['row'])); self.db.commit()
            return False
        if matched <= 0: return False
        ts_ms = ts_ms or int(time.time() * 1000)
        before = self.mover.adverse_bps(r['side'], now_ms=ts_ms)          # the 1 s BEFORE the fill
        self.db.execute('update orders set status=? where id=?', ('FILLED', r['row'])); self.db.commit()
        self.db.execute('insert into fills(order_row,epoch,utc_day,side,fill_ts_ms,price,shares,spent,'
                        'bn_before_bps) values(?,?,?,?,?,?,?,?,?)',
                        (r['row'], epoch, time.strftime('%Y-%m-%d', time.gmtime(ts_ms / 1000)),
                         r['side'], ts_ms, price, matched, matched * (price or 0), before))
        self.db.commit()
        self.filled_epochs.add(epoch); self.resting = None; self.counts['fill'] += 1
        log(f'[{time.strftime("%F %T", time.gmtime())}] FILL epoch {epoch} {r["side"]} '
            f'{matched:g}sh @ {price} bn_before {before if before is None else round(before,2)}bps')
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
                log(f'[{time.strftime("%F %T", time.gmtime())}] PASS ERROR {type(e).__name__}: {e}')
                self.counts['error'] += 1
                await asyncio.sleep(1)

    async def one_pass(self, now=None):
        # `now` is injectable so the post path can be tested at a chosen second in the candle.
        # The 30 min dry run never saw a calm candle, so without this the posting path would be
        # covered only by tests that skip whenever the wall clock sits outside 60-180 s.
        now = time.time() if now is None else now
        ep = int(now // 300) * 300; sec = int(now - ep)
        # A resting order never survives its own candle.
        if self.resting and self.resting['epoch'] != ep:
            await self.cancel('candle_end')
        tok_up, tok_dn = tokens_for(ep, self.gamma_db)
        if not tok_up or not tok_dn: return
        ub, ua = self.best(tok_up); dbid, da = self.best(tok_dn)
        vol = self.fav.vol_before_open(ep)
        side_r = self.resting['side'] if self.resting else None
        adv = self.mover.adverse_bps(side_r) if side_r else None
        act, side, price, reason = self.quoter.decide(
            sec=sec, up_bid=ub, dn_bid=dbid, up_ask=ua, dn_ask=da, vol=vol,
            resting=self.resting, adverse=adv, filled_this_candle=(ep in self.filled_epochs))
        self.funnel[NUM.sub('N', reason)] += 1
        if act == 'cancel':
            self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
            await self.cancel(reason); return
        if act == 'post':
            if self.dry_run:
                # A dry run must SHOW the decision it would have made. Routing it through
                # guard.may_trade() would only ever record "BLOCKED: DRY-RUN" and tell us nothing
                # about the rule. place() is still the only thing that can sign, and it returns a
                # DRY row without touching the broker (self.broker is None in a dry run).
                self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
                await self.place(ep, side, (tok_up if side == 'UP' else tok_dn), price)
                return
            ok, why = self.guard.may_trade(now)
            if not ok:
                self.record_decision(ep, sec, 'blocked', side, price, f'{reason} | BLOCKED: {why}',
                                     vol, ub, dbid, ua, da, adv)
                if why.startswith(('DAY STOP', 'LIFETIME STOP')) and self.stopped != why:
                    self.stopped = why
                    log(f'[{time.strftime("%F %T", time.gmtime())}] HARD STOP: {why}')
                return
            self.record_decision(ep, sec, act, side, price, reason, vol, ub, dbid, ua, da, adv)
            tok = tok_up if side == 'UP' else tok_dn
            oid, row = await self.place(ep, side, tok, price)
            if oid or self.dry_run:
                self.resting = dict(epoch=ep, side=side, price=price, token=tok,
                                    order_id=oid, post_ts_ms=int(now * 1000), row=row)
                if self.dry_run: self.resting = None      # nothing rests in a dry run
            return
        if act == 'hold':
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
