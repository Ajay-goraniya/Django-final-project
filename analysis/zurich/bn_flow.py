#!/usr/bin/env python3
"""Binance aggTrades -> SIGNED taker flow, spot and perp, for EF-9. RECORDER ONLY - places nothing.

EF-9 wants signed taker flow at sub-second resolution and Zurich held none: k1s gives 1 s OHLCV with
UNSIGNED volume, and the only true trade capture was a 2-hour probe. aggTrades carries `m` = "buyer is
the market maker", so the TAKER side is the opposite: m=False -> taker bought (+qty), m=True -> taker
sold (-qty). That sign is the whole point; without it volume cannot tell pressure from activity.

Rows are 250 ms buckets to match decide_log's cadence, so a sequence model can align them without
resampling: per bucket, per stream, the signed notional, the trade count, and the last price.
"""
import asyncio, json, math, os, sqlite3, time, websockets

DB = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
# PERP IS UNREACHABLE FROM THIS BOX, measured 09-28 18:1x: a direct websockets.connect to
# fstream.binance.com/ws/btcusdt@aggTrade times out with no handshake while the spot endpoint returns a
# trade in under a second. Left in the dict deliberately - the reconnect loop costs nothing, the log shows
# the failures rather than hiding them, and if the route opens the data starts landing without a change.
STREAMS = {'spot': 'wss://stream.binance.com:9443/ws/btcusdt@aggTrade',
           'perp': 'wss://fstream.binance.com/ws/btcusdt@aggTrade'}
BUCKET_MS = 250
DDL = ["""CREATE TABLE IF NOT EXISTS flow(ts_ms INTEGER, stream TEXT, px REAL, buy_notional REAL,
          sell_notional REAL, n INTEGER, PRIMARY KEY(ts_ms, stream))""",
       "CREATE INDEX IF NOT EXISTS flow_ts ON flow(ts_ms)",
       "CREATE TABLE IF NOT EXISTS health(ts INTEGER, note TEXT)"]


def db():
    d = sqlite3.connect(DB, timeout=30)
    d.execute('PRAGMA journal_mode=WAL')
    for q in DDL: d.execute(q)
    return d


async def stream(name, url, buf):
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, max_queue=4096) as w:
                while True:
                    e = json.loads(await asyncio.wait_for(w.recv(), timeout=60))
                    p, q, t, m = e.get('p'), e.get('q'), e.get('T'), e.get('m')
                    if p is None or q is None or t is None: continue
                    p, q = float(p), float(q)
                    if not (math.isfinite(p) and math.isfinite(q) and q > 0): continue
                    k = (int(t) // BUCKET_MS) * BUCKET_MS
                    r = buf.setdefault((k, name), [p, 0.0, 0.0, 0])
                    r[0] = p
                    # m is "buyer is the maker", so the TAKER sold. m False -> taker bought.
                    if m: r[2] += p * q
                    else: r[1] += p * q
                    r[3] += 1
        except Exception as ex:
            print(f'{time.strftime("%H:%M:%S")} {name} reconnect after {repr(ex)[:80]}', flush=True)
            await asyncio.sleep(2)


async def writer(d, buf):
    n = 0
    while True:
        await asyncio.sleep(2.0)
        cut = (int(time.time() * 1000) // BUCKET_MS) * BUCKET_MS - 2 * BUCKET_MS
        done = [k for k in buf if k[0] <= cut]
        if done:
            d.executemany('INSERT OR REPLACE INTO flow VALUES(?,?,?,?,?,?)',
                          [(k[0], k[1], *buf.pop(k)) for k in done])
            d.commit(); n += len(done)
        if int(time.time()) % 300 < 2:
            tot = d.execute('SELECT count(*) FROM flow').fetchone()[0]
            d.execute('INSERT INTO health VALUES(?,?)', (int(time.time()), f'rows {tot} buffered {len(buf)}'))
            d.commit()
            print(f'{time.strftime("%H:%M:%S")} alive, flow rows {tot:,}, written this run {n:,}', flush=True)


async def main():
    d = db(); buf = {}
    print(f'{time.strftime("%H:%M:%S")} bn_flow start - RECORDER ONLY, spot+perp aggTrades, '
          f'{BUCKET_MS} ms buckets, signed by taker side', flush=True)
    await asyncio.gather(*[stream(n, u, buf) for n, u in STREAMS.items()], writer(d, buf))

if __name__ == '__main__':
    asyncio.run(main())
