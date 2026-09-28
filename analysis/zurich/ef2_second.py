#!/usr/bin/env python3
"""OWNER's design, 09-28 13:0x: keep the CURRENT EF, add a SECOND trigger in the same candle that can only
fire AFTER the first. READ-ONLY. Master OFF, London untouched.

His reasoning, via V: London's real 60-120 s fires re-cross the line 65% of the time and then win 25%, so the
second trigger is "a brain that knows the move is wrong and reverses".

FIRST FIRE = the current rule exactly: the first pass whose ENGINE-CHOSEN side (p >= 0.5, which the engine's
logged side always is) clears the bar.
SECOND FIRE = the first STRICTLY LATER pass in the same candle clearing the same bar, in three variants
reported side by side, no best cell:
    A  either side      B  opposite side only (the reversal)      C  same side only (the add)
For the second fire the bar is the EV test on THAT side's own p and ask - the opposite side's p is 1 - p, and
it is allowed to be below 0.5, because a reversal that required p >= 0.5 on both sides could never fire.

Both arms: raw25 (ev(p) >= 0.25) and fixed15 (ev(platt(p)) >= 0.15 at ask + 1 tick, as the engine does).
Fills are ef_persist's simulator per pass, so the fill collapse with the second is already inside every
number here - it is not applied as a flat rate.
"""
import sys, math, collections, statistics as st, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, per1, cost, be

A_P, B_P, TICK, RATE, PAD, STAKE = 1.0677, -0.3208, 0.01, 0.07, 1, 10.0
MIN_CELL = 60
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


QUAL = {'raw25': lambda p, a: (p / be(a) - 1) >= 0.25 if be(a) > 0 else False,
        'fixed15': lambda p, a: (platt(p) / pad_cost(a) - 1) >= 0.15}


def pnl(leg):
    return STAKE * per1(leg['win'], leg['q']) if leg and leg['q'] == leg['q'] else 0.0


def stats(legs):
    """legs in time order; returns per$1, total $, drawdown $, longest losing run."""
    fl = [l for l in legs if l and l['q'] == l['q']]
    if not fl: return float('nan'), 0.0, 0.0, 0
    num = sum(per1(l['win'], l['q']) * cost(l['q']) for l in fl)
    den = sum(cost(l['q']) for l in fl)
    cum = peak = mdd = 0.; run = worst = 0
    for l in sorted(fl, key=lambda x: x['t']):
        x = STAKE * per1(l['win'], l['q'])
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return num / den, sum(STAKE * per1(l['win'], l['q']) for l in fl), mdd, worst


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True)
    X, y, q, ep, ts, day = z['X'], z['y'].astype(float), z['q'], z['ep'], z['ts'], z['day']
    names = [str(s) for s in z['names']]; isup = z['is_up']
    fin = np.all(np.isfinite(X), axis=1)
    X, y, q, ep, ts, day, isup = X[fin], y[fin], q[fin], ep[fin], ts[fin], day[fin], isup[fin]
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    C = collections.defaultdict(list)
    for i in range(len(y)):
        C[int(ep[i])].append(dict(t=int(ts[i]), p=float(X[i, ip]), ask=float(X[i, ia]), q=float(q[i]),
                                  win=float(y[i]), sec=int(X[i, isec]), up=int(isup[i]), day=str(day[i])))
    for e in C: C[e].sort(key=lambda c: c['t'])
    days = sorted(set(day.tolist()))
    print(f'decide_log both-sides candidates: {len(C)} candles, {len(y):,} rows, days {days}')
    print(f'Fills are the ef_persist per-pass simulator, so the fill collapse with the second is inside every '
          f'number below.\n')

    for arm, qual in QUAL.items():
        first, second = {}, {v: {} for v in 'ABC'}
        for e, lst in C.items():
            f1 = next((c for c in lst if c['p'] >= 0.5 and qual(c['p'], c['ask'])), None)
            if f1 is None: continue
            first[e] = f1
            later = [c for c in lst if c['t'] > f1['t'] and qual(c['p'], c['ask'])]
            second['A'][e] = next((c for c in later), None)
            second['B'][e] = next((c for c in later if c['up'] != f1['up']), None)
            second['C'][e] = next((c for c in later if c['up'] == f1['up']), None)
        f1v, f1t, f1dd, f1run = stats(list(first.values()))
        nf1 = sum(1 for l in first.values() if l['q'] == l['q'])
        print(f'{"="*140}\n{arm}: FIRST FIRE (the current rule) - {len(first)} candles, {nf1} fills '
              f'({100*nf1/max(len(first),1):.1f}%), win {100*np.mean([l["win"] for l in first.values() if l["q"]==l["q"]]):.1f}%, '
              f'per$1 {f1v:+.3f}, total {f1t:+.1f}$, DD {f1dd:.1f}$, longest losing run {f1run}\n{"="*140}')
        print(f'  {"variant":26s}{"cands":>7}{"fill%":>7}{"win%":>7}{"2nd$1":>8}{"2nd$":>9}'
              f'{"CANDLE$":>10}{"vs 1st":>9}{"DD$":>8}{"run":>5}{"H1":>8}{"H2":>8}')
        for v, lab in (('A', 'A either side'), ('B', 'B opposite only (reversal)'), ('C', 'C same side only (add)')):
            S2 = {e: l for e, l in second[v].items() if l is not None}
            if not S2: print(f'  {lab:26s}{0:>7}  (none)'); continue
            legs = list(S2.values())
            v2, t2, dd2, run2 = stats(legs)
            nf2 = sum(1 for l in legs if l['q'] == l['q'])
            both = [l for e in S2 for l in (first[e], S2[e])]
            bv, bt, bdd, brun = stats(both)
            only1 = stats([first[e] for e in S2])[1]
            srt = sorted([l for l in legs if l['q'] == l['q']], key=lambda l: l['t'])
            h = len(srt) // 2
            h1 = stats(srt[:h])[0]; h2 = stats(srt[h:])[0]
            print(f'  {lab:26s}{len(S2):>7}{100*nf2/len(S2):>6.1f}%'
                  f'{(100*np.mean([l["win"] for l in legs if l["q"]==l["q"]]) if nf2 else float("nan")):>6.1f}%'
                  f'{v2:>+8.3f}{t2:>+9.1f}{bt:>+10.1f}{bt-only1:>+9.1f}{bdd:>8.1f}{brun:>5}'
                  f'{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
                  + ('  *n<60' if nf2 < MIN_CELL else ''))
        print(f'\n  per-day CANDLE $ (both legs) minus first-only, by variant:')
        print(f'    {"variant":26s}' + ''.join(f'{d:>12}' for d in days))
        for v, lab in (('A', 'A either'), ('B', 'B opposite'), ('C', 'C same')):
            S2 = {e: l for e, l in second[v].items() if l is not None}
            row = f'    {lab:26s}'
            for d in days:
                es = [e for e in S2 if first[e]['day'] == d]
                if not es: row += f'{"-":>12}'; continue
                gain = sum(pnl(S2[e]) for e in es)
                row += f'{gain:>+12.1f}'
            print(row)
        print(f'\n  2nd fire SPLIT by FIRST-fire second (rows) x 2nd-fire second (cols), variant B (reversal):')
        S2 = {e: l for e, l in second['B'].items() if l is not None}
        print(f'    {"1st sec":10s}' + ''.join(f'{f"2nd {lo}-{hi}":>20}' for lo, hi in
                                               ((15, 120), (120, 200), (200, 241))))
        for flo, fhi in ((15, 120), (120, 200), (200, 241)):
            row = f'    {f"{flo}-{fhi}":10s}'
            for lo, hi in ((15, 120), (120, 200), (200, 241)):
                s = [S2[e] for e in S2 if flo <= first[e]['sec'] < fhi and lo <= S2[e]['sec'] < hi]
                nf = sum(1 for l in s if l['q'] == l['q'])
                row += f'{(f"{stats(s)[0]:+.3f} ({nf}/{len(s)})" if s else "-"):>20}'
            print(row)

        print(f'\n  WHERE THE FIRST FIRE LOST - did a qualifying OPPOSITE-side pass appear later?')
        lost = [e for e in first if first[e]['q'] == first[e]['q'] and first[e]['win'] == 0]
        won = [e for e in first if first[e]['q'] == first[e]['q'] and first[e]['win'] == 1]
        for lab, es in (('first fire FILLED and LOST', lost), ('first fire FILLED and WON', won)):
            hit = [e for e in es if second['B'].get(e) is not None]
            if not es: continue
            asks = [second['B'][e]['ask'] for e in hit]
            secs = [second['B'][e]['sec'] for e in hit]
            fills = sum(1 for e in hit if second['B'][e]['q'] == second['B'][e]['q'])
            print(f'    {lab:28s} n {len(es):>4}  opposite pass appeared on {len(hit):>4} '
                  f'({100*len(hit)/len(es):>5.1f}%)  its ask p10/p50/p90 '
                  f'{np.percentile(asks,10):.2f}/{np.percentile(asks,50):.2f}/{np.percentile(asks,90):.2f}'
                  f'  sec p50 {np.median(secs):.0f}  it would fill {100*fills/max(len(hit),1):.1f}%'
                  if hit else f'    {lab:28s} n {len(es):>4}  no opposite pass')
        print()
