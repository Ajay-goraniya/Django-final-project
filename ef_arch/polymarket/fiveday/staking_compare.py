#!/usr/bin/env python3
"""
staking_compare.py -- same trades, different staking rules. If a staking rule could rescue the favourite strategy,
it would show here. Trades: favourite-by-midpoint at 120 s, one per market, $5-bucket fills (tape proxy on the five
validation days; REAL ladders on Aug 1 with the corrected higher-mid rule), fee 0.07 (BUY semantics) and fee 0.
Rules (all start at $50, stake capped at capital, path stops below $1):
  hybrid 3W/2L      the user's rule (10% of capital, recomputed after 3 wins or 2 losses)
  hybrid 3W/1L      same, but any loss triggers a recompute (shrinks faster, grows the same)
  10% every trade   plain fractional staking, recomputed on every trade
  5% every trade
  2% every trade
  fixed $5          flat
  fixed $2          flat
"""
import pathlib, sys, numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from hybrid_stake import run_hybrid
DATES = ["2026-08-22", "2026-08-24", "2026-08-27", "2026-08-31", "2026-09-05"]
def fill_fn(vwaps):  # vwaps: dict bucket->(vwap, ok)
    def f(s):
        for b in (2, 5, 10, 100):
            if s <= b + 1e-9: v, ok = vwaps[b]; return ((float(v) if ok else float("nan")), 1e9)
        v, ok = vwaps[100]; return ((float(v) if ok else float("nan")), 1e9)
    return f
def tape_trades(d):
    P = pd.read_parquet(HERE / "data" / f"tape_proxy_{d}.parquet"); P = P[(P.offset_s == 120) & P.fav.notna()].sort_values("window_epoch")
    return [(fill_fn({b: (r[f"vwap_d0_s{b}"], r[f"ok_d0_s{b}"]) for b in (2, 5, 10, 100)}), bool(r.win_fav)) for _, r in P.iterrows()]
def aug1_trades():
    L = pq.read_table(HERE.parent / "polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book & (L.offset_s == 120)]
    out = []
    for ep, g in L.groupby("window_epoch"):
        g = g.set_index("side")
        if not {"UP", "DOWN"} <= set(g.index) or g.loc["UP", "mid"] == g.loc["DOWN", "mid"] or not np.isfinite(g.loc["UP", "mid"]) or not np.isfinite(g.loc["DOWN", "mid"]): continue
        fav = "UP" if g.loc["UP", "mid"] > g.loc["DOWN", "mid"] else "DOWN"; r = g.loc[fav]
        out.append((fill_fn({2: (r.vwap_s10, r.fill_ok_s10), 5: (r.vwap_s10, r.fill_ok_s10), 10: (r.vwap_s10, r.fill_ok_s10), 100: (r.vwap_s100, r.fill_ok_s100)}), r.outcome == fav))
    return out
def frac_every(trades, r, frac):  # recompute every trade
    res, _, eq, _ = run_hybrid(trades, r, frac=frac, win_trigger=1, loss_trigger=1); return res
RULES = {
    "hybrid 3W/2L (yours)": lambda t, r: run_hybrid(t, r)[0],
    "hybrid 3W/1L":         lambda t, r: run_hybrid(t, r, win_trigger=3, loss_trigger=1)[0],
    "10% every trade":      lambda t, r: frac_every(t, r, 0.10),
    "5% every trade":       lambda t, r: frac_every(t, r, 0.05),
    "2% every trade":       lambda t, r: frac_every(t, r, 0.02),
    "fixed $5":             lambda t, r: run_hybrid(t, r, frac=0.10, win_trigger=10**9, loss_trigger=10**9)[0],
    "fixed $2":             lambda t, r: run_hybrid(t, r, frac=0.04, win_trigger=10**9, loss_trigger=10**9)[0],
}
days = {d: tape_trades(d) for d in DATES}; days["2026-08-01 (real ladders, corrected rule)"] = aug1_trades()
for r_fee in (0.07, 0.0):
    print(f"\nEND CAPITAL from $50, favourite @120s, fee {r_fee:.2f}   (bankrupt = path stopped below $1)")
    hdr = f"{'rule':<24}" + "".join(f"{d[5:10]:>10}" for d in DATES) + f"{'5-day cont.':>13}{'Aug01':>9}"; print(hdr)
    for name, fn in RULES.items():
        ends = []
        for d in DATES: ends.append(fn(days[d], r_fee)["end"])
        # continuous: chain state
        st = None; C = 50.0
        for d in DATES:
            if name.startswith("hybrid"):
                wt, lt = (3, 2) if "2L" in name else (3, 1); res, st, _, _ = run_hybrid(days[d], r_fee, win_trigger=wt, loss_trigger=lt, state=st)
            elif name.endswith("every trade"):
                frac = float(name.split("%")[0]) / 100; res, st, _, _ = run_hybrid(days[d], r_fee, frac=frac, win_trigger=1, loss_trigger=1, state=st)
            else:
                stake = 5.0 if "$5" in name else 2.0; res, st, _, _ = run_hybrid(days[d], r_fee, frac=stake / 50, win_trigger=10**9, loss_trigger=10**9, state=(st or dict(C=50.0, stake=stake, wins=0, losses=0)))
            C = res["end"]
        a1 = fn(days["2026-08-01 (real ladders, corrected rule)"], r_fee)["end"]
        print(f"{name:<24}" + "".join(f"{e:>10.2f}" for e in ends) + f"{C:>13.2f}{a1:>9.2f}")
n = {d: len(days[d]) for d in days}; print("\ntrades per day:", n)
# expectation per $1 staked, the number no staking rule can change
print("\nEXPECTED RETURN PER $1 STAKED (the thing staking cannot change):")
for d, t in days.items():
    q = np.array([f(5.0)[0] for f, _ in t]); w = np.array([x for _, x in t]); m = np.isfinite(q)
    e7 = np.where(w[m], (1 - .07 * (1 - q[m])) / q[m] - 1, -1.0).mean(); e0 = np.where(w[m], 1 / q[m] - 1, -1.0).mean()
    print(f"  {d:<42} n {m.sum():>3}  win {100*w[m].mean():5.1f}%  avg fill {q[m].mean():.3f}   E[ret] fee7 {100*e7:+6.2f}%   fee0 {100*e0:+6.2f}%")
