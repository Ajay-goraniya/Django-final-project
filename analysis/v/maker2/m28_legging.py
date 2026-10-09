#!/usr/bin/env python3
"""M28 (V, 10-02) - owner: buy the two sides at DIFFERENT times in the candle so the pair costs < $1.
Real 1 Hz asks (book1s 09-11..16), taker both legs, fee 0.07p(1-p) each, 1 share. Grid fixed before running, all cells:
 first leg at sec {30, 60, 120} on {favourite, underdog, UP always}; second leg = the OTHER side, the first second after leg 1
 where leg1_cost + ask2 + fee(ask2) <= 1 - m, m in {0.02, 0.05, 0.10, 0.20}, until sec 295; if never -> hold leg 1 alone.
Venue outcome. Reports: pair-completed share, pnl of completed pairs, pnl of lone legs, total, per day."""
import sys, glob, gzip, json, sqlite3, collections, datetime, itertools
import numpy as np
B = collections.defaultdict(dict)
for ep, sec, au, ad in sqlite3.connect(sys.argv[1]).execute(
        'select epoch, sec, ask_up, ask_dn from b1 where epoch = book_candle and sec is not null and ask_up is not null and ask_dn is not null'):
    s = int(sec)
    if 0 <= s < 300: B[int(ep)][s] = (au, ad)
UP = {}
for f in glob.glob(sys.argv[2]):
    for k, v in json.load(gzip.open(f)).items():
        if 'up_won' in v: UP[int(k)] = v['up_won']
fee = lambda p: 0.07 * p * (1 - p)
print('leg1 sec side   m    | candles pair%  pair$   lone$  lone win%   TOTAL$  per candle  days+')
for t1, side, m in itertools.product((30, 60, 120), ('fav', 'dog', 'up'), (0.02, 0.05, 0.10, 0.20)):
    pair, lone, lw, n = [], [], [], 0
    d = collections.defaultdict(float)
    for e, S in B.items():
        if e not in UP or t1 not in S: continue
        au, ad = S[t1]
        tok = {'up': 1, 'fav': 1 if au >= ad else 0, 'dog': 0 if au >= ad else 1}[side]
        a1 = au if tok else ad
        if not (0.02 <= a1 <= 0.98): continue
        c1 = a1 + fee(a1); n += 1
        done = None
        for s in range(t1 + 1, 296):
            if s not in S: continue
            a2 = S[s][1] if tok else S[s][0]
            if a2 and 0.01 <= a2 <= 0.99 and c1 + a2 + fee(a2) <= 1 - m: done = c1 + a2 + fee(a2); break
        won = (UP[e] == 1) == (tok == 1)
        if done is not None: p = 1 - done; pair.append(p)
        else: p = (1 if won else 0) - c1; lone.append(p); lw.append(won)
        d[datetime.datetime.utcfromtimestamp(e).strftime('%m-%d')] += p
    tot = sum(pair) + sum(lone)
    print(f'{t1:4d}     {side:4s} {m:.2f} | {n:5d} {len(pair)/n*100:5.1f} {sum(pair):+7.2f} {sum(lone):+7.2f}   {np.mean(lw)*100 if lw else 0:5.1f}   {tot:+7.2f}  {tot/n:+.4f}   {sum(v>0 for v in d.values())}/{len(d)}')
