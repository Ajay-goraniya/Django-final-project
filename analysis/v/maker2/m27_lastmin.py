#!/usr/bin/env python3
"""M27 (V, 10-02) - owner's question: buy the favourite only if it is >= 0.70 in the LAST MINUTE (sec 240-299).
Real Polymarket 1 Hz top of book (polybook 09-11..16, has bid AND ask). Per candle: first second in 240-298 where the
favourite's ask >= 0.70; (a) TAKER at that token's ask 1 s later + fee; (b) MAKER UPPER BOUND: bought at the bid at the
decision second, assumed filled every time, no fee (real maker fills are worse: adverse selection). Calm and all candles.
Bands 0.70-0.80 / 0.80-0.90 / 0.90-0.99 and all. Per day, halves. Venue outcome."""
import sys, json, glob, gzip, sqlite3, collections, datetime
import numpy as np
B = collections.defaultdict(dict)
for ep, sec, au, bu, ad, bd, age in sqlite3.connect(sys.argv[1]).execute(
        "select epoch, sec, ask_up, bid_up, ask_dn, bid_dn, age_s from pb where status='ok' or status is null or ask_up is not null"):
    if sec is None or ep is None or au is None or ad is None: continue
    B[int(ep)][int(sec)] = (au, bu, ad, bd, age)
BN = {int(k): float(v) for k, v in json.load(open(sys.argv[2])).items()}
UP = {}
for f in glob.glob(sys.argv[3]):
    for k, v in json.load(gzip.open(f)).items():
        if 'up_won' in v: UP[int(k)] = v['up_won']
fee = lambda p: 0.07 * p * (1 - p)
R = []
for e, S in B.items():
    if e not in UP: continue
    raw = [BN[t] for t in range(e - 300, e) if t in BN]
    calm = len(raw) >= 240 and float(np.std(np.diff(np.log(raw)))) * 1e4 < 0.304
    for s in range(240, 299):
        if s not in S or (s + 1) not in S: continue
        au, bu, ad, bd, age = S[s]
        fav = 1 if au >= ad else 0
        a, b = (au, bu) if fav else (ad, bd)
        if a < 0.70 or a > 0.99: continue
        n = S[s + 1]; ta = n[0] if fav else n[2]
        if ta is None or not (0.02 <= ta <= 0.995): break
        won = (UP[e] == 1) == (fav == 1)
        da = n[2] if fav else n[0]  # the UNDERDOG's ask 1 s later (owner 10-02: buy the losing side)
        dog = ((0 if won else 1) - da - fee(da)) if (da is not None and 0.005 <= da <= 0.98) else None
        R.append(dict(dog=dog, e=e, calm=calm, a=a, taker=(1 if won else 0) - ta - fee(ta), maker=((1 if won else 0) - b) if b else None, won=won))
        break
def line(nm, L):
    if not L: print(f'  {nm:22s} none'); return
    t = sum(x['taker'] for x in L); m = sum(x['maker'] for x in L if x['maker'] is not None)
    d = collections.defaultdict(float)
    for x in L: d[datetime.datetime.utcfromtimestamp(x['e']).strftime('%m-%d')] += x['taker']
    k = len(L) // 2
    dg = [x['dog'] for x in L if x['dog'] is not None]
    print(f'  {nm:22s} UNDERDOG taker n {len(dg)} win {np.mean([not x["won"] for x in L])*100:4.1f}% pnl {sum(dg):+7.2f} ({sum(dg)/max(1,len(dg)):+.3f}/trade)')
    print(f'  {nm:22s} n {len(L):4d} win {np.mean([x["won"] for x in L])*100:5.1f}%  TAKER {t:+7.2f} ({t/len(L):+.3f}/trade, halves {sum(x["taker"] for x in L[:k]):+.2f}/{sum(x["taker"] for x in L[k:]):+.2f}, days+ {sum(v>0 for v in d.values())}/{len(d)})  MAKER-upper-bound {m:+7.2f}')
R.sort(key=lambda x: x['e'])
print(f'M27: {len(B)} candles with book; {len(R)} last-minute favourite >= 0.70 entries. pnl per 1 share.')
for nm, f in (('ALL candles', lambda x: True), ('CALM only', lambda x: x['calm']), ('NOT calm', lambda x: not x['calm'])):
    print(nm)
    for lo, hi in ((0.70, 0.80), (0.80, 0.90), (0.90, 0.995), (0.70, 0.995)):
        line(f'fav ask {lo:.2f}-{hi:.2f}', [x for x in R if f(x) and lo <= x['a'] < hi])
