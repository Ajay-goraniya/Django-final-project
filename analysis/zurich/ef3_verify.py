#!/usr/bin/env python3
"""EF-3 (5): the top 3 arms by profit/drawdown with n>=60 through verify.py, plus the per-day table.

All three came out of the same family - EF-2 v0 fired late - so the sweeps below are the honest test of
whether the (m, S) cell was picked or found: a monotone sweep is a regularity, a sweep that peaks exactly
where I stopped is the grid choosing for me.
"""
import sys, sqlite3, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef2_model import ROWS, per1, cost, be, halves, perm_opp
from ef3 import FITS, SS, MARG, platt, pad_cost, STAKE, score

z = np.load(ROWS, allow_pickle=True); f_ = np.load(FITS, allow_pickle=True)
keep = f_['keep']
X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
y = y.astype(float); isup = z['is_up'][keep]; names = [str(s) for s in z['names']]
pw = f_['pw']; wf = np.isfinite(pw)
ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
opp = {}
for i in range(len(y)): opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
C = collections.defaultdict(list)
for i in range(len(y)):
    if not wf[i]: continue
    C[int(ep[i])].append(dict(t=int(ts[i]), pe=float(X[i, ip]), pw=float(pw[i]), ask=float(X[i, ia]),
                              q=float(q[i]), win=float(y[i]), sec=int(X[i, isec]), day=str(day[i]),
                              oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
for e in C: C[e].sort(key=lambda c: c['t'])
DAYS = sorted({str(d) for d in day[wf]})

def fire(m, S):
    out = []
    for e, lst in C.items():
        c = next((c for c in lst if c['sec'] >= S and c['pw'] >= 0.5 and (c['pw'] / be(c['ask']) - 1) >= m), None)
        if c is not None: out.append(c)
    return out

def base():                                     # the live London rule on the same candles
    out = []
    for e, lst in C.items():
        c = next((c for c in lst if c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(c['ask']) - 1) >= 0.15), None)
        if c is not None: out.append(c)
    return out

def W(sel, hc=0.0):
    fl = [s for s in sel if s['q'] == s['q']]
    if not fl: return float('nan')
    qs = [min(s['q'] + hc, 0.99) for s in fl]
    return sum(per1(s['win'], b) * cost(b) for s, b in zip(fl, qs)) / sum(cost(b) for b in qs)

g = []
for p in ('/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3'):
    try:
        c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        g.append({int(e): o for e, o in c.execute(
            "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
    except Exception: g.append({})

def pnl_fn(yv, pv, price):
    fq = price[:, 0]; k = pv >= 0.5
    if k.sum() == 0: return float('nan')
    return sum(per1(a, b) * cost(b) for a, b in zip(yv[k], fq[k])) / sum(cost(b) for b in fq[k])

TOP = [(0.02, 150), (0.00, 150), (0.05, 120)]
bl = base(); passed = []
for m, S in TOP:
    sel = fire(m, S); fl = [s for s in sel if s['q'] == s['q']]
    sc = score(sel, len(DAYS))
    tup = [(s['win'], s['q'], s['t'], s['oq']) for s in sel]
    h1, h2 = halves(tup)
    nm = f'EF-2 v0 m={m:.2f} S>={S}'
    print(f'\n{"#"*78}\n# {nm}: $tot {sc["tot"]:+.1f} at ${STAKE:.0f}, worst DD ${sc["mdd"]:.1f}, '
          f'P/DD {sc["ratio"]:.2f}, {sc["fpd"]:.1f} fires/day, fill {100*sc["fill"]:.1f}%, '
          f'days+ {sc["pos"]}/{sc["days"]}, longest losing run {sc["run"]}\n{"#"*78}')
    print('  per day $ at $10:  ' + '   '.join(f'{d} {sc["byd"].get(d, 0.0):+7.1f}' for d in DAYS))
    nd = collections.Counter(s['day'] for s in fl)
    print('  per day fills:     ' + '   '.join(f'{d} {nd.get(d, 0):7d}' for d in DAYS))
    wd = {d: np.mean([s['win'] for s in fl if s['day'] == d]) for d in DAYS if nd.get(d)}
    print('  per day win%:      ' + '   '.join(f'{d} {100*wd.get(d, float("nan")):6.1f}%' for d in DAYS))
    print('  mean ask paid %.3f, mean pw %.3f' % (np.mean([s['ask'] for s in fl]), np.mean([s['pw'] for s in fl])))
    F = Finding(nm, per_fire=W(sel), n=len(fl))
    F.grading(gamma_btc5=g[0], gamma_btc5b=g[1])
    F.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms; DECISION on the quoted ask')
    F.sample({'fires': len(sel), 'filled': len(fl)})
    F.sample(dict(nd))
    F.halves(h1, h2)
    yy = np.array([s['win'] for s in fl]); qq = np.array([s['q'] for s in fl])
    pp = np.array([s['pw'] for s in fl]); aa = np.array([s['ask'] for s in fl])
    F.permutation(yy, pp, np.c_[qq, aa], pnl_fn, draws=400)
    print(f"    V's control - flip priced at the OPPOSITE real ask: p = {perm_opp(tup):.3f}")
    swS = [W(fire(m, s)) for s in SS]
    print(f'    sweep over S {SS} at m={m:.2f} -> ' + ' '.join(f'{v:+.3f}' for v in swS))
    F.sweep(swS)
    swM = [W(fire(mm, S)) for mm in MARG]
    print(f'    sweep over m {MARG} at S={S} -> ' + ' '.join(f'{v:+.3f}' for v in swM))
    F.sweep(swM)
    F.costs({h: W(sel, h) for h in (0.0, 0.005, 0.01, 0.02)})
    F.null(W(sel), W(bl), 'fixed15, the live London rule, same candles')
    mine = {s['t'] // 1000 // 300 * 300: s for s in fl}
    bmap = {b['t'] // 1000 // 300 * 300: b for b in bl if b['q'] == b['q']}
    both = sorted(set(mine) & set(bmap))
    if both: F.paired([mine[e]['win'] == 1 for e in both], [bmap[e]['win'] == 1 for e in both])
    if F.verdict(): passed.append(nm)
print('=' * 78)
print('ARMS THAT PASS EVERY GATE: ' + (', '.join(passed) if passed else 'none'))
