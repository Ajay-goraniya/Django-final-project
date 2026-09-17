#!/usr/bin/env python3
"""How close is the trade-inferred touch to the real book? Measured on the days where both exist."""
import pathlib, numpy as np, pandas as pd
Q = pathlib.Path(__file__).resolve().parent / "predictfun/quotes_1s"
for day in ("2026-09-02", "2026-09-03"):
    r = pd.read_parquet(Q / f"poly_quotes_1s_{day}.parquet")
    t = pd.read_parquet(Q / f"poly_touch_1s_{day}.parquet")
    m = r.merge(t, on=["window_epoch", "side", "offset_s"], suffixes=("", "_inf"))
    m = m[m.best_ask.notna() & m.best_bid.notna() & m.ask_inferred.notna() & m.bid_inferred.notna()]
    if not len(m): print(day, "no overlap"); continue
    da = m.ask_inferred - m.best_ask
    db = m.best_bid - m.bid_inferred
    dm = m.mid_inferred - m.mid
    print(f"{day}: overlapping seconds {len(m):,}")
    print(f"   inferred ask - real ask : p50 {da.median():+.4f}  p10 {da.quantile(.1):+.4f}  p90 {da.quantile(.9):+.4f}  |within 0.01| {100*(da.abs()<=0.0101).mean():.1f}%")
    print(f"   real bid - inferred bid : p50 {db.median():+.4f}  p10 {db.quantile(.1):+.4f}  p90 {db.quantile(.9):+.4f}  |within 0.01| {100*(db.abs()<=0.0101).mean():.1f}%")
    print(f"   inferred mid - real mid : p50 {dm.median():+.4f}  MAE {dm.abs().mean():.4f}  |within 0.01| {100*(dm.abs()<=0.0101).mean():.1f}%  |within 0.02| {100*(dm.abs()<=0.0201).mean():.1f}%")
    fr = m[m.ask_age_s <= 5]
    if len(fr):
        d2 = fr.mid_inferred - fr.mid
        print(f"   fresh only (buy print <=5 s old, {len(fr):,} rows): mid MAE {d2.abs().mean():.4f}  |within 0.01| {100*(d2.abs()<=0.0101).mean():.1f}%")
