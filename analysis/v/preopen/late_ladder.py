#!/usr/bin/env python3
"""PolyBot-style late maker ladder (V, 09-28, owner: 'see how others do it'). In the last 25 s of each BTC 5m candle, rest bids on
the side the TWAP projection favours (Binance 1 s proxy: locked part of the closing TWAP60 + current price for the rest, vs the
opening TWAP60) at rungs 0.20/0.35/0.50/0.65/0.80. A rung FILLS only if a public taker SELL print of that token lands STRICTLY BELOW
the rung inside the window (data-api ts shifted -2.2 s) - PolyBot's no-queue rule; filled at the rung, maker = no fee. Venue outcome.
Also reports the projection's agreement with the venue on those candles. usage: late_ladder.py <hours> -> LATE_LADDER.txt"""
import sys, json, time, urllib.request, urllib.error, collections
def g(u):
    for a in range(6):
        try:
            time.sleep(0.12); return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'v'}), timeout=20))
        except Exception:
            if a == 5: raise
            time.sleep(2 ** a)
H = float(sys.argv[1]); now = int(time.time()); e0 = now // 300 * 300
t0 = (e0 - int(H * 3600) - 600) * 1000
px = {}
t = t0
while t < now * 1000:                                    # Binance 1 s closes
    b = g(f'https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1s&startTime={t}&limit=1000')
    if not b: break
    for k in b: px[int(k[0]) // 1000] = float(k[4])
    t = int(b[-1][0]) + 1000
tw = lambda a, b: (lambda v: sum(v) / len(v) if len(v) > 40 else None)([px[s] for s in range(a, b) if s in px])
RUNGS = (0.20, 0.35, 0.50, 0.65, 0.80)
R = {r: [0, 0.0, 0] for r in RUNGS}; agree = [0, 0]; nc = 0; per_c = collections.defaultdict(float)
for k in range(2, int(H * 12) + 2):
    e = e0 - 300 * k; D = e + 275                        # decision at 275 s: 25 s left
    try:
        ev = g(f'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{e}'); m = ev[0]['markets'][0]
        toks = json.loads(m['clobTokenIds']); op = [float(x) for x in json.loads(m['outcomePrices'])]
    except Exception: continue
    if max(op) < 0.99: continue
    L = tw(e - 60, e); lk = [px[s] for s in range(e + 240, D) if s in px]
    if L is None or len(lk) < 30 or D not in px: continue
    proj = (sum(lk) + px[D] * (300 - (D - e))) / (len(lk) + 300 - (D - e))
    side = 0 if proj >= L else 1; win = 1 if op[side] > 0.5 else 0; nc += 1
    agree[0] += win; agree[1] += 1
    tr, off = [], 0
    while off < 5000:
        p = g(f'https://data-api.polymarket.com/trades?market={m["conditionId"]}&limit=500&offset={off}&takerOnly=true')
        if not p: break
        tr += p; off += len(p)
        if len(p) < 500: break
    sells = [float(x['price']) for x in tr if x['asset'] == toks[side] and x.get('side') == 'SELL' and D <= x['timestamp'] - 2.2 < e + 300]
    for r in RUNGS:
        if sells and min(sells) < r:
            R[r][0] += 1; pn = win / r - 1; R[r][1] += pn; R[r][2] += win; per_c[e] += pn
print(f'{nc} candles, last {H} h. TWAP projection at 275 s agrees with the venue {agree[0]}/{agree[1]} = {agree[0]/max(agree[1],1):.3f}')
for r in RUNGS:
    n, p, w = R[r]
    print(f'rung {r:.2f}: fills {n:4d} ({n/max(nc,1):.1%} of candles)  win {w/max(n,1):.1%}  per$1 {p/max(n,1):+.3f}  $ at $10/fill {10*p:+.1f}' + ('  INSUF' if n < 60 else ''))
es = sorted(per_c); h = len(es) // 2
for lab, part in (('H1', es[:h]), ('H2', es[h:])): print(f'{lab}: candles with a fill {len(part)}, sum per$1 {sum(per_c[x] for x in part):+.2f}')
