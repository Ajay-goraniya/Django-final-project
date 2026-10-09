#!/usr/bin/env python3
"""Lean public-tape fetch (WALLET variant: also keeps side and proxyWallet[:12]) for strict_pfav.py: per settled BTC 5m candle keep only the deduplicated prints (ts, token_is_up, price, size)
and the winner. Saves a chunk file every 100 candles so a crash loses little. usage: fetch_tape_lean.py <e_from> <e_to> <out_prefix> [workers] [slug_prefix=btc-updown-5m] [step=300]"""
import sys, json, gzip, time, urllib.request
SLUG = 'btc-updown-5m'
from concurrent.futures import ThreadPoolExecutor
def g(u):
    for a in range(6):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'v'}), timeout=25))
        except Exception:
            if a == 5: raise
            time.sleep(2 ** a)
def one(e):
    try:
        m = g(f'https://gamma-api.polymarket.com/events?slug={SLUG}-{e}')[0]['markets'][0]
        op = [float(x) for x in json.loads(m['outcomePrices'])]; toks = json.loads(m['clobTokenIds'])
    except Exception: return e, None
    if max(op) < 0.99: return e, None
    out, off, seen = [], 0, set()
    while off < 10000:
        p = g(f'https://data-api.polymarket.com/trades?market={m["conditionId"]}&limit=500&offset={off}&takerOnly=false')
        if not p: break
        for t in p:
            k = (t['transactionHash'], t['asset'], t['size'], t['price'], t['proxyWallet'])
            if k in seen: continue
            seen.add(k); out.append((t['timestamp'], 1 if t['asset'] == toks[0] else 0, float(t['price']), float(t['size']), t['side'][0], t['proxyWallet'][:12]))
        off += len(p)
        if len(p) < 500: break
    return e, dict(up_won=1 if op[0] > 0.5 else 0, p=sorted(out))
a, b, pre = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]; W = int(sys.argv[4]) if len(sys.argv) > 4 else 12
SLUG = sys.argv[5] if len(sys.argv) > 5 else 'btc-updown-5m'; STEP = int(sys.argv[6]) if len(sys.argv) > 6 else 300
es = list(range(a, b, STEP))
for c in range(0, len(es), 100):
    fn = f'{pre}_{es[c]}.json.gz'
    try:
        json.load(gzip.open(fn)); continue          # chunk already done
    except Exception: pass
    with ThreadPoolExecutor(W) as ex: data = {str(e): d for e, d in ex.map(one, es[c:c + 100]) if d}
    json.dump(data, gzip.open(fn, 'wt')); print(c + 100, len(data), flush=True)
print('done')
