#!/usr/bin/env python3
"""Pass 2: cache the rows once, then answer the three open questions + emit the report body."""
import sys, os, pickle, collections, itertools, numpy as np, datetime as dt
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef3_fine import QUAL
from ef2_model import per1, be
TICK, STAKE = 0.01, 10.0
TRAIN, TEST = ('09-24','09-25','09-26','09-27'), ('09-28','09-29','09-30')
SESS = [('Asia 00-07',0,7), ('Europe 07-13',7,13), ('US 13-20',13,20), ('Late 20-24',20,24)]
CACHE = '/home/ubuntu/pm_ef3/session_ef_rows.pkl'

if os.path.exists(CACHE):
    R = pickle.load(open(CACHE,'rb'))
else:
    import ef3_shadow as S
    S.ALL52, S.STRICT = None, None
    cand, vo, nk = S.load_candles(); R = []
    for ep in sorted(cand):
        if ep not in vo: continue
        d = dt.datetime.fromtimestamp(ep, dt.UTC); day = d.strftime('%m-%d')
        if day not in TRAIN+TEST: continue
        for r in S.build_rows(cand[ep], ep, vo[ep], nk):
            R.append(dict(ep=ep, ts=r['ts'], own=r['own'], lat=r['q'], ps=r['pe'],
                          sec=r['sec'], win=r['win'], day=day, hour=d.hour))
    R.sort(key=lambda r:(r['ep'],r['ts'])); pickle.dump(R, open(CACHE,'wb'))

def score(F):
    fl=[f for f in F if f['q']==f['q']]
    if not fl: return dict(n=len(F),nf=0,tot=0.0,mdd=0.0,byd={},h1=0.0,h2=0.0)
    p=[STAKE*per1(f['win'],min(f['q'],0.99)) for f in fl]
    c=np.cumsum(p); byd=collections.defaultdict(float)
    for f,v in zip(fl,p): byd[f['day']]+=v
    h=len(p)//2
    return dict(n=len(F),nf=len(fl),tot=float(sum(p)),
                mdd=float(np.max(np.maximum.accumulate(np.r_[0,c])-np.r_[0,c])),
                byd=dict(byd),h1=float(sum(p[:h])),h2=float(sum(p[h:])))

def fire_named(Rx,arm,S0):
    out,seen=[],set()
    for r in Rx:
        if r['ep'] in seen or r['sec']<S0: continue
        if QUAL[arm](dict(p=r['ps'],ask=r['own'])):
            seen.add(r['ep']); out.append(dict(q=r['lat'],win=r['win'],day=r['day'],hour=r['hour']))
    return out

def fire_cell(Rx,evb,e,l,amn,amx,cp):
    out,seen=[],set()
    for r in Rx:
        if r['ep'] in seen: continue
        if r['ps']<0.5 or not (e<=r['sec']<=l) or not (amn<=r['own']<=amx): continue
        capx=min(r['own']+cp*TICK,0.99)
        if (r['ps']/be(capx)-1.0)<evb: continue
        seen.add(r['ep'])
        q=r['lat'] if (r['lat']==r['lat'] and r['lat']<=capx+1e-12) else float('nan')
        out.append(dict(q=q,win=r['win'],day=r['day'],hour=r['hour']))
    return out

Rtr=[r for r in R if r['day'] in TRAIN]; Rte=[r for r in R if r['day'] in TEST]
byday=collections.Counter(r['day'] for r in R)
cbd=collections.Counter()
for ep,d in {r['ep']:r['day'] for r in R}.items(): cbd[d]+=1
print('== COVERAGE')
print(f'rows {len(R):,}  candles {sum(cbd.values()):,}')
for d in sorted(cbd): print(f'   {d}: {cbd[d]:4d} candles, {byday[d]:7,d} passes')
print('\n== Q: are the top-3 EF-10 cells really distinct rules?')
n0515=sum(1 for r in R if 0.05<=r['own']<0.15 and r['ps']>=0.5)
print(f'   rows with p>=0.5 and own ask in [0.05,0.15): {n0515}  -> ask_min 0.05 vs 0.15 cannot differ if 0')
for a,b in (((0.20,60,210,0.05,0.55,2),(0.20,60,210,0.15,0.55,2)),
            ((0.20,60,210,0.05,0.55,2),(0.20,60,210,0.05,0.65,2))):
    fa,fb=fire_cell(R,*a),fire_cell(R,*b)
    print(f'   {a[3]}-{a[4]} vs {b[3]}-{b[4]}: n {len(fa)} vs {len(fb)}, identical={fa==fb}')

# ---- NaN-safe identity: dict == dict is False whenever q is NaN, so the first check was broken ----
def key(F): return [(round(f['q'],9) if f['q']==f['q'] else 'NF', f['win'], f['day'], f['hour']) for f in F]
print('\n== Q (corrected, NaN-safe): are the top-3 cells distinct?')
A,B,Cc = fire_cell(R,0.20,60,210,0.05,0.55,2), fire_cell(R,0.20,60,210,0.15,0.55,2), fire_cell(R,0.20,60,210,0.05,0.65,2)
print(f'   #1 vs #2: n {len(A)}/{len(B)}  same_fires={key(A)==key(B)}')
print(f'   #1 vs #3: n {len(A)}/{len(Cc)} same_fires={key(A)==key(Cc)}')
print(f'   min own ask among p>=0.5 rows: {min(r["own"] for r in R if r["ps"]>=0.5):.3f}')

ARMS=[('fixed15',lambda X:fire_named(X,'fixed15',0)),
      ('raw25 S0=60',lambda X:fire_named(X,'raw25',60)),
      ('raw25 S0=0',lambda X:fire_named(X,'raw25',0)),
      ('EF10#1 ev0.2 60-210 0.05-0.55 c2',lambda X:fire_cell(X,0.20,60,210,0.05,0.55,2)),
      ('EF10#2 ev0.2 60-210 0.15-0.55 c2',lambda X:fire_cell(X,0.20,60,210,0.15,0.55,2)),
      ('EF10#3 ev0.2 60-210 0.05-0.65 c2',lambda X:fire_cell(X,0.20,60,210,0.05,0.65,2))]
print('\n== KEPT CELLS, per TEST DAY (this is what "days +" is counted on)')
kept=[]
for nm,fn in ARMS:
    ftr,fte=fn(Rtr),fn(Rte)
    for sn,lo,hi in SESS:
        a=score([f for f in ftr if lo<=f['hour']<hi]); b=score([f for f in fte if lo<=f['hour']<hi])
        if a['nf']>=30 and a['tot']>0 and a['h1']>0 and a['h2']>0:
            kept.append((nm,sn,lo,hi,a,b))
            pd_={d:(round(v,1),sum(1 for f in fn(Rte) if lo<=f['hour']<hi and f['day']==d and f['q']==f['q'])) for d,v in sorted(b['byd'].items())}
            print(f'   {nm} / {sn}: test {b["tot"]:+.1f} n {b["nf"]}  per-day {pd_}')
print('\n== how many candles exist per session per TEST day (is a zero a loss or an absence?)')
cb={}
for r in Rte: cb.setdefault((r['day'],r['hour']//1),set()).add(r['ep'])
for sn,lo,hi in SESS:
    row=' '.join(f'{d}:{sum(len(v) for (dd,h),v in cb.items() if dd==d and lo<=h<hi)}' for d in ('09-28','09-29','09-30'))
    print(f'   {sn:13s} {row}')
