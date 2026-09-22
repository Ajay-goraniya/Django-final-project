#!/usr/bin/env python3
"""Train on the engine's OWN decision snapshots (every evaluated second, fired or not), full feature set as the engine
computed it, label = Polymarket resolution. Walk-forward by UTC day. Compare against the venue price on the same rows.
Usage: python3 train_snapshots.py --journals a.sqlite3 b.sqlite3 --venues venues.sqlite3 [--min-train-days 2]
Read-only. Prints one compact table. No files written unless --out is given."""
import argparse,sqlite3,json,datetime as dt,math,sys,numpy as np
from collections import defaultdict
ap=argparse.ArgumentParser(); ap.add_argument('--journals',nargs='+',required=True); ap.add_argument('--venues',required=True)
ap.add_argument('--min-train-days',type=int,default=2); ap.add_argument('--out',default=None)
ap.add_argument('--klines',nargs='*',default=[],help='sqlite files with k1s(ts ms, cl) 1-second Binance closes; enables settlement-line features'); a=ap.parse_args()
oc={}
vc=sqlite3.connect(a.venues)
for ep,act in vc.execute("select epoch,actual from outcome where actual in ('UP','DOWN')"): oc[int(ep)]=1 if act=='UP' else 0
FEATS=['move_bps','ret5','ret15','ret30','ret60','rv60','range_bps','pos_in_range','dist_hi_bps','dist_lo_bps','spot_imb15','spot_imb60',
       'ofi5','ofi15','ofi60','perp_n15','basis_bps','spread_bps','imb5','imb20','micro_bps','prev1_bps','prev2_bps','sec_left','hod_sin','hod_cos','p_venue','lv','mv_x_sec','lv_x_sec']
import bisect
KT=[];KC=[]
for kp in a.klines:
    for t,c in sqlite3.connect(kp).execute("select ts,cl from k1s order by ts"): KT.append(t/1000); KC.append(c)
KT=np.array(KT); KC=np.array(KC)
def _seg(t0,t1):
    i=int(np.searchsorted(KT,t0)); j=int(np.searchsorted(KT,t1)); return KC[i:j]
def rule_feats(ep,sec):
    if len(KT)==0: return None
    lo=_seg(ep-60,ep); t=ep+sec
    if len(lo)<45: return None
    line_open=float(lo.mean()); cur=_seg(t-3,t)
    if len(cur)==0: return None
    p=float(cur[-1]); ln_seg=_seg(t-60,t) if sec>=60 else _seg(ep,t)
    if len(ln_seg)<5: return None
    line_now=float(ln_seg.mean()); body=_seg(ep-120,t)
    sig1=float(np.std(np.diff(np.log(body)))) if len(body)>10 else 1e-4
    known=_seg(ep+240,t) if sec>240 else np.array([]); T=300-max(sec,240); proj=(known.sum()+T*p)/60.0
    tau=max(0,240-sec); sd=sig1*math.sqrt(tau+T/3.0)*(T/60.0)+1e-9
    pup=0.5*(1+math.erf(((proj/line_open-1)/sd)/math.sqrt(2)))
    return [(p/line_open-1)*1e4,(line_now/line_open-1)*1e4,pup]
RULE=['move_line_bps','line_move_bps','mech_pup']
if a.klines: FEATS=FEATS+RULE
rows=[]; seen=set()
for jp in a.journals:
    c=sqlite3.connect(jp)
    for ep,ts,d in c.execute("select epoch,ts,detail from diagnostics"):
        try: j=json.loads(d)
        except Exception: continue
        if not (isinstance(j,dict) and 'fire' in j and j.get('features')): continue
        f=j['features']; ep=int(ep)
        if ep not in oc: continue
        try: x=[float(f[k]) for k in FEATS if k not in RULE]
        except Exception: continue
        if a.klines:
            rf=rule_feats(ep,float(j.get('sec',0)))
            if rf is None: continue
            x=x+rf
        au,ad=f.get('_ask_up'),f.get('_ask_dn')
        if au is None or ad is None or not (0<au<1 and 0<ad<1): continue
        key=(ep,int(j.get('sec',0)))
        if key in seen: continue
        pp=float(j.get('p') or 0.5); pup=pp if str(j.get('side','UP')).upper()=='UP' else 1-pp
        seen.add(key); rows.append((ep,float(j.get('sec',0)),x,float(au),float(ad),oc[ep],pup))
rows.sort(key=lambda r:(r[0],r[1]))
if len(rows)<500: print('too few labelled snapshots:',len(rows)); sys.exit(0)
eps=np.array([r[0] for r in rows]); sec=np.array([r[1] for r in rows]); X=np.array([r[2] for r in rows]); au=np.array([r[3] for r in rows]); ad=np.array([r[4] for r in rows]); y=np.array([r[5] for r in rows]); pv10=np.array([r[6] for r in rows])
pv=X[:,FEATS.index('p_venue')]
day=np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in eps]); days=sorted(set(day))
print(f'snapshots {len(rows)} candles {len(set(eps))} days {days}')
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from scipy.stats import binomtest
def wf(kind):
    pred=np.full(len(rows),np.nan)
    for k in range(a.min_train_days,len(days)):
        tr=np.isin(day,days[:k]); te=day==days[k]
        if tr.sum()<300 or te.sum()==0: continue
        if kind=='logit':
            sc=StandardScaler().fit(X[tr]); m=LogisticRegression(C=0.3,max_iter=1000).fit(sc.transform(X[tr]),y[tr]); pred[te]=m.predict_proba(sc.transform(X[te]))[:,1]
        else:
            m=HistGradientBoostingClassifier(max_depth=3,learning_rate=0.05,max_iter=200,l2_regularization=1.0).fit(X[tr],y[tr]); pred[te]=m.predict_proba(X[te])[:,1]
    return pred
P={'logit':wf('logit'),'gbm':wf('gbm')}
m=~np.isnan(P['logit'])
if m.sum()<300: print('too few walk-forward test rows',m.sum()); sys.exit(0)
brier=lambda p: float(np.mean((p[m]-y[m])**2)); acc=lambda p: float(np.mean((p[m]>0.5)==(y[m]==1)))
print(f'test rows {m.sum()} | Brier venue {brier(pv):.4f} v10-live {brier(pv10):.4f} logit {brier(P["logit"]):.4f} gbm {brier(P["gbm"]):.4f} | acc venue {acc(pv):.3f} v10 {acc(pv10):.3f} logit {acc(P["logit"]):.3f} gbm {acc(P["gbm"]):.3f}')
# paired direction vs venue, per second band
for name in ('logit','gbm'):
    out=[]
    for lo,hi in ((15,60),(60,150),(150,241)):
        s=m&(sec>=lo)&(sec<hi); mr=(P[name][s]>0.5)==(y[s]==1); vr=(pv[s]>0.5)==(y[s]==1); b=int((mr&~vr).sum()); c_=int((~mr&vr).sum())
        out.append(f'{lo}-{hi}s {b}/{c_} p={binomtest(b,b+c_,0.5).pvalue if b+c_ else 1:.2f}')
    print(f'{name} vs venue, discordant (model right/venue right): '+' | '.join(out))
# trading: one trade per candle, first second where p_side*(1-fee)-ask_side > margin; per$1 after fee; H1|H2
FEE=0.0167; uniq=sorted(set(eps[m])); half=uniq[len(uniq)//2]
def trade(p,mg):
    res={}
    for i in np.lexsort((sec,eps)):
        if not m[i] or eps[i] in res: continue
        cands=[]
        if p[i]*(1-FEE)-au[i]>mg: cands.append(('UP',au[i],p[i]))
        if (1-p[i])*(1-FEE)-ad[i]>mg: cands.append(('DOWN',ad[i],1-p[i]))
        if not cands: continue
        side,ask,pp=max(cands,key=lambda t:t[2]*(1-FEE)-t[1]); win=(y[i]==1)==(side=='UP')
        res[eps[i]]=((1/ask-1-FEE) if win else (-1-FEE), eps[i]<half, win)
    return res
print('TRADE one/candle, per$1 after fee (n, hit, per$1, H1|H2):')
for mg in (0.0,0.05,0.10,0.15):
    line=f'  margin {mg:.2f}: '
    for name,p in (('logit',P['logit']),('gbm',P['gbm']),('venue',pv),('v10',pv10)):
        r=trade(p,mg); n=len(r)
        if n==0: line+=f'{name} none | '; continue
        v=list(r.values()); f=lambda z: np.mean(z) if len(z) else float('nan')
        line+=f'{name} n={n} hit={100*np.mean([t[2] for t in v]):.0f}% {f([t[0] for t in v]):+.3f} ({f([t[0] for t in v if t[1]]):+.2f}|{f([t[0] for t in v if not t[1]]):+.2f}){"*" if n<60 else ""} | '
    print(line)
# permutation null for gbm at margin 0.10
rng=np.random.default_rng(1); base=trade(P['gbm'],0.10); bv=np.mean([t[0] for t in base.values()]) if base else float('nan'); null=[]
for _ in range(30):
    ps=P['gbm'].copy()
    for lo,hi in ((15,60),(60,150),(150,241)):
        idx=np.where(m&(sec>=lo)&(sec<hi))[0]; ps[idx]=rng.permutation(ps[idx])
    r=trade(ps,0.10); null.append(np.mean([t[0] for t in r.values()]) if r else 0)
print(f'permutation null gbm@0.10: real {bv:+.3f} vs null median {np.median(null):+.3f} p95 {np.percentile(null,95):+.3f}')
if a.out:
    import pickle; pickle.dump(dict(feats=FEATS,rows=len(rows)),open(a.out,'wb'))
