#!/usr/bin/env python3
"""
validate_depth20.py -- independent checks on the reconstructed depth20 ladders.

The ladders were built from a DIFF-only feed with no snapshot, so they must be validated against
something that did not come from the book. The independent witness is the real tick trade tape
(Binance Vision futures/um/daily/trades): every executed trade must print at or inside the
reconstructed touch at that instant. A book that has drifted shows up as trades outside the touch.
Also reports crossed-book rate and how the warm-up resolves. Nothing here repairs anything.
"""
import glob, json, pathlib, sys, zipfile, io
import numpy as np, pandas as pd, pyarrow.parquet as pq
H = pathlib.Path(__file__).resolve().parent
LAD = H / "depth/depth20"

def load_trades(day):
    z = H / f"trades/BTCUSDT-trades-{day}.zip"
    if z.exists():
        with zipfile.ZipFile(z) as zz:
            n = zz.namelist()[0]
            d = pd.read_csv(zz.open(n), usecols=["price", "time"])
        return d.rename(columns={"time": "ts_ms"})
    c = H / f"trades/BTCUSDT-perp-aggTrades-{day}.csv"
    if c.exists():
        d = pd.read_csv(c, usecols=["price", "transact_time"])
        return d.rename(columns={"transact_time": "ts_ms"})
    return None

def check(day, sample_hours=None):
    fs = sorted(glob.glob(str(LAD / f"perp_depth20_{day}_*.parquet")))
    if not fs: return None
    hrs = sample_hours or list(range(len(fs)))
    T = load_trades(day)
    out = dict(day=day, hours=len(fs))
    T = load_trades(day)
    per_hour = []
    tot_in = tot_n = 0
    L_all = []
    for i in hrs:
        if i >= len(fs): continue
        t = pq.read_table(fs[i], columns=["timestamp", "bid_px_0", "ask_px_0", "is_crossed",
                                          "is_warmup", "n_bid_levels", "n_ask_levels"]).to_pandas()
        t = t.sort_values("timestamp"); L_all.append(t)
        # compare ONLY trades that fall inside this hour's own ladder span
        t2 = t[t.is_warmup == 0]
        if T is None or len(t2) == 0: continue
        ts = t2.timestamp.to_numpy() // 1000
        bb = t2.bid_px_0.to_numpy(); ba = t2.ask_px_0.to_numpy()
        Tt = T[(T.ts_ms >= ts.min()) & (T.ts_ms <= ts.max())]
        if not len(Tt): continue
        idx = np.searchsorted(ts, Tt.ts_ms.to_numpy(), side="right") - 1
        ok = idx >= 0
        idx = idx[ok]; p = Tt.price.to_numpy()[ok]
        age_ms = Tt.ts_ms.to_numpy()[ok] - ts[idx]
        fresh = age_ms <= 1000                      # ladder must be at most 1 s stale
        idx = idx[fresh]; p = p[fresh]
        inside = (p >= bb[idx] - 1e-9) & (p <= ba[idx] + 1e-9)
        tot_in += int(inside.sum()); tot_n += int(len(p))
        per_hour.append(dict(hour=i, trades=int(len(p)), inside_pct=round(100*float(inside.mean()), 3)))
    L = pd.concat(L_all, ignore_index=True)
    out["ladders_checked"] = len(L)
    out["crossed_pct"] = round(100 * L.is_crossed.mean(), 3)
    out["warmup_rows"] = int(L.is_warmup.sum())
    out["median_levels"] = [int(L.n_bid_levels.median()), int(L.n_ask_levels.median())]
    out["spread_p50"] = round(float((L.ask_px_0 - L.bid_px_0).median()), 3)
    out["spread_p99"] = round(float((L.ask_px_0 - L.bid_px_0).quantile(.99)), 3)
    out["trades_checked"] = tot_n
    out["trades_inside_touch_pct"] = round(100 * tot_in / tot_n, 3) if tot_n else None
    out["trades_outside"] = tot_n - tot_in
    out["per_hour"] = per_hour
    return out

if __name__ == "__main__":
    days = sys.argv[1:] or ["2026-08-31", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
    res = []
    for d in days:
        r = check(d, sample_hours=[0, 6, 12, 18])
        if r: res.append(r); print(json.dumps(r), flush=True)
    json.dump(res, open(H / "depth/depth20/validation.json", "w"), indent=1)
    print("\n%-12s %9s %9s %10s %12s %14s %10s" % ("day", "ladders", "crossed%", "spread50", "trades", "inside touch%", "outside"))
    for r in res:
        print("%-12s %9s %9.3f %10.3f %12s %14s %10s" % (
            r["day"], f"{r['ladders_checked']:,}", r["crossed_pct"], r["spread_p50"],
            f"{r.get('trades_checked',0):,}", r.get("trades_inside_touch_pct", "n/a"), r.get("trades_outside", "n/a")))
