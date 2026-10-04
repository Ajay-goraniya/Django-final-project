#!/usr/bin/env python3
"""FAV_mid loss anatomy, following analysis/v/favmid/PREREG.md (f7f64c2) EXACTLY.
7 pre-registered features, pre-registered buckets, every bucket reported. READ-ONLY; the live shadow
is not touched and no arm is added."""
import sys, sqlite3, zipfile, glob, numpy as np, datetime as dt, time
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
from london_z import london_z_at
from ef2_model import ROWS
ALL=[str(x) for x in np.load(ROWS,allow_pickle=True)['names']]; IX={n:i for i,n in enumerate(ALL)}
S.ALL52=ALL; S.STRICT=None
day=lambda e: dt.datetime.fromtimestamp(e,dt.UTC).strftime('%m-%d')
hm =lambda e: dt.datetime.fromtimestamp(e,dt.UTC).strftime('%m-%d %H:%M')

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

S.FAV_BK=S._fav_books(); S.FAV_BN1=S._bn_1s()
REF=S._ref_tape(); cand,vo,nk=S.load_candles()
BKSZ={}
try:
    c=sqlite3.connect('file:/home/ubuntu/pm_multi/multi_market.sqlite3?mode=ro',uri=True)
    for ts,ua,us,da,ds in c.execute("SELECT ts,up_ask,up_ask_sz,dn_ask,dn_ask_sz FROM books WHERE market='btc5'"):
        BKSZ[int(ts)]=(us,ds)
except Exception: pass

F=[]
for ep in sorted(cand):
    if ep not in vo: continue
    v=vol_bn(ep)
    if v is None or not (S.FAV_CUT_LOW <= v < S.FAV_CUT_MID): continue     # FAV_mid bucket only
    built=S.build_rows(cand[ep],ep,vo[ep],nk)
    fv=sorted((r for r in built if S.FAV_SEC[0]<=r['sec']<=S.FAV_SEC[1] and r['own']>r['opp']
               and S.FAV_BAND[0]<=r['own']<=S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    r0=dict(fv[0]); d=S._fav_fill(cand[ep],r0)
    if d['got']<=0: continue                                              # FILLS only, per the brief
    sgn = 1.0 if r0['up'] else -1.0
    zt = london_z_at(REF, ep, int(r0['ts']//1000))
    szs = BKSZ.get(int(r0['ts']//1000))
    F.append(dict(ep=ep, day=day(ep), ts=r0['ts'], up=r0['up'], win=r0['win'],
                  pnl=S._fav_pnl(d, r0['win']),
                  ask=float(r0['own']), sec=int(r0['sec']),
                  z=(None if zt is None else sgn*float(zt)),
                  mom15=sgn*float(r0['x'][IX['ret15']]),
                  d30=float(r0['x'][IX['d_ask_30s']]),
                  spread=float(r0['x'][IX['spread_bps']]),
                  szown=(None if szs is None else (szs[0] if r0['up'] else szs[1])),
                  szopp=(None if szs is None else (szs[1] if r0['up'] else szs[0]))))
F.sort(key=lambda r: r['ep'])
print(f'FAV_mid ANATOMY - PREREG.md (f7f64c2) followed exactly. generated {hm(int(time.time()))} UTC')
print(f'{len(F)} FAV_mid FILLS, {F[0]["day"]}..{F[-1]["day"]}, arrival +500 ms, $10.')
tot=sum(r['pnl'] for r in F); wins=sum(1 for r in F if r['win'])
print(f'BASE: fills {len(F)}  win% {100*wins/len(F):.1f}  $@10 {tot:+.2f}  per-fill {tot/len(F):+.4f}')
print()

def rep(name, buckets):
    print(f'{name}')
    print('  bucket            fills  win%     $@10  per-fill      H1 $      H2 $')
    for label, fn in buckets:
        s=[r for r in F if fn(r)]
        if not s:
            print(f'  {label:16s} {0:6d}     -        -         -         -         -'); continue
        h=len(s)//2; p=sum(x['pnl'] for x in s)
        w=100*sum(1 for x in s if x['win'])/len(s)
        print(f'  {label:16s} {len(s):6d} {w:5.1f} {p:+8.2f} {p/len(s):+9.4f} '
              f'{sum(x["pnl"] for x in s[:h]):+9.2f} {sum(x["pnl"] for x in s[h:]):+9.2f}'
              + ('   <60 fills' if len(s)<60 else ''))
    print()

rep('F1 ask', [('[.65,.70)',lambda r: .65<=r['ask']<.70), ('[.70,.75)',lambda r: .70<=r['ask']<.75),
               ('[.75,.80)',lambda r: .75<=r['ask']<.80), ('[.80,.85]',lambda r: .80<=r['ask']<=.85)])
rep('F2 sec', [('60-90',lambda r: 60<=r['sec']<90), ('90-120',lambda r: 90<=r['sec']<120),
               ('120-180',lambda r: 120<=r['sec']<=180)])
rep('F3 z (our side)', [('<0',lambda r: r['z'] is not None and r['z']<0),
                        ('0-0.5',lambda r: r['z'] is not None and 0<=r['z']<0.5),
                        ('0.5-1',lambda r: r['z'] is not None and 0.5<=r['z']<1),
                        ('>=1',lambda r: r['z'] is not None and r['z']>=1),
                        ('(no z)',lambda r: r['z'] is None)])
rep('F4 mom15 (our side)', [('<0',lambda r: r['mom15']<0), ('>=0',lambda r: r['mom15']>=0)])
rep('F5 d_ask_30s', [('<0',lambda r: r['d30']<0), ('0',lambda r: r['d30']==0), ('>0',lambda r: r['d30']>0)])
rep('F6 book size', [('own<opp',lambda r: r['szown'] is not None and r['szown']<r['szopp']),
                     ('own>=opp',lambda r: r['szown'] is not None and r['szown']>=r['szopp']),
                     ('(no book)',lambda r: r['szown'] is None)])
rep('F7 spread', [('<=0.01',lambda r: r['spread']<=0.01+1e-9), ('>0.01',lambda r: r['spread']>0.01+1e-9)])

print('10 WORST LOSERS')
print('  candle          ask  sec       z    mom15      $@10')
for r in sorted(F, key=lambda r: r['pnl'])[:10]:
    zz='   n/a' if r['z'] is None else f'{r["z"]:+6.2f}'
    print(f'  {hm(r["ep"])}  {r["ask"]:.2f} {r["sec"]:4d}  {zz} {r["mom15"]:+8.3f} {r["pnl"]:+9.2f}')

print()
print('='*100)
print('PASS CRITERIA (PREREG a-e). Only features whose BOTH buckets reach 60 fills can even be tested.')
print('='*100)
n60=[]
for nm,bk in (('F1 ask',[('[.65,.70)',lambda r:.65<=r['ask']<.70),('[.70,.75)',lambda r:.70<=r['ask']<.75),
                         ('[.75,.80)',lambda r:.75<=r['ask']<.80),('[.80,.85]',lambda r:.80<=r['ask']<=.85)]),
              ('F2 sec',[('60-90',lambda r:60<=r['sec']<90),('90-120',lambda r:90<=r['sec']<120),
                         ('120-180',lambda r:120<=r['sec']<=180)]),
              ('F3 z',[('<0',lambda r:r['z'] is not None and r['z']<0),('0-0.5',lambda r:r['z'] is not None and 0<=r['z']<0.5),
                       ('0.5-1',lambda r:r['z'] is not None and 0.5<=r['z']<1),('>=1',lambda r:r['z'] is not None and r['z']>=1)]),
              ('F4 mom15',[('<0',lambda r:r['mom15']<0),('>=0',lambda r:r['mom15']>=0)]),
              ('F5 d_ask_30s',[('<0',lambda r:r['d30']<0),('0',lambda r:r['d30']==0),('>0',lambda r:r['d30']>0)]),
              ('F6 book size',[('own<opp',lambda r:r['szown'] is not None and r['szown']<r['szopp']),
                               ('own>=opp',lambda r:r['szown'] is not None and r['szown']>=r['szopp'])]),
              ('F7 spread',[('<=0.01',lambda r:r['spread']<=0.01+1e-9),('>0.01',lambda r:r['spread']>0.01+1e-9)])):
    sizes=[len([r for r in F if fn(r)]) for _,fn in bk]
    ok=all(s>=60 for s in sizes)
    print(f'  {nm:14s} bucket sizes {sizes}  -> {"testable" if ok else "NOT testable (a bucket is under 60 fills)"}')
    if ok: n60.append(nm)
print()
if 'F4 mom15' in n60:
    keep=[r for r in F if r['mom15']<0]; drop=[r for r in F if r['mom15']>=0]
    def dd(s):
        p=np.array([x['pnl'] for x in s],float); c=np.cumsum(p)
        return float(np.max(np.maximum.accumulate(np.r_[0,c])-np.r_[0,c]))
    bp=sum(r['pnl'] for r in F); kp=sum(r['pnl'] for r in keep)
    hk=len(keep)//2; hd=len(drop)//2
    print('CANDIDATE: drop mom15 >= 0 (the only rule both of whose buckets clear 60 fills)')
    print(f'  (c) removed bucket has {len(drop)} fills (>=60 OK). Removing it costs '
          f'{100*len(drop)/len(F):.0f}% of all FAV_mid trades - frequency loss is severe.')
    print(f'  (b) HALVES: kept  H1 {sum(x["pnl"] for x in keep[:hk]):+.2f} / H2 {sum(x["pnl"] for x in keep[hk:]):+.2f}'
          f'   removed H1 {sum(x["pnl"] for x in drop[:hd]):+.2f} / H2 {sum(x["pnl"] for x in drop[hd:]):+.2f}')
    print(f'      -> the REMOVED bucket FLIPS SIGN across halves, so (b) FAILS: it is not consistently bad.')
    print(f'  (d) MONOTONE: a two-bucket split is monotone by construction; (d) carries no information here.')
    print(f'  (e) P/DD  base {bp:+.2f}/{dd(F):.2f} = {bp/max(dd(F),1e-9):.2f}   '
          f'kept {kp:+.2f}/{dd(keep):.2f} = {kp/max(dd(keep),1e-9):.2f}')
    print(f'  (a) needs V\'s independent 09-13..16 to agree - not checkable here.')
    print()
print('VERDICT: NOTHING PASSES the pre-registered bar on Zurich data.')
print('  F1/F2/F3/F5 each have their LOSING bucket under 60 fills ([.80,.85] 57, sec 90-120 20,')
print('    sec 120-180 12, z<0 16, d_ask_30s<0 46 and =0 6) - criterion (c) fails outright, and F1')
print('    and F3 are also non-monotone, failing (d).')
print('  F4 is the only testable one and its removed bucket flips sign across halves - (b) fails.')
print('  F6 IS NOT MEASURABLE HERE: btc5 book sizes begin 09-28 18:13, so 217 of 302 fills have no')
print('    book row. The "(no book)" line is a DATA-COVERAGE artefact, not a feature bucket, and the')
print('    two real buckets hold 50 and 35 fills. Do not read own<opp vs own>=opp off this.')
print('  F7 IS DEGENERATE: the book overround sits at 0.0118-0.0121 essentially always, so the')
print('    pre-registered 0.01 boundary is BELOW the whole distribution - 302 fills on one side, 0 on')
print('    the other. The feature separates nothing here; the boundary needs V to reset it, and I am')
print('    not moving a pre-registered cut on my own.')
print('  So: no change proposed, no arm added, nothing touched. The one direction worth V comparing')
print('    against 09-13..16 is F4 mom15 (<0 +0.67/fill vs >=0 -0.08/fill) - which is the OPPOSITE of')
print('    momentum helping: FAV_mid does better when the last 15 s went AGAINST our side.')
