#!/usr/bin/env python3
"""V 09-28 14:4x: does the '(c) veto' reading give B more history on the 10 stable_ef days? READ-ONLY.

(c) showed that on the 5 per-pass days the start-second bar is pure composition: of 102 candles that fire
and fill under both S0=0 and S0=60, 88 are the SAME pass and none differ on outcome. So restricting the
engine's own fire list to sec >= S is close to the rule, and the 10-day stable_ef set can be read that way.

CLOSE TO, NOT EQUAL TO, and the gap is measurable rather than rhetorical. A slice can only DROP fires. The
rule can also ADD one: when a candle's first qualifying pass is early, the slice loses that candle
entirely, but the rule fires at the next qualifying pass later in the same candle. On the 5 per-pass days
the rule has 121 fills where the slice has 102 - so the slice understates the rule by 19 fills, and every
number below is a LOWER bound on the rule's activity. This is the same survivorship distinction that the
fires-after-220 test turned on, in the opposite direction.

Paper = fill at the quoted ask. London = lane_exec_sim: P(fill|win) 0.541, P(fill|lose) 0.650, slippage
p10/p50/p90 -1/+2/+11c, averaged over the sim runs, with the drawdown taken PER RUN and then averaged so
it is a drawdown someone could actually have lived through rather than a drawdown of the average.
"""
import sys, os, collections, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stable_ef as S
from ef2_model import per1

STAKE = 10.0
CUTS = (0, 30, 45, 60, 75)


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return cum, mdd, worst


def paper(rows):
    seq = [STAKE * per1(r['win'], r['ask']) for r in rows]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float)
    for r, x in zip(rows, seq): byd[r['day']] += x
    h = len(rows) // 2
    W = lambda s: (sum(per1(r['win'], r['ask']) * r['ask'] for r in s) / sum(r['ask'] for r in s)) if s else float('nan')
    return dict(tot=tot, mdd=mdd, worst=worst, byd=dict(byd),
                pos=sum(1 for v in byd.values() if v > 0), days=len(byd),
                h1=W(rows[:h]), h2=W(rows[h:]))


def london(rows, runs=400, seed=17):
    """Per-RUN drawdown, then averaged. Averaging the curves first would hide the real swings."""
    rng = random.Random(seed)
    T, D, R, P, N = [], [], [], [], []
    for _ in range(runs):
        seq = []; byd = collections.defaultdict(float)
        for r in rows:
            if rng.random() > (0.541 if r['win'] else 0.650): continue
            px = min(0.99, max(0.01, r['ask'] + S.slip(rng)))
            x = STAKE * per1(r['win'], px)
            seq.append(x); byd[r['day']] += x
        t, m, w = dd_run(seq)
        T.append(t); D.append(m); R.append(w); N.append(len(seq))
        P.append(sum(1 for v in byd.values() if v > 0))
    return dict(tot=float(np.mean(T)), mdd=float(np.mean(D)), worst=float(np.mean(R)),
                pos=float(np.mean(P)), n=float(np.mean(N)))


HDR = (f'  {"cell":22s}|{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"f/day":>7}{"days+":>7}{"run":>5}{"H1":>8}{"H2":>8}'
       f' |{"L $tot":>8}{"L DD":>7}{"L P/DD":>7}{"L days+":>8}{"L run":>6}')

if __name__ == '__main__':
    allrows = S.load()
    for arm in ('RAW', 'FIXED'):
        rows = [r for r in allrows if r['arm'] == arm]
        days = sorted({r['day'] for r in rows})
        print(f'\n{"="*124}\n{arm}  -  {len(rows)} engine fires over {len(days)} days {days}\n{"="*124}')
        print(HDR)
        for S0 in CUTS:
            sel = [r for r in rows if r['sec'] >= S0]
            if not sel: continue
            p = paper(sel); l = london(sel)
            print(f'  {arm} sec>={S0:<14d}|{p["tot"]:>+8.1f}{p["mdd"]:>7.1f}'
                  f'{(p["tot"]/p["mdd"] if p["mdd"]>0 else 99.9):>7.2f}{len(sel)/max(len(days),1):>7.1f}'
                  f'{f"{p[chr(112)+chr(111)+chr(115)]}/{p[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}{p["worst"]:>5}'
                  f'{p["h1"]:>+8.3f}{p["h2"]:>+8.3f} |{l["tot"]:>+8.1f}{l["mdd"]:>7.1f}'
                  f'{(l["tot"]/l["mdd"] if l["mdd"]>0 else 99.9):>7.2f}{l["pos"]:>7.1f}/{len(days)}{l["worst"]:>6.1f}')
        print('  ' + '-' * 122)
        for S0 in (30, 45, 60, 75):
            dr = [r for r in rows if r['sec'] < S0]
            if not dr: continue
            d = paper(dr)
            print(f'    dropped sec<{S0:<3d}: n {len(dr):4d}  win% {100*np.mean([r["win"] for r in dr]):5.1f}  '
                  f'paper $ {d["tot"]:+8.1f}  mean sec {np.mean([r["sec"] for r in dr]):5.1f}  '
                  f'mean ask {np.mean([r["ask"] for r in dr]):.3f}')
        print('  ' + '-' * 122)
        for S0 in (0, 60):
            sel = [r for r in rows if r['sec'] >= S0]
            p = paper(sel)
            print(f'    {arm} sec>={S0} per day $: ' + '  '.join(f'{d} {p["byd"].get(d, 0.0):+6.1f}' for d in days))

    # does the 5-day "two good days" pattern hold on 10?
    print(f'\n{"="*124}\nTHE QUESTION: does the two-good-days pattern hold or dissolve on 10 days?\n{"="*124}')
    for arm in ('RAW', 'FIXED'):
        rows = [r for r in allrows if r['arm'] == arm and r['sec'] >= 60]
        days = sorted({r['day'] for r in rows})
        p = paper(rows)
        v = [p['byd'].get(d, 0.0) for d in days]
        o = sorted(v, reverse=True)
        print(f'  {arm} sec>=60: total {sum(v):+.1f} over {len(days)} days, {p["pos"]}/{p["days"]} positive')
        print(f'    best two days {o[0]:+.1f} {o[1]:+.1f} = {o[0]+o[1]:+.1f}  '
              f'({100*(o[0]+o[1])/sum(v):.0f}% of the total)   rest {sum(o[2:]):+.1f}')
        print(f'    all days: ' + '  '.join(f'{d} {x:+.1f}' for d, x in zip(days, v)))
