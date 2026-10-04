#!/usr/bin/env python3
"""verify.py gates + per-day concentration for the Zurich favourite-buyer replication."""
import sys, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from verify import Finding
import fav_rule_zurich as F

base, REF, UA, DA, vo, DL, live_eps, (agree, nboth) = F.load()
n = len(REF)
eps = sorted(e for e in vo if base <= e - 300 and e - base + 300 < n and e % 300 == 0 and e not in live_eps)
vol = {}
for e in eps:
    w = REF[e-300-base:e-base]; w = w[~np.isnan(w)]
    if len(w) >= F.MIN_VOL_PTS: vol[e] = float(np.std(np.diff(np.log(w))) * 1e4)
eps = [e for e in eps if e in vol]
days = sorted({F.dayof(e) for e in eps}); CUT, TEST = days[:2], days[2:]
c1, c2 = np.quantile([vol[e] for e in eps if F.dayof(e) in CUT], [1/3, 2/3])
test = [e for e in eps if F.dayof(e) in TEST]

def fires(W, B):
    out = []
    for e in test:
        for s in range(W[0], W[1] + 1):
            i = e + s - base
            au, ad = UA[i], DA[i]
            if np.isnan(au) or np.isnan(ad) or au == ad: continue
            up = au > ad; own = max(au, ad)
            if not (B[0] <= own <= B[1]): continue
            d = DL.get(e); lt = np.nan
            if d is not None:
                j = int(np.searchsorted(d[0], (e+s)*1000 + F.DELAY_MS))
                if j < len(d[0]): lt = (d[1] if up else d[2])[j]
            if np.isnan(lt):
                k = e + s + 1 - base
                lt = (UA[k] if up else DA[k]) if 0 <= k < n else np.nan
            filled = (not np.isnan(lt)) and lt <= own + F.TICK + 1e-12
            out.append(dict(ep=e, day=F.dayof(e), vol=vol[e], up=up, own=own,
                            fill=filled, paid=float(lt) if filled else np.nan,
                            win=1.0 if vo[e] == ('UP' if up else 'DOWN') else 0.0))
            break
    return out

def per1(f, hc=0.0):
    if not f: return 0.0
    return sum((r['win'] / F.cost(min(r['paid'] + hc, .99)) - 1) for r in f if r['fill']) / len(f)

W, B = (60, 180), (0.65, 0.85)
allf = fires(W, B)
lo = [r for r in allf if r['vol'] < c1]
mi = [r for r in allf if c1 <= r['vol'] < c2]
hi = [r for r in allf if r['vol'] >= c2]
lo.sort(key=lambda r: r['ep']); h = len(lo)//2

print(f'headline cell {W[0]}-{W[1]}s, fav ask {B[0]}-{B[1]}, LOW vol   n={len(lo)}  per$1 {per1(lo):+.3f}')
print('per-day:  ' + '  '.join(f'{d} n={sum(1 for r in lo if r["day"]==d):3d} {per1([r for r in lo if r["day"]==d]):+.3f}' for d in TEST))
print()
f = Finding('Zurich replication: low-vol early favourites (60-180s, ask 0.65-0.85)',
            per_fire=per1(lo), n=len(lo))
# REAL two-source grading check. Passing vo twice would be a tautology, and grading is the one gate
# that has actually invented a fake edge here, so it gets the two independent label sources.
import sqlite3
g = {}
for p_ in F.GAMMA:
    try:
        cc = sqlite3.connect(f'file:{p_}?mode=ro', uri=True)
        g.update({int(e): str(o).upper() for e, o in cc.execute(
            "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
    except Exception: pass
aa = sqlite3.connect(f'file:{F.ARCH}?mode=ro', uri=True)
ar = {int(e): str(v).upper() for e, v in aa.execute(
    "SELECT epoch,actual FROM results WHERE actual IS NOT NULL")}
ov = [e for e in ar if e in g]
f.grading(gamma={e: g[e] for e in ov}, archive={e: ar[e] for e in ov})
print(f'(grading compared {len(ov)} candles present in BOTH sources)')
f.sample({'low': len(lo), 'mid': len(mi), 'high': len(hi)})
f.halves(per1(lo[:h]), per1(lo[h:]))
f.sweep([per1(hi), per1(mi), per1(lo)])
f.costs({0.0: per1(lo), 0.01: per1(lo, 0.01), 0.02: per1(lo, 0.02)})
f.null(per1(lo), per1(allf), 'buy every favourite (no vol filter)')
f.verdict()
