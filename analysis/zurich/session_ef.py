#!/usr/bin/env python3
"""Did fixed / raw work by SESSION? READ-ONLY research, no deploy. Owner's question via V, 09-30.

Per-pass FAK sim at London exec (+250 ms) on decide_log 09-24..30, $10, gamma labels, fee exact.
Arms: fixed15, raw25 S0=60, raw25 S0=0, and the top-3 EF-10 grid cells by TRAIN P/DD.
Sessions FIXED BEFORE LOOKING (UTC): Asia 00-07, Europe 07-13, US 13-20, Late 20-24.
WALK-FORWARD: cells chosen on 09-24..27 (train $>0, BOTH train halves >0, n>=30); sealed test 09-28..30.

Rows come from ef3_shadow.build_rows, whose --selftest proves it row-for-row against ef2_rows.npz, and
whose q IS the +250 ms FAK fill. The arm predicates are imported from ef3_fine (QUAL) and the EF-10 cell
semantics are copied from ef10.py, so nothing here is a re-derivation of a published rule."""
import sys, collections, itertools, numpy as np, datetime as dt
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
from ef3_fine import QUAL
from ef2_model import per1, cost, be
from ef3 import platt, pad_cost
TICK, STAKE = 0.01, 10.0
TRAIN, TEST = ('09-24', '09-25', '09-26', '09-27'), ('09-28', '09-29', '09-30')
SESS = [('Asia 00-07', 0, 7), ('Europe 07-13', 7, 13), ('US 13-20', 13, 20), ('Late 20-24', 20, 24)]
EVS, EARLY, LATE = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40), (0, 30, 60, 90), (180, 210, 240)
AMIN, AMAX, CAPS = (0.05, 0.15, 0.25), (0.55, 0.65, 0.80), (0, 1, 2)


def rows():
    S.ALL52, S.STRICT = None, None
    cand, vo, nk = S.load_candles()
    out = []
    for ep in sorted(cand):
        if ep not in vo: continue
        d = dt.datetime.fromtimestamp(ep, dt.UTC)
        day = d.strftime('%m-%d')
        if day not in TRAIN + TEST: continue
        for r in S.build_rows(cand[ep], ep, vo[ep], nk):
            out.append(dict(ep=ep, ts=r['ts'], own=r['own'], lat=r['q'], ps=r['pe'], sec=r['sec'],
                            win=r['win'], day=day, hour=d.hour))
    out.sort(key=lambda r: (r['ep'], r['ts']))
    return out


def score(fires, hc=0.0):
    fl = [f for f in fires if f['q'] == f['q']]
    if not fl: return dict(n=len(fires), nf=0, tot=0.0, mdd=0.0, byd={})
    pnl = [STAKE * per1(f['win'], min(f['q'] + hc, 0.99)) for f in fl]
    c = np.cumsum(pnl); mdd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    byd = collections.defaultdict(float)
    for f, p in zip(fl, pnl): byd[f['day']] += p
    h = len(pnl) // 2
    return dict(n=len(fires), nf=len(fl), tot=float(sum(pnl)), mdd=mdd, byd=dict(byd),
                h1=float(sum(pnl[:h])), h2=float(sum(pnl[h:])))


def fire_named(R, arm, S0):
    """one fire per candle: first pass at sec>=S0 passing the arm predicate; q = the +250 ms fill."""
    out, seen = [], set()
    for r in R:
        if r['ep'] in seen or r['sec'] < S0: continue
        c = dict(p=r['ps'], ask=r['own'])
        if QUAL[arm](c):
            seen.add(r['ep']); out.append(dict(q=r['lat'], win=r['win'], day=r['day'], hour=r['hour']))
    return out


def fire_cell(R, evb, e, l, amn, amx, cp):
    out, seen = [], set()
    for r in R:
        if r['ep'] in seen: continue
        if r['ps'] < 0.5 or not (e <= r['sec'] <= l) or not (amn <= r['own'] <= amx): continue
        capx = min(r['own'] + cp * TICK, 0.99)
        if (r['ps'] / be(capx) - 1.0) < evb: continue
        seen.add(r['ep'])
        q = r['lat'] if (r['lat'] == r['lat'] and r['lat'] <= capx + 1e-12) else float('nan')
        out.append(dict(q=q, win=r['win'], day=r['day'], hour=r['hour']))
    return out


R = rows()
days = sorted({r['day'] for r in R})
print(f'rows {len(R):,}  candles {len({r["ep"] for r in R}):,}  days {days}')
print(f'train {list(TRAIN)}   sealed test {list(TEST)}\n')
Rtr = [r for r in R if r['day'] in TRAIN]

# --- top-3 EF-10 cells by TRAIN P/DD (chosen on train only, never on test) ---
cells = []
for evb, e, l, amn, amx, cp in itertools.product(EVS, EARLY, LATE, AMIN, AMAX, CAPS):
    st = score(fire_cell(Rtr, evb, e, l, amn, amx, cp))
    if st['nf'] < 30 or st['mdd'] <= 0: continue
    cells.append((st['tot'] / st['mdd'], (evb, e, l, amn, amx, cp), st))
cells.sort(key=lambda x: -x[0])
top3 = cells[:3]
print('TOP-3 EF-10 CELLS BY TRAIN P/DD (selected on 09-24..27 only)')
for pdd, prm, st in top3:
    print(f'  ev{prm[0]} sec{prm[1]}-{prm[2]} ask{prm[3]}-{prm[4]} cap+{prm[5]}  train $ {st["tot"]:+7.1f} '
          f'DD {st["mdd"]:6.1f} P/DD {pdd:.2f} n {st["nf"]}')
ARMS = [('fixed15', lambda Rx: fire_named(Rx, 'fixed15', 0)),
        ('raw25 S0=60', lambda Rx: fire_named(Rx, 'raw25', 60)),
        ('raw25 S0=0', lambda Rx: fire_named(Rx, 'raw25', 0))]
for i, (pdd, prm, st) in enumerate(top3):
    ARMS.append((f'EF10#{i+1} ev{prm[0]} {prm[1]}-{prm[2]} {prm[3]}-{prm[4]} c{prm[5]}',
                 (lambda p: (lambda Rx: fire_cell(Rx, *p)))(prm)))

print('\nFULL GRID  (train 09-24..27 -> sealed test 09-28..30), $ at $10/fill')
print('arm                                  session        train $/n      test $/n    KEEP')
kept = []
for name, fn in ARMS:
    ftr, fte = fn(Rtr), fn([r for r in R if r['day'] in TEST])
    for sname, lo, hi in SESS:
        a = score([f for f in ftr if lo <= f['hour'] < hi])
        b = score([f for f in fte if lo <= f['hour'] < hi])
        keep = a['nf'] >= 30 and a['tot'] > 0 and a.get('h1', 0) > 0 and a.get('h2', 0) > 0
        if keep: kept.append((name, sname, lo, hi, b))
        print(f'  {name:34s} {sname:13s} {a["tot"]:+8.1f}/{a["nf"]:<4d} {b["tot"]:+8.1f}/{b["nf"]:<4d}  '
              + ('KEEP' if keep else ''))
print(f'\nKEPT CELLS (train $>0, BOTH train halves >0, n>=30): {len(kept)}')
if kept:
    pn, byd = 0.0, collections.defaultdict(float)
    for name, sname, lo, hi, b in kept:
        print(f'  {name} / {sname}: test $ {b["tot"]:+.1f} n {b["nf"]}')
        pn += b['tot']
        for d_, v in b['byd'].items(): byd[d_] += v
    print(f'  POOLED sealed test: $ {pn:+.1f}, days + {sum(1 for v in byd.values() if v>0)}/{len(byd)}')
else:
    print('  none - no arm x session cell passed the train filter, so there is nothing to test.')
print('\nSAME ARMS TRADING ALL SESSIONS ON THE TEST DAYS (the thing a session filter has to beat)')
for name, fn in ARMS:
    b = score(fn([r for r in R if r['day'] in TEST]))
    print(f'  {name:34s} test $ {b["tot"]:+8.1f}  n {b["nf"]:<4d} DD {b["mdd"]:6.1f} '
          f'days+ {sum(1 for v in b["byd"].values() if v>0)}/{len(b["byd"])}')
