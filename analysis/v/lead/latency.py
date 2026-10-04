#!/usr/bin/env python3
"""Stage-1, step 5: does the direction call SURVIVE our own latency?
Signal at t (score = up-model minus down-model, trained on '>= X bps within 1 s'). Our order lands at t + L.
What we can still capture = the spot move over (t + L, t + 1000 ms] = r1000 - rL, L = 300 / 500 ms.
Grid: for moves |r1000 - rL| >= Y bps (Y = 1 / 2 / 5), AUC of the score for the sign; plus the same for the move
over (t, t + L] (what we MISS, already printed before we land). Walk-forward test days pooled; per-day for Y = 2."""
import sys, os, json, numpy as np
from sklearn.metrics import roc_auc_score

data, out = sys.argv[1], sys.argv[2]
M = json.load(open(os.path.join(out, 'metrics.json'))); S = np.load(os.path.join(out, 'scores.npz'))
days = M['days']; OFF = 40
MODELS = ['gbm', 'gbm0', 'gbmA', 'lr']
NM = {'lr': 'LR full', 'gbm': 'GBM full', 'gbm0': 'GBM null(mom 1s)', 'gbmA': 'GBM activity-only'}


def auc(y, s): return roc_auc_score(y, s) if 0 < y.sum() < len(y) else float('nan')


for X in (2, 5):
    print(f'**Score from the >= {X} bps / 1 s models.** AUC for the sign of the move AFTER we land (t+L, t+1s], '
          'and of the move we miss (t, t+L]; n = grid points\n')
    print('| model | ' + ' | '.join(f'L={L}: after, |mv|>={Y}' for L in (300, 500) for Y in (1, 2, 5)) +
          ' | L=300: missed, |mv|>=2 |'); print('|---' * 8 + '|')
    per = {}
    for m in MODELS:
        acc = {}
        for f in M['folds']:
            k = days.index(f['test']); z = np.load(os.path.join(data, f['test'] + '.npz'))
            sl = slice(OFF, len(z['u1000']) - 10)
            s = S[f'{k}|up|{X}|1000|{m}'] - S[f'{k}|dn|{X}|1000|{m}']
            for L in (300, 500):
                after = z['r1000'][sl] - z[f'r{L}'][sl]
                for Y in (1, 2, 5):
                    w = np.abs(after) >= Y; acc.setdefault((L, Y), [[], []]); acc[(L, Y)][0].append(s[w]); acc[(L, Y)][1].append(after[w] > 0)
                    if (L, Y) == (300, 2): per.setdefault(m, []).append(auc(after[w] > 0, s[w]))
            miss = z['r300'][sl]; w = np.abs(miss) >= 2
            acc.setdefault('miss', [[], []]); acc['miss'][0].append(s[w]); acc['miss'][1].append(miss[w] > 0)
        cells = []
        for key in [(L, Y) for L in (300, 500) for Y in (1, 2, 5)] + ['miss']:
            sc = np.concatenate(acc[key][0]); y = np.concatenate(acc[key][1])
            cells.append(f'{auc(y, sc):.3f} (n={len(y)}{"*" if len(y) < 60 else ""})')
        print(f'| {NM[m]} | ' + ' | '.join(cells) + ' |')
    print('\nper test day, L=300, after-move |mv|>=2: ' + '; '.join(f'{NM[m]}: ' + ' '.join(f'{a:.2f}' for a in per[m]) for m in ('gbm', 'gbm0')) + '\n')

# ---- alarms of the one-sided models (train-set thresholds): what is left to catch after we land at t+300 ms ----
RATES = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2]
print('**Alarms of the one-sided models (threshold = train flag rate), signed in the alarm direction.** '
      'cell = mean move caught (t+300, t+1s] bps / right-way >=2 bps / wrong-way >=2 bps / mean move missed (t, t+300] bps (n alarms)\n')
for X in (2, 5):
    print(f'*>= {X} bps / 1 s models*\n'); print('| model | ' + ' | '.join(f'rate {r:g}' for r in RATES) + ' |'); print('|---' * 6 + '|')
    for m in MODELS:
        cells = []
        for i in range(len(RATES)):
            cap, mis, dayv = [], [], []
            for f in M['folds']:
                k = days.index(f['test']); z = np.load(os.path.join(data, f['test'] + '.npz')); sl = slice(OFF, len(z['u1000']) - 10)
                aft = z['r1000'][sl] - z['r300'][sl]; r3 = z['r300'][sl]
                for side, sgn in (('up', 1), ('dn', -1)):
                    fl = S[f'{k}|{side}|{X}|1000|{m}'] >= f['cells'][f'{side}_{X}_1000'][m]['thr'][i]
                    cap.append(sgn * aft[fl]); mis.append(sgn * r3[fl])
            c = np.concatenate(cap); ms = np.concatenate(mis)
            cells.append(f'{c.mean():+.2f} / {(c >= 2).mean():.3f} / {(c <= -2).mean():.3f} / {ms.mean():+.2f} (n={len(c)})')
        print(f'| {NM[m]} | ' + ' | '.join(cells) + ' |')
    print('')
