#!/usr/bin/env python3
"""M19 independent period check: 09-11..09-22 (never used to build or choose M19). k=1.4 FIXED from the M19 train, m fixed grid.
usage: m19_oldperiod.py <bn1s json files,> <old tape glob>"""
import sys, json, glob, gzip, math, collections, datetime
import numpy as np
BN = {}
for f in sys.argv[1].split(','): BN.update({int(k): float(v) for k, v in json.load(open(f)).items()})
TP = {}
for f in glob.glob(sys.argv[2]):
    for k, v in json.load(gzip.open(f)).items():
        if 'p' in v and 'up_won' in v: TP[int(k)] = v
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
K = 1.4
def series(a, b):
    out, last = [], None
    for t in range(a, b + 1): last = BN.get(t, last); out.append(last)
    return out
C = []
for e in sorted(TP):
    if not (1789084800 <= e < 1790121600): continue  # 09-11 00:00 .. 09-23 00:00
    s = series(e - 300, e + 299)
    if any(x is None for x in s): continue
    lr = np.diff(np.log(s)); cur = s[300:]
    pr = {0: {}, 1: {}}
    for t, tok, p, sz in TP[e]['p']:
        sec = int(t) - e
        if 0 <= sec < 300: pr[int(tok)].setdefault(sec, []).append((p, sz))
    f = []
    for t in range(300):
        n = min(t + 1, 60); O = sum(cur[:n]) / n
        sig = float(np.std(lr[t:t + 300])) or 1e-6
        f.append(Phi(math.log(cur[t] / O) / (K * sig * math.sqrt(max(300 - t, 1)))))
    C.append(dict(e=e, up=int(TP[e]['up_won']), f=f, pr=pr))
print(f'M19 independent period 09-11..09-22: {len(C)} candles')
def run(m, lat, minsize=5):
    F = []
    for c in C:
        done = {0: False, 1: False}
        for t in range(30, 271):
            pu = c['f'][t - lat]
            for tok, pf in ((1, pu), (0, 1 - pu)):
                if done[tok]: continue
                bid = math.floor((pf - m) * 100) / 100
                if not (0.05 <= bid <= 0.90): continue
                ps = [z for p, z in c['pr'][tok].get(t, []) if p < bid - 1e-9]
                if ps and sum(ps) >= minsize:
                    won = (c['up'] == 1) == (tok == 1)
                    F.append(dict(e=c['e'], bid=bid, won=won, pnl=5 * ((1 - bid) if won else -bid), cost=5 * bid)); done[tok] = True
    return F
for m in (0.10, 0.15, 0.20, 0.25):
    for lat in (1, 2, 3):
        F = run(m, lat); h = sorted(F, key=lambda x: x['e']); k = len(h) // 2
        D = collections.defaultdict(float)
        for x in F: D[datetime.datetime.utcfromtimestamp(x['e']).strftime('%m-%d')] += x['pnl']
        pos = sum(v > 0 for v in D.values())
        print(f' m={m:.2f} lat{lat}: n {len(F):5d} win {np.mean([x["won"] for x in F])*100:5.1f}% pnl {sum(x["pnl"] for x in F):+8.2f} /$ {sum(x["pnl"] for x in F)/sum(x["cost"] for x in F):+.3f} halves {sum(x["pnl"] for x in h[:k]):+7.2f}/{sum(x["pnl"] for x in h[k:]):+7.2f} days+ {pos}/{len(D)}')
