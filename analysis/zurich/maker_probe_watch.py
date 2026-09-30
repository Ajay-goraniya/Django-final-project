#!/usr/bin/env python3
"""Maker-probe alert watcher. Exits on the FIRST alertable event so the session reports it once.

Rewritten 09-30: the bash version nested python inside double quotes inside a shell function, and a
query containing a string literal came back as -1 from the except branch instead of a count. It never
fired and it never complained - the exact 'silence is not success' failure. One process, no quoting.
"""
import os, re, sqlite3, sys, time

DB   = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
LOG  = '/home/ubuntu/maker_probe/live3.log'
FLAG = '/home/ubuntu/maker_probe/ENABLED'
PID  = int(sys.argv[1])
SINCE_MS = int(sys.argv[2]) if len(sys.argv) > 2 else 0
REJECT_ALERT = 12          # a burst of post-only rejects since the restart
PAT = re.compile(r'HARD STOP|CANCEL ERROR|PASS ERROR', re.I)

def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False

def q(sql, args=()):
    d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try: return d.execute(sql, args).fetchone()[0]
    finally: d.close()

while True:
    if not alive(PID):
        print(f'ALERT PROCESS_DOWN: maker probe pid {PID} is gone'); break
    if not os.path.exists(FLAG):
        print('ALERT FLAG_REMOVED: ENABLED gone; the probe stops posting on its next pass'); break
    fills = q('select count(*) from fills')
    if fills >= 1:
        r = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        row = r.execute('select epoch, side, shares, price, bn_before_bps from fills order by id desc limit 1').fetchone()
        r.close()
        print(f'ALERT FILL: {fills} fill(s); latest epoch {row[0]} {row[1]} {row[2]}sh @ {row[3]} bn_before {row[4]}'); break
    rej = q("select count(*) from orders where dry=0 and status='REJECTED' and post_ts_ms>?", (SINCE_MS,))
    if rej >= REJECT_ALERT:
        print(f'ALERT REJECT_RATE: {rej} post-only rejects since the restart'); break
    try:
        with open(LOG) as f: hits = [l for l in f if PAT.search(l)]
        if hits: print('ALERT LOG: ' + hits[-1].strip()); break
    except OSError: pass
    time.sleep(20)
