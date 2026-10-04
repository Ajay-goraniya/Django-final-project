# M49 (V, 10-03 13:4x) owner EXACT: "when one side hits 70 buy both sides and apply the same rule".
# Trigger: first second either side's ask >= 0.70 -> buy BOTH sides at their asks ($1 each, taker).
# Each side: mark = its buy price; stop = mark-0.10 (sell at the bid); re-buy at ask >= mark+0.10 with stake x1.10; repeat to sec 295.
# Reference: HOLD both (no stops), and flat stake.
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    g=runpy.run_path('analysis/v/maker2/m45_stop15_rebuy55.py')
CP,CD,fee=g['CP'],g['CD'],g['fee']
def leg(s,ask,bid,win,i0,fin,fout,payout,grow,rule=True,cut=295):
    M=ask[i0]; stake=1.0; sh=stake/M; cash=-stake-sh*fin(M); staked=stake; pos=True; n=1
    if rule:
        for j in range(i0+1,len(s)):
            if s[j]>cut: break
            k,b=ask[j],bid[j]
            if np.isnan(k) or np.isnan(b): continue
            if pos:
                if b<=M-0.10: cash+=sh*(b-fout(b)); pos=False
            elif k>=M+0.10 and k<0.99:
                stake*=grow; sh=stake/k; cash-=stake+sh*fin(k); staked+=stake; pos=True; n+=1
    if pos and win: cash+=sh*payout
    return cash,staked,n
for tag,C,fin,fout,pay in (('POLY fee',CP,fee,fee,1.0),('POLY 0fee',CP,lambda x:0,lambda x:0,1.0),('PRED',CD,lambda x:0.02*x,lambda x:0,0.98)):
    for name,grow,rule in (('OWNER EXACT x1.10',1.10,True),('flat stake',1.00,True),('HOLD both',1.0,False)):
        r=[];st=[];days=[];nb=[];fav=[]
        for e,(s,au,ad,bu,bd,w) in C.items():
            hit=np.where(((au>=0.70)|(ad>=0.70))&(s<=280)&~np.isnan(au)&~np.isnan(ad))[0]
            if not len(hit): continue
            i=hit[0]
            if not (au[i]<0.99 and ad[i]<0.99): continue
            a,sa,na=leg(s,au,bu,w,i,fin,fout,pay,grow,rule); b,sb,nbb=leg(s,ad,bd,not w,i,fin,fout,pay,grow,rule)
            r.append(a+b); st.append(sa+sb); nb.append(na+nbb); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
            fav.append((au[i]>=0.70)==w)
        r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r)
        print(f"{tag:9s} {name:17s}: candles {len(r)} \$/candle {r.mean():+.4f} per \$ staked {r.sum()/sum(st):+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} buys {np.mean(nb):.2f} worst {r.min():+.2f} | 70-side won {np.mean(fav):.0%}")
