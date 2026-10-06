#!/usr/bin/env python3
"""Hourly status: M53-NC (the live-fill, not-calm arm, prereg 3224c11) then one short legacy line
for the uncapped all-candle M53. READ-ONLY apart from the cached `calm` flag on the legacy table."""
import sqlite3, math, statistics as st

STAKE, START_CASH = 5.0, 50.0
NC = int(open('/home/ubuntu/m53/nc_start_epoch').read().strip())
SW = int(open('/home/ubuntu/m53/switch_epoch').read().strip())
d = sqlite3.connect('/home/ubuntu/m53/m53.sqlite3', timeout=30)

# ---------------- M53-NC ----------------
r = d.execute('select status,win,pnl,spent,slip,latency_ms,shares from nc where epoch>=?', (NC,)).fetchall()
cnt = lambda s: sum(1 for x in r if x[0] == s)
full, part = cnt('full'), cnt('partial')
missed = sum(1 for x in r if (x[0] or '').startswith('missed'))
nodata, calmskip, cashskip = cnt('skipped-no-data'), cnt('skipped-calm'), cnt('skipped-cash')
s = [x for x in r if x[0] in ('full', 'partial') and x[1] is not None]
w = sum(1 for x in s if x[1] == 1)
pnl = sum(x[2] or 0 for x in s); dep = sum(x[3] or 0 for x in s)
t = 0.0
if len(s) > 1:
    v = [x[2] or 0 for x in s]
    t = (st.mean(v) / st.stdev(v) * math.sqrt(len(v))) if st.stdev(v) > 0 else 0.0
_sp, _cr = d.execute("select coalesce(sum(spent),0), coalesce(sum(case when win=1 then shares else 0 end),0) "
                     "from nc where status in ('full','partial')").fetchone()
cash = START_CASH - (_sp or 0) + (_cr or 0)      # DERIVED, never chained - see m53nc_paper.cash_now
sl = [x[4] for x in r if x[4] is not None]; la = [x[5] for x in r if x[5] is not None]
print(f"M53-NC (prereg 3224c11) since epoch {NC}: signals {len(r)}, full {full} / partial {part} / "
      f"missed {missed} / skipped-no-data {nodata} (also skipped-calm {calmskip}, skipped-cash {cashskip}); "
      f"settled {len(s)}, {w}W-{len(s)-w}L, ${pnl:+.2f}, per $1 {(pnl/dep if dep else 0):+.4f}, "
      f"t {t:+.2f}, bankroll ${cash:.2f} (from ${START_CASH:.0f}); median slip "
      f"{(st.median(sl) if sl else 0):+.4f}, median latency {int(st.median(la)) if la else 0}ms")

# ---------------- legacy reference ----------------
g = d.execute('select fill3_unc,win,pnl3_unc from dec where epoch>=? and src=?', (SW, 'clob_ws')).fetchall()
f2 = [x for x in g if x[0] == 1 and x[1] is not None]
w2 = sum(1 for x in f2 if x[1] == 1); p2 = sum(x[2] or 0 for x in f2)
print(f"LEGACY M53 uncapped, all candles, since 03:30Z: settled {len(f2)}, {w2}W-{len(f2)-w2}L, "
      f"${p2:+.2f} @$5, per $1 {(p2/(STAKE*len(f2)) if f2 else 0):+.4f}")
