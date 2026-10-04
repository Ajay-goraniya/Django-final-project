#!/usr/bin/env python3
"""verify.py on every EF-2 acceptance cell meeting the standing precondition (positive in BOTH halves,
n >= 60 fills). Two qualify: EF-2 at margin 0.02, and the S=15 placebo. READ-ONLY, master OFF.

fixed15 itself does NOT qualify - its halves are +0.277 / -0.177 - which is the first thing to say about the
comparison, because a rule whose own halves disagree is not a stable baseline to be measured against.
"""
import sys, sqlite3, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef2_model import ROWS, per1, cost, be, MARGINS, halves, perm_opp
from ef2_report import fire, platt, pad_cost, Wsel

FITS = '/home/ubuntu/pm_ef2/ef2_fits.npz'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']


def gamma():
    out = []
    for p in GAMMA_DBS:
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            out.append({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: out.append({})
    return out


z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
keep = f['keep']
X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
y = y.astype(float); isup = z['is_up'][keep]
names = [str(s) for s in z['names']]
pw = f['pw']; sc = np.isfinite(pw)
ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
opp = {}
for i in np.nonzero(sc)[0]:
    opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
cands = collections.defaultdict(list)
for i in np.nonzero(sc)[0]:
    cands[int(ep[i])].append(dict(t=int(ts[i]), p=float(pw[i]), pe=float(X[i, ip]), ask=float(X[i, ia]),
                                  q=float(q[i]), win=float(y[i]), sec=int(X[i, isec]),
                                  day=str(day[i]),
                                  oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
ga, gb = gamma()

CELLS = [('EF-2 margin 0.02', fire(cands, lambda c, px: c['p'] / be(px) - 1 >= 0.02), 0.02),
         ('S=15 placebo', fire(cands, lambda c, px: c['pe'] >= 0.5 and c['sec'] >= 15 and px <= 0.60), None)]
base = fire(cands, lambda c, px: c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(px) - 1) >= 0.15)
bfl = [b for b in base if b['q'] == b['q']]
bval = Wsel(base)

for lab, sel, marg in CELLS:
    fl = sorted([s for s in sel if s['q'] == s['q']], key=lambda s: s['t'])
    tup = [(s['win'], s['q'], s['t'], s['oq']) for s in sel]
    real = Wsel(sel); h1, h2 = halves(tup)
    print(f'\n### {lab}: {len(sel)} fires, {len(fl)} fills, per$1 {real:+.4f}, '
          f'win {100*np.mean([s["win"] for s in fl]):.1f}%')
    fd = Finding(lab, per_fire=real, n=len(fl))
    fd.grading(gamma_btc5=ga, gamma_btc5b=gb)
    fd.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms; DECISION on the quoted ask')
    fd.sample({'fires': len(sel), 'filled': len(fl)})
    fd.sample({d: sum(1 for s in fl if s['day'] == d) for d in sorted({s['day'] for s in fl})})
    fd.halves(h1, h2)

    yy = np.array([s['win'] for s in fl]); qq = np.array([s['q'] for s in fl])
    pp = np.array([s['p'] for s in fl]); aa = np.array([s['ask'] for s in fl])

    def pnl_fn(yv, pv, price, marg=marg):
        fq, ask = price[:, 0], price[:, 1]
        k = (pv / (ask * (1 + 0.07 * (1 - ask))) - 1 >= marg) if marg is not None else np.ones(len(pv), bool)
        if k.sum() == 0: return float('nan')
        num = sum(per1(a_, b_) * cost(b_) for a_, b_ in zip(yv[k], fq[k]))
        return num / sum(cost(b_) for b_ in fq[k])
    fd.permutation(yy, pp, np.c_[qq, aa], pnl_fn, draws=400)
    print(f'    V\'s control - flip priced at the OPPOSITE real ask: p = {perm_opp(tup):.3f}')

    if marg is not None:
        sw = []
        for m in MARGINS:
            s2 = [s for s in fire(cands, lambda c, px, m=m: c['p'] / be(px) - 1 >= m) if s['q'] == s['q']]
            sw.append(Wsel(s2))
        print(f'    sweep over the margin {MARGINS} -> ' + ' '.join(f'{v:+.3f}' for v in sw))
        fd.sweep(sw)
    fd.costs({h: Wsel([dict(win=s['win'], q=min(s['q'] + h, 0.99)) for s in fl]) for h in (0.0, 0.005, 0.01, 0.02)})
    fd.null(real, bval, 'fixed15 (the live London rule)')
    mine = {s['t'] // 1000 // 300 * 300: s for s in fl}
    bmap = {b['t'] // 1000 // 300 * 300: b for b in bfl}
    both = sorted(set(mine) & set(bmap))
    if both:
        fd.paired([mine[e]['win'] == 1 for e in both], [bmap[e]['win'] == 1 for e in both])
    fd.verdict()
