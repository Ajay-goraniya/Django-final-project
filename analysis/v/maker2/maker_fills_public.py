#!/usr/bin/env python3
"""M1b (V, 09-30): do PASSIVE fills make money on BTC 5m in aggregate? Every public fill (data-api, 48 h, 576 candles), tagged maker/taker
by the takerOnly legs; per share held to settlement at the venue's (gamma) winner. Taker fee 0.07 p(1-p) on taker legs; maker rebates NOT counted.
Split maker BUY fills by price bucket and by second (ts - 2.2 s lag). usage: maker_fills_public.py <wallets_raw.json.gz>"""
import sys, json, gzip, collections
import numpy as np
D = json.load(gzip.open(sys.argv[1]))
agg = collections.defaultdict(lambda: [0.0, 0.0, 0])   # key -> [pnl$, notional$, n]
days = collections.defaultdict(lambda: collections.defaultdict(float))
for e, d in D.items():
    e = int(e); tk = set((w, tx, a, s) for w, sd, a, s, p, ts, tx in d['taker'])
    for w, sd, a, s, p, ts, tx in d['all']:
        t = (w, tx, a, s) in tk; win = 1.0 if a == d['win'] else 0.0
        pnl = (win - p) * s if sd == 'BUY' else (p - win) * s
        if t: pnl -= 0.07 * p * (1 - p) * s
        role = 'taker' if t else 'maker'
        sec = ts - 2.2 - e
        for key in [(role, sd), (role, sd, 'px', min(9, int(p * 10))), (role, sd, 'sec', min(4, max(0, int(sec // 60))))]:
            x = agg[key]; x[0] += pnl; x[1] += p * s; x[2] += 1
        days[(role, sd)][(e // 3600) // 6] += pnl
print(f'{len(D)} candles. per $1 = pnl / notional. maker rebates excluded (makers understated).')
for k in sorted(agg, key=str):
    p, v, n = agg[k]
    if len(k) == 2:
        dv = list(days[k].values())
        print(f'{str(k):40s} n{n:7d} notional {v:10.0f}  pnl {p:+9.0f}  per$1 {p/v:+.4f}   6h blocks positive {sum(x>0 for x in dv)}/{len(dv)}')
for k in sorted(agg, key=str):
    p, v, n = agg[k]
    if len(k) == 4 and k[0] == 'maker' and k[1] == 'BUY':
        print(f'   maker BUY {k[2]} {k[3]}  n{n:6d} notional {v:9.0f} per$1 {p/v:+.4f}')
