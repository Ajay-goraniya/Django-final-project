# M44 (V, 10-03 12:4x) owner: "place 60-60 orders at candle open, stop 10 points below, then our trailing-up method".
# Polymarket has no buy-stop: a resting BUY limit at 0.60 with the ask at ~0.50 fills at once. So the rule is modelled as: from sec 0,
# the first time a side's ask >= 0.60 -> buy that side at that ask (taker). Each side independently (both can trigger).
# Stop = entry - 0.10, trailing: stop = peak_bid - 0.10 (points; the M41 method). Stop hit -> sell at the triggering bid.
# R0 = no re-buy; R1 = re-buy when that side's ask is back at >= 0.60 (the same trigger). Held at 295 -> settle.
# Ref row OWN = owner's % ratchet after entry (stop entry-0.10, bid>=1.10P -> 1.05P, bid>=1.20P -> 1.10P).
import sqlite3, numpy as np, pandas as pd
SESS=[('ASIA',0,7),('EU',7,13),('US',13,20),('LATE',20,24)]
def leg(s,ask,bid,win,fin,fout,settle,mode,R,T=0.60,d=0.10,cut=295):
    cash=0.0; pos=False; peak=None; stop=None; P=None; armed_rebuy=True; n=0
    for j in range(len(s)):
        if s[j]>cut: break
        k,b=ask[j],bid[j]
        if np.isnan(k) or np.isnan(b): continue
        if not pos:
            if (n==0 or R) and k>=T and k<0.99:
                cash-=k+fin(k); pos=True; P=k; peak=b; stop=k-d; n+=1
        else:
            peak=max(peak,b)
            if mode=='TRAIL': stop=max(stop,peak-d)
            else:
                if b>=1.20*P: stop=max(stop,1.10*P)
                elif b>=1.10*P: stop=max(stop,1.05*P)
            if b<=stop: cash+=b-fout(b); pos=False
    if pos: cash+=settle(win)
    return cash,n
def run(tag,C,fin,fout,settle):
    print(f'\n== {tag}: {len(C)} candles  (per candle $, 1 share per buy)')
    for mode in ('TRAIL','OWN'):
        for R in (0,1):
            r=[];days=[];hrs=[];nb=[]
            for e,(s,au,ad,bu,bd,upw) in C.items():
                a,na=leg(s,au,bu,upw,fin,fout,settle,mode,R); b,nb_=leg(s,ad,bd,not upw,fin,fout,settle,mode,R)
                r.append(a+b); nb.append(na+nb_); dt=pd.to_datetime(e,unit='s'); days.append(dt.strftime('%m-%d')); hrs.append(dt.hour)
            r=np.array(r); hrs=np.array(hrs); h=len(r)//2; g=pd.Series(r).groupby(days).sum()
            ss=' | '.join(f'{nm} {r[(hrs>=a)&(hrs<z)].mean():+.3f}' for nm,a,z in SESS)
            print(f'  {mode:5s} R{R}: per candle {r.mean():+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(g>0).sum()}/{len(g)} buys/candle {np.mean(nb):.2f} | {ss}')
# POLYMARKET 08-01
p=pd.read_parquet('btc_replay_day/2026-08-01/polymarket_btc5m_2026-08-01_books.parquet'); p=p[p.has_book]
C={}
for e,g in p.groupby('window_epoch'):
    u=g[g.side=='UP'].set_index('offset_s'); dn=g[g.side=='DOWN'].set_index('offset_s'); idx=u.index.intersection(dn.index).sort_values()
    if len(idx)<40: continue
    u=u.loc[idx]; dn=dn.loc[idx]
    C[e]=(idx.to_numpy(),u.best_ask.to_numpy(),dn.best_ask.to_numpy(),u.best_bid.to_numpy(),dn.best_bid.to_numpy(),u.outcome.iloc[0]=='UP')
fee=lambda x:0.07*x*(1-x)
run('POLYMARKET 08-01, taker fee',C,fee,fee,lambda w:1.0 if w else 0.0)
run('POLYMARKET 08-01, zero fee',C,lambda x:0,lambda x:0,lambda w:1.0 if w else 0.0)
# PREDICT
c=sqlite3.connect('/tmp/book1s.sqlite3')
d=pd.read_sql('select epoch,sec,price,open,ask_up,ask_dn,book_candle from b1',c).dropna(subset=['sec'])
lab=d.sort_values(['epoch','sec']).groupby('epoch').agg(price=('price','last'),open=('open','first'),mx=('sec','max'))
lab=lab[lab.mx>=290]; upw=(lab.price>=lab.open)
d=d[d.book_candle==d.epoch].copy(); d['s']=d.sec.astype(int); d=d.drop_duplicates(['epoch','s']).sort_values(['epoch','s'])
C={}
for e,g in d.groupby('epoch'):
    if e not in upw.index or len(g)<200: continue
    s=g.s.to_numpy(); au=g.ask_up.to_numpy(float); ad=g.ask_dn.to_numpy(float)
    C[e]=(s,au,ad,1-ad,1-au,bool(upw[e]))
run('PREDICT 09-11..16 (2% on winning shares, exits at 1-ask_opp)',C,lambda x:0.02*x,lambda x:0,lambda w:0.98 if w else 0.0)
