#!/usr/bin/env python3
"""M24 (V, 10-02) - Zurich's FROZEN calm-FAV taker rule (poly_fav.py: calm vol<0.304, sec 60-180, favourite ASK in
[0.65,0.85], one buy per candle) replayed on an INDEPENDENT period it never saw: book1s 09-11..16, REAL 1 Hz asks.
Entry = that token's ask one second after the decision (latency), stale (>2 s) skipped; fee 0.07p(1-p); venue resolution.
Nothing tuned. Per day, halves, and a random-side null (same candles, same entry second, coin-flip side at THAT side's ask).
usage: m24_fav_oos.py <book1s.sqlite3> <bn1s json> <tape glob>"""
import sys, json, glob, gzip, sqlite3, collections, random, datetime
import numpy as np
B = collections.defaultdict(dict)
for ep, sec, au, agu, ad, agd in sqlite3.connect(sys.argv[1]).execute(
        'select epoch, sec, ask_up, age_up, ask_dn, age_dn from b1 where epoch = book_candle and sec is not null'):
    s = int(sec)
    if 0 <= s < 300: B[int(ep)][s] = (au, agu, ad, agd)
BN = {int(k): float(v) for k, v in json.load(open(sys.argv[2])).items()}
UP = {}
for f in glob.glob(sys.argv[3]):
    for k, v in json.load(gzip.open(f)).items():
        if 'up_won' in v: UP[int(k)] = v['up_won']
fee = lambda p: 0.07 * p * (1 - p)
T, NUL = [], []
for e in sorted(B):
    S = B[e]
    if e not in UP: continue
    raw = [BN[t] for t in range(e - 300, e) if t in BN]
    if len(raw) < 240 or float(np.std(np.diff(np.log(raw)))) * 1e4 >= 0.304: continue
    for s in range(60, 181):
        if s not in S or (s + 1) not in S: continue
        au, _, ad, _ = S[s]
        fav = 1 if (au or 0) >= (ad or 0) else 0
        a = au if fav == 1 else ad
        if a is None or not (0.65 <= a <= 0.85): continue
        nx = S[s + 1]
        ask, age = (nx[0], nx[1]) if fav == 1 else (nx[2], nx[3])
        if ask is None or (age or 0) > 2000 or not (0.02 <= ask <= 0.99): break
        won = (UP[e] == 1) == (fav == 1)
        T.append((e, ask, won))
        oth = (nx[2], nx[3]) if fav == 1 else (nx[0], nx[1])
        NUL.append((ask, won, oth[0], not won))
        break
pnl = lambda a, w: (1 if w else 0) - a - fee(a)
tot = sum(pnl(a, w) for _, a, w in T); cost = sum(a + fee(a) for _, a, _ in T)
print(f'M24 frozen calm-FAV on 09-11..16 real asks: {len(T)} trades, win {np.mean([w for *_, w in T])*100:.1f}%, '
      f'avg ask {np.mean([a for _, a, _ in T]):.3f}, pnl {tot:+.2f} per $1-share-units = {tot/cost:+.3f}/$  (x10 for $10-ish stakes)')
k = len(T) // 2
print(f'halves: {sum(pnl(a, w) for _, a, w in T[:k]):+.2f} / {sum(pnl(a, w) for _, a, w in T[k:]):+.2f}')
d = collections.defaultdict(list)
for e, a, w in T: d[datetime.datetime.utcfromtimestamp(e).strftime('%m-%d')].append(pnl(a, w))
print('per day:', '  '.join(f'{x} n{len(v)} {sum(v):+.2f}' for x, v in sorted(d.items())))
random.seed(24); null = []
for _ in range(4000):
    s = 0
    for a, w, ao, wo in NUL:
        if random.random() < 0.5: s += pnl(a, w)
        elif ao is not None and 0.02 <= ao <= 0.99: s += pnl(ao, wo)
    null.append(s)
print(f'null (coin-flip side, priced at THAT side\'s real ask): mean {np.mean(null):+.2f}; P(null >= ours) = {np.mean([x >= tot for x in null]):.4f}')
