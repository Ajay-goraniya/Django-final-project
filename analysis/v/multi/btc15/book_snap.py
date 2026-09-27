#!/usr/bin/env python3
"""Live public CLOB book snapshots of the CURRENT btc up/down market (15m and 5m side by side), read-only (V/multi/btc15).
The data-api trades carry no book, so spread and depth at best are measured here, forward, from clob.polymarket.com/book.
usage: book_snap.py OUT.csv MINUTES [STEP_S]   rows: t, tf, sec_into_candle, side, best_bid, best_ask, bid_sz, ask_sz ($ at best)"""
import sys, json, time, urllib.request, csv
UA = {'User-Agent': 'curl/8.5.0'}
OUT, MIN = sys.argv[1], float(sys.argv[2]); STEP = float(sys.argv[3]) if len(sys.argv) > 3 else 10
get = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=15))
toks = {}
def tokens(tf, ep):
    if (tf, ep) not in toks:
        m = get(f'https://gamma-api.polymarket.com/events?slug=btc-updown-{tf}m-{ep}')[0]['markets'][0]
        t = json.loads(m['clobTokenIds']); o = json.loads(m['outcomes']); toks[(tf, ep)] = {o[0]: t[0], o[1]: t[1]}
    return toks[(tf, ep)]
fh = open(OUT, 'a'); w = csv.writer(fh); end = time.time() + 60 * MIN
while '--summary' not in sys.argv and time.time() < end:
    now = time.time()
    for tf in (15, 5):
        L = tf * 60; ep = int(now // L * L)
        try:
            for side, tok in tokens(tf, ep).items():
                b = get(f'https://clob.polymarket.com/book?token_id={tok}')
                bids = sorted(((float(x['price']), float(x['size'])) for x in b.get('bids', [])), reverse=True)
                asks = sorted((float(x['price']), float(x['size'])) for x in b.get('asks', []))
                if bids and asks:
                    w.writerow([int(now), tf, int(now - ep), side, bids[0][0], asks[0][0], round(bids[0][0] * bids[0][1], 2), round(asks[0][0] * asks[0][1], 2)])
        except Exception as e:
            print('err', tf, e, flush=True)
    fh.flush(); sys.stdout.flush(); time.sleep(max(0, STEP - (time.time() - now)))

# summary: python3 book_snap.py OUT.csv 0 10 --summary   (spread = ask_up + ask_dn - 1 from the same snapshot; depth = $ at best ask)
if '--summary' in sys.argv:
    import numpy as np, collections
    rows = list(csv.reader(open(OUT))); snap = collections.defaultdict(dict)
    for t, tf, sec, side, bb, ba, bsz, asz in rows: snap[(int(t), int(tf))][side] = (int(sec), float(bb), float(ba), float(bsz), float(asz))
    for tf in (15, 5):
        sp, dep = [], []
        for (t, f), d in snap.items():
            if f != tf or len(d) < 2: continue
            (sec, _, au, _, du), (_, _, ad, _, dd) = d['Up'], d['Down']
            if not (15 <= sec <= tf * 60 - 60) or not (.05 <= au <= .95): continue
            sp.append(au + ad - 1); dep += [du, dd]
        print(f'{tf}m: snapshots {len(sp)} (s 15..CL-60, ask 0.05..0.95) spread p25/p50/p75 {np.percentile(sp,25):.3f}/{np.median(sp):.3f}/{np.percentile(sp,75):.3f}; '
              f'$ at best ask p25/p50/p75 {np.percentile(dep,25):.0f}/{np.median(dep):.0f}/{np.percentile(dep,75):.0f}')
