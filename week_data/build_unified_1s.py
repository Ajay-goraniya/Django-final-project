#!/usr/bin/env python3
"""
build_unified_1s.py -- one per-second Polymarket quote file per day, all 7 days, with the
provenance of every row stated in the data.

quote_source column:
  "book"           real L2: best_bid/best_ask from the venue's price_change stream, and ask-ladder
                   VWAP from the latest full book snapshot. Executable.
  "trade_inferred" no book archive for that market-second: best_ask is the latest taker-BUY print
                   and best_bid the latest taker-SELL print. Real executed prices, but a noisy
                   estimate of the touch (measured on 2026-09-02/03: mid MAE 0.040 and 0.075,
                   within 1 cent 48% and 39% of the time, median bias 0.000). No ladder VWAP.
Nothing is synthetic and nothing is interpolated; missing stays missing.
"""
import pathlib, sys
import numpy as np, pandas as pd
H = pathlib.Path(__file__).resolve().parent
Q = H / "predictfun/quotes_1s"
OUT = H / "predictfun/quotes_1s_unified"; OUT.mkdir(parents=True, exist_ok=True)
DAYS = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
KEY = ["window_epoch", "side", "offset_s"]
LAD = [f"{p}_s{s}" for s in (2, 5, 10, 100) for p in ("vwap", "shares", "levels", "fill_ok")]

for day in DAYS:
    t = pd.read_parquet(Q / f"poly_touch_1s_{day}.parquet")
    base = t[KEY + ["decision_ts_ms", "ask_inferred", "bid_inferred", "mid_inferred", "spread_inferred",
                    "ask_age_s", "bid_age_s", "last_trade_price", "last_trade_age_s"]].copy()
    bp = Q / f"poly_quotes_1s_{day}.parquet"
    if bp.exists():
        r = pd.read_parquet(bp)
        keep = KEY + ["best_bid", "best_ask", "mid", "spread", "quote_age_ms", "book_age_ms",
                      "n_bid_levels", "n_ask_levels", "ask_depth_top5", "bid_depth_top5"] + \
               [c for c in LAD if c in r.columns]
        m = base.merge(r[keep], on=KEY, how="outer")
    else:
        m = base.copy()
        for c in ["best_bid", "best_ask", "mid", "spread", "quote_age_ms", "book_age_ms",
                  "n_bid_levels", "n_ask_levels", "ask_depth_top5", "bid_depth_top5"] + LAD:
            m[c] = np.nan
    has_book = m.best_ask.notna() & m.best_bid.notna()
    m["quote_source"] = np.where(has_book, "book", "trade_inferred")
    m["best_ask"] = np.where(has_book, m.best_ask, m.ask_inferred)
    m["best_bid"] = np.where(has_book, m.best_bid, m.bid_inferred)
    m["mid"] = np.where(has_book, m["mid"], m.mid_inferred)
    m["spread"] = np.where(has_book, m["spread"], m.spread_inferred)
    m["quote_age_ms"] = np.where(has_book, m.quote_age_ms, m.ask_age_s * 1000)
    m.loc[m.best_ask.isna() & m.best_bid.isna(), "quote_source"] = "none"
    m = m.sort_values(KEY).reset_index(drop=True)
    out = OUT / f"poly_1s_{day}.parquet"
    m.to_parquet(out, compression="zstd", index=False)
    vc = m.quote_source.value_counts().to_dict()
    ex = int(m.get("fill_ok_s10", pd.Series(dtype=bool)).fillna(False).sum())
    print(f"{day}: {len(m):>7,} rows  {m.window_epoch.nunique():>3} markets  "
          f"book {vc.get('book',0):>7,}  inferred {vc.get('trade_inferred',0):>7,}  none {vc.get('none',0):>6,}  "
          f"$10-executable {ex:,}", flush=True)
