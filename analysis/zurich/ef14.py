#!/usr/bin/env python3
"""EF-14: EF-12/13 re-run with LONDON'S EXACT z, and on fixed15's OWN FIRES. READ-ONLY. Master OFF.

V relayed London's tl.py definition. It differs from mine in five places that all matter, and I had every
one of them different:
  line   = mean REF[E-61 .. E-2]        - a TWAP60 ending BEFORE the epoch. I used ref AT the epoch.
  P      = latest REF in [t-5, t-1]     - not the ref at t.
  sigma  = sqrt(mean(dlogREF^2 over [t-121,t-1])) * P   - RMS of log returns, no mean subtraction, in $/s.
  start  = E + 239                      - I used 240, and a 60-sample window, not 61.
  sd     = sqrt(var)/60,  var locked = sigma^2*m(m+1)(2m+1)/6 ; unlocked = sigma^2*(3600*d + S2),
           S2 = sum_{i,j<60} min(i,j).   z = (mean - line)*side / sd, SIGNED to the side being bought.

AND THE COMPARISON WAS WRONG TOO. EF-12's B arm took the first pass clearing fixed15 AND |z|, which can be
a LATER pass than the one fixed15 actually fires. London filters the fire it really took. Both are
reported: FIRE-ONLY is the one comparable to London's live fills, and it is the primary.
"""
import sys, os, math, sqlite3, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1, cost, be
from ef3 import platt, pad_cost, STAKE
from ef10 import build as build_rows
from ef12 import segs, cell, show
from london_z import london_z_at, S2 as _S2

LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
CUTS = (0.25, 0.50, 0.75, 1.00)
S2 = _S2   # single definition lives in london_z.py
CACHE = '/home/ubuntu/pm_ef3/ef14_z.npz'


def zbuild(eps):
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {int(a): z['z'][i] for i, a in enumerate(z['ep'])}
    c = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    ref = {int(t): float(p) for t, p in c.execute('SELECT ts, ref_px FROM tape1s WHERE ref_px IS NOT NULL')}
    EP, Z = [], []
    for E in sorted(eps):
        pre = [ref[E - k] for k in range(2, 62) if (E - k) in ref]      # REF[E-61 .. E-2]
        if len(pre) < 45: continue
        line = float(np.mean(pre))
        start = E + 239
        zz = np.full(301, np.nan)
        for s in range(0, 301):
            t = E + s                                                   # t = ceil(signal_ts)
            win5 = [ref[u] for u in range(t - 5, t) if u in ref]
            if not win5: continue
            P = float(win5[-1])
            hist = [ref[u] for u in range(t - 121, t) if u in ref]
            if len(hist) < 60: continue
            dl = np.diff(np.log(np.array(hist, float)))
            sigma = float(math.sqrt(float(np.mean(dl ** 2)))) * P
            if sigma <= 0: continue
            if t - 1 >= start:
                kn = t - start
                m = 60 - kn
                if m <= 0: continue
                seg = [ref[u] for u in range(start, t) if u in ref]
                if not seg: continue
                mean = (float(np.mean(seg)) * kn + m * P) / 60.0
                var = sigma ** 2 * m * (m + 1) * (2 * m + 1) / 6.0
            else:
                d = start - (t - 1)
                mean = P
                var = sigma ** 2 * (3600.0 * d + S2)
            sd = math.sqrt(var) / 60.0
            if sd <= 0: continue
            zz[s] = (mean - line) / sd                                  # UP-signed; DOWN = negate
        EP.append(E); Z.append(zz)
    np.savez(CACHE, ep=np.array(EP), z=np.stack(Z))
    return {int(a): Z[i] for i, a in enumerate(EP)}


def fire_only(mask, zs, cut, lat, cap, own, win, day, starts, BIG, hc=0.0):
    """fixed15 fires, THEN the |z| filter is applied to that fire - London's order, not mine."""
    idx = np.where(mask, np.arange(len(mask)), BIG)
    first = np.minimum.reduceat(idx, starts); first = first[first < BIG]
    if cut is not None: first = first[np.abs(zs[first]) >= cut]
    if not len(first): return None
    q = np.where(lat[first] <= cap[first] + 1e-12, lat[first], np.nan)
    fl = np.isfinite(q)
    if not fl.any(): return None
    ff = first[fl]
    pnl = STAKE * per1(win[ff], np.minimum(q[fl] + hc, 0.99))
    cum = np.cumsum(pnl); mdd = float(np.max(np.maximum.accumulate(cum) - cum))
    byd = collections.defaultdict(float)
    for a, b in zip(day[ff], pnl): byd[a] += b
    h = len(ff) // 2
    W = lambda sl: (sum(per1(win[ff][sl], q[fl][sl]) * cost(q[fl][sl])) / sum(cost(q[fl][sl]))
                    if len(q[fl][sl]) else float('nan'))
    return dict(tot=float(cum[-1]), mdd=mdd, n=len(first), nf=int(fl.sum()), fill=float(fl.mean()),
                byd=dict(byd), pos=sum(1 for v in byd.values() if v > 0), days=len(byd),
                h1=W(slice(0, h)), h2=W(slice(h, None)))


if __name__ == '__main__':
    D = build_rows()
    ep, ts, own, ps, sec, lat, win, day = (D[k] for k in ('ep', 'ts', 'own', 'ps', 'sec', 'lat', 'win', 'day'))
    o = np.lexsort((ts, ep))
    ep, ts, own, ps, sec, lat, win, day = (x[o] for x in (ep, ts, own, ps, sec, lat, win, day))
    ZT = zbuild(set(ep.tolist()))
    keep = np.array([int(e) in ZT for e in ep])
    ep, ts, own, ps, sec, lat, win, day = (x[keep] for x in (ep, ts, own, ps, sec, lat, win, day))
    tsec = np.ceil(ts / 1000.0).astype(np.int64)
    ss = np.clip((tsec - ep).astype(int), 0, 300)
    zup = np.array([ZT[int(e)][s] for e, s in zip(ep, ss)])
    isup = np.r_[True, (ts[1:] != ts[:-1]) | (ep[1:] != ep[:-1])]
    zs = np.where(isup, zup, -zup)
    good = np.isfinite(zs)
    days = sorted(set(day.tolist())); nd = len(days)
    starts = segs(ep); BIG = len(ep) + 10
    cap1 = np.minimum(own + 0.01, 0.99)
    f15 = (ps >= 0.5) & ((np.array([platt(p) for p in ps]) / np.array([pad_cost(a) for a in own]) - 1) >= 0.15)
    print(f'EF-14, LONDON z. rows {len(ep):,}  candles {len(starts):,}  z finite on {100*good.mean():.1f}%')
    print(f'  signed z: p10 {np.nanpercentile(zs,10):+.2f}  p50 {np.nanpercentile(zs,50):+.2f}  '
          f'p90 {np.nanpercentile(zs,90):+.2f}   |z|<0.5 on {100*np.nanmean(np.abs(zs)<0.5):.1f}%')
    zf = np.where(good, zs, 0.0)
    print(f'\n  FIRE-ONLY (fixed15 fires, then filtered) - comparable to London\'s live fills')
    print(f'  {"arm":26s}{"$tot":>8}{"DD$":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"+1c":>8}{"H1":>8}{"H2":>8}')
    show('A fixed15 as-is', fire_only(f15, zf, None, lat, cap1, own, win, day, starts, BIG), nd,
         fire_only(f15, zf, None, lat, cap1, own, win, day, starts, BIG, 0.01))
    for c_ in CUTS:
        show(f'B fire-only |z|>={c_:.2f}', fire_only(f15, zf, c_, lat, cap1, own, win, day, starts, BIG), nd,
             fire_only(f15, zf, c_, lat, cap1, own, win, day, starts, BIG, 0.01))
    print(f'  contrarian only (z <= -cut), London\'s "against" bucket:')
    for c_ in (0.5,):
        idx = np.where(f15, np.arange(len(f15)), BIG)
        fst = np.minimum.reduceat(idx, starts); fst = fst[fst < BIG]
        sel = fst[zf[fst] <= -c_]
        if len(sel):
            q = np.where(lat[sel] <= cap1[sel] + 1e-12, lat[sel], np.nan); fl = np.isfinite(q)
            pnl = STAKE * per1(win[sel][fl], q[fl])
            print(f'    z <= -{c_:.2f}: n {len(sel)} fills {int(fl.sum())} $ {pnl.sum():+.1f} '
                  f'win {100*win[sel][fl].mean():.1f}% ask {own[sel][fl].mean():.3f}')
    print(f'\n  FIRST-PASS-CLEARING-BOTH (my EF-12 order, for contrast)')
    for c_ in CUTS:
        m = f15 & good & (np.abs(zs) >= c_)
        show(f'B first-both |z|>={c_:.2f}', cell(m, lat, cap1, own, win, day, starts, BIG), nd,
             cell(m, lat, cap1, own, win, day, starts, BIG, 0.01))
