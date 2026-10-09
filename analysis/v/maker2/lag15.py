#!/usr/bin/env python3
"""M9 - 15m vs 5m lag test, see PREREG_LAG15.md. usage: lag15.py <scratch dir> <out prefix>"""
import sys, runpy, io, contextlib, collections, random, math, datetime as dt, glob, gzip, json
import numpy as np
from statistics import NormalDist
N = NormalDist()
S, OUT = sys.argv[1], sys.argv[2]
sys.argv = ['x', '--tape', f'{S}/hist/lean*.json.gz,{S}/wallets_raw.json.gz,{S}/fresh48/fresh_tape.json.gz',
            '--bn', f'{S}/hist/bin1s_0911_0926.json,{S}/bin1s_48h.json,{S}/fresh48/bin1s_fresh.json', '--out', f'{S}/m9tmp']
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path(__file__.replace('lag15.py', 'strict_pfav.py'))
T5, prints, day, BN = g['T'], g['prints'], g['day'], g['BN']
T15 = {}
for f in sorted(glob.glob(f'{S}/b15/q*_*.json.gz')): T15.update(json.load(gzip.open(f)))
def upath(T, e, upto):
    d = T.get(str(e))
    if not d: return None, None
    if 'p' in d and 'win' not in d: d['win'] = 'U' if d['up_won'] else 'D'; d['up'] = 'U'
    up, dn, P = prints(d, e)
    if dn is None: return None, None
    path = {}; last, j = None, 0
    for s in range(0, upto + 1):
        while j < len(P) and P[j][0] <= s: a, p = P[j][1], P[j][2]; last = p if a == up else 1 - p; j += 1
        path[s] = last
    return path, d['win'] == up
rows = []   # (E, day, t, gap, u15, upwin15)
for Es in sorted(T15, key=int):
    E = int(Es); p15, up15 = upath(T15, E, 870)
    p5, _ = upath(T5, E + 600, 270)
    if p15 is None or p5 is None: continue
    o0, o2 = BN.get(E), BN.get(E + 600)
    r = [BN.get(t) for t in range(E + 300, E + 600)]; r = [x for x in r if x]
    if not o0 or not o2 or len(r) < 240: continue
    sig = float(np.std(np.diff(np.log(np.array(r)))) * 1e4); D = (o2 / o0 - 1) * 1e4
    for t in range(630, 871, 30):
        u15, u5 = p15.get(t), p5.get(t - 600)
        if u15 is None or u5 is None or not (0.02 < u5 < 0.98) or not (0.03 < u15 < 0.97) or sig <= 0: continue
        s = sig * math.sqrt(900 - t); fair = N.cdf(N.inv_cdf(u5) + D / s)
        rows.append((E, day(E), t, fair - u15, u15, up15))
cost = lambda pr: (lambda c: c + 0.07 * c * (1 - c))(pr + 0.02)
def trades(gthr, dayf, flip=None):
    out, seen = [], set()
    for E, d, t, gap, u15, upw in rows:
        if E in seen or not dayf(d) or abs(gap) < gthr: continue
        seen.add(E); side_up = gap > 0
        if flip is not None and flip(E): side_up = not side_up
        pr = u15 if side_up else 1 - u15; c = cost(pr)
        if c >= 0.99: continue
        out.append((E, d, (10 / c - 10) if (upw == side_up) else -10.0))
    return out
tr = lambda d: d <= '2026-09-20'; te = lambda d: d >= '2026-09-21'
L = []
def P(s=''): L.append(s); print(s)
P(f'M9: {len(rows)} (15m candle, checkpoint) rows over {len({r[0] for r in rows})} 15m candles')
best = None
for gthr in (0.03, 0.05, 0.08, 0.12):
    x = trades(gthr, tr); v = np.array([a[2] for a in x]); h = len(v) // 2
    ok = len(v) >= 60 and v[:h].sum() > 0 and v[h:].sum() > 0
    P(f'  TRAIN g={gthr:.2f}: n {len(v)}, $/1 {v.sum()/(10*max(1,len(v))):+.4f}, $ {v.sum():+.1f}, halves {v[:h].sum():+.1f}/{v[h:].sum():+.1f} {"eligible" if ok else ""}')
    if ok and (best is None or v.sum() / len(v) > best[1]): best = (gthr, v.sum() / len(v))
if not best:
    P('NO g passes the train bar -> FAIL (test not run).')
else:
    gthr = best[0]; x = trades(gthr, te); v = np.array([a[2] for a in x]); byd = collections.defaultdict(float)
    for E, d, pn in x: byd[d] += pn
    P(f'SELECTED g={gthr} (sealed). TEST: n {len(v)}, win {100*np.mean(v>0):.1f}%, $ {v.sum():+.1f}, $/1 {v.sum()/(10*len(v)):+.4f}, days + {sum(a>0 for a in byd.values())}/{len(byd)}')
    P('  ' + '  '.join(f'{d[5:]} {a:+.0f}' for d, a in sorted(byd.items())))
    random.seed(9); dr = []
    for _ in range(200):
        fl = {E: random.random() < 0.5 for E, *_ in rows}
        dr.append(sum(a[2] for a in trades(gthr, te, flip=lambda E: fl[E])))
    P(f'NULL (random side flips, each side at its own price): median {np.median(dr):+.1f}, p95 {np.percentile(dr,95):+.1f}; draws >= ours {sum(a >= v.sum() for a in dr)}/200')
open(OUT + '.txt', 'w').write('\n'.join(L) + '\n')
