#!/usr/bin/env python3
"""EF-2 step 3: the two comparison arms, on exactly the days the walk-forward scores. READ-ONLY.

Both are rebuilt from the SAME candidate table as EF-2, so the fill simulator, the prices, the labels and the
one-fire-per-candle convention are identical and the only thing that differs is the rule.

  fixed15   - the rule live on London before the pause: Platt a=1.0677 b=-0.3208 applied to the engine p,
              EV >= 0.15 taken at ask + 1 tick (poly_core.EV_REFERENCE_PAD, as the engine does).
  S=15      - the placebo from EF_FIRE_TIME section 2: first pass at sec >= 15 with own ask <= 0.60, model
              still choosing the SIDE but its confidence bar dropped entirely.

Both fire only on the side the ENGINE picked, which is the side with p_side >= 0.5 - that is how the logged
side is recovered from the candidate table, since the engine only ever logged the side it favoured.
"""
import sys, math, collections, numpy as np
from decimal import Decimal, ROUND_CEILING

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, W, halves, perm_opp, per1, cost, MIN_CELL, be

A_P, B_P, TICK, RATE, PAD = 1.0677, -0.3208, 0.01, 0.07, 1
Dc = lambda x: Decimal(str(x))


def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))


def pad_cost(ask):
    px = float((Dc(ask) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))


def run(label, qual, cands, nday):
    sel = []
    for ep, lst in cands.items():
        best = None
        for t, p, ask, q, win, oq, sec in sorted(lst):
            if p < 0.5: continue                       # the engine only ever fired on the side it favoured
            if not qual(p, ask, sec): continue
            best = (win, q, t, oq); break
        if best: sel.append(best)
    nf = sum(1 for s in sel if s[1] == s[1])
    wins = [s[0] for s in sel if s[1] == s[1]]
    h1, h2 = halves(sel)
    tot = sum(10.0 * per1(w_, qq) for w_, qq, *_ in sel if qq == qq)
    print(f'  {label:30s}{len(sel):>7}{len(sel)/max(nday,1):>7.0f}{nf:>7}'
          f'{100*nf/max(len(sel),1):>6.1f}%{(100*np.mean(wins) if wins else float("nan")):>6.1f}%'
          f'{W(sel):>+9.3f}{tot:>+9.1f}{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
          f'{perm_opp(sel):>7.3f}' + ('  *n<60' if nf < MIN_CELL else ''))


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True)
    X, y, q, ep, ts, day = z['X'], z['y'].astype(float), z['q'], z['ep'], z['ts'], z['day']
    names = [str(s) for s in z['names']]
    keep = np.all(np.isfinite(X), axis=1)
    X, y, q, ep, ts, day = X[keep], y[keep], q[keep], ep[keep], ts[keep], day[keep]
    isup = z['is_up'][keep]
    days = sorted(set(day.tolist()))
    scored = set(days[1:])                     # exactly the days the walk-forward scores
    m = np.array([d in scored for d in day.tolist()])
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    opp = {}
    for i in np.nonzero(m)[0]:
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    cands = collections.defaultdict(list)
    for i in np.nonzero(m)[0]:
        cands[int(ep[i])].append((int(ts[i]), float(X[i, ip]), float(X[i, ia]), float(q[i]), float(y[i]),
                                  opp.get((int(ts[i]), int(isup[i])), float('nan')), int(X[i, isec])))
    nday = len(scored)
    print(f'comparison arms on the walk-forward days {sorted(scored)}: {len(cands)} candles, '
          f'{int(m.sum()):,} candidate rows')
    print(f'  {"arm":30s}{"fires":>7}{"/day":>7}{"fills":>7}{"fill%":>7}{"win%":>7}{"per$1":>9}'
          f'{"total$":>9}{"H1":>8}{"H2":>8}{"permP":>7}')
    run('fixed15 (the paused London rule)',
        lambda p, a, s: (platt(p) / pad_cost(a) - 1) >= 0.15, cands, nday)
    run('S=15 placebo (EF_FIRE_TIME)',
        lambda p, a, s: s >= 15 and a <= 0.60, cands, nday)
    run('raw25 (EV>=0.25 at the ask)',
        lambda p, a, s: (p / be(a) - 1) >= 0.25, cands, nday)
