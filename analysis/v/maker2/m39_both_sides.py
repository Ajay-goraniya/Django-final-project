# M39 (V): owner 10-03 12:0x "do the same on both side, up and down, at minute 3". Buy UP and DOWN at sec 180 (taker at ask),
# each leg runs the owner's ratchet exactly: stop at mark P arms once bid>=P; bid>=1.10P -> stop 1.05P; bid>=1.20P -> stop 1.10P.
# v1: stop hit -> sell at triggering bid, done. v2 (his step-5 fix): stop S becomes new mark, re-buy at ask>=1.10S, repeat to sec 270.
# Held at 270 -> settlement. Venues: PRED = Predict.fun book1s 1 Hz (fee 2% winning shares; exit = 1-ask_opp-0.02),
#                                     POLY = Polymarket 08-01 5 s grid (taker fee 0.07p(1-p); bid = best_bid).
import sqlite3, numpy as np, pandas as pd, sys
def leg(s,ask,bid,win,i,fee_in,fee_out,settle,v2):
    P=ask[i]; cash=-P-fee_in(P); pos=True; mark=P; stop=None; S=None
    for j in range(i+1,len(s)):
        if s[j]>270: break
        b,k=bid[j],ask[j]
        if pos:
            if stop is None and b>=mark-1e-9: stop=mark
            if b>=1.20*mark-1e-9: stop=1.10*mark
            elif b>=1.10*mark-1e-9: stop=max(stop or 0,1.05*mark)
            if stop is not None and b<=stop+1e-9 and j>i+1:
                cash+=b-fee_out(b); pos=False; S=stop
                if not v2: break
        elif v2 and k>=1.10*S and k<0.99:
            cash-=k+fee_in(k); pos=True; mark=S; stop=None
    if pos: cash+=settle(win)
    return cash
def run(name,cands,fee_in,fee_out,settle,secs=(180,)):
    for sec in secs:
        for v2 in (0,1):
            r=[];d=[]
            for e,(s,au,ad,bu,bd,upwin) in cands.items():
                i=np.searchsorted(s,sec)
                if i>=len(s)-2 or np.isnan(au[i]) or np.isnan(ad[i]): continue
                pu=leg(s,au,bu,upwin,i,fee_in,fee_out,settle,v2); pd_=leg(s,ad,bd,not upwin,i,fee_in,fee_out,settle,v2)
                cost=au[i]+ad[i]; r.append((pu+pd_)/cost); d.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
            r=np.array(r); hold=None
            h=len(r)//2; dd=pd.Series(r).groupby(d).sum()
            print(f"{name} sec{sec} {'v2 re-buy' if v2 else 'v1 no re-buy'}: n{len(r)} per\$1 {r.mean():+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(dd>0).sum()}/{len(dd)} worst {r.min():+.3f} best {r.max():+.3f}")
        # HOLD both = guaranteed 1 payout minus cost
# PREDICT
c=sqlite3.connect('/tmp/book1s.sqlite3')
d=pd.read_sql('select epoch,sec,price,open,ask_up,ask_dn,book_candle from b1',c).dropna(subset=['sec'])
lab=d.sort_values(['epoch','sec']).groupby('epoch').agg(price=('price','last'),open=('open','first'),mx=('sec','max'))
lab=lab[lab.mx>=290]; upw=(lab.price>=lab.open)
d=d[(d.book_candle==d.epoch)].copy(); d['s']=d.sec.astype(int); d=d.drop_duplicates(['epoch','s']).sort_values(['epoch','s'])
F=0.02; cands={}
for e,g in d.groupby('epoch'):
    if e not in upw.index or len(g)<200: continue
    s=g.s.to_numpy(); au=g.ask_up.to_numpy(float); ad=g.ask_dn.to_numpy(float)
    cands[e]=(s,au,ad,1-ad-F,1-au-F,bool(upw[e]))
run('PRED',cands,lambda p:0,lambda p:0,lambda w:(1-F) if w else 0.0,secs=(120,180,240))
# hold-both reference
hb=[]
for e,(s,au,ad,_,_,w) in cands.items():
    i=np.searchsorted(s,180)
    if i<len(s) and not np.isnan(au[i]+ad[i]): hb.append(((1-F)-(au[i]+ad[i]))/(au[i]+ad[i]))
print(f"PRED sec180 HOLD both: n{len(hb)} per\$1 {np.mean(hb):+.4f}")
# POLYMARKET 08-01
p=pd.read_parquet('btc_replay_day/2026-08-01/polymarket_btc5m_2026-08-01_books.parquet'); p=p[p.has_book]
fee=lambda x:0.07*x*(1-x); cands={}
for e,g in p.groupby('window_epoch'):
    u=g[g.side=='UP'].set_index('offset_s'); dn=g[g.side=='DOWN'].set_index('offset_s'); idx=u.index.intersection(dn.index).sort_values()
    if len(idx)<40: continue
    u=u.loc[idx]; dn=dn.loc[idx]
    cands[e]=(idx.to_numpy(),u.best_ask.to_numpy(),dn.best_ask.to_numpy(),u.best_bid.to_numpy(),dn.best_bid.to_numpy(),u.outcome.iloc[0]=='UP')
run('POLY fee',cands,fee,fee,lambda w:1.0 if w else 0.0,secs=(120,180,240))
run('POLY 0fee',cands,lambda x:0,lambda x:0,lambda w:1.0 if w else 0.0,secs=(180,))
