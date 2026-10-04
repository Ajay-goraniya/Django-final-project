# M37 (V): owner's ratchet-stop family (M36 grid) on PREDICT.FUN's own 1 Hz book (book1s 09-11..09-16).
# Predict settles on Binance close >= open. Fee 2% of shares on winners only. Exit = buy opposite side (bid_up = 1-ask_dn),
# charged 2% conservatively. Entries: RAND (random side, sec 15-150) and BN_s (side Binance is on at sec s, s in 30/60/90/120).
import sqlite3, numpy as np, pandas as pd, itertools, sys
c=sqlite3.connect(sys.argv[1] if len(sys.argv)>1 else '/tmp/book1s.sqlite3')
d=pd.read_sql('select epoch,sec,price,open,ask_up,ask_dn from b1 where book_candle=epoch and ask_up is not null and ask_dn is not null',c)
d=d.dropna(subset=['sec','price','open']); d['s']=d.sec.astype(int); d=d.drop_duplicates(['epoch','s']).sort_values(['epoch','s'])
lab=pd.read_sql('select epoch,price,open,sec from b1',c).sort_values(['epoch','sec']).groupby('epoch').agg(price=('price','last'),open=('open','first'),mx=('sec','max'))
lab=lab[lab.mx>=290]; up=(lab.price>=lab.open)
F=0.02
P={}
for e,g in d.groupby('epoch'):
    if e not in up.index or len(g)<200: continue
    a=g[['s','ask_up','ask_dn','price','open']].to_numpy()
    P[e]=a
def path(e,side):
    a=P[e]; s=a[:,0]
    ask=a[:,1] if side=='UP' else a[:,2]; bid=1-(a[:,2] if side=='UP' else a[:,1])-F
    return s,ask,bid
def sim(e,side,i,A,G,R,T):
    s,ask,bid=path(e,side); win=bool(up[e])==(side=='UP')
    Pp=ask[i]; cash=-Pp; pos=True; mark=Pp; peak=bid[i]; armed=False; S=None
    for j in range(i+1,len(s)):
        if s[j]>270: break
        b=bid[j]; k=ask[j]
        if pos:
            peak=max(peak,b)
            if T and b>=mark*(1+T)+0.01: cash+=mark*(1+T); pos=False; break   # resting take-profit, zero fee
            if not armed and b>=mark*(1+A)-1e-9: armed=True
            if armed and b<=max(mark,peak*(1-G)):
                cash+=b; pos=False; S=max(mark,peak*(1-G))
                if not R: break
        elif R and S and k>=1.10*S and k<0.97:
            cash-=k; pos=True; mark=S; peak=b; armed=True
    if pos: cash+= (1-F) if win else 0.0
    return cash/Pp
rng=np.random.default_rng(7); ents={}
eps=sorted(P)
for e in eps:
    s,_,_=path(e,'UP'); a=P[e]
    for side in ('UP','DOWN'):
        _,ask,_=path(e,side)
        ok=np.where((s>=15)&(s<=150)&(ask>=0.15)&(ask<=0.85))[0]
        if len(ok): ents.setdefault('RAND',[]).append((e,side,int(rng.choice(ok))))
    for sec in (30,60,90,120):
        i=np.searchsorted(s,sec); 
        if i>=len(s): continue
        side='UP' if a[i,3]>=a[i,4] else 'DOWN'
        _,ask,_=path(e,side)
        if 0.15<=ask[i]<=0.85: ents.setdefault(f'BN_{sec}',[]).append((e,side,i))
half=eps[len(eps)//2]
out=[]
for name,E in ents.items():
    E=E if name!='RAND' else E[::2]
    days=np.array([pd.to_datetime(e,unit='s').strftime('%m-%d') for e,_,_ in E]); h1=np.array([e<half for e,_,_ in E])
    hold=np.array([sim(e,sd,i,9,9,0,0) for e,sd,i in E])
    def row(tag,r):
        dd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r); mdd=(cum-np.maximum.accumulate(cum)).min()
        return dict(entry=name,cell=tag,n=len(r),per1=r.mean(),t=r.mean()/r.std()*np.sqrt(len(r)),h1=r[h1].mean(),h2=r[~h1].mean(),
                    green=f'{(dd>0).sum()}/{len(dd)}',maxDD=mdd,worst=r.min(),vsHOLD=(r-hold).mean())
    out.append(row('HOLD',hold))
    for A,G,R,T in itertools.product([0,.05,.1,.15,.2,.3],[.05,.1,.15,.2],[0,1],[0,.2,.3,.5]):
        out.append(row(f'a{int(A*100)} g{int(G*100)} R{R} T{int(T*100)}',np.array([sim(e,sd,i,A,G,R,T) for e,sd,i in E])))
df=pd.DataFrame(out)
pd.set_option('display.width',200); pd.set_option('display.max_rows',2000)
for name,g in df.groupby('entry'):
    cells=g[g.cell!='HOLD']
    print(f'\n== {name}  HOLD:',g[g.cell=='HOLD'].round(4).to_string(index=False,header=False))
    print(f'   cells per1>0: {(cells.per1>0).sum()}/192   t>=2: {(cells.t>=2).sum()}   both halves>0: {((cells.h1>0)&(cells.h2>0)).sum()}   beat HOLD: {(cells.vsHOLD>0).sum()}')
    print(cells.sort_values('per1').tail(5).round(4).to_string(index=False))
df.round(4).to_csv(sys.argv[2] if len(sys.argv)>2 else '/tmp/claude-0/s/m37_grid.csv',index=False)
