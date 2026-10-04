# M51 (V, 10-03 14:1x) owner: M50B at 60c. When either side's ask >= 0.60 -> buy BOTH ($1 each); each side mark = its buy price,
# stop mark-0.10 (bid), re-buy ask >= mark+0.10, stake DOUBLES each buy. Refs: flat stake, HOLD both.
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    b=runpy.run_path('analysis/v/maker2/m49_hit70_both.py')
CP,CD,fee,leg=b['CP'],b['CD'],b['fee'],b['leg']
for tag,C,fin,fout,pay in (('POLY fee',CP,fee,fee,1.0),('POLY 0fee',CP,lambda x:0,lambda x:0,1.0),('PRED',CD,lambda x:0.02*x,lambda x:0,0.98)):
    for name,grow,rule in (('OWNER x2',2.0,True),('flat stake',1.0,True),('HOLD both',1.0,False)):
        r=[];st=[];days=[];nb=[];mx=[]
        for e,(s,au,ad,bu,bd,w) in C.items():
            hit=np.where(((au>=0.60)|(ad>=0.60))&(s<=280)&~np.isnan(au)&~np.isnan(ad))[0]
            if not len(hit): continue
            i=hit[0]
            if not (au[i]<0.99 and ad[i]<0.99): continue
            x1,s1,n1=leg(s,au,bu,w,i,fin,fout,pay,grow,rule); x2,s2,n2=leg(s,ad,bd,not w,i,fin,fout,pay,grow,rule)
            r.append(x1+x2); st.append(s1+s2); nb.append(n1+n2); mx.append(max(n1,n2)); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
        r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r)
        print(f"{tag:9s} {name:10s}: n {len(r)} \$/candle {r.mean():+.4f} per \$ staked {r.sum()/sum(st):+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} win-candles {(r>0).mean():.0%} worst {r.min():+.2f} best {r.max():+.2f} max buys/side {max(mx)} maxDD {(cum-np.maximum.accumulate(cum)).min():+.1f}")
