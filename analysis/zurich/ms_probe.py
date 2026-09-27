#!/usr/bin/env python3
"""Millisecond probe: Binance vs the Polymarket BTC 5m book. READ-ONLY, separate process, public websockets.

Answers two of the owner's questions from one capture, because they need the same data at the same
resolution:
  VENUE_REACTION_MS - after a Binance move, how long until the Polymarket ask on the favoured side moves?
  ASK_LIFETIME_MS   - how long does a best-ask level (price+size) actually survive, and does it end by
                      being TAKEN or by being CANCELLED?

Nothing else on the box can answer these: decide_log is throttled to one row per 250 ms and tape1s is
1 Hz, so neither can resolve a 50 ms event. Hence a dedicated probe.

Every row carries BOTH clocks: the venue's own `timestamp` (ms, the field poly_core.Books.apply uses) and
the local receive time (ns). They are kept separate on purpose - a venue-clock difference and a transport
delay are different facts, and mixing them is how a latency number becomes fiction.

Holds no credentials, places nothing, touches no engine file.
"""
import asyncio, json, sqlite3, time, urllib.request, datetime as dt, os, sys, argparse

ap = argparse.ArgumentParser(); ap.add_argument('--seconds', type=int, default=7200)
A = ap.parse_args()
DB = '/home/ubuntu/pm_probe/ms_probe.sqlite3'
GAMMA = 'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-%d'
PM_WS = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
BN_WS = 'wss://stream.binance.com:9443/stream?streams=btcusdt@bookTicker/btcusdt@aggTrade'
UA = 'Mozilla/5.0 (X11; Linux x86_64) zurich-ms-probe/1.0'

DDL = [
    """CREATE TABLE IF NOT EXISTS bn(rx_ns INTEGER, ev_ms INTEGER, kind TEXT, px REAL, qty REAL,
       bid REAL, bid_sz REAL, ask REAL, ask_sz REAL)""",
    """CREATE TABLE IF NOT EXISTS pm_ev(rx_ns INTEGER, ev_ms INTEGER, token TEXT, kind TEXT,
       side TEXT, price REAL, size REAL)""",
    """CREATE TABLE IF NOT EXISTS pm_top(rx_ns INTEGER, ev_ms INTEGER, token TEXT, kind TEXT,
       ask REAL, ask_sz REAL, bid REAL, bid_sz REAL)""",
    """CREATE TABLE IF NOT EXISTS pm_trade(rx_ns INTEGER, ev_ms INTEGER, token TEXT, price REAL)""",
    """CREATE TABLE IF NOT EXISTS markets(epoch INTEGER PRIMARY KEY, token_up TEXT, token_dn TEXT)""",
    """CREATE TABLE IF NOT EXISTS resolutions(epoch INTEGER PRIMARY KEY, outcome TEXT)""",
    """CREATE TABLE IF NOT EXISTS health(ts REAL PRIMARY KEY, note TEXT)""",
    "CREATE INDEX IF NOT EXISTS i_bn ON bn(rx_ns)",
    "CREATE INDEX IF NOT EXISTS i_top ON pm_top(token, rx_ns)",
]
books, toks, tok_side = {}, {}, {}
buf = {'bn': [], 'ev': [], 'top': [], 'tr': []}
stop_at = time.time() + A.seconds

def log(db, s):
    try: db.execute('INSERT OR REPLACE INTO health VALUES(?,?)', (time.time(), s[:400])); db.commit()
    except Exception: pass
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {s}', flush=True)

def gj(u, t=12):
    r = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(r, timeout=t) as f: return json.load(f)

async def flush(db):
    while time.time() < stop_at:
        await asyncio.sleep(2)
        try:
            if buf['bn']: db.executemany('INSERT INTO bn VALUES(?,?,?,?,?,?,?,?,?)', buf['bn']); buf['bn'].clear()
            if buf['ev']: db.executemany('INSERT INTO pm_ev VALUES(?,?,?,?,?,?,?)', buf['ev']); buf['ev'].clear()
            if buf['top']: db.executemany('INSERT INTO pm_top VALUES(?,?,?,?,?,?,?,?)', buf['top']); buf['top'].clear()
            if buf['tr']: db.executemany('INSERT INTO pm_trade VALUES(?,?,?,?)', buf['tr']); buf['tr'].clear()
            db.commit()
        except Exception as e: log(db, f'flush error {repr(e)[:90]}')

async def gamma_loop(db):
    while time.time() < stop_at:
        try:
            now = int(time.time())
            for ep in (now // 300 * 300, now // 300 * 300 + 300):
                if ep in toks: continue
                for e in gj(GAMMA % ep) or []:
                    for m in e.get('markets', []):
                        if m.get('slug') != f'btc-updown-5m-{ep}': continue
                        t = json.loads(m['clobTokenIds']); up, dn = str(t[0]), str(t[1])
                        toks[ep] = (up, dn); tok_side[up] = 'UP'; tok_side[dn] = 'DOWN'
                        db.execute('INSERT OR REPLACE INTO markets VALUES(?,?,?)', (ep, up, dn)); db.commit()
            for ep in list(toks):
                if ep > now - 420: continue
                if db.execute('SELECT 1 FROM resolutions WHERE epoch=?', (ep,)).fetchone(): continue
                for e in gj(GAMMA % ep) or []:
                    for m in e.get('markets', []):
                        if m.get('slug') != f'btc-updown-5m-{ep}': continue
                        op = m.get('outcomePrices')
                        if not op: continue
                        op = json.loads(op) if isinstance(op, str) else op
                        if len(op) < 2 or max(float(op[0]), float(op[1])) < 0.99: continue
                        db.execute('INSERT OR REPLACE INTO resolutions VALUES(?,?)',
                                   (ep, 'UP' if float(op[0]) > float(op[1]) else 'DOWN')); db.commit()
        except Exception as e: log(db, f'gamma {repr(e)[:80]}')
        await asyncio.sleep(20)

def top(tk):
    b = books.get(tk)
    if not b: return (None, None, None, None)
    a = b['asks']; d = b['bids']
    ap_ = min(a) if a else None; bp = max(d) if d else None
    return (ap_, a.get(ap_), bp, d.get(bp))

async def pm_loop(db):
    import websockets
    while time.time() < stop_at:
        want = sorted({t for ep, (u, d) in toks.items() if ep >= int(time.time()) // 300 * 300 - 300 for t in (u, d)})
        if not want: await asyncio.sleep(2); continue
        try:
            async with websockets.connect(PM_WS, ping_interval=20, close_timeout=5, max_size=None) as w:
                await w.send(json.dumps({'assets_ids': want, 'type': 'market'}))
                log(db, f'pm ws {len(want)} tokens')
                end = min(stop_at, time.time() + 300)
                while time.time() < end:
                    raw = await asyncio.wait_for(w.recv(), timeout=30)
                    rx = time.time_ns()
                    # The venue sends `book` as a LIST but price_change / last_trade_price as a BARE
                    # DICT (measured: 2,496 dict price_change vs 2 list book in 50 s). Iterating the
                    # dict walks its KEYS, so every delta was being dropped silently - the books were
                    # only as fresh as the REST resync. Normalise the payload before iterating.
                    _p = raw if isinstance(raw, (list, dict)) else json.loads(raw)
                    for e in (_p if isinstance(_p, list) else [_p]):
                        if not isinstance(e, dict): continue
                        k = e.get('event_type'); tk = str(e.get('asset_id') or '')
                        try: ev = int(float(e.get('timestamp', 0)))
                        except Exception: ev = 0
                        if k == 'book':
                            b = {s: {float(x['price']): float(x['size']) for x in e.get(s, [])
                                     if 0 < float(x['price']) < 1 and float(x['size']) > 0} for s in ('asks', 'bids')}
                            books[tk] = b
                            buf['ev'].append((rx, ev, tk, 'book', None, None, None))
                        elif k == 'price_change':
                            for c in e.get('price_changes', []):
                                t2 = str(c.get('asset_id')); b = books.get(t2)
                                if not b or c.get('side') not in ('BUY', 'SELL'): continue
                                p, q = float(c['price']), float(c['size'])
                                if not (0 < p < 1 and q >= 0): continue
                                (b['asks'] if c['side'] == 'SELL' else b['bids'])[p] = q
                                if q == 0: (b['asks'] if c['side'] == 'SELL' else b['bids']).pop(p, None)
                                buf['ev'].append((rx, ev, t2, 'price_change', c['side'], p, q))
                                a2, az, b2, bz = top(t2)
                                buf['top'].append((rx, ev, t2, 'price_change', a2, az, b2, bz))
                            continue
                        elif k == 'last_trade_price':
                            try: buf['tr'].append((rx, ev, tk, float(e.get('price'))))
                            except Exception: pass
                            continue
                        elif k == 'tick_size_change':
                            continue
                        a2, az, b2, bz = top(tk)
                        buf['top'].append((rx, ev, tk, k or '?', a2, az, b2, bz))
        except Exception as e:
            log(db, f'pm reconnect {repr(e)[:80]}'); await asyncio.sleep(2)

async def bn_loop(db):
    import websockets
    while time.time() < stop_at:
        try:
            async with websockets.connect(BN_WS, ping_interval=20, close_timeout=5, max_size=None) as w:
                log(db, 'bn ws connected')
                while time.time() < stop_at:
                    raw = await asyncio.wait_for(w.recv(), timeout=30)
                    rx = time.time_ns(); m = json.loads(raw)
                    d = m.get('data') or {}
                    st = m.get('stream', '')
                    if 'aggTrade' in st:
                        buf['bn'].append((rx, int(d.get('T') or d.get('E') or 0), 'trade',
                                          float(d['p']), float(d['q']), None, None, None, None))
                    elif 'bookTicker' in st:
                        buf['bn'].append((rx, int(d.get('E') or 0), 'book', None, None,
                                          float(d['b']), float(d['B']), float(d['a']), float(d['A'])))
        except Exception as e:
            log(db, f'bn reconnect {repr(e)[:80]}'); await asyncio.sleep(2)

async def status(db):
    while time.time() < stop_at:
        await asyncio.sleep(300)
        n = {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('bn', 'pm_ev', 'pm_top', 'pm_trade')}
        log(db, f'alive {n} size {os.path.getsize(DB)/1048576:.1f}MB left {int(stop_at-time.time())}s')

async def main():
    db = sqlite3.connect(DB, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    for x in DDL: db.execute(x)
    db.commit()
    log(db, f'ms probe start, {A.seconds}s')
    async def guard(f):
        while time.time() < stop_at:
            try: await f(db)
            except asyncio.CancelledError: raise
            except Exception as ex: log(db, f'{f.__name__} died {type(ex).__name__}: {str(ex)[:120]}'); await asyncio.sleep(2)
    await asyncio.gather(*(guard(f) for f in (gamma_loop, pm_loop, bn_loop, flush, status)))
    for k, sql, cols in (('bn', 'INSERT INTO bn VALUES(?,?,?,?,?,?,?,?,?)', 9),
                         ('ev', 'INSERT INTO pm_ev VALUES(?,?,?,?,?,?,?)', 7),
                         ('top', 'INSERT INTO pm_top VALUES(?,?,?,?,?,?,?,?)', 8),
                         ('tr', 'INSERT INTO pm_trade VALUES(?,?,?,?)', 4)):
        if buf[k]: db.executemany(sql, buf[k])
    db.commit()
    log(db, 'ms probe done')

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
