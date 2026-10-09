#!/usr/bin/env python3
"""Parallel public-tape fetch (same fields as top_wallets.py's cache) for settled BTC 5m candles in [e_from, e_to).
usage: fetch_tape.py <e_from> <e_to> <out.json.gz> [workers]"""
import sys, json, gzip, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
def g(u):
    for a in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'v'}), timeout=25))
        except Exception:
            if a == 5: raise
            time.sleep(2 ** a)
def one(e):
    try:
        m = g(f'https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{e}')[0]['markets'][0]
        op = [float(x) for x in json.loads(m['outcomePrices'])]; toks = json.loads(m['clobTokenIds'])
    except Exception: return e, None
    if max(op) < 0.99: return e, None
    rows = {}
    for taker in ('false', 'true'):
        out, off = [], 0
        while off < 10000:
            p = g(f'https://data-api.polymarket.com/trades?market={m["conditionId"]}&limit=500&offset={off}&takerOnly={taker}')
            if not p: break
            out += p; off += len(p)
            if len(p) < 500: break
        rows[taker] = [(t['proxyWallet'], t['side'], t['asset'], float(t['size']), float(t['price']), t['timestamp'], t['transactionHash']) for t in out]
    return e, dict(win=toks[0] if op[0] > 0.5 else toks[1], up=toks[0], all=rows['false'], taker=rows['true'])
a, b, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]; W = int(sys.argv[4]) if len(sys.argv) > 4 else 8
data, n = {}, 0
with ThreadPoolExecutor(W) as ex:
    for e, d in ex.map(one, range(a, b, 300)):
        n += 1
        if d: data[str(e)] = d
        if n % 50 == 0: print(n, len(data), flush=True)
json.dump(data, gzip.open(out, 'wt')); print('done', len(data))
