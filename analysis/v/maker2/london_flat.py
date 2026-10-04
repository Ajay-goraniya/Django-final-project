#!/usr/bin/env python3
"""M13 (V, 09-30, owner: 'in what candles does fixed London lose? flat, low-vol, low-volume candles?').
London's REAL EF fills (analysis/v/combo/london_ef_real.csv) bucketed by Binance 1 s data, buckets fixed BEFORE looking:
  pre-open vol  = std of 1 s log returns over the 5 min before the open (bps)      -> terciles
  pre-open vol  = Binance 1 s volume proxy: count of seconds with a price change   -> terciles
  in-candle move = |close - open| / open (bps) and range (max-min) over the 5 min  -> terciles
Per bucket: n, win%, $ and $/1 at the real stake, first/second half $. Only the PRE-OPEN buckets could be used live;
move/range are known only after the candle and are shown to answer the owner's question, not as a rule.
usage: london_flat.py <bn json files,>"""
import sys, csv, json, collections
import numpy as np
BN = {}
for f in sys.argv[1].split(','): BN.update({int(k): v for k, v in json.load(open(f)).items()})
R = [(int(r['candle_epoch']), float(r['pnl_usd']), float(r['stake_usd'])) for r in csv.DictReader(open('analysis/v/combo/london_ef_real.csv'))]
rows = []
for e, p, st in R:
    pre = [BN.get(t) for t in range(e - 300, e)]; pre = [x for x in pre if x]
    cur = [BN.get(t) for t in range(e, e + 300)]; cur = [x for x in cur if x]
    if len(pre) < 240 or len(cur) < 240: continue
    lr = np.diff(np.log(pre))
    rows.append(dict(e=e, p=p, st=st, vol=float(np.std(lr) * 1e4), act=int(np.sum(lr != 0)),
                     move=abs(cur[-1] / cur[0] - 1) * 1e4, rng=(max(cur) - min(cur)) / cur[0] * 1e4))
print(f'M13: {len(rows)} of {len(R)} London real EF fills have Binance 1 s coverage ({len(R)-len(rows)} missing)')
half = sorted(r['e'] for r in rows)[len(rows) // 2]
for key, lab, live in (('vol', 'pre-open volatility (known at the open)', True), ('act', 'pre-open activity: seconds with a price change (known at the open)', True),
                       ('move', 'candle move |close-open| (known only AFTER)', False), ('rng', 'candle range high-low (known only AFTER)', False)):
    q1, q2 = np.percentile([r[key] for r in rows], [33.3, 66.7])
    print(f'\n{lab}: cuts {q1:.2f} / {q2:.2f}')
    for nm, f in (('LOW  (flat)', lambda v: v < q1), ('MID', lambda v: q1 <= v < q2), ('HIGH', lambda v: v >= q2)):
        s = [r for r in rows if f(r[key])]; pn = sum(r['p'] for r in s); stk = sum(r['st'] for r in s)
        a = sum(r['p'] for r in s if r['e'] < half); b = sum(r['p'] for r in s if r['e'] >= half)
        print(f'   {nm:12s} n {len(s):3d}  win {100*np.mean([r["p"] > 0 for r in s]):5.1f}%  $ {pn:+7.2f}  $/1 {pn/max(1e-9,stk):+.3f}  halves {a:+7.2f} / {b:+7.2f}')
