#!/usr/bin/env python3
"""P1 part 3: EF's would-fire stream out of the Zurich shadow, so V can join fires to Predict asks.

READ-ONLY on the shadow (mode=ro) and writes only its own sqlite. One row per EF fire: the side, the
fire timestamp and the MODEL probability - which is what P2 needs to price each fire at Predict's own
ask at fire time rather than at Polymarket's (the cross-venue grading error CLAUDE.md bans).

Only the MODEL arms are exported. C_fixed15 and B_raw25_S60 carry a model p; the FAV family is a
market rule with no model (its 'p' is the favourite's own ask) and exporting it as a model p would
invite exactly the confusion this file exists to avoid. The arm is kept on every row so nothing has
to be inferred later.
"""
import sqlite3, time

SHADOW = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
OUT = '/home/ubuntu/predict_p1/predict_quotes.sqlite3'
ARMS = ('C_fixed15', 'B_raw25_S60')


def main():
    o = sqlite3.connect(OUT, timeout=30)
    o.executescript("""
    create table if not exists ef_fire(
      arm text, epoch integer, fire_ts_ms integer, side text, p real, ask real, sec integer,
      win integer, primary key(arm, epoch));
    create index if not exists ix_fire_ts on ef_fire(fire_ts_ms);""")
    o.commit()
    s = sqlite3.connect(f'file:{SHADOW}?mode=ro', uri=True)
    q = ('select arm, epoch, ts_ms, up, p, ask, sec, win from fires '
         'where arm in (%s)' % ','.join('?' * len(ARMS)))
    rows = s.execute(q, ARMS).fetchall()
    s.close()
    before = o.execute('select count(*) from ef_fire').fetchone()[0]
    for arm, ep, ts, up, p, ask, sec, win in rows:
        o.execute('insert or replace into ef_fire values(?,?,?,?,?,?,?,?)',
                  (arm, ep, ts, 'UP' if up else 'DOWN', p, ask, sec, win))
    o.commit()
    after = o.execute('select count(*) from ef_fire').fetchone()[0]
    print(f'{time.strftime("%F %T", time.gmtime())} ef_fire {before} -> {after} '
          f'({after - before} new) from {len(rows)} shadow rows', flush=True)
    for arm, n, lo, hi in o.execute('select arm, count(*), min(fire_ts_ms), max(fire_ts_ms) '
                                    'from ef_fire group by arm'):
        import datetime as dt
        print(f'  {arm}: {n} fires, {dt.datetime.fromtimestamp(lo/1000, dt.UTC):%m-%d %H:%M} .. '
              f'{dt.datetime.fromtimestamp(hi/1000, dt.UTC):%m-%d %H:%M}', flush=True)


if __name__ == '__main__':
    main()
