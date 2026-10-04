#!/usr/bin/env python3
"""Who actually makes money on BTC 5m up/down? (V, 09-28, owner: 'see how others do it'). Public data-api trades (both legs,
takerOnly=false) + the taker legs (takerOnly=true) to tag maker vs taker, venue outcomes from gamma, last H hours.
Per wallet: realized PnL = sum(sell cash) - sum(buy cost) + held shares x payout - taker fees (0.07 p(1-p) per share on taker legs).
Then, for the top wallets by PnL (n trades >= 100): maker share, mean entry price, entry second (data-api ts - 2.2 s), buys vs sells.
usage: top_wallets.py <hours> -> TOP_WALLETS.txt (+ wallets_raw.json.gz cache in the scratch dir given as argv[2])"""
import sys, json, time, gzip, os, urllib.request, collections
def g(u):
    for a in range(6):
        try:
            time.sleep(0.1); return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'v'}), timeout=25))
        except Exception:
            if a == 5: raise
            time.sleep(2 ** a)
H = float(sys.argv[1]); cache = sys.argv[2] + '/wallets_raw.json.gz'
now = int(time.time()); e0 = now // 300 * 300
data = json.load(gzip.open(cache)) if os.path.exists(cache) else {}
for k in range(2, int(H * 12) + 2):
    e = str(e0 - 300 * k)
    if e in data: continue
    try:
        m = g(f'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{e}')[0]['markets'][0]
        op = [float(x) for x in json.loads(m['outcomePrices'])]; toks = json.loads(m['clobTokenIds'])
    except Exception: continue
    if max(op) < 0.99: continue
    rows = {}
    for taker in ('false', 'true'):
        out, off = [], 0
        while off < 10000:
            p = g(f'https://data-api.polymarket.com/trades?market={m["conditionId"]}&limit=500&offset={off}&takerOnly={taker}')
            if not p: break
            out += p; off += len(p)
            if len(p) < 500: break
        rows[taker] = [(t['proxyWallet'], t['side'], t['asset'], float(t['size']), float(t['price']), t['timestamp'], t['transactionHash']) for t in out]
    data[e] = dict(win=toks[0] if op[0] > 0.5 else toks[1], all=rows['false'], taker=rows['true'])
json.dump(data, gzip.open(cache, 'wt'))
W = collections.defaultdict(lambda: dict(pnl=0.0, n=0, maker=0, vol=0.0, px=0.0, sec=[], buys=0, cands=set(), fee=0.0))
for e, d in data.items():
    e = int(e); tk = set((w, tx, a, s) for w, sd, a, s, p, ts, tx in d['taker'])
    pos = collections.defaultdict(float)
    for w, sd, a, s, p, ts, tx in d['all']:
        is_taker = (w, tx, a, s) in tk
        x = W[w]; x['n'] += 1; x['vol'] += s * p; x['px'] += p; x['cands'].add(e); x['sec'].append(ts - 2.2 - e)
        if not is_taker: x['maker'] += 1
        fee = 0.07 * p * (1 - p) * s if is_taker else 0.0
        x['fee'] += fee
        if sd == 'BUY': x['pnl'] -= s * p + fee; pos[(w, a)] += s; x['buys'] += 1
        else: x['pnl'] += s * p - fee; pos[(w, a)] -= s
    for (w, a), sh in pos.items():
        if a == d['win']: W[w]['pnl'] += sh
print(f'{len(data)} settled BTC 5m candles; {len(W)} wallets')
top = sorted(((w, x) for w, x in W.items() if x['n'] >= 100), key=lambda t: -t[1]['pnl'])
tot = sum(x['pnl'] for x in W.values())
print(f'sum of all wallets pnl {tot:+.0f} (should be ~ -fees {-sum(x["fee"] for x in W.values()):.0f})')
print('rank wallet        pnl$    trades cands  maker%  buy%  mean px  vol$     sec p10/p50/p90')
for i, (w, x) in enumerate(top[:25] + top[-5:]):
    import statistics as st
    sq = sorted(x['sec']); q = lambda f: sq[int(f * (len(sq) - 1))]
    print(f'{i+1:3d} {w[:10]}  {x["pnl"]:+8.0f}  {x["n"]:6d} {len(x["cands"]):5d}  {100*x["maker"]/x["n"]:5.0f}  {100*x["buys"]/x["n"]:4.0f}  {x["px"]/x["n"]:.3f}  {x["vol"]:8.0f}  {q(.1):+.0f}/{q(.5):+.0f}/{q(.9):+.0f}')
