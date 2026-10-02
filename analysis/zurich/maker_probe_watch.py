#!/usr/bin/env python3
"""Maker-probe alert watcher. Exits on the FIRST alertable event so the session reports it once.

Rewritten 09-30: the bash version nested python inside double quotes inside a shell function, and a
query containing a string literal came back as -1 from the except branch instead of a count. It never
fired and it never complained - the exact 'silence is not success' failure. One process, no quoting.
"""
import os, re, sqlite3, sys, time

DB   = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
# 10-02 01:4x: this pointed at live7.log, which is ZERO BYTES - the probe's logfile is
# maker_probe.LOGFILE, the committed incident record. So the HARD STOP / CANCEL ERROR / PASS ERROR
# alert could never have fired, for any of the runs that used it. Same shape as the bash watcher
# that returned -1 instead of a count: armed, silent, useless.
LOG  = '/home/ubuntu/claude-work/repo/analysis/zurich/MAKER_PROBE.txt'
FLAG = '/home/ubuntu/maker_probe/ENABLED'
PID  = int(sys.argv[1])
SINCE_MS = int(sys.argv[2]) if len(sys.argv) > 2 else 0
# Fills already in the db when we armed. 27 real fills were recovered from the venue and
# backfilled, so a bare 'fills >= 1' would fire on history instead of on the next real
# fill - which is precisely the alert V asked to be sure about.
FILL_BASE = int(sys.argv[3]) if len(sys.argv) > 3 else 0      # kept for the arm line; no longer alerts
REM_MIN   = 1.0     # a remainder below this is dust and does not interrupt - see below
_UNUSED   = int(sys.argv[4]) if len(sys.argv) > 4 else 0      # was TOP_BASE; the top-band
                                                             # alert is gone (V, 10-01 23:2x,
                                                             # to save tokens). Arg kept so the
                                                             # arm line and watch.args still fit.
REM_BASE  = int(sys.argv[5]) if len(sys.argv) > 5 else 0      # remainder-cancels already seen
REJECT_ALERT = 12          # a burst of post-only rejects since the restart
CAND60_FLAG  = '/home/ubuntu/maker_probe/.candles60.alerted'  # fires the 60-candle report once, ever
CAND200_FLAG = '/home/ubuntu/maker_probe/.candles200.alerted' # M21 out-of-sample mark, once, ever
M21_BAR = 200
# ANCHORED on the log-line format, and only lines NEWER than the arm time. The file is also the
# written record, and my own prose about hard stops matches a bare pattern on 4 lines - an
# unanchored grep would have cried wolf the moment it was pointed at the right file.
PAT = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] '
                 r'(HARD STOP|CANCEL ERROR|PASS ERROR|AMEND ERROR)')

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
    # 10-01 23:2x, V: the bar is now 60 DISTINCT GRADED CANDLES, not 60 graded fills. Candles, not
    # fills, is the honest unit - one calm candle can hand us several fills (the 09-30 17:00 candle
    # alone holds 15), so a fills bar can be reached on far fewer independent outcomes than it looks.
    # GRADED, not total: an unsettled fill carries no outcome. 60 is a REPORT, not a stop (owner) -
    # the latch fires it once, ever, so a re-arm keeps covering faults instead of re-reporting.
    cand = q('select count(distinct epoch) from fills where pnl is not null')
    # M21 (PREREG_M21_PROBE_OOS.md, V 10-02 10:4x): the out-of-sample evaluation point. Latched like
    # the 60 mark so it fires once and the watcher keeps covering faults afterwards. The cron twin in
    # m21_watch.py writes the same flag independently, so the mark is not missed if no watcher is up.
    if cand >= M21_BAR and not os.path.exists(CAND200_FLAG):
        open(CAND200_FLAG, 'w').write(str(cand))
        print(f'ALERT M21_200_CANDLES: {cand} distinct graded candles - run the M21 out-of-sample '
              f'evaluation (fills after 10-02 10:27 UTC only) and report to V'); break
    if cand >= 60 and not os.path.exists(CAND60_FLAG):
        open(CAND60_FLAG, 'w').write(str(cand))
        print(f'ALERT GRADED_60_CANDLES: {cand} distinct graded candles - run maker_60.py and send '
              f'the full report to V'); break
    # V, 10-01 20:5x then 23:2x: QUIET. No ping per fill, and no top-of-band ping either. The only
    # fill-driven interrupt left is A PARTIAL NEEDING A REMAINDER CANCEL - the remainder is live at the
    # venue until that cancel lands, and an orphaned remainder is the one shape here that can lose money
    # unwatched. Everything else that still speaks is a fault: process death, the flag going, an error
    # or hard stop in the log, a cash reject, or a reject storm.
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
        import datetime as _dt
        hits = []
        with open(LOG, errors='replace') as f:
            for ln in f:
                m = PAT.search(ln)
                if not m: continue
                t = _dt.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(
                    tzinfo=_dt.timezone.utc).timestamp() * 1000
                if t >= SINCE_MS: hits.append(ln)
        if hits: print('ALERT LOG: ' + hits[-1].strip()); break
    except OSError: pass
    time.sleep(20)
