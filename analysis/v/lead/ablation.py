#!/usr/bin/env python3
"""Stage-1, step 6: where does the direction skill come from, and is it worth anything after our latency?
ONE walk-forward split (train 09-18..09-22, test 09-23..09-25), GBM as in model.py, target >= 2 bps / 1 s up & down.
Feature groups: all | spot tape only | perp tape + basis only | basis change only | spot returns only (r100..r3000).
Score = up minus down. Reported on the test days:
  dirAUC_after: sign of the move over (t+300 ms, t+1 s] when |move| >= 2 bps (what is left after we land);
  top-alarm table (all features): the |score| top q of grid points -> mean signed move we would still catch after
  landing at t+300 ms, and share right-way / wrong-way >= 2 bps."""
import sys, os, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score

data = sys.argv[1]; OFF = 40
TR = ['2026-09-18', '2026-09-19', '2026-09-20', '2026-09-21', '2026-09-22']; TE = ['2026-09-23', '2026-09-24', '2026-09-25']
GBP = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_child_samples=300, feature_fraction=0.8,
           bagging_fraction=0.8, bagging_freq=1, lambda_l2=10, verbose=-1, num_threads=4)
rng = np.random.default_rng(7)


def load(days):
    X, u, d, r3, r10 = [], [], [], [], []
    for day in days:
        z = np.load(os.path.join(data, day + '.npz')); sl = slice(OFF, len(z['u1000']) - 10)
        X.append(np.nan_to_num(z['X'][sl])); u.append(z['u1000'][sl] >= 2); d.append(z['d1000'][sl] >= 2)
        r3.append(z['r300'][sl]); r10.append(z['r1000'][sl]); nm = [str(x) for x in z['names']]
    return np.concatenate(X), np.concatenate(u), np.concatenate(d), np.concatenate(r3), np.concatenate(r10), nm


Xtr, utr, dtr, _, _, nm = load(TR); Xte, ute, dte, r3, r10, _ = load(TE)
after = r10 - r3
G = {'all': list(range(len(nm))),
     'spot tape only': [i for i, n in enumerate(nm) if n.startswith('s_')],
     'perp tape + basis only': [i for i, n in enumerate(nm) if n.startswith(('p_', 'db'))],
     'basis change only': [i for i, n in enumerate(nm) if n.startswith('db')],
     'spot returns only': [i for i, n in enumerate(nm) if n in ('s_r100', 's_r250', 's_r500', 's_r1000', 's_r3000')]}


def fit(cols, y):
    pos = np.flatnonzero(y); neg = np.flatnonzero(~y); nn = min(len(neg), 500_000); ng = rng.choice(neg, nn, replace=False)
    sel = np.sort(np.r_[pos, ng]); w = np.where(y[sel], 1.0, len(neg) / nn)
    b = lgb.train(GBP, lgb.Dataset(Xtr[sel][:, cols], y[sel].astype(np.float32), weight=w), 200)
    return b.predict(Xte[:, cols], raw_score=True)


print('| feature group | n features | dirAUC after landing (+300 ms), |mv|>=2 | same, |mv|>=5 |'); print('|---|---|---|---|')
keep = None
for g, cols in G.items():
    s = fit(cols, utr) - fit(cols, dtr)
    w2 = np.abs(after) >= 2; w5 = np.abs(after) >= 5
    print(f'| {g} | {len(cols)} | {roc_auc_score(after[w2] > 0, s[w2]):.3f} (n={w2.sum()}) | {roc_auc_score(after[w5] > 0, s[w5]):.3f} (n={w5.sum()}) |')
    if g == 'all': keep = s
s = keep
print(f'\ncorr(score, spot r1000 at t) = {np.corrcoef(s, Xte[:, nm.index("s_r1000")])[0, 1]:+.3f};  '
      f'corr(score, perp-minus-spot 1 s: p_r1000 - s_r1000) = {np.corrcoef(s, Xte[:, nm.index("p_r1000")] - Xte[:, nm.index("s_r1000")])[0, 1]:+.3f}')
print('\n| top-|score| share (alarms/hour) | n | mean signed move caught after +300 ms (bps) | right-way >= 2 bps | wrong-way >= 2 bps | mean signed move missed in first 300 ms (bps) |')
print('|---|---|---|---|---|---|')
a = np.abs(s); sg = np.sign(s)
for q in (1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2):
    th = np.quantile(a, 1 - q); f = a >= th
    cap = sg[f] * after[f]; miss = sg[f] * r3[f]
    print(f'| {q:g} ({q * 36000:.0f}/h) | {f.sum()} | {cap.mean():+.2f} | {(cap >= 2).mean():.3f} | {(cap <= -2).mean():.3f} | {miss.mean():+.2f} |')
