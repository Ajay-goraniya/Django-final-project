#!/usr/bin/env python3
"""Does a NONLINEAR model (boosted trees) on price + everything beat the price alone? (V, 09-28, EF-8 rows 09-11..16)
Earlier 'X adds nothing to the price' tests were linear/logistic. UP rows, seconds 30..240 step 30 pooled with sec as a feature,
walk-forward by day (train earlier days, test the day), venue labels. Base = logistic on logit(mid) + sec interaction."""
import sys, numpy as np, datetime as dt
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score
S = sys.argv[1]; Z = np.load(f'{S}/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
U = X[(X[:, c['side']] == 1) & np.isin(X[:, c['sec']], np.arange(30, 241, 10))]
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in U[:, c['ep']]]); days = sorted(set(day))
mid = np.clip((U[:, c['own_ask']] + (1 - U[:, c['opp_ask']])) / 2, 0.005, 0.995); lg = np.log(mid / (1 - mid)); sec = U[:, c['sec']]
y = U[:, c['win']]
base = np.column_stack([lg, lg * sec / 300])
rest = [k for k in ('dist_bps', 'proj_bps', 'z', 'vol', 'mom5', 'mom15', 'mom60', 'd_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30',
                    'own_size', 'opp_size', 'age', 'spread')]
full = np.column_stack([lg, sec] + [U[:, c[k]] for k in rest])
res = {k: ([], []) for k in ('mid', 'trees_mid_only', 'trees_all')}
for d in days[2:]:
    tr = np.isin(day, [x for x in days if x < d]); te = day == d
    p0 = LogisticRegression(max_iter=500).fit(base[tr], y[tr]).predict_proba(base[te])[:, 1]
    h0 = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=200, random_state=0).fit(full[tr][:, :2], y[tr]).predict_proba(full[te][:, :2])[:, 1]
    h1 = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=200, random_state=0).fit(full[tr], y[tr]).predict_proba(full[te])[:, 1]
    for k, p in (('mid', p0), ('trees_mid_only', h0), ('trees_all', h1)):
        res[k][0].extend(p); res[k][1].extend(np.where(te)[0])
idx = np.array(res['mid'][1]); Y = y[idx]; SEC = sec[idx]
print(f'test days {days[2:]}, rows {len(idx)} (UP side, sec 30..240 step 10). log loss / AUC')
for lo, hi in ((30, 90), (100, 150), (160, 200), (210, 240), (30, 240)):
    m = (SEC >= lo) & (SEC <= hi)
    print(f'sec {lo:3d}-{hi:3d} n{m.sum():5d}  ' + '  '.join(f'{k} {log_loss(Y[m], np.array(res[k][0])[m]):.4f}/{roc_auc_score(Y[m], np.array(res[k][0])[m]):.3f}' for k in res))
