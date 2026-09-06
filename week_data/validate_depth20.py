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
    lad = []
    for i in hrs:
        if i >= len(fs): continue
        t = pq.read_table(fs[i], columns=["timestamp", "bid_px_0", "ask_px_0", "is_crossed",
                                          "is_warmup", "n_bid_levels", "n_ask_levels"]).to_pandas()
        lad.append(t)
    L = pd.concat(lad, ignore_index=True).sort_values("timestamp")
    out["ladders_checked"] = len(L)
    out["crossed_pct"] = round(100 * L.is_crossed.mean(), 3)
    out["warmup_rows"] = int(L.is_warmup.sum())
    out["median_levels"] = [int(L.n_bid_levels.median()), int(L.n_ask_levels.median())]
    out["spread_p50"] = round(float((L.ask_px_0 - L.bid_px_0).median()), 3)
    out["spread_p99"] = round(float((L.ask_px_0 - L.bid_px_0).quantile(.99)), 3)
    if T is not None and len(T):
        L2 = L[L.is_warmup == 0]
        ts = (L2.timestamp.to_numpy() // 1000)
        bb = L2.bid_px_0.to_numpy(); ba = L2.ask_px_0.to_numpy()
        lo, hi = ts.min(), ts.max()
        Tt = T[(T.ts_ms >= lo) & (T.ts_ms <= hi)]
        if len(Tt):
            idx = np.searchsorted(ts, Tt.ts_ms.to_numpy(), side="right") - 1
            ok = idx >= 0
            idx = idx[ok]; p = Tt.price.to_numpy()[ok]
            inside = (p >= bb[idx] - 1e-9) & (p <= ba[idx] + 1e-9)
            out["trades_checked"] = int(len(p))
            out["trades_inside_touch_pct"] = round(100 * float(inside.mean()), 3)
            out["trades_outside"] = int((~inside).sum())
            if (~inside).any():
                dev = np.where(p < bb[idx], bb[idx] - p, p - ba[idx])[~inside]
                out["outside_dev_usd_p50"] = round(float(np.median(dev)), 2)
                out["outside_dev_usd_p99"] = round(float(np.quantile(dev, .99)), 2)
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
