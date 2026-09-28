#!/usr/bin/env python3
"""PAIR bot (13.2.0 DRAFT, V 09-28): the 5m/15m TWAP dominance pair. PAPER unless --live AND --owner-confirmed.

Spec: analysis/v/twap/PAIR_LANE_SPEC.md. Evidence: analysis/zurich/ARB_5M_15M.md (books), analysis/v/twap/ARB_TRADES_CHECK.txt
(public trades). The BTC 15m market and the LAST 5m candle inside it settle on the SAME Chainlink TWAP60 stream value at
T+900, against different lines: L15 = TWAP60 before T, L5 = TWAP60 before T+600. If L15 < L5, 15m UP + 5m DOWN pays 1 or
2 per share, never 0 (mirror if L15 > L5). When ask15 + fee + ask5 + fee <= 1 - margin, both legs are bought at once.

A SEPARATE process: the live engine is untouched and keeps its own journal. This bot keeps its own sqlite journal. The
wallet is shared in live mode, so live is capped per pair (--stake), per window (one pair) and per UTC day (--max-day).
Pure functions first (tested in test_pair_bot.py), then the async shell. No secret is ever printed.
"""
import argparse, asyncio, json, math, os, sqlite3, time, urllib.request

FEE = 0.07
POLY_WS = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
REF_WS = 'wss://ws-live-data.polymarket.com/'
REF_SUBSCRIBE = {"action": "subscribe", "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "update"}]}
GAMMA = 'https://gamma-api.polymarket.com/events?slug={}'


# ---------------------------------------------------------------- pure functions
def fee(p):
    return FEE * p * (1 - p)


def twap(px, lo, hi, min_n=45):
    """Mean of the per-second reference values in [lo, hi) (seconds); None when fewer than min_n seconds are present."""
    v = [px[t] for t in range(lo, hi) if t in px]
    return (sum(v) / len(v)) if len(v) >= min_n else None


def pair_legs(L15, L5, min_gap):
    """(15m side, 5m side) of the dominance pair, or None when the lines are too close to trust the ordering."""
    if L15 is None or L5 is None or abs(L5 - L15) < min_gap: return None
    return ('UP', 'DOWN') if L15 < L5 else ('DOWN', 'UP')


def pair_cost(a15, a5):
    return a15 + fee(a15) + a5 + fee(a5)


def payoff(legs, out15, out5):
    """Shares' payout per pair: 1 or 2 by construction (0 would mean the premise is broken)."""
    return int(out15 == legs[0]) + int(out5 == legs[1])


def decide(now_s, T, L15, L5, q15, q5, cfg):
    """One pair per window. q15/q5 are BookCache-style quotes of the chosen legs' tokens (or None when stale/absent)."""
    ep5 = T + 600
    if not (ep5 + cfg['first_sec'] <= now_s < ep5 + cfg['last_sec']): return None
    legs = pair_legs(L15, L5, cfg['min_gap'])
    if legs is None or not q15 or not q5: return None
    a15, a5 = float(q15['ask']), float(q5['ask'])
    if not (0.01 <= a15 <= 0.99 and 0.01 <= a5 <= 0.99): return None
    cost = pair_cost(a15, a5)
    if cost > 1.0 - cfg['margin']: return None
    top = lambda q: float(q['asks'][0][1]) if q.get('asks') else 0.0
    shares = math.floor(min(cfg['stake'] / cost, top(q15), top(q5)))
    if shares < cfg['min_shares']: return None
    return dict(T=T, ep5=ep5, legs=legs, a15=a15, a5=a5, cost=round(cost, 5), shares=shares,
                L15=round(L15, 4), L5=round(L5, 4), sec=int(now_s - ep5))


def ref_samples(j):
    """(ts_s, price) for BTC/USD out of one RTDS frame (the engine's PolyRunner.ref_samples, seconds instead of us)."""
    out = []; stack = [j]
    while stack:
        x = stack.pop()
        if isinstance(x, list): stack.extend(x); continue
        if not isinstance(x, dict): continue
        sym = str(x.get('symbol') or x.get('asset') or x.get('pair') or '').lower().replace('-', '/').replace('_', '/')
        val = x.get('value', x.get('price', x.get('full_accuracy_value'))); ts = x.get('timestamp', x.get('ts', x.get('time')))
        if sym in ('btc/usd', 'btcusd', 'btc') and isinstance(val, (int, float, str)) and ts is not None:
            try:
                v = float(val); t = float(ts)
                if v > 1e9: v = v / 1e18
                t_s = t if t < 1e11 else (t / 1e3 if t < 1e14 else t / 1e6)
                if v > 0: out.append((int(t_s), v))
            except (TypeError, ValueError): pass
        for k in ('payload', 'data', 'message', 'updates'):
            if k in x: stack.append(x[k])
    return out


# ---------------------------------------------------------------- journal
class Journal:
    def __init__(self, path):
        self.c = sqlite3.connect(path, check_same_thread=False)
        self.c.executescript('''CREATE TABLE IF NOT EXISTS pairs(T INTEGER PRIMARY KEY, ep5 INTEGER, mode TEXT, ts REAL, sec INTEGER,
            leg15 TEXT, leg5 TEXT, a15 REAL, a5 REAL, cost REAL, shares REAL, L15 REAL, L5 REAL,
            st15 TEXT, st5 TEXT, sh15 REAL, sh5 REAL, spent15 REAL, spent5 REAL, detail TEXT,
            out15 TEXT, out5 TEXT, payout REAL, pnl REAL);''')
        self.c.commit()
    def fired(self, T): return self.c.execute('SELECT 1 FROM pairs WHERE T=?', (T,)).fetchone() is not None
    def day_spent(self, day0):
        r = self.c.execute('SELECT coalesce(sum(coalesce(spent15,0)+coalesce(spent5,0)),0) FROM pairs WHERE ts>=?', (day0,)).fetchone()
        return float(r[0] or 0)
    def record(self, d, mode):
        self.c.execute('INSERT OR IGNORE INTO pairs(T,ep5,mode,ts,sec,leg15,leg5,a15,a5,cost,shares,L15,L5) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (d['T'], d['ep5'], mode, time.time(), d['sec'], d['legs'][0], d['legs'][1], d['a15'], d['a5'], d['cost'], d['shares'], d['L15'], d['L5']))
        self.c.commit()
    def legs_done(self, T, st15, st5, sh15, sh5, sp15, sp5, detail):
        self.c.execute('UPDATE pairs SET st15=?,st5=?,sh15=?,sh5=?,spent15=?,spent5=?,detail=? WHERE T=?',
                       (st15, st5, sh15, sh5, sp15, sp5, json.dumps(detail)[:4000], T)); self.c.commit()
    def unsettled(self):
        return self.c.execute('SELECT T,ep5,leg15,leg5,sh15,sh5,spent15,spent5 FROM pairs WHERE out15 IS NULL').fetchall()
    def settle(self, T, out15, out5, payout, pnl):
        self.c.execute('UPDATE pairs SET out15=?,out5=?,payout=?,pnl=? WHERE T=?', (out15, out5, payout, pnl, T)); self.c.commit()


def settle_row(row, out15, out5):
    """payout, pnl of one journal row from the legs' actual shares and spend (a lone leg pays on its own market)."""
    T, ep5, leg15, leg5, sh15, sh5, sp15, sp5 = row
    pay = (sh15 or 0) * (out15 == leg15) + (sh5 or 0) * (out5 == leg5)
    return pay, pay - (sp15 or 0) - (sp5 or 0)


# ---------------------------------------------------------------- venue I/O
def http_json(url, timeout=8):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'pair-bot'}), timeout=timeout) as r:
        return json.load(r)


def market(slug):
    """(UP token, DOWN token, conditionId, resolved outcome or None) for one slug."""
    for ev in http_json(GAMMA.format(slug)) or []:
        for m in ev.get('markets', []):
            if m.get('slug') != slug: continue
            names = m['outcomes']; toks = m['clobTokenIds']; px = m.get('outcomePrices')
            names = json.loads(names) if isinstance(names, str) else names
            toks = json.loads(toks) if isinstance(toks, str) else toks
            px = json.loads(px) if isinstance(px, str) else (px or [])
            p = {str(n).upper(): str(t) for n, t in zip(names, toks)}
            out = None
            if px and str(m.get('umaResolutionStatus', '')).lower() == 'resolved':
                out = 'UP' if float(px[0]) > 0.5 else 'DOWN'
            return p.get('UP'), p.get('DOWN'), m.get('conditionId'), out
    return None


class Bot:
    def __init__(self, a):
        from poly_core import BookCache
        self.a = a; self.books = BookCache(); self.ref = {}; self.mk = {}; self.db = Journal(a.db)
        self.cfg = dict(first_sec=a.first_sec, last_sec=a.last_sec, margin=a.margin, min_gap=a.min_gap,
                        stake=a.stake, min_shares=a.min_shares)
        self.broker = None; self.live = bool(a.live and a.owner_confirmed)

    async def markets_for(self, T):
        if T not in self.mk:
            m15 = await asyncio.to_thread(market, f'btc-updown-15m-{T}')
            m5 = await asyncio.to_thread(market, f'btc-updown-5m-{T+600}')
            if not m15 or not m5: return None
            self.mk[T] = dict(m15=m15, m5=m5)
        return self.mk[T]

    async def ref_loop(self):
        import websockets
        while True:
            try:
                async with websockets.connect(REF_WS, ping_interval=15, ping_timeout=10, max_size=2 ** 22) as w:
                    await w.send(json.dumps(REF_SUBSCRIBE))
                    while True:
                        msg = await asyncio.wait_for(w.recv(), 10)
                        if isinstance(msg, (bytes, bytearray)): msg = msg.decode('utf-8', 'replace')
                        if not str(msg).strip(): continue
                        try: j = json.loads(msg)
                        except ValueError: continue
                        for t, v in ref_samples(j): self.ref[t] = v
                        cut = int(time.time()) - 1800
                        for t in [k for k in self.ref if k < cut]: self.ref.pop(t, None)
            except Exception as e:
                print(f'[ref] reconnect: {type(e).__name__}', flush=True); await asyncio.sleep(1)

    async def book_loop(self):
        import websockets
        while True:
            T = int(time.time() // 900) * 900
            m = await self.markets_for(T)
            if not m: await asyncio.sleep(2); continue
            toks = [t for t in (m['m15'][0], m['m15'][1], m['m5'][0], m['m5'][1]) if t]
            self.books.prune(toks)
            try:
                async with websockets.connect(POLY_WS, ping_interval=None, max_size=2 ** 23) as w:
                    await w.send(json.dumps({'assets_ids': toks, 'type': 'market'}))
                    async def ping():
                        while True: await asyncio.sleep(5); await w.send('PING')
                    pt = asyncio.create_task(ping())
                    try:
                        while time.time() < T + 900:
                            msg = await asyncio.wait_for(w.recv(), 15)
                            if isinstance(msg, (bytes, bytearray)): msg = msg.decode('utf-8', 'replace')
                            if not str(msg).strip() or msg == 'PONG': continue
                            try: data = json.loads(msg)
                            except ValueError: continue
                            for ev in (data if isinstance(data, list) else [data]):       # book is a LIST, price_change a bare DICT
                                if isinstance(ev, dict):
                                    try: self.books.apply(ev)
                                    except Exception: pass
                    finally: pt.cancel()
            except Exception as e:
                print(f'[book] reconnect: {type(e).__name__}', flush=True); await asyncio.sleep(1)

    async def decide_loop(self):
        while True:
            await asyncio.sleep(0.05)
            now = time.time(); T = int(now // 900) * 900
            if now < T + 600 + self.cfg['first_sec'] or self.db.fired(T): continue
            m = self.mk.get(T)
            if not m: continue
            L15, L5 = twap(self.ref, T - 60, T), twap(self.ref, T + 540, T + 600)
            legs = pair_legs(L15, L5, self.cfg['min_gap'])
            if not legs: continue
            tok15 = m['m15'][0 if legs[0] == 'UP' else 1]; tok5 = m['m5'][0 if legs[1] == 'UP' else 1]
            q15, q5 = self.books.quote(tok15, self.a.quote_age), self.books.quote(tok5, self.a.quote_age)
            d = decide(now, T, L15, L5, q15, q5, self.cfg)
            if not d: continue
            day0 = now - (now % 86400)
            if self.live and self.db.day_spent(day0) + d['shares'] * d['cost'] > self.a.max_day:
                print(f'[pair] day cap reached, skip T={T}', flush=True); self.db.record(dict(d, shares=0), 'CAPPED'); continue
            self.db.record(d, 'LIVE' if self.live else 'PAPER')
            print(f"[pair] T={T} sec={d['sec']} legs 15m {d['legs'][0]} @{d['a15']:.3f} + 5m {d['legs'][1]} @{d['a5']:.3f} "
                  f"cost {d['cost']:.4f} x{d['shares']} ({'LIVE' if self.live else 'PAPER'})", flush=True)
            if self.live: asyncio.create_task(self.fire_live(d, tok15, tok5))
            else:
                self.db.legs_done(T, 'PAPER_FILL', 'PAPER_FILL', d['shares'], d['shares'],
                                  d['shares'] * (d['a15'] + fee(d['a15'])), d['shares'] * (d['a5'] + fee(d['a5'])), {})

    async def fire_live(self, d, tok15, tok5):
        """Both legs signed first, then posted together; each capped at its own ask (no chasing). Results are
        reconciled with the engine's LiveBroker.reconcile until terminal."""
        b = self.broker
        async def leg(tok, ask):
            # rate/exponent: LiveBroker._trade_fills' local fee fallback (fee = n*rate*p*(1-p)); the venue's own rate wins when reported.
            plan = dict(amount=round(d['shares'] * ask, 2), cap=ask, rate=FEE, exponent=1)
            s, oid = await b.prepare(tok, plan)
            return s, oid, plan
        try:
            (s15, o15, p15), (s5, o5, p5) = await asyncio.gather(leg(tok15, d['a15']), leg(tok5, d['a5']))
        except Exception as e:
            self.db.legs_done(d['T'], 'PREPARE_FAILED', 'PREPARE_FAILED', 0, 0, 0, 0, dict(error=type(e).__name__)); return
        t0 = time.time()
        r15, r5 = await asyncio.gather(b.post(s15), b.post(s5), return_exceptions=True)
        async def settle(oid, tok, r, plan):
            if isinstance(r, Exception) or not isinstance(r, dict) or r.get('id') != oid:
                return 'NOT_ACCEPTED', 0.0, 0.0, (repr(r)[:300] if not isinstance(r, dict) else r)
            for k in range(40):     # a filled FAK takes 6.7-16 s to show on the account tape (poly_live, 12.15.3)
                try: out = await b.reconcile(dict(id=oid, token=tok, ts=t0, plan=json.dumps(plan), reconcile_count=k, venue_absent=0))
                except Exception as e: out = dict(terminal=False, fills=[], reason=type(e).__name__)
                if out.get('terminal'):
                    fl = [f for _, f in out.get('fills', [])]
                    sh = sum(float(f.get('shares', 0) or 0) for f in fl)
                    sp = sum(float(f.get('spent', 0) or 0) + float(f.get('fees', 0) or 0) for f in fl)
                    return ('FILLED' if sh > 0 else 'NO_FILL'), sh, sp, out.get('reason')
                await asyncio.sleep(2)
            return 'UNRESOLVED', 0.0, 0.0, 'reconcile timeout'
        (st15, sh15, sp15, i15), (st5, sh5, sp5, i5) = await asyncio.gather(settle(o15, tok15, r15, p15), settle(o5, tok5, r5, p5))
        self.db.legs_done(d['T'], st15, st5, sh15, sh5, sp15, sp5, dict(leg15=i15, leg5=i5))
        print(f"[pair live] T={d['T']} 15m {st15} {sh15:.2f}sh ${sp15:.2f} | 5m {st5} {sh5:.2f}sh ${sp5:.2f}", flush=True)

    async def settle_loop(self):
        while True:
            await asyncio.sleep(30)
            for row in self.db.unsettled():
                T = row[0]
                if time.time() < T + 900 + 60: continue
                try:
                    m15 = await asyncio.to_thread(market, f'btc-updown-15m-{T}')
                    m5 = await asyncio.to_thread(market, f'btc-updown-5m-{T+600}')
                except Exception: continue
                if not m15 or not m5 or m15[3] is None or m5[3] is None: continue
                pay, pnl = settle_row(row, m15[3], m5[3])
                self.db.settle(T, m15[3], m5[3], pay, pnl)
                print(f'[settle] T={T} 15m {m15[3]} 5m {m5[3]} payout {pay:.2f} pnl {pnl:+.2f}', flush=True)

    async def run(self):
        if self.live:
            from poly_live import LiveBroker
            self.broker = LiveBroker(self.books); await self.broker.open()
            print(f'[pair] LIVE: stake ${self.a.stake} per pair, day cap ${self.a.max_day}', flush=True)
        else:
            print('[pair] PAPER: no order is sent', flush=True)
        await asyncio.gather(self.ref_loop(), self.book_loop(), self.decide_loop(), self.settle_loop())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--db', default='pair_bot.sqlite3')
    ap.add_argument('--stake', type=float, default=5.0, help='max $ per pair (both legs)')
    ap.add_argument('--margin', type=float, default=0.01, help='required cost below 1 incl. fees')
    ap.add_argument('--min-gap', dest='min_gap', type=float, default=1.0, help='$ between lines; closer is skipped')
    ap.add_argument('--first-sec', dest='first_sec', type=int, default=0)
    ap.add_argument('--last-sec', dest='last_sec', type=int, default=290)
    ap.add_argument('--min-shares', dest='min_shares', type=int, default=5, help='venue minimum order size')
    ap.add_argument('--quote-age', dest='quote_age', type=float, default=0.25, help='max book age, s')
    ap.add_argument('--max-day', dest='max_day', type=float, default=50.0, help='live: max $ spent per UTC day')
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--owner-confirmed', dest='owner_confirmed', action='store_true',
                    help='required with --live: the owner confirmed THIS live test (CLAUDE.md)')
    a = ap.parse_args()
    if a.live and not a.owner_confirmed: raise SystemExit('--live needs --owner-confirmed (the owner must confirm this specific test)')
    asyncio.run(Bot(a).run())


if __name__ == '__main__':
    main()
