#!/usr/bin/env python3
"""Calibrate trade-inferred asks onto REAL executable economics.

On 2026-09-02/03 both a trade-inferred ask and a real ask-ladder price exist
for the same market-second, so every EF fire on those days is a paired
observation. The inferred ask runs ~1.8c cheap and, because a prediction
market pays 1/q, that bias inflates the mean payoff-if-win from 2.70 to 4.37.

Calibrating the PRICE (median inferred -> median executable) does not fix
this: averaging prices destroys the convexity that produces the error, and
overcorrects to -32%. So we calibrate the quantity that actually matters,
E[payoff | inferred bin], measured on the paired fires, then invert it to the
effective price that reproduces that payoff:

    payoff(q) = (1 - r(1-q))/q - 1     =>     q = (1-r) / (payoff + 1 - r)

The result is a price the staking simulation can use directly, whose expected
economics match the real book. Fitted on real paired observations only.
"""
import bisect
import json
import math
import pathlib
import sqlite3
import statistics

import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOK_DAYS = ("2026-09-02", "2026-09-03")
R = 0.07
COLS = ["window_epoch", "side", "offset_s", "quote_source", "best_ask", "ask_inferred",
        "vwap_s10", "shares_s10", "fill_ok_s10", "vwap_s100", "shares_s100", "fill_ok_s100"]

num = lambda x: x if isinstance(x, (int, float)) and x is not None and math.isfinite(x) and 0 < x < 1 else None
payoff = lambda q: (1.0 - R * (1.0 - q)) / q - 1.0
inv_payoff = lambda p: (1.0 - R) / (p + 1.0 - R)


def _exec_price(row):
    ex = None
    for tier in ("s10", "s100"):
        v = num(row.get("vwap_" + tier))
        if v and row.get("shares_" + tier) and row.get("fill_ok_" + tier):
            ex = v
    return ex or num(row.get("best_ask"))


def paired(tags=("v9_4", "v9_5", "b36")):
    Q, S = {}, {}
    for D in BOOK_DAYS:
        t = pq.read_table(ROOT / f"week_data/predictfun/quotes_1s_unified/poly_1s_{D}.parquet", columns=COLS)
        c = {n: t.column(n).to_pylist() for n in COLS}
        for i in range(t.num_rows):
            if c["quote_source"][i] == "book":
                Q[(c["window_epoch"][i], str(c["side"][i]).upper(), c["offset_s"][i])] = {k: c[k][i] for k in COLS[3:]}
        rows = json.loads((ROOT / f"ef_arch/polymarket/fiveday/data/markets/btc5m_markets_{D}.json").read_text())["rows"]
        for r in rows:
            m = r["market"]
            try:
                names = json.loads(m["outcomes"])
                prices = json.loads(m["outcomePrices"])
            except Exception:
                continue
            w = [n for n, p in zip(names, prices) if str(p) == "1"]
            if len(w) == 1:
                S[int(r["epoch"])] = w[0].upper()
    out = []
    for tag in tags:
        con = sqlite3.connect(f"file:{ROOT}/week_replay/runs/week_{tag}.sqlite3?mode=ro", uri=True, timeout=30)
        for cid, d, ts in con.execute("SELECT candle_id,direction,ts_ms FROM trades WHERE kind='EF'"):
            e = cid // 1000
            if S.get(e) is None:
                continue
            row = Q.get((e, d, int(round((ts - cid) / 1000.0))))
            if not row:
                continue
            inf, ex = num(row.get("ask_inferred")), _exec_price(row)
            if inf and ex:
                out.append((inf, ex))
    out.sort()
    return out


def build(n_bins=10, min_per_bin=25):
    """Piecewise-CONSTANT bins: an inferred price in a bin maps to the single
    effective price whose payoff equals the mean payoff the real ladder paid
    on that bin's fires. Constant, not interpolated: interpolating reintroduces
    within-bin convexity (and extrapolating below the cheapest knot drives
    prices toward zero, where 1/q explodes) which is the whole error we are
    removing. Returns (edges, eff) with len(eff) == len(edges) + 1."""
    pairs = paired()
    per = max(min_per_bin, len(pairs) // n_bins)
    chunks = [pairs[s:s + per] for s in range(0, len(pairs), per)]
    if len(chunks) > 1 and len(chunks[-1]) < min_per_bin:
        chunks[-2].extend(chunks.pop())
    eff = [inv_payoff(sum(payoff(b) for _a, b in ch) / len(ch)) for ch in chunks]
    edges = [ch[-1][0] for ch in chunks[:-1]]          # upper inferred bound of each bin
    return edges, eff, pairs


def apply(edges, eff, q):
    if q is None:
        return None
    return min(0.99, max(0.01, eff[bisect.bisect_left(edges, q)]))


if __name__ == "__main__":
    edges, eff, pairs = build()
    print(f"fitted on {len(pairs)} paired EF fires")
    print(f"{'inferred range':>20}{'effective price':>17}")
    lo = 0.0
    for i, e in enumerate(eff):
        hi = edges[i] if i < len(edges) else 1.0
        print(f"{lo:8.3f} - {hi:<8.3f}{eff[i]:>17.3f}")
        lo = hi
    real = sum(payoff(b) for _a, b in pairs) / len(pairs)
    raw = sum(payoff(a) for a, _b in pairs) / len(pairs)
    cal = sum(payoff(apply(edges, eff, a)) for a, _b in pairs) / len(pairs)
    print(f"\nmean payoff-if-win   real book {real:.4f}   raw inferred {raw:.4f}   CALIBRATED {cal:.4f}")
    print(f"residual: {100 * (cal - real) / real:+.1f}%   (raw was {100 * (raw - real) / real:+.1f}%)")
    json.dump({"edges": edges, "eff": eff, "n_pairs": len(pairs)},
              open(ROOT / "week_replay/runs/inferred_calibration.json", "w"), indent=2)
