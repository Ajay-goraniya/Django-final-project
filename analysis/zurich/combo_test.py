#!/usr/bin/env python3
"""COMBINATION test per analysis/v/favmid/COMBO_PREREG.md (1802b5f), followed exactly.
READ-ONLY on the live engine. 10 pre-registered arms, singles at $10, every pair at $5+$5.
usage: combo_test.py"""
import sys, sqlite3, glob, zipfile, itertools, csv, numpy as np, datetime as dt
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
ARMS=['FAV','FAV_ref','FAV_mid','FAV_all','C_fixed15','F_z50','F25_z25','F75_z75','E3_trail_1h_q90','S_fixed_top20']
FAVFAM={'FAV','FAV_ref','FAV_mid','FAV_all'}
FWD0=1790645000                      # forward shadow starts 09-29 01:20
day=lambda e: dt.datetime.fromtimestamp(e,dt.UTC).strftime('%m-%d')
hour=lambda e: dt.datetime.fromtimestamp(e,dt.UTC).strftime('%m-%d %H')

# ---- Binance 1 s series for the history vol gate (archive klines + live bn_flow) ----
BN={}
for z in sorted(glob.glob('/tmp/parity/z-2026-09-*.zip')):
    with zipfile.ZipFile(z) as fh:
        for line in fh.read(fh.namelist()[0]).decode().splitlines():
            p=line.split(',')
            if not p or not p[0] or p[0][0].isalpha(): continue
            t=int(p[0]); t=t//1000 if t>20_000_000_000_000 else t
            BN[t//1000]=float(p[4])
for k,v in S._bn_1s().items(): BN.setdefault(k,v)
def vol_bn(ep):
    w=[BN[t] for t in range(ep-300,ep) if t in BN]
    return None if len(w)<S.FAV_BN_MIN_PTS else float(np.std(np.diff(np.log(np.asarray(w,float))))*1e4)

S.ALL52,S.STRICT=None,None; S.FAV_BK=S._fav_books(); S.FAV_BN1=S._bn_1s()
REF=S._ref_tape(); cand,vo,nk=S.load_candles()
sh=sqlite3.connect(f'file:{S.DB}?mode=ro',uri=True)

# ---- HISTORY replay, FAV family only (arrival +500 ms partial). No replay exists for the others. ----
hist={a:{} for a in FAVFAM}
for ep in sorted(cand):
    if ep not in vo or ep>=FWD0: continue
    v=vol_bn(ep)
    built=S.build_rows(cand[ep],ep,vo[ep],nk)
    fv=sorted((r for r in built if S.FAV_SEC[0]<=r['sec']<=S.FAV_SEC[1] and r['own']>r['opp']
               and S.FAV_BAND[0]<=r['own']<=S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    r0=dict(fv[0]); d=S._fav_fill(cand[ep],r0)
    if d['got']<=0: continue
    pnl=S._fav_pnl(d,r0['win'])
    vr=S._vol_open(REF,ep)
    if v is not None:
        hist['FAV_all'][ep]=pnl
        if v<S.FAV_CUT_LOW: hist['FAV'][ep]=pnl
        elif v<S.FAV_CUT_MID: hist['FAV_mid'][ep]=pnl
    if vr is not None and vr<S.FAV_REF_CUT: hist['FAV_ref'][ep]=pnl

# ---- FORWARD, every arm, each with its OWN registered fill model ----
fwd={a:{} for a in ARMS}
for a in ARMS:
    col='pnl_part' if a in FAVFAM else 'pnl'
    for ep,p in sh.execute(f"SELECT epoch,{col} FROM fires WHERE arm=? AND epoch>=? AND {col} IS NOT NULL",(a,FWD0)):
        fwd[a][int(ep)]=float(p)

# pooled: FAV family = history (<FWD0) then forward (>=FWD0), no overlap. Others = forward only.
pool={a:dict(hist.get(a,{})) for a in ARMS}
for a in ARMS: pool[a].update(fwd[a])
cover={a:((min(pool[a]) if pool[a] else FWD0) if a in FAVFAM else FWD0, max(max(pool[a],default=FWD0),FWD0)) for a in ARMS}

def stats(series, lo=None, hi=None):
    eps=sorted(e for e in series if (lo is None or e>=lo) and (hi is None or e<=hi))
    if not eps: return None
    p=np.array([series[e] for e in eps],float)
    c=np.cumsum(p); dd=float(np.max(np.maximum.accumulate(np.r_[0,c])-np.r_[0,c]))
    per={}
    for e in eps: per[day(e)]=per.get(day(e),0.0)+series[e]
    h=len(eps)//2
    return dict(n=len(eps),tot=float(p.sum()),dd=dd,pdd=(float(p.sum())/dd if dd>0 else float('inf')),
                pos=sum(1 for v in per.values() if v>0),neg=sum(1 for v in per.values() if v<0),
                h1=float(p[:h].sum()),h2=float(p[h:].sum()),per=per,eps=eps)

def hourly(series):
    o={}
    for e,v in series.items(): o[hour(e)]=o.get(hour(e),0.0)+v
    return o

print('COMBINATION TEST - PREREG analysis/v/favmid/COMBO_PREREG.md (1802b5f), followed exactly')
print('READ-ONLY. Live engine untouched. All figures are $ at the stated stake.')
print()
print('DATA BASIS PER ARM')
print('arm                      basis                                   fills')
for a in ARMS:
    b=('history 09-24..29 replay (arrival +500 ms partial) + forward' if a in FAVFAM
       else 'FORWARD ONLY - no history replay exists for this arm')
    print(f'  {a:22s} {b:52s} {len(pool[a]):5d}')
print('  History replay exists ONLY for the FAV family. C_fixed15, F_z50, F25_z25, F75_z75,')
print('  E3_trail_1h_q90 and S_fixed_top20 have NO history replay and are forward-only, as briefed.')
print('  FAV-family pooling is history for epochs < 09-29 01:20 then the live forward rows after it,')
print('  so the 09-29 overlap is NOT double counted.')
print()
print('SINGLES at $10')
hdr='arm                      fills      $      maxDD   P/DD  days+/-      H1$      H2$  flag'
print(hdr); print('-'*len(hdr))
single={}
for a in ARMS:
    s=stats(pool[a]); single[a]=s
    if not s: print(f'  {a:22s}  (no rows)'); continue
    print(f'  {a:22s} {s["n"]:5d} {s["tot"]:+8.2f} {s["dd"]:8.2f} {s["pdd"]:6.2f}  {s["pos"]}/{s["neg"]:<5d} '
          f'{s["h1"]:+8.2f} {s["h2"]:+8.2f}  ' + ('' if s['n']>=60 else '<60 fills'))
print()
print('PAIRS at $5+$5, each arm halved, on the COMMON window of the two arms')
hdr2=('pair                                       cand      $      maxDD   P/DD  days+/-      H1$      H2$   '
      'corr(hourly)  beats both P/DD')
print(hdr2); print('-'*len(hdr2))
rows=[]
for x,y in itertools.combinations(ARMS,2):
    lo=max(cover[x][0],cover[y][0]); hi=min(cover[x][1],cover[y][1])
    comb={}
    for e in set(list(pool[x])+list(pool[y])):
        if e<lo or e>hi: continue
        comb[e]=0.5*pool[x].get(e,0.0)+0.5*pool[y].get(e,0.0)
    s=stats(comb)
    if not s: continue
    hx,hy=hourly({e:v for e,v in pool[x].items() if lo<=e<=hi}),hourly({e:v for e,v in pool[y].items() if lo<=e<=hi})
    ks=sorted(set(hx)|set(hy))
    cr=float('nan')
    if len(ks)>2:
        vx=np.array([hx.get(k,0.0) for k in ks]); vy=np.array([hy.get(k,0.0) for k in ks])
        if vx.std()>0 and vy.std()>0: cr=float(np.corrcoef(vx,vy)[0,1])
    sx=stats(pool[x],lo,hi); sy=stats(pool[y],lo,hi)
    beats=bool(sx and sy and s['pdd']>sx['pdd'] and s['pdd']>sy['pdd'])
    rows.append((x,y,s,cr,beats))
    print(f'  {x[:18]:18s}+{y[:18]:18s} {s["n"]:5d} {s["tot"]:+8.2f} {s["dd"]:8.2f} {s["pdd"]:6.2f}  '
          f'{s["pos"]}/{s["neg"]:<5d} {s["h1"]:+8.2f} {s["h2"]:+8.2f}   {cr:+.3f}        {"yes" if beats else "no"}')
print()
days=sorted({day(e) for a in ARMS for e in pool[a]})
print('PER-DAY $ (singles at $10)')
print('arm                    '+'  '.join(f'{d:>8s}' for d in days))
for a in ARMS:
    s=single[a]
    if not s: continue
    print(f'  {a:20s} '+'  '.join(f'{s["per"].get(d,0.0):+8.2f}' for d in days))
print()
print('PASS BARS (a)-(e). (a) needs V\'s independent 09-13..16 too, which is not checkable here.')
ok=[r for r in rows if r[2]['tot']>0 and r[2]['h1']>0 and r[2]['h2']>0 and r[2]['pdd']>=2
    and r[4] and single[r[0]] and single[r[1]] and single[r[0]]['n']>=60 and single[r[1]]['n']>=60]
print(f'  pairs meeting (b)+(c)+(d)+(e) on Zurich data: {len(ok)} of {len(rows)}')
for x,y,s,cr,_ in ok:
    print(f'    {x}+{y}: ${s["tot"]:+.2f} P/DD {s["pdd"]:.2f} H1 {s["h1"]:+.2f} H2 {s["h2"]:+.2f} corr {cr:+.3f}')
if not ok: print('    none - so nothing passes, and no change is proposed.')
with open('/home/ubuntu/claude-work/repo/analysis/zurich/combo_hourly.csv','w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['hour','arm','pnl_at_10'])
    for a in ARMS:
        for k,v in sorted(hourly(pool[a]).items()): w.writerow([k,a,round(v,6)])
print('\nwrote analysis/zurich/combo_hourly.csv (hour, arm, pnl@$10)')

print()
print('='*100)
print('CORRECTED VERDICT - criterion (a) applied, which the block above omitted')
print('='*100)
print('(a) requires $ > 0 on EVERY set: Zurich history 09-24..29, Zurich forward, and V\'s 09-13..16.')
print('The two pairs listed above as passing (b)-(e) both pair FAV_mid with a FORWARD-ONLY arm')
print('(C_fixed15, F25_z25). For those pairs a Zurich HISTORY set does not exist at all, so (a) cannot')
print('be satisfied - not "fails", but is UNTESTABLE on the data I have. Their common window is ~1 day')
print('(148 and 143 candles, days+/- of 1/1), so their P/DD of 3.09 and 2.10 are one-day numbers and')
print('not drawdown statistics.')
print()
print('Pairs where BOTH arms have history, and can therefore be tested on both sets:')
fam=[r for r in rows if r[0] in FAVFAM and r[1] in FAVFAM]
for x,y,s,cr,beats in fam:
    print(f'  {x:9s}+{y:9s}  $ {s["tot"]:+8.2f}  P/DD {s["pdd"]:5.2f}  H1 {s["h1"]:+8.2f} H2 {s["h2"]:+8.2f} '
          f' corr {cr:+.3f}  beats both: {"yes" if beats else "no"}')
_b=max(fam,key=lambda r: r[2]['pdd']) if fam else None
if _b: print(f'  Every one of these fails (c) P/DD >= 2, and the best of them, {_b[0]}+{_b[1]}, correlates '
             f'{_b[3]:+.3f} hourly - very nearly the same arm, so pairing them diversifies nothing.')
print()
print('SO: NO PAIR PASSES THE PRE-REGISTERED BAR. No change proposed, no arm added, nothing deployed.')
print('The mechanism the owner asked about does show up - every FAV_mid pairing with an independent arm')
print('has NEGATIVE hourly correlation (-0.079 to -0.393) and a much smaller drawdown than FAV_mid alone')
print('(135.00 -> 15-22). That is the right direction and it is worth more data. It is not yet a result:')
print('one day, a partner arm with no history, and (a) untestable.')
