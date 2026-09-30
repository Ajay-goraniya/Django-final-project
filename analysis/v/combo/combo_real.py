#!/usr/bin/env python3
"""COMBO_PREREG.md test on real data: London REAL EF fills (scaled to $10 via pnl/stake) + Zurich FAV-family per-candle
(arrival +500 ms, $10). Common window only. Singles at $10, pairs at $5+$5 (= 0.5 each). Per-candle cumulative curve."""
import csv, numpy as np, datetime as dt, collections as C
L = {}
for r in csv.DictReader(open('analysis/v/combo/london_ef_real.csv')):
    e = int(r['candle_epoch']); L[e] = L.get(e, 0) + 10 * float(r['pnl_usd']) / float(r['stake_usd'])
Z = C.defaultdict(dict)
for r in csv.DictReader(open('analysis/zurich/fav_percandle.csv')):
    Z[r['arm']][int(r['candle_epoch'])] = float(r['pnl_usd_at10'])
allz = [e for a in Z for e in Z[a]]
lo = max(min(L), min(allz)); hi = min(max(L), max(allz))
arms = {'LDN_fixed15': {e: v for e, v in L.items() if lo <= e <= hi}}
for a in ('FAV', 'FAV_ref', 'FAV_mid', 'FAV_all'):
    arms[a] = {e: v for e, v in Z[a].items() if lo <= e <= hi}
f = lambda e: dt.datetime.utcfromtimestamp(e).strftime('%m-%d %H:%M')
print(f'common window {f(lo)} .. {f(hi)} UTC')
days = sorted({dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in range(lo, hi + 1, 300)})
def stats(curve):
    es = sorted(curve); pn = np.array([curve[e] for e in es])
    cum = np.cumsum(pn); dd = np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum])
    mid = (lo + hi) / 2; h1 = sum(curve[e] for e in es if e < mid); h2 = pn.sum() - h1
    per = [sum(v for e, v in curve.items() if dt.datetime.utcfromtimestamp(e).strftime('%m-%d') == d) for d in days]
    return pn.sum(), dd, h1, h2, per
def hourly(c):
    h = C.defaultdict(float)
    for e, v in c.items(): h[e // 3600] += v
    return h
print(f'\n{"arm / pair":24s} {"trades":>6s} {"$":>8s} {"maxDD":>7s} {"P/DD":>5s} {"days+":>6s} {"H1$":>8s} {"H2$":>8s}  corr   per day ' + ' '.join(days))
res = {}
for a, c in arms.items():
    s, dd, h1, h2, per = stats(c); res[a] = s / dd if dd else 0
    print(f'{a:24s} {len(c):6d} {s:+8.2f} {dd:7.2f} {s/dd if dd else 0:5.2f} {sum(p>0 for p in per)}/{len(per):<4d} {h1:+8.2f} {h2:+8.2f}   --   ' + ' '.join(f'{p:+.0f}' for p in per))
names = list(arms)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = names[i], names[j]
        c = C.defaultdict(float)
        for e, v in arms[a].items(): c[e] += 0.5 * v
        for e, v in arms[b].items(): c[e] += 0.5 * v
        s, dd, h1, h2, per = stats(c)
        ha, hb = hourly(arms[a]), hourly(arms[b]); hs = sorted(set(ha) | set(hb))
        corr = np.corrcoef([ha.get(h, 0) for h in hs], [hb.get(h, 0) for h in hs])[0, 1]
        beats = 'yes' if dd and s / dd > max(res[a], res[b]) else 'no'
        print(f'{a+"+"+b:24s} {len(c):6d} {s:+8.2f} {dd:7.2f} {s/dd if dd else 0:5.2f} {sum(p>0 for p in per)}/{len(per):<4d} {h1:+8.2f} {h2:+8.2f} {corr:+.2f}  ' + ' '.join(f'{p:+.0f}' for p in per) + f'  beats-both:{beats}')
