#!/usr/bin/env python3
"""Reprice every EF fire of a faithful Build 36 replay day at the REAL Polymarket ladders of that day,
settle on the market's own outcome, and run fixed-stake and the user's hybrid staking. DATE from env."""
import sys, pathlib, sqlite3, json
_sys = sys; _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import daycfg as CFG
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "ef_arch" / "polymarket" / "fiveday"))
import numpy as np, pandas as pd, pyarrow.parquet as pq
from hybrid_stake import run_hybrid, run_fixed
def cost(q, r): return q / (1.0 - r * (1.0 - q))
L = pq.read_table(CFG.LADDERS).to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): r for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}
db = CFG.DAYROOT / f"build36_replay_{CFG.DATE}.sqlite3"
c = sqlite3.connect(db); cols = [x[1] for x in c.execute("pragma table_info(ef_predictions)")]
fires = c.execute("select candle_id, direction, ts_ms from ef_predictions order by ts_ms").fetchall()
rows = []
for cid, side, ts in fires:
    ep = cid // 1000; o = max(5, min(295, int(((ts - cid) / 1000) // 5 * 5))); r = lad.get((ep, side, o))
    rec = dict(window_epoch=ep, side=side, offset_s=o, ts_ms=ts, outcome=outcome.get(ep), win=(outcome.get(ep) == side))
    for k in ("s10", "s100", "s1000"):
        rec[f"vwap_{k}"] = float(getattr(r, f"vwap_{k}")) if r is not None and getattr(r, f"fill_ok_{k}") else float("nan")
        rec[f"ok_{k}"] = bool(r is not None and getattr(r, f"fill_ok_{k}"))
    rec["best_ask"] = float(r.best_ask) if r is not None else float("nan")
    rows.append(rec)
F = pd.DataFrame(rows); F.to_csv(CFG.DAYROOT / f"ef_fires_repriced_{CFG.DATE}.csv", index=False)
n = len(F); Fq = F[F.ok_s10]
def fill(rw):
    def f(s):
        k = "s10" if s <= 10 else ("s100" if s <= 100 else "s1000"); return (rw[f"vwap_{k}"], 1e9)
    return f
trades = [(fill(rw), bool(rw.win)) for _, rw in F.iterrows()]
out = {"date": CFG.DATE, "fires": n, "priced": int(len(Fq)), "fires_per_100_candles": 100 * n / 288, "accuracy_pct": 100 * Fq.win.mean() if len(Fq) else None,
       "avg_entry": float(Fq.vwap_s10.mean()) if len(Fq) else None}
for r in (0.0, 0.07):
    p = np.where(Fq.win, 1 / cost(Fq.vwap_s10, r) - 1, -1.0)
    h, _, _, _ = run_hybrid(trades, r); fx = run_fixed(trades, r, 5.0)
    out[f"fee{r}"] = dict(pnl_per_1usd_stake_total=float(p.sum()), pnl_per_100_candles=float(100 * p.sum() / 288), fixed5_pnl=fx["pnl"],
                         hybrid50_end=h["end"], hybrid50_pnl=h["pnl"], hybrid_maxdd=h["maxdd"], hybrid_low=h["lowest_capital"])
json.dump(out, open(CFG.DAYROOT / f"ef_repriced_summary_{CFG.DATE}.json", "w"), indent=1)
print(json.dumps(out, indent=1)); print(F.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
