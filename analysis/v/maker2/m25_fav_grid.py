#!/usr/bin/env python3
"""M25 (V, 10-02) - can calm-FAV be improved? Grid FIXED before running, all 27 cells reported, nothing picked here:
band {0.55-0.90, 0.60-0.85, 0.65-0.85 base} x window {0-120, 60-180 base, 0-240} x vol cut {0.20, 0.25, 0.304 base}.
Same mechanics as M24 (real 1 Hz asks 09-11..16, first qualifying second, entry = ask 1 s later, fee, venue outcome).
A cell is only a candidate if it ALSO beats base on Zurich's forward 09-29.. recorded asks (separate test)."""
import sys, json, glob, gzip, sqlite3, collections, itertools
import numpy as np
B = collections.defaultdict(dict)
for ep, sec, au, agu, ad, agd in sqlite3.connect(sys.argv[1]).execute(
        'select epoch, sec, ask_up, age_up, ask_dn, age_dn from b1 where epoch = book_candle and sec is not null'):
    s = int(sec)
    if 0 <= s < 300: B[int(ep)][s] = (au, agu, ad, agd)
BN = {int(k): float(v) for k, v in json.load(open(sys.argv[2])).items()}
UP = {}
for f in glob.glob(sys.argv[3]):
    for k, v in json.load(gzip.open(f)).items():
        if 'up_won' in v: UP[int(k)] = v['up_won']
fee = lambda p: 0.07 * p * (1 - p)
VOL = {}
for e in B:
    raw = [BN[t] for t in range(e - 300, e) if t in BN]
    if len(raw) >= 240 and e in UP: VOL[e] = float(np.std(np.diff(np.log(raw)))) * 1e4
def run(lo, hi, a, b, vc):
    T = []
    for e in sorted(VOL):
        if VOL[e] >= vc: continue
        S = B[e]
        for s in range(a, b + 1):
            if s not in S or (s + 1) not in S: continue
            au, _, ad, _ = S[s]
            fav = 1 if (au or 0) >= (ad or 0) else 0
            x = au if fav else ad
            if x is None or not (lo <= x <= hi): continue
            nx = S[s + 1]; ask, age = (nx[0], nx[1]) if fav else (nx[2], nx[3])
            if ask is None or (age or 0) > 2000 or not (0.02 <= ask <= 0.99): break
            T.append((e, ask, (UP[e] == 1) == (fav == 1))); break
    return T
P = lambda a, w: (1 if w else 0) - a - fee(a)
print('band       window  vol<  |   n  win%   ask   pnl/$   total  halves         days+')
for (lo, hi), (a, b), vc in itertools.product([(0.55, 0.90), (0.60, 0.85), (0.65, 0.85)], [(0, 120), (60, 180), (0, 240)], [0.20, 0.25, 0.304]):
    T = run(lo, hi, a, b, vc)
    if not T: print(lo, hi, a, b, vc, 'none'); continue
    pn = [P(x, w) for _, x, w in T]; k = len(pn) // 2
    cost = sum(x + fee(x) for _, x, _ in T)
    d = collections.defaultdict(float)
    for (e, x, w), p in zip(T, pn): d[e // 86400] += p
    tag = ' <- BASE (frozen FAV)' if (lo, hi, a, b, vc) == (0.65, 0.85, 60, 180, 0.304) else ''
    print(f'{lo:.2f}-{hi:.2f} {a:3d}-{b:<3d} {vc:.3f} | {len(T):4d} {np.mean([w for *_, w in T])*100:5.1f} {np.mean([x for _, x, _ in T]):.3f} {sum(pn)/cost:+.3f} {sum(pn):+7.2f} {sum(pn[:k]):+6.2f}/{sum(pn[k:]):+6.2f} {sum(v > 0 for v in d.values())}/{len(d)}{"*" if len(T) < 60 else ""}{tag}')
