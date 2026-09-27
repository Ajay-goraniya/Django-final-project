#!/usr/bin/env python3
"""Runs analysis/h1/verify.py on the one positive stage-1 claim: 'the order-flow model calls the sign of the spot
move that is still to come AFTER our order lands (t+300 ms, t+1 s] better than 1 s momentum'.
Metric per test day = AUC(full GBM) - AUC(momentum GBM) on grid points where that later move is >= Y bps.
grading() is given ONE source on purpose: the labels are Binance spot last trade, NOT the Chainlink TWAP60 the
venue settles on - so it must FAIL for any trading use; this is a Binance-predictability result only."""
import sys, os, json, numpy as np
from sklearn.metrics import roc_auc_score
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(here, '..', '..', 'h1'))
from verify import Finding

data, out = sys.argv[1], sys.argv[2]
M = json.load(open(os.path.join(out, 'metrics.json'))); S = np.load(os.path.join(out, 'scores.npz')); days = M['days']; OFF = 40
for X, Y in ((2, 2), (5, 5)):
    diff, ns, g_all, n_all = [], {}, [], []
    for f in M['folds']:
        k = days.index(f['test']); z = np.load(os.path.join(data, f['test'] + '.npz')); sl = slice(OFF, len(z['u1000']) - 10)
        aft = z['r1000'][sl] - z['r300'][sl]; w = np.abs(aft) >= Y; y = aft[w] > 0
        a = {m: roc_auc_score(y, (S[f'{k}|up|{X}|1000|{m}'] - S[f'{k}|dn|{X}|1000|{m}'])[w]) for m in ('gbm', 'gbm0')}
        diff.append(a['gbm'] - a['gbm0']); ns[f['test']] = int(w.sum()); g_all.append(a['gbm']); n_all.append(a['gbm0'])
    fnd = Finding(f'order flow calls the sign of the >= {Y} bps spot move left after +300 ms (models >= {X} bps / 1 s)')
    fnd.grading(binance_spot_last_trade={})
    fnd.sample(ns)
    fnd.halves(float(np.mean(diff[:3])), float(np.mean(diff[3:])))
    fnd.null(float(np.mean(g_all)), float(np.mean(n_all)), 'momentum-1s GBM (AUC)')
    fnd.verdict()
    print('per-day AUC gain over momentum:', np.round(diff, 3).tolist(), '\n')
