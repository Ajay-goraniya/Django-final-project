"""Polymarket settlement-reference logger (read-only, Task 98).

Records the two public feeds that decide a 5-min BTC market:
  crypto_prices_chainlink  btc/usd   - the Chainlink value Polymarket settles on
  crypto_prices            btcusdt   - Binance spot at the same second, for the gap
plus the market metadata (eventStartTime, endDate, cryptoMarketConfig) per 5-min epoch.

No credentials, no engine contact, its own sqlite. The socket has no replay: on any
drop we reconnect at once and write a gaps row with the silent interval.

Task 98 correction (09-16 11:55 UTC): two orphaned copies of this logger were found running
on the AWS box, both writing every tick, which doubled every count reported before that time.
`ticks_u` and `INSERT OR IGNORE` below are the fix - a second writer, or a replayed frame after
a reconnect, is now a no-op instead of a duplicate row.
"""
import asyncio, json, sqlite3, time, sys, urllib.request

WS = "wss://ws-live-data.polymarket.com/"
GAMMA = "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}"
DB = "/home/ubuntu/ref_stream/ref_stream.sqlite3"
SUBS = {"action": "subscribe", "subscriptions": [
    {"topic": "crypto_prices_chainlink", "type": "update"},
    {"topic": "crypto_prices", "type": "update"}]}
KEEP = {("crypto_prices_chainlink", "btc/usd"), ("crypto_prices", "btcusdt")}

def db():
    c = sqlite3.connect(DB, timeout=15)
    c.execute("""CREATE TABLE IF NOT EXISTS ticks(
        arrival_ms INTEGER, topic TEXT, symbol TEXT, value REAL,
        full_accuracy TEXT, src_ts_ms INTEGER)""")
    c.execute("CREATE INDEX IF NOT EXISTS ticks_ts ON ticks(arrival_ms)")
    # Task 98: a second writer or a replayed frame after a reconnect must be a
    # no-op, not a duplicate row - this is what doubled every count before 09-16
    # 11:55 UTC.
    c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ticks_u
                 ON ticks(topic, symbol, src_ts_ms, value)""")
    c.execute("""CREATE TABLE IF NOT EXISTS markets(
        epoch INTEGER PRIMARY KEY, slug TEXT, question TEXT, event_start TEXT,
        end_date TEXT, config TEXT, resolution_source TEXT, fetched_ms INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS gaps(
        down_ms INTEGER, up_ms INTEGER, silent_s REAL, reason TEXT)""")
    c.commit()
    return c

def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ref-logger/1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

def record_market(c, epoch):
    if c.execute("SELECT 1 FROM markets WHERE epoch=?", (epoch,)).fetchone():
        return
    slug = f"btc-updown-5m-{epoch}"
    try:
        data = http_json(GAMMA.format(epoch))
    except Exception:
        return
    for e in data:
        for m in e.get("markets", []):
            if m.get("slug") == slug:
                c.execute("INSERT OR REPLACE INTO markets VALUES(?,?,?,?,?,?,?,?)",
                          (epoch, slug, m.get("question"), m.get("eventStartTime"),
                           m.get("endDate"), json.dumps(m.get("cryptoMarketConfig")),
                           m.get("resolutionSource"), int(time.time() * 1000)))
                c.commit()
                return

async def run():
    import websockets
    c = db()
    last_up = int(time.time() * 1000)
    while True:
        try:
            async with websockets.connect(WS, ping_interval=None, open_timeout=15,
                                          max_size=2 ** 22) as w:
                now = int(time.time() * 1000)
                if now - last_up > 2000:
                    c.execute("INSERT INTO gaps VALUES(?,?,?,?)",
                              (last_up, now, (now - last_up) / 1000, "reconnect"))
                    c.commit()
                await w.send(json.dumps(SUBS))
                batch, last_epoch = [], 0
                while True:
                    msg = await asyncio.wait_for(w.recv(), 30)
                    last_up = int(time.time() * 1000)
                    if not msg or not str(msg).startswith("{"):
                        continue
                    try:
                        j = json.loads(msg)
                    except Exception:
                        continue
                    p = j.get("payload") or {}
                    key = (j.get("topic"), str(p.get("symbol", "")).lower())
                    if key not in KEEP:
                        continue
                    batch.append((last_up, key[0], key[1], p.get("value"),
                                  str(p.get("full_accuracy_value")), p.get("timestamp")))
                    if len(batch) >= 20:
                        c.executemany("INSERT OR IGNORE INTO ticks VALUES(?,?,?,?,?,?)", batch)
                        c.commit()
                        batch = []
                    ep = int(time.time() // 300) * 300
                    if ep != last_epoch:
                        last_epoch = ep
                        record_market(c, ep)
        except Exception as e:
            now = int(time.time() * 1000)
            c.execute("INSERT INTO gaps VALUES(?,?,?,?)",
                      (last_up, now, (now - last_up) / 1000, type(e).__name__))
            c.commit()
            await asyncio.sleep(1)

asyncio.run(run())
