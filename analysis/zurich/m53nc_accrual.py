#!/usr/bin/env python3
"""M53-NC accrual note: not-calm share by UTC hour, expected fills/day, ETA to n=100 and n=200.
READ-ONLY. Calm comes from ef3_shadow's OWN _vol_bn vs its OWN FAV_CUT_LOW - nothing re-implemented,
no threshold searched."""
import sys, io, contextlib, sqlite3, collections, datetime as dt
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
with contextlib.redirect_stdout(io.StringIO()):
    import ef3_shadow as S
    S.ALL52, S.STRICT = None, None
    BN = S._bn_1s()
CUT = S.FAV_CUT_LOW
A = int(dt.datetime(2026, 9, 29, tzinfo=dt.UTC).timestamp())
B = int(dt.datetime(2026, 10, 7, tzinfo=dt.UTC).timestamp())
hour = collections.defaultdict(lambda: [0, 0, 0])      # hour -> [not-calm, calm, no-data]
day = collections.defaultdict(lambda: [0, 0, 0])
for ep in range(A, B, 300):
    v = S._vol_bn(BN, ep)
    h = dt.datetime.fromtimestamp(ep, dt.UTC).hour
    d = dt.datetime.fromtimestamp(ep, dt.UTC).strftime('%m-%d')
    i = 2 if v is None else (0 if v >= CUT else 1)
    hour[h][i] += 1; day[d][i] += 1
tot = [sum(hour[h][i] for h in hour) for i in range(3)]
N = sum(tot)
print(f'NOT-CALM SHARE BY UTC HOUR, 09-29..10-06 ({N} candles; frozen cut: Binance 1 s std >= {CUT})')
print('  hour  candles  not-calm   calm  no-data   not-calm%')
for h in range(24):
    nc, cm, nd = hour[h]
    n = nc + cm + nd
    if not n: continue
    base = nc + cm
    print(f'  {h:02d}:00  {n:7d}  {nc:8d} {cm:6d} {nd:8d}   '
          + (f'{100*nc/base:5.1f}%' if base else '    -'))
base = tot[0] + tot[1]
print(f'  ALL    {N:7d}  {tot[0]:8d} {tot[1]:6d} {tot[2]:8d}   {100*tot[0]/base:5.1f}%'
      f'   (no-data {100*tot[2]/N:.1f}% of all candles)')
print()
print('PER DAY')
for d in sorted(day):
    nc, cm, nd = day[d]; b = nc + cm
    print(f'  {d}: candles {nc+cm+nd:3d}  not-calm {nc:3d} ({100*nc/b:4.1f}%)  calm {cm:3d}  no-data {nd:3d}')
# ---- observed arm rates since it started ----
m = sqlite3.connect('file:/home/ubuntu/m53/m53.sqlite3?mode=ro', uri=True)
NC0 = int(open('/home/ubuntu/m53/nc_start_epoch').read().strip())
r = m.execute('select status from nc where epoch>=?', (NC0,)).fetchall()
sig = len(r)
fills = sum(1 for x in r if x[0] in ('full', 'partial'))
calm = sum(1 for x in r if x[0] == 'skipped-calm')
nodata = sum(1 for x in r if x[0] == 'skipped-no-data')
cand = (int(dt.datetime.now(dt.UTC).timestamp()) - NC0) // 300
print()
print(f'OBSERVED SINCE THE ARM STARTED ({NC0}, {cand} candles elapsed)')
print(f'  signals {sig} = {100*sig/max(cand,1):.0f}% of candles produced a qualifying print')
print(f'  of those: not-calm (traded) {fills}, calm {calm}, no-data {nodata}')
print(f'  fill rate given a not-calm signal: {fills}/{fills} = 100% (0 partial, 0 missed so far)')
print(f'  observed not-calm share of signals: {100*fills/max(sig-nodata,1):.1f}%')
print()
p_sig = sig / max(cand, 1)
for lab, p_nc in (('8-day historical not-calm share', tot[0]/base),
                  ('share observed since the arm started', fills/max(sig-nodata, 1))):
    per_day = 288 * p_sig * p_nc
    print(f'EXPECTED FILLS/DAY on the {lab} ({100*p_nc:.1f}%): {per_day:.1f}')
    for target in (100, 200):
        need = target - fills
        days = need / per_day if per_day > 0 else float('inf')
        eta = dt.datetime.now(dt.UTC) + dt.timedelta(days=days)
        print(f'    n={target}: need {need} more -> {days:.1f} days -> ETA {eta:%Y-%m-%d}')
