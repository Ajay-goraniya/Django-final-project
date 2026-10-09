#!/usr/bin/env python3
"""M8 copy-the-smart-wallets test - see PREREG_COPY.md. usage: copy_smart.py <wallet tape glob> <out prefix>"""
import sys, glob, gzip, json, collections, random, datetime as dt
import numpy as np
T = {}
for f in sorted(glob.glob(sys.argv[1])): T.update(json.load(gzip.open(f)))
OUT = sys.argv[2]; LAG = 2.2
day = lambda e: dt.datetime.fromtimestamp(e, dt.timezone.utc).strftime('%Y-%m-%d')
eps = sorted(int(e) for e in T)
tr_e = [e for e in eps if day(e) <= '2026-09-20']; te_e = [e for e in eps if day(e) >= '2026-09-21']
def wallet_stats(es):
    W = collections.defaultdict(lambda: [0.0, 0.0, 0, set(), []])   # pnl, notional, n, candles, per-record (ts, pnl, notional)
    for e in es:
        d = T[str(e)]; upw = d['up_won']
        for ts, isup, p, s, sd, w in d['p']:
            if sd != 'B': continue
            win = 1.0 if isup == upw else 0.0; x = W[w]; x[0] += (win - p) * s; x[1] += p * s; x[2] += 1; x[3].add(e); x[4].append((ts, (win - p) * s, p * s))
    return W
Wtr = wallet_stats(tr_e)
def smart_of(W):
    out = []
    for w, (pn, nt, n, cs, recs) in W.items():
        if n < 200 or len(cs) < 50 or nt <= 0: continue
        recs.sort(); h = len(recs) // 2
        a = sum(r[1] for r in recs[:h]) / max(1e-9, sum(r[2] for r in recs[:h])); b = sum(r[1] for r in recs[h:]) / max(1e-9, sum(r[2] for r in recs[h:]))
        if pn / nt >= 0.03 and a > 0 and b > 0: out.append(w)
    return out
SMART = smart_of(Wtr)
json.dump(sorted(SMART), open(OUT + '_smart.json', 'w'))          # sealed before the test is read
active = [w for w, x in Wtr.items() if x[2] >= 200]
def copy(ws, es):
    ws = set(ws); res = []
    for e in es:
        d = T[str(e)]; P = d['p']; upw = d['up_won']
        first = next(((ts, isup) for ts, isup, p, s, sd, w in P if sd == 'B' and w in ws and ts - e <= 279), None)
        if not first: continue
        t_act = first[0] + 1; tok = first[1]
        last = None
        for ts, isup, p, s, sd, w in P:
            if ts > t_act: break
            if isup == tok: last = p
            else: last = 1 - p
        if last is None or t_act - e > 280: continue
        c = last + 0.02; c = c + 0.07 * c * (1 - c)
        if c >= 0.99: continue
        win = tok == upw; res.append((e, (10 / c - 10) if win else -10.0))
    return res
L = []
def Pr(s=''): L.append(s); print(s)
Pr(f'M8: {len(eps)} candles; train {len(tr_e)}, test {len(te_e)}; wallets with >= 200 train BUYs: {len(active)}; SMART: {len(SMART)}')
Wte = wallet_stats(te_e)
own = [(Wte[w][0], Wte[w][1]) for w in SMART if w in Wte and Wte[w][1] > 0]
Pr(f'(a) SMART wallets own test $/1: {sum(a for a, _ in own)/max(1e-9, sum(b for _, b in own)):+.4f} over {len(own)} wallets still trading; '
   f'{sum(1 for a, b in own if a > 0)}/{len(own)} individually positive')
for nm, es in (('TRAIN (in-sample)', tr_e), ('TEST (sealed)', te_e)):
    r = copy(SMART, es); x = np.array([v for _, v in r]); byd = collections.defaultdict(float)
    for e, v in r: byd[day(e)] += v
    q = np.cumsum(x) if len(x) else np.array([0.0]); dd = float(np.max(np.maximum.accumulate(np.r_[0, q]) - np.r_[0, q]))
    eq, broke = 100.0, None
    for e, v in r:
        if eq < 10: broke = day(e); break
        eq += v
    Pr(f'{nm}: copies {len(x)}, win {100*np.mean([v > 0 for v in x]) if len(x) else 0:.1f}%, $ {q[-1]:+.1f}, per $1 {q[-1]/(10*max(1,len(x))):+.4f}, worst drop {dd:.1f}, days + {sum(v>0 for v in byd.values())}/{len(byd)}, $100 acct: {"broke "+broke if broke else f"ends {eq:.0f}"}')
    Pr('   ' + '  '.join(f'{d[5:]} {v:+.0f}' for d, v in sorted(byd.items())))
    if nm.startswith('TEST'): ours = q[-1]
random.seed(8); draws = []
for _ in range(200):
    rs = random.sample(active, min(len(SMART), len(active))) if SMART else []
    r = copy(rs, te_e); draws.append(sum(v for _, v in r))
Pr(f'NULL (200 random sets of {len(SMART)} active wallets, copied the same way on TEST): median {np.median(draws):+.1f}, p95 {np.percentile(draws,95):+.1f}; draws >= ours: {sum(d >= ours for d in draws)}/200')
open(OUT + '.txt', 'w').write('\n'.join(L) + '\n')
