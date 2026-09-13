#!/usr/bin/env python3
"""Design + quick-test many EF architectures on the 2026-08-01 grid."""
import numpy as np, json, math
d=np.load("grid.npz")
mid,micro,b15,b610,b1120=d["mid"],d["micro"],d["b15"],d["b610"],d["b1120"]
flow,tcnt,spot,svol,spr=d["flow"],d["tcnt"],d["spot"],d["svol"],d["spr"]
SEC=len(spot); CAND=300; NC=SEC//CAND          # 288 candles
FEE=0.02; SPREAD=0.01; COMPRESS=0.15           # favourite-longshot: prices compressed toward 0.5
rng=np.random.default_rng(0)

def roll_sum(a,w):
    c=np.concatenate([[0.0],np.cumsum(a)]); out=np.empty_like(a)
    for i in range(len(a)):
        lo=max(0,i-w+1); out[i]=c[i+1]-c[lo]
    return out
def roll_sum_fast(a,w):
    c=np.concatenate([[0.0],np.cumsum(a)]); idx=np.arange(len(a))
    lo=np.maximum(0,idx-w+1)
    return c[idx+1]-c[lo]

logret=np.zeros(SEC); logret[1:]=np.diff(np.log(np.maximum(spot,1e-9)))
# causal rolling vol (per sqrt-second) over trailing 600s, shifted by 1 to exclude current
var600=roll_sum_fast(logret**2,600)
sig=np.sqrt(np.maximum(var600,1e-18)/600.0)
sig=np.concatenate([[sig[0]],sig[:-1]])        # shift -> strictly past
f1=roll_sum_fast(flow,1); f5=roll_sum_fast(flow,5); f30=roll_sum_fast(flow,30)
n30=roll_sum_fast(np.abs(flow),30)
fnorm5=f5/np.maximum(n30,1e-9); fnorm30=f30/np.maximum(n30,1e-9)
tc5=roll_sum_fast(tcnt,5)

def NORM(x):
    return 0.5*(1.0+np.vectorize(math.erf)(x/math.sqrt(2.0)))

# ---- decision grid: every 5s inside each candle, seconds 5..295 -------------
rows=[]
for c in range(NC):
    s0=c*CAND; op=spot[s0]; cl=spot[s0+CAND-1]
    up_closed = cl>op
    for off in range(5,300,5):
        i=s0+off; left=CAND-off
        px=spot[i]; s=max(sig[i],1e-9)
        drift=(px-op)/max(px*s*math.sqrt(left),1e-12)   # z of distance to open over remaining time
        rows.append((c,i,off,left,op,px,cl,up_closed,drift,s))
A=np.array([[r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9]] for r in rows],float)
ci=A[:,0].astype(int); ii=A[:,1].astype(int); off=A[:,2]; left=A[:,3]
op=A[:,4]; px=A[:,5]; cl=A[:,6]; upc=A[:,7].astype(bool); z=A[:,8]; sg=A[:,9]

fair_up=NORM(z)                                  # P(close>open) under driftless GBM
cur_up = px>op                                   # candle currently up
# EF-style contrarian side, and the momentum/favourite side
contr_up = ~cur_up                               # contrarian bets against current body
fair_contr = np.where(contr_up, fair_up, 1-fair_up)
fair_fav   = 1-fair_contr
def market(p):                                   # favourite-longshot compression + half-spread
    return np.clip(0.5+(p-0.5)*(1-COMPRESS)+SPREAD/2, 0.02, 0.98)
pc=market(fair_contr); pf=market(fair_fav)
win_contr = (contr_up==upc); win_fav = (~contr_up==upc)

X=np.column_stack([b15[ii],b610[ii],b1120[ii],fnorm5[ii],fnorm30[ii],
                   (micro[ii]-mid[ii])/np.maximum(spr[ii],1e-9),
                   np.tanh(z),left/300.0,np.log1p(tc5[ii]),
                   np.sign(px-op)*np.tanh(np.abs(px-op)/np.maximum(px*sg*np.sqrt(off),1e-12))])
X=np.nan_to_num(X,nan=0.0,posinf=0.0,neginf=0.0)
Xs=(X-X.mean(0))/np.maximum(X.std(0),1e-9)
hour=(ii//3600).astype(int)

def ret(win,p):  return np.where(win, 1.0/((1+FEE)*p)-1.0, -1.0)

def evaluate(name, fire, side_contr, price, win, size=None):
    """One trade per candle: first firing decision point."""
    out={"name":name}
    idx=np.where(fire)[0]
    if len(idx)==0: return {**out,"trades":0,"pnl":0.0,"per_trade":0.0,"winrate":None,"worst_hour":0.0}
    seen=set(); take=[]
    for k in idx:
        c=ci[k]
        if c in seen: continue
        seen.add(c); take.append(k)
    take=np.array(take)
    p=price[take]; w=win[take]; r=ret(w,p)
    sz=np.ones(len(take)) if size is None else np.clip(size[take],0,1)
    pnl=r*sz
    hh=hour[take]
    hourly=np.array([pnl[hh==h].sum() for h in range(24)])
    eq=np.cumsum(pnl); dd=float((np.maximum.accumulate(eq)-eq).max()) if len(eq) else 0.0
    return {**out,"trades":int(len(take)),"pnl":float(pnl.sum()),
            "per_trade":float(pnl.sum()/len(take)),"winrate":float(w.mean()),
            "avg_price":float(p.mean()),"worst_hour":float(hourly.min()),
            "pos_hours":int((hourly>0).sum()),"maxdd":dd,"hourly":hourly.tolist()}

RES=[]
# ---------------- architectures -------------------------------------------
# 1 null: EV on fair model itself (should be ~0 minus costs)
ev_c=fair_contr-(1+FEE)*pc
RES.append(evaluate("A01 fair-EV contrarian (null)", ev_c>0.0, contr_up, pc, win_contr))
# 2 momentum / favourite side, pure
ev_f=fair_fav-(1+FEE)*pf
RES.append(evaluate("A02 favourite side, EV>0", ev_f>0.0, ~contr_up, pf, win_fav))
# 3 classic EF: extension + book confirms reversal
conf=np.where(contr_up, b15[ii], -b15[ii])
RES.append(evaluate("A03 EF-style ext+book", (np.abs(z)>0.25)&(conf>0.15), contr_up, pc, win_contr))
# 4 flow-aligned contrarian
fa=np.where(contr_up, fnorm5[ii], -fnorm5[ii])
RES.append(evaluate("A04 contrarian + flow align", (np.abs(z)>0.25)&(fa>0.15), contr_up, pc, win_contr))
# 5 flow-aligned favourite (momentum)
ff=np.where(~contr_up, fnorm5[ii], -fnorm5[ii])
RES.append(evaluate("A05 favourite + flow align", (np.abs(z)>0.25)&(ff>0.15), ~contr_up, pf, win_fav))
# 6 book imbalance only, contrarian
RES.append(evaluate("A06 book-imbalance contrarian", conf>0.30, contr_up, pc, win_contr))
# 7 deep-book confluence favourite
deep=np.where(~contr_up, 0.5*b15[ii]+0.3*b610[ii]+0.2*b1120[ii], -(0.5*b15[ii]+0.3*b610[ii]+0.2*b1120[ii]))
RES.append(evaluate("A07 favourite deep-book", deep>0.25, ~contr_up, pf, win_fav))
# 8 cheap-only contrarian (price gate)
RES.append(evaluate("A08 contrarian price<0.40", (pc<0.40)&(np.abs(z)>0.3), contr_up, pc, win_contr))
# 9 favourite when cheap-ish (<0.62)
RES.append(evaluate("A09 favourite price<0.62", (pf<0.62)&(np.abs(z)>0.3), ~contr_up, pf, win_fav))
# 10 early only contrarian
RES.append(evaluate("A10 contrarian early t<90s", (off<90)&(np.abs(z)>0.25)&(conf>0.10), contr_up, pc, win_contr))
# 11 late favourite (longshot bias harvest)
RES.append(evaluate("A11 favourite late t>180s", (off>180)&(pf<0.70), ~contr_up, pf, win_fav))
np.save("Xs.npy",Xs)
json.dump({"n_decisions":int(len(ci))},open("meta.json","w"))
# ---------------- learned models (walk-forward by hour) --------------------
def logistic_wf(y, name, price, side_contr, win, thr_grid=(0.0,)):
    """Train on hours < h, predict hour h. Pure numpy logistic + L2."""
    P=np.zeros(len(y))
    for h in range(24):
        tr=hour<h; te=hour==h
        if tr.sum()<2000: P[te]=y[tr].mean() if tr.sum() else 0.5; continue
        Xtr=np.column_stack([np.ones(tr.sum()),Xs[tr]]); ytr=y[tr].astype(float)
        w=np.zeros(Xtr.shape[1])
        for _ in range(300):
            p=1/(1+np.exp(-Xtr@w)); g=Xtr.T@(ytr-p)/len(ytr)-0.01*w
            w+=1.0*g
        P[te]=1/(1+np.exp(-(np.column_stack([np.ones(te.sum()),Xs[te]])@w)))
    out=[]
    for m in thr_grid:
        ev=P-(1+FEE)*price
        kel=np.clip((P-(1+FEE)*price)/np.maximum(1-(1+FEE)*price,1e-6),0,1)
        out.append(evaluate(f"{name} margin={m:.2f}", ev>m, side_contr, price, win))
        out.append(evaluate(f"{name} margin={m:.2f} +halfKelly", ev>m, side_contr, price, win, size=0.5*kel))
    return out,P

r1,Pc=logistic_wf(win_contr,"A12 learned contrarian",pc,contr_up,win_contr,(0.00,0.05,0.10))
r2,Pf=logistic_wf(win_fav,"A13 learned favourite",pf,~contr_up,win_fav,(0.00,0.05,0.10))
RES+=r1; RES+=r2
# 14 best-of-both: take whichever side has larger EV
evc=Pc-(1+FEE)*pc; evf=Pf-(1+FEE)*pf
better_c=evc>=evf
price_b=np.where(better_c,pc,pf); win_b=np.where(better_c,win_contr,win_fav)
ev_b=np.maximum(evc,evf)
for m in (0.00,0.05,0.10):
    kel=np.clip(ev_b/np.maximum(1-(1+FEE)*price_b,1e-6),0,1)
    RES.append(evaluate(f"A14 learned both-sides margin={m:.2f}", ev_b>m, better_c, price_b, win_b))
    RES.append(evaluate(f"A14 learned both-sides margin={m:.2f} +halfKelly", ev_b>m, better_c, price_b, win_b, size=0.5*kel))

RES.sort(key=lambda r:-r["pnl"])
print(f"{'architecture':<48}{'trades':>7}{'win%':>7}{'avgP':>7}{'PnL':>9}{'/trade':>9}{'worstHr':>9}{'+hrs':>6}{'maxDD':>8}")
for r in RES:
    if r["trades"]==0: print(f"{r['name']:<48}{0:>7}"); continue
    print(f"{r['name']:<48}{r['trades']:>7}{100*r['winrate']:>6.1f}%{r['avg_price']:>7.3f}"
          f"{r['pnl']:>+9.2f}{r['per_trade']:>+9.3f}{r['worst_hour']:>+9.2f}{r['pos_hours']:>6}{r['maxdd']:>8.2f}")
json.dump(RES,open("results_quick.json","w"),indent=1)
