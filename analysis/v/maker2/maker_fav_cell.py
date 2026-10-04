#!/usr/bin/env python3
"""M1c (V, 09-30): stability of the passive favourite buy (maker BUY at price 0.60-0.80) - per 6 h block, per second bucket,
per price tenth, vs taker BUY in the same band; share of the cell held by the top-10 maker wallets (is it one bot's skill?).
usage: maker_fav_cell.py <wallets_raw.json.gz>"""
import sys, json, gzip, collections
D = json.load(gzip.open(sys.argv[1]))
blk = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0, 0]))
sec = collections.defaultdict(lambda: [0.0, 0.0, 0]); wal = collections.defaultdict(lambda: [0.0, 0.0])
for e, d in D.items():
    e = int(e); tk = set((w, tx, a, s) for w, sd, a, s, p, ts, tx in d['taker'])
    for w, sd, a, s, p, ts, tx in d['all']:
        if sd != 'BUY' or not (0.60 <= p < 0.80): continue
        t = (w, tx, a, s) in tk; win = 1.0 if a == d['win'] else 0.0
        pnl = (win - p) * s - (0.07 * p * (1 - p) * s if t else 0.0)
        role = 'taker' if t else 'maker'
        b = blk[role][(e - 1790000000) // 21600]; b[0] += pnl; b[1] += p * s; b[2] += 1
        if not t:
            x = sec[min(9, max(0, int((ts - 2.2 - e) // 30)))]; x[0] += pnl; x[1] += p * s; x[2] += 1
            wal[w][0] += pnl; wal[w][1] += p * s
for role in ('maker', 'taker'):
    print(role, 'BUY 0.60-0.80 per 6 h block (per $1, notional $):')
    print('   ' + '  '.join(f'{b[0]/b[1]:+.3f}/{b[1]/1e3:.0f}k' for k, b in sorted(blk[role].items())))
print('maker BUY 0.60-0.80 by 30 s bucket of the candle:')
print('   ' + '  '.join(f'{k*30}s {x[0]/x[1]:+.3f}' for k, x in sorted(sec.items())))
tot = sum(v[1] for v in wal.values()); top = sorted(wal.items(), key=lambda t: -t[1][1])[:10]
print(f'makers in the cell: {len(wal)} wallets; top-10 by notional hold {100*sum(v[1] for _, v in top)/tot:.0f}% of notional')
for w, (p, v) in top: print(f'   {w[:10]} notional {v:8.0f} per$1 {p/v:+.4f}')
rest = [(p, v) for w, (p, v) in wal.items() if w not in dict(top)]
print(f'   all OTHER makers: per$1 {sum(p for p, _ in rest)/sum(v for _, v in rest):+.4f} on {sum(v for _, v in rest):.0f}')
