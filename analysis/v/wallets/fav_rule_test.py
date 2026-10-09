#!/usr/bin/env python3
"""Test the favourite-buyer's style as a rule on INDEPENDENT days (09-11..16 polybook 1 s, EF-8 rows, after-fill pnl incl. fill model
= same-side ask 1 s later <= ask+1c, fee-exact, venue labels). Rule (grid fixed before the run): per candle, first second in window W
where our side is the favourite (own_ask > opp_ask) with own_ask in band B, and the candle's trailing-5-min vol (at the open) in
vol tercile V (cuts from 09-11/12 only). $10 per fire. Report the WHOLE grid. usage: fav_rule_test.py <scratch>"""
import sys, numpy as np, datetime as dt
Z = np.load(sys.argv[1] + '/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in X[:, c['ep']]])
cut = np.quantile(X[np.isin(day, ['09-11', '09-12']), c['vol']], [1/3, 2/3])
TEST = ['09-13', '09-14', '09-15', '09-16']; m = np.isin(day, TEST)
Y = X[m]; dy = day[m]; order = np.lexsort((Y[:, c['sec']], Y[:, c['ep']])); Y = Y[order]; dy = dy[order]
print(f'vol cuts {cut[0]:.3f}/{cut[1]:.3f}; test days {TEST}')
print('window   band        vol    fires /day fill%  win%  paid   $@10    DD   days+  +1c    per day')
cost = lambda a: a * (1 + 0.07 * (1 - a))
for W in ((30, 60), (30, 120), (60, 180)):
    for B in ((0.65, 0.75), (0.70, 0.80), (0.65, 0.85)):
        for vn, vf in (('low', lambda v: v < cut[0]), ('mid', lambda v: cut[0] <= v < cut[1]), ('high', lambda v: v >= cut[1]), ('all', lambda v: True)):
            sel = (Y[:, c['sec']] >= W[0]) & (Y[:, c['sec']] <= W[1]) & (Y[:, c['own_ask']] > Y[:, c['opp_ask']]) & \
                  (Y[:, c['own_ask']] >= B[0]) & (Y[:, c['own_ask']] <= B[1]) & np.array([vf(v) for v in Y[:, c['vol']]])
            idx = np.where(sel)[0]; _, first = np.unique(Y[idx, c['ep']], return_index=True); f = idx[first]
            if len(f) == 0: continue
            pn = 10 * Y[f, c['pnl']]; fl = Y[f, c['fill']] > 0
            p1 = np.where(fl, 10 * (Y[f, c['win']] / np.array([cost(min(a + .01, .99)) for a in Y[f, c['paid']]]) - 1), 0)
            cum = np.cumsum(pn); dd = np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum])
            per = [pn[dy[f] == d].sum() for d in TEST]
            print(f'{W[0]:3d}-{W[1]:<3d}  {B[0]:.2f}-{B[1]:.2f}  {vn:5s} {len(f):5d} {len(f)/4:5.0f} {100*fl.mean():4.0f}  {100*Y[f[fl], c["win"]].mean() if fl.any() else 0:4.0f}  '
                  f'{Y[f[fl], c["paid"]].mean() if fl.any() else 0:.3f} {pn.sum():+7.1f} {dd:6.1f}  {sum(v > 0 for v in per)}/4 {p1.sum():+7.1f}  ' + ' '.join(f'{v:+.0f}' for v in per))
