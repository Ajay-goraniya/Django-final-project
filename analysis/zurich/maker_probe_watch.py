#!/usr/bin/env python3
"""Maker-probe alert watcher. Exits on the FIRST alertable event so the session reports it once.

Rewritten 09-30: the bash version nested python inside double quotes inside a shell function, and a
query containing a string literal came back as -1 from the except branch instead of a count. It never
fired and it never complained - the exact 'silence is not success' failure. One process, no quoting.
"""
import os, re, sqlite3, sys, time

DB   = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
LOG  = '/home/ubuntu/maker_probe/live7.log'
FLAG = '/home/ubuntu/maker_probe/ENABLED'
PID  = int(sys.argv[1])
SINCE_MS = int(sys.argv[2]) if len(sys.argv) > 2 else 0
# Fills already in the db when we armed. 27 real fills were recovered from the venue and
# backfilled, so a bare 'fills >= 1' would fire on history instead of on the next real
# fill - which is precisely the alert V asked to be sure about.
FILL_BASE = int(sys.argv[3]) if len(sys.argv) > 3 else 0
REJECT_ALERT = 12          # a burst of post-only rejects since the restart
PAT = re.compile(r'HARD STOP|CANCEL ERROR|PASS ERROR', re.I)

def alive(pid):
    """EPERM means the process EXISTS but we may not signal it - that is ALIVE, not dead. Only
    ESRCH (no such process) is death. The naive `except OSError: return False` reports a live
    process as gone, which is a false PROCESS_DOWN alert on the one channel that must not cry wolf."""
    import errno
    try:
        os.kill(pid, 0); return True
    except PermissionError:
        return True
    except OSError as e:
        return e.errno != errno.ESRCH

def q(sql, args=()):
    d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try: return d.execute(sql, args).fetchone()[0]
    finally: d.close()

while True:
    if not alive(PID):
        print(f'ALERT PROCESS_DOWN: maker probe pid {PID} is gone'); break
    if not os.path.exists(FLAG):
        print('ALERT FLAG_REMOVED: ENABLED gone; the probe stops posting on its next pass'); break
    # The owner's 60-GRADED-FILL ping takes priority over everything else here. GRADED, not total:
    # an unsettled fill carries no outcome, so counting it would announce the bar on a number that
    # cannot yet be read. The report itself is maker_60.py.
    graded = q('select count(*) from fills where pnl is not null')
    if graded >= 60:
        print(f'ALERT GRADED_60: {graded} graded fills - run maker_60.py and send the report to V'); break
    fills = q('select count(*) from fills')
    if fills > FILL_BASE:
        r = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        row = r.execute('select epoch, side, shares, price, bn_before_bps from fills order by id desc limit 1').fetchone()
        r.close()
        print(f'ALERT FILL: {fills - FILL_BASE} NEW fill(s) (baseline {FILL_BASE}); latest epoch {row[0]} {row[1]} {row[2]}sh @ {row[3]} bn_before {row[4]}'); break
    rej = q("select count(*) from orders where dry=0 and status='REJECTED' and post_ts_ms>?", (SINCE_MS,))
    if rej >= REJECT_ALERT:
        print(f'ALERT REJECT_RATE: {rej} post-only rejects since the restart'); break
    try:
        with open(LOG) as f: hits = [l for l in f if PAT.search(l)]
        if hits: print('ALERT LOG: ' + hits[-1].strip()); break
    except OSError: pass
    time.sleep(20)
