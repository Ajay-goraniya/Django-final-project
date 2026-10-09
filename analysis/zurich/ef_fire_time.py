#!/usr/bin/env python3
"""WHEN should EF fire? Owner, 09-28 09:5x: "EF acts like everyone else - fires late, after the price has
moved. Predict.fun's v11 fired at ~20 s and earned early cheap entries. Same v10 model on both."

READ-ONLY on the Zurich research archive's decide_log. 5 days, 1,015 gamma-graded candles, raw p and both
side asks every ~250 ms. Master OFF, nothing live, nothing deployed.

Labels are the venue's own resolution. The fill simulator, the capital-weighted per $1 and the halves are
IMPORTED from ef_persist.py, so these numbers sit on the same basis as EF_PERSIST.md and EF_TRIGGER_SOURCE.md:
a FAK at ask+1 tick fills iff our side's ask on the first row at >= t+250 ms is within a tick, and it fills AT
that later ask.

PERMUTATION (V's spec, and it is stricter than ef_persist's): a flipped draw is priced at the OPPOSITE side's
real ask, not at 1-q+tick. Both arms then run the identical FAK test - the real arm on our side, the flipped
arm on the other side's ask at the same pass and at the same +250 ms row. A flipped draw that would not have
filled contributes nothing, exactly as a real non-fill contributes nothing. So the control answers "what if
the model had picked the other side", fully priced, rather than "what if the payout flipped".

Two facts from the data that make the grid unambiguous, both checked before building it:
  - the engine logs the side the MODEL favours on 100.0% of passes (p < 0.5 on 0.0% of 785,924), so a
    "p_side >= P" rule can only ever mean the logged side, and nothing is hidden on the unlogged one;
  - the binding constraint is the price, not p: 64.7% of passes already have p >= 0.70, but only 21.4% have
    an own-side ask <= 0.60.
"""
import sys, math, random, collections, statistics as st, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef_persist import (load, fill, fire_at_k, qual_fix, score, halves, per1, cost, be, pad_cost, platt,
                        TICK, STAKE, MIN_CELL, DELAY_MS)

S_GRID = (15, 20, 30, 45, 60, 90, 120)
P_GRID = (0.55, 0.60, 0.65, 0.70)
ASK_CAP = 0.60
SEC_BUCKETS = [(15, 30), (30, 60), (60, 120), (120, 180), (180, 241)]
ASK_BUCKETS = [(0.0, 0.45), (0.45, 0.55), (0.55, 1.0)]
DRAWS = 500


def augment(cand):
    """Add the OPPOSITE side's ask now and at +250 ms, so the permutation can price a flip properly."""
    for ep, rs in cand.items():
        ts = [r['t'] for r in rs]
        for i, r in enumerate(rs):
            r['opp'] = r['da'] if r['side'] == 'UP' else r['ua']
            j = np.searchsorted(ts, r['t'] + DELAY_MS, side='left')
            if j < len(rs):
                o = rs[j]['da'] if r['side'] == 'UP' else rs[j]['ua']
                r['opp_later'] = o if 0.01 < o < 0.99 else None
            else:
                r['opp_later'] = None


def fill_opp(r):
    if r.get('opp_later') is None or not (0.01 < r['opp'] < 0.99): return None
    return r['opp_later'] if r['opp_later'] <= r['opp'] + TICK + 1e-12 else None


def perm_opp(sel, draws=DRAWS, seed=11):
    """Sign flip priced at the OPPOSITE ask, both arms through the same FAK test."""
    fl = [(r, q) for r, q in sel if q is not None]
    if not fl: return float('nan'), float('nan')
    real = sum(per1(r['win'], q) * cost(q) for r, q in fl) / sum(cost(q) for r, q in fl)
    rng = random.Random(seed); sims = []
    for _ in range(draws):
        num = den = 0.0
        for r, q in fl:
            if rng.random() < 0.5:
                qo = fill_opp(r)
                if qo is None: continue                      # the other side would not have filled
                w, qq = 1 - r['win'], qo
            else:
                w, qq = r['win'], q
            num += per1(w, qq) * cost(qq); den += cost(qq)
        if den > 0: sims.append(num / den)
    if not sims: return float('nan'), float('nan')
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims), st.mean(sims)


def cell(sel):
    s = score(sel)
    if not s: return None
    a, b = halves(sel); pp, pm = perm_opp(sel)
    askm = np.mean([r['ask'] for r, _ in sel])
    secm = np.median([r['sec'] for r, _ in sel])
    return dict(n=s['n'], nf=s['nf'], fillpct=s['fillpct'], win=s['win'], per1=s['per1'], total=s['total'],
                h1=a, h2=b, pp=pp, pm=pm, ask=askm, sec=secm, days=s['days'])


HDR = (f'  {"rule":22s}{"fires":>6}{"fills":>6}{"fill%":>7}{"win%":>7}{"per$1":>9}{"total$":>9}'
       f'{"H1":>8}{"H2":>8}{"permP":>7}{"askFire":>8}{"secFire":>8}{"revC":>7}')


def line(lab, sel):
    c = cell(sel)
    if not c:
        print(f'  {lab:22s}{len(sel):6d}      (no fills)'); return None
    rv = [r['later'] - r['ask'] for r, _ in sel if r.get('later') is not None]
    print(f'  {lab:22s}{c["n"]:6d}{c["nf"]:6d}{100*c["fillpct"]:6.1f}%{100*c["win"]:6.1f}%'
          f'{c["per1"]:+9.3f}{c["total"]:+9.1f}{(c["h1"] or 0):+8.3f}{(c["h2"] or 0):+8.3f}'
          f'{c["pp"]:7.3f}{c["ask"]:8.3f}{c["sec"]:8.0f}'
          f'{(100*np.mean(rv) if rv else float("nan")):+7.2f}' + ('  *n<60' if c['nf'] < MIN_CELL else ''))
    return c


def fire_grid(rs, S, P):
    for r in rs:
        if r['sec'] >= S and r['p_raw'] >= P and r['ask'] <= ASK_CAP:
            return r
    return None


if __name__ == '__main__':
    cand, names = load()
    augment(cand)
    MV = names.index('move_bps') if 'move_bps' in names else None
    allrows = [r for rs in cand.values() for r in rs]
    print(f'candles graded {len(cand)}, passes {len(allrows)}, '
          f'days {sorted({r["day"] for r in allrows})}')
    opp_ok = sum(1 for r in allrows if r.get('opp_later') is not None)
    print(f'  opposite-side +{DELAY_MS} ms ask available on {opp_ok}/{len(allrows)} passes '
          f'({100*opp_ok/len(allrows):.1f}%) - that is what prices a flipped draw')

    # ---------------- 1. BASELINE: the current fixed15 rule ----------------
    print(f'\n{"="*136}\n1. BASELINE - the rule that is live on London today (fixed15, first qualifying pass)\n{"="*136}')
    base = {}
    for ep, rs in cand.items():
        r = fire_at_k(rs, qual_fix, 1)
        if r is not None: base[ep] = r
    bsel = [(r, fill(r)) for r in base.values()]
    secs = np.array([r['sec'] for r in base.values()])
    print(f'  fire second: p10 {np.percentile(secs,10):.0f}  p50 {np.percentile(secs,50):.0f}  '
          f'p90 {np.percentile(secs,90):.0f}   mean {secs.mean():.0f}   (decision window is 15-240 s)')
    print(f'  fires at sec <= 30: {int((secs<=30).sum())}/{len(secs)} = {100*(secs<=30).mean():.1f}%   '
          f'at sec >= 120: {int((secs>=120).sum())}/{len(secs)} = {100*(secs>=120).mean():.1f}%')
    print(HDR)
    line('fixed15 ALL', bsel)
    line('fixed15 + ask<=0.60', [(r, q) for r, q in bsel if r['ask'] <= ASK_CAP])
    print('  per $1 by FIRE-SECOND bucket:')
    for lo, hi in SEC_BUCKETS:
        line(f'  sec {lo}-{hi if hi<241 else 240}', [(r, q) for r, q in bsel if lo <= r['sec'] < hi])

    # ---------------- 2. THE GRID ----------------
    print(f'\n{"="*136}\n2. GRID - fire at the FIRST pass with sec >= S and raw p_side >= P and own ask <= {ASK_CAP}\n'
          f'   All 28 cells reported. No best cell.\n{"="*136}')
    print(HDR)
    G = {}
    for S in S_GRID:
        for P in P_GRID:
            sel = []
            for ep, rs in cand.items():
                r = fire_grid(rs, S, P)
                if r is not None: sel.append((r, fill(r)))
            G[(S, P)] = line(f'S={S:<3d} P={P:.2f}', sel)
        print('  ' + '-' * 134)
    # placebo on the model: the SAME timing rule with no p condition at all. If P=0.00 pays what P=0.55
    # pays, then p is contributing nothing and the whole effect is WHEN you fire, not what the model thinks.
    print(f'\n  PLACEBO CONTROL (not part of the grid): the same rule with NO p condition, P = 0.00.')
    print(HDR)
    for S in S_GRID:
        sel = []
        for ep, rs in cand.items():
            r = fire_grid(rs, S, 0.0)
            if r is not None: sel.append((r, fill(r)))
        G[(S, 0.0)] = line(f'S={S:<3d} P=0.00 placebo', sel)

    print('\n  per $1 as a grid (rows S, cols P); n fills in brackets:')
    print('    ' + ''.join(f'{"P="+format(P,".2f"):>18}' for P in (0.0,) + P_GRID))
    for S in S_GRID:
        row = f'    S={S:<3d}'
        for P in (0.0,) + P_GRID:
            c = G[(S, P)]
            row += f'{(f"{c[chr(112)+chr(101)+chr(114)+chr(49)]:+.3f} ({c[chr(110)+chr(102)]})" if c else "-"):>18}'
        print(row)

    # ---------------- 3. DOES EF FOLLOW THE CROWD? ----------------
    print(f'\n{"="*136}\n3. "FOLLOWS THE CROWD" - is the ask at the fire just the move that already happened?\n{"="*136}')
    fires = [r for r in base.values() if r['feats'] is not None and MV is not None
             and r['feats'][MV] is not None]
    x = np.array([abs(r['feats'][MV]) for r in fires])          # |move| from the opening TWAP60 line, bps
    sg = np.array([np.sign(r['feats'][MV]) for r in fires])
    dirn = np.array([1.0 if r['side'] == 'UP' else -1.0 for r in fires])
    y = np.array([(r['ask'] - 0.50) for r in fires])
    smv = np.array([r['feats'][MV] for r in fires])
    print(f'  n {len(fires)} fires with a move_bps feature')
    print(f'  corr(ask-0.50, move_bps signed toward OUR side) = '
          f'{np.corrcoef(y, smv*dirn)[0,1]:+.3f}   corr(ask-0.50, |move_bps|) = {np.corrcoef(y, x)[0,1]:+.3f}')
    print(f'  fires taken WITH the move already in place (sign(move) == our side): '
          f'{100*np.mean(sg==dirn):.1f}%')
    print('  ask-0.50 by |move_bps| bucket (if EF only buys what already moved, these rise together):')
    for lo, hi in [(0, 2), (2, 5), (5, 10), (10, 20), (20, 1e9)]:
        m = (x >= lo) & (x < hi)
        if m.sum() == 0: continue
        print(f'    |move| {lo:>3}-{hi if hi<1e9 else "inf":<4} n {int(m.sum()):5d}  mean ask-0.50 '
              f'{np.mean(y[m]):+.3f}  mean ask {np.mean([r["ask"] for r,k in zip(fires,m) if k]):.3f}')

    print('\n  per $1 by ASK-AT-FIRE x FIRE-SECOND (the two ways of asking "did we pay up for news"):')
    print(f'    {"ask bucket":14s}' + ''.join(f'{f"sec {lo}-{hi if hi<241 else 240}":>20}' for lo, hi in SEC_BUCKETS))
    for alo, ahi in ASK_BUCKETS:
        row = f'    {f"{alo:.2f}-{ahi:.2f}":14s}'
        for lo, hi in SEC_BUCKETS:
            s = [(r, q) for r, q in bsel if alo <= r['ask'] < ahi and lo <= r['sec'] < hi]
            c = score(s)
            row += f'{(f"{c['per1']:+.3f} ({c['nf']}/{c['n']})" if c else f"- (0/{len(s)})"):>20}'
        print(row)
    print('    cell format: per $1 (fills/fires). Anything under 60 fills is not a reading.')

    # what the same candle looked like EARLY
    print(f'\n  What p and the ask were at sec 20 and sec 30, in the {len(base)} candles fixed15 later fired on')
    print(f'  (ask is always OUR side - the side the fire eventually took - so it is the price we could have paid):')
    for probe in (20, 30):
        rec = []
        for ep, fr in base.items():
            rs = cand[ep]
            cands = [r for r in rs if r['sec'] <= probe]
            if not cands: continue
            r0 = cands[-1]
            own = r0['ua'] if fr['side'] == 'UP' else r0['da']
            if not (0.01 < own < 0.99): continue
            rec.append((own, r0['p_raw'], r0['side'] == fr['side'], fr['ask'], fr['sec'], fr['win']))
        if not rec: continue
        a0 = np.array([z[0] for z in rec]); p0 = np.array([z[1] for z in rec])
        af = np.array([z[3] for z in rec]); agree = np.mean([z[2] for z in rec])
        print(f'    sec {probe}: n {len(rec)}  ask then {a0.mean():.3f} (p50 {np.median(a0):.3f})  '
              f'ask at the fire {af.mean():.3f} (p50 {np.median(af):.3f})  ->  the price moved '
              f'{100*(af-a0).mean():+.2f}c against us on average, p50 {100*np.median(af-a0):+.2f}c')
        print(f'             p then {p0.mean():.3f} (p50 {np.median(p0):.3f}); the pass at sec {probe} already '
              f'favoured the SAME side we later bought on {100*agree:.1f}% of candles')
        cheaper = np.mean(a0 < af - 1e-9)
        print(f'             the sec-{probe} ask was CHEAPER than the fire ask on {100*cheaper:.1f}% of candles, '
              f'the same on {100*np.mean(abs(a0-af)<1e-9):.1f}%, dearer on {100*np.mean(a0>af+1e-9):.1f}%')
