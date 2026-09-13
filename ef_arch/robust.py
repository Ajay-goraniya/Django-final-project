#!/usr/bin/env python3
"""Robustness sweep: does each architecture survive different pricing assumptions?"""
import numpy as np, json, math
exec(open("testbed.py").read().split("RES=[]")[0].replace('COMPRESS=0.15','COMPRESS=0.15'))

def build(COMPRESS, SPREAD):
    def market(p): return np.clip(0.5+(p-0.5)*(1-COMPRESS)+SPREAD/2,0.02,0.98)
    return market(fair_contr), market(fair_fav)

def logistic_wf(y, price, side, win, margins):
    P=np.zeros(len(y))
    for h in range(24):
        tr=hour<h; te=hour==h
        if tr.sum()<2000: P[te]=(y[tr].mean() if tr.sum() else 0.5); continue
        mu=X[tr].mean(0); sd=np.maximum(X[tr].std(0),1e-9)      # train-only scaling
        Xtr=np.column_stack([np.ones(tr.sum()),(X[tr]-mu)/sd]); ytr=y[tr].astype(float)
        w=np.zeros(Xtr.shape[1])
        for _ in range(300):
            p=1/(1+np.exp(-Xtr@w)); w+=1.0*(Xtr.T@(ytr-p)/len(ytr)-0.01*w)
        P[te]=1/(1+np.exp(-(np.column_stack([np.ones(te.sum()),(X[te]-mu)/sd])@w)))
    return P

SCEN=[("no bias   c=0.00",0.00,0.010),("base      c=0.15",0.15,0.010),
      ("strong    c=0.25",0.25,0.010),("wide spr  c=0.15",0.15,0.025)]
ALL={}
for sname,C,S in SCEN:
    pc,pf=build(C,S)
    Pc=logistic_wf(win_contr,pc,contr_up,win_contr,None)
    Pf=logistic_wf(win_fav,pf,~contr_up,win_fav,None)
    evc=Pc-(1+FEE)*pc; evf=Pf-(1+FEE)*pf
    bc=evc>=evf; pb=np.where(bc,pc,pf); wb=np.where(bc,win_contr,win_fav); eb=np.maximum(evc,evf)
    conf=np.where(contr_up,b15[ii],-b15[ii])
    deep=np.where(~contr_up,0.5*b15[ii]+0.3*b610[ii]+0.2*b1120[ii],-(0.5*b15[ii]+0.3*b610[ii]+0.2*b1120[ii]))
    ff=np.where(~contr_up,fnorm5[ii],-fnorm5[ii])
    cands={
     "A03 EF ext+book":                 ((np.abs(z)>0.25)&(conf>0.15), contr_up, pc, win_contr, None),
     "A05 favourite+flow":              ((np.abs(z)>0.25)&(ff>0.15), ~contr_up, pf, win_fav, None),
     "A07 favourite deep-book":         (deep>0.25, ~contr_up, pf, win_fav, None),
     "A11 favourite late":              ((off>180)&(pf<0.70), ~contr_up, pf, win_fav, None),
     "A12 learned contrarian m=.10":    (evc>0.10, contr_up, pc, win_contr, None),
     "A13 learned favourite m=.10":     (evf>0.10, ~contr_up, pf, win_fav, None),
     "A13 learned favourite m=.10 K":   (evf>0.10, ~contr_up, pf, win_fav,
                                         0.5*np.clip(evf/np.maximum(1-(1+FEE)*pf,1e-6),0,1)),
     "A14 both-sides m=.10":            (eb>0.10, bc, pb, wb, None),
     "A14 both-sides m=.10 K":          (eb>0.10, bc, pb, wb,
                                         0.5*np.clip(eb/np.maximum(1-(1+FEE)*pb,1e-6),0,1)),
     "A14 both-sides m=.05 K":          (eb>0.05, bc, pb, wb,
                                         0.5*np.clip(eb/np.maximum(1-(1+FEE)*pb,1e-6),0,1)),
    }
    for n,(fire,side,pr,wn,sz) in cands.items():
        ALL.setdefault(n,{})[sname]=evaluate(n,fire,side,pr,wn,sz)

names=list(ALL); scen=[s[0] for s in SCEN]
print(f"{'architecture':<32}"+"".join(f"{s.split()[0]+s.split()[-1]:>16}" for s in scen)+f"{'min':>9}{'worstHr':>9}{'maxDD':>8}")
rank=[]
for n in names:
    pn=[ALL[n][s]["pnl"] for s in scen]
    wh=min(ALL[n][s]["worst_hour"] for s in scen); dd=max(ALL[n][s]["maxdd"] for s in scen)
    print(f"{n:<32}"+"".join(f"{v:>+16.2f}" for v in pn)+f"{min(pn):>+9.2f}{wh:>+9.2f}{dd:>8.2f}")
    rank.append((min(pn),n,ALL[n]))
rank.sort(reverse=True)
print("\nRanked by WORST-CASE PnL across pricing assumptions:")
for v,n,_ in rank: print(f"   {v:>+8.2f}   {n}")
json.dump({n:{s:ALL[n][s] for s in scen} for n in names},open("robust.json","w"),indent=1,default=str)
