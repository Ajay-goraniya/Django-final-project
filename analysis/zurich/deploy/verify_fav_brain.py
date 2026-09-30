#!/usr/bin/env python3
"""Check (b): does the staged FAV brain reproduce the shadow's FAV decisions byte-for-byte - same candle,
side, sec and ask? Replays the ENGINE's own decide_log passes through the brain and diffs against the
shadow's recorded FAV fires. READ-ONLY."""
import sys, sqlite3, glob, zipfile, numpy as np, datetime as dt
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich/deploy')
import ef3_shadow as S, poly_fav
hm=lambda t: dt.datetime.fromtimestamp(t,dt.UTC).strftime('%m-%d %H:%M')

# full forward-filled bn_flow series, same construction the brain uses live (its live read is capped to
# the last hour for speed; for a historical replay it is handed the whole series explicitly)
PX=S._bn_1s()
ENG='/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
sh=sqlite3.connect(f'file:{S.DB}?mode=ro',uri=True)
fires={int(e):(int(u),float(a),int(s)) for e,u,a,s in sh.execute(
    "SELECT epoch,up,ask,sec FROM fires WHERE arm='FAV' ORDER BY epoch")}
eng=sqlite3.connect(f'file:{ENG}?mode=ro',uri=True)
eps=sorted(fires)[-40:]                      # the last 40 FAV candles the shadow recorded
print(f'check (b): replaying the ENGINE decide_log through the staged brain on the last {len(eps)} FAV candles')
print('candle          shadow(side sec ask)      brain(side sec ask)      match')
ok=bad=miss=0
for ep in eps:
    rows=eng.execute("SELECT ts_ms,up_ask,dn_ask FROM decide_log WHERE epoch=? ORDER BY ts_ms",(ep,)).fetchall()
    b=poly_fav.FavBrain(); d=None
    for tms,ua,da in rows:
        sec=int(tms)//1000-ep
        d=b.watch(ep,sec,ua,da,px=PX)
        if d: break
    su,sa,ss=fires[ep]
    sside='UP' if su else 'DOWN'
    if d is None:
        miss+=1; print(f'{hm(ep)}  {sside:4s} {ss:4d} {sa:.2f}      (no fire: {b.block[:28]})   MISS'); continue
    m = (d['side']==sside and d['sec']==ss and abs(d['fav']['own_ask']-sa)<1e-9)
    ok+=m; bad+= (not m)
    print(f'{hm(ep)}  {sside:4s} {ss:4d} {sa:.2f}      {d["side"]:4s} {d["sec"]:4d} {d["fav"]["own_ask"]:.2f}      '
          + ('OK' if m else 'DIFFER'))
print()
print(f'  matched {ok}  differed {bad}  no-fire {miss}  of {len(eps)}')
print('  ' + ('(b) PASS - byte-for-byte on candle, side, sec and ask' if bad==0 and miss==0
              else '(b) FAIL - see the rows above'))
