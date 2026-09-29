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
capped_n = {a: 0 for a in size_rej}
nosize = 0
for e in [x for x in seen if x in cand and x in vo]:
    rows = S.build_rows(cand[e], e, vo[e], nk)
    fv = sorted((r for r in rows if S.FAV_SEC[0] <= r['sec'] <= S.FAV_SEC[1] and r['own'] > r['opp']
                 and S.FAV_BAND[0] <= r['own'] <= S.FAV_BAND[1]), key=lambda r: r['ts'])
    if not fv: continue
    r0 = dict(fv[0])
    # _fav_fill returns a DICT now, so the old on/off replay (`d != d`) silently reported zero. Read the
    # two outcomes straight off it instead: price cleared but the all-or-nothing gate refused, and
    # price cleared but depth truncated the partial fill.
    d = S._fav_fill(cand[e], r0)
    price_ok = d['px'] == d['px']
    aon_rej = price_ok and (d['aon'] != d['aon'])
    ta = np.array([x[0] for x in sorted(cand[e], key=lambda x: x[0])])
    j = int(np.searchsorted(ta, r0['ts'] + S.FAV_LAG_MS, side='left'))
    if j < len(ta) and S.FAV_BK.get(int(ta[j] // 1000)) is None: nosize += 1
    if not price_ok: continue
    vb, vr = S._vol_bn(BN, e), S._vol_open(REF, e)
    tags = []
    if vb is not None:
        tags.append('FAV_all')
        tags.append('FAV' if vb < S.FAV_CUT_LOW else ('FAV_mid' if vb < S.FAV_CUT_MID else None))
    if vr is not None and vr < S.FAV_REF_CUT: tags.append('FAV_ref')
    for a in [t for t in tags if t]:
        if aon_rej: size_rej[a] += 1
        if d['capped']: capped_n[a] += 1

hdr = ('arm         dec | PARTIAL: scored filled shares wins  win%     $@10    DD  cap | '
       'AON: fills size-rej    $@10    DD')
print(); print(hdr); print('-' * len(hdr))
for arm in ('FAV', 'FAV_mid', 'FAV_all', 'FAV_ref', 'C_fixed15'):
    r = sh.execute("SELECT fill, win, pnl, sh, pnl_part FROM fires WHERE arm=? AND epoch >= ? "
                   "ORDER BY epoch", (arm, START)).fetchall()
    n = len(r)
    aon = [x for x in r if x[0] is not None]
    pa = np.array([x[2] for x in r], dtype=float)
    dda = float(np.max(np.maximum.accumulate(np.r_[0, np.cumsum(pa)]) - np.r_[0, np.cumsum(pa)])) if n else 0.0
    # the partial columns are NULL on rows written before the model existed - excluded, not zero-filled
    pr = [x for x in r if x[4] is not None]
    got = [x for x in pr if (x[3] or 0) > 0]
    pp = np.array([x[4] for x in pr], dtype=float)
    ddp = float(np.max(np.maximum.accumulate(np.r_[0, np.cumsum(pp)]) - np.r_[0, np.cumsum(pp)])) if len(pr) else 0.0
    wp = sum(x[1] for x in got)
    # `scored` is the denominator: rows written since the partial model existed. Without it a fresh
    # arm shows 0 filled / $0.00 and reads as "the model fills nothing" rather than "no rows yet".
    print(f'{arm:11s} {n:4d} | {len(pr):13d} {len(got):6d} {sum(x[3] for x in got):6.1f} {wp:4d} '
          f'{100*wp/max(len(got),1):4.0f}% {pp.sum():+8.2f} {ddp:5.2f} {capped_n.get(arm,0):4d} | '
          f'{len(aon):9d} {size_rej.get(arm,0):8d} {pa.sum():+8.2f} {dda:5.2f}')
print()
print('  PARTIAL = V\'s venue mechanic: take every share at price <= cap, cancel the rest, $ scales with')
print('  shares filled. TRUNCATED AT LEVEL 1 - the recorder persists only the top level, so depth at the')
print('  next level (which ask+1c reaches) is unknown and `filled` is a FLOOR, not V\'s exact model.')
print('  ALL-OR-NOTHING = the previously registered gate, kept as the reference column.')
# gaps / errors
lo, hi = min(BN), max(BN)
miss = sum(1 for t in range(max(lo, START - 300), hi + 1) if t not in BN)
span = hi - max(lo, START - 300) + 1
print(f'bn_flow: {f(lo)} .. {f(hi)}, {100*(1-miss/max(span,1)):.1f}% of seconds present after the 60 s-capped fill')
gaps = sorted({e for e in seen if S._vol_bn(BN, e) is None})
print(f'  candles refused by the 240 s gate: {len(gaps)}' + (f'  {[f(g) for g in gaps[:4]]}' if gaps else ''))
print(f'  FAV decisions with no book row for the size check: {nosize}')
