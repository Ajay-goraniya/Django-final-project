#!/usr/bin/env python3
"""
validate.py -- quick trust checks over the normalized dataset.

Includes an independent correctness proof for the reconstructed order book:
the top-20 rebuilt from `incremental_book_L2` is compared, level by level,
against Tardis' own `book_snapshot_25` product at identical timestamps. The two
are produced by different pipelines from the same stream, so agreement means the
reconstruction is faithful. Comparison is by exact (timestamp, local_timestamp)
match -- no future row is used to fix any earlier one.
"""
import glob, gzip, json, pathlib
import pandas as pd, numpy as np, pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent
NORM, VAL = ROOT / "normalized", ROOT / "validation"
WIN_START, WIN_END = 1785542400_000_000, 1785628800_000_000
K = 20
out = {"window_utc": {"start": "2026-08-01T00:00:00Z", "end": "2026-08-02T00:00:00Z",
                      "end_exclusive": True},
       "canonical_clock": "UTC", "timestamp_unit": "microseconds"}

def parts(prefix):
    return sorted(glob.glob(str(NORM / f"{prefix}_[0-2][0-9].parquet")))

# ------------------------------------------------------------------- klines
kl = pq.read_table(NORM / "spot_klines_5m.parquet").to_pandas()
d = kl.open_time.diff().dropna().astype("int64")
out["klines"] = {
    "measured_candles": int(len(kl)), "expected": 288,
    "exactly_288": len(kl) == 288,
    "consecutive_5m": bool((d == 300_000_000).all()),
    "duplicates": int(kl.open_time.duplicated().sum()),
    "all_completed_in_window": bool((kl.close_time < WIN_END).all()),
    "first_open_us": int(kl.open_time.iloc[0]), "last_close_us": int(kl.close_time.iloc[-1]),
    "preroll_candles": int(pq.read_table(NORM / "spot_klines_5m_preroll.parquet").num_rows)
                       if (NORM / "spot_klines_5m_preroll.parquet").exists() else 0,
    "columns": list(kl.columns),
}

# ------------------------------------------------------------------- trades
def trade_stats(prefix, idcol):
    fs = parts(prefix)
    if not fs:
        return {"files": 0}
    df = pd.concat([pq.read_table(f).to_pandas() for f in fs], ignore_index=True)
    ts = df.timestamp.to_numpy()
    st = {
        "files": len(fs), "rows": int(len(df)),
        "first_ts_us": int(ts.min()), "last_ts_us": int(ts.max()),
        "within_window": bool((ts >= WIN_START).all() and (ts < WIN_END).all()),
        "monotonic_after_sort": bool((np.diff(ts) >= 0).all()),
        "duplicate_ids": int(df[idcol].duplicated().sum()),
    }
    ids = np.sort(df[idcol].to_numpy())
    gaps = np.diff(ids)
    st["id_gaps_gt1"] = int((gaps > 1).sum())
    st["id_missing_count"] = int((gaps[gaps > 1] - 1).sum())
    pre = NORM / f"{prefix}_preroll.parquet"
    st["preroll_rows"] = int(pq.read_table(pre).num_rows) if pre.exists() else 0
    return st

out["spot_aggtrades"] = trade_stats("spot_aggtrades", "agg_trade_id")
out["perp_aggtrades"] = trade_stats("perp_aggtrades", "agg_trade_id")
out["perp_trades"] = trade_stats("perp_trades", "id")

# -------------------------------------------------------------- perp depth20
fs = parts("perp_depth20")
tss, crossed, resync, thin, nb_min, na_min = [], 0, 0, 0, 10**9, 10**9
rows = 0
for f in fs:
    t = pq.read_table(f, columns=["timestamp", "is_crossed", "is_resync",
                                  "n_bid_levels", "n_ask_levels"]).to_pandas()
    rows += len(t); tss.append(t.timestamp.to_numpy())
    crossed += int(t.is_crossed.sum()); resync += int(t.is_resync.sum())
    thin += int(((t.n_bid_levels < K) | (t.n_ask_levels < K)).sum())
    nb_min = min(nb_min, int(t.n_bid_levels.min())); na_min = min(na_min, int(t.n_ask_levels.min()))
ts = np.concatenate(tss); ts.sort()
g = np.diff(ts)
# fraction of the 24h measured period covered by a depth update within 1s
covered = float(np.clip(g, 0, 1_000_000).sum() + 1_000_000) / (WIN_END - WIN_START)
out["perp_depth20"] = {
    "files": len(fs), "snapshots": rows,
    "first_ts_us": int(ts.min()), "last_ts_us": int(ts.max()),
    "within_window": bool(ts.min() >= WIN_START and ts.max() < WIN_END),
    "monotonic": bool((g >= 0).all()),
    "crossed_books": crossed, "resync_events": resync,
    "messages_with_fewer_than_20_levels": thin,
    "min_bid_levels": nb_min, "min_ask_levels": na_min,
    "top20_available_pct": round(100.0 * (rows - thin) / rows, 6) if rows else 0,
    "max_gap_us": int(g.max()), "gap_p50_us": int(np.percentile(g, 50)),
    "gap_p95_us": int(np.percentile(g, 95)), "gap_p99_us": int(np.percentile(g, 99)),
    "mean_interval_us": float(g.mean()),
    "pct_period_with_depth_fresher_than_1s": round(100.0 * min(covered, 1.0), 4),
    "sequence_ids": "UNAVAILABLE - Tardis incremental_book_L2 CSV carries no "
                    "exchange update id; ordering is by (timestamp, local_timestamp) "
                    "in provider file order",
}

# ------------------- cross-check reconstruction vs provider book_snapshot_25
SNAP = ROOT / "raw/tardis/binance-futures_book_snapshot_25_2026-08-01_BTCUSDT.csv.gz"
cmp_stats = {"compared_snapshots": 0, "matched_timestamps": 0,
             "level_price_mismatches": 0, "level_qty_mismatches": 0,
             "unmatched_provider_snapshots": 0, "levels_compared": 0}
usecols = ["timestamp", "local_timestamp"] + \
          [f"{s}[{i}].{f}" for i in range(K) for s in ("asks", "bids") for f in ("price", "amount")]
cache_hour, cache = None, {}
HOUR = 3_600_000_000
for chunk in pd.read_csv(SNAP, usecols=usecols, chunksize=100_000):
    chunk = chunk[(chunk.timestamp >= WIN_START) & (chunk.timestamp < WIN_END)]
    if chunk.empty:
        continue
    for hour, sub in chunk.groupby((chunk.timestamp - WIN_START) // HOUR):
        f = NORM / f"perp_depth20_{int(hour):02d}.parquet"
        if not f.exists():
            continue
        if cache_hour != hour:
            r = pq.read_table(f).to_pandas()
            cache = {(int(a), int(b)): i for i, (a, b) in
                     enumerate(zip(r.timestamp, r.local_timestamp))}
            cache_df, cache_hour = r, hour
        idx = [cache.get((int(a), int(b)), -1)
               for a, b in zip(sub.timestamp, sub.local_timestamp)]
        ok = [i for i in idx if i >= 0]
        cmp_stats["compared_snapshots"] += len(sub)
        cmp_stats["unmatched_provider_snapshots"] += len(idx) - len(ok)
        if not ok:
            continue
        keep = [j for j, i in enumerate(idx) if i >= 0]
        mine = cache_df.iloc[ok]
        theirs = sub.iloc[keep]
        cmp_stats["matched_timestamps"] += len(ok)
        for i in range(K):
            for side, col in (("bid", "bids"), ("ask", "asks")):
                mp = mine[f"{side}_px_{i}"].to_numpy(dtype="float64")
                tp = theirs[f"{col}[{i}].price"].to_numpy(dtype="float64")
                mq = mine[f"{side}_qty_{i}"].to_numpy(dtype="float64")
                tq = theirs[f"{col}[{i}].amount"].to_numpy(dtype="float64")
                both_nan = np.isnan(mp) & np.isnan(tp)
                cmp_stats["level_price_mismatches"] += int(
                    (~(np.isclose(mp, tp, rtol=0, atol=1e-8) | both_nan)).sum())
                bn = np.isnan(mq) & np.isnan(tq)
                cmp_stats["level_qty_mismatches"] += int(
                    (~(np.isclose(mq, tq, rtol=0, atol=1e-8) | bn)).sum())
                cmp_stats["levels_compared"] += len(mp)
m = cmp_stats["matched_timestamps"]
cmp_stats["price_agreement_pct"] = round(
    100.0 * (1 - cmp_stats["level_price_mismatches"] / max(cmp_stats["levels_compared"], 1)), 6)
cmp_stats["qty_agreement_pct"] = round(
    100.0 * (1 - cmp_stats["level_qty_mismatches"] / max(cmp_stats["levels_compared"], 1)), 6)
out["depth_reconstruction_crosscheck"] = cmp_stats

out["notes"] = {
    "SPOT_DEPTH_UNAVAILABLE": "Binance publishes no historical spot L2 depth in any "
                              "public archive (spot daily families: aggTrades, klines, trades).",
    "PREDICT_BOOK_HISTORY_UNAVAILABLE": "api.predict.fun/v1/markets -> HTTP 401; no read credential.",
    "PRE_ROLL_PERP_DEPTH_UNAVAILABLE": "Tardis free tier serves only the first day of each "
                                       "month, so 2026-07-31 perp L2 is not retrievable. "
                                       "Pre-roll covers spot klines/aggTrades and perp aggTrades only.",
    "LIVE_RECEIVE_CLOCK": "AVAILABLE for Tardis products as `local_timestamp` (collector "
                          "receive clock, microseconds). Binance Vision archives carry "
                          "exchange time only.",
}
VAL.mkdir(exist_ok=True)
(VAL / "validation.json").write_text(json.dumps(out, indent=2, default=str))
print(json.dumps(out, indent=2, default=str)[:4000])
