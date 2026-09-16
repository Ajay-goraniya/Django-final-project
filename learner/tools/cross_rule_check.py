"""Plain cross-venue spread rule, no ML: at decision second S, if Polymarket UP ask minus Predict.fun
implied P(UP) exceeds THR buy UP on Predict.fun at its raw ask; if below -THR buy DOWN. One fire per
candle per S. Grades from the outcome table. Full grid over S x THR, halves, liquidity floor, and the
null (buy whichever side Polymarket favours regardless of the spread). Overlap with twin C's EF fires."""
import sqlite3, numpy as np
D="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
c=sqlite3.connect(f"{D}/venues.sqlite3")
out=dict(c.execute("select epoch, actual from outcome"))
rows={}
for ep,sec,pu,yu,yd,su,sd in c.execute("select epoch,sec,poly_up,pred_up,pred_dn,pred_size_up,pred_size_dn from q order by epoch,sec"):
    rows.setdefault(ep,{})[sec]=(pu,yu,yd,su,sd)
t=sqlite3.connect(f"{D}/v11/tests/c_thr1.sqlite3")
ef={cid//1000:d for cid,d in t.execute("select candle_id,direction from ef_predictions")}
FEE=0.98
def sample(ep,S):
    r=rows[ep]; base=min(r)
    for s in (S,S-5,S+5,S-10):
        v=r.get(base+s)
        if v and v[0] is not None and v[1] is not None and v[2] is not None: return v
    return None
def run(S,THR,floor=0,haircut=0.0,null=False,only=None):
    res=[]
    for ep in sorted(rows):
        if ep not in out or out[ep] not in("UP","DOWN"): continue
        v=sample(ep,S)
        if not v: continue
        pu,yu,yd,su,sd=v
        imp=yu/(yu+yd); cross=pu-imp
        if null: side="UP" if pu>0.5 else "DOWN"
        elif cross>THR: side="UP"
        elif cross<-THR: side="DOWN"
        else: continue
        ask=(yu if side=="UP" else yd)+haircut; sz=su if side=="UP" else sd
        if not (0.02<ask<0.98): continue
        if floor and (sz is None or sz<floor): continue
        if only=="ef_same" and ef.get(ep)!=side: continue
        if only=="ef_none" and ep in ef: continue
        hit=out[ep]==side
        res.append((ep,((1/ask)*FEE-1) if hit else -1.0,hit,ask))
    return res
def fmt(r):
    if not r: return "n=0"
    p=[x[1] for x in r]; h=len(p)//2
    return f"n={len(r):3d} hit {np.mean([x[2] for x in r])*100:3.0f}% per-fire {np.mean(p):+.3f} halves {sum(p[:h]):+.1f}/{sum(p[h:]):+.1f} ask~{np.median([x[3] for x in r]):.2f}"
print("epochs",len([e for e in rows if e in out]),"twinC EF fires",len(ef))
for S in (30,60,90,120,150,180,210,240):
    print(f"--- S={S}  null(poly side): {fmt(run(S,0,null=True))}")
    for THR in (0.02,0.04,0.06,0.08,0.10,0.15):
        print(f"   thr {THR:.2f}: {fmt(run(S,THR))} | +10c {fmt(run(S,THR,haircut=0.10))[:40]} | floor50 {fmt(run(S,THR,floor=50))[:40]}")
print("=== overlap with twin C EF (thr 0.05): same side as EF fire / candles with no EF fire")
for S in (120,180,210,240):
    print(f"S={S} ef_same: {fmt(run(S,0.05,only='ef_same'))} | no EF fire: {fmt(run(S,0.05,only='ef_none'))}")
