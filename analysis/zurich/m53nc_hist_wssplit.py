#!/usr/bin/env python3
import sqlite3, collections, math, statistics as st, sys, io, contextlib
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
with contextlib.redirect_stdout(io.StringIO()):
    import ef3_shadow as S
    S.ALL52,S.STRICT=None,None; BN=S._bn_1s()
CUT=S.FAV_CUT_LOW; STAKE,FEE,SLIP=5.0,0.07,0.016
be=lambda a: a*(1+FEE*(1-a))
mm=sqlite3.connect('file:/home/ubuntu/pm_multi/multi_market.sqlite3?mode=ro',uri=True)
m53=sqlite3.connect('file:/home/ubuntu/m53/m53.sqlite3?mode=ro',uri=True)
BK=collections.defaultdict(dict)
for ts,ep,ua,us,da,ds in mm.execute("select ts,epoch,up_ask,up_ask_sz,dn_ask,dn_ask_sz from books where market='btc5'"):
    BK[int(ep)][int(ts)-int(ep)]=(ua,us,da,ds)
UP={}
for ep,a in sqlite3.connect('file:/home/ubuntu/m29/venues.sqlite3?mode=ro',uri=True).execute('select epoch,actual from outcome where actual is not null'): UP[int(ep)]=(a=='UP')
for ep,o in sqlite3.connect('file:/home/ubuntu/pm_ef3/gamma_zurich.sqlite3?mode=ro',uri=True).execute("select epoch,outcome from mkt where outcome is not null and asset='btc'"): UP[int(ep)]=(o=='UP')
def ask(ep,sec,side):
    for d in (0,1,-1,2,-2):
        v=BK[ep].get(int(round(sec))+d)
        if v:
            a=v[0] if side=='UP' else v[2]
            if a is not None: return float(a)
    return None
rows=m53.execute("select epoch,print_ts,side from dec where src='clob_ws'").fetchall()
for delay,lab in ((0.25,'entry +250 ms (B / live NC arm)'),(3.0,'entry +3 s   (legacy arm)      ')):
    for calmflag,nm in ((False,'NOT-CALM'),(True,'CALM    ')):
        pn=[]
        for ep,pt,sd in rows:
            ep=int(ep)
            if ep not in UP: continue
            v=S._vol_bn(BN,ep)
            if v is None or (v<CUT)!=calmflag: continue
            a=ask(ep,(float(pt)-ep)+delay,sd)
            if a is None: continue
            a=min(a+SLIP,0.99)
            if a>=0.99: continue
            sh=STAKE/be(a); win=1 if ((sd=='UP')==UP[ep]) else 0
            pn.append((sh if win else 0.0)-STAKE)
        if pn:
            t=st.mean(pn)/st.stdev(pn)*math.sqrt(len(pn)) if len(pn)>1 and st.stdev(pn)>0 else 0
            print(f'    {lab}  {nm}  n {len(pn):4d}  ${sum(pn):+8.2f}  per $1 {sum(pn)/(STAKE*len(pn)):+.4f}  t {t:+5.2f}'
                  + ('  INSUFFICIENT (n<60)' if len(pn)<60 else ''))
