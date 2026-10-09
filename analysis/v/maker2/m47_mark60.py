# M47 (V, 10-03 13:2x) owner, EXACT: "60 is marked price, stop loss at 10 points below it and rebuy is 10 points above it,
# works both sides and stake increase by 10% each time".
# Each side: BUY $1 at the ask when ask >= 0.60 (mark). SELL at the bid when bid <= 0.50 (mark-10). RE-BUY when ask >= 0.70
# (mark+10) with stake x1.10 each time; same stop 0.50. Repeat to sec 295; held -> settle. FIXED = his words.
# Reference rows: stake flat (x1.00), and TRAIL (stop also trails peak bid - 0.10, his earlier "trailing up").
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    g=runpy.run_path('analysis/v/maker2/m45_stop15_rebuy55.py')
CP,CD,fee=g['CP'],g['CD'],g['fee']
def leg(s,ask,bid,win,fin,fout,payout,mode,grow,M=0.60,cut=295):
    cash=0.0; pos=False; n=0; stake=1.0; staked=0.0; sh=0; stops=0
    for j in range(len(s)):
        if s[j]>cut: break
        k,b=ask[j],bid[j]
        if np.isnan(k) or np.isnan(b): continue
        if not pos:
            if k>=(M if n==0 else M+0.10) and k<0.99:
                if n>0: stake*=grow
                sh=stake/k; cash-=stake+sh*fin(k); staked+=stake; pos=True; stop=M-0.10; peak=b; n+=1
        else:
            peak=max(peak,b)
            if mode=='TRAIL': stop=max(stop,peak-0.10)
            if b<=stop: cash+=sh*(b-fout(b)); pos=False; stops+=1
    if pos and win: cash+=sh*payout
    return cash,staked,n
for tag,C,fin,fout,pay in (('POLY fee',CP,fee,fee,1.0),('POLY 0fee',CP,lambda x:0,lambda x:0,1.0),('PRED',CD,lambda x:0.02*x,lambda x:0,0.98)):
    for mode in ('FIXED','TRAIL'):
        for grow in (1.10,1.00):
            r=[];st=[];days=[];nb=[]
            for e,(s,au,ad,bu,bd,w) in C.items():
                a,sa,na=leg(s,au,bu,w,fin,fout,pay,mode,grow); b,sb,nbb=leg(s,ad,bd,not w,fin,fout,pay,mode,grow)
                r.append(a+b); st.append(sa+sb); nb.append(na+nbb); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
            r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r)
            lab='OWNER EXACT' if (mode=='FIXED' and grow==1.10) else 'reference'
            print(f"{tag:9s} {mode:5s} stake x{grow:.2f} [{lab:11s}]: \$/candle {r.mean():+.4f} per \$ staked {r.sum()/max(sum(st),1e-9):+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} buys {np.mean(nb):.2f} worst {r.min():+.2f} maxDD {(cum-np.maximum.accumulate(cum)).min():+.1f}")
