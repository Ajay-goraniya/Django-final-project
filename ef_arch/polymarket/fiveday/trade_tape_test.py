#!/usr/bin/env python3
"""
trade_tape_test.py -- FULL-DAY test on the five requested dates using the public Polymarket trade tape
(data-api /trades: every executed fill, 1-second timestamps, taker side, token, price, size).

THIS IS NOT A LADDER WALK. It is labelled TRADE-TAPE PROXY everywhere. What it does:
  favourite at T   = token whose LAST executed price before T (same window) is higher; tie / one side
                     untraded before T -> abstain. (Selection signal only; never used as the fill.)
  fill             = VWAP of the ACTUAL taker-BUY fills on that token with ts >= T (+delay), accumulated
                     until their notional covers the stake, within 15 s. Real prices real people paid at
                     that moment. If the tape does not cover the stake within 15 s -> unexecutable, no trade.
  outcome          = the market's own Gamma outcomePrices (Chainlink TWAP rule on these dates).
Fees: r=0.07 official (BUY semantics: return = (1 - r(1-q))/q - 1 on a win) and r=0 stress; 0.07 is PRIMARY
here because the tape does not carry per-trade fee rates on these dates.
"""
import json, pathlib, sys, math, datetime
import numpy as np, pandas as pd
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from hybrid_stake import run_hybrid, run_fixed
DATES = ["2026-08-22", "2026-08-24", "2026-08-27", "2026-08-31", "2026-09-05"]
OFFSETS = (30, 60, 90, 120, 180, 240); STAKES = (2.0, 5.0, 10.0, 100.0); DELAYS = (0, 1, 5); HORIZON = 15
def cost(q, r): return q / (1.0 - r * (1.0 - q))   # BUY-fee semantics: win return = (1 - r(1-q))/q - 1
def sess(ep): h = (ep % 86400) // 3600; return "ASIA" if h < 8 else ("LONDON" if h < 16 else "US")

def build_day(date):
    M = json.load(open(HERE / "data" / "markets" / f"btc5m_markets_{date}.json"))
    outcome = {}
    for r in M["rows"]:
        m = r["market"]; op = json.loads(m["outcomePrices"]); outs = json.loads(m["outcomes"]); outcome[r["epoch"]] = outs[int(np.argmax([float(x) for x in op]))].upper()
    T = pd.read_parquet(HERE / "data" / "trades" / f"trades_{date}.parquet"); T["tok"] = T.outcome.str.upper()
    T = T[(T.ts >= T.window_epoch) & (T.ts < T.window_epoch + 300)].sort_values(["window_epoch", "ts"])
    rows = []
    for ep, g in T.groupby("window_epoch"):
        up = g[g.tok == "UP"]; dn = g[g.tok == "DOWN"]
        for X in OFFSETS:
            t0 = ep + X
            lu = up[up.ts < t0]; ld = dn[dn.ts < t0]
            rec = dict(date=date, window_epoch=ep, offset_s=X, decision_ts=t0, outcome=outcome[ep], n_trades=len(g), sess=sess(ep))
            if lu.empty or ld.empty: rec.update(fav=None, reason="one side untraded before T"); rows.append(rec); continue
            pu, pd_ = float(lu.price.iloc[-1]), float(ld.price.iloc[-1])
            if pu == pd_: rec.update(fav=None, reason="tie"); rows.append(rec); continue
            fav = "UP" if pu > pd_ else "DOWN"; rec.update(fav=fav, fav_last=max(pu, pd_), other_last=min(pu, pd_), win_fav=(outcome[ep] == fav))
            tape = (up if fav == "UP" else dn); tape = tape[(tape.side == "BUY")]
            for dly in DELAYS:
                w = tape[(tape.ts >= t0 + dly) & (tape.ts <= t0 + dly + HORIZON)]
                notional = (w.price * w.size).to_numpy(); cum = np.cumsum(notional); pr = w.price.to_numpy()
                rec[f"tape_fills_d{dly}"] = len(w); rec[f"tape_notional_d{dly}"] = float(cum[-1]) if len(cum) else 0.0
                for st in STAKES:
                    k = f"d{dly}_s{int(st)}"
                    if len(cum) == 0 or cum[-1] < st: rec[f"vwap_{k}"] = float("nan"); rec[f"ok_{k}"] = False; continue
                    j = int(np.searchsorted(cum, st)); take = notional[:j + 1].copy(); take[-1] -= (cum[j] - st)
                    rec[f"vwap_{k}"] = float((pr[:j + 1] * take).sum() / take.sum()); rec[f"ok_{k}"] = True; rec[f"first_fill_lag_{k}"] = int(w.ts.iloc[0] - t0)
            rows.append(rec)
    return pd.DataFrame(rows), len(outcome), T.window_epoch.nunique()


def stake_bucket(s):
    """precomputed fills exist for $2/$5/$10/$100: use the smallest bucket >= stake (conservative); above $100 use $100 (optimistic, flagged)"""
    for b in (2, 5, 10, 100):
        if s <= b + 1e-9: return b
    return 100
def fill_at(r, dly, s):
    b = stake_bucket(s); k = f"d{dly}_s{b}"
    return ((float(getattr(r, f"vwap_{k}")) if getattr(r, f"ok_{k}", False) else float("nan")), 1e9)

def trades_for(Tbl, dly, st):
    return [((lambda s, r=r, dly=dly: fill_at(r, dly, s)), bool(r.win_fav)) for r in Tbl.itertuples()]

def pnl100(Tbl, dly, st, r):
    v = np.array([getattr(x, f"vwap_d{dly}_s{int(st)}", np.nan) for x in Tbl.itertuples()], dtype=float); ok = np.array([bool(getattr(x, f"ok_d{dly}_s{int(st)}", False)) for x in Tbl.itertuples()]); w = Tbl.win_fav.to_numpy(dtype=bool)
    m = ok & np.isfinite(v); n = int(m.sum())
    if n == 0: return float("nan"), 0, float("nan"), float("nan"), np.array([]), m
    p = np.where(w[m], (1 - r * (1 - v[m])) / v[m] - 1, -1.0); return 100 * p.sum() / n, n, 100 * w[m].mean(), float(v[m].mean()), p, m

def main():
    out = {}; allF = []
    for d in DATES:
        f = HERE / "data" / "trades" / f"trades_{d}.parquet"
        if not f.exists(): print(d, "TRADES NOT YET AVAILABLE"); continue
        D, nmap, ntr = build_day(d); D.to_parquet(HERE / "data" / f"tape_proxy_{d}.parquet", index=False); out[d] = (D, nmap, ntr); allF.append(D[D.fav.notna()])
        print(f"{d}: markets mapped {nmap}  with tape {ntr}  decision rows {len(D)}  abstain {int(D.fav.isna().sum())}")
    F = pd.concat(allF)
    print("\nFAVOURITE CALIBRATION, TRADE-TAPE PROXY, $5 fill VWAP bucket, all 5 days, all offsets pooled:")
    print(f"{'bucket':<12}{'n':>7}{'mean fill':>11}{'realized':>10}{'diff':>8}{'EV/$ fee7':>11}{'EV/$ fee0':>11}")
    for lo, hi in ((.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.0)):
        m = (F.vwap_d0_s5 >= lo) & (F.vwap_d0_s5 < hi) & F.ok_d0_s5
        if m.sum(): q = F.vwap_d0_s5[m].mean(); w = F.win_fav[m].mean(); print(f"[{lo:.1f},{hi:.1f})   {int(m.sum()):>7}{q:>11.3f}{w:>10.3f}{w-q:>+8.3f}{w*(1-.07*(1-q))/q-1:>+11.3f}{w/q-1:>+11.3f}")
    print(f"\n{'date':<12}{'off':>4}{'mkts':>5}{'trades':>7}{'win%':>6}{'fill$5':>8}{'/100 f7':>9}{'/100 f0':>9}{'fix$2 f7':>9}{'fix$5 f7':>9}{'fix$10 f7':>10}{'HYB$50 f7':>10}{'HYB end':>8}{'maxDD':>7}{'HYB f0':>8}{'+1s f7':>8}{'+5s f7':>8}{'$100 f7':>9}{'wst1h':>7}{'wst3h':>7}{'ASIA':>7}{'LON':>7}{'US':>7}")
    summ = []; paths = []; cont_state = None; cont_rows = []
    for d in DATES:
        if d not in out: continue
        D, nmap, ntr = out[d]
        for X in OFFSETS:
            Tb = D[(D.offset_s == X) & D.fav.notna()].sort_values("window_epoch")
            p7, n, wr, av, pv, m = pnl100(Tb, 0, 5, 0.07); p0, _, _, _, _, _ = pnl100(Tb, 0, 5, 0.0); p1, *_ = pnl100(Tb, 1, 5, 0.07); p5, *_ = pnl100(Tb, 5, 5, 0.07); p100, *_ = pnl100(Tb, 0, 100, 0.07)
            fx = {s: run_fixed(trades_for(Tb, 0, s), 0.07, s)["pnl"] for s in (2.0, 5.0, 10.0)}
            h7, _, eq7, log7 = run_hybrid(trades_for(Tb, 0, 5), 0.07); h0, _, _, _ = run_hybrid(trades_for(Tb, 0, 5), 0.0)
            ep = Tb.window_epoch.to_numpy()[m]; pd_ = pd.DataFrame(dict(ep=ep, p=pv, sess=[sess(e) for e in ep]))
            hr = pd_.groupby(pd_.ep // 3600).p.sum(); h3 = pd_.groupby(pd_.ep // 10800).p.sum(); ss = pd_.groupby("sess").p.sum()
            rec = dict(date=d, offset=X, markets=ntr, trades=n, win=wr, avg_fill=av, pnl100_f7=p7, pnl100_f0=p0, fixed2_f7=fx[2.0], fixed5_f7=fx[5.0], fixed10_f7=fx[10.0],
                       hybrid_f7=h7["pnl"], hybrid_end_f7=h7["end"], hybrid_maxdd_f7=h7["maxdd"], hybrid_f0=h0["pnl"], hybrid_end_f0=h0["end"], p1s_f7=p1, p5s_f7=p5, p100_f7=p100,
                       worst1h=hr.min() if len(hr) else float("nan"), worst3h=h3.min() if len(h3) else float("nan"), asia=ss.get("ASIA", 0.0), london=ss.get("LONDON", 0.0), us=ss.get("US", 0.0), **{f"hyb_{k}": v for k, v in h7.items()})
            summ.append(rec)
            if X == 120:
                for i, l in enumerate(log7): paths.append(dict(date=d, mode="independent", i=i, **l))
                r_c, cont_state, eq_c, log_c = run_hybrid(trades_for(Tb, 0, 5), 0.07, state=cont_state); cont_rows.append(dict(date=d, **r_c))
                for i, l in enumerate(log_c): paths.append(dict(date=d, mode="continuous", i=i, **l))
            print(f"{d:<12}{X:>4}{ntr:>5}{n:>7}{wr:>6.1f}{av:>8.3f}{p7:>+9.2f}{p0:>+9.2f}{fx[2.0]:>+9.2f}{fx[5.0]:>+9.2f}{fx[10.0]:>+10.2f}{h7['pnl']:>+10.2f}{h7['end']:>8.2f}{h7['maxdd']:>7.2f}{h0['pnl']:>+8.2f}{p1:>+8.2f}{p5:>+8.2f}{p100:>+9.2f}{rec['worst1h']:>+7.2f}{rec['worst3h']:>+7.2f}{rec['asia']:>+7.2f}{rec['london']:>+7.2f}{rec['us']:>+7.2f}")
    S = pd.DataFrame(summ); S.to_csv(HERE / "market_favourite_5day_summary.csv", index=False); pd.DataFrame(paths).to_csv(HERE / "hybrid_staking_5day_paths.csv", index=False)
    C = pd.DataFrame(cont_rows); C.to_csv(HERE / "hybrid_continuous_120s.csv", index=False)
    print("\nCONTINUOUS $50 PATH, 120 s, fee 0.07, capital and stake carried across the dates in order:")
    for r in C.itertuples(): print(f"  {r.date}: start {r.start:7.2f} -> end {r.end:7.2f}  ({r.pnl:+.2f})  trades {r.trades} acc {r.acc:.1f}%  stake {r.start_stake:.2f}->{r.end_stake:.2f}  recalc 3W {r.recalc_3w} 2L {r.recalc_2l}  maxDD {r.maxdd:.2f}  low {r.lowest_capital:.2f}{'  BANKRUPT' if r.bankrupt else ''}")
    s120 = S[S.offset == 120]
    print(f"\n120 s across days: positive {(s120.pnl100_f7 > 0).sum()}/{len(s120)}  negative {(s120.pnl100_f7 <= 0).sum()}/{len(s120)}  worst day {s120.pnl100_f7.min():+.2f}/100  median {s120.pnl100_f7.median():+.2f}/100  best {s120.pnl100_f7.max():+.2f}/100")
    print("\nLABEL: TRADE-TAPE PROXY (fills = VWAP of actual taker-BUY prints after T, not a ladder walk). Primary fee 0.07. One trade per window. Not Predict.fun.")

if __name__ == "__main__":
    main()
