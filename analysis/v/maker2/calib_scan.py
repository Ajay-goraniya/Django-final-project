#!/usr/bin/env python3
"""M7 calibration scan with a sealed test half - see PREREG_SCAN.md. usage: calib_scan.py <scratch dir> <out prefix>"""
import sys, runpy, io, contextlib, collections, json, random, datetime as dt
import numpy as np
S, OUT = sys.argv[1], sys.argv[2]
sys.argv = ['x', '--tape', f'{S}/hist/lean*.json.gz,{S}/wallets_raw.json.gz,{S}/fresh48/fresh_tape.json.gz',
            '--bn', f'{S}/hist/bin1s_0911_0926.json,{S}/bin1s_48h.json,{S}/fresh48/bin1s_fresh.json', '--out', f'{S}/m7tmp']
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path(__file__.replace('calib_scan.py', 'strict_pfav.py'))
T, V, eps, prints, day, BN = g['T'], g['V'], g['eps'], g['prints'], g['day'], g['BN']
SS = (30, 60, 90, 120, 150, 180, 210, 240, 270)
rows = []   # (e, day, s, pbucket, mom, volr, agree, cost, win)
for e in eps:
    d = T[str(e)]; up, dn, P = prints(d, e)
    if dn is None: continue
    upwin = d['win'] == up
    v = V[e]; volr = None if v is None else (0 if v < 0.304 else 1 if v < 0.466 else 2)
    o = BN.get(e)
    uu = {}; last, j = None, 0
    for s in range(0, 271):
        while j < len(P) and P[j][0] <= s:
            a, p = P[j][1], P[j][2]; last = p if a == up else 1 - p; j += 1
        uu[s] = last
    for s in SS:
        u, u30 = uu.get(s), uu.get(s - 30)
        if u is None or u30 is None or volr is None or o is None: continue
        b = BN.get(e + s)
        if b is None: continue
        mv = (b / o - 1) * 1e4
        for side, pr, pr30, w, sgn in ((1, u, u30, upwin, 1), (0, 1 - u, 1 - u30, not upwin, -1)):
            if not (0.05 <= pr < 0.95): continue
            pb = int(pr * 20)                     # 0.05 buckets
            dm = pr - pr30; mom = 0 if dm < -0.02 else 2 if dm > 0.02 else 1
            ag = 2 if abs(mv) < 2 else (0 if mv * sgn > 0 else 1)
            c = pr + 0.02; c = c + 0.07 * c * (1 - c)
            if c >= 0.99: continue
            rows.append((e, day(e), s, pb, mom, volr, ag, c, 1 if w else 0))
R = np.array([(r[0], r[2], r[3], r[4], r[5], r[6], r[7], r[8]) for r in rows], dtype=float)
days = np.array([r[1] for r in rows])
train = days <= '2026-09-20'; test = ~train
key = lambda r: (int(r[1]), int(r[2]), int(r[3]), int(r[4]), int(r[5]))
keys = [key(r) for r in R]
pnl = lambda r, w: w / r[6] - 1.0
def select(wins):
    cell = collections.defaultdict(list)
    for i in np.where(train)[0]: cell[keys[i]].append(i)
    sel = []
    for k, idx in cell.items():
        if len(idx) < 100: continue
        idx = sorted(idx, key=lambda i: R[i][0]); x = np.array([wins[i] / R[i][6] - 1 for i in idx]); h = len(x) // 2
        if x.mean() >= 0.03 and x[:h].mean() > 0 and x[h:].mean() > 0: sel.append(k)
    return set(sel), len(cell)
def test_of(sel):
    idx = [i for i in np.where(test)[0] if keys[i] in sel]
    if not idx: return 0, 0.0, {}
    x = np.array([R[i][7] / R[i][6] - 1 for i in idx]); byd = collections.defaultdict(float)
    for i, v in zip(idx, x): byd[days[i]] += 10 * v
    return len(idx), float(x.mean()), byd
wins = R[:, 7].copy()
sel, ncell = select(wins)
json.dump(sorted(sel), open(OUT + '_selected.json', 'w'))          # sealed before looking at test
n, m, byd = test_of(sel)
L = []
def P(s=''): L.append(s); print(s)
P(f'M7 scan: {len(R)} (candle, s, side) rows; cells with train rows {ncell}; SELECTED on train {len(sel)}')
for k in sorted(sel):
    idx = [i for i in np.where(train)[0] if keys[i] == k]; x = np.array([R[i][7] / R[i][6] - 1 for i in idx])
    ti = [i for i in np.where(test)[0] if keys[i] == k]; tx = np.array([R[i][7] / R[i][6] - 1 for i in ti]) if ti else np.array([np.nan])
    P(f'  s={k[0]:3d} price {k[1]*0.05:.2f}-{k[1]*0.05+0.05:.2f} mom={["down","flat","up"][k[2]]:4s} vol={["calm","mid","high"][k[3]]:4s} binance={["agrees","disagrees","flat"][k[4]]:9s}  train n{len(x):4d} {x.mean():+.3f}/$1   TEST n{len(ti):4d} {np.nanmean(tx):+.3f}/$1')
P(f'\nTEST (sealed) pooled: n {n}, {m:+.4f} per $1, $ at $10/trade {10*m*n:+.1f}; test days positive {sum(v>0 for v in byd.values())}/{len(byd)}')
P('  per test day $: ' + '  '.join(f'{d[5:]} {v:+.0f}' for d, v in sorted(byd.items())))
# null: shuffle train labels within (s, price bucket) across candles, rerun the selection, score on the REAL test labels
random.seed(7); better = 0; draws = []
grp = collections.defaultdict(list)
for i in np.where(train)[0]: grp[(int(R[i][1]), int(R[i][2]))].append(i)
for t in range(200):
    w2 = wins.copy()
    for idx in grp.values():
        vals = [wins[i] for i in idx]; random.shuffle(vals)
        for i, v in zip(idx, vals): w2[i] = v
    s2, _ = select(w2); n2, m2, _ = test_of(s2); draws.append(10 * m2 * n2)
    if 10 * m2 * n2 >= 10 * m * n: better += 1
P(f'NULL (200 label-shuffled selections): test $ median {np.median(draws):+.1f}, p95 {np.percentile(draws,95):+.1f}; draws >= ours: {better}/200')
open(OUT + '.txt', 'w').write('\n'.join(L) + '\n')
