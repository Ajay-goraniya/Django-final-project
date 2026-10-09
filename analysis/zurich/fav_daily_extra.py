#!/usr/bin/env python3
"""The extra sections of the FAV daily ledger: cumulative, PFAV vs PFAV_THRU, the calm-FAV session
split, and the maker-probe line. READ-ONLY.  usage: fav_daily_extra.py YYYY-MM-DD [since]

The per-arm aggregation is the SAME rule fav_daily.py uses - prefer the partial arrival fill
(pnl_part, with filled shares as the floor) and fall back to the whole-fill pnl only for arms that
have no partial column - so a row here is comparable with the day table above it instead of being a
second, quietly different definition of the same arm.
"""
import sys, sqlite3, datetime as dt
import numpy as np

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
DB     = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
MAKER  = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
ARMS   = ('FAV', 'FAV_mid', 'FAV_all', 'FAV_ref', 'C_fixed15')
SESSION = (('Asia 00-07', 0, 7), ('Europe 07-13', 7, 13), ('US 13-20', 13, 20), ('Late 20-24', 20, 24))
BAR = 60

D = sys.argv[1]
d0 = dt.datetime.strptime(D, '%Y-%m-%d').replace(tzinfo=dt.UTC)
END = int((d0 + dt.timedelta(days=1)).timestamp())
SINCE = (int(dt.datetime.strptime(sys.argv[2], '%Y-%m-%d').replace(tzinfo=dt.UTC).timestamp())
         if len(sys.argv) > 2 else int(dt.datetime(2026, 9, 29, tzinfo=dt.UTC).timestamp()))
sh = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


def agg(arm, a, b, where='', args=()):
    """(decisions, fills, wins, pnl, maxDD, pnl_1c) on the fav_daily convention."""
    r = sh.execute(f'SELECT fill,win,pnl,pnl_part,sh,pnl_1c FROM fires WHERE arm=? AND epoch>=? '
                   f'AND epoch<? {where} ORDER BY epoch', (arm, a, b) + args).fetchall()
    part = [x for x in r if x[3] is not None]
    if part:
        got = [x for x in part if (x[4] or 0) > 0]
        pn = np.array([x[3] for x in part], float)
        nf, w = len(got), sum(x[1] for x in got)
    else:
        fl = [x for x in r if x[0] is not None]
        pn = np.array([x[2] for x in r], float) if r else np.array([0.0])
        nf, w = len(fl), sum(x[1] for x in fl)
    c = np.cumsum(pn)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    one = [x[5] for x in r if x[5] is not None]
    return len(r), nf, w, pn.sum(), dd, (sum(one) if one else None)


def table(title, rows, extra_1c=False):
    print()
    print(title)
    head = ('arm          decisions  fills  wins     $@10   $@10+1c   maxDD   flag' if extra_1c else
            'arm          decisions  fills  wins     $@10    maxDD   flag')
    print(head)
    for name, (n, nf, w, pnl, dd, one) in rows:
        flag = 'INSUFFICIENT (<60 fills)' if nf < BAR else ''
        if extra_1c:
            o = f'{one:+9.2f}' if one is not None else '        -'
            print(f'{name:11s} {n:9d} {nf:6d} {w:5d} {pnl:+8.2f} {o} {dd:7.2f}   {flag}')
        else:
            print(f'{name:11s} {n:9d} {nf:6d} {w:5d} {pnl:+8.2f} {dd:8.2f}   {flag}')


days = int((END - SINCE) / 86400)
table(f'CUMULATIVE {dt.datetime.fromtimestamp(SINCE, dt.UTC):%m-%d} .. {D[5:]} '
      f'({days} full days), $10 a fill, REAL recorded ask + exact fee',
      [(a, agg(a, SINCE, END)) for a in ARMS])

table('PFAV vs PFAV_THRU, the SAME day as the table above. +1c = the same trade paying one cent more.',
      [(a, agg(a, int(d0.timestamp()), END)) for a in ('PFAV', 'PFAV_THRU')], extra_1c=True)

print()
print('CALM-FAV BY UTC SESSION, same day (real recorded ask + fee)')
print('session        decisions  fills  wins     $@10    maxDD   flag')
for label, h0, h1 in SESSION:
    a = int(d0.timestamp()) + h0 * 3600
    b = int(d0.timestamp()) + h1 * 3600
    n, nf, w, pnl, dd, _ = agg('FAV', a, b)
    print(f'{label:14s} {n:9d} {nf:6d} {w:5d} {pnl:+8.2f} {dd:8.2f}   '
          + ('INSUFFICIENT (<60 fills)' if nf < BAR else ''))

seen = sh.execute('SELECT count(*) FROM seen WHERE epoch>=? AND epoch<?',
                  (int(d0.timestamp()), END)).fetchone()[0]
print()
print(f'coverage: {seen} candles scored on {D} (of 288).')

# ---- the maker probe, which is a LIVE process and not part of the shadow at all ----------------
print()
print('MAKER PROBE (live, separate process, NOT part of the shadow)')
try:
    mk = sqlite3.connect(f'file:{MAKER}?mode=ro', uri=True); mk.row_factory = sqlite3.Row
    g = [dict(r) for r in mk.execute('SELECT * FROM fills WHERE pnl IS NOT NULL AND utc_day=?', (D,))]
    un = mk.execute('SELECT count(*) FROM fills WHERE pnl IS NULL AND utc_day=?', (D,)).fetchone()[0]
    lg = [dict(r) for r in mk.execute('SELECT * FROM fills WHERE pnl IS NOT NULL')]
    w = sum(1 for x in g if x['pnl'] > 0); l = sum(1 for x in g if x['pnl'] < 0)
    dep = sum(x['spent'] for x in g)
    print(f'  {D}: {len(g)} graded fills over {len({x["epoch"] for x in g})} distinct candles, '
          f'{w}W/{l}L, {sum(x["pnl"] for x in g):+.4f} on ${dep:.2f} deployed '
          f'({sum(x["pnl"] for x in g)/max(dep,1e-9):+.4f} per $1), venue-graded'
          + (f'; {un} unsettled and excluded rather than guessed' if un else ''))
    print(f'  lifetime: {len(lg)} graded fills over {len({x["epoch"] for x in lg})} candles, '
          f'{sum(x["pnl"] for x in lg):+.4f} of the -20 stop'
          + ('  INSUFFICIENT (<60 fills)' if len(g) < BAR else ''))
    print('  5 shares a post-only BUY, maker fee 0, held to settlement. Distinct CANDLES is the '
          'honest sample here, not fills: one calm candle can hand us several.')
    mk.close()
except Exception as e:
    print(f'  maker probe db unreadable: {type(e).__name__}: {e}')
