#!/usr/bin/env python3
"""Replay 12.18.0's lane price rule on an EXISTING journal: every MAIN/REVERSAL decision the lane logged
(diagnostics rows with lane=MAIN/REVERSAL carrying side, p, sec, ask_up, ask_dn), first decision per candle,
accepted iff ask(side) <= cap, 5-share minimum top-up, Polymarket fee 1.67% of shares both ways.
Label: results.actual (Gamma resolution) where the candle was traded; else TWAP60 proxy from 1 s klines
(--klines), flagged. Whole cap grid printed, both halves, never a best cell.
Usage: replay_lane_cap.py --journal X.sqlite3 [--journal Y.sqlite3] [--klines k_*.sqlite3] [--since EPOCH]"""
import argparse,sqlite3,json,datetime as dt,numpy as np,os
ap=argparse.ArgumentParser(); ap.add_argument('--journal',action='append',required=True); ap.add_argument('--klines',nargs='*',default=[])
ap.add_argument('--since',type=int,default=0); a=ap.parse_args()
FEE=0.0167; MINSH=5.0
KT=[];KC=[]
for kp in a.klines:
    for t,c in sqlite3.connect(kp).execute("select ts,cl from k1s order by ts"): KT.append(t/1000); KC.append(c)
KT=np.array(KT); KC=np.array(KC)
if len(KT): o=np.argsort(KT,kind='stable'); KT=KT[o]; KC=KC[o]; k=np.concatenate([[True],np.diff(KT)>0]); KT=KT[k]; KC=KC[k]
def twap(t0,t1):
    if len(KT)==0: return None
    i=int(np.searchsorted(KT,t0)); j=int(np.searchsorted(KT,t1)); s=KC[i:j]; return float(s.mean()) if len(s)>=45 else None
def proxy(ep):
    lo=twap(ep-60,ep); hi=twap(ep+240,ep+300)
    return None if lo is None or hi is None else ('UP' if hi>=lo else 'DOWN')
label={}; src={}
dec={}  # (kind,epoch) -> first decision
for jp in a.journal:
    c=sqlite3.connect(f'file:{jp}?mode=ro',uri=True)
    for ep,act in c.execute("select epoch,actual from results where actual in ('UP','DOWN')"): label[int(ep)]=act; src[int(ep)]='exact'
    for ts,ep,d in c.execute("select ts,epoch,detail from diagnostics where epoch>=? order by ts",(a.since,)):
        try: j=json.loads(d)
        except Exception: continue
        if not isinstance(j,dict) or j.get('lane') not in ('MAIN','REVERSAL') or j.get('side') not in ('UP','DOWN'): continue
        key=(j['lane'],int(ep))
        if key in dec: continue
        au,ad=j.get('ask_up'),j.get('ask_dn')
        if au is None or ad is None: continue
        dec[key]=dict(ts=ts,ep=int(ep),kind=j['lane'],side=j['side'],p=j.get('p'),sec=j.get('sec'),ask=float(au if j['side']=='UP' else ad))
for (kind,ep) in list(dec):
    if ep not in label:
        pr=proxy(ep)
        if pr: label[ep]=pr; src[ep]='proxy'
rows=[d for d in dec.values() if d['ep'] in label]
print(f'decisions {len(dec)} labelled {len(rows)} (exact {sum(1 for d in rows if src[d["ep"]]=="exact")}, proxy {sum(1 for d in rows if src[d["ep"]]=="proxy")}) span {dt.datetime.utcfromtimestamp(min(d["ep"] for d in rows)):%m-%d %H:%M} -> {dt.datetime.utcfromtimestamp(max(d["ep"] for d in rows)):%m-%d %H:%M}')
def per1(d,win): return ((1-FEE)/d['ask']-1) if win else (-1-FEE)
def table(kind):
    R=sorted([d for d in rows if d['kind']==kind],key=lambda d:d['ep'])
    if not R: print(f'{kind}: none'); return
    h=R[len(R)//2]['ep']
    print(f'\n== {kind}: {len(R)} candles, ask median {np.median([d["ask"] for d in R]):.2f}, sec median {np.median([d["sec"] or 0 for d in R]):.0f} ==')
    print('cap    n    hit   per$1   H1     H2     exact-only per$1(n)   $ at 5sh')
    for cap in (0.70,0.80,0.85,0.90,0.95,1.00):
        S=[d for d in R if d['ask']<=cap+1e-9]
        if not S: print(f'{cap:.2f}  none'); continue
        w=[label[d['ep']]==d['side'] for d in S]; v=[per1(d,x) for d,x in zip(S,w)]
        e=[(d,x) for d,x in zip(S,w) if src[d['ep']]=='exact']
        stake=[max(3.0,MINSH*d['ask']) for d in S]; pnl=sum(s*per1(d,x) for s,d,x in zip(stake,S,w))
        f=lambda z: np.mean(z) if z else float('nan')
        print(f'{cap:.2f} {len(S):4d} {100*np.mean(w):5.1f}% {f(v):+.3f} {f([y for d,y in zip(S,v) if d["ep"]<h]):+.3f} {f([y for d,y in zip(S,v) if d["ep"]>=h]):+.3f}  {f([per1(d,x) for d,x in e]):+.3f}({len(e)})  {pnl:+8.2f}{"*" if len(S)<60 else ""}')
    print('sec band at cap 0.90:')
    S=[d for d in R if d['ask']<=0.90]
    for lo,hi in ((0,90),(90,180),(180,300)):
        T=[d for d in S if lo<=(d['sec'] or 0)<hi]
        if T: w=[label[d['ep']]==d['side'] for d in T]; print(f'  {lo}-{hi}s n={len(T)} hit={100*np.mean(w):.0f}% per$1={np.mean([per1(d,x) for d,x in zip(T,w)]):+.3f} ask_med={np.median([d["ask"] for d in T]):.2f}{"*" if len(T)<60 else ""}')
table('MAIN'); table('REVERSAL')
