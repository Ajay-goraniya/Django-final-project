# M45 (V, 10-03 13:0x) owner: "move the stop loss by 15 points and rebuy at 55 instead of increasing every time".
# Each side: first buy at the ask when ask >= Tin (0.60, and 0.55 for reference); stop = entry-0.15, trailing peak bid-0.15 (TRAIL)
# or fixed entry-0.15 (FIXED); after a stop, RE-BUY at the ask when ask >= 0.55 again; repeat to sec 295; held -> settle.
import numpy as np, pandas as pd, sqlite3
def leg(s,ask,bid,win,fin,fout,settle,mode,Tin,Tre=0.55,d=0.15,cut=295):
    cash=0.0; pos=False; n=0
    for j in range(len(s)):
        if s[j]>cut: break
        k,b=ask[j],bid[j]
        if np.isnan(k) or np.isnan(b): continue
        if not pos:
            if k>=(Tin if n==0 else Tre) and k<0.99:
                cash-=k+fin(k); pos=True; stop=k-d; peak=b; n+=1
        else:
            peak=max(peak,b)
            if mode=='TRAIL': stop=max(stop,peak-d)
            if b<=stop: cash+=b-fout(b); pos=False
    if pos: cash+=settle(win)
    return cash,n
fee=lambda x:0.07*x*(1-x)
p=pd.read_parquet('btc_replay_day/2026-08-01/polymarket_btc5m_2026-08-01_books.parquet'); p=p[p.has_book]; CP={}
for e,g in p.groupby('window_epoch'):
    u=g[g.side=='UP'].set_index('offset_s'); dn=g[g.side=='DOWN'].set_index('offset_s'); idx=u.index.intersection(dn.index).sort_values()
    if len(idx)<40: continue
    u=u.loc[idx]; dn=dn.loc[idx]; CP[e]=(idx.to_numpy(),u.best_ask.to_numpy(),dn.best_ask.to_numpy(),u.best_bid.to_numpy(),dn.best_bid.to_numpy(),u.outcome.iloc[0]=='UP')
c=sqlite3.connect('/tmp/book1s.sqlite3')
d=pd.read_sql('select epoch,sec,price,open,ask_up,ask_dn,book_candle from b1',c).dropna(subset=['sec'])
lab=d.sort_values(['epoch','sec']).groupby('epoch').agg(price=('price','last'),open=('open','first'),mx=('sec','max'))
lab=lab[lab.mx>=290]; upw=(lab.price>=lab.open)
d=d[d.book_candle==d.epoch].copy(); d['s']=d.sec.astype(int); d=d.drop_duplicates(['epoch','s']).sort_values(['epoch','s']); CD={}
for e,g in d.groupby('epoch'):
    if e not in upw.index or len(g)<200: continue
    s=g.s.to_numpy(); au=g.ask_up.to_numpy(float); ad=g.ask_dn.to_numpy(float); CD[e]=(s,au,ad,1-ad,1-au,bool(upw[e]))
for tag,C,fin,fout,st in (('POLY fee',CP,fee,fee,lambda w:1.0 if w else 0.0),('POLY 0fee',CP,lambda x:0,lambda x:0,lambda w:1.0 if w else 0.0),('PRED',CD,lambda x:0.02*x,lambda x:0,lambda w:0.98 if w else 0.0)):
    for Tin in (0.60,0.55):
        for mode in ('TRAIL','FIXED'):
            r=[];days=[];nb=[]
            for e,(s,au,ad,bu,bd,w) in C.items():
                a,na=leg(s,au,bu,w,fin,fout,st,mode,Tin); b,nbb=leg(s,ad,bd,not w,fin,fout,st,mode,Tin)
                r.append(a+b); nb.append(na+nbb); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
            r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum()
            print(f"{tag:9s} first buy {Tin:.2f} rebuy 0.55 stop 15pt {mode:5s}: per candle {r.mean():+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} buys {np.mean(nb):.2f}")
