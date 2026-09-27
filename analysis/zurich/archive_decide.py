#!/usr/bin/env python3
"""Accumulating READ-ONLY export of the Zurich journal's research tables (V, 09-27).

The engine prunes: decide_log at 4 days (DECIDE_LOG_KEEP_S), tape1s and diagnostics at 7
(TAPE_KEEP_S). This copies the rows the REV-brain work needs into an archive OUTSIDE the engine's
directory before those prunes fire, so a 14-day sample can accumulate.

It touches NOTHING on the engine side: the source is ATTACHed with mode=ro, so SQLite itself refuses
any write to it, and no engine setting, retention constant or prune is changed. Nothing reads this
archive back into the engine.

Tables and why each dedupe rule is what it is:
  decide_log  PK ts_ms          rows are append-only -> INSERT OR IGNORE, incremental past max(ts_ms)
  tape1s      PK ts             append-only 1 Hz     -> INSERT OR IGNORE, incremental
              (pruned at 7 days, so the archive needs it or a 14-day rerun has no ask to price with)
  results     epoch UNIQUE      actual/payout/venue_*/shadow_* are filled in LATER, so a trailing
                                window is re-copied with INSERT OR REPLACE, keyed on epoch (the
                                source's autoincrement id is not carried - it is not meaningful here)
  signals     PK (epoch,kind)   status/attempts update after insert -> same trailing-window REPLACE.
                                `decision` is the column that carries feed_timing.
"""
import sqlite3, os, sys, time, datetime as dt

SRC = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LOG = '/home/ubuntu/pm_archive/archive.log'
REFRESH_S = 3 * 86400          # trailing window re-copied for the mutable tables

DDL = [
    """CREATE TABLE IF NOT EXISTS decide_log(ts_ms INTEGER PRIMARY KEY,epoch INTEGER,side TEXT,p REAL,
       p_raw REAL,ask REAL,ev REAL,fire INTEGER,up_ask REAL,dn_ask REAL,reason TEXT,feats TEXT)""",
    """CREATE TABLE IF NOT EXISTS tape1s(ts INTEGER PRIMARY KEY,spot_px REAL,spot_buy REAL,spot_sell REAL,
       perp_px REAL,perp_buy REAL,perp_sell REAL,bid5 REAL,ask5 REAL,bid20 REAL,ask20 REAL,ref_px REAL,
       up_ask REAL,dn_ask REAL)""",
    """CREATE TABLE IF NOT EXISTS results(epoch INTEGER PRIMARY KEY,actual TEXT,payout REAL,pnl REAL,ts REAL,
       claim_status TEXT,claim_id TEXT,claim_tries INTEGER,venue_pnl REAL,venue_realized_pnl REAL,
       venue_fees REAL,venue_value REAL,venue_ts REAL,pnl_basis TEXT,shadow_payout REAL,shadow_pnl REAL)""",
    """CREATE TABLE IF NOT EXISTS signals(epoch INTEGER,ts REAL,side TEXT,token TEXT,condition_id TEXT,
       decision TEXT,status TEXT,kind TEXT,attempts INTEGER,PRIMARY KEY(epoch,kind))""",
    """CREATE TABLE IF NOT EXISTS runs(ts REAL PRIMARY KEY,note TEXT)""",
]

def main():
    if not os.path.exists(SRC):
        print('source missing', SRC); return 2
    c = sqlite3.connect(ARCH, uri=False, timeout=60)
    c.execute('PRAGMA journal_mode=WAL')
    for d in DDL: c.execute(d)
    c.commit()
    c.execute(f"ATTACH DATABASE 'file:{SRC}?mode=ro' AS src")   # read-only: SQLite refuses any write
    n = {}
    hi = c.execute('SELECT coalesce(max(ts_ms),0) FROM decide_log').fetchone()[0]
    before = c.execute('SELECT count(*) FROM decide_log').fetchone()[0]
    c.execute('INSERT OR IGNORE INTO decide_log SELECT * FROM src.decide_log WHERE ts_ms>?', (hi,))
    n['decide_log'] = c.execute('SELECT count(*) FROM decide_log').fetchone()[0] - before

    hi = c.execute('SELECT coalesce(max(ts),0) FROM tape1s').fetchone()[0]
    before = c.execute('SELECT count(*) FROM tape1s').fetchone()[0]
    c.execute('INSERT OR IGNORE INTO tape1s SELECT * FROM src.tape1s WHERE ts>?', (hi,))
    n['tape1s'] = c.execute('SELECT count(*) FROM tape1s').fetchone()[0] - before

    cut = time.time() - REFRESH_S
    before = c.execute('SELECT count(*) FROM results').fetchone()[0]
    c.execute("""INSERT OR REPLACE INTO results SELECT epoch,actual,payout,pnl,ts,claim_status,claim_id,
                 claim_tries,venue_pnl,venue_realized_pnl,venue_fees,venue_value,venue_ts,pnl_basis,
                 shadow_payout,shadow_pnl FROM src.results WHERE epoch>=? OR epoch NOT IN
                 (SELECT epoch FROM results)""", (cut,))
    n['results'] = c.execute('SELECT count(*) FROM results').fetchone()[0] - before

    before = c.execute('SELECT count(*) FROM signals').fetchone()[0]
    c.execute("""INSERT OR REPLACE INTO signals SELECT epoch,ts,side,token,condition_id,decision,status,
                 kind,attempts FROM src.signals WHERE epoch>=? OR (epoch,kind) NOT IN
                 (SELECT epoch,kind FROM signals)""", (cut,))
    n['signals'] = c.execute('SELECT count(*) FROM signals').fetchone()[0] - before

    tot = {t: c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('decide_log', 'tape1s', 'results', 'signals')}
    a, b = c.execute('SELECT min(ts_ms),max(ts_ms) FROM decide_log').fetchone()
    days = ((b - a) / 86400000.0) if a else 0.0
    c.execute('INSERT OR REPLACE INTO runs VALUES(?,?)', (time.time(), repr({'new': n, 'total': tot})))
    c.commit(); c.execute('DETACH DATABASE src'); c.close()
    mb = os.path.getsize(ARCH) / 1048576.0
    f = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime('%m-%d %H:%M') if ms else '-'
    line = (f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}Z new {n} total {tot} '
            f'decide_log span {f(a)}->{f(b)} = {days:.2f}d  archive {mb:.1f} MB '
            f'({mb/max(days,1e-9):.1f} MB/day)')
    print(line)
    with open(LOG, 'a') as fh: fh.write(line + '\n')
    return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as e:
        msg = f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}Z FAILED {type(e).__name__}: {e}'
        print(msg)
        with open(LOG, 'a') as fh: fh.write(msg + '\n')
        sys.exit(1)
