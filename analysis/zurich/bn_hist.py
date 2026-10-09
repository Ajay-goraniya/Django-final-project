#!/usr/bin/env python3
"""Binance aggTrades HISTORY -> 250 ms signed-flow buckets, spot + um-futures. DOWNLOAD ONLY.

V, 09-28: the missing EF-9 inputs do not need a recorder - data.binance.vision publishes daily aggTrades
zips, and both the spot and the um-futures paths are reachable from this box even though the futures
WEBSOCKET (fstream) is not. So perp flow is obtainable after all, historically.

aggTrades gives `is_buyer_maker`: True means the buyer was the maker, so the TAKER SOLD. That sign is the
whole point - unsigned volume cannot tell pressure from activity. Per 250 ms bucket, per stream:
last price, taker-buy notional, taker-sell notional, trade count.
"""
import io, os, sys, time, urllib.request, zipfile, numpy as np

OUT = '/home/ubuntu/pm_bnhist'
URLS = {'spot': 'https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{}.zip',
        'perp': 'https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{}.zip'}
BUCKET_MS = 250
UA = {'User-Agent': 'Mozilla/5.0'}


def fetch(stream, day):
    dst = f'{OUT}/{stream}_{day}.npz'
    if os.path.exists(dst): return dst, 'cached'
    url = URLS[stream].format(day)
    t0 = time.time()
    req = urllib.request.Request(url, headers=UA)
    raw = urllib.request.urlopen(req, timeout=600).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = z.namelist()[0]
    px, qty, ts, bm = [], [], [], []
    with z.open(name) as f:
        for i, line in enumerate(io.TextIOWrapper(f, 'utf-8')):
            p = line.rstrip('\n').split(',')
            if i == 0 and not p[0].lstrip('-').isdigit(): continue      # some files carry a header
            try:
                px.append(float(p[1])); qty.append(float(p[2])); ts.append(int(p[5]))
                bm.append(p[6].strip().lower() in ('true', '1'))
            except Exception: continue
    px = np.array(px); qty = np.array(qty); ts = np.array(ts, np.int64); bm = np.array(bm)
    # some futures files stamp in microseconds; normalise to ms
    if ts.max() > 4e13: ts //= 1000
    k = (ts // BUCKET_MS) * BUCKET_MS
    uk, inv = np.unique(k, return_inverse=True)
    notion = px * qty
    buy = np.zeros(len(uk)); sell = np.zeros(len(uk)); cnt = np.zeros(len(uk), np.int32)
    np.add.at(buy, inv[~bm], notion[~bm])          # buyer NOT maker -> taker bought
    np.add.at(sell, inv[bm], notion[bm])
    np.add.at(cnt, inv, 1)
    last = np.zeros(len(uk))
    order = np.argsort(ts, kind='stable')
    last[inv[order]] = px[order]                   # stable sort -> final write is the latest trade
    np.savez_compressed(dst, ts=uk, px=last, buy=buy, sell=sell, n=cnt)
    return dst, f'{len(px):,} trades -> {len(uk):,} buckets in {time.time()-t0:.0f}s'


if __name__ == '__main__':
    days = sys.argv[1:] or ['2026-09-24', '2026-09-25', '2026-09-26', '2026-09-27']
    for d in days:
        for s in ('spot', 'perp'):
            try:
                p, msg = fetch(s, d)
                print(f'  {s:5s} {d}: {msg}', flush=True)
            except Exception as e:
                print(f'  {s:5s} {d}: FAILED {type(e).__name__} {repr(e)[:110]}', flush=True)
