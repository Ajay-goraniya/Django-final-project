#!/usr/bin/env python3
"""
build_ladders.py -- turn extracted pmxt `book` snapshots into the compact
decision-time ladder dataset:

    polymarket_btc5m_2026-08-01_books.parquet

One row per (window, side, decision offset). At every offset t in
{5,10,...,295} s after window open, take the LATEST `book` snapshot whose
source timestamp <= window_open + t (causal; no future event), and walk the
ask ladder for fixed dollar stakes to get executable VWAP, shares, depth
consumed and an insufficient-liquidity flag. Also stores best bid/ask, mid,
spread, book age, and the number of snapshots seen so far.

Outcome per window comes from Gamma (Chainlink resolution), NOT from Binance.

Economics columns are left to the backtest; this file is pure market state.
"""
import glob, json, pathlib, sys
import numpy as np, pandas as pd, pyarrow as pa, pyarrow.parquet as pq

HERE = pathlib.Path(__file__).resolve().parent
M = json.load(open(HERE / "aug01_btc5m_markets.json")); W0 = M["W0"]
OFFSETS = list(range(5, 300, 5)); STAKES = (10.0, 100.0, 1000.0)
OUT = HERE / "polymarket_btc5m_2026-08-01_books.parquet"

def walk(asks, stake):
    """Buy `stake` dollars through ascending asks. Returns (vwap, shares, levels, ok)."""
    left = stake; shares = 0.0; cost = 0.0; lv = 0
    for p, s in asks:
        if left <= 1e-9: break
        take = min(s, left / p); shares += take; cost += take * p; left -= take * p; lv += 1
    if shares <= 0: return (np.nan, 0.0, 0, False)
    return (cost / shares, shares, lv, left <= 1e-6)

meta = {r["epoch"]: r for r in M["rows"]}
outcome = {}
for ep, r in meta.items():
    op = json.loads(r["market"]["outcomePrices"]); outs = json.loads(r["market"]["outcomes"])
    outcome[ep] = outs[int(np.argmax([float(x) for x in op]))].upper()      # 'UP' or 'DOWN'

rows = []
files = sorted(glob.glob(str(HERE / "books" / "hour_*.parquet")))
frames = []
for f in files:
    t = pq.read_table(f, columns=["timestamp", "timestamp_received", "event_type", "asset_id", "bids", "asks", "window_epoch", "side_label"])
    d = t.to_pandas(); d = d[d.event_type == "book"]
    d["ts"] = (d.timestamp.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1ms")
    d["tsr"] = (d.timestamp_received.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1ms")
    frames.append(d[["ts", "tsr", "asset_id", "bids", "asks", "window_epoch", "side_label"]])
B = pd.concat(frames, ignore_index=True).drop_duplicates(["asset_id", "ts", "tsr"]).sort_values(["window_epoch", "side_label", "ts"])
print(f"book snapshots: {len(B):,} across {B.window_epoch.nunique()} windows")

for (ep, side), g in B.groupby(["window_epoch", "side_label"], sort=True):
    ep = int(ep); ws = ep * 1000
    ts = g.ts.to_numpy(); tsr = g.tsr.to_numpy(); bids_j = g.bids.to_numpy(); asks_j = g.asks.to_numpy()
    for off in OFFSETS:
        T = ws + off * 1000
        i = np.searchsorted(ts, T, side="right") - 1           # latest snapshot with source ts <= T
        if i < 0:
            rows.append(dict(window_epoch=ep, side=side, offset_s=off, decision_ts_ms=T, has_book=False)); continue
        bids = sorted(((float(p), float(s)) for p, s in json.loads(bids_j[i])), key=lambda x: -x[0])
        asks = sorted(((float(p), float(s)) for p, s in json.loads(asks_j[i])), key=lambda x: x[0])
        bb = bids[0][0] if bids else np.nan; ba = asks[0][0] if asks else np.nan
        r = dict(window_epoch=ep, side=side, offset_s=off, decision_ts_ms=T, has_book=True,
                 book_ts_ms=int(ts[i]), book_recv_ms=int(tsr[i]), book_age_ms=int(T - ts[i]),
                 snapshots_so_far=int(i + 1), best_bid=bb, best_ask=ba,
                 mid=(bb + ba) / 2 if bids and asks else np.nan, spread=(ba - bb) if bids and asks else np.nan,
                 ask_depth_top5=float(sum(s for _, s in asks[:5])), bid_depth_top5=float(sum(s for _, s in bids[:5])),
                 n_ask_levels=len(asks), n_bid_levels=len(bids), outcome=outcome[ep])
        for st in STAKES:
            v, sh, lv, ok = walk(asks, st)
            k = f"s{int(st)}"; r[f"vwap_{k}"] = v; r[f"shares_{k}"] = sh; r[f"levels_{k}"] = lv; r[f"fill_ok_{k}"] = ok
        rows.append(r)

D = pd.DataFrame(rows)
pq.write_table(pa.Table.from_pandas(D, preserve_index=False), OUT, compression="zstd")
have = D[D.has_book]
print(f"wrote {OUT.name}: {len(D):,} rows, {D.window_epoch.nunique()} windows, book coverage {100*D.has_book.mean():.2f}%")
print(f"book age ms: p50 {have.book_age_ms.median():.0f}  p95 {have.book_age_ms.quantile(.95):.0f}  max {have.book_age_ms.max():.0f}")
print(f"spread: p50 {have.spread.median():.3f}  p90 {have.spread.quantile(.9):.3f}")
for st in STAKES:
    k = f"s{int(st)}"; print(f"stake ${int(st):>4}: fill_ok {100*have[f'fill_ok_{k}'].mean():.1f}%  vwap-best_ask p50 {(have[f'vwap_{k}']-have.best_ask).median():.4f}  p90 {(have[f'vwap_{k}']-have.best_ask).quantile(.9):.4f}")
print("outcomes:", D.drop_duplicates('window_epoch').outcome.value_counts().to_dict())
