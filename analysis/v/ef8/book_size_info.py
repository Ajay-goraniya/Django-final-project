#!/usr/bin/env python3
"""Does Polymarket's own BOOK SIZE / quote age carry outcome information the price does not? (V, 09-28, EF-8 rows 09-11..16)
UP-side rows only (one per candle-second), sampled at fixed seconds. Walk-forward by day (train on earlier days, test on the day),
logistic: base = logit(mid) ; + size terms (log own/opp size at best ask, log ratio) ; + age. Venue-graded. Log loss and AUC."""
import sys, numpy as np, datetime as dt
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
S = sys.argv[1]; Z = np.load(f'{S}/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
U = X[X[:, c['side']] == 1]
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in U[:, c['ep']]]); days = sorted(set(day))
mid = np.clip((U[:, c['own_ask']] + (1 - U[:, c['opp_ask']])) / 2, 0.01, 0.99)
lg = np.log(mid / (1 - mid))
ls = np.log1p(np.nan_to_num(U[:, c['own_size']])); lo = np.log1p(np.nan_to_num(U[:, c['opp_size']]))
age = np.log1p(np.clip(np.nan_to_num(U[:, c['age']]), 0, 60))
sets = {'price': [lg], 'price+size': [lg, ls, lo, ls - lo, lg * (ls - lo)], 'price+size+age': [lg, ls, lo, ls - lo, lg * (ls - lo), age]}
y = U[:, c['win']]
print('sec  n_test  ' + '  '.join(f'{k:>22s}' for k in sets) + '   (log loss / AUC, walk-forward, test days ' + ','.join(days[2:]) + ')')
for sec in (15, 30, 60, 90, 120, 150, 180, 210, 240):
    m = U[:, c['sec']] == sec; out = []
    for k, cols in sets.items():
        F = np.column_stack(cols)
        P, Y = [], []
        for d in days[2:]:
            tr = m & np.isin(day, [x for x in days if x < d]); te = m & (day == d)
            if tr.sum() < 100 or te.sum() < 20: continue
            clf = LogisticRegression(C=1.0, max_iter=500).fit(F[tr], y[tr]); P += list(clf.predict_proba(F[te])[:, 1]); Y += list(y[te])
        out.append(f'{log_loss(Y, P):.4f}/{roc_auc_score(Y, P):.3f}')
    print(f'{sec:3d}  {len(Y):6d}  ' + '  '.join(f'{o:>22s}' for o in out))
