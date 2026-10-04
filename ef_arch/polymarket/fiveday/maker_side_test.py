#!/usr/bin/env python3
"""
maker_side_test.py -- the counterparty view. Instead of paying the ask for the favourite (taker), REST A BID on the
favourite and get filled only when a taker sells into it. Fill evidence = actual taker-SELL prints at or below our bid.
Five days: Polymarket data-api tape (taker side, token, price, size, 1-second ts).
Aug 1: pmxt last_trade_price events (side, price) + real best_bid at T from the ladder file.
Rule (frozen): at T = open + 120 s, favourite = token with the higher last print (tie/one-sided -> abstain).
  bid price      = last taker-SELL print on the favourite before T (five days)  /  real best_bid at T (Aug 1)
  filled         = a taker-SELL print on the favourite at price <= bid within FILL_WINDOW s after T
  fill price     = our bid (a resting order fills at its own price); stake $5, shares = 5/bid
  hold to settlement; win -> 1/bid - 1 per $1 (maker fee 0 primary; 0.07 shown as stress), loss -> -1
  unfilled       = no trade (0). PnL/100 windows counts unfilled windows as 0.
Adverse selection is the thing to watch: fills happen when the price is falling.
"""
import json, pathlib, sys, numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); from hybrid_stake import run_hybrid
DATES = ["2026-08-22", "2026-08-24", "2026-08-27", "2026-08-31", "2026-09-05"]; X = 120; FILL_WINDOWS = (30, 60, 120)
def ret(win, q, r): return ((1 - r * (1 - q)) / q - 1) if win else -1.0
def run_day(T, outcome, label, bid_src=None):
    """T: DataFrame ts, tok(UP/DOWN), side(BUY/SELL taker), price, window_epoch. bid_src: optional {ep: {side: best_bid}}"""
    rows = []
    for ep, g in T.groupby("window_epoch"):
        t0 = ep + X; up = g[g.tok == "UP"]; dn = g[g.tok == "DOWN"]; lu = up[up.ts < t0]; ld = dn[dn.ts < t0]
        if lu.empty or ld.empty: continue
        pu, pd_ = float(lu.price.iloc[-1]), float(ld.price.iloc[-1])
        if pu == pd_: continue
        fav = "UP" if pu > pd_ else "DOWN"; ft = up if fav == "UP" else dn
        if bid_src is not None:
            bid = bid_src.get(ep, {}).get(fav)
        else:
            s = ft[(ft.ts < t0) & (ft.side == "SELL")]; bid = float(s.price.iloc[-1]) if len(s) else None
        if bid is None or not np.isfinite(bid) or bid <= 0.02 or bid >= 0.98: continue
        rec = dict(ep=ep, fav=fav, bid=bid, ask_last=max(pu, pd_), win=(outcome[ep] == fav))
        after = ft[(ft.ts >= t0) & (ft.side == "SELL") & (ft.price <= bid)]
        for W in FILL_WINDOWS: rec[f"fill_{W}"] = bool(len(after[after.ts <= t0 + W]))
        rows.append(rec)
    D = pd.DataFrame(rows); n = len(D)
    print(f"\n{label}: windows {n}  avg bid {D.bid.mean():.3f}  avg last ask-side print {D.ask_last.mean():.3f}  favourite win rate (all) {100*D.win.mean():.1f}%")
    out = {}
    for W in FILL_WINDOWS:
        f = D[D[f"fill_{W}"]]; fr = 100 * len(f) / n
        for r in (0.0, 0.07):
            p = np.array([ret(w, q, r) for w, q in zip(f.win, f.bid)]); tot = p.sum()
            trades = [((lambda s, q=q: (float(q), 1e9)), bool(w)) for w, q in zip(f.win, f.bid)]
            h, _, _, _ = run_hybrid(trades, r)
            print(f"  fill window {W:>3}s  fee {r:.2f}: filled {fr:5.1f}%  win% on fills {100*f.win.mean():5.1f}  PnL/100 windows {100*tot/n:+6.2f}  fixed$5 {5*tot:+7.2f}  hybrid$50 -> {h['end']:6.2f} (maxDD {h['maxdd']:.2f})")
            out[(W, r)] = dict(filled=fr, win=100 * f.win.mean(), pnl100=100 * tot / n, hyb=h["end"])
    # adverse selection: win rate filled vs unfilled
    f = D[D.fill_60]; u = D[~D.fill_60]; print(f"  adverse selection @60s: win% filled {100*f.win.mean():.1f} vs unfilled {100*u.win.mean():.1f}  (fills happen when the favourite is being sold)")
    return D, out
res = {}
for d in DATES:
    M = json.load(open(HERE / "data" / "markets" / f"btc5m_markets_{d}.json")); outcome = {}
    for r in M["rows"]:
        m = r["market"]; op = json.loads(m["outcomePrices"]); outs = json.loads(m["outcomes"]); outcome[r["epoch"]] = outs[int(np.argmax([float(x) for x in op]))].upper()
    T = pd.read_parquet(HERE / "data" / "trades" / f"trades_{d}.parquet"); T["tok"] = T.outcome.str.upper(); T = T[(T.ts >= T.window_epoch) & (T.ts < T.window_epoch + 300)].sort_values("ts")
    D, out = run_day(T, outcome, d); res[d] = out
# Aug 1 from pmxt: last_trade_price events + real best_bid at T
import glob
fr = []
for f in sorted(glob.glob(str(HERE.parent / "books" / "hour_*.parquet"))):
    t = pq.read_table(f, columns=["timestamp", "event_type", "price", "side", "window_epoch", "side_label"]).to_pandas(); t = t[t.event_type == "last_trade_price"]
    t["ts"] = (t.timestamp.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1s"); fr.append(t)
A = pd.concat(fr); A["tok"] = A.side_label.str.upper(); A["price"] = A.price.astype(float); A["window_epoch"] = A.window_epoch.astype(int)
A = A[(A.ts >= A.window_epoch) & (A.ts < A.window_epoch + 300)].sort_values("ts")
L = pq.read_table(HERE.parent / "polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book & (L.offset_s == X)]
bid_src = {}; outcome1 = {}
for r in L.itertuples(): bid_src.setdefault(int(r.window_epoch), {})[r.side] = float(r.best_bid); outcome1[int(r.window_epoch)] = r.outcome
print("\npmxt trade side values:", A.side.value_counts().to_dict())
D1, out1 = run_day(A, outcome1, "2026-08-01 (pmxt prints + REAL best_bid at T)", bid_src=bid_src); res["2026-08-01"] = out1
print("\nSUMMARY maker-side favourite, 60 s fill window, fee 0 (primary for a resting order) | fee 0.07:")
for d, o in res.items(): print(f"  {d}: filled {o[(60,0.0)]['filled']:5.1f}%  win {o[(60,0.0)]['win']:5.1f}%  PnL/100 {o[(60,0.0)]['pnl100']:+6.2f} | fee7 {o[(60,0.07)]['pnl100']:+6.2f}   hybrid$50 -> {o[(60,0.0)]['hyb']:.2f}")
print("\nLABEL: maker-side proxy. Fill = an actual taker-SELL print at or below our bid after T; queue position and partial fills not modelled (optimistic). Not Predict.fun.")
