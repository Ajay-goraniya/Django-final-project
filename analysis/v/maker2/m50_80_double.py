# M50 (V, 10-03 14:0x) owner: "buy at 80 but this time double the stake on rebuy". Two readings, both reported:
#  A = M47 rule with mark 0.80: each side buys $1 when ask >= 0.80, stop 0.70 (bid), re-buy ask >= 0.90, stake x2 each re-buy.
#  B = M49b: when either side hits 0.80 buy BOTH ($1 each), each mark = its price, stop -0.10, re-buy +0.10, stake x2.
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    a=runpy.run_path('analysis/v/maker2/m47_mark60.py'); b=runpy.run_path('analysis/v/maker2/m49_hit70_both.py')
CP,CD,fee=a['CP'],a['CD'],a['fee']; legA=a['leg']; legB=b['leg']
def stats(tag,name,r,st,days,nb):
    r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r)
    print(f"{tag:9s} {name:22s}: n {len(r)} \$/candle {r.mean():+.4f} per \$ staked {r.sum()/sum(st):+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} buys {np.mean(nb):.2f} worst {r.min():+.2f} maxDD {(cum-np.maximum.accumulate(cum)).min():+.1f}")
for tag,C,fin,fout,pay in (('POLY fee',CP,fee,fee,1.0),('POLY 0fee',CP,lambda x:0,lambda x:0,1.0),('PRED',CD,lambda x:0.02*x,lambda x:0,0.98)):
    for grow in (2.0,1.0):
        r=[];st=[];days=[];nb=[]
        for e,(s,au,ad,bu,bd,w) in C.items():
            x1,s1,n1=legA(s,au,bu,w,fin,fout,pay,'FIXED',grow,M=0.80); x2,s2,n2=legA(s,ad,bd,not w,fin,fout,pay,'FIXED',grow,M=0.80)
            if n1+n2==0: continue
            r.append(x1+x2); st.append(s1+s2); nb.append(n1+n2); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
        stats(tag,f'A mark80 stake x{grow:.0f}',r,st,days,nb)
        r=[];st=[];days=[];nb=[]
        for e,(s,au,ad,bu,bd,w) in C.items():
            hit=np.where(((au>=0.80)|(ad>=0.80))&(s<=280)&~np.isnan(au)&~np.isnan(ad))[0]
            if not len(hit): continue
            i=hit[0]
            if not (au[i]<0.99 and ad[i]<0.99): continue
            x1,s1,n1=legB(s,au,bu,w,i,fin,fout,pay,grow); x2,s2,n2=legB(s,ad,bd,not w,i,fin,fout,pay,grow)
            r.append(x1+x2); st.append(s1+s2); nb.append(n1+n2); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
        stats(tag,f'B both@80 stake x{grow:.0f}',r,st,days,nb)
