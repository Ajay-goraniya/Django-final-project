#!/usr/bin/env python3
"""EF-12: does EF improve if it can see the SETTLEMENT LINE? READ-ONLY. PAPER. Master OFF.

Owner, via V: EF's move features are Binance close-vs-open. The venue settles on the Chainlink
btc-5m-twap-60 - the 60 s TWAP at the candle close against the TWAP at the open. EF has never seen the
quantity it is actually paid on. London's real fills say the neutral zone is where the money dies
(|z|<0.5: n123, -0.110/$1, both halves negative) and the contrarian zone pays (z<-0.5: n111, +$142).

z, built causally from tape1s ref_px:
  opening line      L  = ref at the candle epoch
  projected close   P  = the settlement window is seconds 240..300. Before 240 none of it has happened,
                         so P = the current ref (a random walk has no better guess). From 240 on, the
                         observed part of the window is used and the rest is filled with the current ref.
  scale             s  = per-second sigma of the ref over the trailing 300 s, times sqrt(seconds left)
  z = (P - L) / s ,  and twap_dist = (P - L) / L * 1e4  as a second, unscaled input

ARMS  A fixed15 as-is | B fixed15 with NO fire while |z| < cut, cut in {0.25,0.5,0.75,1.0}, whole grid
      C fixed15 refit walk-forward with z and twap_dist ADDED as inputs | D raw25 with B's rule
All on decide_log 09-24..28 (where the engine's p lives) with the per-pass +250 ms FAK sim.
"""
import sys, os, math, sqlite3, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1, cost, be, fit_logistic, predict
from ef3 import platt, pad_cost, STAKE
from ef10 import build as build_rows
from ef3_shadow import outcomes

LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
CUTS = (0.25, 0.50, 0.75, 1.00)
CACHE = '/home/ubuntu/pm_ef3/ef12_z.npz'


def zbuild(ep_u):
    """per (epoch, sec) -> z and twap_dist, from the 1 s ref tape. Causal: only seconds <= s are used."""
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True); return {int(a): (b, c) for a, b, c in
                                                       zip(z['ep'], z['z'], z['td'])}
    c = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    ref = {int(t): float(p) for t, p in c.execute('SELECT ts, ref_px FROM tape1s WHERE ref_px IS NOT NULL')}
    EPs, Z, TD = [], [], []
    for ep in sorted(ep_u):
        L = ref.get(ep)
        if L is None or L <= 0: continue
        r = np.array([ref.get(ep + s, np.nan) for s in range(-300, 301)], float)
        m = np.isnan(r)
        if m[300:].mean() > 0.25: continue                    # candle too gappy to trust
        i = np.where(~m, np.arange(len(r)), 0); np.maximum.accumulate(i, out=i); r = r[i]
        if np.isnan(r).any(): continue
        cur = r[300:]                                          # seconds 0..300 of the candle
        pre = r[:300]
        zz = np.zeros(301); td = np.zeros(301)
        for s in range(301):
            hist = np.concatenate([pre, cur[:s + 1]])[-301:]
            d = np.diff(hist)
            sig = float(np.std(d)) if len(d) > 30 else 0.0
            if s < 240:
                P = cur[s]
            else:
                obs = cur[240:s + 1]
                P = (obs.sum() + cur[s] * (300 - s)) / 61.0
            rem = max(300 - s, 1)
            sc = sig * math.sqrt(rem)
            zz[s] = (P - L) / sc if sc > 1e-9 else 0.0
            td[s] = (P - L) / L * 1e4
        EPs.append(ep); Z.append(zz); TD.append(td)
    np.savez(CACHE, ep=np.array(EPs), z=np.stack(Z), td=np.stack(TD))
    return {int(a): (b, c) for a, b, c in zip(EPs, Z, TD)}


def segs(ep):
    b = np.flatnonzero(np.r_[True, ep[1:] != ep[:-1]])
    return b


def cell(mask, lat, cap, own, win, day, starts, BIG, hc=0.0):
    idx = np.where(mask, np.arange(len(mask)), BIG)
    first = np.minimum.reduceat(idx, starts); first = first[first < BIG]
    if not len(first): return None
    q = np.where(lat[first] <= cap[first] + 1e-12, lat[first], np.nan)
    fl = np.isfinite(q)
    if not fl.any(): return None
    ff = first[fl]
    pnl = STAKE * per1(win[ff], np.minimum(q[fl] + hc, 0.99))
    cum = np.cumsum(pnl); mdd = float(np.max(np.maximum.accumulate(cum) - cum))
    byd = collections.defaultdict(float)
    for a, b_ in zip(day[ff], pnl): byd[a] += b_
    h = len(ff) // 2
    W = lambda sl: (sum(per1(win[ff][sl], q[fl][sl]) * cost(q[fl][sl])) / sum(cost(q[fl][sl]))
                    if len(q[fl][sl]) else float('nan'))
    return dict(tot=float(cum[-1]), mdd=mdd, n=len(first), nf=int(fl.sum()), fill=float(fl.mean()),
                byd=dict(byd), pos=sum(1 for v in byd.values() if v > 0), days=len(byd),
                h1=W(slice(0, h)), h2=W(slice(h, None)))


def show(tag, r, nd, r1=None):
    if not r: print(f'  {tag:26s} (no fills)'); return
    print(f'  {tag:26s}{r["tot"]:>+8.1f}{r["mdd"]:>7.1f}{r["n"]/nd:>7.1f}{100*r["fill"]:>6.1f}%'
          f'{f"{r[chr(112)+chr(111)+chr(115)]}/{r[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}'
          f'{(r1["tot"] if r1 else float("nan")):>+8.1f}{r["h1"]:>+8.3f}{r["h2"]:>+8.3f}')


if __name__ == '__main__':
    D = build_rows()
    ep, ts, own, ps, sec, lat, win, day = (D[k] for k in ('ep', 'ts', 'own', 'ps', 'sec', 'lat', 'win', 'day'))
    o = np.lexsort((ts, ep))
    ep, ts, own, ps, sec, lat, win, day = (x[o] for x in (ep, ts, own, ps, sec, lat, win, day))
    ZT = zbuild(set(ep.tolist()))
    keep = np.array([int(e) in ZT for e in ep])
    ep, ts, own, ps, sec, lat, win, day = (x[keep] for x in (ep, ts, own, ps, sec, lat, win, day))
    zz = np.array([ZT[int(e)][0][min(int(s), 300)] for e, s in zip(ep, sec)])
    td = np.array([ZT[int(e)][1][min(int(s), 300)] for e, s in zip(ep, sec)])
    days = sorted(set(day.tolist())); nd = len(days)
    starts = segs(ep); BIG = len(ep) + 10
    cap1 = np.minimum(own + 0.01, 0.99)
    base = ps >= 0.5
    f15 = base & ((platt_v := np.array([platt(p) for p in ps])) / np.array([pad_cost(a) for a in own]) - 1 >= 0.15)
    r25 = base & ((ps / be(own) - 1) >= 0.25)
    print(f'EF-12. rows {len(ep):,}  candles {len(starts):,}  days {days}')
    print(f'  |z| distribution: p10 {np.percentile(abs(zz),10):.2f}  p50 {np.percentile(abs(zz),50):.2f}  '
          f'p90 {np.percentile(abs(zz),90):.2f}   share |z|<0.5 {100*(abs(zz)<0.5).mean():.1f}%')
    hdr = (f'  {"arm":26s}{"$tot":>8}{"DD$":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"+1c":>8}{"H1":>8}{"H2":>8}')
    print(hdr)
    show('A fixed15 as-is', cell(f15, lat, cap1, own, win, day, starts, BIG), nd,
         cell(f15, lat, cap1, own, win, day, starts, BIG, 0.01))
    for c_ in CUTS:
        m = f15 & (np.abs(zz) >= c_)
        show(f'B fixed15 |z|>={c_:.2f}', cell(m, lat, cap1, own, win, day, starts, BIG), nd,
             cell(m, lat, cap1, own, win, day, starts, BIG, 0.01))
    show('D raw25 as-is', cell(r25, lat, cap1, own, win, day, starts, BIG), nd,
         cell(r25, lat, cap1, own, win, day, starts, BIG, 0.01))
    for c_ in CUTS:
        m = r25 & (np.abs(zz) >= c_)
        show(f'D raw25 |z|>={c_:.2f}', cell(m, lat, cap1, own, win, day, starts, BIG), nd,
             cell(m, lat, cap1, own, win, day, starts, BIG, 0.01))
    # ---- C: refit fixed15's calibration WITH z and twap_dist, walk-forward by day ----
    lg = np.log(np.clip(ps, 1e-6, 1 - 1e-6) / np.clip(1 - ps, 1e-6, 1 - 1e-6))
    X = np.c_[lg, zz, td / 10.0, np.abs(zz)]
    pc = np.full(len(ps), np.nan)
    for i, d_ in enumerate(days):
        if i == 0: continue
        tr = np.isin(day, days[:i]); te = day == d_
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        w = fit_logistic((X[tr] - mu) / sd, win[tr])
        pc[te] = predict(w, (X[te] - mu) / sd)
    okc = np.isfinite(pc)
    mC = okc & (pc >= 0.5) & ((pc / np.array([pad_cost(a) for a in own]) - 1) >= 0.15)
    ndC = len(days) - 1
    print(f'  (C trains day-by-day, so it has {ndC} test days not {nd})')
    show('C fixed15 + z inputs', cell(mC, lat, cap1, own, win, day, starts, BIG), ndC,
         cell(mC, lat, cap1, own, win, day, starts, BIG, 0.01))
    for c_ in (0.5,):
        show(f'C + |z|>={c_:.2f}', cell(mC & (np.abs(zz) >= c_), lat, cap1, own, win, day, starts, BIG),
             ndC, cell(mC & (np.abs(zz) >= c_), lat, cap1, own, win, day, starts, BIG, 0.01))
