#!/usr/bin/env python3
"""FAV rule improvements (V, 09-28), fixed BEFORE the run, base = low-vol favourite 0.65-0.85 in 60-180 s (the verified cell).
Variants: + TWAP agreement (side-signed z >= 0 / >= 0.5), + calm momentum (side-signed 60 s move 0..5 bp, from the wallet profile),
+ both. Same data/fill model as fav_rule_test.py (09-13..16 polybook 1 s). Whole table. usage: fav_improve.py <scratch>"""
import sys, numpy as np, datetime as dt
Z = np.load(sys.argv[1] + '/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in X[:, c['ep']]])
cut = np.quantile(X[np.isin(day, ['09-11', '09-12']), c['vol']], [1/3, 2/3])
TEST = ['09-13', '09-14', '09-15', '09-16']; m = np.isin(day, TEST); Y = X[m]; dy = day[m]
o = np.lexsort((Y[:, c['sec']], Y[:, c['ep']])); Y = Y[o]; dy = dy[o]
cost = lambda a: a * (1 + 0.07 * (1 - a))
base = (Y[:, c['sec']] >= 60) & (Y[:, c['sec']] <= 180) & (Y[:, c['own_ask']] > Y[:, c['opp_ask']]) & (Y[:, c['own_ask']] >= .65) & (Y[:, c['own_ask']] <= .85)
low = Y[:, c['vol']] < cut[0]
z = np.nan_to_num(Y[:, c['z']], nan=-9); m60 = np.nan_to_num(Y[:, c['mom60']], nan=-99)
V = {'base (low vol)': base & low, '+ z>=0': base & low & (z >= 0), '+ z>=0.5': base & low & (z >= .5),
     '+ m60 0..5bp': base & low & (m60 >= 0) & (m60 <= 5), '+ z>=0 & m60 0..5': base & low & (z >= 0) & (m60 >= 0) & (m60 <= 5),
     'all-vol + z>=0.5': base & (z >= .5), 'all-vol + z>=0.5 & m60 0..5': base & (z >= .5) & (m60 >= 0) & (m60 <= 5)}
print('variant                        fires /day fill% win%  paid   $@10    DD  days+   +1c   per day')
for k, sel in V.items():
    idx = np.where(sel)[0]; _, first = np.unique(Y[idx, c['ep']], return_index=True); f = idx[first]
    pn = 10 * Y[f, c['pnl']]; fl = Y[f, c['fill']] > 0
    p1 = np.where(fl, 10 * (Y[f, c['win']] / np.array([cost(min(a + .01, .99)) for a in Y[f, c['paid']]]) - 1), 0)
    cum = np.cumsum(pn); dd = np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]); per = [pn[dy[f] == d].sum() for d in TEST]
    print(f'{k:30s} {len(f):5d} {len(f)/4:4.0f} {100*fl.mean():4.0f} {100*Y[f[fl], c["win"]].mean():4.0f}  {Y[f[fl], c["paid"]].mean():.3f} {pn.sum():+7.1f} {dd:6.1f}  {sum(v > 0 for v in per)}/4 {p1.sum():+7.1f}  ' + ' '.join(f'{v:+.0f}' for v in per))
