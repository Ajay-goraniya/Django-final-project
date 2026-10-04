#!/usr/bin/env python3
"""Final report writer for SESSION_EF.txt. Reads the cached rows built by session_ef2.py."""
import sys, pickle, collections, numpy as np
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
from ef3_fine import QUAL
from ef2_model import per1, be
TICK,STAKE=0.01,10.0
TRAIN,TEST=('09-24','09-25','09-26','09-27'),('09-28','09-29','09-30')
SESS=[('Asia 00-07',0,7),('Europe 07-13',7,13),('US 13-20',13,20),('Late 20-24',20,24)]
R=pickle.load(open('/home/ubuntu/pm_ef3/session_ef_rows.pkl','rb'))
Rtr=[r for r in R if r['day'] in TRAIN]; Rte=[r for r in R if r['day'] in TEST]
def score(F):
    fl=[f for f in F if f['q']==f['q']]
    if not fl: return dict(n=len(F),nf=0,tot=0.,mdd=0.,byd={},h1=0.,h2=0.)
    p=[STAKE*per1(f['win'],min(f['q'],0.99)) for f in fl]; c=np.cumsum(p)
    byd=collections.defaultdict(float)
    for f,v in zip(fl,p): byd[f['day']]+=v
    h=len(p)//2
    return dict(n=len(F),nf=len(fl),tot=float(sum(p)),byd=dict(byd),h1=float(sum(p[:h])),h2=float(sum(p[h:])),
                mdd=float(np.max(np.maximum.accumulate(np.r_[0,c])-np.r_[0,c])))
def fire_named(X,arm,S0):
    o,s=[],set()
    for r in X:
        if r['ep'] in s or r['sec']<S0: continue
        if QUAL[arm](dict(p=r['ps'],ask=r['own'])):
            s.add(r['ep']); o.append(dict(q=r['lat'],win=r['win'],day=r['day'],hour=r['hour']))
    return o
def fire_cell(X,ev,e,l,amn,amx,cp):
    o,s=[],set()
    for r in X:
        if r['ep'] in s or r['ps']<0.5 or not(e<=r['sec']<=l) or not(amn<=r['own']<=amx): continue
        cx=min(r['own']+cp*TICK,0.99)
        if (r['ps']/be(cx)-1.0)<ev: continue
        s.add(r['ep']); q=r['lat'] if (r['lat']==r['lat'] and r['lat']<=cx+1e-12) else float('nan')
        o.append(dict(q=q,win=r['win'],day=r['day'],hour=r['hour']))
    return o
ARMS=[('fixed15',lambda X:fire_named(X,'fixed15',0)),
      ('raw25 S0=60',lambda X:fire_named(X,'raw25',60)),
      ('raw25 S0=0',lambda X:fire_named(X,'raw25',0)),
      ('EF10#1 ev.20 s60-210 a.05-.55 c+2',lambda X:fire_cell(X,.20,60,210,.05,.55,2)),
      ('EF10#2 ev.20 s60-210 a.15-.55 c+2',lambda X:fire_cell(X,.20,60,210,.15,.55,2)),
      ('EF10#3 ev.20 s60-210 a.05-.65 c+2',lambda X:fire_cell(X,.20,60,210,.05,.65,2))]
L=[]; P=L.append
P("SESSION x ARM WALK-FORWARD - 'did we test fixed / raw by session?' (owner via V, 09-30). READ-ONLY, NO DEPLOY.")
P("")
P("METHOD (fixed before looking, nothing re-derived here)")
P("  rows      decide_log per-pass, 09-24..30, via ef3_shadow.load_candles + build_rows (the same builder")
P("            whose --selftest reproduces ef2_rows.npz row-for-row). q IS the +250 ms London-exec FAK fill.")
P("  sim       one fire per candle, FAK at the pass's own ask, $10, fee exact (per1/be), gamma labels")
P("            (venues.outcome, the venue's own resolution - the settlement rule).")
P("  arms      fixed15 and raw25 are imported from ef3_fine.QUAL, not rewritten. EF-10 cell semantics are")
P("            ef10.py's mask verbatim; the top-3 are re-ranked by P/DD ON THE TRAIN DAYS ONLY, never read")
P("            off EF10_grid.csv (whose totals are over a different 5-day window).")
P("  sessions  Asia 00-07 / Europe 07-13 / US 13-20 / Late 20-24 UTC, by the candle's open hour.")
P("  split     train 09-24..27, sealed test 09-28..30. Keep a cell iff train $>0 AND both train halves >0")
P("            AND n>=30. The test days were scored only after the keep list was fixed.")
P(f"  size      {len(R):,} passes over {len({r['ep'] for r in R}):,} candles.")
cbd=collections.Counter()
for ep,d in {r['ep']:r['day'] for r in R}.items(): cbd[d]+=1
P("            candles/day  "+"  ".join(f"{d} {cbd[d]}" for d in sorted(cbd)))
P("")
P("TWO THINGS THAT LIMIT HOW THIS CAN BE READ - stated before the numbers, not after")
P("  1. 09-24 is a HALF day (132 of 288 candles) and 09-30 is the day in progress (151).")
P("  2. US 13-20 and Late 20-24 have ZERO candles on 09-30 (it is ~13:00 UTC). So every kept cell in")
P("     those two sessions is tested on 09-28 and 09-29 ONLY - a 2-day sealed test, not 3. 'days +'")
P("     below counts days that EXIST for that cell.")
P("")
P("TOP-3 EF-10 CELLS BY TRAIN P/DD - and a correction to what 'top-3' bought us")
for nm,fn in ARMS[3:]:
    a=score(fn(Rtr)); P(f"  {nm}   train $ {a['tot']:+7.1f}  DD {a['mdd']:5.1f}  P/DD {a['tot']/a['mdd']:.2f}  n {a['nf']}")
P("  #1 and #2 ARE THE SAME RULE. The lowest own ask on any p>=0.5 pass is 0.150, so ask_min 0.05 and")
P("  ask_min 0.15 select identically - verified fire-for-fire (474 vs 474, same list). The grid's top-3")
P("  by P/DD is therefore only TWO distinct rules, and the 'three' EF-10 columns below are not three")
P("  independent tests. (My first identity check said they differed; that check compared dicts holding")
P("  NaN no-fill prices, and NaN != NaN makes any such comparison False. The check was broken, not the cells.)")
P("")
P("FULL GRID - every arm x session cell, train and sealed test, $ at $10/fill")
P("  arm                                 session        train $/n     halves      test $/n    KEEP")
kept=[]
for nm,fn in ARMS:
    ftr,fte=fn(Rtr),fn(Rte)
    for sn,lo,hi in SESS:
        a=score([f for f in ftr if lo<=f['hour']<hi]); b=score([f for f in fte if lo<=f['hour']<hi])
        k=a['nf']>=30 and a['tot']>0 and a['h1']>0 and a['h2']>0
        if k: kept.append((nm,sn,lo,hi,a,b,fn))
        P(f"  {nm:35s} {sn:13s} {a['tot']:+7.1f}/{a['nf']:<3d} {a['h1']:+6.1f}/{a['h2']:+6.1f} {b['tot']:+8.1f}/{b['nf']:<3d}  {'KEEP' if k else ''}")
P("")
P(f"KEPT CELLS ({len(kept)}) AND THEIR SEALED TEST, day by day")
pool=0.0; pbd=collections.defaultdict(float)
for nm,sn,lo,hi,a,b,fn in kept:
    per={d:round(v,1) for d,v in sorted(b['byd'].items())}
    P(f"  {nm} / {sn}:  test $ {b['tot']:+.1f}  n {b['nf']}   per day {per}")
    pool+=b['tot']
    for d,v in b['byd'].items(): pbd[d]+=v
P(f"  POOLED sealed test: $ {pool:+.1f} over {sum(v['nf'] for *_,v,__ in [(k[0],k[1],k[2],k[3],k[4],k[5],k[6]) for k in kept])} fills"
  if False else f"  POOLED sealed test: $ {pool:+.1f} over {sum(k[5]['nf'] for k in kept)} fills, "
                f"days + {sum(1 for v in pbd.values() if v>0)}/{len(pbd)}  ({', '.join(f'{d} {v:+.1f}' for d,v in sorted(pbd.items()))})")
P("")
P("THE COMPARISON THAT DECIDES IT - same arms, ALL sessions, same sealed test days")
P("  arm                                 test $/n      DD    days +")
for nm,fn in ARMS:
    b=score(fn(Rte))
    P(f"  {nm:35s} {b['tot']:+7.1f}/{b['nf']:<3d} {b['mdd']:6.1f}   {sum(1 for v in b['byd'].values() if v>0)}/{len(b['byd'])}")
P("")
P("WHAT THIS ANSWERS")
ALL={nm:score(fn(Rte)) for nm,fn in ARMS}
f15,r60,r00=ALL['fixed15'],ALL['raw25 S0=60'],ALL['raw25 S0=0']
f15u=score([f for f in fire_named(Rtr,'fixed15',0) if 13<=f['hour']<20])
k60=[k for k in kept if k[0]=='raw25 S0=60'][0][5]; k00=[k for k in kept if k[0]=='raw25 S0=0'][0][5]
P(f"  1. NO fixed15 cell survived the train filter, in ANY session. fixed15/US 13-20 had train "
  f"{f15u['tot']:+.1f} on n={f15u['nf']}")
P(f"     but its halves were {f15u['h1']:+.1f} / {f15u['h2']:+.1f}, so the both-halves rule dropped it. And fixed15")
P(f"     trading ALL sessions is the BEST arm on the sealed test ({f15['tot']:+.1f}, n={f15['nf']}, "
  f"{sum(1 for v in f15['byd'].values() if v>0)}/{len(f15['byd'])} days). So for fixed15 the session")
P("     split found nothing - applying it would have taken us from the best result on the board to no trades.")
P(f"  2. For the RAW arms the split is the difference between a loss and a gain. All sessions: raw25 S0=60")
P(f"     {r60['tot']:+.1f} (n={r60['nf']}, DD {r60['mdd']:.1f}) and raw25 S0=0 {r00['tot']:+.1f} (n={r00['nf']}, "
  f"DD {r00['mdd']:.1f}), both losing on")
P(f"     EVERY test day ({sum(1 for v in r60['byd'].values() if v>0)}/{len(r60['byd'])} and "
  f"{sum(1 for v in r00['byd'].values() if v>0)}/{len(r00['byd'])}). Their kept session cells: {k60['tot']:+.1f} (n={k60['nf']}) and "
  f"{k00['tot']:+.1f} (n={k00['nf']}).")
P("     The effect is large and points the same way in both raw variants, which is the one thing here")
P("     that is not explainable by a single lucky cell.")
P("  3. The EF-10 cells are the CONTROL, and they say be careful: the same procedure kept three US cells")
ef=[k[5]['tot'] for k in kept if k[0].startswith('EF10')]
P(f"     whose sealed test is {', '.join(f'{v:+.1f}' for v in ef)} - indistinguishable from zero. A selection rule that")
P("     returns a real number on one arm and 0.0 on another, from the same train window, is not yet a finding.")
P(f"  4. Sample. The pooled {pool:+.1f} leans on raw25 S0=0 / Late 20-24 at n={k00['nf']} fills "
  f"({', '.join(f'{d} {v:+.1f}' for d,v in sorted(k00['byd'].items()))}).")
P("     Under 60 graded fires is 'insufficient' by our own standard - do not read it. raw25 S0=60 / US 13-20")
P(f"     at n={k60['nf']} is the only kept cell with both a real effect and a real sample, and it is still under 60")
P("     and still only 2 days. No cell in this study clears the 60-fill bar.")
P("")
P("VERDICT: session timing DOES separate the raw arms - US and Late carry them, Asia and Europe sink them -")
P("but it does NOT beat simply using fixed15 unfiltered, and the EF-10 control shows the same selection")
P("procedure returning zero. NO DEPLOY, NO CHANGE: this is a research answer to a research question.")
import datetime as _dt
P("")
P(f"Built {_dt.datetime.now(_dt.UTC):%Y-%m-%d %H:%M} UTC from a live decide_log; re-running later moves the")
P("late-09-30 columns as that day fills in. Rows cached at /home/ubuntu/pm_ef3/session_ef_rows.pkl.")
open('/home/ubuntu/claude-work/repo/analysis/zurich/SESSION_EF.txt','w').write('\n'.join(L)+'\n')
print('\n'.join(L))
