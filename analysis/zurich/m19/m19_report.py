#!/usr/bin/env python3
"""The 4-line M19 paper report V asked for, at 6 h and 24 h. READ-ONLY."""
import sqlite3, sys, datetime as dt

DB = '/home/ubuntu/m19_paper/m19_paper.sqlite3'
MARGINS, DELAYS = (0.15, 0.20), (300, 700, 1000, 1500)
d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); d.row_factory = sqlite3.Row
g = [dict(r) for r in d.execute('select * from fills where pnl is not null')]
op = d.execute('select count(*) from fills where pnl is null').fetchone()[0]
h = d.execute('select * from health order by ts_ms desc limit 1').fetchone()
# elapsed time comes from the RUNNING process's own START line, not from min(quotes): the db also
# holds the smoke-test rows from before the real launch, and dating the run from those would
# overstate how long it has been measuring.
t0 = None
try:
    import re, datetime as _dt
    for ln in open('/home/ubuntu/m19_paper/m19.log'):
        if 'START pid' in ln:
            t0 = _dt.datetime.strptime(ln[1:20], '%Y-%m-%d %H:%M:%S').replace(
                tzinfo=_dt.timezone.utc).timestamp() * 1000
except Exception:
    pass
if t0 is None:
    t0 = d.execute('select min(ts_ms) from quotes').fetchone()[0]
rt = [r[0] for r in d.execute('select ms from rtt where code=200')]
rt.sort()
pct = lambda p: rt[min(len(rt) - 1, int(p * len(rt)))] if rt else float('nan')
hrs = (dt.datetime.now(dt.UTC).timestamp() - (t0 or 0) / 1000) / 3600 if t0 else 0

L = [f'M19 PAPER SHADOW - {hrs:.1f} h in, {dt.datetime.now(dt.UTC):%F %T} UTC. NO ORDERS, paper only.',
     f'  graded {len(g)} fills, {op} unsettled; quotes {h["quotes"] if h else 0}; '
     f'venue trade prints seen {h["poly_trades"] if h else 0}']
L.append(f'  {"arm":>12s} {"n":>5s} {"W/L":>8s} {"deployed":>9s} {"pnl":>9s} {"pnl/$1":>8s}  flag')
for m in MARGINS:
    for D in DELAYS:
        s = [x for x in g if abs(x['m'] - m) < 1e-9 and x['delay_ms'] == D]
        w = sum(1 for x in s if x['pnl'] > 0); l = sum(1 for x in s if x['pnl'] < 0)
        dep = sum(x['spent'] for x in s); pnl = sum(x['pnl'] for x in s)
        L.append(f'  m{m:.2f} D{D:>5d} {len(s):5d} {f"{w}/{l}":>8s} {dep:9.2f} {pnl:+9.4f} '
                 f'{pnl/max(dep,1e-9):+8.4f}  {"INSUFFICIENT (<60)" if len(s) < 60 else ""}')
L += [f'  REST round-trip to the CLOB read endpoint: n {len(rt)}, p50 {pct(0.5):.0f} ms, '
      f'p90 {pct(0.9):.0f} ms, max {rt[-1] if rt else float("nan"):.0f} ms']
if rt:
    real = min(DELAYS, key=lambda D: abs(D - (pct(0.5) * 2)))
    L.append(f'  WHICH D IS REALISTIC: a quote needs one read + one write, so the floor is ~2x the '
             f'one-way p50 = ~{pct(0.5)*2:.0f} ms -> D={real} is the closest arm. The sim says the '
             f'edge survives ~1000 ms and dies by ~2000 ms.')
print('\n'.join(L))
