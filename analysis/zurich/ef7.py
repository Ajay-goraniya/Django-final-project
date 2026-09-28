#!/usr/bin/env python3
"""EF-7 (V, 09-28 17:2x): EF-5 CAUSAL and EF-6 re-run under the STRICT threshold. READ-ONLY. Master OFF.

STRICT THRESHOLD, accepted by V after the 09-26 reconciliation: thr = the smallest DISTINCT prediction
value strictly greater than the sample quantile. A stump ensemble emits ~545 distinct values over 472k
rows, so a plain sample quantile IS one of them and `pred >= thr` fires on equality - which pass fires
was decided by ties, and that is why ef6.py (+$119.8) and the lane (-$147.9) disagreed on the same model
and the same day while sharing 221 of ~225 candles.

ANCHOR ROBUSTNESS, V's addition, fixed before any number was looked at: every EF-6 cell is run at 60 s
grid anchors of 0/15/30/45 s and reported as the MEAN over the four with the MIN and MAX $. A cell counts
only if ALL FOUR anchors beat C on $ and the mean drawdown is <= C's.

EF-5 CAUSAL TAKES NO ANCHOR. Its threshold is a single value per day, the q-quantile of the PREVIOUS
day's predictions - there is no 60 s grid to anchor, so the four anchors are identical by construction.
Reported once and labelled, rather than printed four times to look like it was tested.
"""
import sys, os, collections, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import ROWS, per1, cost, be
from ef3 import FITS, platt, pad_cost, STAKE, MIN_CELL

WS, QS6, QS5 = (1, 3, 6), (0.80, 0.90, 0.95), (0.70, 0.80, 0.90, 0.95)
ANCHORS = (0, 15, 30, 45)
G = 60_000
CACHE = '/home/ubuntu/pm_ef3/ef5_preds.npz'


def strict_thr(sorted_w, qq):
    """smallest distinct value strictly greater than the sample quantile; inf if none."""
    if len(sorted_w) < 500: return np.inf
    qv = np.quantile(sorted_w, qq)
    i = int(np.searchsorted(sorted_w, qv, side='right'))
    return float(sorted_w[i]) if i < len(sorted_w) else np.inf


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return cum, mdd, worst


def stats(sel, nd):
    fl = sorted([c for c in sel if c['q'] == c['q']], key=lambda c: c['t'])
    if not fl: return None
    seq = [STAKE * per1(c['win'], c['q']) for c in fl]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float); nb = collections.Counter()
    for c, x in zip(fl, seq): byd[c['day']] += x; nb[c['day']] += 1
    n = list(nb.values())
    den = sum(cost(c['q']) for c in fl)
    return dict(tot=tot, mdd=mdd, ratio=(tot / mdd if mdd > 0 else 99.9), n=len(sel), nf=len(fl),
                fill=len(fl) / len(sel), fpd=len(sel) / max(nd, 1), run=worst,
                pos=sum(1 for v in byd.values() if v > 0), days=len(byd),
                cv=(float(np.std(n)) / float(np.mean(n)) if n and np.mean(n) > 0 else float('inf')),
                per1=sum(per1(c['win'], c['q']) * cost(c['q']) for c in fl) / den)


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True); keep = f['keep']
    X, yw, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    yw = yw.astype(float); isup = z['is_up'][keep]; names = [str(s) for s in z['names']]
    own = X[:, names.index('own_ask')].astype(float); ps = X[:, names.index('p_side')].astype(float)
    days = sorted(set(day.tolist())); pwf = np.load(CACHE)['pwf']
    opp = {}
    for i in range(len(yw)): opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if np.isfinite(q[i]) else float('nan')
    per_day = {}
    for k, d in enumerate(days):
        if k == 0: continue
        pv = f'/tmp/ef5_pprev_{d}.npy'
        if not os.path.exists(pv): continue
        m_t = day == d; m_p = day == days[k - 1]
        tt = np.concatenate([ts[m_p], ts[m_t]]); pp = np.concatenate([np.load(pv), pwf[m_t]])
        isd = np.concatenate([np.zeros(m_p.sum(), bool), np.ones(m_t.sum(), bool)])
        o = np.argsort(tt, kind='stable')
        per_day[d] = (tt[o], pp[o], isd[o], np.where(m_t)[0], np.load(pv))
    test = sorted(per_day); nd = len(test)

    def mk(j, tday_j, idx, d):
        i = idx[j]
        return dict(t=int(ts[i]), q=float(q[i]), win=yw[i], day=d, ask=own[i],
                    oq=opp.get((int(ts[i]), int(isup[i])), float('nan')))

    def fire6(W, qq, anch):
        sel = []
        for d in test:
            tt, pp, isd, idx, _ = per_day[d]
            tday = tt[isd]; pday = pp[isd]
            t0 = (tday.min() // G) * G + anch * 1000
            grid = np.arange(t0, tday.max() + G, G)
            lo = np.searchsorted(tt, grid - W * 3600_000, 'left'); hi = np.searchsorted(tt, grid, 'left')
            thr = np.full(len(grid), np.inf)
            for i2, (a, b) in enumerate(zip(lo, hi)):
                if b - a >= 500: thr[i2] = strict_thr(np.sort(pp[a:b]), qq)
            g = np.clip(np.searchsorted(grid, tday, 'right') - 1, 0, len(grid) - 1)
            ok = pday >= thr[g]
            byc = {}
            for j in np.argsort(tday, kind='stable'):
                if not ok[j]: continue
                i = idx[j]
                if ps[i] < 0.5: continue
                e = int(ep[i])
                if e in byc: continue
                byc[e] = mk(j, tday[j], idx, d)
            sel += list(byc.values())
        return sel

    def fire5(qq):
        sel = []
        for d in test:
            tt, pp, isd, idx, prev = per_day[d]
            t = strict_thr(np.sort(prev), qq)
            tday = tt[isd]; pday = pp[isd]
            byc = {}
            for j in np.argsort(tday, kind='stable'):
                if pday[j] < t: continue
                i = idx[j]
                if ps[i] < 0.5: continue
                e = int(ep[i])
                if e in byc: continue
                byc[e] = mk(j, tday[j], idx, d)
            sel += list(byc.values())
        return sel

    C = stats([c for c in (next((c for c in l if c['p'] >= 0.5 and
        (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15), None) for l in
        (lambda: [sorted([dict(t=int(ts[i]), p=ps[i], ask=own[i], q=float(q[i]), win=yw[i], day=str(day[i]),
                              oq=opp.get((int(ts[i]), int(isup[i])), float('nan')))
                         for i in np.where((day == d))[0] if True], key=lambda c: c['t'])
                  for d in test for _ in [0]])() ) if c], nd) if False else None
    Cs = collections.defaultdict(list)
    for i in range(len(yw)):
        if str(day[i]) in test:
            Cs[int(ep[i])].append(dict(t=int(ts[i]), p=ps[i], ask=own[i], q=float(q[i]), win=yw[i],
                                       day=str(day[i]), oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
    for e in Cs: Cs[e].sort(key=lambda c: c['t'])
    C = stats([c for c in (next((c for c in l if c['p'] >= 0.5 and
              (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15), None) for l in Cs.values()) if c], nd)
    print(f'test days {test}   STRICT threshold   C fixed15: $ {C["tot"]:+.1f}  DD {C["mdd"]:.1f}  '
          f'ratio {C["ratio"]:.2f}  {C["fpd"]:.1f}/day  fill {100*C["fill"]:.1f}%  {C["pos"]}/{C["days"]} days')

    print(f'\nEF-5 CAUSAL under the strict threshold  (NO grid -> anchor-invariant by construction)')
    print(f'  {"cell":12s}{"$tot":>9}{"DD$":>7}{"P/DD":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"run":>5}{"CV":>7}{"per$1":>8}')
    for qq in QS5:
        s = stats(fire5(qq), nd)
        if s: print(f'  q={qq:.2f}      {s["tot"]:>+9.1f}{s["mdd"]:>7.1f}{s["ratio"]:>7.2f}{s["fpd"]:>7.1f}'
                    f'{100*s["fill"]:>6.1f}%{f"{s[chr(112)+chr(111)+chr(115)]}/{s[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}'
                    f'{s["run"]:>5}{s["cv"]:>7.2f}{s["per1"]:>+8.3f}')

    print(f'\nEF-6 under the strict threshold, MEAN over anchors 0/15/30/45 s, with MIN/MAX $')
    print(f'  {"cell":12s}{"$mean":>9}{"$min":>9}{"$max":>9}{"DDmean":>8}{"P/DD":>7}{"f/day":>7}{"fill%":>7}'
          f'{"days+":>7}{"CV":>7}  verdict')
    QUAL = []
    for W in WS:
        for qq in QS6:
            ss = [stats(fire6(W, qq, a), nd) for a in ANCHORS]
            ss = [s for s in ss if s]
            if not ss: continue
            tots = [s['tot'] for s in ss]
            mt, mdd = float(np.mean(tots)), float(np.mean([s['mdd'] for s in ss]))
            allbeat = all(t > C['tot'] for t in tots); ddok = mdd <= C['mdd']
            v = 'COUNTS' if (allbeat and ddok and np.mean([s['nf'] for s in ss]) >= MIN_CELL) else \
                ('all4>C, DD fails' if allbeat else 'not all 4 anchors beat C')
            if allbeat and ddok: QUAL.append((f'W={W}h q={qq:.2f}', mt, mdd))
            print(f'  W={W}h q={qq:.2f} {mt:>+9.1f}{min(tots):>+9.1f}{max(tots):>+9.1f}{mdd:>8.1f}'
                  f'{(mt/mdd if mdd>0 else 99.9):>7.2f}{np.mean([s["fpd"] for s in ss]):>7.1f}'
                  f'{100*np.mean([s["fill"] for s in ss]):>6.1f}%'
                  f'{np.mean([s["pos"] for s in ss]):>6.1f}/{ss[0]["days"]}'
                  f'{np.mean([s["cv"] for s in ss]):>7.2f}  {v}')
    print(f'\n  CELLS THAT COUNT (all four anchors beat C on $, mean DD <= C): '
          f'{[k for k, _, _ in QUAL] if QUAL else "NONE"}')
