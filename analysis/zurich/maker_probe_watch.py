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
FILL_BASE = int(sys.argv[3]) if len(sys.argv) > 3 else 0      # kept for the arm line; no longer alerts
TOP_BAND  = 0.78
REM_MIN   = 1.0     # a remainder below this is dust and does not interrupt - see below
TOP_BASE  = int(sys.argv[4]) if len(sys.argv) > 4 else 0      # top-of-band fills already seen
REM_BASE  = int(sys.argv[5]) if len(sys.argv) > 5 else 0      # remainder-cancels already seen
REJECT_ALERT = 12          # a burst of post-only rejects since the restart
SIXTY_FLAG   = '/home/ubuntu/maker_probe/.graded60.alerted'   # fires the 60 report once, ever
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
    # 10-01 22:0x, owner via V: "Keep Zurich maker test running even if it goes over 60 trades." 60 is
    # a REPORT, not a stop. Nothing in the probe, the grader or cron stops at 60 (verified). The one
    # thing that did end at 60 was THIS watcher: it breaks to deliver the alert, and with no latch a
    # re-arm would re-fire GRADED_60 on every start, so hard stop / error / process death could never
    # be watched again past the 60th graded fill. The latch fires the report once, for good.
    graded = q('select count(*) from fills where pnl is not null')
    if graded >= 60 and not os.path.exists(SIXTY_FLAG):
        open(SIXTY_FLAG, 'w').write(str(graded))
        print(f'ALERT GRADED_60: {graded} graded fills - run maker_60.py and send the report to V'); break
    # V, 10-01 20:5x: GO QUIET ON SINGLE FILLS. The market turned calm and fills began landing every
    # few minutes, so a ping per fill was spending tokens on information the 60-graded report carries
    # anyway. Only these fills still interrupt:
    #   TOP OF BAND (>= 0.78) - the asymmetric corner. At 0.78 a win pays ~1.10 and a loss costs the
    #     full ~3.90, so it needs ~79% to break even; both 5-share fills at 0.78+ were the two worst
    #     outcomes in the ledger at the time V asked for this.
    #   A PARTIAL NEEDING A REMAINDER CANCEL - because the remainder is live at the venue until that
    #     cancel lands, and an orphaned remainder is the one shape here that can lose money unwatched.
    # The plain fill counter is deliberately gone: a quiet channel that only speaks for these is worth
    # more than one that speaks for everything.
    topband = q('select count(*) from fills where price >= ?', (TOP_BAND,))
    if topband > TOP_BASE:
        r = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        row = r.execute('select epoch, side, shares, price from fills where price >= ? '
                        'order by id desc limit 1', (TOP_BAND,)).fetchone()
        r.close()
        print(f'ALERT TOP_BAND_FILL: {row[1]} {row[2]}sh @ {row[3]} (epoch {row[0]}) - '
              f'top-of-band entry, needs ~{100*row[3]:.0f}% to break even'); break
    # MATERIALITY FLOOR on the remainder alert, added 10-01 21:0x. V kept this category because an
    # orphaned remainder can lose money unwatched - which is right, but the first one it caught was
    # 0.005897 shares, worth $0.0036. Alerting on a third of a cent is noise, and a channel that cries
    # wolf is the one nobody reads when it matters. The floor is 1.0 share, the same number the owner
    # approved as the dust threshold for candle-locking, so "dust" means one thing across the system.
    # The remainders actually seen so far are 3.47sh, 4.99sh and 0.0059sh, so this separates them
    # cleanly rather than being fitted to a borderline case.
    rem = q("select count(*) from orders where dry=0 and cancel_reason like 'remainder%' "
            "and cast(replace(substr(cancel_reason, 11), 'sh after partial fill', '') as real) >= ?",
            (REM_MIN,))
    if rem > REM_BASE:
        r = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        row = r.execute("select id, side, price, cancel_reason from orders where dry=0 and "
                        "cancel_reason like 'remainder%' and cast(replace(substr(cancel_reason, 11), "
                        "'sh after partial fill', '') as real) >= ? order by id desc limit 1",
                        (REM_MIN,)).fetchone()
        r.close()
        print(f'ALERT PARTIAL_REMAINDER: order {row[0]} {row[1]} @ {row[2]} - {row[3]}'); break
    # 10-01 21:5x, V: the shared wallet is down to ~$25 (London's master is OFF). A not-enough-cash
    # rejection is bounded by the 3-posts-per-candle cap and can never become a fill (tested), but V
    # wants ONE ping if it ever happens - and it would not trip REJECT_RATE until the 12th one.
    cash = q("select count(*) from orders where dry=0 and status='REJECTED' and post_ts_ms>? and ("
             "lower(coalesce(note,'')) like '%balance%' or lower(coalesce(note,'')) like '%insufficient%'"
             " or lower(coalesce(note,'')) like '%allowance%' or lower(coalesce(note,'')) like '%funds%'"
             " or lower(coalesce(note,'')) like '%collateral%')", (SINCE_MS,))
    if cash:
        r = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        row = r.execute("select id, epoch, price, substr(note,1,90) from orders where dry=0 and "
                        "status='REJECTED' and post_ts_ms>? order by id desc limit 1",
                        (SINCE_MS,)).fetchone()
        r.close()
        print(f'ALERT BALANCE_REJECT: {cash} cash reject(s); last order {row[0]} epoch {row[1]} '
              f'@ {row[2]} :: {row[3]}'); break
    rej = q("select count(*) from orders where dry=0 and status='REJECTED' and post_ts_ms>?", (SINCE_MS,))
    if rej >= REJECT_ALERT:
        print(f'ALERT REJECT_RATE: {rej} post-only rejects since the restart'); break
    try:
        with open(LOG) as f: hits = [l for l in f if PAT.search(l)]
        if hits: print('ALERT LOG: ' + hits[-1].strip()); break
    except OSError: pass
    time.sleep(20)
