#!/usr/bin/env python3
"""Real BTCUSDT USD-M perp aggTrades for 2026-09-06 UTC, paged by aggTradeId from the live
Binance futures REST API via www.binance.com (fapi.binance.com is geo-blocked here).
Nothing synthetic: every row is a real aggTrade as returned by the exchange."""
import json, time, urllib.request, pathlib, csv
B = "https://www.binance.com/fapi/v1/aggTrades"
DAY0 = 1788652800000   # 2026-09-06T00:00:00Z
OUT = pathlib.Path("trades/BTCUSDT-perp-aggTrades-2026-09-06.csv")
def get(url):
    for a in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=45) as r:
                return json.load(r)
        except Exception as e:
            if a == 5: raise
            time.sleep(1.5 * (a + 1))
# find the first aggTrade id at or after DAY0
first = get(f"{B}?symbol=BTCUSDT&startTime={DAY0}&endTime={DAY0+60000}&limit=1")
fid = first[0]["a"]
print("first agg id of the day:", fid, "T:", first[0]["T"], flush=True)
rows = []; cur = fid; last_T = 0; n = 0
w = OUT.open("w", newline=""); cw = csv.writer(w)
cw.writerow(["agg_trade_id", "price", "qty", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"])
t0 = time.time()
while True:
    d = get(f"{B}?symbol=BTCUSDT&fromId={cur}&limit=1000")
    if not d: break
    stop = False
    for x in d:
        if x["T"] >= DAY0 + 86400000: stop = True; break
        cw.writerow([x["a"], x["p"], x["q"], x["f"], x["l"], x["T"], x["m"]]); n += 1; last_T = x["T"]
    cur = d[-1]["a"] + 1
    if stop or len(d) < 1000: break
    if n % 100000 < 1000:
        print(f"  {n:,} rows, last T {last_T}, {time.time()-t0:.0f}s", flush=True)
    time.sleep(0.06)
w.close()
print(f"DONE {n:,} rows -> {OUT}  first {first[0]['T']} last {last_T}  {time.time()-t0:.0f}s")
