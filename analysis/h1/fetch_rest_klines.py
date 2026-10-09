"""Task 15 part 1 - fill the kline gap via REST when data.binance.vision has not published the day.

api.binance.com is geo-blocked from this container; data-api.binance.vision serves the same
/api/v3 responses and is not. 1s klines, paged at 1000 rows (1000 s) per request.
"""
import json, sys, time, urllib.request

HOST = 'https://data-api.binance.vision'
SEC = 300


def fetch(sym, start_ms, end_ms, out):
    rows, t = [], start_ms
    while t < end_ms:
        url = (f'{HOST}/api/v3/klines?symbol={sym}&interval=1s'
               f'&startTime={t}&endTime={min(t + 1000_000, end_ms)}&limit=1000')
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    batch = json.load(r)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        if not batch:
            t += 1000_000
            continue
        rows.extend((int(b[0]), float(b[4])) for b in batch)
        t = int(batch[-1][0]) + 1000
        if len(rows) % 20000 < 1000:
            print('  %d rows, at %s' % (len(rows), time.strftime('%H:%M:%S', time.gmtime(t / 1000))),
                  flush=True)
    with open(out, 'w') as f:
        json.dump(rows, f)
    print('wrote %d rows -> %s' % (len(rows), out), flush=True)
    return rows


if __name__ == '__main__':
    start, end, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    fetch('BTCUSDT', start, end, out)
