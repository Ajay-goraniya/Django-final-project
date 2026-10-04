#!/usr/bin/env python3
"""M2 PASSIVE FAV vs TAKER FAV on the public tape - see PREREG.md (pre-registered before running).
usage: passive_fav.py <wallets_raw.json.gz> <binance 1 s json {epoch_s: price}>"""
import sys, json, gzip, collections
import numpy as np
D = json.load(gzip.open(sys.argv[1])); BN = {int(k): v for k, v in json.load(open(sys.argv[2])).items()}
import os
LAG, S0, S1, LO, HI = 2.2, 60, 180, 0.60, 0.80
SH = float(os.environ.get("SH", "14"))   # shares that must fill at <= p in one second (queue-depth sensitivity)
def vol(e):
    r = [BN.get(t) for t in range(e - 300, e)]; r = [x for x in r if x]
    if len(r) < 240: return None
    return float(np.std(np.diff(np.log(np.array(r)))) * 1e4)
fires = {'passive': {}, 'taker': {}}; V = {}
for es, d in D.items():
    e = int(es); V[e] = vol(e)
    tk = set((w, tx, a, s) for w, sd, a, s, p, ts, tx in d['taker'])
    mk = collections.defaultdict(float); first_t = None
    rows = sorted(d['all'], key=lambda r: r[5])
    for w, sd, a, s, p, ts, tx in rows:
        sec = ts - LAG - e
        if sd != 'BUY' or not (S0 <= sec <= S1) or not (LO <= p <= HI): continue
        t = (w, tx, a, s) in tk
        if t:
            if first_t is None: first_t = (sec, a, p)
        else:
            mk[(int(sec), a, p)] += s
    # passive: first second with >= SH maker shares filled at <= p on one token
    cand = sorted(mk.items())
    per = collections.defaultdict(float); got = None
    for (sc, a, p), s in cand:
        # cumulative within the second on that token at price <= p
        tot = sum(v for (sc2, a2, p2), v in cand if sc2 == sc and a2 == a and p2 <= p)
        if tot >= SH: got = (sc, a, p); break
    if got: fires['passive'][e] = (got[2], got[1] == d['win'])
    if first_t: fires['taker'][e] = (first_t[2], first_t[1] == d['win'])
def pnl(arm, p, w):
    c = p if arm == 'passive' else p + 0.07 * p * (1 - p)
    return 10 / c - 10 if w else -10.0
def stats(arm, es):
    es = sorted(es); p = np.array([pnl(arm, *fires[arm][e]) for e in es])
    if len(p) == 0: return None
    c = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])); h = len(p) // 2
    bl = collections.defaultdict(float)
    for e, x in zip(es, p): bl[(e - 1790000000) // 21600] += x
    return len(p), 100 * np.mean([fires[arm][e][1] for e in es]), c[-1], dd, c[-1] / dd if dd else 0, sum(v > 0 for v in bl.values()), len(bl), p[:h].sum() / (10 * h), p[h:].sum() / (10 * (len(p) - h)), np.median([fires[arm][e][0] for e in es])
arms = {'all': lambda v: True, 'calm<0.304': lambda v: v is not None and v < 0.304, 'mid': lambda v: v is not None and 0.304 <= v < 0.466, 'high>=0.466': lambda v: v is not None and v >= 0.466}
print(f'{len(D)} candles; vol known on {sum(v is not None for v in V.values())}. $10/fire, one per candle, sec {S0}-{S1}, band {LO}-{HI}.')
print(f"{'arm':8s} {'vol':12s} {'n':>4s} {'win%':>5s} {'$tot':>8s} {'maxDD':>7s} {'P/DD':>5s} {'6h+':>5s} {'H1':>7s} {'H2':>7s} {'px':>5s}")
for vn, f in arms.items():
    for arm in ('passive', 'taker'):
        es = [e for e in fires[arm] if f(V[e])]
        s = stats(arm, es)
        if s: print(f"{arm:8s} {vn:12s} {s[0]:4d} {s[1]:5.1f} {s[2]:+8.1f} {s[3]:7.1f} {s[4]:5.2f} {s[5]:2d}/{s[6]:<2d} {s[7]:+7.3f} {s[8]:+7.3f} {s[9]:5.3f}{'  *n<60' if s[0] < 60 else ''}")
    both = [e for e in fires['passive'] if e in fires['taker'] and f(V[e])]
    dp = sum(pnl('passive', *fires['passive'][e]) for e in both); dt = sum(pnl('taker', *fires['taker'][e]) for e in both)
    same = sum(fires['passive'][e][1] == fires['taker'][e][1] for e in both)
    print(f"   paired {vn}: {len(both)} candles, passive {dp:+.1f} vs taker {dt:+.1f}; same outcome {same}/{len(both)}")
