#!/usr/bin/env python3
"""verify.py on every EF_FIRE_TIME cell that meets the standing precondition: positive in BOTH halves with
n >= 60 fills. Six qualify - the three S in {15,20,30} at P=0.55, two placebo cells, and the baseline with
the ask cap. READ-ONLY, nothing live.

Two notes on the controls, because the choice matters more than the result here:
  - verify.py's permutation shuffles the MODEL'S predictions and re-applies the rule's own bar. On these
    cells that control is WEAK BY CONSTRUCTION: 90.7% of all passes already clear p >= 0.55, so a shuffled p
    re-selects almost the same set. It is reported for completeness and should not be read as strong.
  - the control that carries the weight here is V's: a sign flip priced at the OPPOSITE side's real ask, both
    arms through the same FAK test. That p-value is printed beside each finding.
  - the null is the PLACEBO - the identical timing rule with no p condition at all. If a cell cannot beat the
    placebo, the model's confidence bar is not earning its place, whatever the other gates say.
"""
import sys, sqlite3, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef_persist import load, fill, fire_at_k, qual_fix, per1, cost, GAMMA_DBS, TICK
from ef_fire_time import augment, fire_grid, perm_opp, ASK_CAP, S_GRID

W = lambda y, q: (np.sum([per1(a, b) * cost(b) for a, b in zip(y, q)]) / np.sum([cost(b) for b in q])
                  if len(q) else float('nan'))

def gamma_by_db():
    out = []
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.append({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: out.append({})
    return out

cand, _ = load(); augment(cand)
ga, gb = gamma_by_db()

def grid_sel(S, P):
    out = []
    for ep, rs in cand.items():
        r = fire_grid(rs, S, P)
        if r is not None: out.append((r, fill(r)))
    return out

base = {}
for ep, rs in cand.items():
    r = fire_at_k(rs, qual_fix, 1)
    if r is not None: base[ep] = (r, fill(r))
base_cap = [(r, q) for r, q in base.values() if r['ask'] <= ASK_CAP]

CELLS = [('grid S=15 P=0.55', grid_sel(15, 0.55), 15, 0.55),
         ('grid S=20 P=0.55', grid_sel(20, 0.55), 20, 0.55),
         ('grid S=30 P=0.55', grid_sel(30, 0.55), 30, 0.55),
         ('placebo S=15 P=0.00', grid_sel(15, 0.00), 15, 0.00),
         ('placebo S=20 P=0.00', grid_sel(20, 0.00), 20, 0.00),
         ('baseline fixed15 + ask cap', base_cap, None, None)]

for lab, sel, S, P in CELLS:
    fl = sorted([(r, q) for r, q in sel if q is not None], key=lambda x: x[0]['t'])
    y = np.array([r['win'] for r, _ in fl], float); q = np.array([qq for _, qq in fl], float)
    pr = np.array([r['p_raw'] for r, _ in fl], float); a = np.array([r['ask'] for r, _ in fl], float)
    real = W(y, q); h = len(fl) // 2
    h1, h2 = W(y[:h], q[:h]), W(y[h:], q[h:])
    if not (h1 > 0 and h2 > 0 and len(fl) >= 60):
        print(f'SKIP {lab}: does not meet the precondition (h1 {h1:+.3f} h2 {h2:+.3f} n {len(fl)})'); continue
    po, pm = perm_opp(sel)
    print(f'\n### {lab}   per$1 {real:+.4f} on {len(fl)} fills of {len(sel)} fires')
    print(f'    V\'s control - sign flip priced at the OPPOSITE real ask: p = {po:.3f}, '
          f'flipped mean {pm:+.3f}')
    f = Finding(lab, per_fire=real, n=len(fl))
    f.grading(gamma_btc5=ga, gamma_btc5b=gb)
    f.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms')
    f.sample({'fires': len(sel), 'filled fires': len(fl)})
    f.sample({d: sum(1 for r, _ in fl if r['day'] == d) for d in sorted({r['day'] for r, _ in fl})})
    f.halves(h1, h2)

    def pnl_fn(yy, pp, price, P=P):
        fq, ask = price[:, 0], price[:, 1]
        keep = (pp >= (P or 0.0)) & (ask <= ASK_CAP)
        if keep.sum() == 0: return float('nan')
        return W(yy[keep], fq[keep])
    f.permutation(y, pr, np.c_[q, a], pnl_fn, draws=500)

    if S is not None:
        sw = []
        for SS in S_GRID:
            s2 = [(r, qq) for r, qq in grid_sel(SS, P) if qq is not None]
            sw.append(W([r['win'] for r, _ in s2], [qq for _, qq in s2]))
        print('    sweep over S ' + ' '.join(f'{SS}:{v:+.3f}' for SS, v in zip(S_GRID, sw)))
        f.sweep(sw)
    f.costs({hc: W(y, np.minimum(q + hc, 0.99)) for hc in (0.0, 0.005, 0.01, 0.02)})

    if P not in (None, 0.0):
        pl = [(r, qq) for r, qq in grid_sel(S, 0.0) if qq is not None]
        nullv = W([r['win'] for r, _ in pl], [qq for _, qq in pl])
        f.null(real, nullv, f'PLACEBO S={S} with no p bar')
    else:
        bfl = [(r, qq) for r, qq in base.values() if qq is not None]
        f.null(real, W([r['win'] for r, _ in bfl], [qq for _, qq in bfl]), 'fixed15 unfiltered')

    mine = {r['ep']: (r, qq) for r, qq in fl}
    both = sorted(set(mine) & {e for e, (r, qq) in base.items() if qq is not None})
    if both:
        f.paired([mine[e][0]['win'] == 1 for e in both], [base[e][0]['win'] == 1 for e in both])
    f.verdict()
