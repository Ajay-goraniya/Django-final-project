#!/usr/bin/env python3
"""Binance 1 s klines for several symbols via data-api.binance.vision (api.binance.com is geo-blocked).
usage: fetch_1s_multi.py DB START_EPOCH END_EPOCH SYMBOL [SYMBOL...]
table k(sym, ts integer (open, seconds), c real close), one row per second that traded. Chunked by hour, 4 threads."""
import sys, json, time, sqlite3, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor
DB, T0, T1, SYMS = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]
db = sqlite3.connect(DB, check_same_thread=False); lock = threading.Lock()
db.execute('create table if not exists k(sym, ts integer, c real, primary key(sym, ts))')
db.execute('create table if not exists kdone(sym, hr integer, primary key(sym, hr))')
done = set(db.execute('select sym, hr from kdone').fetchall())

def get(u):
    for i in range(8):
        try: return json.load(urllib.request.urlopen(u, timeout=30))
        except Exception: time.sleep(2 * (i + 1))
    raise RuntimeError(u)

def hour(job):
    sym, h = job; rows = []; t = h * 1000; end = (h + 3600) * 1000
    while t < end:
        d = get(f'https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=1s&startTime={t}&endTime={end - 1}&limit=1000')
        if not d: break
        rows += [(sym, r[0] // 1000, float(r[4])) for r in d]
        t = d[-1][0] + 1000; time.sleep(0.05)
    with lock:
        db.executemany('insert or ignore into k values(?,?,?)', rows); db.execute('insert into kdone values(?,?)', (sym, h)); db.commit()
    return len(rows)

jobs = [(s, h) for s in SYMS for h in range(T0, T1, 3600) if (s, h) not in done]
print('jobs', len(jobs), flush=True); n = 0
with ThreadPoolExecutor(4) as ex:
    for i, r in enumerate(ex.map(hour, jobs)):
        n += r
        if i % 50 == 0: print(i, n, flush=True)
print('ALL DONE', db.execute('select sym, count(*) from k group by sym').fetchall(), flush=True)
