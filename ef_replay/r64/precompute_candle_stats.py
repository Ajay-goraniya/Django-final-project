#!/usr/bin/env python3
"""
precompute_candle_stats.py -- per-candle observables for the CLEAN6 router, from the SAME raw
sources the replay uses. Two of Sol's six features (path efficiency, open crossings) are
properties of the price PATH inside a candle, which the synthetic generator had natively and a
5-minute OHLC bar does not. They are therefore measured from the real Binance spot aggTrade tape,
which is exactly the tape r6.4 itself watches, using r6.4's own definitions:

    path efficiency = |close - open| / (sum of absolute tick-to-tick moves inside the candle)
    open crossings  = number of times the traded price crosses the candle's open

The other four come from the official closed 5-minute klines. Nothing here is fitted and nothing
uses data from after the candle it describes.
"""
import pathlib, numpy as np, pandas as pd, pyarrow.parquet as pq
DATA = pathlib.Path(__file__).resolve().parents[2] / "btc_replay_2026-08-01_24h" / "normalized"
OUT = pathlib.Path(__file__).resolve().parent / "candle_stats_2026-08-01.parquet"
CANDLE_MS = 300_000
kl = pq.read_table(DATA / "spot_klines_5m.parquet").to_pandas()
kl["cid"] = (kl.open_time // 1000).astype("int64")
rows = {int(r.cid): dict(cid=int(r.cid), open=float(r.open), high=float(r.high), low=float(r.low),
                         close=float(r.close), volume=float(r.volume), travel=0.0, crosses=0.0, ticks=0)
        for r in kl.itertuples()}
for h in range(24):
    f = DATA / f"spot_aggtrades_{h:02d}.parquet"
    if not f.exists(): continue
    t = pq.read_table(f, columns=["timestamp", "price"]).to_pandas()
    t["cid"] = ((t.timestamp // 1000) // CANDLE_MS) * CANDLE_MS
    for cid, g in t.groupby("cid"):
        r = rows.get(int(cid))
        if r is None: continue
        p = g.price.to_numpy()
        r["travel"] += float(np.abs(np.diff(p)).sum()) if len(p) > 1 else 0.0
        o = r["open"]
        s = np.sign(p - o)
        s = s[s != 0]
        r["crosses"] += float(np.sum(s[1:] != s[:-1])) if len(s) > 1 else 0.0
        r["ticks"] += len(p)
D = pd.DataFrame([rows[c] for c in sorted(rows)])
D["eff"] = np.where(D.travel > 1e-9, (D.close - D.open).abs() / D.travel, 0.0)
rng = (D.high - D.low)
D["wick"] = np.where(rng > 1e-9, ((D.high - D[["open", "close"]].max(axis=1)) + (D[["open", "close"]].min(axis=1) - D.low)) / rng, 0.0)
D["body"] = (D.close - D.open).abs()
D["range"] = rng
D["rv"] = np.where(D.close > 0, rng / D.close, 0.0)
D["dir"] = np.sign(D.close - D.open)
D.to_parquet(OUT, index=False)
print(f"wrote {OUT.name}: {len(D)} candles, ticks {int(D.ticks.sum()):,}")
print(D[["eff", "wick", "crosses", "rv", "body", "range"]].describe().round(4).to_string())
