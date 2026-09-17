#!/usr/bin/env python3
"""
real_book_partial.py -- REAL L2 LADDERS (PolyOrderbooks open files, 1-second capture) for every BTC 5m
market those files contain (2026-08-21 .. 2026-08-24; requested dates 08-22 and 08-24 are PARTIAL days).

Corrected favourite rule: at decision time T = open + X, take the latest snapshot <= T of BOTH tokens,
mid = (best_bid+best_ask)/2; favourite = higher mid; exact tie or a one-sided book on either token -> abstain.
Fill = walk the favourite's real ask ladder for the stake (executable VWAP). Latency variants buy the SAME side
chosen at T using the snapshot at T+1s / T+5s (1-second capture: +300ms is not resolvable, +1s is the floor).
Outcome = the file's winner column, cross-checked against Gamma outcomePrices where we mapped the day.
Writes data/polyorderbooks_btc5m_ladders.parquet and prints per-day / per-offset results.
"""
import json, pathlib, sys, math, datetime
import numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
from hybrid_stake import run_hybrid, run_fixed
OFFSETS = (30, 60, 90, 120, 180, 240); STAKES = (2.0, 5.0, 10.0, 100.0); DELAYS = (0, 1, 5)
def cost(q, r): return q / (1.0 - r * (1.0 - q))   # BUY-fee semantics: win return = (1 - r(1-q))/q - 1
def walk(prices, sizes, stake):
    left = stake; sh = 0.0; c = 0.0
    for p, s in zip(prices, sizes):
        if left <= 1e-9: break
        take = min(s, left / p); sh += take; c += take * p; left -= take * p
    return (c / sh if sh > 0 else float("nan")), sh, left <= 1e-6

frames = []
for f in ("updown_5m.parquet", "btc_5min_l2.parquet"):
    t = pq.read_table(HERE / "data" / "hf_polyorderbooks" / f).to_pandas(); t = t[t.market_slug.str.startswith("btc-updown-5m")]; frames.append(t)
B = pd.concat(frames).drop_duplicates(["market_slug", "outcome", "captured_at"]).sort_values(["market_slug", "outcome", "captured_at"])
B["ts"] = (B.captured_at.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1s")
B["open"] = B.market_slug.str.split("-").str[-1].astype(int)
print(f"real-book snapshots: {len(B):,}  markets {B.market_slug.nunique()}  days {sorted(B.market_end_at.dt.date.astype(str).unique())}")

# Gamma cross-check of winners where we have the mapping
gam = {}
for f in (HERE / "data" / "markets").glob("btc5m_markets_*.json"):
    for r in json.load(open(f))["rows"]:
        m = r["market"]; op = json.loads(m["outcomePrices"]); outs = json.loads(m["outcomes"]); gam[r["epoch"]] = outs[int(np.argmax([float(x) for x in op]))].upper()

rows = []
for slug, g in B.groupby("market_slug"):
    op = int(g.open.iloc[0]); wrow = g[g.is_winning_outcome]; win = wrow.outcome.iloc[0].upper() if len(wrow) else None; day = str((g.market_end_at.iloc[0] - pd.Timedelta("1s")).date())
    tok = {o.upper(): gg.sort_values("ts") for o, gg in g.groupby("outcome")}
    if "UP" not in tok or "DOWN" not in tok or win is None: continue
    cov = min(len(tok["UP"]), len(tok["DOWN"]))
    for X in OFFSETS:
        T = op + X; rec = dict(slug=slug, day=day, window_epoch=op, offset_s=X, decision_ts=T, winner=win, gamma_winner=gam.get(op), snaps=cov)
        book = {}
        for side in ("UP", "DOWN"):
            s = tok[side]; i = np.searchsorted(s.ts.to_numpy(), T, side="right") - 1
            if i < 0: book = None; break
            r = s.iloc[i]; bb = r.best_bid; ba = r.best_ask
            book[side] = dict(i=i, bb=bb, ba=ba, age=T - int(r.ts), mid=(bb + ba) / 2 if (np.isfinite(bb) and np.isfinite(ba) and bb > 0 and ba > 0) else float("nan"), s=s)
        if book is None: rec.update(has_book=False); rows.append(rec); continue
        mu, md = book["UP"]["mid"], book["DOWN"]["mid"]; rec.update(has_book=True, mid_up=mu, mid_down=md, age_up=book["UP"]["age"], age_down=book["DOWN"]["age"])
        if not (np.isfinite(mu) and np.isfinite(md)) or mu == md: rec.update(fav=None); rows.append(rec); continue
        fav = "UP" if mu > md else "DOWN"; rec.update(fav=fav, fav_mid=max(mu, md), fav_best_ask=book[fav]["ba"], win_fav=(win == fav))
        s = book[fav]["s"]
        for dly in DELAYS:
            j = np.searchsorted(s.ts.to_numpy(), T + dly, side="right") - 1; r = s.iloc[j]
            ap, asz = list(r.ask_prices), list(r.ask_sizes)
            if r.crossed or not ap: 
                for st in STAKES: rec[f"vwap_d{dly}_s{int(st)}"] = float("nan"); rec[f"ok_d{dly}_s{int(st)}"] = False
                continue
            for st in STAKES:
                v, sh, ok = walk(ap, asz, st); rec[f"vwap_d{dly}_s{int(st)}"] = v; rec[f"shares_d{dly}_s{int(st)}"] = sh; rec[f"ok_d{dly}_s{int(st)}"] = ok
        rows.append(rec)
D = pd.DataFrame(rows); D.to_parquet(HERE / "data" / "polyorderbooks_btc5m_ladders.parquet", index=False)
H = D[D.has_book]
print(f"ladder rows {len(D):,}  with both books {len(H):,}  abstain(tie/one-sided) {int(H.fav.isna().sum())}  "
      f"gamma cross-check: {int((H.gamma_winner.notna() & (H.gamma_winner != H.winner)).sum())} mismatches of {int(H.gamma_winner.notna().sum())} checked")
F = H[H.fav.notna()].copy()
print("\nFAVOURITE CALIBRATION (real $5 VWAP bucket, all PolyOrderbooks BTC 5m markets, all offsets pooled):")
print(f"{'bucket':<12}{'n':>6}{'mean vwap':>11}{'realized':>10}{'diff':>8}{'EV/$ fee0':>11}{'EV/$ fee7':>11}")
for lo, hi in ((.5,.6),(.6,.7),(.7,.8),(.8,.9),(.9,1.0)):
    m = (F.vwap_d0_s5 >= lo) & (F.vwap_d0_s5 < hi) & F.ok_d0_s5
    if m.sum(): q = F.vwap_d0_s5[m].mean(); w = F.win_fav[m].mean(); print(f"[{lo:.1f},{hi:.1f})   {int(m.sum()):>6}{q:>11.3f}{w:>10.3f}{w-q:>+8.3f}{w/cost(q,0)-1:>+11.3f}{w/cost(q,.07)-1:>+11.3f}")
print(f"\n{'day':<12}{'off':>4}{'mkts':>5}{'trades':>7}{'win%':>6}{'avgVWAP$5':>10}{'PnL/100 f0':>11}{'PnL/100 f7':>11}{'fix$5 f0':>9}{'hyb$50 f0':>10}{'hyb$50 f7':>10}{'+1s f0':>8}{'+5s f0':>8}{'$100 f0':>9}")
summ = []
for day, g in F.groupby("day"):
    for X in OFFSETS:
        T = g[g.offset_s == X].sort_values("window_epoch"); nm = T.slug.nunique()
        if T.empty: continue

        def stake_bucket(s):
            """precomputed fills exist for $2/$5/$10/$100: use the smallest bucket >= stake (conservative); above $100 use $100 (optimistic, flagged)"""
            for b in (2, 5, 10, 100):
                if s <= b + 1e-9: return b
            return 100
        def fill_at(r, dly, s):
            b = stake_bucket(s); k = f"d{dly}_s{b}"
            return ((float(getattr(r, f"vwap_{k}")) if getattr(r, f"ok_{k}", False) else float("nan")), 1e9)
        def trades(dly, key):
            return [((lambda s, r=r, dly=dly: fill_at(r, dly, s)), bool(r.win_fav)) for r in T.itertuples()]
        def pnl100(dly, st, r):
            v = np.array([getattr(x, f"vwap_d{dly}_s{int(st)}") for x in T.itertuples()]); ok = np.array([getattr(x, f"ok_d{dly}_s{int(st)}") for x in T.itertuples()]); w = T.win_fav.to_numpy()
            m = ok & np.isfinite(v); return 100 * np.where(w[m], 1 / cost(v[m], r) - 1, -1.0).sum() / max(m.sum(), 1), int(m.sum()), 100 * w[m].mean() if m.sum() else float("nan"), float(v[m].mean()) if m.sum() else float("nan")
        p0, n0, wr, av = pnl100(0, 5, 0.0); p7, _, _, _ = pnl100(0, 5, 0.07); p1, _, _, _ = pnl100(1, 5, 0.0); p5, _, _, _ = pnl100(5, 5, 0.0); p100, _, _, _ = pnl100(0, 100, 0.0)
        h0, _, _, _ = run_hybrid(trades(0, 5), 0.0); h7, _, _, _ = run_hybrid(trades(0, 5), 0.07); f5 = run_fixed(trades(0, 5), 0.0, 5.0)
        summ.append(dict(day=day, offset=X, markets=nm, trades=n0, win=wr, avg_vwap=av, pnl100_f0=p0, pnl100_f7=p7, fixed5_f0=f5["pnl"], hybrid_f0=h0["pnl"], hybrid_f7=h7["pnl"], p1s=p1, p5s=p5, p100=p100, hybrid_end_f0=h0["end"], maxdd=h0["maxdd"]))
        print(f"{day:<12}{X:>4}{nm:>5}{n0:>7}{wr:>6.1f}{av:>10.3f}{p0:>+11.2f}{p7:>+11.2f}{f5['pnl']:>+9.2f}{h0['pnl']:>+10.2f}{h7['pnl']:>+10.2f}{p1:>+8.2f}{p5:>+8.2f}{p100:>+9.2f}")
pd.DataFrame(summ).to_csv(HERE / "polyorderbooks_partial_summary.csv", index=False)
print("\nLABEL: REAL LADDERS (PolyOrderbooks open files). Days are PARTIAL (a few hours each), not full 288-window days. Fee 0.07 = official rate; fee 0 = what the Aug-1 stream reported.")
