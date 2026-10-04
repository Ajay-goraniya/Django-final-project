#!/usr/bin/env python3
"""M3 (V, 09-30, owner idea: buy BOTH sides near 0.50 just before the open). As a TAKER this costs >= 1.01 (books mirror, PREOPEN_48H).
As a MAKER: rest a bid at b on UP and a bid at b on DOWN from T-W s until T+C s (T = candle start), then cancel what is unfilled.
Fill rule from the public tape (ts - 2.2 s): every print is mapped to an UP-equivalent price u (u = p on UP, 1 - p on DOWN - the venue
mint-matches the mirror). Our UP bid at b fills at the first print with u <= b (a seller accepted <= b; price priority puts our b first),
our DOWN bid at b at the first print with u >= 1 - b; the prints within that second must carry >= N shares. Hold to settlement (gamma).
PnL per candle with N shares per side: both -> N(1 - 2b); one side -> N(1 - b) if it wins else -N b. Maker fee 0, rebates NOT counted.
Grid printed in full: b x window. usage: preopen_pair.py <wallets_raw.json.gz> [N]"""
import sys, json, gzip, collections
import numpy as np
D = json.load(gzip.open(sys.argv[1])); N = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
LAG = 2.2
C = {}
for es, d in D.items():
    e = int(es); toks = {a for _, _, a, *_ in d['all']}
    up = d.get('up')
    C[e] = d
# which token is UP? gamma's clobTokenIds[0] is UP; the cache stores only the winner, so infer UP as the token whose prints pair with the
# other at ~1 - p. We take the token id order from the cache: first-seen convention is not reliable, so use the winner + outcome check below.
def run(b, W, Cc):
    res = []
    for e, d in sorted(C.items()):
        toks = sorted({a for _, _, a, *_ in d['all']})
        if len(toks) != 2: continue
        A, B = toks                     # treat A as "X" and B as "Y": the rule is symmetric, so labels do not matter
        per = collections.defaultdict(lambda: [0.0, 0.0])   # sec -> [shares with uA <= b, shares with uA >= 1-b]
        seen = set()
        for w, sd, a, s, p, ts, tx in d['all']:
            k = (tx, a, s, p)
            if k in seen: continue
            seen.add(k)
            sec = ts - LAG - e
            if not (-W <= sec <= Cc): continue
            u = p if a == A else 1 - p
            if u <= b + 1e-9: per[int(sec)][0] += s
            if u >= 1 - b - 1e-9: per[int(sec)][1] += s
        fa = any(v[0] >= N for v in per.values()); fb = any(v[1] >= N for v in per.values())
        winA = d['win'] == A
        if fa and fb: pnl = N * (1 - 2 * b); kind = 2
        elif fa: pnl = N * (1 - b) if winA else -N * b; kind = 1
        elif fb: pnl = N * (1 - b) if not winA else -N * b; kind = 1
        else: pnl = 0.0; kind = 0
        res.append((e, pnl, kind))
    return res
print(f'{len(C)} candles (48 h), N={N:.0f} shares per side, maker, rebates excluded.')
print(f"{'bid':>5s} {'window':>12s} {'both%':>6s} {'one%':>5s} {'none%':>6s} {'$tot':>8s} {'maxDD':>7s} {'P/DD':>6s} {'6h+':>5s} {'H1$':>7s} {'H2$':>7s} {'one-side $':>10s}")
for W, Cc in ((600, 0), (120, 0), (30, 0), (600, 15)):
    for b in (0.45, 0.46, 0.47, 0.48, 0.49):
        r = run(b, W, Cc); p = np.array([x[1] for x in r]); c = np.cumsum(p)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])); h = len(p) // 2
        bl = collections.defaultdict(float)
        for e, x, k in r: bl[(e - 1790000000) // 21600] += x
        k = collections.Counter(x[2] for x in r); n = len(r)
        one = sum(x[1] for x in r if x[2] == 1)
        print(f"{b:5.2f} {f'T-{W}..T+{Cc}':>12s} {100*k[2]/n:6.1f} {100*k[1]/n:5.1f} {100*k[0]/n:6.1f} {c[-1]:+8.1f} {dd:7.1f} {c[-1]/dd if dd else 0:6.2f} {sum(v>0 for v in bl.values()):2d}/{len(bl):<2d} {p[:h].sum():+7.1f} {p[h:].sum():+7.1f} {one:+10.1f}")
