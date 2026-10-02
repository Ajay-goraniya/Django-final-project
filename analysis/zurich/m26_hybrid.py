#!/usr/bin/env python3
"""M26 TEST A - HYBRID: rest at the bid 60-120, take the ask at 121-180 only if not filled.
READ-ONLY. Nothing is written to the probe, the shadow or the engine.

Phase 1 is the probe's REAL fills (real money, maker fee 0). Phase 2 is simulated with the shadow's
own arrival-fill model, called rather than reimplemented. The probe ran 60-180 until 11:50 today, so
phase 1 uses only its fills at sec <= 120 - the prereg logs that caveat and this honours it.
"""
import math, sqlite3, sys
import datetime as dt

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
from ef2_model import be

PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
A = int(dt.datetime(2026, 9, 30, 17, 0, tzinfo=dt.UTC).timestamp())
NOW = int(dt.datetime.now(dt.UTC).timestamp())
P1_HI, P2_LO, P2_HI = 120, 121, 180
BAR = 60

S.ALL52, S.STRICT = None, None
S.FAV_BK = S._fav_books(); S.FAV_BN1 = S._bn_1s()
cand, vo, nk = S.load_candles()

pr = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); pr.row_factory = sqlite3.Row
PFILL = {}
for r in pr.execute('select * from fills where pnl is not null and epoch>=? and epoch<?', (A, NOW)):
    sec = r['fill_ts_ms'] // 1000 - r['epoch']
    if sec > P1_HI: continue                     # phase 1 is 60-120 only, per the prereg caveat
    d = PFILL.setdefault(r['epoch'], dict(pnl=0.0, dep=0.0, sh=0.0, sec=sec, price=r['price']))
    d['pnl'] += r['pnl']; d['dep'] += r['spent']; d['sh'] += r['shares']

def fav_row(rows, lo, hi):
    fv = sorted((r for r in rows if lo <= r['sec'] <= hi and r['own'] > r['opp']
                 and S.FAV_BAND[0] <= r['own'] <= S.FAV_BAND[1]), key=lambda r: r['ts'])
    return dict(fv[0]) if fv else None

def taker(ep, r0):
    fd = S._fav_fill(cand[ep], r0)
    if not fd['got']: return None
    vw = fd['vwap'] if fd['vwap'] == fd['vwap'] else r0['own']
    return dict(pnl=float(S._fav_pnl(fd, r0['win'])), dep=float(fd['got']) * be(float(vw)),
                sec=int(r0['sec']), ask=float(r0['own']), sh=float(fd['got']))

REC = {}
for ep in sorted(cand):
    if ep < A or ep >= NOW or ep not in vo: continue
    v = S._vol_bn(S.FAV_BN1, ep)
    if v is None or v >= S.FAV_CUT_LOW: continue              # calm candles only, frozen gate
    try: rows = S.build_rows(cand[ep], ep, vo[ep], nk)
    except Exception: continue
    full = fav_row(rows, S.FAV_SEC[0], S.FAV_SEC[1])          # FAV taker as it actually is, 60-180
    fb = fav_row(rows, P2_LO, P2_HI)                          # the hybrid's phase-2 candidate
    REC[ep] = dict(probe=PFILL.get(ep), fav=taker(ep, full) if full else None,
                   fb=taker(ep, fb) if fb else None, day=dt.datetime.fromtimestamp(ep, dt.UTC).strftime('%m-%d'))

def hybrid(e):
    """Phase 1 if the probe really filled by sec 120, else the simulated phase-2 taker."""
    r = REC[e]
    return (r['probe'], 'maker') if r['probe'] else ((r['fb'], 'fallback') if r['fb'] else (None, None))

def agg(eps, pick):
    t = [x for x in (pick(e) for e in eps) if x]
    pnl = sum(x['pnl'] for x in t); dep = sum(x['dep'] for x in t)
    return len(t), pnl, (pnl / dep if dep else 0.0), dep

L = [f'M26 TEST A - HYBRID (rest 60-120, take 121-180 only if unfilled) vs FAV TAKER vs PROBE.',
     f'READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC. Window 09-30 17:00 .. now, calm candles only.',
     'Phase 1 = the probe\'s REAL fills at sec <= 120 (real money, maker fee 0). Phase 2 = simulated',
     "with the shadow's own _fav_fill/_fav_pnl (real recorded ask, arrival +500 ms, exact fee).",
     'Per $1 is on money ACTUALLY deployed on both legs, so the three arms are comparable.',
     f'calm candles in the window: {len(REC)}', '']

ALL = sorted(REC)
def table(eps, title):
    out = ['', f'== {title}  ({len(eps)} calm candles)',
           f'   {"arm":12s} {"trades":>6s} {"pnl $":>9s} {"per $1":>8s} {"deployed":>9s}  flag']
    rows = [('HYBRID', lambda e: hybrid(e)[0]),
            ('FAV taker', lambda e: REC[e]['fav']),
            ('PROBE only', lambda e: REC[e]['probe'])]
    res = {}
    for name, f in rows:
        n, pnl, per, dep = agg(eps, f)
        res[name] = (n, pnl, per)
        out.append(f'   {name:12s} {n:6d} {pnl:+9.2f} {per:+8.4f} {dep:9.2f}  '
                   f'{"INSUFFICIENT (<60)" if n < BAR else ""}')
    return out, res

o, R = table(ALL, 'WHOLE WINDOW'); L += o
half = ALL[:(len(ALL) + 1) // 2], ALL[(len(ALL) + 1) // 2:]
for i, h in enumerate(half, 1):
    o, _ = table(h, f'HALF {i} ({REC[h[0]]["day"]} .. {REC[h[-1]]["day"]})'); L += o

# the decisive number: the fallback leg on its own
fb = [REC[e]['fb'] for e in ALL if not REC[e]['probe'] and REC[e]['fb']]
n_fb = len(fb); p_fb = sum(x['pnl'] for x in fb); d_fb = sum(x['dep'] for x in fb)
w_fb = sum(1 for x in fb if x['pnl'] > 0); l_fb = sum(1 for x in fb if x['pnl'] < 0)
no_fb = sum(1 for e in ALL if not REC[e]['probe'] and not REC[e]['fb'])
L += ['', '== THE FALLBACK LEG ALONE - the number that decides it',
      f'   fallback trades: {n_fb} ({w_fb}W/{l_fb}L), pnl {p_fb:+.2f} on ${d_fb:.2f} = '
      f'{p_fb/max(d_fb,1e-9):+.4f} per $1'
      f'{"   INSUFFICIENT (<60)" if n_fb < BAR else ""}',
      f'   candles with no probe fill and no phase-2 qualifier (hybrid does nothing): {no_fb}',
      f'   mean fallback entry: sec {sum(x["sec"] for x in fb)/max(n_fb,1):.0f}, '
      f'ask {sum(x["ask"] for x in fb)/max(n_fb,1):.4f}',
      '   For reference, FAV taker entering in its full 60-180 window on the same candles:']
same = [REC[e]['fav'] for e in ALL if not REC[e]['probe'] and REC[e]['fav']]
if same:
    L.append(f'   {len(same)} trades, {sum(x["pnl"] for x in same):+.2f} on '
             f'${sum(x["dep"] for x in same):.2f} = '
             f'{sum(x["pnl"] for x in same)/max(sum(x["dep"] for x in same),1e-9):+.4f} per $1, '
             f'mean sec {sum(x["sec"] for x in same)/len(same):.0f} ask '
             f'{sum(x["ask"] for x in same)/len(same):.4f}')
    L.append('   -> the cost of WAITING for 121 instead of taking FAV\'s own first qualifying second.')

L += ['', '== PER DAY',
      f'   {"day":7s} {"candles":>7s} {"hyb n":>5s} {"hyb $":>8s} {"fav n":>5s} {"fav $":>8s} '
      f'{"probe n":>7s} {"probe $":>8s} {"fb n":>4s} {"fb $":>8s}']
for d in sorted({REC[e]['day'] for e in ALL}):
    eps = [e for e in ALL if REC[e]['day'] == d]
    hn, hp, _, _ = agg(eps, lambda e: hybrid(e)[0])
    fn, fp, _, _ = agg(eps, lambda e: REC[e]['fav'])
    pn, pp, _, _ = agg(eps, lambda e: REC[e]['probe'])
    fbd = [REC[e]['fb'] for e in eps if not REC[e]['probe'] and REC[e]['fb']]
    L.append(f'   {d:7s} {len(eps):7d} {hn:5d} {hp:+8.2f} {fn:5d} {fp:+8.2f} {pn:7d} {pp:+8.2f} '
             f'{len(fbd):4d} {sum(x["pnl"] for x in fbd):+8.2f}')

h1 = agg(half[0], lambda e: hybrid(e)[0]); h2 = agg(half[1], lambda e: hybrid(e)[0])
c1 = R['HYBRID'][2] > R['FAV taker'][2] and R['HYBRID'][1] > R['FAV taker'][1]
c2 = h1[1] > 0 and h2[1] > 0
L += ['', '== TEST A VERDICT against the prereg',
      f'   hybrid beats FAV taker per $1 AND in $: {R["HYBRID"][2]:+.4f} vs {R["FAV taker"][2]:+.4f}, '
      f'{R["HYBRID"][1]:+.2f} vs {R["FAV taker"][1]:+.2f} -> {"PASS" if c1 else "FAIL"}',
      f'   hybrid > 0 in both halves: {h1[1]:+.2f} and {h2[1]:+.2f} -> {"PASS" if c2 else "FAIL"}',
      f'   TEST A: {"PASS" if (c1 and c2) else "FAIL"}  (test B is forward and judged at 150 calm candles)']
print('\n'.join(L))
