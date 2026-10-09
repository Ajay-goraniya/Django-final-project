import pandas as pd, numpy as np, itertools
d=pd.read_parquet('btc_replay_day/2026-08-01/polymarket_btc5m_2026-08-01_books.parquet')
d=d[d.has_book].sort_values(['window_epoch','side','offset_s'])
fee=lambda p:0.07*p*(1-p)
paths={k:g[['offset_s','best_bid','best_ask']].to_numpy() for k,g in d.groupby(['window_epoch','side'])}
outc=d.groupby(['window_epoch','side']).outcome.first()
rng=np.random.default_rng(1)
ents=[]
for k,p in paths.items():
    for _ in range(3):
        i=rng.integers(0,max(1,int((p[:,0]<=150).sum())))
        if 0.15<=p[i,2]<=0.85: ents.append((k,i))
def sim(k,i,a,g,R,T):
    p=paths[k]; win=1.0 if outc[k]==k[1] else 0.0
    P=p[i,2]; cash=-P-fee(P); pos=1; mark=P; peak=p[i,1]; armed=False; flat_mark=None
    for j in range(i+1,len(p)):
        t,b,ak=p[j]
        if t>270: break
        if pos:
            peak=max(peak,b)
            if T and b>=mark*(1+T)+0.01: cash+=mark*(1+T); pos=0; flat_mark=None; break
            if not armed and b>=mark*(1+a) - 1e-9: armed=True
            if armed:
                stop=max(mark,peak*(1-g))
                if b<=stop:
                    cash+=b-fee(b); pos=0; flat_mark=stop
                    if not R: break
        elif R and flat_mark is not None and ak>=1.10*flat_mark and ak<0.97:
            cash-=ak+fee(ak); pos=1; mark=flat_mark; peak=b; armed=True  # already >= 1.10S
    if pos: cash+=win
    return cash/P   # per $1 staked
rows=[]
hold=np.array([ (1.0 if outc[k]==k[1] else 0)/paths[k][i,2]-1-fee(paths[k][i,2])/paths[k][i,2] for k,i in ents])
for a,g,R,T in itertools.product([0,.05,.1,.15,.2,.3],[.05,.1,.15,.2],[0,1],[0,.2,.3,.5]):
    r=np.array([sim(k,i,a,g,R,T) for k,i in ents]); rows.append((a,g,R,T,r.mean(),r.mean()/r.std()*np.sqrt(len(r)),(r-hold).mean()))
df=pd.DataFrame(rows,columns='a g R T per1 t vsHOLD'.split())
print('n entries',len(ents),'HOLD per1 %.4f'%hold.mean())
print(df.describe().loc[['mean','min','max']].round(4))
print('cells per1>0:',(df.per1>0).sum(),'of',len(df)); print(df.sort_values('per1').tail(5).round(4)); print(df.sort_values('per1').head(3).round(4))
