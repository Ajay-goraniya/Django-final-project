#!/usr/bin/env python3
"""NC-16 shadow arm - PAPER ONLY. Separate process, own sqlite, no engine change, no credentials.

V, 09-28: at sec 45, if div = (Chainlink ref - Binance spot)/Binance <= -3 bps buy DOWN at the ask; mirror at
div >= +3 buy UP; $10 nominal; fills through the ef_persist simulator.

THERE IS NO ORDER PATH IN THIS FILE. It does not import poly_live, holds no credentials, and every endpoint
it touches is public. Master stays OFF and is never read or written.

div is taken from the ENGINE's own 1 Hz tape (tape1s, opened read-only) rather than from a second Chainlink
subscription of my own. That is deliberate: it makes this shadow and the frozen-tape cell in
analysis/zurich/ef_chainlink_div.py use the IDENTICAL divergence series, so the two reports V asked for are
comparable by construction instead of differing by feed.

The book is my own WS, because the fill simulator needs the own-side ask again 250 ms after the decision and
a 1 Hz tape cannot provide that. Fill rule, unchanged from ef_persist: a FAK at ask+1 tick fills iff the ask
on the first book read at >= t+250 ms is within one tick, and it fills AT that later ask.
"""
import asyncio, json, sqlite3, time, math, urllib.request, datetime as dt

DB = '/home/ubuntu/pm_chaindiv/chaindiv.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA = 'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}'
WS = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
BOOK = 'https://clob.polymarket.com/book?token_id={}'
UA = 'Mozilla/5.0 (X11; Linux x86_64) zurich-chaindiv-shadow/1.0'
SEC, THR, TICK, RATE, STAKE, DELAY_MS = 45, 3.0, 0.01, 0.07, 10.0, 250

DDL = [
    """CREATE TABLE IF NOT EXISTS fires(epoch INTEGER PRIMARY KEY, ts REAL, sec INTEGER, side TEXT,
       div REAL, ref REAL, spot REAL, ask REAL, ask_sz REAL, opp_ask REAL, later_ask REAL, later_ms REAL,
       filled INTEGER, fill_price REAL, shares REAL, spent REAL, fees REAL, book_age_s REAL,
       outcome TEXT, win INTEGER, graded_ts REAL)""",
    """CREATE TABLE IF NOT EXISTS skips(epoch INTEGER PRIMARY KEY, sec INTEGER, div REAL, reason TEXT)""",
    """CREATE TABLE IF NOT EXISTS markets(epoch INTEGER PRIMARY KEY, token_up TEXT, token_dn TEXT, seen REAL)""",
    """CREATE TABLE IF NOT EXISTS health(ts REAL PRIMARY KEY, note TEXT)""",
]
books, toks = {}, {}


def log(db, note):
    try:
        db.execute('INSERT OR REPLACE INTO health VALUES(?,?)', (time.time(), note[:400])); db.commit()
    except Exception: pass
    print(f'{dt.datetime.now(dt.timezone.utc):%H:%M:%S} {note}', flush=True)


def get_json(url, timeout=12):
    rq = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return json.loads(r.read().decode())


def top(tk, side='asks'):
    b = books.get(tk)
    if not b: return (None, None, None)
    d = b.get(side) or {}
    if not d: return (None, None, b.get('snapshot'))
    p = min(d) if side == 'asks' else max(d)
    return (p, d[p], b.get('snapshot'))


def div_now(ts, back=5):
    """The engine's own tape, read-only. The most recent second at or before `ts` that has BOTH feeds.

    Looking only at `ts` loses candles to a write race rather than to the signal: the engine commits the
    row for second t a fraction of a second into t, so a read at t+0.05 can miss it. Measured on the first
    live candle - one skip logged as no_div at 11:00:45 with the tape perfectly healthy. Scanning back a
    few seconds keeps the denominator honest, and the age is recorded so a stale div can be filtered later.
    Returns (div_bps, ref, spot, age_s) or None."""
    try:
        c = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
        r = c.execute('SELECT ts,spot_px,ref_px FROM tape1s WHERE ts<=? AND ts>=? '
                      'AND spot_px IS NOT NULL AND ref_px IS NOT NULL ORDER BY ts DESC LIMIT 1',
                      (ts, ts - back)).fetchone()
        c.close()
        if not r: return None
        return ((r[2] - r[1]) / r[1] * 1e4, float(r[2]), float(r[1]), ts - int(r[0]))
    except Exception:
        return None


async def gamma_loop(db):
    while True:
        try:
            now = int(time.time())
            for ep in (now // 300 * 300, now // 300 * 300 + 300):
                if ep in toks: continue
                data = await asyncio.to_thread(get_json, GAMMA.format(ep))
                for e in data or []:
                    for m in e.get('markets', []):
                        if m.get('slug') != f'btc-updown-5m-{ep}': continue
                        t = json.loads(m['clobTokenIds'])
                        toks[ep] = (str(t[0]), str(t[1]))
                        db.execute('INSERT OR REPLACE INTO markets VALUES(?,?,?,?)',
                                   (ep, str(t[0]), str(t[1]), time.time())); db.commit()
                        log(db, f'discovered btc-updown-5m-{ep}')
        except Exception as e:
            log(db, f'gamma error {repr(e)[:90]}')
        await asyncio.sleep(20)


async def ws_loop(db):
    import websockets
    while True:
        want = sorted({t for ep, (u, d) in toks.items()
                       if ep >= int(time.time()) // 300 * 300 - 300 for t in (u, d)})
        if not want:
            await asyncio.sleep(3); continue
        try:
            async with websockets.connect(WS, ping_interval=20, close_timeout=5, max_size=None) as w:
                await w.send(json.dumps({'assets_ids': want, 'type': 'market'}))
                log(db, f'ws subscribed {len(want)} tokens')
                deadline = time.time() + 300
                while time.time() < deadline:
                    raw = await asyncio.wait_for(w.recv(), timeout=30)
                    # `book` arrives as a LIST, price_change as a BARE DICT - iterating the dict walks its
                    # keys and drops every delta silently. Normalise before iterating (recorder.py, 09-27).
                    _p = raw if isinstance(raw, (list, dict)) else json.loads(raw)
                    for e in (_p if isinstance(_p, list) else [_p]):
                        if not isinstance(e, dict): continue
                        k = e.get('event_type'); tk = str(e.get('asset_id') or '')
                        if k == 'book':
                            b = {s: {float(x['price']): float(x['size']) for x in e.get(s, [])
                                     if 0 < float(x['price']) < 1 and float(x['size']) > 0}
                                 for s in ('asks', 'bids')}
                            b['snapshot'] = time.monotonic(); books[tk] = b
                        elif k == 'price_change':
                            for c in e.get('price_changes', []):
                                b = books.get(str(c.get('asset_id')))
                                if not b or c.get('side') not in ('BUY', 'SELL'): continue
                                p, q = float(c['price']), float(c['size'])
                                if not (0 < p < 1 and q >= 0 and math.isfinite(q)): continue
                                sd = b['asks' if c['side'] == 'SELL' else 'bids']
                                if q: sd[p] = q
                                else: sd.pop(p, None)
        except Exception as e:
            log(db, f'ws reconnect after {repr(e)[:90]}')
            await asyncio.sleep(2)


async def resync_loop(db):
    """REST /book every 10 s. A price_change delta does not resync the book, and past ~15 s of snapshot age
    the top of book drifts 8.8c against an independent witness (ARB_5M_15M correction, 09-28)."""
    while True:
        await asyncio.sleep(10)
        try:
            now = int(time.time())
            for tk in sorted({t for ep, (u, d) in toks.items() if ep + 300 > now for t in (u, d)}):
                try: d = await asyncio.to_thread(get_json, BOOK.format(tk), 10)
                except Exception: continue
                b = {s: {float(x['price']): float(x['size']) for x in (d.get(s) or [])
                         if 0 < float(x['price']) < 1 and float(x['size']) > 0} for s in ('asks', 'bids')}
                b['snapshot'] = time.monotonic(); books[tk] = b
        except Exception as e:
            log(db, f'resync error {repr(e)[:90]}')


async def decide_loop(db):
    done = set()
    while True:
        await asyncio.sleep(0.05)
        now = time.time(); ts = int(now)
        ep = ts // 300 * 300
        if ts - ep != SEC or ep in done: continue
        done.add(ep)
        if ep not in toks:
            db.execute('INSERT OR REPLACE INTO skips VALUES(?,?,?,?)', (ep, SEC, None, 'no_tokens'))
            db.commit(); continue
        dd = div_now(ts)
        if dd is None:
            db.execute('INSERT OR REPLACE INTO skips VALUES(?,?,?,?)', (ep, SEC, None, 'no_div_5s'))
            db.commit(); continue
        div, ref, spot, dage = dd
        side = 'DOWN' if div <= -THR else ('UP' if div >= THR else None)
        if side is None:
            db.execute('INSERT OR REPLACE INTO skips VALUES(?,?,?,?)', (ep, SEC, div, 'no_signal'))
            db.commit(); continue
        up, dn = toks[ep]
        tk = dn if side == 'DOWN' else up
        otk = up if side == 'DOWN' else dn
        a, sz, snap = top(tk); oa, _, _ = top(otk)
        if a is None or not (0.01 < a < 0.99):
            db.execute('INSERT OR REPLACE INTO skips VALUES(?,?,?,?)', (ep, SEC, div, 'no_book'))
            db.commit(); continue
        age = (time.monotonic() - snap) if snap else None
        t0 = time.monotonic()
        await asyncio.sleep(DELAY_MS / 1000.0)
        la, _, _ = top(tk)
        lat = (time.monotonic() - t0) * 1000
        filled, fp = 0, None
        if la is not None and 0.01 < la < 0.99 and la <= a + TICK + 1e-12:
            filled, fp = 1, la
        shares = (STAKE / fp) if fp else None
        fees = (RATE * shares * fp * (1 - fp)) if fp else None
        db.execute('INSERT OR REPLACE INTO fires VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (ep, now, SEC, side, div, ref, spot, a, sz, oa, la, lat, filled, fp, shares,
                    (STAKE if fp else None), fees, age, None, None, None))
        db.execute('UPDATE fires SET div_age_s=? WHERE epoch=?', (dage, ep))
        db.commit()
        log(db, f'{ep} div {div:+.2f} (age {dage}s) -> {side} ask {a:.3f} later {la} '
                f'{"FILL @ " + format(fp, ".3f") if filled else "no fill"} (PAPER)')


async def grade_loop(db):
    while True:
        await asyncio.sleep(60)
        try:
            for (ep, side) in db.execute(
                    'SELECT epoch,side FROM fires WHERE outcome IS NULL AND ?-epoch>420',
                    (int(time.time()),)).fetchall():
                try: data = await asyncio.to_thread(get_json, GAMMA.format(ep))
                except Exception: continue
                for e in data or []:
                    for m in e.get('markets', []):
                        if m.get('slug') != f'btc-updown-5m-{ep}': continue
                        pr = m.get('outcomePrices')
                        if not pr: continue
                        pr = json.loads(pr) if isinstance(pr, str) else pr
                        out = 'UP' if float(pr[0]) > 0.5 else 'DOWN'
                        db.execute('UPDATE fires SET outcome=?,win=?,graded_ts=? WHERE epoch=?',
                                   (out, 1 if out == side else 0, time.time(), ep)); db.commit()
                        log(db, f'{ep} settled {out} ({"win" if out == side else "loss"})')
        except Exception as e:
            log(db, f'grade error {repr(e)[:90]}')


async def main():
    db = sqlite3.connect(DB)
    for q in DDL: db.execute(q)
    try: db.execute('ALTER TABLE fires ADD COLUMN div_age_s REAL')
    except Exception: pass
    db.commit()
    log(db, 'chaindiv shadow start - PAPER ONLY, no order path in this file')
    await asyncio.gather(gamma_loop(db), ws_loop(db), resync_loop(db), decide_loop(db), grade_loop(db))


if __name__ == '__main__':
    asyncio.run(main())
