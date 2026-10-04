import sys, sqlite3, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef2_model import ROWS, per1, cost, halves, perm_opp
from ef2_v0b import Wsel, hair, SS, CAPS, platt, pad_cost
z = np.load(ROWS, allow_pickle=True)
X, y, q, ep, ts, day = z['X'], z['y'].astype(float), z['q'], z['ep'], z['ts'], z['day']
names = [str(s) for s in z['names']]; isup = z['is_up']
fin = np.all(np.isfinite(X), axis=1)
X, y, q, ep, ts, day, isup = X[fin], y[fin], q[fin], ep[fin], ts[fin], day[fin], isup[fin]
ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
opp = {}
for i in range(len(y)): opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
cands = collections.defaultdict(list)
for i in range(len(y)):
    cands[int(ep[i])].append(dict(t=int(ts[i]), pe=float(X[i, ip]), ask=float(X[i, ia]), q=float(q[i]),
                                  win=float(y[i]), sec=int(X[i, isec]), day=str(day[i]),
                                  oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
for e in cands: cands[e].sort(key=lambda c: c['t'])
def fire(S, cap):
    out = []
    for e, lst in cands.items():
        for c in lst:
            if c['pe'] >= 0.5 and c['sec'] >= S and c['ask'] <= cap: out.append(c); break
    return out
g = []
for p in ('/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3'):
    try:
        c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        g.append({int(e): o for e, o in c.execute("SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
    except Exception: g.append({})
bl = []
for e, lst in cands.items():
    for c in lst:
        if c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(c['ask']) - 1) >= 0.15: bl.append(c); break
sel = fire(15, 0.60)
fl = [s for s in sel if s['q'] == s['q']]
tup = [(s['win'], s['q'], s['t'], s['oq']) for s in sel]
h1, h2 = halves(tup)
f = Finding('v0b S=15 cap=0.60 (timing only, model picks the side)', per_fire=Wsel(sel), n=len(fl))
f.grading(gamma_btc5=g[0], gamma_btc5b=g[1])
f.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms; DECISION on the quoted ask')
f.sample({'fires': len(sel), 'filled': len(fl)})
f.sample({d: sum(1 for s in fl if s['day'] == d) for d in sorted({s['day'] for s in fl})})
f.halves(h1, h2)
yy = np.array([s['win'] for s in fl]); qq = np.array([s['q'] for s in fl])
pp = np.array([s['pe'] for s in fl]); aa = np.array([s['ask'] for s in fl])
def pnl_fn(yv, pv, price):
    fq, ask = price[:, 0], price[:, 1]
    k = pv >= 0.5
    if k.sum() == 0: return float('nan')
    return sum(per1(a_, b_) * cost(b_) for a_, b_ in zip(yv[k], fq[k])) / sum(cost(b_) for b_ in fq[k])
f.permutation(yy, pp, np.c_[qq, aa], pnl_fn, draws=400)
print(f"    V's control - flip priced at the OPPOSITE real ask: p = {perm_opp(tup):.3f}")
sw = [Wsel(fire(15, c)) for c in CAPS]
print(f'    sweep over the cap {CAPS} -> ' + ' '.join(f'{v:+.3f}' for v in sw))
f.sweep(sw)
sw2 = [Wsel(fire(S, 0.60)) for S in SS]
print(f'    sweep over S {SS} -> ' + ' '.join(f'{v:+.3f}' for v in sw2))
f.sweep(sw2)
f.costs({c: hair(sel, c) for c in (0.0, 0.01, 0.02, 0.03)})
f.null(Wsel(sel), Wsel(bl), 'fixed15 on the same 5 days')
mine = {s['t'] // 1000 // 300 * 300: s for s in fl}
bmap = {b['t'] // 1000 // 300 * 300: b for b in bl if b['q'] == b['q']}
both = sorted(set(mine) & set(bmap))
if both: f.paired([mine[e]['win'] == 1 for e in both], [bmap[e]['win'] == 1 for e in both])
f.verdict()
