#!/usr/bin/env python3
"""Pull the public Polymarket data-api trade tape for every BTC 5m market of a date (real executed fills).
usage: fetch_trades_day.py YYYY-MM-DD  -> data/trades/trades_<date>.parquet"""
import json, time, urllib.request, sys, pathlib, concurrent.futures as cf
import pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
U = "https://data-api.polymarket.com/trades?market={}&limit=500&offset={}"
def get(u):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research/1.0"}), timeout=40) as r: return json.load(r)
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
    return None
def market_trades(row):
    m = row["market"]; cid = m["conditionId"]; out = []
    for off in range(0, 100000, 500):
        t = get(U.format(cid, off))
        if t is None: return row["epoch"], None
        out += [dict(window_epoch=row["epoch"], ts=x["timestamp"], side=x["side"], outcome=x["outcome"], price=float(x["price"]), size=float(x["size"]), tx=x.get("transactionHash")) for x in t]
        if len(t) < 500: break
    return row["epoch"], out
def run(date, workers=4):
    out = HERE / "data" / "trades" / f"trades_{date}.parquet"
    if out.exists(): print(date, "trades cached"); return out
    M = json.load(open(HERE / "data" / "markets" / f"btc5m_markets_{date}.json"))
    rows = []; failed = []
    with cf.ThreadPoolExecutor(workers) as ex:
        for ep, t in ex.map(market_trades, M["rows"]):
            if t is None: failed.append(ep)
            else: rows += t
    D = pd.DataFrame(rows); D.to_parquet(out, compression="zstd", index=False)
    print(f"{date}: trades {len(D):,} markets {D.window_epoch.nunique() if len(D) else 0} failed {len(failed)}", flush=True); return out
if __name__ == "__main__":
    run(sys.argv[1])
