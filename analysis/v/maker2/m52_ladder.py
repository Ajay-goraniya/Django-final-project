# M52 (V, 10-03 14:3x) owner's LADDER (correcting V's M47/M49/M50/M51 implementation, where the mark never moved and the same
# stop/re-buy pair could repeat). Owner: "buy at 60, re-buy only at 70, 80, 90, only after a 10-point drop (stop), stop 10 below".
# Each side: level L0 = first buy level; buy at the ask when ask >= L0. Stop = L-0.10 (sell at the bid). After a stop, next level
# L+0.10: re-buy when ask >= L+0.10 (and < 0.99); its stop = (L+0.10)-0.10. Max buys = levels up to 0.90. Stake x grow per buy.
# Setups: S60 = one side when it reaches 0.60 (M47); B60 = both sides when either reaches 0.60 (other side ladders from its own
# price rounded to the 10c level at/under its ask); B80 = same at 0.80. Hold/settle at 295.
import numpy as np, pandas as pd, runpy, io, contextlib, math
with contextlib.redirect_stdout(io.StringIO()):
    g=runpy.run_path('analysis/v/maker2/m45_stop15_rebuy55.py')
CP,CD,fee=g['CP'],g['CD'],g['fee']
def ladder(s,ask,bid,win,i0,L,fin,fout,pay,grow,cut=295):
    cash=0.0; staked=0.0; stake=1.0; n=0; pos=False; sh=0
    for j in range(i0,len(s)):
        if s[j]>cut: break
        k,b=ask[j],bid[j]
        if np.isnan(k) or np.isnan(b): continue
        if not pos:
            if L>0.905: break
            if k>=L-1e-9 and k<0.99:
                if n>0: stake*=grow
                sh=stake/k; cash-=stake+sh*fin(k); staked+=stake; pos=True; n+=1; stop=L-0.10
        elif b<=stop+1e-9:
            cash+=sh*(b-fout(b)); pos=False; L=round(L+0.10,2)
    if pos and win: cash+=sh*pay
    return cash,staked,n
def run(tag,C,fin,fout,pay,setup,grow):
    r=[];st=[];days=[];nb=[]
    for e,(s,au,ad,bu,bd,w) in C.items():
        if setup=='S60':
            a,sa,na=ladder(s,au,bu,w,0,0.60,fin,fout,pay,grow); b,sb,nbb=ladder(s,ad,bd,not w,0,0.60,fin,fout,pay,grow)
            if na+nbb==0: continue
        else:
            T=0.60 if setup=='B60' else 0.80
            hit=np.where(((au>=T)|(ad>=T))&(s<=280)&~np.isnan(au)&~np.isnan(ad))[0]
            if not len(hit): continue
            i=hit[0]
            if not (au[i]<0.99 and ad[i]<0.99): continue
            Lu=math.floor(au[i]*10+1e-9)/10; Ld=math.floor(ad[i]*10+1e-9)/10
            a,sa,na=ladder(s,au,bu,w,i,max(Lu,0.1),fin,fout,pay,grow); b,sb,nbb=ladder(s,ad,bd,not w,i,max(Ld,0.1),fin,fout,pay,grow)
        r.append(a+b); st.append(sa+sb); nb.append((na,nbb)); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
    r=np.array(r); h=len(r)//2; gd=pd.Series(r).groupby(days).sum(); cum=np.cumsum(r); mx=max(max(x) for x in nb)
    print(f"{tag:9s} {setup} stake x{grow:.2f}: n {len(r)} \$/candle {r.mean():+.4f} per \$ staked {r.sum()/sum(st):+.4f} t{r.mean()/r.std()*np.sqrt(len(r)):+6.2f} halves {r[:h].mean():+.4f}/{r[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} win-candles {(r>0).mean():.0%} worst {r.min():+.2f} max buys/side {mx} maxDD {(cum-np.maximum.accumulate(cum)).min():+.1f}")
for tag,C,fin,fout,pay in (('POLY fee',CP,fee,fee,1.0),('POLY 0fee',CP,lambda x:0,lambda x:0,1.0),('PRED',CD,lambda x:0.02*x,lambda x:0,0.98)):
    for setup,grows in (('S60',(1.10,2.0,1.0)),('B60',(2.0,1.0)),('B80',(2.0,1.0))):
        for gr in grows: run(tag,C,fin,fout,pay,setup,gr)
