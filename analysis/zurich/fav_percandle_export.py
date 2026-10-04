#!/usr/bin/env python3
"""Export one row per FAV-family decision for V to combine with London's real fixed15 per-candle PnL.
READ-ONLY. Columns: candle_epoch, arm, sec, side, ask, filled_shares, pnl_usd_at10, source."""
import sys, sqlite3, glob, zipfile, csv, numpy as np, datetime as dt
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
FWD0=1790645000                                  # forward shadow starts 09-29 01:20
OUT='/home/ubuntu/claude-work/repo/analysis/zurich/fav_percandle.csv'

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
rows=[]
for ep in sorted(cand):
    if ep not in vo or ep>=FWD0: continue
    built=S.build_rows(cand[ep],ep,vo[ep],nk)
    fv=sorted((r for r in built if S.FAV_SEC[0]<=r['sec']<=S.FAV_SEC[1] and r['own']>r['opp']
               and S.FAV_BAND[0]<=r['own']<=S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    r0=dict(fv[0]); d=S._fav_fill(cand[ep],r0)
    if d['got']<=0: continue
    pnl=S._fav_pnl(d,r0['win']); vb=vol_bn(ep); vr=S._vol_open(REF,ep)
    base=dict(candle_epoch=ep,sec=int(r0['sec']),side=('UP' if r0['up'] else 'DOWN'),
              ask=round(float(r0['own']),4),filled_shares=round(float(d['got']),6),
              pnl_usd_at10=round(pnl,6),source='history')
    if vb is not None:
        rows.append(dict(base,arm='FAV_all'))
        if vb<S.FAV_CUT_LOW: rows.append(dict(base,arm='FAV'))
        elif vb<S.FAV_CUT_MID: rows.append(dict(base,arm='FAV_mid'))
    if vr is not None and vr<S.FAV_REF_CUT: rows.append(dict(base,arm='FAV_ref'))

sh=sqlite3.connect(f'file:{S.DB}?mode=ro',uri=True)
for arm in ('FAV','FAV_ref','FAV_mid','FAV_all'):
    for ep,sec,up,ask,shq,pp in sh.execute(
        "SELECT epoch,sec,up,ask,sh,pnl_part FROM fires WHERE arm=? AND epoch>=? AND pnl_part IS NOT NULL "
        "ORDER BY epoch",(arm,FWD0)):
        rows.append(dict(candle_epoch=int(ep),arm=arm,sec=int(sec),side=('UP' if up else 'DOWN'),
                         ask=round(float(ask),4),filled_shares=round(float(shq or 0.0),6),
                         pnl_usd_at10=round(float(pp),6),source='forward'))
rows.sort(key=lambda r:(r['candle_epoch'],r['arm']))
with open(OUT,'w',newline='') as fh:
    w=csv.DictWriter(fh,fieldnames=['candle_epoch','arm','sec','side','ask','filled_shares','pnl_usd_at10','source'])
    w.writeheader(); w.writerows(rows)
d0=dt.datetime.fromtimestamp(min(r['candle_epoch'] for r in rows),dt.UTC)
d1=dt.datetime.fromtimestamp(max(r['candle_epoch'] for r in rows),dt.UTC)
print(f'wrote {len(rows)} rows  {d0:%m-%d %H:%M} .. {d1:%m-%d %H:%M} UTC')
for s in ('history','forward'):
    sub=[r for r in rows if r['source']==s]
    days=sorted({dt.datetime.fromtimestamp(r['candle_epoch'],dt.UTC).strftime('%m-%d') for r in sub})
    print(f'  {s:8s} {len(sub):5d} rows, days {days}')
for arm in ('FAV','FAV_ref','FAV_mid','FAV_all'):
    sub=[r for r in rows if r['arm']==arm]
    print(f'  {arm:8s} {len(sub):5d} rows, pnl@10 sum {sum(r["pnl_usd_at10"] for r in sub):+9.2f}')
