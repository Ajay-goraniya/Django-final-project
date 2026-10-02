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
# The owner asked for this to run indefinitely, so it WILL be restarted (cron+flock, and once at
# the old 48 h self-stop). Dating the report from the current process alone would read "0.0 h in"
# after every restart, so the data span is taken from the db and the uptime shown beside it.
span0 = d.execute('select min(ts_ms) from quotes').fetchone()[0]
span = (dt.datetime.now(dt.UTC).timestamp() - (span0 or 0) / 1000) / 3600 if span0 else 0

L = [f'M19 PAPER SHADOW - data spans {span:.1f} h, this process up {hrs:.1f} h, '
     f'{dt.datetime.now(dt.UTC):%F %T} UTC. NO ORDERS, paper only.',
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
L += ['  BINANCE CLOCK: SETTLED 10-02 01:5x, see analysis/zurich/m19/M19_CLOCK.txt. The +329 ms REST',
      '    serverTime offset I flagged was MY artefact, not Binance\'s clock: it tracks the round trip',
      '    (slow hosts data-api.binance.vision +331 at rtt 883, api-gcp +384 at rtt 1026; fast hosts',
      '    api.binance.com +3, fapi +4, testnet +4 at rtt ~227). Decisive check: a 1 s kline cannot be',
      '    published before it closes, and all 76 closed bars arrived AFTER their own close time',
      '    (p50 +139 ms, p10 +127), so the publishing clock is not ahead. True feed lag is the measured',
      '    ~111 ms (p90 126) and the REST offset must NOT be added to D.']
if rt:
    real = min(DELAYS, key=lambda D: abs(D - (pct(0.5) * 2)))
    L.append(f'  WHICH D IS REALISTIC: a quote needs one read + one write, so the floor is ~2x the '
             f'one-way p50 = ~{pct(0.5)*2:.0f} ms -> D={real} is the closest arm. The sim says the '
             f'edge survives ~1000 ms and dies by ~2000 ms.')
# ---- the owner's post-to-ack question (V, 10-02 01:4x). READ-ONLY, probe untouched. ----------
L.append('')
L.append('  PROBE POST -> ACK LATENCY: NOT MEASURABLE from what the probe records. Why, and what is:')
try:
    import re
    mk = sqlite3.connect('file:/home/ubuntu/maker_probe/maker_probe.sqlite3?mode=ro', uri=True)
    mk.row_factory = sqlite3.Row
    gaps = [b - a for a, b in zip(*[[r[0] for r in mk.execute(
        'select ts_ms from decisions order by ts_ms')]] * 2 and
        [[r[0] for r in mk.execute('select ts_ms from decisions order by ts_ms')]] * 2)]
    rows = [r[0] for r in mk.execute('select ts_ms from decisions order by ts_ms')]
    gaps = [b - a for a, b in zip(rows, rows[1:]) if 0 < b - a < 60000]
    gq = lambda f: sorted(gaps)[int(f * (len(gaps) - 1))] if gaps else float('nan')
    ds = []
    for ln in open('/home/ubuntu/claude-work/repo/analysis/zurich/MAKER_PROBE.txt', errors='replace'):
        m = re.search(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] REJECTED epoch (\d+) '
                      r'(UP|DOWN) ([0-9.]+) ::', ln)
        if not m: continue
        t = dt.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(
            tzinfo=dt.UTC).timestamp() * 1000
        r = mk.execute("select post_ts_ms from orders where epoch=? and abs(price-?)<1e-9 and "
                       "status='REJECTED' order by abs(post_ts_ms-?) limit 1",
                       (int(m.group(2)), float(m.group(4)), t)).fetchone()
        if r: ds.append(t - r['post_ts_ms'])
    rq = lambda f: sorted(ds)[int(f * (len(ds) - 1))] if ds else float('nan')
    L += [f'    orders has post_ts_ms but NO ack timestamp, and the probe does not log a successful',
          f'    post at all - only rejects, fills and errors. So no post/ack pair exists to difference.',
          f'    The decisions table is not a substitute: its rows arrive every ~{gq(.5)/1000:.1f} s '
          f'(p10 {gq(.1)/1000:.1f} s, p90 {gq(.9)/1000:.1f} s, n {len(gaps)}), NOT once per 200 ms pass,',
          f'    so consecutive rows are not adjacent passes. I tried that differential first and it',
          f'    returned a NEGATIVE latency (-132 ms), which is how I know the method is invalid.',
          f'    THE ONE REAL BOUND, from the reject path (the log line is written AFTER the venue',
          f'    answers): n {len(ds)} samples, p50 {rq(.5):+.0f} ms, p90 {rq(.9):+.0f} ms, range '
          f'{min(ds) if ds else float("nan"):+.0f}..{max(ds) if ds else float("nan"):+.0f} ms.',
          f'    Those stamps are whole SECONDS and truncated, so values up to -999 ms are expected and',
          f'    the only honest reading is: the venue answered within the same second or the next,',
          f'    i.e. the round trip is UNDER ~1 s. It cannot be resolved finer than that from here.',
          f'    To get a real median/p90 the probe must record the ack time inside place() - a code',
          f'    change plus a restart, which is the owner\'s call, not mine.']
    mk.close()
except Exception as e:
    L.append(f'    could not read the probe artefacts: {type(e).__name__}: {e}')
print('\n'.join(L))
