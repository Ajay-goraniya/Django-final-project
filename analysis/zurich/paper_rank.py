#!/usr/bin/env python3
"""Every paper/shadow arm running on Zurich, ranked by per $1. READ-ONLY, nothing live."""
import sqlite3, math, collections
import datetime as dt
import numpy as np
D=lambda t: dt.datetime.fromtimestamp(t,dt.UTC)
day=lambda t: D(t).strftime('%m-%d')
ro=lambda p: sqlite3.connect(f'file:{p}?mode=ro',uri=True)
R=[]   # (group, arm, start, n, total, per1, t, green/nd, model, live)
def add(group,arm,eps,pnl,dep,model,live=True):
    v=np.asarray(pnl,float); e=list(eps)
    if not len(v): R.append((group,arm,'-',0,0.0,0.0,0.0,'0/0',model,live)); return
    t=v.mean()/v.std(ddof=1)*math.sqrt(len(v)) if len(v)>1 and v.std(ddof=1)>0 else 0.0
    g=collections.defaultdict(float)
    for x,p in zip(e,v): g[day(x)]+=p
    R.append((group,arm,day(min(e)),len(v),v.sum(),(v.sum()/dep if dep else 0.0),t,
              f'{sum(1 for z in g.values() if z>0)}/{len(g)}',model,live))

# ---- 1. ef3_shadow: every arm. FAV* on the registered PARTIAL model, everything else AON $10/fill.
c=ro('/home/ubuntu/pm_ef3/ef3_shadow.sqlite3')
arms=[a for (a,) in c.execute('select distinct arm from fires order by arm')]
for a in arms:
    r=c.execute('select epoch,fill,win,pnl,pnl_part,sh,vwap from fires where arm=? order by epoch',(a,)).fetchall()
    if a.startswith('FAV'):
        got=[x for x in r if (x[5] or 0)>0]
        add('ef3 shadow',a,[x[0] for x in got],[x[4] for x in got],
            sum((x[5] or 0)*(x[6] or 0) for x in got),'partial arrival fill')
    else:
        fl=[x for x in r if x[1] is not None]
        add('ef3 shadow',a,[x[0] for x in fl],[x[3] for x in fl],10.0*len(fl),'AON $10/fill')

# ---- 2. M19 paper maker: 8 arms = (margin m, delay)
c=ro('/home/ubuntu/m19_paper/m19_paper.sqlite3')
for m,d in c.execute('select distinct m,delay_ms from fills order by m,delay_ms'):
    r=c.execute('select ts_ms/1000,pnl,spent from fills where m=? and delay_ms=? and outcome is not null '
                'and pnl is not null order by ts_ms',(m,d)).fetchall()
    add('M19 paper maker',f'm{m:.2f} D{d}',[x[0] for x in r],[x[1] for x in r],
        sum(x[2] for x in r),'post-only, own bid')

# ---- 3. ETH / SOL engine shadows (own DBs, own stake)
for nm,p in (('eth','shadow_eth'),('eth_platt','shadow_eth_platt'),
             ('sol','shadow_sol'),('sol_platt','shadow_sol_platt')):
    c=ro(f'/home/ubuntu/pm_multi/{p}.sqlite3')
    r=c.execute('select r.epoch,r.pnl,o.spent from results r join orders o on o.epoch=r.epoch '
                'where r.pnl is not null order by r.epoch').fetchall()
    add('ETH/SOL shadow',nm,[x[0] for x in r],[x[1] for x in r],sum(x[2] or 0 for x in r),'engine taker')

# ---- 4. v12_2 pair bot (15m vs 5m legging, paper, stake 20)
c=ro('/home/ubuntu/pm_pair/pair_paper.sqlite3')
r=c.execute('select ep5,pnl,spent15,spent5 from pairs where pnl is not null order by ep5').fetchall()
add('pair bot','v12_2 pair 15m/5m',[x[0] for x in r],[x[1] for x in r],
    sum((x[2] or 0)+(x[3] or 0) for x in r),'paper, stake 20')

# ---- 5. ef2 shadow: dead, kept visible on purpose
c=ro('/home/ubuntu/pm_ef2shadow/ef2_shadow.sqlite3')
r=c.execute('select epoch,win,fill_price from fires where filled=1 and win is not null').fetchall()
add('ef2 shadow','margin arms (DEAD)',[x[0] for x in r],[0.0]*len(r),0.0,'no pnl column',live=False)

print('EVERY PAPER / SHADOW ARM ON ZURICH, ranked by per $1 inside each group')
print(f'{"group":17s} {"arm":22s} {"start":6s} {"n":>5s} {"$":>9s} {"per $1":>8s} {"t":>6s} {"green":>6s} '
      f'{"flag":28s} fill model')
for grp in ('ef3 shadow','M19 paper maker','ETH/SOL shadow','pair bot','ef2 shadow'):
    rows=sorted([x for x in R if x[0]==grp], key=lambda x:-x[5])
    print()
    for g,a,s,n,tot,p1,t,gr,mdl,live in rows:
        fl=[]
        if not live: fl.append('STOPPED')
        if n<60: fl.append('n<60 NOT PROVEN')
        if abs(t)<2: fl.append('|t|<2 NOT PROVEN')
        print(f'{g:17s} {a:22s} {s:6s} {n:5d} {tot:+9.2f} {p1:+8.4f} {t:+6.2f} {gr:>6s} '
              f'{",".join(fl) if fl else "":28s} {mdl}')
