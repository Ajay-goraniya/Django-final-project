#!/usr/bin/env python3
"""Polymarket RTDS recorder - Chainlink oracle + spot. RECORDER ONLY, places nothing.

The owner is right that Polymarket publishes its own price feeds and that beats reconstructing them.
What this box could actually reach, after probing (see the poke for the full trail):

  ws-live-data.polymarket.com, ROOT path, and the envelope is NOT the documented one:
      {"action":"subscribe","subscriptions":[{"topic":..., "type":...}]}
  The documented {"op":"subscribe","subscriptions":[{"channel":"price.crypto.twap","filter":{...}}]} is
  rejected - "op" is ignored, dotted topics return "Invalid request body", and ANY "filters" value tried
  so far silently drops every message rather than erroring.

  WORKS   crypto_prices           / update   Binance-style spot (btcusdt, ethusdt, ...)
  WORKS   crypto_prices_chainlink / update   CHAINLINK oracle (btc/usd) - the settlement source itself
  NOT FOUND  every twap topic tried: crypto_prices/twap, crypto_prices_twap, crypto_twap, twap,
             crypto_prices_chainlink_twap, crypto_price_twap, twap_prices, agg_twap, price.crypto.twap

So the TWAP channel is NOT off limits, it is NOT NAMED what the docs say on this deployment. The Chainlink
feed is still worth having on its own: it is the oracle Zurich has been RESAMPLING into tape1s.ref_px, and
this is it at source.

Also: this host has NO IPv6 route, and ws-live-data resolves to Cloudflare v6 first, so every connect must
force AF_INET or it times out with no handshake - which is what made the endpoint look unreachable at all.
"""
import asyncio, json, socket, sqlite3, time, websockets

DB = '/home/ubuntu/pm_multi/rtds.sqlite3'
URL = 'wss://ws-live-data.polymarket.com'
SUBS = [('crypto_prices_chainlink', 'update'), ('crypto_prices', 'update')]
DDL = ["""CREATE TABLE IF NOT EXISTS px(ts_ms INTEGER, topic TEXT, symbol TEXT, value REAL,
          full_value TEXT, src_ts INTEGER, PRIMARY KEY(ts_ms, topic, symbol))""",
       "CREATE INDEX IF NOT EXISTS px_sym ON px(symbol, src_ts)",
       "CREATE TABLE IF NOT EXISTS health(ts INTEGER, note TEXT)"]
WANT = ('btc/usd', 'btcusdt')


def db():
    d = sqlite3.connect(DB, timeout=30)
    d.execute('PRAGMA journal_mode=WAL')
    for q in DDL: d.execute(q)
    return d


async def main():
    d = db(); n = 0; last = 0
    print(f'{time.strftime("%H:%M:%S")} rtds start - RECORDER ONLY, {[s[0] for s in SUBS]}', flush=True)
    while True:
        try:
            async with websockets.connect(URL, ping_interval=20, family=socket.AF_INET,
                                          max_queue=4096) as w:
                await w.send(json.dumps({"action": "subscribe", "subscriptions":
                                         [{"topic": t, "type": ty} for t, ty in SUBS]}))
                print(f'{time.strftime("%H:%M:%S")} subscribed', flush=True)
                buf = []
                while True:
                    m = await asyncio.wait_for(w.recv(), timeout=120)
                    s = m if isinstance(m, str) else m.decode()
                    if not s.strip(): continue
                    try: e = json.loads(s)
                    except Exception: continue
                    p = e.get('payload') or {}
                    sym = str(p.get('symbol', '')).lower()
                    if sym not in WANT: continue
                    v = p.get('value')
                    if v is None: continue
                    buf.append((int(e.get('timestamp') or time.time() * 1000), str(e.get('topic')), sym,
                                float(v), str(p.get('full_accuracy_value') or ''), int(p.get('timestamp') or 0)))
                    if len(buf) >= 40:
                        d.executemany('INSERT OR REPLACE INTO px VALUES(?,?,?,?,?,?)', buf)
                        d.commit(); n += len(buf); buf = []
                    if time.time() - last > 300:
                        last = time.time()
                        tot = d.execute('SELECT count(*) FROM px').fetchone()[0]
                        d.execute('INSERT INTO health VALUES(?,?)', (int(last), f'rows {tot}'))
                        d.commit()
                        print(f'{time.strftime("%H:%M:%S")} alive, rows {tot:,} (+{n:,} this run)', flush=True)
        except Exception as ex:
            print(f'{time.strftime("%H:%M:%S")} reconnect after {repr(ex)[:90]}', flush=True)
            await asyncio.sleep(3)

if __name__ == '__main__':
    asyncio.run(main())
