#!/usr/bin/env python3
"""Session split for the calm FAV arm, for the 00:20 daily. READ-ONLY.

Owner asked for session timing; V's candidate under forward watch is FAV calm, EUROPE 07-13 UTC only
(analysis/v/maker2/SESSION_TEST.txt). Money here is priced at the REAL RECORDED ASK PLUS FEE -
cost = ask + 0.07*ask*(1-ask) on the fires.ask column, i.e. what was actually quoted - NOT the
arrival/partial fill model the FAV arms normally book. That is what the owner asked to see.

Carry V's own verdict with any positive number: the candidate was chosen on 09-11..20 (+81) and held on
sealed 09-21..30 (+59, 7/10 days), 20 days +140 at +1c - but +55 at +2c and -28 at +3c, where it broke,
and 11 of 12 arm x session cells lose on test. A ~2c/$1 edge is the size of 1-2c of execution error, so
V does not trust it. usage: session_split.py [since_epoch]"""
import sqlite3, sys, numpy as np, datetime as dt

SHADOW = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
SESS = [('Asia 00-07', 0, 7), ('Europe 07-13', 7, 13), ('US 13-20', 13, 20), ('Late 20-24', 20, 24)]
cost = lambda a: a + 0.07 * a * (1 - a)


def run(since):
    s = sqlite3.connect(f'file:{SHADOW}?mode=ro', uri=True)
    rows = s.execute("SELECT epoch,ask,win,fill FROM fires WHERE arm='FAV' AND epoch>=? ORDER BY epoch",
                     (since,)).fetchall()
    fills = [r for r in rows if r[3] is not None]
    hr = lambda e: dt.datetime.fromtimestamp(e, dt.UTC).hour
    pnl = lambda r: (10.0 / cost(r[1]) - 10.0) if r[2] else -10.0
    print(f'FAV (calm) BY UTC SESSION since {dt.datetime.fromtimestamp(since, dt.UTC):%m-%d %H:%M}, '
          f'$10/fill, priced at the REAL recorded ask + fee')
    print('  session        fills  wins   win%       $      maxDD   cum$')
    tot = 0.0
    for name, lo, hi in SESS:
        sub = [r for r in fills if lo <= hr(r[0]) < hi]
        p = np.array([pnl(r) for r in sub]) if sub else np.array([0.0])
        c = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
        w = sum(1 for r in sub if r[2]); tot += float(p.sum()) if sub else 0.0
        flag = '' if len(sub) >= 60 else '  INSUFFICIENT'
        print(f'  {name:13s} {len(sub):5d} {w:5d} {100*w/max(len(sub),1):5.1f}% {(p.sum() if sub else 0):+9.2f} '
              f'{dd:9.2f} {tot:+8.2f}{flag}')
    p = np.array([pnl(r) for r in fills]) if fills else np.array([0.0])
    c = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    print(f'  {"ALL":13s} {len(fills):5d} {sum(1 for r in fills if r[2]):5d} '
          f'{100*sum(1 for r in fills if r[2])/max(len(fills),1):5.1f}% {p.sum():+9.2f} {dd:9.2f}')
    eu = [r for r in fills if 7 <= hr(r[0]) < 13]
    pe = np.array([pnl(r) for r in eu]) if eu else np.array([0.0])
    ce = np.cumsum(pe); dde = float(np.max(np.maximum.accumulate(np.r_[0, ce]) - np.r_[0, ce]))
    print(f'\n  CANDIDATE under forward watch - FAV calm, Europe 07-13 only: n {len(eu)}, '
          f'$ {pe.sum():+.2f}, maxDD {dde:.2f}' + ('   INSUFFICIENT (<60 fills)' if len(eu) < 60 else ''))
    print('  V chose it on 09-11..20 (+81), held on sealed 09-21..30 (+59, 7/10 days), 20 days +140 at +1c')
    print('  - but +55 at +2c and -28 at +3c, where it BROKE, and 11 of 12 arm x session cells lose on test.')
    print('  A ~2c/$1 edge is the size of 1-2c of execution error. Not validated; forward watch only.')


if __name__ == '__main__':
    run(int(sys.argv[1]) if len(sys.argv) > 1 else int(dt.datetime(2026, 9, 29, tzinfo=dt.UTC).timestamp()))
