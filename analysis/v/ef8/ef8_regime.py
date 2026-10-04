#!/usr/bin/env python3
"""Why did 09-14 carry EF-8? Buckets DEFINED BEFORE LOOKING: trailing 5-min Binance vol (vol, known at the open) and |60 s momentum| at
the fire, tercile cut points from the TRAINING days (09-11/12) only. Every cell of the pinned q.90 fires, n<60 marked INSUF."""
import sys, numpy as np, datetime as dt
S = sys.argv[1]; Z = np.load(f'{S}/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
F = np.load(f'{S}/ef8_fired.npz')
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in X[:, c['ep']]])
tr = np.isin(day, ['09-11', '09-12'])
for v in ('vol', 'mom60'):
    base = np.abs(X[tr, c[v]]); base = base[np.isfinite(base)]; cuts = np.quantile(base, [1/3, 2/3])
    print(f'# {v}: tercile cuts (training days) {cuts[0]:.3f} / {cuts[1]:.3f}; per-day mean |{v}| over test rows:',
          ' '.join(f'{d} {np.nanmean(np.abs(X[day == d, c[v]])):.3f}' for d in ('09-13', '09-14', '09-15', '09-16')))
    for arm in ('E5_q0.90_pin=phys', 'E4_q0.90_pin=phys', 'E4_q0.80_pin=phys'):
        f = F[arm]; x = np.abs(X[f, c[v]]); b = np.digitize(x, cuts)
        cells = []
        for k, lab in enumerate(('low', 'mid', 'high')):
            m = b == k; n = m.sum(); fl = X[f[m], c['fill']] > 0
            cells.append(f'{lab} n{n}{"*" if n < 60 else ""} win {100*X[f[m][fl], c["win"]].mean() if fl.any() else float("nan"):.0f}% $ {10*X[f[m], c["pnl"]].sum():+.0f}')
        print(f'  {arm:20s} ' + ' | '.join(cells))
