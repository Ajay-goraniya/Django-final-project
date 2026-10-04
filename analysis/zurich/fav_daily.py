#!/usr/bin/env python3
"""Daily FAV ledger for a CLOSED UTC day. READ-ONLY. usage: fav_daily.py YYYY-MM-DD [start_epoch]"""
import sys, sqlite3, numpy as np, datetime as dt, time
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
D=sys.argv[1]
d0=dt.datetime.strptime(D,'%Y-%m-%d').replace(tzinfo=dt.UTC)
END=int((d0+dt.timedelta(days=1)).timestamp())            # 24:00 exclusive
f=lambda t: dt.datetime.fromtimestamp(t,dt.UTC).strftime('%m-%d %H:%M')
sh=sqlite3.connect(f'file:{S.DB}?mode=ro',uri=True)
START=int(sys.argv[2]) if len(sys.argv)>2 else sh.execute(
    "SELECT min(epoch) FROM fires WHERE arm LIKE 'FAV%'").fetchone()[0]
covered=sh.execute("SELECT max(epoch) FROM seen WHERE epoch<?",(END,)).fetchone()[0]
print(f'FAV DAILY LEDGER  {D}  window {f(START)} .. 24:00 UTC (exclusive)')
print(f'  last candle scored inside the window: {f(covered)}   day is '
      f'{"COMPLETE" if covered>=END-300 else "INCOMPLETE"}')
print()
print('arm          decisions  fills  wins     $@10    maxDD   flag')
for a in ('FAV','FAV_mid','FAV_all','FAV_ref','C_fixed15'):
    r=sh.execute("SELECT fill,win,pnl,pnl_part,sh FROM fires WHERE arm=? AND epoch>=? AND epoch<? "
                 "ORDER BY epoch",(a,START,END)).fetchall()
    part=[x for x in r if x[3] is not None]
    if part:
        got=[x for x in part if (x[4] or 0)>0]; pn=np.array([x[3] for x in part],float)
        nf=len(got); w=sum(x[1] for x in got)
    else:
        fl=[x for x in r if x[0] is not None]; pn=np.array([x[2] for x in r],float) if r else np.array([0.0])
        nf=len(fl); w=sum(x[1] for x in fl)
    c=np.cumsum(pn); dd=float(np.max(np.maximum.accumulate(np.r_[0,c])-np.r_[0,c]))
    print(f'{a:11s} {len(r):9d} {nf:6d} {w:5d} {pn.sum():+8.2f} {dd:8.2f}   '
          + ('INSUFFICIENT (<60 fills)' if nf<60 else ''))
print('  FAV arms use the PARTIAL arrival fill (filled shares a FLOOR, depth truncated at level 1).')
print('  C_fixed15 uses its own registered 250 ms FAK - a different fill model, so C is context')
print('  beside the FAV arms, not a like-for-like row.')

S.ALL52,S.STRICT=None,None; S.FAV_BK=S._fav_books(); S.FAV_BN1=S._bn_1s()
cand,vo,nk=S.load_candles()
dec=pm=sm=cap=0
for e in [x for (x,) in sh.execute("SELECT epoch FROM seen WHERE epoch>=? AND epoch<? ORDER BY epoch",(START,END))]:
    if e not in cand or e not in vo: continue
    rows=S.build_rows(cand[e],e,vo[e],nk)
    fv=sorted((r for r in rows if S.FAV_SEC[0]<=r['sec']<=S.FAV_SEC[1] and r['own']>r['opp']
               and S.FAV_BAND[0]<=r['own']<=S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    q=S._fav_fill(cand[e],dict(fv[0])); dec+=1
    if q['px']!=q['px']: pm+=1; continue
    if q['aon']!=q['aon']: sm+=1
    if q['capped']: cap+=1
print()
print(f'ARRIVAL FILLS (+500 ms): {dec} decisions -> {dec-pm} cleared the price cap '
      f'({100*(dec-pm)/max(dec,1):.0f}%) | PRICE-MISS {pm} ({100*pm/max(dec,1):.0f}%) | '
      f'SIZE-MISS {sm} ({100*sm/max(dec,1):.0f}%) | depth-capped {cap}')
