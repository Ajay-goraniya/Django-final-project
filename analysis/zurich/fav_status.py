#!/usr/bin/env python3
"""READ-ONLY status of the FAV family since FAV's first row. Opens every source mode=ro and writes
nothing. The size-rejection count is NOT stored in the fires table - _fav_fill returns NaN for a price
miss and a size miss alike - so it is recomputed here by replaying the same decision with and without
the size gate. usage: fav_status.py"""
import sys, sqlite3, numpy as np, datetime as dt
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S

f = lambda t: dt.datetime.fromtimestamp(t, dt.UTC).strftime('%m-%d %H:%M')
sh = sqlite3.connect(f'file:{S.DB}?mode=ro', uri=True)
START = sh.execute("SELECT min(epoch) FROM fires WHERE arm='FAV'").fetchone()[0]
if START is None:
    print('FAV has no rows yet'); sys.exit()
now = sh.execute("SELECT max(epoch) FROM seen").fetchone()[0]
seen = [e for (e,) in sh.execute("SELECT epoch FROM seen WHERE epoch >= ? ORDER BY epoch", (START,))]
print(f'window: {f(START)} .. {f(now)}  ({(now-START)/3600:.1f} h)   candles seen {len(seen)}')

BN = S._bn_1s()
gate_ok = sum(1 for e in seen if S._vol_bn(BN, e) is not None)
vols = [S._vol_bn(BN, e) for e in seen]
low = sum(1 for v in vols if v is not None and v < S.FAV_CUT_LOW)
mid = sum(1 for v in vols if v is not None and S.FAV_CUT_LOW <= v < S.FAV_CUT_MID)
print(f'  bn_flow vol computable on {gate_ok}/{len(seen)} candles (240 s gate) | '
      f'LOW(<{S.FAV_CUT_LOW}) {low}  MID {mid}  HIGH {gate_ok-low-mid}')

# size-rejection replay: price-only fill vs price+size fill, same code path
S.ALL52, S.STRICT = None, None
S.FAV_BK = S._fav_books(); S.FAV_BN1 = BN
REF = S._ref_tape()
cand, vo, nk = S.load_candles()
size_rej = {a: 0 for a in ('FAV', 'FAV_mid', 'FAV_all', 'FAV_ref')}
nosize = 0
for e in [x for x in seen if x in cand and x in vo]:
    rows = S.build_rows(cand[e], e, vo[e], nk)
    fv = sorted((r for r in rows if S.FAV_SEC[0] <= r['sec'] <= S.FAV_SEC[1] and r['own'] > r['opp']
                 and S.FAV_BAND[0] <= r['own'] <= S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    r0 = dict(fv[0])
    with_sz = S._fav_fill(cand[e], r0)
    bk, S.FAV_BK = S.FAV_BK, {}          # same call, size gate disabled
    no_sz = S._fav_fill(cand[e], r0)
    S.FAV_BK = bk
    rejected = (no_sz == no_sz) and (with_sz != with_sz)
    # the size is checked at the ARRIVAL second, not the decision second, so the coverage probe has to
    # look there too - probing r0['ts'] would report on a book row the gate never consults.
    ta = np.array([x[0] for x in sorted(cand[e], key=lambda x: x[0])])
    j = int(np.searchsorted(ta, r0['ts'] + S.FAV_LAG_MS, side='left'))
    if j < len(ta) and S.FAV_BK.get(int(ta[j] // 1000)) is None: nosize += 1
    if rejected:
        vb, vr = S._vol_bn(BN, e), S._vol_open(REF, e)
        if vb is not None:
            size_rej['FAV_all'] += 1
            if vb < S.FAV_CUT_LOW: size_rej['FAV'] += 1
            elif vb < S.FAV_CUT_MID: size_rej['FAV_mid'] += 1
        if vr is not None and vr < S.FAV_REF_CUT: size_rej['FAV_ref'] += 1

hdr = 'arm        decisions  fills  fill%  size-rej  wins  win% of fills     $@10      DD'
print(); print(hdr); print('-' * len(hdr))
for arm in ('FAV', 'FAV_mid', 'FAV_all', 'FAV_ref', 'C_fixed15'):
    r = sh.execute("SELECT fill, win, pnl FROM fires WHERE arm=? AND epoch >= ? ORDER BY epoch",
                   (arm, START)).fetchall()
    n = len(r); fl = [x for x in r if x[0] is not None]
    w = sum(x[1] for x in fl)
    pnl = np.array([x[2] for x in r], dtype=float)
    cum = np.cumsum(pnl)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum])) if n else 0.0
    sr = size_rej.get(arm, 0)
    print(f'{arm:11s} {n:8d} {len(fl):6d} {100*len(fl)/max(n,1):5.0f}% {sr:9d} {w:5d} '
          f'{100*w/max(len(fl),1):9.0f}%   {pnl.sum():+8.2f} {dd:7.2f}')
print()
# gaps / errors
lo, hi = min(BN), max(BN)
miss = sum(1 for t in range(max(lo, START - 300), hi + 1) if t not in BN)
span = hi - max(lo, START - 300) + 1
print(f'bn_flow: {f(lo)} .. {f(hi)}, {100*(1-miss/max(span,1)):.1f}% of seconds present after the 60 s-capped fill')
gaps = sorted({e for e in seen if S._vol_bn(BN, e) is None})
print(f'  candles refused by the 240 s gate: {len(gaps)}' + (f'  {[f(g) for g in gaps[:4]]}' if gaps else ''))
print(f'  FAV decisions with no book row for the size check: {nosize}')
