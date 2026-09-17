import numpy as np, json, math
exec(open("testbed.py").read().split("RES=[]")[0])
def market(p,C,S): return np.clip(0.5+(p-0.5)*(1-C)+S/2,0.02,0.98)
def logistic_wf(y):
    P=np.zeros(len(y))
    for h in range(24):
        tr=hour<h; te=hour==h
        if tr.sum()<2000: P[te]=(y[tr].mean() if tr.sum() else 0.5); continue
        mu=X[tr].mean(0); sd=np.maximum(X[tr].std(0),1e-9)
        Xtr=np.column_stack([np.ones(tr.sum()),(X[tr]-mu)/sd]); ytr=y[tr].astype(float); w=np.zeros(Xtr.shape[1])
        for _ in range(300): p=1/(1+np.exp(-Xtr@w)); w+=1.0*(Xtr.T@(ytr-p)/len(ytr)-0.01*w)
        P[te]=1/(1+np.exp(-(np.column_stack([np.ones(te.sum()),(X[te]-mu)/sd])@w)))
    return P
Pc=logistic_wf(win_contr); Pf=logistic_wf(win_fav)

# per-candle regime labels (computed from that candle only -> descriptive, not used to trade)
reg=np.empty(NC,object); rng_=np.zeros(NC); bod=np.zeros(NC)
for c in range(NC):
    s=spot[c*CAND:(c+1)*CAND]; hi,lo=s.max(),s.min(); o,cl_=s[0],s[-1]
    rng_[c]=(hi-lo)/o*1e4; bod[c]=abs(cl_-o)/max(hi-lo,1e-9)
med=np.median(rng_)
for c in range(NC):
    reg[c]=("trend" if bod[c]>0.5 else "chop")+("/hiVol" if rng_[c]>med else "/loVol")

def trades_of(fire,side,price,win,size=None):
    idx=np.where(fire)[0]; seen=set(); take=[]
    for k in idx:
        if ci[k] in seen: continue
        seen.add(ci[k]); take.append(k)
    take=np.array(take,int)
    if len(take)==0: return take,np.array([]),np.array([])
    r=np.where(win[take],1.0/((1+FEE)*price[take])-1.0,-1.0)
    sz=np.ones(len(take)) if size is None else np.clip(size[take],0,1)
    return take,r*sz,win[take]

def boot(p,n=4000):
    if len(p)==0: return (0,0)
    rs=np.random.default_rng(1)
    m=[p[rs.integers(0,len(p),len(p))].mean() for _ in range(n)]
    return float(np.percentile(m,2.5)),float(np.percentile(m,97.5))

for C,S,tag in ((0.15,0.010,"base c=0.15"),(0.00,0.010,"no-bias c=0.00"),(0.25,0.010,"strong c=0.25")):
    pc,pf=market(fair_contr,C,S),market(fair_fav,C,S)
    evc=Pc-(1+FEE)*pc; evf=Pf-(1+FEE)*pf
    bc=evc>=evf; pb=np.where(bc,pc,pf); wb=np.where(bc,win_contr,win_fav); eb=np.maximum(evc,evf)
    kelf=0.5*np.clip(evf/np.maximum(1-(1+FEE)*pf,1e-6),0,1)
    kelb=0.5*np.clip(eb/np.maximum(1-(1+FEE)*pb,1e-6),0,1)
    SETS={"A13 favourite m=.10":(evf>0.10,~contr_up,pf,win_fav,None),
          "A13 favourite m=.10 halfKelly":(evf>0.10,~contr_up,pf,win_fav,kelf),
          "A14 both-sides m=.10":(eb>0.10,bc,pb,wb,None),
          "A14 both-sides m=.10 halfKelly":(eb>0.10,bc,pb,wb,kelb),
          "A03 current-EF style":((np.abs(z)>0.25)&(np.where(contr_up,b15[ii],-b15[ii])>0.15),contr_up,pc,win_contr,None)}
    print(f"\n########## pricing scenario: {tag} ##########")
    for n,(f_,s_,p_,w_,z_) in SETS.items():
        take,pnl,win=trades_of(f_,s_,p_,w_,z_)
        if len(take)==0: print(f"{n:<34} no trades"); continue
        lo,hi=boot(pnl)
        print(f"{n:<34} n={len(take):>3} win {100*win.mean():>5.1f}% "
              f"PnL {pnl.sum():>+8.2f}  /trade {pnl.mean():>+7.4f}  95%CI[{lo:+.4f},{hi:+.4f}]"
              f"  {'POSITIVE' if lo>0 else 'not sig'}")
        cregs=np.array([reg[ci[k]] for k in take])
        parts=[]
        for r in ("trend/hiVol","trend/loVol","chop/hiVol","chop/loVol"):
            m=cregs==r
            if m.sum(): parts.append(f"{r}: n={m.sum():>3} {pnl[m].sum():>+7.2f}")
        print(f"{'':34} "+" | ".join(parts))
