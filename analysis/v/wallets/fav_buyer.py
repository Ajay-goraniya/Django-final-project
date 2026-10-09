#!/usr/bin/env python3
"""Profile wallet 0xc4e21390 (selective early-favourite buyer, 48 h) vs the market: in the candles it trades, at its FIRST entry
second, what do z (TWAP60 projection vs line, Binance proxy, London's shape), 30/60 s momentum signed to the bought side, and trailing
vol look like - versus ALL candles at the same second where the favourite's ask is in the same 0.65-0.85 band (from the public prints
around that second). usage: fav_buyer.py <scratch>"""
import sys, json, gzip, math, time, urllib.request, collections, statistics as st
S = sys.argv[1]; data = json.load(gzip.open(f'{S}/wallets_raw.json.gz')); W = '0xc4e21390'
pxf = f'{S}/bin1s_48h.json'
try: px = {int(k): v for k, v in json.load(open(pxf)).items()}
except Exception:
    px = {}; eps = sorted(int(e) for e in data); t = (eps[0] - 700) * 1000
    while t < (eps[-1] + 310) * 1000:
        for a in range(6):
            try: b = json.load(urllib.request.urlopen(f'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1s&startTime={t}&limit=1000', timeout=25)); break
            except Exception: time.sleep(2 ** a)
        if not b: break
        for k in b: px[int(k[0]) // 1000] = float(k[4])
        t = int(b[-1][0]) + 1000
    json.dump(px, open(pxf, 'w'))
P = lambda s: next((px[s - k] for k in range(5) if s - k in px), None)
S2 = sum(min(i, j) for i in range(60) for j in range(60))
def feats(e, s):
    line = [px[x] for x in range(e - 61, e - 1) if x in px]; p = P(s - 1)
    r = [math.log(P(x) / P(x - 1)) for x in range(s - 121, s - 1) if P(x) and P(x - 1)]
    if len(line) < 45 or not p or len(r) < 60: return None
    line = sum(line) / len(line); sig = math.sqrt(sum(v * v for v in r) / len(r)) * p
    d = e + 239 - (s - 1); var = sig ** 2 * (3600 * max(d, 0) + S2); z = (p - line) / (math.sqrt(var) / 60)
    m30 = (p / P(s - 31) - 1) * 1e4 if P(s - 31) else None; m60 = (p / P(s - 61) - 1) * 1e4 if P(s - 61) else None
    return dict(z=z, m30=m30, m60=m60, vol=sig / p * 1e4, dist=(p / line - 1) * 1e4)
his, mkt = [], []
for e, d in data.items():
    e = int(e); win = d['win']
    # the market's UP token: the token whose trades are called 'Up'? not stored - infer: token that wins when projection > 0 at close
    toks = sorted(set(a for _, _, a, *_ in d['all']))
    if len(toks) != 2: continue
    fp = feats(e, e + 299)
    if fp is None: continue
    up = win if fp['dist'] >= 0 else [t for t in toks if t != win][0]
    buys = sorted((ts - 2.2 - e, a, p) for w, sd, a, s, p, ts, tx in d['taker'] if w.startswith(W) and sd == 'BUY')
    if buys:
        sec, a, p = buys[0]; f = feats(e, e + int(sec))
        if f:
            sg = 1 if a == up else -1
            his.append(dict(sec=sec, p=p, win=int(a == win), z=sg * f['z'], m30=sg * (f['m30'] or 0), m60=sg * (f['m60'] or 0), vol=f['vol']))
    # market reference: every candle, at sec 30/60/90/120/150, the side whose recent print is 0.65-0.85
    for s0 in (30, 60, 90, 120, 150):
        pr = [(abs(ts - 2.2 - e - s0), a, p) for w, sd, a, s, p, ts, tx in d['taker'] if sd == 'BUY' and abs(ts - 2.2 - e - s0) <= 3 and 0.65 <= p <= 0.85]
        if not pr: continue
        _, a, p = min(pr); f = feats(e, e + s0)
        if f:
            sg = 1 if a == up else -1
            mkt.append(dict(sec=s0, p=p, win=int(a == win), z=sg * f['z'], m30=sg * (f['m30'] or 0), m60=sg * (f['m60'] or 0), vol=f['vol']))
def summ(lab, R):
    if not R: print(lab, 'n0'); return
    q = lambda k: st.median([r[k] for r in R])
    pn = sum(r['win'] / (r['p'] * (1 + 0.07 * (1 - r['p']))) - 1 for r in R) / len(R)
    print(f'{lab:28s} n{len(R):5d} win {100*st.mean(r["win"] for r in R):4.1f}% paid {st.mean(r["p"] for r in R):.3f} per$1 {pn:+.3f} | median z {q("z"):+.2f} m30 {q("m30"):+.1f}bp m60 {q("m60"):+.1f}bp vol {q("vol"):.2f} sec {q("sec"):.0f}')
print(f'{len(data)} candles (48 h). Wallet {W}: FIRST buy per candle; market = favourite prints 0.65-0.85 at sec 30..150 in every candle.')
summ('wallet first entries', his); summ('market favourites (all)', mkt)
for lo, hi in ((-9, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99)):
    summ(f'market fav, z {lo:+.1f}..{hi:+.1f}', [r for r in mkt if lo <= r['z'] < hi])
for lo, hi in ((-99, 0), (0, 5), (5, 15), (15, 999)):
    summ(f'market fav, m60 {lo}..{hi} bp', [r for r in mkt if lo <= r['m60'] < hi])
