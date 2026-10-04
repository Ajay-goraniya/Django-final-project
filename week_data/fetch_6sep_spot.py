#!/usr/bin/env python3
"""Real BTCUSDT SPOT aggTrades + 5m klines for 2026-09-06 UTC from data-api.binance.vision."""
import json, time, urllib.request, pathlib, csv
DAY0 = 1788652800000
def get(u):
    for a in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=45) as r:
                return json.load(r)
        except Exception:
            if a == 5: raise
            time.sleep(1.5 * (a + 1))
k = get(f"https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={DAY0}&endTime={DAY0+86400000}&limit=1000")
p = pathlib.Path("trades/BTCUSDT-spot-klines5m-2026-09-06.csv")
with p.open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_base","taker_quote","ignore"])
    for r in k: w.writerow(r)
print("klines", len(k), "->", p, flush=True)
B = "https://data-api.binance.vision/api/v3/aggTrades"
first = get(f"{B}?symbol=BTCUSDT&startTime={DAY0}&endTime={DAY0+60000}&limit=1")
cur = first[0]["a"]; n = 0; last = 0
out = pathlib.Path("trades/BTCUSDT-spot-aggTrades-2026-09-06.csv")
with out.open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["agg_trade_id","price","qty","first_trade_id","last_trade_id","transact_time","is_buyer_maker"])
    while True:
        d = get(f"{B}?symbol=BTCUSDT&fromId={cur}&limit=1000")
        if not d: break
        stop = False
        for x in d:
            if x["T"] >= DAY0 + 86400000: stop = True; break
            w.writerow([x["a"], x["p"], x["q"], x["f"], x["l"], x["T"], x["m"]]); n += 1; last = x["T"]
        cur = d[-1]["a"] + 1
        if stop or len(d) < 1000: break
        if n % 100000 < 1000: print(f"  spot {n:,} rows", flush=True)
        time.sleep(0.05)
print(f"DONE spot aggTrades {n:,} rows, last T {last}")
