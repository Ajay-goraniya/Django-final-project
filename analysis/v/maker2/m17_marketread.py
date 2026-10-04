#!/usr/bin/env python3
"""M17 (V, 10-01) - London fixed15: does the market read INSIDE the candle, up to the fire, separate winners from flat losers?
Pre-registered in PREREG_M17_MARKETREAD.md (2463aeb) before any data was read.
usage: m17_marketread.py <fills.csv> <bn1s json files,> <tape glob>"""
import sys, csv, json, glob, gzip, random
import numpy as np
from sklearn.linear_model import LogisticRegression

SPLIT = 1790553600  # 09-28 00:00 UTC: train 09-23..27, sealed test 09-28..
FILLS = list(csv.DictReader(open(sys.argv[1])))
BN = {}
for f in sys.argv[2].split(','): BN.update({int(k): float(v) for k, v in json.load(open(f)).items()})
TP = {}
for f in glob.glob(sys.argv[3]): TP.update({int(k): v for k, v in json.load(gzip.open(f)).items()})


def series(a, b):
    return [BN[t] for t in range(a, b + 1) if t in BN]


rows, miss = [], 0
for r in FILLS:
    e = int(r['candle_epoch']); f = int(float(r['fire_ts'])); up = r['side'].upper().startswith('U')
    c = series(e, f)
    if len(c) < max(5, 0.8 * (f - e)) or e not in TP: miss += 1; continue
    d = np.diff(c); path = float(np.sum(np.abs(d)))
    chop = abs(c[-1] - c[0]) / path if path > 0 else 0.0
    act = float(np.mean(d != 0)) if len(d) else 0.0
    tok = 1 if up else 0
    pr = sorted((p[0], p[2]) for p in TP[e]['p'] if p[1] == tok and e <= p[0] < f)
    prints = len(pr)
    def last(t):
        x = [q for s, q in pr if s <= t]; return x[-1] if x else None
    a1, a0 = last(f), last(f - 30)
    agree = (a1 - a0) if (a1 is not None and a0 is not None) else 0.0
    rows.append(dict(e=e, pnl=float(r['pnl_usd']), F1=chop, F2=act, F3=prints, F4=agree))
rows.sort(key=lambda x: x['e'])
TR = [x for x in rows if x['e'] < SPLIT]; TE = [x for x in rows if x['e'] >= SPLIT]
print(f'M17: {len(rows)} London fixed15 fills with full data ({miss} missing). train {len(TR)} (09-23..27)  test {len(TE)} (09-28..)')

K = ['F1', 'F2', 'F3', 'F4']
X = lambda S: np.array([[x[k] for k in K] for x in S], float)
mu, sd = X(TR).mean(0), X(TR).std(0) + 1e-9
lr = LogisticRegression().fit((X(TR) - mu) / sd, [x['pnl'] > 0 for x in TR])
for S in (TR, TE):
    for x, p in zip(S, lr.predict_proba((X(S) - mu) / sd)[:, 1]): x['F5'] = float(p)
# F5 on TRAIN is in-sample (fitted there), so its train cells are flattered; only the TEST read counts.

def stats(S, skip):
    keep = [x for x in S if not skip(x)]; sk = [x for x in S if skip(x)]
    return dict(pnl=sum(x['pnl'] for x in keep), lost=-sum(x['pnl'] for x in keep if x['pnl'] < 0), n=len(sk),
                net=sum(x['pnl'] for x in sk), win=(np.mean([x['pnl'] > 0 for x in sk]) * 100 if sk else 0))

def null_p(S, n, net, R=4000):
    random.seed(17); P = [x['pnl'] for x in S]
    return np.mean([sum(random.sample(P, n)) <= net for _ in range(R)]) if n else 1.0

for nm, S in (('TRAIN', TR), ('TEST', TE)):
    b = stats(S, lambda x: False); print(f'{nm} baseline: PnL {b["pnl"]:+.2f}  $ lost {b["lost"]:.2f}  fires {len(S)}')
print('\nfeature cut | TRAIN: PnL  lost-cut%  skipped n net win% halves | TEST: PnL  lost-cut%  skipped n net win%  null-p | PASS')
bTR, bTE = stats(TR, lambda x: False), stats(TE, lambda x: False)
hTR = sorted(x['e'] for x in TR)[len(TR) // 2]
npass = 0
for k in K + ['F5']:
    for pc in (10, 20, 30):
        q = np.percentile([x[k] for x in TR], pc); sk = lambda x, q=q, k=k: x[k] <= q
        a, t = stats(TR, sk), stats(TE, sk)
        h1 = stats([x for x in TR if x['e'] < hTR], sk)['net']; h2 = stats([x for x in TR if x['e'] >= hTR], sk)['net']
        p = null_p(TE, t['n'], t['net'])
        cut = lambda s, b: (1 - s['lost'] / b['lost']) * 100
        ok = (cut(t, bTE) >= 5 and t['pnl'] >= bTE['pnl'] and t['net'] < 0 and h1 < 0 and h2 < 0 and t['n'] >= 60 and p < 0.05)
        npass += ok
        print(f'{k} {pc:2d}% | {a["pnl"]:+8.2f} {cut(a, bTR):+6.1f}% {a["n"]:4d} {a["net"]:+8.2f} {a["win"]:5.1f} {h1:+7.2f}/{h2:+7.2f} |'
              f' {t["pnl"]:+8.2f} {cut(t, bTE):+6.1f}% {t["n"]:4d} {t["net"]:+8.2f} {t["win"]:5.1f}  {p:.3f} | {"PASS" if ok else "fail"}')
print(f'\n{npass} of 15 cells pass every pre-registered condition.')

# descriptive: are winning candles being missed? fire rate by candle |move| tercile, all candles 09-23..
fired = {x['e'] for x in rows}
allc = []
for e in sorted(TP):
    if e < 1790121600: continue
    c = series(e, e + 299)
    if len(c) < 240: continue
    allc.append((e, abs(c[-1] / c[0] - 1) * 1e4))
if allc:
    q1, q2 = np.percentile([m for _, m in allc], [33.3, 66.7])
    print(f'\nDESCRIPTIVE: {len(allc)} candles 09-23.., |move| cuts {q1:.1f}/{q2:.1f} bps; London fired on:')
    for nm, lo, hi in (('flat third', -1, q1), ('middle', q1, q2), ('big-move third', q2, 1e9)):
        C = [e for e, m in allc if lo < m <= hi]; F = [x for x in rows if x['e'] in set(C)]
        print(f'  {nm:15s} candles {len(C):4d}  fired {len(F):3d} ({len(F)/max(1,len(C))*100:4.1f}%)  win {np.mean([x["pnl"]>0 for x in F])*100 if F else 0:5.1f}%  $ {sum(x["pnl"] for x in F):+8.2f}')
