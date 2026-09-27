#!/usr/bin/env python3
"""ETH + SOL 5-minute market recorder (owner order 09-27, via V). SEPARATE PROCESS - no engine change.

Writes to its own sqlite at /home/ubuntu/pm_multi/multi_market.sqlite3. It never opens, reads or writes
the engine's journal, never places an order, and holds no credentials: every endpoint used here is public.

  books        1 Hz top-of-book for BOTH tokens of each market (best bid/ask and their sizes), plus the
               age of the last full `book` snapshot per token, because a price_change delta does NOT
               resync the book and age from the last snapshot is the only measure of drift (this is the
               engine's own reasoning in poly_core.Books.apply, followed rather than re-derived).
  markets      epoch -> token ids, as discovered from gamma
  resolutions  the venue's own settlement (gamma outcomePrices), which is what these trades grade on
  k1s          Binance ETHUSDT/SOLUSDT 1 s klines, for the coin's own move and the BTC lead term

Protocol matches the running engine: subscribe {'assets_ids': [...], 'type': 'market'}; events carry
event_type in {book, price_change, tick_size_change} with asset_id and bids/asks of {price,size}.
"""
import asyncio, json, sqlite3, time, urllib.request, datetime as dt, math, sys, os

DB = '/home/ubuntu/pm_multi/multi_market.sqlite3'
GAMMA = 'https://gamma-api.polymarket.com/events?slug={}-{}'
WS = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
BOOK = 'https://clob.polymarket.com/book?token_id={}'
KLINES = 'https://data-api.binance.vision/api/v3/klines?symbol={}&interval=1s&limit={}'
# market key -> slug prefix, epoch grid in seconds, Binance symbol for its 1 s klines.
# BTC 15m sits on a 900 s grid, so the epoch is NOT interchangeable with the 5 m markets - every loop
# derives the epoch from the market's own step rather than assuming 300.
MARKETS = {
    'eth':   dict(slug='eth-updown-5m',  step=300, sym='ETHUSDT'),
    'sol':   dict(slug='sol-updown-5m',  step=300, sym='SOLUSDT'),
    'btc15': dict(slug='btc-updown-15m', step=900, sym='BTCUSDT'),
}
COINS = {k: v['sym'] for k, v in MARKETS.items()}
SYMS = sorted({v['sym'] for v in MARKETS.values()})

DDL = [
    """CREATE TABLE IF NOT EXISTS books(ts INTEGER, market TEXT, epoch INTEGER,
       up_bid REAL, up_bid_sz REAL, up_ask REAL, up_ask_sz REAL,
       dn_bid REAL, dn_bid_sz REAL, dn_ask REAL, dn_ask_sz REAL,
       up_snap_age_s REAL, dn_snap_age_s REAL, PRIMARY KEY(ts, market))""",
    """CREATE TABLE IF NOT EXISTS markets(epoch INTEGER, market TEXT, token_up TEXT, token_dn TEXT,
       slug TEXT, seen REAL, PRIMARY KEY(epoch, market))""",
    """CREATE TABLE IF NOT EXISTS resolutions(epoch INTEGER, market TEXT, outcome TEXT, src TEXT,
       ts REAL, PRIMARY KEY(epoch, market))""",
    """CREATE TABLE IF NOT EXISTS k1s(ts INTEGER, sym TEXT, o REAL, h REAL, l REAL, cl REAL, v REAL,
       n INTEGER, tb REAL, PRIMARY KEY(ts, sym))""",
    """CREATE TABLE IF NOT EXISTS health(ts REAL PRIMARY KEY, note TEXT)""",
]

books = {}          # token -> {'asks':{p:q}, 'bids':{p:q}, 'snapshot': monotonic}
toks = {}           # (epoch, market) -> (up, dn)
tok_market = {}     # token -> (market, epoch)
errs = {}

def log(db, note):
    try:
        db.execute('INSERT OR REPLACE INTO health VALUES(?,?)', (time.time(), note[:400])); db.commit()
    except Exception: pass
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {note}', flush=True)

UA = 'Mozilla/5.0 (X11; Linux x86_64) zurich-multimarket-recorder/1.0'

def get_json(url, timeout=12):
    # gamma answers curl but 403s Python's default urllib User-Agent, so it is set explicitly.
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)

def discover(market, epoch):
    slug = f"{MARKETS[market]['slug']}-{epoch}"
    data = get_json(GAMMA.format(MARKETS[market]['slug'], epoch))
    for e in data or []:
        for m in e.get('markets', []):
            if m.get('slug') != slug: continue
            t = json.loads(m['clobTokenIds'])
            return str(t[0]), str(t[1]), m.get('slug')
    return None

async def gamma_loop(db):
    while True:
        try:
            now = int(time.time())
            for market, cfg in MARKETS.items():
                st = cfg['step']
                for ep in (now // st * st, now // st * st + st):
                    if (ep, market) in toks: continue
                    r = await asyncio.to_thread(discover, market, ep)
                    if not r: continue
                    up, dn, slug = r
                    toks[(ep, market)] = (up, dn)
                    tok_market[up] = (market, ep, 'up'); tok_market[dn] = (market, ep, 'dn')
                    db.execute('INSERT OR REPLACE INTO markets VALUES(?,?,?,?,?,?)',
                               (ep, market, up, dn, slug, time.time())); db.commit()
                    log(db, f'discovered {slug}')
        except Exception as e:
            errs['gamma'] = repr(e)[:120]; log(db, f'gamma error {repr(e)[:90]}')
        await asyncio.sleep(20)

async def ws_loop(db):
    import websockets
    while True:
        want = sorted({t for (ep, m), (u, d) in toks.items() if ep >= int(time.time()) // 300 * 300 - 300
                       for t in (u, d)})
        if not want:
            await asyncio.sleep(3); continue
        try:
            async with websockets.connect(WS, ping_interval=20, close_timeout=5, max_size=None) as w:
                await w.send(json.dumps({'assets_ids': want, 'type': 'market'}))
                log(db, f'ws subscribed to {len(want)} tokens')
                deadline = time.time() + 300           # resubscribe each candle with the new token set
                while time.time() < deadline:
                    raw = await asyncio.wait_for(w.recv(), timeout=30)
                    # The venue sends `book` as a LIST but price_change / last_trade_price as a BARE
                    # DICT (measured: 2,496 dict price_change vs 2 list book in 50 s). Iterating the
                    # dict walks its KEYS, so every delta was being dropped silently - the books were
                    # only as fresh as the REST resync. Normalise the payload before iterating.
                    _p = raw if isinstance(raw, (list, dict)) else json.loads(raw)
                    for e in (_p if isinstance(_p, list) else [_p]):
                        if not isinstance(e, dict): continue
                        k = e.get('event_type'); tk = str(e.get('asset_id') or '')
                        if k == 'book':
                            b = {s: {float(x['price']): float(x['size']) for x in e.get(s, [])
                                     if 0 < float(x['price']) < 1 and float(x['size']) > 0} for s in ('asks', 'bids')}
                            b['snapshot'] = time.monotonic(); books[tk] = b
                        elif k == 'price_change':
                            for c in e.get('price_changes', []):
                                b = books.get(str(c.get('asset_id')))
                                if not b or c.get('side') not in ('BUY', 'SELL'): continue
                                p, q = float(c['price']), float(c['size'])
                                if not (0 < p < 1 and q >= 0 and math.isfinite(q)): continue
                                side = b['asks' if c['side'] == 'SELL' else 'bids']
                                if q: side[p] = q
                                else: side.pop(p, None)
                        elif k == 'tick_size_change':
                            pass
        except Exception as e:
            errs['ws'] = repr(e)[:120]; log(db, f'ws reconnect after {repr(e)[:90]}')
            await asyncio.sleep(2)

def top(tk, side):
    b = books.get(tk)
    if not b: return (None, None, None)
    d = b.get(side) or {}
    if not d: return (None, None, b.get('snapshot'))
    p = min(d) if side == 'asks' else max(d)
    return (p, d[p], b.get('snapshot'))

async def snap_loop(db):
    last = 0
    while True:
        await asyncio.sleep(0.15)
        now = int(time.time())
        if now == last: continue
        last = now
        rows = []
        for market, cfg in MARKETS.items():
            ep = now // cfg['step'] * cfg['step']
            t = toks.get((ep, market))
            if not t: continue
            up, dn = t
            ub, ubs, usn = top(up, 'bids'); ua, uas, _ = top(up, 'asks')
            dbid, dbs, dsn = top(dn, 'bids'); da, das, _ = top(dn, 'asks')
            if ua is None and da is None and ub is None and dbid is None: continue
            mono = time.monotonic()
            rows.append((now, market, ep, ub, ubs, ua, uas, dbid, dbs, da, das,
                         (mono - usn) if usn else None, (mono - dsn) if dsn else None))
        if rows:
            try:
                db.executemany('INSERT OR REPLACE INTO books VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
                db.commit()
            except Exception as e: errs['snap'] = repr(e)[:120]

async def resync_loop(db):
    """A price_change delta does not resync the book, and the venue sends a full `book` event only on
    subscribe, so snapshot age grows for the whole candle. Refetching REST /book every 45 s bounds the
    drift to 45 s instead of 300 s. 8 requests per 45 s is negligible against the venue's limits."""
    while True:
        await asyncio.sleep(45)
        try:
            now = int(time.time())
            live = {t for (ep, m), (u, d) in toks.items() if ep >= now // 300 * 300 for t in (u, d)}
            for tk in sorted(live):
                try:
                    d = await asyncio.to_thread(get_json, BOOK.format(tk), 10)
                except Exception: continue
                b = {s_: {float(x['price']): float(x['size']) for x in (d.get(s_) or [])
                          if 0 < float(x['price']) < 1 and float(x['size']) > 0} for s_ in ('asks', 'bids')}
                b['snapshot'] = time.monotonic(); books[tk] = b
        except Exception as e:
            errs['resync'] = repr(e)[:120]

async def klines_loop(db):
    while True:
        try:
            for sym in SYMS:
                k = await asyncio.to_thread(get_json, KLINES.format(sym, 120), 20)
                tag = sym.replace('USDT', '').lower()          # eth / sol / btc, one row per symbol
                rows = [(int(x[0]) // 1000, tag, float(x[1]), float(x[2]), float(x[3]), float(x[4]),
                         float(x[5]), int(x[8]), float(x[9])) for x in k]
                db.executemany('INSERT OR REPLACE INTO k1s VALUES(?,?,?,?,?,?,?,?,?)', rows)
            db.commit()
        except Exception as e:
            errs['klines'] = repr(e)[:120]
        await asyncio.sleep(45)

def resolve(market, epoch):
    slug = f"{MARKETS[market]['slug']}-{epoch}"
    data = get_json(GAMMA.format(MARKETS[market]['slug'], epoch))
    for e in data or []:
        for m in e.get('markets', []):
            if m.get('slug') != slug: continue
            op = m.get('outcomePrices')
            if not op: return None
            try: op = json.loads(op) if isinstance(op, str) else op
            except Exception: return None
            if len(op) < 2: return None
            a, b = float(op[0]), float(op[1])
            if max(a, b) < 0.99: return None                # not settled yet
            return 'UP' if a > b else 'DOWN'
    return None

async def resolve_loop(db):
    while True:
        try:
            now = int(time.time())
            for market, cfg in MARKETS.items():
                st = cfg['step']
                for ep in range(now // st * st - 8 * st, now // st * st - st, st):
                    if (ep, market) not in toks: continue
                    if db.execute('SELECT 1 FROM resolutions WHERE epoch=? AND market=?', (ep, market)).fetchone(): continue
                    r = await asyncio.to_thread(resolve, market, ep)
                    if r:
                        db.execute('INSERT OR REPLACE INTO resolutions VALUES(?,?,?,?,?)',
                                   (ep, market, r, 'gamma.outcomePrices', time.time())); db.commit()
        except Exception as e:
            errs['resolve'] = repr(e)[:120]
        await asyncio.sleep(120)

async def status_loop(db):
    while True:
        await asyncio.sleep(300)
        n = {t: db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
             for t in ('books', 'k1s', 'resolutions', 'markets')}
        log(db, f'alive rows {n} tokens_in_book {len(books)} size {os.path.getsize(DB)/1048576:.1f}MB errs {errs}')

async def main():
    db = sqlite3.connect(DB, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    for d in DDL: db.execute(d)
    db.commit()
    log(db, 'recorder start (separate process; public endpoints only; engine untouched)')
    await asyncio.gather(gamma_loop(db), ws_loop(db), snap_loop(db), klines_loop(db),
                         resync_loop(db), resolve_loop(db), status_loop(db))

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
