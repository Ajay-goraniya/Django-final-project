#!/usr/bin/env python3
"""Grade settled maker-probe fills. OUTSIDE the probe process, on cron.

10-01 13:0x: the owner saw the 12:40 fill (5sh @ 0.79) reading "pending" at 13:04 while gamma had
resolved it DOWN at 12:45:53. Cause: maker_probe.settle() is reachable ONLY from the `--settle` CLI
flag. The live probe never calls it, so every fill stayed pnl=NULL until a human typed the command -
and because BOTH hard stops sum fills.pnl over non-NULL rows, an ungraded loss is invisible to them.
At 13:04 the day read +2.4372 when the truth was -1.5128: $3.95 of realised loss uncounted, and a
run of losses would have left the day stop unable to fire at all.

This closes it without touching the probe: same tested settle() function, own short-lived process,
generous busy timeout so it never contends with the probe's own writes. The in-process fix (the probe
grading inside its own loop) needs a code change and a restart, which is V's and the owner's call.
"""
import sqlite3, sys, time
sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
import maker_probe as M

HEARTBEAT = '/home/ubuntu/maker_probe/grade.heartbeat'
HOURLY = 3600

db = sqlite3.connect(M.DB_PATH, timeout=30)       # wait for the probe's lock rather than failing
db.row_factory = sqlite3.Row
try:
    n = M.settle(db)
    # HEARTBEAT, added 10-01 on V's instruction. This script only wrote when it actually graded
    # something, so an empty log was indistinguishable from a dead cron - and the stops depend on
    # this script running. Now every run overwrites a heartbeat file (so the LAST run is always
    # provable from one cheap read) and the log gets one line an hour (so the log itself carries a
    # liveness trail without 720 lines a day). Silence is now a readable fact, not an assumption.
    today_hb = time.strftime('%Y-%m-%d', time.gmtime())
    d_hb = db.execute('select coalesce(sum(pnl),0) from fills where utc_day=?', (today_hb,)).fetchone()[0]
    l_hb = db.execute('select coalesce(sum(pnl),0) from fills').fetchone()[0]
    nf = db.execute('select count(*) from fills').fetchone()[0]
    uns = db.execute('select count(*) from fills where pnl is null').fetchone()[0]
    now = time.time()
    with open(HEARTBEAT, 'w') as f:
        f.write(f'{int(now)} {time.strftime("%F %T", time.gmtime(now))} graded_this_run={n} '
                f'fills={nf} unsettled={uns} today={d_hb:+.4f} lifetime={l_hb:+.4f}\n')
    try:
        last = float(open(HEARTBEAT + '.hourly').read().strip())
    except Exception:
        last = 0.0
    if now - last >= HOURLY:
        open(HEARTBEAT + '.hourly', 'w').write(str(now))
        print(f'{time.strftime("%F %T", time.gmtime(now))} alive; fills {nf} unsettled {uns} '
              f'today {d_hb:+.4f} lifetime {l_hb:+.4f}', flush=True)
    if n:
        d, l = d_hb, l_hb
        print(f'{time.strftime("%F %T", time.gmtime())} graded {n}; today {d:+.4f} lifetime {l:+.4f}',
              flush=True)
        if d <= M.DAY_STOP or l <= M.LIFE_STOP:
            print(f'{time.strftime("%F %T", time.gmtime())} *** A STOP IS NOW BREACHED: '
                  f'today {d:+.2f} vs {M.DAY_STOP}, lifetime {l:+.2f} vs {M.LIFE_STOP} ***', flush=True)
finally:
    db.close()
