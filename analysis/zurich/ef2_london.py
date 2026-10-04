#!/usr/bin/env python3
"""What does EF-2 lose on LONDON's 35-key table? READ-ONLY, master OFF.

V, 09-28: London's final-test table has 654 attempts / 209 fills and 35 feature keys, with NO depth beyond
top and NO sub-second ask history. The exported scorer now imputes a missing feature with its training mean
(standardised zero, so it contributes nothing rather than something wrong). That is a real loss, and the
question London needs answered before it reads anything into its own scores is HOW MUCH.

So: take the SAME walk-forward fits, blank the features London does not have, and measure what happens to
AUC and to the acceptance table. If the 35-key version scores materially worse, London's run is a test of a
degraded model and has to be read as one.

ABSENT ON LONDON, from V's list:
  _ask_up, _ask_dn, _price, _venue_ok   engine internals not in the 35
  bn_line_now, bn_line_open             Binance line levels, not in the 35
  opp_ask                               London records its own side's ask, not the other side's
  dip30                                 needs a 30 s running MINIMUM of its own ask; London has ask_1s/5s/30s
                                        but not the min. Cheap for London to add - a 30 s deque - and this
                                        script measures exactly what adding it would be worth.
Everything else in the 52 is either in London's 35 or is something London must already have to form a
decision at all (own_ask, sec, p_side).
"""
import sys, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, auc, be, MARGINS
from ef2_report import Wsel, line, HDR, fire, platt, pad_cost

FITS = '/home/ubuntu/pm_ef2/ef2_fits.npz'
ABSENT = ['_ask_up', '_ask_dn', '_price', '_venue_ok', 'bn_line_now', 'bn_line_open', 'opp_ask', 'dip30']


def rescore(X, names, coef, mean, sd, blank):
    """Re-apply the fitted logistic with `blank` features held at their training mean (standardised 0)."""
    j = [names.index(k) for k in blank if k in names]
    Z = (X - mean) / sd
    Z[:, j] = 0.0
    return 1 / (1 + np.exp(-np.clip(coef[0] + Z @ coef[1:], -30, 30)))


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    y = y.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    fitted = [str(s) for s in f['fitted']]
    pw_full = f['pw']
    pw_lon = np.full(len(y), np.nan)
    for i, d in enumerate(fitted):
        te = day == d
        if te.sum() == 0: continue
        pw_lon[te] = rescore(X[te].astype(np.float64), names, f['coef'][i], f['mean'][i], f['sd'][i], ABSENT)
    sc = np.isfinite(pw_full) & np.isfinite(pw_lon)
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    tot = float(np.abs(f['coef'][:, 1:]).mean(0).sum())
    lost = float(sum(np.abs(f['coef'][:, 1:]).mean(0)[names.index(k)] for k in ABSENT if k in names))
    print(f'EF-2 on London\'s 35-key table: {len(ABSENT)} of {len(names)} features imputed, carrying '
          f'{100*lost/tot:.1f}% of the mean |coefficient| mass')
    print(f'  AUC full 52 keys {auc(y[sc], pw_full[sc]):.4f}   AUC London subset {auc(y[sc], pw_lon[sc]):.4f}   '
          f'delta {auc(y[sc], pw_lon[sc]) - auc(y[sc], pw_full[sc]):+.4f}')
    print(f'  and with dip30 ADDED BACK (the one London could cheaply compute):', end=' ')
    pw_dip = np.full(len(y), np.nan)
    for i, d in enumerate(fitted):
        te = day == d
        if te.sum() == 0: continue
        pw_dip[te] = rescore(X[te].astype(np.float64), names, f['coef'][i], f['mean'][i], f['sd'][i],
                             [k for k in ABSENT if k != 'dip30'])
    print(f'AUC {auc(y[sc], pw_dip[sc]):.4f}')

    opp = {}
    for i in np.nonzero(sc)[0]:
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    nday = len(set(day[sc].tolist()))
    for lab, pred in (('full 52 keys', pw_full), ('London 35-key subset', pw_lon), ('subset + dip30', pw_dip)):
        cands = collections.defaultdict(list)
        for i in np.nonzero(sc)[0]:
            cands[int(ep[i])].append(dict(t=int(ts[i]), p=float(pred[i]), pe=float(X[i, ip]),
                                          ask=float(X[i, ia]), q=float(q[i]), win=float(y[i]),
                                          sec=int(X[i, isec]),
                                          oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
        print(f'\n  --- {lab} ---')
        print(HDR)
        for m in MARGINS:
            line(f'EF-2 margin {m:.2f}', fire(cands, lambda c, px, m=m: c['p'] / be(px) - 1 >= m), nday)
