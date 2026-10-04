import sys, os, json, sqlite3, collections, datetime as dt, numpy as np
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0,'/home/ubuntu/claude-work/repo/learner/v12_2')
from ef2_model import ROWS, per1
from ef3 import FITS
from ef6_lane import EF6Lane
from ef3_shadow import outcomes
D='09-26'; W_MS=3600_000; Q=0.90; G=60_000; STAKE=10.0
z=np.load(ROWS,allow_pickle=True); f=np.load(FITS,allow_pickle=True); keep=f['keep']
X,yw,q,ep,ts,day=(z[k][keep] for k in ('X','y','q','ep','ts','day'))
yw=yw.astype(float); isup=z['is_up'][keep]; names=[str(s) for s in z['names']]
ia,ip=names.index('own_ask'),names.index('p_side')
own=X[:,ia].astype(float); ps=X[:,ip].astype(float)
pwf=np.load('/home/ubuntu/pm_ef3/ef5_preds.npz')['pwf']
days=sorted(set(day.tolist())); k=days.index(D)
m_t=day==D; m_p=day==days[k-1]
tt=np.concatenate([ts[m_p],ts[m_t]]); pp=np.concatenate([np.load(f'/tmp/ef5_pprev_{D}.npy'),pwf[m_t]])
isd=np.concatenate([np.zeros(m_p.sum(),bool),np.ones(m_t.sum(),bool)])
o=np.argsort(tt,kind='stable'); tt,pp,isd=tt[o],pp[o],isd[o]; idx=np.where(m_t)[0]
t0,t1=tt[isd].min(),tt[isd].max()
grid=np.arange(t0,t1+G,G)
lo=np.searchsorted(tt,grid-W_MS,'left'); hi=np.searchsorted(tt,grid,'left')
thr=np.full(len(grid),np.nan)
for i,(a,b) in enumerate(zip(lo,hi)):
    if b-a>=500: thr[i]=np.quantile(pp[a:b],Q)
tday=tt[isd]; pday=pp[isd]
g=np.clip(np.searchsorted(grid,tday,'right')-1,0,len(grid)-1); th=thr[g]
okk=np.isfinite(th)&(pday>=th)
A={}
for j in np.argsort(tday,kind='stable'):
    if not okk[j]: continue
    i=idx[j]
    if ps[i]<0.5: continue
    e=int(ep[i])
    if e in A: continue
    A[e]=dict(sec=int(tday[j]//1000-e),side=('UP' if isup[i] else 'DOWN'),thr=float(th[j]),
              pred=float(pday[j]),ask=float(own[i]),q=float(q[i]),win=float(yw[i]))
print(f'ef6.py   09-26 fires: {len(A)}')
print(f'  grid anchor t0={t0} -> t0%60000={t0%G}  (lane anchors at floor(now/60)*60, i.e. t%60000==0)')
vo=outcomes()
L=sqlite3.connect('file:/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3?mode=ro',uri=True)
keys=json.loads(L.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
c=sqlite3.connect('file:/home/ubuntu/pm_archive/zurich_research_archive.sqlite3?mode=ro',uri=True)
lane=EF6Lane(cfg=dict(enabled=True,model_dir='/home/ubuntu/claude-work/repo/learner/v12_2/ef6'))
lane.load_day_model(f'2026-{D}')
print(f'  lane seed rows {len(lane.tq.rows):,}')
B={}
for tsx,epx,side,p,ua,da,fs in c.execute('SELECT ts_ms,epoch,side,p,up_ask,dn_ask,feats FROM decide_log '
   'WHERE p IS NOT NULL AND side IS NOT NULL AND up_ask IS NOT NULL AND dn_ask IS NOT NULL AND feats IS NOT NULL ORDER BY ts_ms'):
    if dt.datetime.fromtimestamp(epx,dt.timezone.utc).strftime('%m-%d')!=D: continue
    s=(tsx//1000)-epx
    if not (15<=s<=240): continue
    try: v=json.loads(fs)
    except Exception: continue
    if len(v)!=len(keys): continue
    r=lane.decide(epx,tsx/1000.0,s,dict(zip(keys,v)),float(ua),float(da),side,float(p))
    if r and epx not in B: B[epx]=dict(sec=int(r['sec']),side=r['side'],thr=float(r['thr']),pred=float(r['pred']),ask=float(r['ask']))
print(f'lane     09-26 fires: {len(B)}')
both=sorted(set(A)&set(B))
ident=[e for e in both if A[e]['side']==B[e]['side'] and A[e]['sec']==B[e]['sec']]
print(f'  both {len(both)}  identical(side+sec) {len(ident)}  ef6-only {len(set(A)-set(B))}  lane-only {len(set(B)-set(A))}')
fa=sum(STAKE*per1(A[e]['win'],A[e]['q']) for e in A if A[e]['q']==A[e]['q'])
print(f'  ef6.py $ (FAK price) {fa:+.1f}')
print(f'\n  first 6 candles in ts order, ef6 vs lane:')
for e in sorted(set(A)|set(B))[:6]:
    a=A.get(e); b=B.get(e)
    print(f'   {e}  ef6 {str((a["side"],a["sec"],round(a["thr"],4),round(a["pred"],4))) if a else "-":38s} '
          f'lane {str((b["side"],b["sec"],round(b["thr"],4),round(b["pred"],4))) if b else "-"}')
