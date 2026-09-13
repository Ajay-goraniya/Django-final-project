#!/usr/bin/env python3
"""
build_poly_inferred_touch.py -- per-second INFERRED touch for the days with no order-book archive.

Method (no synthetic prices anywhere): on a CLOB, a taker BUY executes against the resting ask and
a taker SELL executes against the resting bid. So the most recent taker-BUY print is a price at
which the ask was actually available, and the most recent taker-SELL print is a price at which the
bid was actually available. Both are REAL executed prices, carried forward with their age.

    ask_inferred  = price of the latest taker BUY  at or before second T   (an upper bound on the
                    true best ask at T: the real ask may have improved since)
    bid_inferred  = price of the latest taker SELL at or before second T   (a lower bound on the
                    true best bid)

These are NOT quotes. Column names say inferred, and every row carries the age of the print it
came from so stale inferences can be filtered. Accuracy against real books is measured by
calibrate_inferred_touch.py on 2026-09-02/03, where both sources exist.
"""
import pathlib, sys
import numpy as np, pandas as pd
H = pathlib.Path(__file__).resolve().parent
TR = H.parent / "ef_arch/polymarket/fiveday/data/trades"
OUT = H / "predictfun/quotes_1s"; OUT.mkdir(parents=True, exist_ok=True)

def run(day, tag="poly_touch_1s"):
    src = TR / f"trades_{day}.parquet"
    if not src.exists(): print(f"{day}: no trade tape"); return None
    T = pd.read_parquet(src)
    T["tok"] = T.outcome.str.upper()
    T = T[(T.ts >= T.window_epoch) & (T.ts < T.window_epoch + 300)].sort_values("ts")
    rows = []
    for (ep, tok), g in T.groupby(["window_epoch", "tok"], sort=False):
        b = g[g.side == "BUY"]; s = g[g.side == "SELL"]
        bt = b.ts.to_numpy(); bp = b.price.to_numpy()
        st = s.ts.to_numpy(); sp = s.price.to_numpy()
        at = g.ts.to_numpy(); ap = g.price.to_numpy()
        for sec in range(300):
            Tsec = ep + sec
            r = dict(window_epoch=int(ep), side=tok, offset_s=sec, decision_ts_ms=Tsec * 1000)
            i = np.searchsorted(bt, Tsec, side="right") - 1
            if i >= 0: r["ask_inferred"] = float(bp[i]); r["ask_age_s"] = int(Tsec - bt[i])
            j = np.searchsorted(st, Tsec, side="right") - 1
            if j >= 0: r["bid_inferred"] = float(sp[j]); r["bid_age_s"] = int(Tsec - st[j])
            k = np.searchsorted(at, Tsec, side="right") - 1
            if k >= 0: r["last_trade_price"] = float(ap[k]); r["last_trade_age_s"] = int(Tsec - at[k])
            if "ask_inferred" in r and "bid_inferred" in r:
                r["mid_inferred"] = (r["ask_inferred"] + r["bid_inferred"]) / 2
                r["spread_inferred"] = r["ask_inferred"] - r["bid_inferred"]
            rows.append(r)
    D = pd.DataFrame(rows)
    out = OUT / f"{tag}_{day}.parquet"
    D.to_parquet(out, compression="zstd", index=False)
    both = D.mid_inferred.notna().mean() if "mid_inferred" in D else 0
    print(f"DONE {day}: {len(D):,} rows, {D.window_epoch.nunique()} markets, "
          f"both sides inferred on {100*both:.1f}% of seconds -> {out.name}", flush=True)
    return out

if __name__ == "__main__":
    for d in sys.argv[1:]: run(d)
