#!/usr/bin/env python3
"""FAV_mid live daemon, V's token policy 09-30: append every trade to FAVMID_LIVE.txt and push to git.
NO Routine per trade. It exits non-zero with ALERT lines ONLY for the five conditions V listed, which is
the signal for the session to send ONE line to V:
    1 a non-EF lane order
    2 an order outside 60-180 s or outside the mid band
    3 the daily stop firing  (read from meta sl LIVE - the owner moved it 40 -> 50, so a hardcoded 40
      would have fired a false alert; never hardcode a threshold the owner can change)
    4 engine down
    5 feeds dead
READ-ONLY on the engine. The only thing it writes is the report file and git."""
import sqlite3, json, os, subprocess, sys, time, datetime as dt
from zoneinfo import ZoneInfo

DB='/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
REPO='/home/ubuntu/claude-work/repo'
DOC=f'{REPO}/analysis/zurich/FAVMID_LIVE.txt'
STATE='/home/ubuntu/pm_ef3/favmid_daemon_state.json'
BASE=1790736036
FEED_MAX_S=180

def q(sql,a=()):
    c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
    try: return c.execute(sql,a).fetchall()
    finally: c.close()

def meta(k):
    r=q("SELECT v FROM meta WHERE k=?",(k,))
    return None if not r else r[0][0]

def st_load():
    try: return json.load(open(STATE))
    except Exception: return {'ordered':[],'settled':[]}

def alerts():
    out=[]
    for k,n in q("SELECT kind,count(*) FROM orders WHERE ts>? AND kind!='EF' GROUP BY kind",(BASE,)):
        out.append(f'non-EF lane ordered: {k} x{n}')
    for (ep,) in q("SELECT DISTINCT epoch FROM orders WHERE lane='LIVE' AND ts>? AND kind='EF'",(BASE,)):
        r=q("SELECT decision FROM signals WHERE epoch=? AND kind='EF'",(ep,))
        if not r: continue
        d=json.loads(r[0][0]); fv=d.get('fav') or {}
        sec=d.get('sec'); v=fv.get('vol')
        if sec is None or not (60<=sec<=180): out.append(f'epoch {ep} sec {sec} OUTSIDE 60-180')
        if v is None or not (0.304<=v<0.466): out.append(f'epoch {ep} vol {v} OUTSIDE mid band')
        if d.get('engine')!='fav_mid': out.append(f'epoch {ep} engine {d.get("engine")} NOT fav_mid')
    try: sl=float(meta('sl') or 0)
    except Exception: sl=0.0
    if sl>0:
        L=ZoneInfo('Europe/London'); now=dt.datetime.now(L)
        s=now.replace(hour=12,minute=0,second=0,microsecond=0)
        if now<s: s-=dt.timedelta(days=1)
        p=q("SELECT coalesce(sum(pnl),0) FROM results WHERE ts>=?",(s.timestamp(),))[0][0]
        if p<=-sl: out.append(f'DAILY STOP FIRED: window pnl {p:+.2f} <= -{sl:.0f}')
    alive=any('btc_model_v12_polymarket' in open(d+'/cmdline','rb').read().decode('utf8','replace')
              for d in __import__('glob').glob('/proc/[0-9]*') if os.path.exists(d+'/cmdline'))
    if not alive: out.append('ENGINE DOWN: no btc_model_v12_polymarket process')
    now=time.time()
    for name,sql in (('decide_log','SELECT max(ts_ms) FROM decide_log'),('tape1s','SELECT max(ts) FROM tape1s')):
        v=q(sql)[0][0]
        if v is None: out.append(f'FEED DEAD: {name} empty'); continue
        v=v/1000 if v>2e10 else v
        if now-v>FEED_MAX_S: out.append(f'FEED DEAD: {name} {int(now-v)} s stale')
    return out

def append_new():
    s=st_load(); new=[]
    for oid,ep,ts,status,plan in q("SELECT id,epoch,ts,status,plan FROM orders WHERE lane='LIVE' AND ts>? "
                                   "AND kind='EF' ORDER BY ts",(BASE,)):
        key=f'{oid}'
        if key in s['ordered']: continue
        pl=json.loads(plan) if plan else {}
        sig=q("SELECT side,decision FROM signals WHERE epoch=? AND kind='EF'",(ep,))
        d=json.loads(sig[0][1]) if sig else {}; fv=d.get('fav') or {}
        fl=q("SELECT sum(shares),sum(spent),sum(fees) FROM fills WHERE order_id=?",(oid,))[0]
        f=lambda t: dt.datetime.fromtimestamp(t,dt.UTC).strftime('%m-%d %H:%M:%S')
        n=lambda v,w='.4f': 'n/a' if v is None else format(v,w)
        new.append(f"  ORDER {f(ts)} candle {f(ep)[6:11]} sec {d.get('sec')} vol {fv.get('vol')} "
                   f"{d.get('side')} ask {n(pl.get('quote'),'.2f')} {status} "
                   f"shares {n(fl[0])} spent {n(fl[1])} fees {n(fl[2],'.5f')} stake_at_the_time ${n(pl.get('budget'),'.2f')}")
        s['ordered'].append(key)
    for (ep,) in q("SELECT DISTINCT epoch FROM orders WHERE lane='LIVE' AND ts>? AND kind='EF'",(BASE,)):
        if str(ep) in s['settled']: continue
        r=q("SELECT actual,payout,pnl FROM results WHERE epoch=?",(ep,))
        if not r or r[0][2] is None: continue
        f=lambda t: dt.datetime.fromtimestamp(t,dt.UTC).strftime('%m-%d %H:%M')
        new.append(f"  SETTLED candle {f(ep)[6:11]} actual {r[0][0]} payout {r[0][1]:.4f} pnl {r[0][2]:+.4f}")
        s['settled'].append(str(ep))
    if new:
        with open(DOC,'a') as fh:
            fh.write(f"\n[{dt.datetime.now(dt.UTC):%m-%d %H:%M:%S} UTC]\n"+"\n".join(new)+"\n")
        json.dump(s,open(STATE,'w'))
        subprocess.run(['git','add','analysis/zurich/FAVMID_LIVE.txt'],cwd=REPO,check=False)
        subprocess.run(['git','commit','-q','-m',f'FAV_mid live: {len(new)} new row(s)'],cwd=REPO,check=False)
        subprocess.run(['git','fetch','-q','origin'],cwd=REPO,check=False)
        subprocess.run(['git','rebase','-q','origin/claude/your-task-3wbq8u'],cwd=REPO,check=False)
        subprocess.run(['git','push','-q','origin','claude/your-task-3wbq8u'],cwd=REPO,check=False)
    return len(new)

while True:
    a=alerts()
    if a:
        print('ALERT\n'+'\n'.join('  '+x for x in a)); sys.exit(2)
    append_new()
    time.sleep(60)
