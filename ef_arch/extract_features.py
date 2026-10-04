#!/usr/bin/env python3
"""Build a 1-second causal feature grid from the replay dataset (no Build36)."""
import glob, numpy as np, pyarrow.parquet as pq, pathlib, time
DATA = pathlib.Path("/home/user/Django-final-project/btc_replay_2026-08-01_24h/normalized")
OUT  = pathlib.Path("/home/user/Django-final-project/ef_arch/grid.npz")
W0, W1 = 1785542400_000, 1785628800_000            # ms
SEC = (W1 - W0)//1000                              # 86400
t0=time.time()

mid=np.full(SEC,np.nan); micro=np.full(SEC,np.nan)
b15=np.full(SEC,np.nan); b610=np.full(SEC,np.nan); b1120=np.full(SEC,np.nan)
spr=np.full(SEC,np.nan); dcnt=np.zeros(SEC)
flow=np.zeros(SEC); tcnt=np.zeros(SEC); tvol=np.zeros(SEC)
spot=np.full(SEC,np.nan); svol=np.zeros(SEC)

for h in range(24):
    f=DATA/f"perp_depth20_{h:02d}.parquet"
    if f.exists():
        cols=["timestamp","bid_px_0","ask_px_0"]+[f"bid_qty_{i}" for i in range(20)]+[f"ask_qty_{i}" for i in range(20)]
        t=pq.read_table(f,columns=cols)
        ts=(np.asarray(t.column("timestamp"))//1000 - W0)//1000
        bq=np.vstack([np.asarray(t.column(f"bid_qty_{i}"),float) for i in range(20)])
        aq=np.vstack([np.asarray(t.column(f"ask_qty_{i}"),float) for i in range(20)])
        bp=np.asarray(t.column("bid_px_0"),float); ap=np.asarray(t.column("ask_px_0"),float)
        def imb(lo,hi):
            b=np.nansum(bq[lo:hi],0); a=np.nansum(aq[lo:hi],0); s=b+a
            return np.where(s>0,(b-a)/np.where(s>0,s,1),0.0)
        z15,z610,z1120=imb(0,5),imb(5,10),imb(10,20)
        m=(ap*bq[0]+bp*aq[0])/np.maximum(bq[0]+aq[0],1e-9)
        ok=(ts>=0)&(ts<SEC)
        idx=ts[ok]
        # last value wins within a second -> causal "state as of end of second"
        mid[idx]=((bp+ap)/2)[ok]; micro[idx]=m[ok]
        b15[idx]=z15[ok]; b610[idx]=z610[ok]; b1120[idx]=z1120[ok]
        spr[idx]=(ap-bp)[ok]
        np.add.at(dcnt,idx,1)
    f=DATA/f"perp_trades_{h:02d}.parquet"
    if f.exists():
        t=pq.read_table(f,columns=["timestamp","signed_quote_notional","quantity"])
        ts=(np.asarray(t.column("timestamp"))//1000 - W0)//1000
        ok=(ts>=0)&(ts<SEC); idx=ts[ok]
        np.add.at(flow,idx,np.asarray(t.column("signed_quote_notional"),float)[ok])
        np.add.at(tcnt,idx,1)
        np.add.at(tvol,idx,np.asarray(t.column("quantity"),float)[ok])
    f=DATA/f"spot_aggtrades_{h:02d}.parquet"
    if f.exists():
        t=pq.read_table(f,columns=["timestamp","price","quantity"])
        ts=(np.asarray(t.column("timestamp"))//1000 - W0)//1000
        ok=(ts>=0)&(ts<SEC); idx=ts[ok]
        spot[idx]=np.asarray(t.column("price"),float)[ok]
        np.add.at(svol,idx,np.asarray(t.column("quantity"),float)[ok])
    print(f"  hour {h:02d} done {time.time()-t0:.0f}s",flush=True)

def ffill(a):
    idx=np.where(~np.isnan(a))[0]
    if len(idx)==0: return a
    out=a.copy(); first=idx[0]
    f=np.maximum.accumulate(np.where(~np.isnan(a),np.arange(len(a)),0))
    out=a[f]; out[:first]=a[first]
    return out
for name in ("mid","micro","b15","b610","b1120","spr","spot"):
    globals()[name]=ffill(globals()[name])

np.savez_compressed(OUT, mid=mid, micro=micro, b15=b15, b610=b610, b1120=b1120,
                    spr=spr, dcnt=dcnt, flow=flow, tcnt=tcnt, tvol=tvol,
                    spot=spot, svol=svol, W0=W0)
print(f"saved {OUT}  ({time.time()-t0:.0f}s)  seconds={SEC}")
