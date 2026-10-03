# M41 (V, 10-03 12:3x) owner: buy UP and DOWN at minute 3 (sec 180). Each side's buy price = its MARK. Stop in POINTS (same d for
# both sides), trailing: stop = peak_bid - d (starts at entry - d). Stop hit -> sell at the bid. Sold side is RE-BOUGHT when its ask
# comes back to its mark (touches/crosses the mark), then trails again. Repeat until sec 285; held legs settle.
# d grid {2,3,3.5,5,7}c, reported in full. Venues: PRED = Predict.fun book1s 1 Hz 09-11..16 (2% of shares skimmed on every buy;
# exit at 1-ask_opp, col B also 2% on exits); POLY = Polymarket 08-01 5 s grid (taker fee 0.07p(1-p) each trade, plus 0-fee col).
import sqlite3, numpy as np, pandas as pd
def leg(s,ask,bid,win,i,d,buy_eff,sell_eff,cutoff=285):
    M=ask[i]; cash=-ask[i]; sh=buy_eff(ask[i]); pos=True; peak=ask[i]; n=1; prev=ask[i]
    for j in range(i+1,len(s)):
        if s[j]>cutoff: break
        b,k=bid[j],ask[j]
        if np.isnan(b) or np.isnan(k): continue
        if pos:
            peak=max(peak,b)
            if b<=peak-d: cash+=sh*sell_eff(b); pos=False; prev=k
        else:
            if (prev<M<=k) or (prev>M>=k) or k==M:      # ask comes back to the mark
                cash-=k; sh=buy_eff(k); pos=True; peak=k; n+=1
            prev=k
    if pos and win: cash+=sh
    return cash,n
def run(tag,C,buy_eff,sell_eff,sec=180):
    for d in (0.02,0.03,0.035,0.05,0.07):
        r=[];days=[];trades=[]
        for e,(s,au,ad,bu,bd,upw) in C.items():
            i=np.searchsorted(s,sec)
            if i>=len(s)-2 or np.isnan(au[i]) or np.isnan(ad[i]): continue
            a,na=leg(s,au,bu,upw,i,d,buy_eff,sell_eff); b,nb=leg(s,ad,bd,not upw,i,d,buy_eff,sell_eff)
            r.append((a+b)/(au[i]+ad[i])); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d')); trades.append(na+nb)
        r=np.array(r); h=len(r)//2; dd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r)
        print(f"{tag:14s} d={d*100:>4.1f}c n{len(r)} per\$1 {r.mean():+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(dd>0).sum()}/{len(dd)} win% {(r>0).mean():.0%} buys/candle {np.mean(trades):.1f} maxDD {(cum-np.maximum.accumulate(cum)).min():+.2f}")
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
run('PRED A',C,lambda p:0.98,lambda b:b)
run('PRED B',C,lambda p:0.98,lambda b:b*0.98)
hb=[(0.98-(C[e][1][i]+C[e][2][i]))/(C[e][1][i]+C[e][2][i]) for e in C for i in [np.searchsorted(C[e][0],180)] if i<len(C[e][0]) and not np.isnan(C[e][1][i]+C[e][2][i])]
print(f"PRED HOLD both (no stops): per\$1 {np.mean(hb):+.4f}")
# POLYMARKET 08-01 (5 s grid)
p=pd.read_parquet('btc_replay_day/2026-08-01/polymarket_btc5m_2026-08-01_books.parquet'); p=p[p.has_book]
C={}
for e,g in p.groupby('window_epoch'):
    u=g[g.side=='UP'].set_index('offset_s'); dn=g[g.side=='DOWN'].set_index('offset_s'); idx=u.index.intersection(dn.index).sort_values()
    if len(idx)<40: continue
    u=u.loc[idx]; dn=dn.loc[idx]
    C[e]=(idx.to_numpy(),u.best_ask.to_numpy(),dn.best_ask.to_numpy(),u.best_bid.to_numpy(),dn.best_bid.to_numpy(),u.outcome.iloc[0]=='UP')
fee=lambda x:0.07*x*(1-x)
run('POLY fee',C,lambda p:1-fee(p)/p,lambda b:b-fee(b))
run('POLY 0fee',C,lambda p:1.0,lambda b:b)
