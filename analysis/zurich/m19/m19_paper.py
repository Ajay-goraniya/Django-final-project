#!/usr/bin/env python3
"""M19 fair-value two-sided maker - LIVE PAPER SHADOW on Zurich. PLACES NO ORDERS.

Why it exists: M19 passed its prereg (analysis/v/maker2/M19_RESULT.txt) but its edge is a SPEED bet -
+0.06..+0.11/$ with a ~1 s reaction, ~0 at 2 s. Simulation cannot answer whether this box can quote
that fast, or whether the prints that went through our virtual bid would really have reached us. So
this process does the real thing with virtual money: real Binance ticks, the real Polymarket market
socket, real wall-clock delay, no orders and no credentials.

HARD BOUNDARIES (V, 10-02): no orders, no trading key, no change to the maker probe or the v12
engine, own database, own process. Everything it reads is read-only: the gamma mirror for tokens and
settlement, two public websockets, and one public REST endpoint for the round-trip measurement.

ARMS: m (margin) in {0.15, 0.20} x D (reaction delay, ms) in {300, 700, 1000, 1500}. D is applied
honestly: a quote derived from a Binance tick at T is not live until T + D, so a print that arrives
before then cannot fill it. The 1 s sim row ("lat 2" after V's correction) is D ~= 1000.
"""
import asyncio, collections, json, math, os, sqlite3, sys, time, urllib.request
import datetime as dt

sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
from maker_probe import tokens_for, outcome_for, GAMMA_DB      # read-only sqlite helpers only

HOME   = '/home/ubuntu/m19_paper'
DB     = f'{HOME}/m19_paper.sqlite3'
LOG    = f'{HOME}/m19.log'
HB     = f'{HOME}/m19.heartbeat'
BN_WS  = 'wss://data-stream.binance.vision/ws/btcusdt@aggTrade'
BN_DB  = '/home/ubuntu/pm_multi/bn_flow.sqlite3'   # read-only WARM START, so sigma is not blind
POLY_WS= 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
RTT_URL= 'https://clob.polymarket.com/time'        # public read endpoint, no credentials
UA     = 'Mozilla/5.0 (zurich-m19-paper)'          # urllib's default UA gets refused by the CLOB
FF_MAX_S = 10                                      # forward-fill a print-less second, as FavBrain does

K        = 1.4                 # fitted on M19's TRAIN only; frozen here, never re-fitted live
MARGINS  = (0.15, 0.20)
DELAYS   = (300, 700, 1000, 1500)
SHARES   = 5.0
MIN_THRU = 5.0                 # shares traded strictly below our bid before we call it a fill
BID_LO, BID_HI = 0.05, 0.90
SEC_LO, SEC_HI = 30, 270
TICK_S   = 0.2                 # recompute the fair price every 200 ms
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))


def log(line):
    with open(LOG, 'a') as f:
        f.write(f'[{dt.datetime.now(dt.UTC):%F %T}] {line}\n')


def connect():
    db = sqlite3.connect(DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
      create table if not exists quotes(
        id integer primary key, ts_ms integer, epoch integer, sec integer, m real,
        token text, side text, bid real, fair real, spot real, sig real, tick_ms integer);
      create table if not exists fills(
        id integer primary key, ts_ms integer, epoch integer, utc_day text, m real, delay_ms integer,
        token text, side text, bid real, shares real, spent real, fair real, sec integer,
        thru_shares real, print_price real, outcome text, pnl real);
      create table if not exists rtt(ts_ms integer, ms real, code integer);
      create table if not exists health(ts_ms integer, bn_ticks integer, poly_msgs integer,
        poly_trades integer, quotes integer, fills integer, note text);
      create index if not exists fills_open on fills(pnl) where pnl is null;''')
    db.commit()
    return db


class Fair:
    """Binance ticks -> (spot, sigma, open line O, fair p_up). The definitions are M19's, verbatim:
    O = mean price over [open, open+60), running before sec 60; sig = std of 1 s log returns over the
    PRIOR 300 s; tau = seconds left; p_up = Phi(ln(S/O) / (K*sig*sqrt(tau)))."""

    def __init__(self):
        self.sec_px = {}            # unix second -> last price in that second
        self.last = None            # (ts_ms, px)
        self.n = 0
        self.warm = self.warm_start()

    def warm_start(self):
        """Load the last ~20 min of 1 s spot from the engine's bn_flow recorder, read-only.

        Found by the 2 min smoke test: without this the process quotes NOTHING for its first five
        minutes, because sigma needs 240 of the 300 seconds BEFORE the candle opened and a cold
        start has none of them. Silence would have looked like 'no opportunities' instead of 'no
        data' - the failure this project keeps hitting."""
        n = 0
        try:
            c = sqlite3.connect(f'file:{BN_DB}?mode=ro', uri=True)
            cut = (int(time.time()) - 1200) * 1000
            for tms, px in c.execute("SELECT ts_ms,px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                                     "AND ts_ms>=? ORDER BY ts_ms", (cut,)):
                self.sec_px[int(tms) // 1000] = float(px); n += 1
            c.close()
        except Exception as e:
            log(f'WARM START failed {type(e).__name__}: {e}')
        return n

    def window(self, a, b):
        """Prices on [a,b) with print-less seconds forward-filled up to FF_MAX_S - the same
        construction poly_fav.FavBrain._series() uses, so a quiet second is a ZERO return and not a
        return taken across a hole. Reimplementing that wrong is what broke the /maker page."""
        out, last, held = [], None, 0
        for t in range(a, b):
            if t in self.sec_px:
                last, held = self.sec_px[t], 0
            else:
                held += 1
                if held > FF_MAX_S: continue
            if last is not None: out.append(last)
        return out

    def add(self, ts_ms, px):
        if not (math.isfinite(px) and px > 0): return
        self.last = (int(ts_ms), float(px))
        self.sec_px[int(ts_ms) // 1000] = float(px)
        self.n += 1
        if len(self.sec_px) > 1200:                    # keep ~20 min
            cut = max(self.sec_px) - 900
            for t in [t for t in self.sec_px if t < cut]: del self.sec_px[t]

    def sigma(self, upto_s):
        w = self.window(upto_s - 300, upto_s)
        if len(w) < 240: return None
        m = [math.log(w[i + 1] / w[i]) for i in range(len(w) - 1)]
        mu = sum(m) / len(m)
        return math.sqrt(sum((x - mu) ** 2 for x in m) / len(m))

    def open_line(self, ep, now_s):
        end = min(now_s, ep + 60)
        w = self.window(ep, end) if end > ep else []
        return (sum(w) / len(w)) if w else None

    def fair(self, ep, now_s):
        """(p_up, spot, sig, tick_ms) or None. tick_ms is the Binance tick this is derived from -
        the clock that the reaction delay is measured FROM."""
        if self.last is None: return None
        sig = self.sigma(ep)                      # prior 300 s, i.e. before the candle opened
        O = self.open_line(ep, now_s)
        tau = (ep + 300) - now_s
        if not sig or not O or tau <= 0 or sig <= 0: return None
        S = self.last[1]
        return Phi(math.log(S / O) / (K * sig * math.sqrt(tau))), S, sig, self.last[0]


class Shadow:
    def __init__(self):
        self.db = connect()
        self.fv = Fair()
        self.books = {}
        self.hist = collections.defaultdict(collections.deque)   # m -> deque of quote snapshots
        self.last_bid = {}                                       # (m, token) -> last logged bid
        self.filled = set()                                      # (m, D, token, epoch)
        self.thru = collections.defaultdict(float)               # (m,D,token,second) -> shares
        self.toks = {}                                           # epoch -> (up, dn)
        self.c = collections.Counter()
        self.rtt = collections.deque(maxlen=120)

    # ---- feeds ---------------------------------------------------------------------------------
    async def bn_loop(self):
        import websockets
        while True:
            try:
                async with websockets.connect(BN_WS, ping_interval=20, max_size=2 ** 20) as w:
                    while True:
                        j = json.loads(await asyncio.wait_for(w.recv(), 30))
                        if 'p' in j and 'T' in j:
                            self.fv.add(int(j['T']), float(j['p'])); self.c['bn'] += 1
            except Exception as e:
                self.c['bn_err'] += 1; log(f'BN feed {type(e).__name__}: {e}')
                await asyncio.sleep(1)

    def token_side(self, token, ep):
        up, dn = self.tokens(ep)
        return 'UP' if token == up else ('DOWN' if token == dn else None)

    def tokens(self, ep):
        """Token pair for a candle, cached - but ONLY when the answer is complete.

        10-02 01:3x, the first real defect of this run and it was silent. poly_loop looks the NEXT
        candle up (`self.tokens(ep + 300)`) to subscribe early. The gamma mirror does not carry a
        future candle yet, so that returned (None, None) - and the old version CACHED it. Five
        minutes later, when that epoch became the current one, the cache answered (None, None)
        again, forever. Consequences, all of them quiet: poly_loop took its `if not toks: sleep(2)`
        branch with no counter and no exception, and quote_loop found no token to write a row
        against. Binance ticks kept climbing while poly_msgs and quotes froze at 00:53 with
        errs bn0 poly0 q0 - 'silence is not success' in its purest form, caught only because the
        heartbeat prints the counters side by side. A miss is now never cached, so it is retried."""
        t = self.toks.get(ep)
        if t is None or not all(t):
            t = tokens_for(ep)
            if all(t):
                self.toks[ep] = t
                for k in [k for k in self.toks if k < ep - 1200]: del self.toks[k]
        return t

    async def poly_loop(self):
        import websockets
        while True:
            ep = int(time.time() // 300) * 300
            nxt = self.tokens(ep + 300)
            toks = [t for t in self.tokens(ep) + nxt if t]
            if not toks:
                self.c['no_tokens'] += 1
                if self.c['no_tokens'] % 30 == 1:
                    log(f'NO TOKENS for epoch {ep} (gamma mirror); subscription idle, '
                        f'{self.c["no_tokens"]} passes so far')
                await asyncio.sleep(2); continue
            deadline = ep + 345 if all(nxt) else ep + 300
            try:
                async with websockets.connect(POLY_WS, ping_interval=None, max_size=2 ** 23) as w:
                    await w.send(json.dumps({'assets_ids': toks, 'type': 'market'}))
                    async def ping():
                        while True:
                            await asyncio.sleep(5); await w.send('PING')
                    task = asyncio.ensure_future(ping())
                    try:
                        while time.time() < deadline:
                            m = await asyncio.wait_for(w.recv(), 15)
                            if isinstance(m, (bytes, bytearray)): m = m.decode('utf-8', 'replace')
                            if not str(m).strip() or m == 'PONG': continue
                            try: d = json.loads(m)
                            except ValueError: continue
                            for e in (d if isinstance(d, list) else [d]):
                                if isinstance(e, dict): self.on_event(e)
                    finally:
                        task.cancel(); await asyncio.gather(task, return_exceptions=True)
            except Exception as e:
                self.c['poly_err'] += 1
                await asyncio.sleep(1)

    def on_event(self, e):
        self.c['poly'] += 1
        et = str(e.get('event_type') or e.get('type') or '')
        self.c[f'ev:{et}'] += 1
        if et in ('book', 'price_change', 'tick_size_change'):
            return                                   # the book is not needed for a trade-through test
        # A TRADE. The market channel has used both 'last_trade_price' and 'trade'; accept anything
        # that carries an asset, a price and a size rather than guessing one shape.
        tok = str(e.get('asset_id') or e.get('asset') or '')
        try:
            px = float(e.get('price')); sz = float(e.get('size'))
        except (TypeError, ValueError):
            return
        if not tok or not (0 < px < 1) or sz <= 0: return
        ts_ms = int(e.get('timestamp') or e.get('match_time') or time.time() * 1000)
        if ts_ms < 10 ** 12: ts_ms *= 1000           # some payloads send seconds
        self.c['trade'] += 1
        self.on_trade(tok, px, sz, ts_ms)

    # ---- the virtual book ----------------------------------------------------------------------
    def live_quote(self, m, delay_ms, now_ms):
        """The quote this arm would ACTUALLY have resting now: the newest snapshot whose Binance
        tick is at least `delay_ms` old. This is the whole experiment - D is not a fudge factor
        applied to the result, it decides which prints could have hit us."""
        for q in reversed(self.hist[m]):
            if q['tick_ms'] + delay_ms <= now_ms:
                return q
        return None

    def on_trade(self, token, px, sz, ts_ms):
        ep = int(ts_ms / 1000 // 300) * 300
        side = self.token_side(token, ep)
        if side is None: return
        sec = int(ts_ms / 1000) - ep
        if not (SEC_LO <= sec <= SEC_HI): return
        for m in MARGINS:
            for D in DELAYS:
                if (m, D, token, ep) in self.filled: continue
                q = self.live_quote(m, D, ts_ms)
                if not q or q['epoch'] != ep: continue
                bid = q['up_bid'] if side == 'UP' else q['dn_bid']
                if bid is None or not (BID_LO <= bid <= BID_HI): continue
                if px >= bid: continue                      # STRICTLY below our bid only
                k = (m, D, token, int(ts_ms // 1000))
                self.thru[k] += sz
                if self.thru[k] < MIN_THRU: continue
                self.filled.add((m, D, token, ep))
                self.db.execute(
                    'insert into fills(ts_ms,epoch,utc_day,m,delay_ms,token,side,bid,shares,spent,'
                    'fair,sec,thru_shares,print_price) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ts_ms, ep, dt.datetime.fromtimestamp(ep, dt.UTC).strftime('%Y-%m-%d'), m, D,
                     token, side, bid, SHARES, SHARES * bid, q['fair'], sec, self.thru[k], px))
                self.db.commit(); self.c['fill'] += 1
                log(f'PAPER FILL m{m} D{D} {side} 5sh @ {bid:.2f} (print {px:.2f} x{sz:g}, '
                    f'fair {q["fair"]:.3f}, sec {sec})')

    async def quote_loop(self):
        while True:
            await asyncio.sleep(TICK_S)
            try:
                now = time.time(); now_ms = int(now * 1000)
                ep = int(now // 300) * 300; sec = int(now - ep)
                f = self.fv.fair(ep, int(now))
                if not f: continue
                p_up, S, sig, tick_ms = f
                up, dn = self.tokens(ep)
                for m in MARGINS:
                    ub = math.floor((p_up - m) * 100) / 100
                    db_ = math.floor((1 - p_up - m) * 100) / 100
                    ub = ub if (SEC_LO <= sec <= SEC_HI and BID_LO <= ub <= BID_HI) else None
                    db_ = db_ if (SEC_LO <= sec <= SEC_HI and BID_LO <= db_ <= BID_HI) else None
                    snap = dict(epoch=ep, sec=sec, tick_ms=tick_ms, fair=p_up, up_bid=ub, dn_bid=db_)
                    h = self.hist[m]
                    h.append(snap)
                    while h and h[0]['tick_ms'] < now_ms - 4000: h.popleft()
                    for tok, side, bid in ((up, 'UP', ub), (dn, 'DOWN', db_)):
                        if not tok: continue
                        if self.last_bid.get((m, tok)) == bid: continue
                        self.last_bid[(m, tok)] = bid
                        self.db.execute('insert into quotes(ts_ms,epoch,sec,m,token,side,bid,fair,'
                                        'spot,sig,tick_ms) values(?,?,?,?,?,?,?,?,?,?,?)',
                                        (now_ms, ep, sec, m, tok, side, bid, p_up, S, sig, tick_ms))
                        self.c['quote'] += 1
                self.db.commit()
            except Exception as e:
                self.c['quote_err'] += 1
                log(f'QUOTE ERROR {type(e).__name__}: {e}')
                await asyncio.sleep(1)

    # ---- measurement, settlement, heartbeat ----------------------------------------------------
    async def rtt_loop(self):
        while True:
            try:
                t0 = time.time()
                code = 0
                try:
                    req = urllib.request.Request(RTT_URL, headers={'User-Agent': UA})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        r.read(64); code = r.status
                except Exception as e:
                    code = -1
                    if self.c['rtt_err'] % 20 == 0: log(f'RTT {type(e).__name__}: {e}')
                    self.c['rtt_err'] += 1
                ms = (time.time() - t0) * 1000
                self.rtt.append(ms)
                self.db.execute('insert into rtt(ts_ms,ms,code) values(?,?,?)',
                                (int(t0 * 1000), ms, code))
                self.db.commit()
            except Exception as e:
                log(f'RTT ERROR {type(e).__name__}: {e}')
            await asyncio.sleep(60)

    async def settle_loop(self):
        while True:
            await asyncio.sleep(45)
            try:
                n = 0
                for r in self.db.execute('select id, epoch, side, bid from fills where pnl is null'):
                    o = outcome_for(r['epoch'])
                    if not o: continue
                    pnl = SHARES * (1 - r['bid']) if o == r['side'] else -SHARES * r['bid']
                    self.db.execute('update fills set outcome=?, pnl=? where id=?',
                                    (o, round(pnl, 6), r['id']))
                    n += 1
                if n: self.db.commit()
                self.db.execute('insert into health(ts_ms,bn_ticks,poly_msgs,poly_trades,quotes,'
                                'fills,note) values(?,?,?,?,?,?,?)',
                                (int(time.time() * 1000), self.c['bn'], self.c['poly'],
                                 self.c['trade'], self.c['quote'], self.c['fill'],
                                 f'settled {n}; errs bn{self.c["bn_err"]} poly{self.c["poly_err"]} '
                                 f'q{self.c["quote_err"]} notok{self.c["no_tokens"]}'))
                self.db.commit()
                rt = sorted(self.rtt)
                med = rt[len(rt) // 2] if rt else float('nan')
                with open(HB, 'w') as f:
                    f.write(f'{int(time.time())} {dt.datetime.now(dt.UTC):%F %T} bn={self.c["bn"]} '
                            f'poly={self.c["poly"]} trades={self.c["trade"]} '
                            f'quotes={self.c["quote"]} fills={self.c["fill"]} rtt_med={med:.0f}ms '
                            f'ev={ {k[3:]: v for k, v in self.c.items() if k.startswith("ev:")} }\n')
            except Exception as e:
                log(f'SETTLE ERROR {type(e).__name__}: {e}')

    async def run(self, until=None):
        log(f'START pid {os.getpid()} arms m{MARGINS} D{DELAYS} k={K} PAPER ONLY, no orders; '
            f'warm start loaded {self.fv.warm} bn_flow seconds')
        tasks = [asyncio.ensure_future(t()) for t in
                 (self.bn_loop, self.poly_loop, self.quote_loop, self.rtt_loop, self.settle_loop)]
        try:
            if until:
                while time.time() < until: await asyncio.sleep(1)
            else:
                while True: await asyncio.sleep(3600)
        finally:
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            log('STOP')


if __name__ == '__main__':
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(Shadow().run(time.time() + secs if secs else None))
