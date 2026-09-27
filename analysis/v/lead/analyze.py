#!/usr/bin/env python3
"""Stage-1 Binance lead test, step 3: grids from model.py output (metrics.json, scores.npz) + build.py days.
Prints markdown tables to stdout.

LEAD TIME: for each spot episode (>= X bps inside 1 s, start = the last tick at the extreme), take the last
100 ms grid point at or before (start - L ms). The episode counts as FLAGGED at lead L if the matching
model (same direction, same X, H = 1000 ms) scored >= its threshold there. Threshold = train-set flag
rate; 'chance' = the realised test flag rate (what a coin with the same alarm budget would catch)."""
import sys, os, glob, json, numpy as np
from sklearn.metrics import roc_auc_score

data, out = sys.argv[1], sys.argv[2]
M = json.load(open(os.path.join(out, 'metrics.json'))); S = np.load(os.path.join(out, 'scores.npz'))
days = M['days']; RATES = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2]; OFF = 40; STEP = 100_000
Z = {d: np.load(os.path.join(data, d + '.npz')) for d in days}
folds = M['folds']; kidx = {f['test']: days.index(f['test']) for f in folds}
MODELS = ['lr', 'lr0', 'gbm', 'gbm0', 'gbmA']
NM = {'lr': 'LR full', 'lr0': 'LR null(mom 1s)', 'gbm': 'GBM full', 'gbm0': 'GBM null(mom 1s)', 'gbmA': 'GBM activity-only'}
P = print

# ---------------- AUC grid ----------------
P('### AUC (mean over 7 walk-forward test days; [min..max] across days); positives = test grid points\n')
P('| target | pos(test) | ' + ' | '.join(NM[m] for m in MODELS) + ' |'); P('|---' * (2 + len(MODELS)) + '|')
for d in ('up', 'dn'):
    for x in (2, 5, 10):
        for h in (300, 500, 1000):
            key = f'{d}_{x}_{h}'; cells = [f['cells'][key] for f in folds]
            pos = sum(c['pos_test'] for c in cells); row = [f'{d} >={x}bps in {h}ms', str(pos)]
            for m in MODELS:
                a = [c[m]['auc'] for c in cells if c.get(m) and c[m]['auc'] is not None]
                row.append('-' if not a else f'{np.mean(a):.3f} [{min(a):.2f}..{max(a):.2f}]' + ('*' if pos < 60 else ''))
            P('| ' + ' | '.join(row) + ' |')
P('\n`*` = under 60 positive test grid points: insufficient, do not read.\n')

# ---------------- precision / recall by flag rate ----------------
P('### Precision / recall by alarm budget (threshold fixed on TRAIN at that flag rate)\n')
P('flag rate 1e-4 = 3.6 alarms/hour, 3e-4 = 11/h (~1 per 5-min candle), 1e-3 = 36/h, 3e-3 = 108/h, 1e-2 = 360/h. '
  'Precision = alarm followed by the move; recall = share of positive grid points alarmed.\n')
for d in ('up', 'dn'):
    for x, h in ((5, 500), (5, 1000), (2, 1000), (10, 1000)):
        key = f'{d}_{x}_{h}'; cells = [f['cells'][key] for f in folds]
        pos = sum(c['pos_test'] for c in cells); n = sum(len(Z[f['test']]['u1000']) - OFF - 10 for f in folds)
        P(f'**{d} >= {x} bps in {h} ms** (test positives {pos}, base rate {pos / n:.5f})\n')
        P('| model | ' + ' | '.join(f'rate {r:g}: real rate / prec / recall' for r in RATES) + ' |'); P('|---' * (1 + len(RATES)) + '|')
        for m in MODELS:
            if not all(c.get(m) for c in cells): continue
            fl = np.sum([c[m]['flags'] for c in cells], 0); tp = np.sum([c[m]['tp'] for c in cells], 0)
            P(f'| {NM[m]} | ' + ' | '.join(f'{fl[i] / n:.1e} / {tp[i] / max(fl[i], 1):.3f} / {tp[i] / max(pos, 1):.3f}'
                                           for i in range(len(RATES))) + ' |')
        P('')

# ---------------- lead time ----------------
P('### Lead time: share of spot episodes already flagged L ms BEFORE the move started\n')
P('Model = same direction, same X, H = 1000 ms. Cell = flagged share / chance share (realised flag rate) ; '
  'n = episodes. Episodes pooled over the 7 test days, both directions.\n')
LEADS = [0, 100, 250, 500]
lead_rows = {}
for x in (2, 5, 10):
    for m in ('gbm', 'gbm0', 'gbmA', 'lr'):
        acc = {(L, i): [0, 0] for L in LEADS for i in range(len(RATES))}; chance = np.zeros(len(RATES)); nt = 0
        dirsc = {L: ([], []) for L in LEADS}
        for f in folds:
            k = kidx[f['test']]; z = Z[f['test']]; d0 = None
            ev = z['ev']; ev = ev[ev[:, 1] == x]
            day0 = int(np.datetime64(f['test'] + 'T00:00:00', 'us').astype(np.int64))
            su = S[f'{k}|up|{x}|1000|{m}']; sd = S[f'{k}|dn|{x}|1000|{m}']
            thu = f['cells'][f'up_{x}_1000'][m]['thr']; thd = f['cells'][f'dn_{x}_1000'][m]['thr']
            for i in range(len(RATES)):
                chance[i] += ((su >= thu[i]).sum() + (sd >= thd[i]).sum()) / 2
            nt += len(su)
            for dr, _, st, dn in ev:
                for L in LEADS:
                    r = (st - L * 1000 - day0) // STEP - OFF
                    if r < 0 or r >= len(su): continue
                    s, th = (su, thu) if dr == 1 else (sd, thd)
                    for i in range(len(RATES)):
                        acc[(L, i)][0] += int(s[r] >= th[i]); acc[(L, i)][1] += 1
                    dirsc[L][0].append(su[r] - sd[r]); dirsc[L][1].append(dr == 1)
        lead_rows[(x, m)] = (acc, chance / nt, dirsc)
for x in (2, 5, 10):
    P(f'**Episodes >= {x} bps inside 1 s**\n')
    P('| model | lead L | n | ' + ' | '.join(f'rate {r:g}' for r in RATES) + ' | direction AUC at L (up-score minus down-score) |')
    P('|---' * (4 + len(RATES)) + '|')
    for m in ('gbm', 'gbm0', 'gbmA', 'lr'):
        acc, ch, dirsc = lead_rows[(x, m)]
        for L in LEADS:
            n = acc[(L, 0)][1]
            cells = [f'{acc[(L, i)][0] / max(n, 1):.3f} / {ch[i]:.4f}' for i in range(len(RATES))]
            a, y = np.array(dirsc[L][0]), np.array(dirsc[L][1])
            dauc = roc_auc_score(y, a) if 0 < y.sum() < len(y) else float('nan')
            P(f'| {NM[m]} | {L} ms | {n}{"*" if n < 60 else ""} | ' + ' | '.join(cells) + f' | {dauc:.3f} |')
    P('')

# ---------------- direction among alarms (right way vs wrong way) ----------------
P('### Direction of what follows an alarm (5 bps, H = 1000 ms): right-way move / wrong-way move / no move\n')
P('| model | ' + ' | '.join(f'rate {r:g}' for r in RATES) + ' |'); P('|---' * (1 + len(RATES)) + '|')
for m in ('gbm', 'gbm0', 'gbmA', 'lr'):
    cnt = np.zeros((len(RATES), 3))
    for f in folds:
        k = kidx[f['test']]; z = Z[f['test']]
        u = z['u1000'][OFF:len(z['u1000']) - 10] >= 5; dn = z['d1000'][OFF:len(z['d1000']) - 10] >= 5
        for side, (s, th) in (('up', (S[f'{k}|up|5|1000|{m}'], f['cells']['up_5_1000'][m]['thr'])),
                              ('dn', (S[f'{k}|dn|5|1000|{m}'], f['cells']['dn_5_1000'][m]['thr']))):
            right, wrong = (u, dn) if side == 'up' else (dn, u)
            for i in range(len(RATES)):
                fl = s >= th[i]
                cnt[i] += [(fl & right).sum(), (fl & wrong & ~right).sum(), (fl & ~right & ~wrong).sum()]
    P(f'| {NM[m]} | ' + ' | '.join(f'{c[0] / max(c.sum(), 1):.3f} / {c[1] / max(c.sum(), 1):.3f} / {c[2] / max(c.sum(), 1):.3f} (n={int(c.sum())})' for c in cnt) + ' |')
P('')

# ---------------- per-day AUC for the headline targets ----------------
P('### Per test day (rain or sun): AUC GBM full vs GBM null, and test positives\n')
P('| test day | ' + ' | '.join(f'{d} 5bps/{h}ms' for d in ('up', 'dn') for h in (500, 1000)) + ' |'); P('|---' * 5 + '|')
for f in folds:
    row = [f['test']]
    for d in ('up', 'dn'):
        for h in (500, 1000):
            c = f['cells'][f'{d}_5_{h}']
            g = c['gbm']['auc'] if c.get('gbm') else None; g0 = c['gbm0']['auc'] if c.get('gbm0') else None
            row.append('-' if g is None else f'{g:.3f} vs {g0:.3f} (n={c["pos_test"]}{"*" if c["pos_test"] < 60 else ""})')
    P('| ' + ' | '.join(row) + ' |')
