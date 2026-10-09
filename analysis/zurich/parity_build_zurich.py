#!/usr/bin/env python3
"""Put ZURICH data into the exact input format V's analysis/v/ef8/ef8_build.py expects, so the same
code path can be run on both boxes. Writes {out}/polybook.sqlite3, {out}/venues.sqlite3,
{out}/bin1s_0911.json (the filename ef8_build.py hardcodes).

Three things this deliberately does NOT do:
  * it does not touch V's scratch or V's code;
  * it does not invent bid/size/age - tape1s never recorded them, so they are written NULL. Nothing in
    fav_rule_test.py reads them; ef8_build tolerates None. They are absent, not zero, and not guessed.
  * it does not reuse the Chainlink reference for vol. V's vol is Binance 1 s closes, so this path uses
    Binance 1 s closes, which is a different series from my first-pass run and is the point of parity.
Read-only on every source. usage: parity_build_zurich.py <outdir>
"""
import sqlite3, json, glob, os, sys, zipfile, datetime as dt, collections

OUT   = sys.argv[1]
ARCH  = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE  = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
os.makedirs(OUT, exist_ok=True)

# ---- Binance 1 s closes. The daily archives are MICROSECONDS for these dates; ef8_build.py does
# int(t)//1000 and wants MILLISECONDS (the REST feed V used). Normalise, or px is keyed 1000x high,
# every P(t) returns None and the build silently produces nothing.
rows = []
for z in sorted(glob.glob('/tmp/parity/z-2026-09-*.zip')):
    with zipfile.ZipFile(z) as f:
        for line in f.read(f.namelist()[0]).decode().splitlines():
            p = line.split(',')
            if not p or not p[0] or p[0][0].isalpha(): continue
            t = int(p[0])
            if t > 20_000_000_000_000: t //= 1000
            rows.append((t, float(p[4])))
rows.sort()
assert rows, 'no klines'
json.dump(rows, open(f'{OUT}/bin1s_0911.json', 'w'))
f = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime('%m-%d %H:%M')
print(f'bin1s   {len(rows):,} closes  {f(rows[0][0])} .. {f(rows[-1][0])}')

# ---- outcomes: gamma, extended by the archive's own label (they agree 838/838 on the overlap)
a = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
vo = {}
for p in GAMMA:
    try:
        g = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        vo.update({int(e): str(o).upper() for e, o in g.execute(
            "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
    except Exception: pass
ar = {int(e): str(v).upper() for e, v in a.execute(
    "SELECT epoch,actual FROM results WHERE actual IS NOT NULL")}
ov = [e for e in ar if e in vo]
dis = sum(1 for e in ov if ar[e] != vo[e])
print(f'labels  gamma {len(vo)}  archive {len(ar)}  overlap {len(ov)}  disagree {dis}')
assert dis == 0, f'{dis} label disagreements - stop and resolve before any grid'
for e, v in ar.items(): vo.setdefault(e, v)
assert set(vo.values()) <= {'UP', 'DOWN'}, sorted(set(vo.values()))

v = sqlite3.connect(f'{OUT}/venues.sqlite3')
v.execute('DROP TABLE IF EXISTS outcome'); v.execute('CREATE TABLE outcome(epoch INT PRIMARY KEY, actual TEXT)')
v.executemany('INSERT INTO outcome VALUES(?,?)', sorted(vo.items())); v.commit()

# ---- pb: one row per second from tape1s. bid/size/age are NULL because they were never recorded.
try:
    lv = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    live_eps = {int(e) for (e,) in lv.execute("SELECT DISTINCT epoch FROM orders WHERE lane='LIVE'")}
except Exception:
    live_eps = set()
pb, per_day, have = [], collections.Counter(), collections.Counter()
for ts, ua, da in a.execute("SELECT ts, up_ask, dn_ask FROM tape1s ORDER BY ts"):
    ep = (int(ts) // 300) * 300; sec = int(ts) - ep
    if ep in live_eps: continue                      # candles this box traded LIVE on: we were in that book
    pb.append((int(ts) * 1000, ep, sec, ua, None, None, da, None, None, None, 'live websocket'))
b = sqlite3.connect(f'{OUT}/polybook.sqlite3')
b.execute('DROP TABLE IF EXISTS pb')
b.execute('CREATE TABLE pb(ts_ms INT, epoch INT, sec INT, ask_up REAL, size_up REAL, bid_up REAL,'
          ' ask_dn REAL, size_dn REAL, bid_dn REAL, age_s REAL, status TEXT)')
b.executemany('INSERT INTO pb VALUES(?,?,?,?,?,?,?,?,?,?,?)', pb); b.commit()
print(f'pb      {len(pb):,} rows   excluded {len(live_eps)} LIVE candle(s)')

# ---- COVERAGE, stated rather than assumed (V check 5)
seen = collections.defaultdict(set)
for _, ep, sec, ua, _, _, da, _, _, _, _ in pb:
    if ua is not None and da is not None: seen[ep].add(sec)
print('coverage  day      candles  with_outcome  mean_sec/300  %candles <60 s of book')
for d in sorted({dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d') for e in seen}):
    eps = [e for e in seen if dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d') == d]
    wo  = [e for e in eps if e in vo]
    ms  = sum(len(seen[e]) for e in eps) / max(len(eps), 1)
    thin = 100 * sum(1 for e in eps if len(seen[e]) < 60) / max(len(eps), 1)
    print(f'          {d}    {len(eps):4d}     {len(wo):4d}        {ms:5.1f}          {thin:4.1f}%')
