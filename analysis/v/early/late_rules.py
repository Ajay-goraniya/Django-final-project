#!/usr/bin/env python3
"""Late-candle EF rules judged on the OWNER'S objective (V, 09-28): profit, small max drawdown, frequency.
Public data only: Binance 1 s spot features at second S, the price takers actually PAID for each side within 3 s of S (max, so
conservative), venue resolution (gamma). One fire per candle. $10 stake per fire, taker fee 0.07 p(1-p) per share.

Arms (full grid, no best cell):
  FAV    buy the venue favourite at the first S >= S0 whose favourite ask is inside [lo, hi]           - the null any EF must beat
  MODEL  walk-forward spot logistic p (fitted per S on days < k); fire at the first S >= S0 where p_side / cost >= 1 + m
  AGREE  MODEL, but only when the model's side IS the venue favourite (model and price agree)
Columns: n, fires/day, win%, per$1, $ total, worst drawdown $, profit/DD, % days positive, longest losing run, H1/H2 per$1.
usage: late_rules.py   (reads early_late_btc_*.json)"""
import os, glob, json, collections
import numpy as np
import early_spot_signal as E

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ['move', 'ret5', 'ret30', 'ret60', 'rv60', 'pos', 'prev1', 'prev2', 'hs', 'hc', 'mv_sec']
fee = lambda p: 0.07 * p * (1 - p)


def load():
    rows = []
    for fn in sorted(glob.glob(os.path.join(HERE, 'early_late_btc_*.json'))): rows += json.load(open(fn))
    return sorted({r['e']: r for r in rows}.values(), key=lambda r: r['e'])


def pnl10(ask, win):
    c = ask + fee(ask); sh = 10.0 / c
    return sh - 10.0 if win else -10.0


def stats(fires, ndays):
    """fires: list of (e, day, ask, win) in time order."""
    if not fires: return None
    fires = sorted(fires)
    p = np.array([pnl10(a, w) for _, _, a, w in fires]); cum = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]))
    run = best = 0
    for x in p:
        run = run + 1 if x < 0 else 0; best = max(best, run)
    byday = collections.defaultdict(float)
    for (e, d, a, w), x in zip(fires, p): byday[d] += x
    h = len(p) // 2
    per1 = lambda q: q.sum() / (10.0 * len(q)) if len(q) else float('nan')
    return dict(n=len(p), fpd=len(p) / ndays, win=100 * np.mean([w for *_, w in fires]), per1=per1(p), tot=float(cum[-1]), dd=dd,
                ratio=(float(cum[-1]) / dd if dd > 0 else float('inf')), pos=100 * np.mean([v > 0 for v in byday.values()]),
                run=best, h1=per1(p[:h]), h2=per1(p[h:]), ask=float(np.median([a for _, _, a, _ in fires])))


def line(name, s):
    if s is None: return f'  {name:34s}    0'
    flag = '  *n<60' if s['n'] < 60 else ''
    return (f"  {name:34s} {s['n']:5d} {s['fpd']:6.1f} {s['win']:5.1f}% {s['per1']:+7.3f} {s['tot']:+9.1f} {s['dd']:8.1f} {s['ratio']:6.2f} "
            f"{s['pos']:5.0f}% {s['run']:4d} {s['h1']:+7.3f} {s['h2']:+7.3f} {s['ask']:5.2f}{flag}")


def main():
    rows = load()
    S_ALL = sorted({int(k) for r in rows for k in r['s']})
    days = sorted({r['day'] for r in rows})
    print(f'candles {len(rows)}, days {len(days)}, seconds {S_ALL}. Model arms score days 2..{len(days)} (walk-forward); FAV scores all days.')
    # walk-forward spot model p per (candle, S)
    P = {}
    for S in S_ALL:
        K = str(S); rs = [r for r in rows if K in r['s']]
        X = np.array([[r['s'][K]['f'][k] for k in KEYS] for r in rs]); y = np.array([r['up'] for r in rs]).astype(int); d = np.array([r['day'] for r in rs])
        for k in days[1:]:
            tr, te = d < k, d == k
            if tr.sum() < 100 or te.sum() == 0: continue
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
            f = E.fit_logit((X[tr] - mu) / sd, y[tr]); pp = f((X[te] - mu) / sd)
            for r, v in zip([r for r, t in zip(rs, te) if t], pp): P[(r['e'], S)] = float(v)
    nd_all, nd_wf = len(days), len(days) - 1
    hdr = f"  {'arm':34s} {'n':>5s} {'/day':>6s} {'win%':>6s} {'per$1':>7s} {'$ tot':>9s} {'maxDD$':>8s} {'P/DD':>6s} {'days+':>6s} {'run':>4s} {'H1':>7s} {'H2':>7s} {'ask':>5s}"
    print('\n=== FAV: buy the venue favourite at the first S >= S0 with its ask in [lo, hi]')
    print(hdr)
    for S0 in (120, 180, 200, 220, 240, 260):
        for lo, hi in ((0.55, 0.70), (0.60, 0.80), (0.70, 0.90), (0.80, 0.95)):
            fires = []
            for r in rows:
                for S in S_ALL:
                    if S < S0 or str(S) not in r['s']: continue
                    q = r['s'][str(S)]; au, ad = q['ask_up'], q['ask_dn']
                    if au is None or ad is None: continue
                    up = au >= ad; a = au if up else ad
                    if lo <= a <= hi:
                        fires.append((r['e'], r['day'], a, r['up'] == up)); break
            print(line(f'S0 {S0:3d} ask {lo:.2f}-{hi:.2f}', stats(fires, nd_all)))
    for arm in ('MODEL', 'AGREE'):
        print(f'\n=== {arm}: walk-forward spot model, fire at first S >= S0 with p_side/cost >= 1+m' + (' and model side = venue favourite' if arm == 'AGREE' else ''))
        print(hdr)
        for S0 in (120, 180, 200, 220, 240):
            for m in (0.0, 0.02, 0.05, 0.10):
                fires = []
                for r in rows:
                    if r['day'] == days[0]: continue
                    for S in S_ALL:
                        if S < S0 or str(S) not in r['s'] or (r['e'], S) not in P: continue
                        q = r['s'][str(S)]; p = P[(r['e'], S)]; up = p >= 0.5; ps = p if up else 1 - p
                        a = q['ask_up'] if up else q['ask_dn']
                        if a is None or not (0.02 < a < 0.98): continue
                        if arm == 'AGREE':
                            o = q['ask_dn'] if up else q['ask_up']
                            if o is None or a < o: continue
                        if ps / (a + fee(a)) >= 1 + m:
                            fires.append((r['e'], r['day'], a, r['up'] == up)); break
                print(line(f'S0 {S0:3d} m {m:.2f}', stats(fires, nd_wf)))


if __name__ == '__main__':
    main()
