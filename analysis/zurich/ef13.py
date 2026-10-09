#!/usr/bin/env python3
"""EF-13: the owner's exact TWAP question. READ-ONLY. PAPER. Master OFF.

"Can the TWAP still close past the settlement line, within the REMAINING TIME and given the STRENGTH OF
THE MOVE." His example is the whole point: a small burst puts price a few dollars over the line with 30 s
left and the TWAP still closes under, because most of the 60 s settlement window is already locked in.

So the denominator is NOT sigma*sqrt(seconds left) - that is the variance of the terminal PRICE, and EF-12
used it. A TWAP is an AVERAGE, its remaining variance is smaller, and part of it is already locked:

  settlement window = seconds 240..300 (61 samples). At second s:
    s >= 240   locked  = [240..s] observed; unlocked u = 300-s samples, each a random walk from r_s
               Var(sum of unlocked) = sigma^2 * sum_{m=1..u} m^2 = sigma^2 * u(u+1)(2u+1)/6
    s <  240   nothing locked; the window starts d = 240-s seconds ahead
               Var(sum) = sigma^2 * [ d*61^2 + sum_{m=1..60} m^2 ]
    Var(TWAP) = Var(sum) / 61^2        ->  denom = sigma * sqrt(Var(TWAP))

  P = (locked sum + r_s * unlocked) / 61          z = (P - L) / denom      P_twap = Phi(z)

MOVE STRENGTH, in sigma units: mom5/mom15/mom30 = ref change over the last 5/15/30 s, and burst = the
largest single-second move in the last 5 s. All signed to the SIDE being bought (negated for DOWN), except
burst which is a magnitude.

ARMS  A fixed15 | B fixed15 skip |z|<cut, grid | C fixed15 refit WITH P_twap + move strength as inputs
      E fixed15 but p REPLACED by a logistic on [z, mom5, mom15, mom30, burst], walk-forward, same EV bar
"""
import sys, os, math, sqlite3, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1, cost, be, fit_logistic, predict
from ef3 import platt, pad_cost, STAKE
from ef10 import build as build_rows
from ef12 import segs, cell, show

LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
CUTS = (0.25, 0.50, 0.75, 1.00)
W0, W1, NW = 240, 300, 61
S60 = 60 * 61 * 121 // 6                      # sum_{m=1..60} m^2 = 73,810
CACHE = '/home/ubuntu/pm_ef3/ef13_z.npz'


def twap_var_factor(s):
    """Var(TWAP) / sigma^2 at second s - the owner's 'effective remaining variance'."""
    if s >= W0:
        u = W1 - s
        return (u * (u + 1) * (2 * u + 1) / 6.0) / NW ** 2
    d = W0 - s
    return (d * NW ** 2 + S60) / float(NW ** 2)


def zbuild(eps):
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {int(a): tuple(z[k][i] for k in ('z', 'm5', 'm15', 'm30', 'bu'))
                for i, a in enumerate(z['ep'])}
    c = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    ref = {int(t): float(p) for t, p in c.execute('SELECT ts, ref_px FROM tape1s WHERE ref_px IS NOT NULL')}
    VF = np.array([twap_var_factor(s) for s in range(301)])
    EP, Z, M5, M15, M30, BU = [], [], [], [], [], []
    for ep in sorted(eps):
        L = ref.get(ep)
        if L is None or L <= 0: continue
        r = np.array([ref.get(ep + s, np.nan) for s in range(-300, 301)], float)
        if np.isnan(r[300:]).mean() > 0.25: continue
        i = np.where(~np.isnan(r), np.arange(len(r)), 0); np.maximum.accumulate(i, out=i); r = r[i]
        if np.isnan(r).any(): continue
        cur = r[300:]
        zz = np.zeros(301); m5 = np.zeros(301); m15 = np.zeros(301); m30 = np.zeros(301); bu = np.zeros(301)
        for s in range(301):
            hist = r[:301 + s][-301:]
            d = np.diff(hist)
            sig = float(np.std(d)) if len(d) > 30 else 0.0
            if sig < 1e-9: sig = 1e-9
            if s >= W0:
                P = (cur[W0:s + 1].sum() + cur[s] * (W1 - s)) / float(NW)
            else:
                P = cur[s]
            zz[s] = (P - L) / (sig * math.sqrt(max(VF[s], 1e-12)))
            base = r[300 + s]
            m5[s] = (base - r[300 + s - 5]) / sig if s >= 5 else 0.0
            m15[s] = (base - r[300 + s - 15]) / sig if s >= 15 else 0.0
            m30[s] = (base - r[300 + s - 30]) / sig if s >= 30 else 0.0
            w = np.diff(r[300 + max(s - 5, 0):300 + s + 1])
            bu[s] = (np.max(np.abs(w)) / sig) if len(w) else 0.0
        EP.append(ep); Z.append(zz); M5.append(m5); M15.append(m15); M30.append(m30); BU.append(bu)
    np.savez(CACHE, ep=np.array(EP), z=np.stack(Z), m5=np.stack(M5), m15=np.stack(M15),
             m30=np.stack(M30), bu=np.stack(BU))
    return {int(a): (Z[i], M5[i], M15[i], M30[i], BU[i]) for i, a in enumerate(EP)}


if __name__ == '__main__':
    D = build_rows()
    ep, ts, own, ps, sec, lat, win, day = (D[k] for k in ('ep', 'ts', 'own', 'ps', 'sec', 'lat', 'win', 'day'))
    o = np.lexsort((ts, ep))
    ep, ts, own, ps, sec, lat, win, day = (x[o] for x in (ep, ts, own, ps, sec, lat, win, day))
    ZT = zbuild(set(ep.tolist()))
    keep = np.array([int(e) in ZT for e in ep])
    ep, ts, own, ps, sec, lat, win, day = (x[keep] for x in (ep, ts, own, ps, sec, lat, win, day))
    # the row's side: decide_log logs the engine's favoured side, ps>=0.5 marks it; UP iff own is up_ask.
    # Rows come in (UP, DOWN) order per pass, so parity of position within the pass gives the side.
    ss = np.minimum(sec.astype(int), 300)
    zc = np.array([ZT[int(e)][0][s] for e, s in zip(ep, ss)])
    m5 = np.array([ZT[int(e)][1][s] for e, s in zip(ep, ss)])
    m15 = np.array([ZT[int(e)][2][s] for e, s in zip(ep, ss)])
    m30 = np.array([ZT[int(e)][3][s] for e, s in zip(ep, ss)])
    bu = np.array([ZT[int(e)][4][s] for e, s in zip(ep, ss)])
    isup = np.r_[True, (ts[1:] != ts[:-1]) | (ep[1:] != ep[:-1])]
    sgn = np.where(isup, 1.0, -1.0)
    zs, m5s, m15s, m30s = zc * sgn, m5 * sgn, m15 * sgn, m30 * sgn
    days = sorted(set(day.tolist())); nd = len(days)
    starts = segs(ep); BIG = len(ep) + 10
    cap1 = np.minimum(own + 0.01, 0.99)
    base = ps >= 0.5
    pc_ = np.array([pad_cost(a) for a in own]); pl_ = np.array([platt(p) for p in ps])
    f15 = base & ((pl_ / pc_ - 1) >= 0.15)
    print(f'EF-13. rows {len(ep):,}  candles {len(starts):,}  days {days}')
    print(f'  |z| (TWAP variance): p10 {np.percentile(abs(zs),10):.2f}  p50 {np.percentile(abs(zs),50):.2f}  '
          f'p90 {np.percentile(abs(zs),90):.2f}  share |z|<0.5 {100*(abs(zs)<0.5).mean():.1f}%')
    print(f'  vs EF-12 terminal-variance z, this denominator is larger before sec 240, so |z| is SMALLER')
    print(f'  {"arm":26s}{"$tot":>8}{"DD$":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"+1c":>8}{"H1":>8}{"H2":>8}')
    show('A fixed15 as-is', cell(f15, lat, cap1, own, win, day, starts, BIG), nd,
         cell(f15, lat, cap1, own, win, day, starts, BIG, 0.01))
    for c_ in CUTS:
        m = f15 & (np.abs(zs) >= c_)
        show(f'B fixed15 |z|>={c_:.2f}', cell(m, lat, cap1, own, win, day, starts, BIG), nd,
             cell(m, lat, cap1, own, win, day, starts, BIG, 0.01))
    lg = np.log(np.clip(ps, 1e-6, 1 - 1e-6) / np.clip(1 - ps, 1e-6, 1 - 1e-6))
    Pt = 0.5 * (1.0 + np.vectorize(math.erf)(zs / math.sqrt(2)))
    XC = np.c_[lg, Pt, zs, m5s, m15s, m30s, bu]
    XE = np.c_[zs, m5s, m15s, m30s, bu]
    ndC = nd - 1
    for tag, X in (('C fixed15 + P_twap+move', XC), ('E p REPLACED by P_twap', XE)):
        pn = np.full(len(ps), np.nan)
        for i, d_ in enumerate(days):
            if i == 0: continue
            tr = np.isin(day, days[:i]); te = day == d_
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            w = fit_logistic((X[tr] - mu) / sd, win[tr])
            pn[te] = predict(w, (X[te] - mu) / sd)
        ok = np.isfinite(pn)
        m = ok & (pn >= 0.5) & ((pn / pc_ - 1) >= 0.15)
        show(tag, cell(m, lat, cap1, own, win, day, starts, BIG), ndC,
             cell(m, lat, cap1, own, win, day, starts, BIG, 0.01))
        for c_ in (0.5, 1.0):
            mm = m & (np.abs(zs) >= c_)
            show(f'  + |z|>={c_:.2f}', cell(mm, lat, cap1, own, win, day, starts, BIG), ndC,
                 cell(mm, lat, cap1, own, win, day, starts, BIG, 0.01))
