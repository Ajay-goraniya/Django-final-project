# M48 (V, 10-03 13:3x) goal: owner's 60/50 rule with a RESTING exit. History only.
# Entry LIMIT: resting buy 0.60 fills only if the first ask >= 0.60 is <= 0.61 (maker, 0 fee). One buy per side, no re-buy.
# Exit: when bid <= W (warning), post a resting SELL at X=W (above the bid, maker, 0 fee). It fills when a later best bid >= X
# (a buyer reaches our price; queue ignored = optimistic). If bid <= H first -> taker sell at that bid + fee. Not stopped -> settle.
# BASE row = Zurich M44b LIMIT (taker sell at the first bid <= 0.50). Grid W {0.52,0.54,0.56} x H {0.46,0.48,0.50}, all reported.
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    g=runpy.run_path('analysis/v/maker2/m45_stop15_rebuy55.py')
CP,CD,fee=g['CP'],g['CD'],g['fee']
def leg(s,ask,bid,win,fout,payout,W,H,cut=295):
    for j in range(len(s)):
        if s[j]>cut: return None
        k=ask[j]
        if not np.isnan(k) and k>=0.60: break
    else: return None
    if k>0.611: return None
    P=0.60; posted=False
    for i in range(j+1,len(s)):
        if s[i]>cut: break
        b=bid[i]
        if np.isnan(b): continue
        if W is None:
            if b<=0.50: return ('stop',b-fout(b)-P)
            continue
        if posted and b>=W: return ('soft',W-P)
        if b<=H: return ('hard',b-fout(b)-P)
        if b<=W: posted=True
    return ('held',(payout if win else 0.0)-P)
def run(tag,C,fout,payout):
    rows=[('BASE',None,None)]+[(f'W{W:.2f} H{H:.2f}',W,H) for W in (0.52,0.54,0.56) for H in (0.46,0.48,0.50)]
    for name,W,H in rows:
        R=[];days=[]
        for e,(s,au,ad,bu,bd,w) in C.items():
            for x in (leg(s,au,bu,w,fout,payout,W,H),leg(s,ad,bd,not w,fout,payout,W,H)):
                if x: R.append(x); days.append(pd.to_datetime(e,unit='s').strftime('%m-%d'))
        df=pd.DataFrame(R,columns=['how','pnl']); df['day']=days; gd=df.groupby('day').pnl.sum(); h=len(df)//2
        ex=df[df.how!='held']; soft=(df.how=='soft').mean()
        print(f"{tag:5s} {name:12s} buys {len(df):4d} per buy {df.pnl.mean():+.4f} t{df.pnl.mean()/df.pnl.std()*np.sqrt(len(df)):+6.2f} halves {df.pnl[:h].mean():+.4f}/{df.pnl[h:].mean():+.4f} green {(gd>0).sum()}/{len(gd)} | exits {len(ex)/len(df):.0%} (soft {soft:.0%}) avg exit loss {ex.pnl.mean():+.3f}")
run('POLY',CP,fee,1.0)
run('PRED',CD,lambda x:0,0.98)
