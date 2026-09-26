#!/usr/bin/env python3
"""
real_book_backtest.py -- POLYMARKET HISTORICAL BOOK BACKTEST, 2026-08-01.

Joins:  the clean causal BTC grid (ef_arch/clean_grid_harness.py: 5 s decision
        points, walk-forward P trained only on earlier hours)
   x    real Polymarket BTC 5m Up/Down ask ladders at the same decision times
        (polymarket_btc5m_2026-08-01_books.parquet, latest `book` <= T)
   x    the market's own Chainlink-resolved outcome (Gamma outcomePrices)

and runs the SEVEN FROZEN policies (constants imported unchanged from
build37a/ef_arc_capture.py) with POLYMARKET economics:

    taker fee per share  f(q) = r * q * (1 - q)      (official formula)
    all-in cost / share  c(q) = q + f(q) = q * (1 + r*(1 - q))
    shares for stake S   N = S / c(q)
    win  -> N * 1  =>  return per $1 = 1/c(q) - 1
    loss -> 0      =>  return per $1 = -1
    break-even P         P_BE = c(q)

r is run at 0.00 (what the venue's trade stream reported on this day) and
0.07 (official crypto rate) as a stress. Fill price = VWAP walking the real
ask ladder for the stated stake; rows where the stake cannot be filled are
not traded. Nothing synthetic anywhere in this file.
"""
import json, pathlib, sys
import numpy as np, pandas as pd, pyarrow.parquet as pq

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "build37a"))
from clean_grid_harness import build_grid, decision_points, walk_forward, auc, clustered_auc_ci
from ef_arc_capture import ARC_POLICIES

W0 = 1785542400
LAD = HERE / "polymarket_btc5m_2026-08-01_books.parquet"
KL = HERE.parent.parent / "btc_replay_2026-08-01_24h" / "normalized" / "spot_klines_5m.parquet"
B36DB = HERE.parent.parent / "ef_replay" / "deliver" / "build36_replay_2026-08-01.sqlite3"

def cost(q, r): return q * (1.0 + r * (1.0 - q))
def ret(win, q, r): return (1.0 / cost(q, r) - 1.0) if win else -1.0

def admits(cfg, p_side, q, seconds_left, r, streak_ok, dd_units):
    if q is None or not np.isfinite(q) or not (0.01 <= q <= 0.99): return False, None, None, None, None
    buf = cfg["buffer"] * (np.sqrt(300.0 / max(seconds_left, 1.0)) if cfg["time_buffer"] else 1.0)
    p_safe = min(max(p_side - buf, 0.01), 0.99); p_be = cost(q, r)
    edge = p_safe - p_be; roi = p_safe / p_be - 1.0
    ok = edge >= cfg["margin"] and roi >= cfg["roi_min"]
    if cfg["p_floor"] is not None and p_safe < cfg["p_floor"]: ok = False
    if cfg["runway"] is not None and seconds_left < cfg["runway"]: ok = False
    if cfg["persist"] > 1 and not streak_ok: ok = False
    if cfg["governor"] is not None and dd_units >= cfg["governor"]: ok = False
    return ok, p_safe, p_be, edge, roi

def session(c):  # UTC hour of candle -> session
    h = (c * 300) // 3600
    return "ASIA 00-08" if h < 8 else ("LONDON 08-16" if h < 16 else "US 16-24")

def main(stake=10.0):
    g = np.load(HERE.parent / "grid.npz"); g = {k: g[k] for k in ("mid", "micro", "b15", "b610", "b1120", "spr", "flow", "tcnt", "spot")}
    d = decision_points(g); P = walk_forward(d["X"], d["win_contr"].astype(float), d["hour"])
    ci, off, left, contr_up, hour = d["ci"], d["off"].astype(int), d["left"], d["contr_up"], d["hour"]
    L = pq.read_table(LAD).to_pandas(); L = L[L.has_book]
    key = f"s{int(stake)}"
    lad = {(int(r.window_epoch), r.side, int(r.offset_s)): r for r in L.itertuples()}
    kl = pq.read_table(KL).to_pandas(); bin_up = {int(r.open_time // 1000 // 1000): float(r.close) > float(r.open) for r in kl.itertuples()}
    outcome = {int(r.window_epoch): r.outcome for r in L.drop_duplicates("window_epoch").itertuples()}

    # ---- outcome source check: Chainlink (Polymarket) vs Binance spot close>open
    dis = [ep for ep in outcome if ep in bin_up and (outcome[ep] == "UP") != bin_up[ep]]
    print("=" * 76); print("POLYMARKET HISTORICAL BOOK BACKTEST -- 2026-08-01 -- REAL LADDERS, REAL OUTCOMES"); print("=" * 76)
    print(f"windows with books: {len(outcome)}/288   Chainlink-vs-Binance outcome disagreements: {len(dis)} ({100*len(dis)/max(len(outcome),1):.1f}%)")
    m = hour >= 4
    print(f"decision rows {int(m.sum()):,}  candles {len(np.unique(ci[m]))}  walk-forward AUC(P vs Binance label) {auc(P[m], d['win_contr'][m].astype(float)):.3f}")

    # ---- per-row join
    rows = []
    for k in np.where(m)[0]:
        ep = W0 + 300 * int(ci[k]); side = "UP" if contr_up[k] else "DOWN"; o = int(off[k])
        r = lad.get((ep, side, o))
        if r is None: continue
        q = getattr(r, f"vwap_{key}"); ok = bool(getattr(r, f"fill_ok_{key}"))
        rows.append(dict(c=int(ci[k]), ep=ep, side=side, off=o, left=float(left[k]), p_rev=float(P[k]),
                         q=float(q) if ok else np.nan, best_ask=float(r.best_ask), spread=float(r.spread),
                         age=int(r.book_age_ms), win_pm=(outcome[ep] == side), win_bin=(bin_up[ep] == (side == "UP"))))
    R = pd.DataFrame(rows).sort_values(["c", "off"]).reset_index(drop=True)
    cov = R.q.notna().mean()
    print(f"joined rows {len(R):,}   real-quote coverage (fill ok at ${int(stake)}) {100*cov:.1f}%   "
          f"best_ask p50 {R.best_ask.median():.3f}  spread p50 {R.spread.median():.3f}  book age p50 {R.age.median():.0f} ms")
    print(f"reversal-side ask price at decision time: p10 {R.best_ask.quantile(.1):.2f}  p50 {R.best_ask.median():.2f}  p90 {R.best_ask.quantile(.9):.2f}")

    # ---- policies
    def run_policy(cfg, r_fee, label_win="win_pm"):
        st = dict(streak=0, cum=0.0, peak=0.0, dd=0.0); trades = []
        for c, grp in R.groupby("c", sort=True):
            fired = False; st["streak"] = 0
            for row in grp.itertuples():
                if fired: break
                ok, p_safe, p_be, edge, roi = admits(cfg, row.p_rev, row.q, row.left, r_fee, st["streak"] >= cfg["persist"] - 1, st["dd"])
                raw = (edge is not None) and edge >= cfg["margin"] and roi >= cfg["roi_min"]
                st["streak"] = st["streak"] + 1 if raw else 0
                if ok:
                    fired = True; win = bool(getattr(row, label_win)); pnl = ret(win, row.q, r_fee)
                    st["cum"] += pnl; st["peak"] = max(st["peak"], st["cum"]); st["dd"] = st["peak"] - st["cum"]
                    trades.append(dict(c=c, off=row.off, side=row.side, q=row.q, p=row.p_rev, p_safe=p_safe, win=win, pnl=pnl, sess=session(c)))
        return pd.DataFrame(trades)

    ncand = R.c.nunique()
    print(f"\n{'policy':<18}{'fee':>5}{'fires/100':>10}{'acc%':>7}{'PnL/100':>9}{'total':>8}{'maxDD':>7}{'worstHr':>8}{'worst3h':>8}{'ASIA':>7}{'LONDON':>8}{'US':>7}{'avg q':>7}")
    summary = []
    for r_fee in (0.00, 0.07):
        for pid, cfg in ARC_POLICIES.items():
            T = run_policy(cfg, r_fee)
            if T.empty:
                print(f"{cfg['name']:<18}{r_fee:>5.2f}{0:>10.1f}{'-':>7}{0:>9.2f}{0:>8.2f}{'-':>7}{'-':>8}{'-':>8}"); continue
            hr = T.groupby(T.c * 300 // 3600).pnl.sum(); h3 = T.groupby(T.c * 300 // 10800).pnl.sum()
            eq = T.pnl.cumsum(); dd = float((eq.cummax() - eq).max())
            ses = T.groupby("sess").pnl.sum()
            rec = dict(policy=cfg["name"], fee=r_fee, fires_per_100=100 * len(T) / ncand, acc=100 * T.win.mean(),
                       pnl_per_100=100 * T.pnl.sum() / ncand, total=T.pnl.sum(), maxdd=dd, worst_hr=hr.min(), worst_3h=h3.min(),
                       asia=ses.get("ASIA 00-08", 0.0), london=ses.get("LONDON 08-16", 0.0), us=ses.get("US 16-24", 0.0), avg_q=T.q.mean(), n=len(T))
            summary.append(rec)
            print(f"{rec['policy']:<18}{r_fee:>5.2f}{rec['fires_per_100']:>10.1f}{rec['acc']:>7.1f}{rec['pnl_per_100']:>+9.2f}{rec['total']:>+8.2f}"
                  f"{rec['maxdd']:>7.2f}{rec['worst_hr']:>+8.2f}{rec['worst_3h']:>+8.2f}{rec['asia']:>+7.2f}{rec['london']:>+8.2f}{rec['us']:>+7.2f}{rec['avg_q']:>7.3f}")
    pd.DataFrame(summary).to_csv(HERE / f"real_book_policy_summary_s{int(stake)}.csv", index=False)

    # ---- Build 36's ACTUAL fires repriced at real books
    try:
        import sqlite3
        c36 = sqlite3.connect(B36DB)
        fires = c36.execute("select candle_id, direction, ts_ms from ef_predictions").fetchall()
        out = []
        for cid, side, ts in fires:
            ep = cid // 1000; o = max(5, min(295, int(((ts - cid) / 1000) // 5 * 5)))
            r = lad.get((ep, side, o))
            if r is None or not getattr(r, f"fill_ok_{key}"): out.append(dict(ep=ep, side=side, off=o, q=np.nan, win=None, pnl0=np.nan, pnl7=np.nan)); continue
            q = float(getattr(r, f"vwap_{key}")); win = outcome.get(ep) == side
            out.append(dict(ep=ep, side=side, off=o, q=q, win=win, pnl0=ret(win, q, 0.0), pnl7=ret(win, q, 0.07)))
        F = pd.DataFrame(out); Fq = F[F.q.notna()]
        print(f"\nBUILD 36's OWN {len(F)} FIRES repriced at real Polymarket ladders (${int(stake)} stake):")
        print(f"  priced {len(Fq)}/{len(F)}   accuracy vs Chainlink {100*Fq.win.mean():.1f}%   avg entry {Fq.q.mean():.3f}   "
              f"PnL fee0 {Fq.pnl0.sum():+.2f} ({100*Fq.pnl0.sum()/288:+.2f}/100)   PnL fee7% {Fq.pnl7.sum():+.2f}")
        print(F.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    except Exception as e:
        print("B36 repricing skipped:", e)
    print("\nLABEL: POLYMARKET HISTORICAL BOOK BACKTEST. Real ladders, real Chainlink outcomes, one day, stake $%d. Not Predict.fun PnL." % int(stake))

if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 10.0)
