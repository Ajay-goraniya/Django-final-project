#!/usr/bin/env python3
"""
build_poly_second_trades.py -- PER-SECOND executed-price series for the days with no L2 archive
(2026-08-31, 09-01, 09-05, 09-06). Built from the real Polymarket trade tape already collected
(data-api /trades: every fill, taker side, price, size, 1-second timestamps).

This is LAST TRADED PRICE per second, not bid/ask. It is labelled that way in the schema and in
the manifest. Seconds with no fill are left null; nothing is forward-filled or interpolated here,
so the consumer decides how to carry a price forward.
"""
import pathlib, sys
import numpy as np, pandas as pd
H = pathlib.Path(__file__).resolve().parent
TR = H.parent / "ef_arch/polymarket/fiveday/data/trades"
OUT = H / "predictfun/quotes_1s"; OUT.mkdir(parents=True, exist_ok=True)

def run(day):
    src = TR / f"trades_{day}.parquet"
    if not src.exists(): print(f"{day}: no trade tape"); return
    T = pd.read_parquet(src)
    T["tok"] = T.outcome.str.upper()
    T = T[(T.ts >= T.window_epoch) & (T.ts < T.window_epoch + 300)]
    T["offset_s"] = (T.ts - T.window_epoch).astype(int)
    g = T.groupby(["window_epoch", "tok", "offset_s"])
    agg = g.apply(lambda d: pd.Series({
        "last_trade_price": float(d.price.iloc[-1]),
        "vwap_traded": float((d.price * d["size"]).sum() / d["size"].sum()),
        "low": float(d.price.min()), "high": float(d.price.max()),
        "n_fills": int(len(d)), "size_total": float(d["size"].sum()),
        "buy_frac": float((d.side == "BUY").mean()),
    }), include_groups=False).reset_index().rename(columns={"tok": "side"})
    out = OUT / f"poly_trades_1s_{day}.parquet"
    agg.to_parquet(out, compression="zstd", index=False)
    mk = agg.window_epoch.nunique()
    print(f"DONE {day}: {len(agg):,} traded seconds, {mk} markets, "
          f"coverage {100*len(agg)/(mk*2*300):.1f}% of market-token-seconds -> {out.name}", flush=True)

if __name__ == "__main__":
    for d in sys.argv[1:]: run(d)
