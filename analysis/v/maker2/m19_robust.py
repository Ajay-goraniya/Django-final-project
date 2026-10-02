#!/usr/bin/env python3
"""M19 robustness (post-hoc checks, NOT new selection): size-filled, latency 2/3 s, wider margins, by day. Reuses m19 data."""
import sys, io, contextlib, runpy, math, random, collections
import numpy as np
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path('analysis/v/maker2/m19_fvmaker.py', run_name='m19')
C, SPLIT = g['C'], g['SPLIT']
def run(S, m, lat=1, minsize=0.0, wmin=30, wmax=270):
    F = []
    for c in S:
        done = {0: False, 1: False}
        for t in range(max(wmin, lat), wmax + 1):
            pu = c['f'][t - lat]
            for tok, pf in ((1, pu), (0, 1 - pu)):
                if done[tok]: continue
                bid = math.floor((pf - m) * 100) / 100
                if not (0.05 <= bid <= 0.90): continue
                ps = [(p, z) for p, z in c['prints'][tok].get(t, []) if p < bid - 1e-9]
                if ps and sum(z for _, z in ps) >= minsize:
                    won = (c['up'] == 1) == (tok == 1)
                    F.append(dict(e=c['e'], bid=bid, won=won, pnl=5 * ((1 - bid) if won else -bid), cost=5 * bid)); done[tok] = True
    return F
def s(F):
    h = sorted(F, key=lambda f: f['e']); k = len(h) // 2
    return f"n {len(F):5d} win {np.mean([f['won'] for f in F])*100:5.1f}% pnl {sum(f['pnl'] for f in F):+8.2f} /$ {sum(f['pnl'] for f in F)/max(1e-9,sum(f['cost'] for f in F)):+.3f} halves {sum(f['pnl'] for f in h[:k]):+7.2f}/{sum(f['pnl'] for f in h[k:]):+7.2f}"
TR = [c for c in C if c['e'] < SPLIT]; TE = [c for c in C if c['e'] >= SPLIT]
print('SIZE CHECK: shares traded strictly below our bid in that second >= N (5 = our size)')
for m in (0.15, 0.20, 0.25):
    for ms in (0, 5, 20):
        print(f' m={m:.2f} size>={ms:3d} TRAIN', s(run(TR, m, minsize=ms)), '| TEST', s(run(TE, m, minsize=ms)))
print('LATENCY with size>=5, m=0.15/0.20')
for m in (0.15, 0.20):
    for lat in (1, 2, 3): print(f' m={m:.2f} lat {lat}s TEST', s(run(TE, m, lat=lat, minsize=5)))
B = [(0.05, .2), (.2, .35), (.35, .5), (.5, .91)]
F = run(TE, 0.15, minsize=5)
print('BY BID (m=0.15 size>=5, test):', ' | '.join(f'{lo:.2f}-{hi:.2f} ' + s([f for f in F if lo <= f['bid'] < hi]) for lo, hi in B))
