#!/usr/bin/env python3
"""OWNER, 09-28 13:3x: "test fixed on the 10 days data and see the fires only after 220 s". READ-ONLY.

TWO DIFFERENT THINGS, and the difference matters:

(1) THE SLICE. The 10-day stable_ef FIXED fire set, restricted to the fires that happened to land at
    sec >= 220. This is a description of fires the normal rule already made - it is not a rule anyone could
    have followed, because you cannot know in advance that the rule will not fire earlier.

(2) THE RULE. fixed15 re-run so that it MAY ONLY fire at the first qualifying pass with sec >= S. Candles the
    normal rule fired on early now get their chance at S or later instead. This one IS followable, and it is
    what the owner means. S = 200 / 220 / 230 so 220 is not a single cell.

(2) reads the research archive live, so it covers every day of per-pass decide_log currently held, not a
frozen snapshot. Fills for (2) are ef_persist's per-pass FAK simulator; paper and the London-exec model are
reported beside it so the execution assumption is visible rather than chosen.
"""
import sys, math, collections, random, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import stable_ef as S
from ef_persist import load as pload, fill as pfill, per1 as pper1, cost as pcost

SS = (200, 220, 230)
A_P, B_P, TICK, RATE, PAD, STAKE = 1.0677, -0.3208, 0.01, 0.07, 1, 10.0
MIN_CELL = 60
Dc = lambda x: Decimal(str(x))
be = lambda q: q * (1 + RATE * (1 - q))


def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))


def pad_cost(a):
    px = float((Dc(a) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))


qual = lambda p, a: (platt(p) / pad_cost(a) - 1) >= 0.15


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return mdd, worst


if __name__ == '__main__':
    # ---------------- (1) the SLICE, 10 days ----------------
    rows = [r for r in S.load() if r['arm'] == 'FIXED']
    days1 = sorted({r['day'] for r in rows})
    print(f'(1) SLICE - stable_ef FIXED fires, {len(rows)} fires over {len(days1)} days {days1}')
    print(f'  {"cut":12s}{"n":>5}{"lost":>6}{"win%":>7}{"paper$1":>9}{"paper$":>9}{"pDD$":>7}'
          f'{"LON$1":>8}{"LON$":>8}{"lonDD$":>8}{"run":>5}{"days+":>7}')
    for lab, fn in (('ALL', lambda r: True), ('sec >= 200', lambda r: r['sec'] >= 200),
                    ('sec >= 220', lambda r: r['sec'] >= 220), ('sec >= 230', lambda r: r['sec'] >= 230)):
        sub = sorted([r for r in rows if fn(r)], key=lambda r: r['ts'])
        if not sub: print(f'  {lab:12s}{0:>5}   (none)'); continue
        c = S.curve(sub, [STAKE] * len(sub))
        l1, lt = S.london(sub, [STAKE] * len(sub))
        rng = random.Random(17); mdds = []
        for _ in range(200):
            cum = peak = m = 0.
            for r in sub:
                if rng.random() > (0.541 if r['win'] else 0.650): continue
                px = min(0.99, max(0.01, r['ask'] + S.slip(rng))); sh = STAKE / px
                f_ = RATE * sh * px * (1 - px)
                cum += (sh if r['win'] else 0) - STAKE - f_
                peak = max(peak, cum); m = max(m, peak - cum)
            mdds.append(m)
        lost = sum(1 for r in sub if not r['win'])
        _, run = dd_run(c['seq'])
        print(f'  {lab:12s}{len(sub):>5}{lost:>6}{100*np.mean([r["win"] for r in sub]):>6.1f}%'
              f'{c["pnl"]/max(c["spent"],1e-9):>+9.3f}{c["pnl"]:>+9.1f}{c["mdd"]:>7.1f}'
              f'{l1:>+8.3f}{lt:>+8.1f}{np.mean(mdds):>8.1f}{run:>5}'
              f'{f"{c[chr(112)+chr(111)+chr(115)+chr(95)+chr(100)+chr(97)+chr(121)+chr(115)]}/{c[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}'
              + ('  *n<60' if len(sub) < MIN_CELL else ''))
    for lab, fn in (('sec >= 220', lambda r: r['sec'] >= 220),):
        sub = [r for r in rows if fn(r)]
        byd = collections.defaultdict(list)
        for r in sub: byd[r['day']].append(r)
        print(f'  per day at {lab}: ' + '  '.join(
            f'{d} n{len(v)} {sum(STAKE*S.per1(r["win"], r["ask"]) for r in v):+.0f}$'
            for d, v in sorted(byd.items())))

    # ---------------- (2) the RULE, all per-pass days ----------------
    cand, _ = pload()
    days2 = sorted({r['day'] for rs in cand.values() for r in rs})
    print(f'\n(2) RULE - fixed15 may only fire at the first qualifying pass with sec >= S. '
          f'{len(cand)} candles, {len(days2)} days {days2}')
    print(f'  {"rule":14s}{"fires":>6}{"/day":>6}{"fills":>6}{"fill%":>7}{"lost":>6}{"win%":>7}'
          f'{"FAK$1":>8}{"FAK$":>8}{"DD$":>7}{"paper$1":>9}{"LON$1":>8}{"LON$":>8}{"run":>5}{"days+":>7}')
    for Sc in SS:
        sel = []
        for ep, rs in cand.items():
            f1 = next((r for r in rs if r['sec'] >= Sc and qual(r['p_raw'], r['ask'])), None)
            if f1 is not None: sel.append(f1)
        sel.sort(key=lambda r: r['t'])
        if not sel: print(f'  {f"sec >= {Sc}":14s}{0:>6}'); continue
        fl = [(r, pfill(r)) for r in sel]
        got = [(r, q) for r, q in fl if q is not None]
        seq = [STAKE * pper1(r['win'], q) for r, q in got]
        mdd, run = dd_run(seq)
        den = sum(STAKE * pcost(q) for _, q in got)
        pap = [STAKE * pper1(r['win'], r['ask']) for r in sel]
        pden = sum(STAKE * pcost(r['ask']) for r in sel)
        lrows = [dict(win=r['win'], ask=r['ask'], day=r['day'], ts=r['t']) for r in sel]
        l1, lt = S.london(lrows, [STAKE] * len(lrows))
        byd = collections.defaultdict(float)
        for r, q in got: byd[r['day']] += STAKE * pper1(r['win'], q)
        lost = sum(1 for r, q in got if not r['win'])
        print(f'  {f"sec >= {Sc}":14s}{len(sel):>6}{len(sel)/max(len(days2),1):>6.1f}{len(got):>6}'
              f'{100*len(got)/len(sel):>6.1f}%{lost:>6}'
              f'{(100*np.mean([r["win"] for r, _ in got]) if got else float("nan")):>6.1f}%'
              f'{(sum(seq)/den if den else float("nan")):>+8.3f}{sum(seq):>+8.1f}{mdd:>7.1f}'
              f'{(sum(pap)/pden if pden else float("nan")):>+9.3f}{l1:>+8.3f}{lt:>+8.1f}{run:>5}'
              f'{f"{sum(1 for v in byd.values() if v>0)}/{len(byd)}":>7}'
              + ('  *n<60' if len(got) < MIN_CELL else ''))
        print(f'      per day (FAK $): ' + '  '.join(f'{d} {byd.get(d,0.0):+.0f}' for d in days2))
