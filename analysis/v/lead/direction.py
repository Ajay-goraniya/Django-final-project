#!/usr/bin/env python3
"""Stage-1, step 4: the question that matters for Polymarket - WHICH WAY, before the move prints.

At every 100 ms test grid point where a >= X bps spot move happens inside the next H = 1000 ms in exactly ONE
direction, score = up-model minus down-model (same model family), label = up. AUC of that = direction skill
given that a move is coming. Buckets = |spot return over the last 1 s| at t (how much of a move has ALREADY
printed): the < 1 bp bucket is 'before the move prints'. Full bucket grid, every model, per test day."""
import sys, os, json, numpy as np
from sklearn.metrics import roc_auc_score

data, out = sys.argv[1], sys.argv[2]
M = json.load(open(os.path.join(out, 'metrics.json'))); S = np.load(os.path.join(out, 'scores.npz'))
days = M['days']; OFF = 40; nm = M['names']; ir = nm.index('s_r1000')
BK = [(0, 1), (1, 2), (2, 5), (5, 1e9)]; MODELS = ['gbm', 'gbm0', 'gbmA', 'lr']
NM = {'lr': 'LR full', 'gbm': 'GBM full', 'gbm0': 'GBM null(mom 1s)', 'gbmA': 'GBM activity-only'}


def auc(y, s): return roc_auc_score(y, s) if 0 < y.sum() < len(y) else float('nan')


for X in (2, 5, 10):
    pooled = {(m, b): ([], []) for m in MODELS for b in range(len(BK))}; perday = {m: [] for m in MODELS}
    for f in M['folds']:
        k = days.index(f['test']); z = np.load(os.path.join(data, f['test'] + '.npz'))
        sl = slice(OFF, len(z['u1000']) - 10)
        u = z['u1000'][sl] >= X; d = z['d1000'][sl] >= X; one = u ^ d
        r = np.abs(np.nan_to_num(z['X'][sl, ir]))
        for m in MODELS:
            s = S[f'{k}|up|{X}|1000|{m}'] - S[f'{k}|dn|{X}|1000|{m}']
            for b, (lo, hi) in enumerate(BK):
                w = one & (r >= lo) & (r < hi)
                pooled[(m, b)][0].append(s[w]); pooled[(m, b)][1].append(u[w])
            w = one & (r < 1); perday[m].append((f['test'], auc(u[w], s[w]), int(w.sum())))
    print(f'**>= {X} bps within 1 s, exactly one direction** - direction AUC by |last-1 s spot move| at t '
          '(n = grid points; `*` < 60)\n')
    print('| model | ' + ' | '.join(f'|r1s| {lo}-{hi if hi < 1e8 else "inf"} bps' for lo, hi in BK) + ' |')
    print('|---' * (1 + len(BK)) + '|')
    for m in MODELS:
        cells = []
        for b in range(len(BK)):
            s = np.concatenate(pooled[(m, b)][0]); y = np.concatenate(pooled[(m, b)][1])
            cells.append(f'{auc(y, s):.3f} (n={len(y)}{"*" if len(y) < 60 else ""})')
        print(f'| {NM[m]} | ' + ' | '.join(cells) + ' |')
    print('\nper test day, |r1s| < 1 bp bucket (before the move prints): ' +
          '; '.join(f'{NM[m]}: ' + ' '.join(f'{a:.2f}' for _, a, _ in perday[m]) for m in ('gbm', 'gbm0')))
    n = [c for _, _, c in perday['gbm']]; print(f'(n per day {n})\n')
