#!/usr/bin/env python3
"""FAV_mid loss anatomy per PREREG.md, on INDEPENDENT days 09-13..16 (EF-8 rows: polybook 1 s, after-fill pnl incl.
fill model, fee-exact, venue labels). Vol cuts from 09-11/12 only (as in fav_rule_test.py). Every bucket of every
feature is printed, with H1/H2. usage: favmid_anatomy.py <scratch>"""
import sys, numpy as np, datetime as dt
Z = np.load(sys.argv[1] + '/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in X[:, c['ep']]])
cut = np.quantile(X[np.isin(day, ['09-11', '09-12']), c['vol']], [1/3, 2/3])
TEST = ['09-13', '09-14', '09-15', '09-16']; m = np.isin(day, TEST)
Y = X[m]; dy = day[m]; o = np.lexsort((Y[:, c['sec']], Y[:, c['ep']])); Y = Y[o]; dy = dy[o]
v = Y[:, c['vol']]
sel = (Y[:, c['sec']] >= 60) & (Y[:, c['sec']] <= 180) & (Y[:, c['own_ask']] > Y[:, c['opp_ask']]) & \
      (Y[:, c['own_ask']] >= .65) & (Y[:, c['own_ask']] <= .85) & (v >= cut[0]) & (v < cut[1])
idx = np.where(sel)[0]; _, first = np.unique(Y[idx, c['ep']], return_index=True); f = idx[first]
F = Y[f]; fl = F[:, c['fill']] > 0; pn = 10 * F[:, c['pnl']]; win = F[:, c['win']] > 0
eps = F[:, c['ep']]; h1 = eps < np.median(eps)
print(f'vol cuts {cut[0]:.3f}/{cut[1]:.3f}  test {TEST}  FAV_mid decisions {len(f)}  fills {fl.sum()}  wins {(win&fl).sum()}  '
      f'$@10 {pn.sum():+.2f}  per-fill {pn[fl].sum()/max(fl.sum(),1):+.3f}')
cum = np.cumsum(pn); print(f'maxDD {np.max(np.maximum.accumulate(np.r_[0,cum])-np.r_[0,cum]):.2f}  H1 {pn[h1].sum():+.2f}  H2 {pn[~h1].sum():+.2f}')
# sanity: is z signed to our side? winners must have higher z
print(f'sanity z: winners mean {F[fl&win, c["z"]].mean():+.2f}  losers mean {F[fl&~win, c["z"]].mean():+.2f}')
d30 = F[:, c['d_ask_30s']]
feats = [
 ('F1 ask', F[:, c['own_ask']], [(.65, .70), (.70, .75), (.75, .80), (.80, .8501)]),
 ('F2 sec', F[:, c['sec']], [(60, 90), (90, 120), (120, 181)]),
 ('F3 z', F[:, c['z']], [(-99, 0), (0, .5), (.5, 1), (1, 99)]),
 ('F4 mom15', F[:, c['mom15']], [(-1e9, 0), (0, 1e9)]),
 ('F5 d_ask_30s', d30, [(-9, -1e-9), (-1e-9, 1e-9), (1e-9, 9)]),
 ('F6 own-opp size', F[:, c['own_size']] - F[:, c['opp_size']], [(-1e12, 0), (0, 1e12)]),
 ('F7 spread', F[:, c['spread']], [(-1, .01001), (.01001, 9)]),
]
print('\nfeature          bucket              dec fills win%    $@10  per-fill    H1$     H2$')
for name, x, bs in feats:
    for lo, hi in bs:
        b = (x >= lo) & (x < hi); bf = b & fl
        print(f'{name:16s} [{lo:>9.3g},{hi:>9.3g}) {b.sum():5d} {bf.sum():5d} {100*win[bf].mean() if bf.any() else 0:4.0f} '
              f'{pn[b].sum():+8.2f} {pn[bf].sum()/max(bf.sum(),1):+8.3f} {pn[b&h1].sum():+7.2f} {pn[b&~h1].sum():+7.2f}' +
              ('   INSUFFICIENT' if bf.sum() < 60 else ''))
    print()
L = np.where(fl & ~win)[0]; L = L[np.argsort(pn[L])][:10]
print('10 worst losers: time  ask  sec  z  mom15  d_ask_30s')
for i in L:
    print(f'  {dt.datetime.utcfromtimestamp(eps[i]).strftime("%m-%d %H:%M")}  {F[i,c["own_ask"]]:.2f} {F[i,c["sec"]]:4.0f} {F[i,c["z"]]:+.2f} {F[i,c["mom15"]]:+.1f} {d30[i]:+.3f}')
