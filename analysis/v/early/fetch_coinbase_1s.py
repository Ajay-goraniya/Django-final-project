#!/usr/bin/env python3
"""Coinbase BTC-USD public trades -> 1 s last price (V, 09-28). Coinbase is a Chainlink BTC/USD source; the crowd on Polymarket
watches Binance. If Coinbase leads Binance by seconds, that is an early input the venue price does not yet hold.
Public endpoint, paginated backwards by trade id ('after' = older). usage: fetch_coinbase_1s.py <start_epoch> <end_epoch> <out.json>"""
import sys, json, time, socket, urllib.request, datetime as dt
socket.setdefaulttimeout(30)
URL = 'https://api.exchange.coinbase.com/products/BTC-USD/trades?limit=1000'

def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'v-check', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r), r.headers.get('CB-AFTER')
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(2.0 * (i + 1))

def main(a, b, out):
    px, after, n, t_min = {}, None, 0, None
    while True:
        rows, after_next = get(URL + (f'&after={after}' if after else ''))
        if not rows: break
        for t in rows:
            ts = int(dt.datetime.fromisoformat(t['time'].replace('Z', '+00:00')).timestamp())
            if a <= ts <= b:
                # trades come newest first; keep the LAST trade of each second = the first seen
                px.setdefault(ts, float(t['price']))
        n += len(rows); t_min = min(int(dt.datetime.fromisoformat(t['time'].replace('Z', '+00:00')).timestamp()) for t in rows)
        if n % 50000 < 1000: print(f'  {n} trades, back to {dt.datetime.fromtimestamp(t_min, dt.timezone.utc):%m-%d %H:%M}', flush=True)
        if t_min < a or not after_next: break
        after = after_next; time.sleep(0.12)
    json.dump(px, open(out, 'w'))
    print(f'coinbase 1 s prices: {len(px)} seconds from {n} trades', flush=True)

if __name__ == '__main__':
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
