#!/usr/bin/env python3
"""Owner idea 09-28 18:5x: buy the NEXT candles before they open, when both sides are ~0.50.
Pre-open, the outcome (closing TWAP60 vs opening TWAP60) is a coin flip UNLESS we are inside the opening TWAP's own window (last 60 s).
Public taker prints (data-api, market=<conditionId>, timestamps shifted -2.2 s), venue outcome from gamma. For each print before the open:
bucket by time to open, and price it: a taker who bought that side at that price earned win/cost - 1 per $1 (fee 0.07(1-p)).
usage: preopen_trades.py <hours back>  -> PREOPEN.txt"""
import sys, json, time, urllib.request, urllib.error, collections
def g(u):
    for a in range(6):
        try:
            time.sleep(0.15); return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'v'}), timeout=20))
        except Exception as x:
            if a == 5: raise
            time.sleep(2 ** a)
H = float(sys.argv[1]) if len(sys.argv) > 1 else 8
now = int(time.time()); e0 = now // 300 * 300
B = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])        # n, $ staked, $ pnl, wins
cells = collections.defaultdict(lambda: [0, 0.0, 0.0])
nc = 0
CC = collections.defaultdict(lambda: [0.0, 0.0])
for k in range(2, int(H * 12) + 2):
    e = e0 - 300 * k
    try:
        ev = g(f'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{e}')
        m = ev[0]['markets'][0]; toks = json.loads(m['clobTokenIds']); op = [float(x) for x in json.loads(m['outcomePrices'])]
    except Exception: continue
    if max(op) < 0.99: continue
    win_tok = toks[0] if op[0] > 0.5 else toks[1]; nc += 1
    tr, off = [], 0
    while off < 5000:
        p = g(f'https://data-api.polymarket.com/trades?market={m["conditionId"]}&limit=500&offset={off}&takerOnly=true')
        if not p: break
        tr += p; off += len(p)
        if len(p) < 500: break
    for t in tr:
        if t.get('side') != 'BUY': continue
        dt = e - (t['timestamp'] - 2.2)
        if dt <= 0: continue
        px = float(t['price']); sz = float(t['size']); win = 1 if t['asset'] == win_tok else 0
        cost = px * (1 + 0.07 * (1 - px)); usd = sz * cost; pnl = sz * win - usd
        tb = '>600s' if dt > 600 else '60-600s' if dt > 60 else '<=60s'
        pb = '<0.45' if px < 0.45 else '0.45-0.55' if px <= 0.55 else '>0.55'
        if tb == '<=60s' and pb == '<0.45': CC[e][0] += usd; CC[e][1] += pnl
        for key in ((tb, 'all'), (tb, pb)):
            c = cells[key]; c[0] += 1; c[1] += usd; c[2] += pnl
        b = B[tb]; b[0] += 1; b[1] += usd; b[2] += pnl; b[3] += win
print(f'{nc} settled candles over the last {H} h; taker BUY prints before the open, per $1 = pnl / staked')
for (tb, pb), (n, usd, pnl) in sorted(cells.items()):
    print(f'{tb:8s} {pb:10s} n{n:5d} staked ${usd:8.0f}  per$1 {pnl/usd:+.3f}' + ('  INSUF' if n < 60 else ''))

es = sorted(CC); h = len(es) // 2
for lab, part in (('H1 (older)', es[:h]), ('H2 (newer)', es[h:])):
    u = sum(CC[x][0] for x in part); q = sum(CC[x][1] for x in part)
    print(f'<=60s <0.45 {lab}: candles {len(part)}, per$1 {q/u:+.3f}, candles positive {sum(CC[x][1] > 0 for x in part)}')
