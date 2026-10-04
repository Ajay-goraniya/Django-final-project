#!/usr/bin/env python3
"""verify.py on the ONE spot-only disagreement cell meeting the standing precondition (positive in both
halves, n >= 60 fills): the no-imb20 specification at S=60, p_side >= 0.60 & own ask <= 0.50.

Read the provenance before the verdict. The BRIEFED specification (imb20 included) gives -0.020 on that cell
with a sign flip across its halves, so it does not qualify. The positive cell comes from a second
specification I ran on the hypothesis that imb20 was a venue-book feature rather than a spot one - and the
data refuted that hypothesis (imb20 correlates +0.200 with the venue mid, against +0.448 for spot_imb60 and
+0.981 for lv). So this cell is a specification search that survived, not a pre-registered result, and that
is the first thing that should be said about it.
"""
import sys, sqlite3, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef_persist import load, per1, cost, GAMMA_DBS, TICK
from ef_fire_time import augment
from ef_spot_only import (SPOT, fit_logistic, predict, auc, own, sim_fill, W, halves, perm_opp, SECS)

S_STAR, PT, AT = 60, 0.60, 0.50

cand, names = load(); augment(cand)
cols = [names.index(k) for k in SPOT if k != 'imb20']
days = sorted({r['day'] for rs in cand.values() for r in rs})

rows = []
for ep, rs in cand.items():
    at = [r for r in rs if r['sec'] == S_STAR]
    if not at: continue
    r = at[0]
    if r['feats'] is None or any(r['feats'][i] is None for i in cols): continue
    if not (0.01 < r['ua'] < 0.99 and 0.01 < r['da'] < 0.99): continue
    rows.append(r)
X = np.array([[r['feats'][i] for i in cols] for r in rows], float)
yUP = np.array([1.0 if (r['win'] == 1) == (r['side'] == 'UP') else 0.0 for r in rows])
dt = np.array([r['day'] for r in rows])
pred = np.full(len(rows), np.nan)
for d in days[1:]:
    tr, te = dt < d, dt == d
    if tr.sum() < 50 or te.sum() == 0: continue
    mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
    pred[te] = predict(fit_logistic((X[tr] - mu) / sd, yUP[tr]), (X[te] - mu) / sd)

def build(pt, at_):
    ent = []
    for r, p in zip(rows, pred):
        if np.isnan(p): continue
        for side in ('UP', 'DOWN'):
            ps = p if side == 'UP' else 1 - p
            a = own(r, side)
            if ps >= pt and a <= at_:
                ent.append(dict(r=r, side=side, ask=a, q=sim_fill(r, side), t=r['t'],
                                win=1 if (r['win'] == 1) == (side == r['side']) else 0,
                                day=r['day'], ep=r['ep'], p=ps))
                break
    return ent

ent = build(PT, AT)
fl = sorted([e for e in ent if e['q'] is not None], key=lambda e: e['t'])
real = W(fl); h1, h2 = halves(ent); po, pm = perm_opp(ent)
print(f'cell: spot-only WITHOUT imb20, S={S_STAR}, p>={PT} & ask<={AT}  ->  {len(ent)} candidates, '
      f'{len(fl)} sim fills, per$1 {real:+.4f}, win {100*np.mean([e["win"] for e in fl]):.1f}%')
print(f"  V's control - sign flip priced at the OPPOSITE real ask: p = {po:.3f}, flipped mean {pm:+.3f}")
print(f'  simulated fill rate {100*len(fl)/len(ent):.1f}% - the simulator was validated near London\'s REAL '
      f'31% per attempt and gives ~42% on the fixed15 baseline, so this is far outside where it was checked')

g = []
for p in GAMMA_DBS:
    try:
        c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        g.append({int(e): o for e, o in c.execute(
            "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
    except Exception: g.append({})

f = Finding(f'spot-only (no imb20) S={S_STAR} disagreement p>={PT} ask<={AT}', per_fire=real, n=len(fl))
f.grading(gamma_btc5=g[0], gamma_btc5b=g[1])
f.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms')
f.sample({'candidates': len(ent), 'filled': len(fl)})
f.sample({d: sum(1 for e in fl if e['day'] == d) for d in sorted({e['day'] for e in fl})})
f.halves(h1, h2)

y = np.array([e['win'] for e in fl], float)
q = np.array([e['q'] for e in fl], float)
pp = np.array([e['p'] for e in fl], float)
aa = np.array([e['ask'] for e in fl], float)
def pnl_fn(yy, ps, price):
    fq, ask = price[:, 0], price[:, 1]
    keep = (ps >= PT) & (ask <= AT)
    if keep.sum() == 0: return float('nan')
    return W([dict(win=a, q=b) for a, b in zip(yy[keep], fq[keep])])
f.permutation(y, pp, np.c_[q, aa], pnl_fn, draws=500)

sw = []
for pt in (0.55, 0.60, 0.65, 0.70):
    e2 = [e for e in build(pt, AT) if e['q'] is not None]
    sw.append(W(e2) if e2 else float('nan'))
print('  sweep over the p bar 0.55/0.60/0.65/0.70 -> ' + ' '.join(f'{v:+.3f}' for v in sw))
f.sweep(sw)
f.costs({hc: W([dict(win=a, q=min(b + hc, 0.99)) for a, b in zip(y, q)]) for hc in (0.0, 0.005, 0.01, 0.02)})

brief = [e for e in ent if e['q'] is not None]
allcols = [names.index(k) for k in SPOT]
X2 = np.array([[r['feats'][i] for i in allcols] for r in rows], float)
pred2 = np.full(len(rows), np.nan)
for d in days[1:]:
    tr, te = dt < d, dt == d
    if tr.sum() < 50 or te.sum() == 0: continue
    mu, sd = X2[tr].mean(0), X2[tr].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
    pred2[te] = predict(fit_logistic((X2[tr] - mu) / sd, yUP[tr]), (X2[te] - mu) / sd)
saved = pred.copy(); pred[:] = pred2
e_brief = [e for e in build(PT, AT) if e['q'] is not None]
pred[:] = saved
f.null(real, W(e_brief), 'the BRIEFED specification, imb20 included')
f.verdict()
