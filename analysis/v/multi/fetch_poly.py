#!/usr/bin/env python3
"""Fetch Polymarket 5-minute up/down markets (btc/eth/sol) + all their taker trades into one sqlite (V/multi, 09-27).

usage: fetch_poly.py DB START_EPOCH END_EPOCH [assets...]
tables: mkt(asset, epoch, cond, tok_up, tok_dn, outcome 'UP'/'DOWN'/None)
        tr(asset, epoch, ts, is_up, side, price, size)   -- data-api /trades (taker trades, 1 s timestamps)
Gamma is paged by series (100 per page); any epoch missing after paging is fetched by slug."""
import sys, json, time, sqlite3, urllib.request, threading, queue
from concurrent.futures import ThreadPoolExecutor
UA = {'User-Agent': 'curl/8.5.0'}
DB, T0, T1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ASSETS = sys.argv[4:] or ['btc', 'eth', 'sol']

def get(u, tries=6):
    for i in range(tries):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))
        except Exception as e:
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(u)

db = sqlite3.connect(DB, check_same_thread=False); lock = threading.Lock()
db.execute('create table if not exists mkt(asset, epoch integer, cond, tok_up, tok_dn, outcome, primary key(asset, epoch))')
db.execute('create table if not exists tr(asset, epoch integer, ts integer, is_up integer, side, price real, size real)')
db.execute('create table if not exists done(asset, epoch integer, n integer, primary key(asset, epoch))')

def add_event(asset, e):
    m = e['markets'][0]; ep = int(e['slug'].rsplit('-', 1)[1])
    if not (T0 <= ep < T1): return ep
    toks = json.loads(m['clobTokenIds']); outs = json.loads(m['outcomes']); px = json.loads(m.get('outcomePrices') or '[]')
    iu = outs.index('Up'); idn = 1 - iu
    oc = None
    if m.get('closed') and px and px[iu] in ('1', '0') and px[idn] in ('1', '0') and px[iu] != px[idn]:
        oc = 'UP' if px[iu] == '1' else 'DOWN'
    with lock:
        db.execute('insert or replace into mkt values(?,?,?,?,?,?)', (asset, ep, m['conditionId'], toks[iu], toks[idn], oc))
    return ep

for asset in ASSETS:
    have = {r[0] for r in db.execute('select epoch from mkt where asset=? and outcome is not null', (asset,))}
    want = set(range(T0, T1, 300)) - have
    off = 0
    while want and off < 20000:
        try:
            d = get(f'https://gamma-api.polymarket.com/events?series_slug={asset}-up-or-down-5m&closed=true&limit=100&offset={off}&order=startTime&ascending=false', tries=2)
        except RuntimeError:
            break                                   # gamma refuses deep offsets (~2000); the rest go by slug
        if not d: break
        eps = [add_event(asset, e) for e in d if e.get('markets')]
        want -= set(eps); off += 100
        if eps and min(eps) < T0: break
        time.sleep(0.2)
    db.commit()
    def one(ep):
        d = get(f'https://gamma-api.polymarket.com/events?slug={asset}-updown-5m-{ep}')
        if d: add_event(asset, d[0])
        time.sleep(0.1)
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, sorted(want)))
    db.commit()
    print(asset, 'markets', db.execute('select count(*), sum(outcome is not null) from mkt where asset=?', (asset,)).fetchone(), flush=True)

def trades(job):
    asset, ep, cond, tu, td = job
    rows = []; off = 0
    while True:
        d = get(f'https://data-api.polymarket.com/trades?market={cond}&limit=1000&offset={off}')
        for x in d:
            if x['asset'] not in (tu, td): continue
            rows.append((asset, ep, int(x['timestamp']), 1 if x['asset'] == tu else 0, x['side'], float(x['price']), float(x['size'])))
        if len(d) < 1000: break
        off += 1000; time.sleep(0.1)
    with lock:
        db.executemany('insert into tr values(?,?,?,?,?,?,?)', rows)
        db.execute('insert or replace into done values(?,?,?)', (asset, ep, len(rows)))
    time.sleep(0.1)
    return len(rows)

jobs = [r for r in db.execute('select asset, epoch, cond, tok_up, tok_dn from mkt where outcome is not null and (asset, epoch) not in (select asset, epoch from done) order by epoch')
        if r[0] in ASSETS]
print('trade jobs', len(jobs), flush=True)
k = 0
with ThreadPoolExecutor(6) as ex:
    for n in ex.map(trades, jobs):
        k += 1
        if k % 200 == 0:
            with lock: db.commit()
            print('done', k, flush=True)
db.commit(); print('ALL DONE', db.execute('select asset, count(*), sum(n) from done group by asset').fetchall(), flush=True)
