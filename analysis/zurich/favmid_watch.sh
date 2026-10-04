#!/bin/bash
# Watch the FAV_mid live test. Exits when the OLDEST still-open live candle settles, or on an alert.
# The epoch is looked up each pass - an earlier version hardcoded one, so after it settled the watcher
# fired instantly on stale news every time it was re-armed.
until /home/ubuntu/pm_paper_zurich/.venv/bin/python - <<'PY'
import sqlite3, json, sys, datetime as dt
from zoneinfo import ZoneInfo
B=1790736036
c=sqlite3.connect('file:/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3?mode=ro',uri=True)
alerts=[]
for k,n in c.execute("SELECT kind,count(*) FROM orders WHERE ts>? AND kind!='EF' GROUP BY kind",(B,)):
    alerts.append(f'ALERT non-EF lane ordered: {k} x{n}')
eps=sorted({e for (e,) in c.execute("SELECT DISTINCT epoch FROM orders WHERE lane='LIVE' AND ts>? AND kind='EF'",(B,))})
for ep in eps:
    r=c.execute("SELECT decision FROM signals WHERE epoch=? AND kind='EF'",(ep,)).fetchone()
    if not r: continue
    d=json.loads(r[0]); fv=d.get('fav') or {}; sec=d.get('sec'); v=fv.get('vol')
    if sec is None or not (60<=sec<=180): alerts.append(f'ALERT epoch {ep} sec {sec} OUTSIDE 60-180')
    if v is None or not (0.304<=v<0.466): alerts.append(f'ALERT epoch {ep} vol {v} OUTSIDE mid band')
    if d.get('engine')!='fav_mid': alerts.append(f'ALERT epoch {ep} engine {d.get("engine")} NOT fav_mid')
L=ZoneInfo('Europe/London'); now=dt.datetime.now(L)
st=now.replace(hour=12,minute=0,second=0,microsecond=0)
if now<st: st-=dt.timedelta(days=1)
p=c.execute("SELECT coalesce(sum(pnl),0) FROM results WHERE ts>=?",(st.timestamp(),)).fetchone()[0]
if p<=-40.0: alerts.append(f'ALERT DAILY STOP TRIGGERED, window pnl {p:+.2f}')
if alerts: print('\n'.join(alerts)); sys.exit(0)
# the oldest live candle with no settled pnl yet
for ep in eps:
    r=c.execute("SELECT actual,payout,pnl FROM results WHERE epoch=?",(ep,)).fetchone()
    if not r or r[2] is None: sys.exit(1)          # still open, keep waiting
print('ALL LIVE CANDLES SETTLED: '+', '.join(
  f"{ep}:{c.execute('SELECT actual,pnl FROM results WHERE epoch=?',(ep,)).fetchone()[0]}"
  f"{c.execute('SELECT pnl FROM results WHERE epoch=?',(ep,)).fetchone()[0]:+.4f}" for ep in eps))
sys.exit(0)
PY
do sleep 30; done
