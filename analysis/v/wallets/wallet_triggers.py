#!/usr/bin/env python3
"""What triggers the top TAKER winners on BTC 5m? (V, 09-28). Uses the cached 48 h trades (top_wallets.py) + Binance 1 s closes.
For each wallet's TAKER BUY legs: second in candle (ts - 2.2 s), price paid, won?, and z = TWAP60 projection vs the opening TWAP60
line (Binance 1 s proxy, London's formula shape: locked part + current price, variance of the average) signed to the bought side.
Per wallet: n, win%, mean paid, per$1 after fee, and per$1 by z bucket and by sec bucket. usage: wallet_triggers.py <scratch>"""
import sys, json, gzip, math, time, urllib.request, collections
S = sys.argv[1]; data = json.load(gzip.open(f'{S}/wallets_raw.json.gz'))
WAL = ['0x3048d653', '0x41e2e1cc', '0xc53375ff', '0x9e3ed7b6', '0xc4e21390', '0x9783f45c', '0xb7e35c5a']
eps = sorted(int(e) for e in data); px = {}
def g(u):
    for a in range(6):
        try: time.sleep(0.1); return json.load(urllib.request.urlopen(u, timeout=25))
        except Exception:
            if a == 5: raise
            time.sleep(2 ** a)
t = (eps[0] - 700) * 1000
while t < (eps[-1] + 310) * 1000:
    b = g(f'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1s&startTime={t}&limit=1000')
    if not b: break
    for k in b: px[int(k[0]) // 1000] = float(k[4])
    t = int(b[-1][0]) + 1000
def P(s):
    for k in range(5):
        if s - k in px: return px[s - k]
S2 = sum(min(i, j) for i in range(60) for j in range(60))
def z_at(e, s):                                   # London's shape on the Binance proxy
    line = [px[x] for x in range(e - 61, e - 1) if x in px]
    p = P(s - 1); r = [math.log(P(x) / P(x - 1)) for x in range(s - 121, s - 1) if P(x) and P(x - 1)]
    if len(line) < 45 or not p or len(r) < 60: return None
    line = sum(line) / len(line); sig = math.sqrt(sum(v * v for v in r) / len(r)) * p; start = e + 239
    if s - 1 >= start:
        kn = s - start; m = 60 - kn; lk = [px[x] for x in range(start, s) if x in px]
        mean = ((sum(lk) / len(lk)) * kn + m * p) / 60 if lk else p; var = sig ** 2 * m * (m + 1) * (2 * m + 1) / 6
    else:
        d = start - (s - 1); mean = p; var = sig ** 2 * (3600 * d + S2)
    sd = math.sqrt(var) / 60
    return (mean - line) / sd if sd > 0 else None
out = []
for w in WAL:
    rows = []
    for e, d in data.items():
        e = int(e); up_tok = None
        tk = [(a, s, p, ts) for ww, sd, a, s, p, ts, tx in d['taker'] if ww.startswith(w) and sd == 'BUY']
        if not tk: continue
        toks = sorted(set(a for _, _, a, *_ in d['all']))
        for a, s, p, ts in tk:
            sec = int(ts - 2.2 - e); win = 1 if a == d['win'] else 0
            z = z_at(e, e + sec) if 0 <= sec < 300 else None
            rows.append((sec, p, win, s, z, a))
    # side sign for z: UP token = the one whose price moves with BTC; infer per candle from the winner + projection sign at close
    n = len(rows)
    if not n: continue
    cost = sum(s * p * (1 + 0.07 * (1 - p)) for sec, p, win, s, z, a in rows); pay = sum(s * win for sec, p, win, s, z, a in rows)
    out.append(f'{w}: taker buys {n}, win {100*sum(r[2] for r in rows)/n:.0f}%, mean paid {sum(r[1] for r in rows)/n:.3f}, per$1 {pay/cost-1:+.3f}')
    for lab, f in (('sec <60', lambda r: r[0] < 60), ('sec 60-180', lambda r: 60 <= r[0] < 180), ('sec 180-240', lambda r: 180 <= r[0] < 240), ('sec >=240', lambda r: r[0] >= 240),
                   ('paid <0.35', lambda r: r[1] < 0.35), ('paid 0.35-0.65', lambda r: 0.35 <= r[1] <= 0.65), ('paid >0.65', lambda r: r[1] > 0.65)):
        sub = [r for r in rows if f(r)]
        if not sub: continue
        c = sum(s * p * (1 + 0.07 * (1 - p)) for sec, p, win, s, z, a in sub); q = sum(s * win for sec, p, win, s, z, a in sub)
        out.append(f'    {lab:15s} n{len(sub):5d} win {100*sum(r[2] for r in sub)/len(sub):3.0f}% per$1 {q/c-1:+.3f}' + ('  INSUF' if len(sub) < 60 else ''))
    # |z| (unsigned: how decided the TWAP was when they bought) and whether they bought the winner-by-projection
    zs = [r for r in rows if r[4] is not None]
    for lab, f in (('|z|<0.5', lambda r: abs(r[4]) < 0.5), ('|z| 0.5-1.5', lambda r: 0.5 <= abs(r[4]) < 1.5), ('|z|>=1.5', lambda r: abs(r[4]) >= 1.5)):
        sub = [r for r in zs if f(r)]
        if not sub: continue
        c = sum(s * p * (1 + 0.07 * (1 - p)) for sec, p, win, s, z, a in sub); q = sum(s * win for sec, p, win, s, z, a in sub)
        out.append(f'    {lab:15s} n{len(sub):5d} win {100*sum(r[2] for r in sub)/len(sub):3.0f}% per$1 {q/c-1:+.3f}' + ('  INSUF' if len(sub) < 60 else ''))
print('\n'.join(out))
