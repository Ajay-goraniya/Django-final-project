#!/usr/bin/env python3
"""
hybrid_staking_sim.py -- apply the user's HYBRID STAKING rule to the real-book
trade sequences of 2026-08-01 (Polymarket BTC 5m, real ladders, Chainlink
outcomes) and report dollar PnL from a $50 starting bankroll.

Rule (as stated by the user):
    stake = 10% of available capital
    the 10% is RE-COMPUTED only after a 3-win streak or a 2-loss streak
    (streak counters reset on the opposite outcome and on every recompute)
Assumptions made explicit:
    * stake never exceeds available capital; sim stops if capital < $0.50
    * fill VWAP: stake <= $10 -> vwap_s10, <= $100 -> vwap_s100, else vwap_s1000
      (the ladder was walked for those three stakes; using the next bucket up
       is conservative for smaller stakes)
    * trades are taken in time order, one per 5-minute window at most
    * fee r = 0.00 (venue-reported) and 0.07 (official) both shown
Nothing synthetic: prices, ladders and outcomes are the recorded ones.
"""
import pathlib, sys, sqlite3
import numpy as np, pandas as pd, pyarrow.parquet as pq

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "build37a"))
from real_book_backtest import cost, admits, W0, LAD, B36DB
from clean_grid_harness import decision_points, walk_forward
from ef_arc_capture import ARC_POLICIES

START = 50.0; FRAC = 0.10; WIN_STREAK = 3; LOSS_STREAK = 2

def vwap_for(row, stake):
    for k, cap in (("s10", 10.0), ("s100", 100.0), ("s1000", 1e9)):
        if stake <= cap:
            ok = bool(getattr(row, f"fill_ok_{k}")); return (float(getattr(row, f"vwap_{k}")) if ok else np.nan)
    return np.nan

def run_hybrid(trades, r, start=START, frac=FRAC):
    """trades: list of (row, side_win_bool) in time order. Returns dict + equity path."""
    C = start; stake = frac * C; wins = losses = 0; eq = [C]; n = 0; nw = 0; skipped = 0; peak = C; maxdd = 0.0
    for row, win in trades:
        if C < 0.5: break
        s = min(stake, C); q = vwap_for(row, s)
        if not np.isfinite(q): skipped += 1; continue
        pnl = s * ((1.0 / cost(q, r) - 1.0) if win else -1.0)
        C += pnl; n += 1; nw += int(win); eq.append(C); peak = max(peak, C); maxdd = max(maxdd, peak - C)
        if win: wins += 1; losses = 0
        else: losses += 1; wins = 0
        if wins >= WIN_STREAK or losses >= LOSS_STREAK:
            stake = frac * C; wins = losses = 0
    return dict(final=C, pnl=C - start, roi=100 * (C - start) / start, trades=n, wins=nw, acc=100 * nw / max(n, 1),
                maxdd=maxdd, min_cap=min(eq), max_cap=max(eq), skipped=skipped), eq

def run_flat(trades, r, stake=START * FRAC, start=START):
    C = start; n = 0; nw = 0
    for row, win in trades:
        q = vwap_for(row, stake)
        if not np.isfinite(q): continue
        C += stake * ((1.0 / cost(q, r) - 1.0) if win else -1.0); n += 1; nw += int(win)
    return C - start

def run_full_fraction(trades, r, start=START, frac=FRAC):
    C = start
    for row, win in trades:
        s = frac * C; q = vwap_for(row, s)
        if not np.isfinite(q): continue
        C += s * ((1.0 / cost(q, r) - 1.0) if win else -1.0)
    return C - start

# ------------------------------------------------------------------ data
L = pq.read_table(LAD).to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): r for r in L.itertuples()}
outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}

def favourite_trades(offset):
    T = L[(L.offset_s == offset) & (L.best_ask > 0.5)].sort_values(["window_epoch", "best_ask"], ascending=[True, False])
    T = T.drop_duplicates("window_epoch")                      # one per window: the higher-priced side
    return [(r, r.outcome == r.side) for r in T.itertuples()]

def reversal_trades():
    g = np.load(HERE.parent / "grid.npz"); g = {k: g[k] for k in ("mid", "micro", "b15", "b610", "b1120", "spr", "flow", "tcnt", "spot")}
    d = decision_points(g); P = walk_forward(d["X"], d["win_contr"].astype(float), d["hour"])
    ci, off, left, contr_up, hour = d["ci"], d["off"].astype(int), d["left"], d["contr_up"], d["hour"]
    rows = []
    for k in np.where(hour >= 4)[0]:
        ep = W0 + 300 * int(ci[k]); side = "UP" if contr_up[k] else "DOWN"; o = int(off[k]); r = lad.get((ep, side, o))
        if r is None: continue
        rows.append((int(ci[k]), o, float(left[k]), float(P[k]), r, outcome[ep] == side))
    rows.sort(key=lambda x: (x[0], x[1]))
    out = {}
    for pid, cfg in ARC_POLICIES.items():
        for r_fee in (0.0, 0.07):
            streak = 0; dd = 0.0; cum = 0.0; peak = 0.0; trades = []; last_c = None; fired = False
            for c, o, lft, p, row, win in rows:
                if c != last_c: last_c = c; fired = False; streak = 0
                if fired: continue
                q = float(row.vwap_s10) if row.fill_ok_s10 else None
                ok, p_safe, p_be, edge, roi = admits(cfg, p, q, lft, r_fee, streak >= cfg["persist"] - 1, dd)
                raw = (edge is not None) and edge >= cfg["margin"] and roi >= cfg["roi_min"]; streak = streak + 1 if raw else 0
                if ok:
                    fired = True; pnl = (1 / cost(q, r_fee) - 1) if win else -1.0
                    cum += pnl; peak = max(peak, cum); dd = peak - cum; trades.append((row, win))
            out[(cfg["name"], r_fee)] = trades
    return out

def b36_trades():
    c36 = sqlite3.connect(B36DB); out = []
    for cid, side, ts in sorted(c36.execute("select candle_id, direction, ts_ms from ef_predictions").fetchall(), key=lambda x: x[2]):
        ep = cid // 1000; o = max(5, min(295, int(((ts - cid) / 1000) // 5 * 5))); r = lad.get((ep, side, o))
        if r is not None: out.append((r, outcome.get(ep) == side))
    return out

# ------------------------------------------------------------------ report
print("=" * 96)
print(f"HYBRID STAKING SIMULATION -- 2026-08-01 -- start ${START:.0f}, stake {FRAC:.0%} of capital, "
      f"recomputed after {WIN_STREAK}-win or {LOSS_STREAK}-loss streak")
print("=" * 96)
hdr = f"{'strategy':<30}{'fee':>5}{'trades':>7}{'acc%':>6}{'HYBRID $PnL':>12}{'final $':>9}{'maxDD $':>9}{'min cap':>9}{'max cap':>9}{'flat $5':>9}{'10%/trade':>10}"
print(hdr)
rev = reversal_trades()
def line(name, trades, r):
    h, eq = run_hybrid(trades, r)
    if h["trades"] == 0:
        print(f"{name:<30}{r:>5.2f}{0:>7}{'-':>6}{0:>+12.2f}{START:>9.2f}{0:>9.2f}{START:>9.2f}{START:>9.2f}{0:>+9.2f}{0:>+10.2f}"); return h, eq
    print(f"{name:<30}{r:>5.2f}{h['trades']:>7}{h['acc']:>6.1f}{h['pnl']:>+12.2f}{h['final']:>9.2f}{h['maxdd']:>9.2f}{h['min_cap']:>9.2f}{h['max_cap']:>9.2f}"
          f"{run_flat(trades, r):>+9.2f}{run_full_fraction(trades, r):>+10.2f}")
    return h, eq

paths = {}
for r in (0.0, 0.07):
    print(f"--- favourite side, fixed offset, no BTC signal (fee {r:.2f}) ---")
    for X in (30, 60, 90, 120, 180, 240):
        h, eq = line(f"FAV fixed offset {X}s", favourite_trades(X), r)
        if r == 0.0: paths[f"FAV {X}s"] = eq
    print(f"--- frozen ARC reversal policies (fee {r:.2f}) ---")
    for pid, cfg in ARC_POLICIES.items():
        line(f"REV {cfg['name']}", rev[(cfg["name"], r)], r)
    print(f"--- Build 36 own fires repriced (fee {r:.2f}) ---")
    line("B36 fires", b36_trades(), r)
    print()

print("EQUITY PATH, favourite 120s, fee 0, hybrid staking (capital after every 24th trade):")
eq = paths["FAV 120s"]
print("  " + "  ".join(f"t{i}:{eq[i]:.2f}" for i in range(0, len(eq), 24)) + f"  end:{eq[-1]:.2f}")
print("\nLABEL: one day, real Polymarket ladders, Chainlink outcomes, no latency, no slippage after the decision instant. Not Predict.fun.")
