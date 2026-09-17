#!/usr/bin/env python3
"""
ef_design_test.py -- test the proposed Build 37 EF changes on Build 36's OWN signal from the faithful Aug-1 replay,
before any code is written. EF's direction and settlement_probability are taken exactly as Build 36 computed them
(grid dump: every second; ef_candidates: the 496 watched candidates). Nothing about the signal is changed.

Tested:
  (3) calibration: does EF's settlement_probability mean what it says?  (bucket table, walk-forward Platt)
  (4) price gate: fire only when calibrated P(side) >= all-in cost at the REAL Polymarket ask (+ margin)
      -> fires/100, accuracy, PnL at fee 0 and 0.07, $50 hybrid.  Compared with Build 36 as-is (19 fires).
  (key) is EF right where the market is wrong? walk-forward AUC of EF alone, market alone, both.
Outcomes = Polymarket (Chainlink). Fills = real $10 ask-ladder VWAP at the 5 s grid point <= decision time.
"""
import sqlite3, pathlib, sys, numpy as np, pandas as pd, pyarrow.parquet as pq
R = pathlib.Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R / "ef_arch" / "polymarket" / "fiveday")); sys.path.insert(0, str(R / "ef_arch"))
from hybrid_stake import run_hybrid
from clean_grid_harness import auc, clustered_auc_ci
W0 = 1785542400
def cost(q, r): return q / (1.0 - r * (1.0 - q))
def logit(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))
def fit_logit(X, y, l2=1e-3, it=300):
    X = np.column_stack([np.ones(len(X)), X]); w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ w)); g = X.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]]
        H = (X * (p * (1 - p))[:, None]).T @ X / len(y) + l2 * np.eye(len(w)); w -= np.linalg.solve(H, g)
    return w
def pred(w, X): X = np.column_stack([np.ones(len(X)), X]); return 1 / (1 + np.exp(-X @ w))

L = pq.read_table(R / "ef_arch/polymarket/polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): (float(r.vwap_s10) if r.fill_ok_s10 else np.nan, float(r.best_ask), float(r.mid)) for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}

# ---- grid rows: one per (candle, side-call, 5 s offset)
g = pd.read_csv(R / "ef_replay/work/grid_dump_b36.csv"); g = g[g.ef_direction.isin(["UP", "DOWN"]) & (g.inputs_ready == 1)].copy()
g["ep"] = (g.candle_open_ms // 1000).astype(int); g["off"] = (np.floor(g.phase_s / 5) * 5).clip(5, 295).astype(int)
g = g.drop_duplicates(["ep", "off"]).copy(); g["hour"] = ((g.ep - W0) // 3600).astype(int)
g["q"] = [lad.get((e, s, o), (np.nan, np.nan, np.nan))[0] for e, s, o in zip(g.ep, g.ef_direction, g.off)]
g["mkt"] = [lad.get((e, s, o), (np.nan, np.nan, np.nan))[2] for e, s, o in zip(g.ep, g.ef_direction, g.off)]     # venue mid for EF's side
g["y"] = [float(outcome.get(e) == s) for e, s in zip(g.ep, g.ef_direction)]; g = g[np.isfinite(g.q) & np.isfinite(g.mkt)].copy()
g["p_ef"] = g.settlement_probability.clip(0.01, 0.99)
print(f"grid rows with an EF direction, inputs ready, real quote: {len(g):,}  candles {g.ep.nunique()}  EF side = venue favourite in {100*(g.mkt>0.5).mean():.1f}% of rows")
print("\n(3) CALIBRATION of Build 36 settlement_probability for EF's side (raw, all hours):")
print(f"{'bucket':<12}{'n':>7}{'mean p_ef':>11}{'realized':>10}{'venue mid':>11}")
for lo, hi in ((0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, .5), (.5, .6), (.6, .7)):
    m = (g.p_ef >= lo) & (g.p_ef < hi)
    if m.sum(): print(f"[{lo:.1f},{hi:.1f})   {int(m.sum()):>7}{g.p_ef[m].mean():>11.3f}{g.y[m].mean():>10.3f}{g.mkt[m].mean():>11.3f}")
# walk-forward calibration + the EF-vs-market question
g["p_cal"] = np.nan; g["p_mkt"] = np.nan; g["p_both"] = np.nan
for h in range(4, 24):
    tr = g[g.hour < h]; te = g.hour == h
    if te.sum() == 0: continue
    w1 = fit_logit(logit(tr.p_ef.to_numpy())[:, None], tr.y.to_numpy()); g.loc[te, "p_cal"] = pred(w1, logit(g.p_ef[te].to_numpy())[:, None])
    w2 = fit_logit(logit(tr.mkt.to_numpy())[:, None], tr.y.to_numpy()); g.loc[te, "p_mkt"] = pred(w2, logit(g.mkt[te].to_numpy())[:, None])
    X3 = np.column_stack([logit(tr.p_ef), logit(tr.mkt)]); w3 = fit_logit(X3, tr.y.to_numpy()); g.loc[te, "p_both"] = pred(w3, np.column_stack([logit(g.p_ef[te]), logit(g.mkt[te])]))
t = g[g.hour >= 4]
print(f"\n(key) WALK-FORWARD, hours 4-23, {len(t):,} rows, {t.ep.nunique()} candles  (AUC, candle-clustered 95% CI):")
for name, col in (("EF settlement_probability (calibrated)", "p_cal"), ("venue mid alone", "p_mkt"), ("venue mid + EF", "p_both")):
    a = auc(t[col].to_numpy(), t.y.to_numpy()); lo, hi = clustered_auc_ci(t[col].to_numpy(), t.y.to_numpy(), t.ep.to_numpy())
    print(f"  {name:<40} AUC {a:.3f}  [{lo:.3f}, {hi:.3f}]")
print(f"  rows where calibrated EF probability exceeds the all-in ask (fee 0): {int((t.p_cal > t.q).sum())} of {len(t):,}   at fee 0.07: {int((t.p_cal > cost(t.q, .07)).sum())}")
print(f"  rows where RAW Build 36 probability exceeds the ask (fee 0): {int((t.p_ef > t.q).sum())}")

# ---- (4) PRICE-GATED EF: one fire per candle, first grid row that passes
print("\n(4) PRICE-GATED EF on Build 36's own direction calls (hours 4-23, 240 candles), $10 real ask VWAP, one fire per candle:")
print(f"{'variant':<44}{'fee':>5}{'fires':>6}{'/100':>7}{'acc%':>6}{'avg q':>7}{'PnL/100':>9}{'fixed$5':>9}{'hyb$50':>8}")
def policy(rows_by_candle, r, margin, pcol):
    trades = []
    for ep, rows in rows_by_candle:
        for rw in rows.itertuples():
            p = getattr(rw, pcol)
            if np.isfinite(p) and p - cost(rw.q, r) >= margin:
                trades.append((rw.q, bool(rw.y))); break
    return trades
def report(name, trades, r, ncand):
    if not trades: print(f"{name:<44}{r:>5.2f}{0:>6}{0:>7.1f}{'-':>6}{'-':>7}{0:>+9.2f}{0:>+9.2f}{50:>8.2f}"); return
    q = np.array([x for x, _ in trades]); w = np.array([y for _, y in trades]); p = np.where(w, 1 / cost(q, r) - 1, -1.0)
    h, _, _, _ = run_hybrid([((lambda s, qq=qq: (float(qq), 1e9)), bool(ww)) for qq, ww in trades], r)
    print(f"{name:<44}{r:>5.2f}{len(trades):>6}{100*len(trades)/ncand:>7.1f}{100*w.mean():>6.1f}{q.mean():>7.3f}{100*p.sum()/ncand:>+9.2f}{5*p.sum():>+9.2f}{h['end']:>8.2f}")
byc = [(ep, rows.sort_values("off")) for ep, rows in t.groupby("ep")]; ncand = len(byc)
for r in (0.0, 0.07):
    for margin in (0.0, 0.02, 0.05):
        report(f"calibrated EF, gate margin {margin:.2f}", policy(byc, r, margin, "p_cal"), r, ncand)
    report("RAW Build 36 probability, gate margin 0.00", policy(byc, r, 0.0, "p_ef"), r, ncand)
    report("venue mid + EF combined, gate margin 0.00", policy(byc, r, 0.0, "p_both"), r, ncand)
# Build 36 as-is (its 19 actual fires) for reference, hours 4-23 subset
c = sqlite3.connect(R / "ef_replay/deliver/build36_replay_2026-08-01.sqlite3")
fires = c.execute("select candle_id, direction, ts_ms from ef_predictions").fetchall(); tr = []
for cid, side, ts in fires:
    ep = cid // 1000; o = max(5, min(295, int(((ts - cid) / 1000) // 5 * 5))); q = lad.get((ep, side, o), (np.nan,))[0]
    if (ep - W0) // 3600 >= 4 and np.isfinite(q): tr.append((q, outcome[ep] == side))
for r in (0.0, 0.07): report("BUILD 36 AS-IS (actual fires, hours 4-23)", tr, r, ncand)
# ---- the 496 candidates themselves with the gate
cd = pd.read_sql("select candle_id, direction, decision_ts_ms, settlement_probability, fired from ef_candidates", c)
cd["ep"] = cd.candle_id // 1000; cd["off"] = ((cd.decision_ts_ms - cd.candle_id) / 1000 // 5 * 5).clip(5, 295).astype(int); cd["hour"] = (cd.ep - W0) // 3600
cd["q"] = [lad.get((e, s, o), (np.nan,))[0] for e, s, o in zip(cd.ep, cd.direction, cd.off)]; cd["y"] = [outcome.get(e) == s for e, s in zip(cd.ep, cd.direction)]
cd = cd[np.isfinite(cd.q)]; print(f"\nBuild 36's 496 watched candidates: {len(cd)} priced; settlement_probability mean {cd.settlement_probability.mean():.3f}, realized {100*cd.y.mean():.1f}%, avg ask {cd.q.mean():.3f};"
      f" candidates whose own probability beats the ask at fee 0: {int((cd.settlement_probability > cd.q).sum())}, at fee 0.07: {int((cd.settlement_probability > cost(cd.q, .07)).sum())}")
print("\nLABEL: Build 36 signal unchanged; only calibration and a price gate added on top, walk-forward, real Aug-1 Polymarket asks, Chainlink outcomes.")
