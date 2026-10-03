# M46 (V, 10-03 13:1x) owner: M45 exactly, but every RE-BUY stakes 10% more than the previous buy ($1, $1.10, $1.21, ...).
# Backtest only (CLAUDE.md: dynamic staking never goes live without the owner's two confirmations).
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    g=runpy.run_path('analysis/v/maker2/m45_stop15_rebuy55.py')
CP,CD,fee=g['CP'],g['CD'],g['fee']
def leg(s,ask,bid,win,fin,fout,payout,mode,Tin,grow,Tre=0.55,d=0.15,cut=295):
    cash=0.0; pos=False; n=0; stake=1.0; staked=0.0; sh=0
    for j in range(len(s)):
        if s[j]>cut: break
        k,b=ask[j],bid[j]
        if np.isnan(k) or np.isnan(b): continue
        if not pos:
            if k>=(Tin if n==0 else Tre) and k<0.99:
                if n>0: stake*=grow
                sh=stake/k; cash-=stake+sh*fin(k); staked+=stake; pos=True; stop=k-d; peak=b; n+=1
        else:
            peak=max(peak,b)
            if mode=='TRAIL': stop=max(stop,peak-d)
            if b<=stop: cash+=sh*(b-fout(b)); pos=False
    if pos and win: cash+=sh*payout
    return cash,staked,n
for tag,C,fin,fout,pay in (('POLY fee',CP,fee,fee,1.0),('POLY 0fee',CP,lambda x:0,lambda x:0,1.0),('PRED',CD,lambda x:0.02*x,lambda x:0,0.98)):
    for grow in (1.0,1.10):
        for mode in ('FIXED','TRAIL'):
            r=[];st=[];days=[];nb=[]
            for e,(s,au,ad,bu,bd,w) in C.items():
                a,sa,na=leg(s,au,bu,w,fin,fout,pay,mode,0.60,grow); b,sb,nbb=leg(s,ad,bd,not w,fin,fout,pay,mode,0.60,grow)
                r.append(a+b); st.append(sa+sb); nb.append(na+nbb); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
            r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r)
            print(f"{tag:9s} stake x{grow:.2f} per re-buy {mode:5s}: \$/candle {r.mean():+.4f} per \$ staked {r.sum()/sum(st):+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} worst candle {r.min():+.2f} maxDD {(cum-np.maximum.accumulate(cum)).min():+.1f}")
