#!/usr/bin/env python3
"""OWNER, 09-28 12:5x: "What's the profit and accuracy in trades taken after 200 s in the candle, and what's
the worst drawdown?" READ-ONLY. Master OFF, nothing live.

Two independent reads of the same question, side by side, because they disagree and the owner should see both:

  A. the stable_ef fire set - 10 days rebuilt from the engine's own diagnostics pnl rows, both profiles,
     venue-graded. Paper = the ask actually read at the fire. London = the lane_exec_sim model,
     P(fill|win) 54.1%, P(fill|lose) 65.0%, slippage p10/p50/p90 -1/+2/+11c, averaged over 400 runs.
  B. the EF_FIRE_TIME decide_log baseline - 5 days, fixed15's first qualifying pass per candle, ef_persist's
     FAK simulator. That read gave sec 180-240 as -0.139, so it is the honest counterweight to A.

Drawdown is the worst peak-to-trough of the CUMULATIVE $ curve in time order, at $10 a fire. For London it is
the mean of that statistic across the 400 fill simulations, since which fires land is itself random there.
"""
import sys, collections, statistics as st, random, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
import stable_ef as S

CUTS = [('ALL', lambda r: True), ('sec < 200', lambda r: r['sec'] < 200),
        ('sec >= 180', lambda r: r['sec'] >= 180), ('sec >= 200', lambda r: r['sec'] >= 200),
        ('sec >= 220', lambda r: r['sec'] >= 220)]
MIN_CELL = 60


def streak(pnl):
    w = c = 0
    for x in pnl:
        c = c + 1 if x < 0 else 0
        w = max(w, c)
    return w


def london_curve(rows, stake=10.0, runs=400, seed=17):
    rng = random.Random(seed); tot = []; spent = []; mdds = []
    for _ in range(runs):
        t = s = 0.; cum = peak = mdd = 0.
        for r in rows:
            if rng.random() > (0.541 if r['win'] else 0.650): continue
            px = min(0.99, max(0.01, r['ask'] + S.slip(rng))); sh = stake / px
            fee = S.RATE * sh * px * (1 - px); s += stake + fee
            x = (sh if r['win'] else 0) - stake - fee
            t += x; cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        tot.append(t); spent.append(s); mdds.append(mdd)
    return (np.mean(tot) / max(1e-9, np.mean(spent))), float(np.mean(tot)), float(np.mean(mdds))


HDR = (f'  {"cut":12s}{"n":>5}{"win%":>7}|{"paper$1":>9}{"paper$":>9}{"pDD$":>8}|'
       f'{"LON$1":>8}{"LON$":>9}{"lonDD$":>8}|{"lose-run":>9}{"days+":>7}')


def emit(rows, lab):
    print(f'\n  --- {lab} ---')
    print(HDR)
    for name, fn in CUTS:
        sub = sorted([r for r in rows if fn(r)], key=lambda r: r['ts'])
        if not sub:
            print(f'  {name:12s}{0:>5}   (none)'); continue
        c = S.curve(sub, [10.0] * len(sub))
        l1, lt, ldd = london_curve(sub)
        print(f'  {name:12s}{len(sub):>5}{100*np.mean([r["win"] for r in sub]):>6.1f}%|'
              f'{c["pnl"]/max(c["spent"],1e-9):>+9.3f}{c["pnl"]:>+9.1f}{c["mdd"]:>8.1f}|'
              f'{l1:>+8.3f}{lt:>+9.1f}{ldd:>8.1f}|{streak(c["seq"]):>9}'
              f'{f"{c[chr(112)+chr(111)+chr(115)+chr(95)+chr(100)+chr(97)+chr(121)+chr(115)]}/{c[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}'
              + ('  *n<60' if len(sub) < MIN_CELL else ''))


if __name__ == '__main__':
    rows = S.load()
    print(f'A. stable_ef fire set: {len(rows)} fires, {len({r["day"] for r in rows})} days, venue-graded')
    for arm in ('FIXED', 'RAW'):
        emit([r for r in rows if r['arm'] == arm], f'A / {arm}')

    # ---------- B: the decide_log baseline, fixed15 first qualifying pass, ef_persist FAK ----------
    import math
    from decimal import Decimal, ROUND_CEILING
    from ef_persist import load as pload, fill as pfill, fire_at_k, qual_fix, per1 as pper1, cost as pcost
    cand, _ = pload()
    base = []
    for ep, rs in cand.items():
        r = fire_at_k(rs, qual_fix, 1)
        if r is None: continue
        q = pfill(r)
        base.append(dict(sec=r['sec'], win=r['win'], q=q, ts=r['t'], day=r['day']))
    print(f'\nB. EF_FIRE_TIME decide_log baseline (fixed15, ef_persist FAK): {len(base)} fires, '
          f'{len({b["day"] for b in base})} days')
    print(f'\n  --- B / fixed15, SIM FILLS ONLY (a no-fill is not a trade) ---')
    print(f'  {"cut":12s}{"fires":>6}{"fills":>6}{"win%":>7}{"per$1":>9}{"total$":>9}{"DD$":>8}'
          f'{"lose-run":>9}{"days+":>7}')
    for name, fn in CUTS:
        sub = sorted([b for b in base if fn(b)], key=lambda b: b['ts'])
        fl = [b for b in sub if b['q'] == b['q'] and b['q'] is not None]
        if not fl:
            print(f'  {name:12s}{len(sub):>6}{0:>6}   (no fills)'); continue
        pnl = [10.0 * pper1(b['win'], b['q']) for b in fl]
        cum = peak = mdd = 0.
        for x in pnl:
            cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        den = sum(10.0 * pcost(b['q']) for b in fl)
        day = collections.defaultdict(float)
        for b, x in zip(fl, pnl): day[b['day']] += x
        print(f'  {name:12s}{len(sub):>6}{len(fl):>6}{100*np.mean([b["win"] for b in fl]):>6.1f}%'
              f'{cum/max(den,1e-9):>+9.3f}{cum:>+9.1f}{mdd:>8.1f}{streak(pnl):>9}'
              f'{f"{sum(1 for v in day.values() if v>0)}/{len(day)}":>7}'
              + ('  *n<60' if len(fl) < MIN_CELL else ''))
