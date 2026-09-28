#!/usr/bin/env python3
"""verify.py on the ONE cell in EF_TRIGGER_SOURCE that meets the standing precondition (positive in BOTH
halves with n>=60): fixed15, fire only on a pass whose BOOK DID NOT MOVE. +0.177/$1 on 163 fires / 86 sim fills.

Standing rule (owner, via V): "Run verify.py on any cell that is positive in both halves with n>=60."
Nothing else in the grid qualifies - raw25's mirror arm is +0.032 with H2 negative, and every per-class cell
is under 60 fills.
"""
import sys, math, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef_persist import (load, fill, runs, fire_at_k, qual_fix, per1, cost, platt, pad_cost, be, TICK,
                        outcomes, GAMMA_DBS)
from ef_trigger_source import classify, policy_inverse
import sqlite3, datetime as dt

W = lambda y, q: (np.sum(np.array([per1(a, b) for a, b in zip(y, q)]) * np.array([cost(b) for b in q]))
                  / np.sum([cost(b) for b in q]))

def gamma_by_db():
    out = []
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.append({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: out.append({})
    return out

cand, _ = load(); classify(cand)
inv, _ = policy_inverse(cand, qual_fix)
sel = [(r, fill(r)) for r in inv.values()]
fl = sorted([(r, q) for r, q in sel if q is not None], key=lambda x: x[0]['t'])
y = np.array([r['win'] for r, _ in fl], float)
q = np.array([qq for _, qq in fl], float)
a = np.array([r['ask'] for r, _ in fl], float)
pr = np.array([r['p_raw'] for r, _ in fl], float)
real = W(y, q)
print(f'cell: fixed15, fire only when the book did not move - {len(sel)} fires, {len(fl)} sim fills, '
      f'per$1 {real:+.4f}, win {100*y.mean():.1f}%')

f = Finding('fixed15 EF fires only on a book-still pass (Zurich shadow, simulated fills)',
            per_fire=real, n=len(fl))

# 1. grading. Labels are the VENUE's own resolution (gamma outcomePrices) - the settlement rule.
ga, gb = gamma_by_db()
f.grading(gamma_btc5=ga, gamma_btc5b=gb)
print('  [info, not a gate] Binance-TWAP60 proxy vs the venue: 96.73% agreement over 2,232 epochs '
      '(MULTI_MARKET.md). The proxy is NOT used here; every label above is the venue resolution.')

# 2. quote age: the decision ask and p are the same decide_log row (same instant); the fill price is the
#    ask on the first row at >= t+250 ms, i.e. strictly after the decision.
f.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms')

# 3. sample
f.sample({'fires': len(sel), 'filled fires': len(fl)})
days = sorted({r['day'] for r, _ in fl})
f.sample({d: sum(1 for r, _ in fl if r['day'] == d) for d in days})

# 4. halves
h = len(fl) // 2
f.halves(W(y[:h], q[:h]), W(y[h:], q[h:]))

# 5. permutation: shuffle the MODEL'S p, keep outcome<->price paired, and re-apply the fixed15 bar at each
#    row's OWN ask so a shuffled p trades a DIFFERENT subset. pnl_fn genuinely depends on pred.
def pnl_fn(yy, pp, price):
    fq, ask = price[:, 0], price[:, 1]
    keep = np.array([platt(x) / pad_cost(z) - 1 >= 0.15 for x, z in zip(pp, ask)])
    if keep.sum() == 0 or np.isnan(pp).all(): return float('nan')
    return W(yy[keep], fq[keep])
f.permutation(y, pr, np.c_[q, a], pnl_fn, draws=500)

# 6. sweep: the claim is that edge falls as the book moves more. |dask| in ticks, 0 / 1 / 2 / >=3.
allq = [(r, fill(r)) for rs in cand.values() for r in runs(rs, qual_fix) if r['run'] >= 1]
allq = [(r, qq) for r, qq in allq if qq is not None and r.get('dask') is not None]
def bucket(lo, hi):
    s = [(r, qq) for r, qq in allq if lo <= round(abs(r['dask']) / TICK) <= hi]
    return (W([r['win'] for r, _ in s], [qq for _, qq in s]), len(s)) if s else (float('nan'), 0)
bs = [bucket(0, 0), bucket(1, 1), bucket(2, 2), bucket(3, 99)]
print('  sweep |dask| ticks 0/1/2/>=3 -> ' + '  '.join(f'{v:+.3f} (n={n})' for v, n in bs))
f.sweep([v for v, _ in bs])
bars = [0.10, 0.15, 0.20, 0.25, 0.30]
bv = []
for bar in bars:
    s = [(r, qq) for r, qq in fl if platt(r['p_raw']) / pad_cost(r['ask']) - 1 >= bar]
    bv.append(W([r['win'] for r, _ in s], [qq for _, qq in s]) if s else float('nan'))
print('  sweep EV bar ' + '  '.join(f'{b:.2f}:{v:+.3f}(n={sum(1 for r,_ in fl if platt(r["p_raw"])/pad_cost(r["ask"])-1>=b)})'
                                    for b, v in zip(bars, bv)))
f.sweep(bv)

# 7. costs: pay more for the same fill
f.costs({hc: W(y, np.minimum(q + hc, 0.99)) for hc in (0.0, 0.005, 0.01, 0.02)})

# 8. null: the same profile without the filter (fixed15 first qualifying pass)
base = {}
for ep, rs in cand.items():
    r = fire_at_k(rs, qual_fix, 1)
    if r is not None: base[ep] = (r, fill(r))
bfl = [(r, qq) for r, qq in base.values() if qq is not None]
f.null(real, W([r['win'] for r, _ in bfl], [qq for _, qq in bfl]), 'fixed15 unfiltered first qualifying pass')

# 9. paired, discordant candles only: my arm vs the unfiltered arm on candles BOTH fill
mine = {r['ep']: (r, qq) for r, qq in fl}
both = sorted(set(mine) & {e for e, (r, qq) in base.items() if qq is not None})
f.paired([mine[e][0]['win'] == 1 for e in both], [base[e][0]['win'] == 1 for e in both])
print(f'  paired pool: {len(both)} candles filled in both; {sum(1 for e in both if mine[e][0]["t"] != base[e][0]["t"])} '
      f'fire at a different pass')
f.verdict()
