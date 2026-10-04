"""EF under the LIVE fire rule: ev >= threshold, NOT p >= ask + 0.06 + fee.

V (09-22 23:2x) is right that the engine fires on `ev >= threshold` and that `ev = p/cost - 1`;
sections (C) and (D) of EF_BRAIN.md used the wrong rule and are superseded here.

ONE CORRECTION TO THE SPEC, checked against the artifact rather than assumed. V wrote
`cost = ask + fee`. The stored `ev` in poly_pnl.trades does NOT match that (median |diff| 0.0030,
max 28.4). It matches `task_r8_taker_feature.ev_of` to a median of 3.7e-5 and a max of 4.1e-4:

    cost(q) = q / (1 - RATE*(1-q)),  RATE = 0.07   ->   ev = p/cost(ask) - 1

which expands to exactly V's form `p/cost - 1`; only the cost function differs. The stored ev's
minimum is 0.1512, consistent with 0.15 being the lowest regime threshold, so the rule reproduces.

Threshold: the row's OWN regime threshold from its rv60 (R8.threshold: 0.15 low / 0.25 mid / 0.25
high, edges 0.1668 / 0.3653), plus a fixed-threshold grid 0.15..0.35 reported whole, not picked.
Stake $3, fees = measured live Polymarket (1.67% of shares, winners AND losers), graded on
venues.outcome.
"""
import csv, os, sys, collections, datetime as dt
import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8

STAKE = 3.0
POLY_SHARE_FEE = 0.0167
GRID = [0.15, 0.20, 0.25, 0.30, 0.35]
CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ef_fires_1108.csv')


def per1(ask, won):
    return (1.0 / ask - 1.0 - POLY_SHARE_FEE / ask) if won else -1.0


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def load():
    out = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            out.append(dict(ts=int(r['ts']), ep=int(r['epoch']), sec=int(r['sec']),
                            side=r['side'], ask=float(r['ask']), p=float(r['p']),
                            p_cal=float(r['p_cal']), won=int(r['win']) == 1,
                            day=r['day'], rv60=float(r['rv60'])))
    out.sort(key=lambda r: r['ts'])
    for r in out:
        r['pnl'] = per1(r['ask'], r['won'])
    return out


def ev(p, ask):
    return R8.ev_of(p, ask)


def stat(rows):
    if not rows:
        return dict(n=0, w=0.0, per1=0.0, total=0.0, dd=0.0, neg=0, run=0)
    v = np.array([r['pnl'] for r in rows]) * STAKE
    eq = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    byday = collections.defaultdict(float)
    for r in rows:
        byday[r['day']] += r['pnl'] * STAKE
    run = mx = 0
    for r in rows:
        run = run + 1 if not r['won'] else 0
        mx = max(mx, run)
    return dict(n=len(rows), w=float(np.mean([r['won'] for r in rows])),
                per1=float(np.mean([r['pnl'] for r in rows])), total=float(v.sum()),
                dd=dd, neg=sum(1 for d in byday.values() if d < 0), run=mx, byday=dict(byday))


def fires(rows, pkey, thr=None):
    out = []
    for r in rows:
        t = R8.threshold(r['rv60']) if thr is None else thr
        if ev(r[pkey], r['ask']) >= t:
            out.append(r)
    return out


def loo_cal(rows):
    """Leave-one-day-out Platt, so the pair never sees the day it is read on."""
    days = sorted({r['day'] for r in rows})
    for d in days:
        tr = [r for r in rows if r['day'] != d]
        te = [r for r in rows if r['day'] == d]
        m = LogisticRegression(max_iter=1000).fit(
            logit(np.array([r['p'] for r in tr])).reshape(-1, 1),
            np.array([r['won'] for r in tr], float))
        a, b = float(m.coef_[0][0]), float(m.intercept_[0])
        for r in te:
            q = 1.0 / (1.0 + np.exp(-(a * logit(r['p']) + b)))
            r['p_loo'] = float(min(q, r['p']))
    return rows


def line(lab, s):
    print('  %-30s %5d %6.1f%% %+9.4f %+10.2f %9.2f %6d %5d%s'
          % (lab, s['n'], 100 * s['w'], s['per1'], s['total'], s['dd'], s['neg'], s['run'],
             '' if s['n'] >= MIN_CELL else '  INSUFFICIENT'))


def main():
    R = loo_cal(load())
    print('EF under the LIVE rule: ev >= threshold   (ev = p/cost-1, cost = ask/(1-0.07*(1-ask)))')
    print('  %d fires, %s -> %s, stake $%.0f' % (len(R), R[0]['day'], R[-1]['day'], STAKE))
    print('  %-30s %5s %6s %9s %10s %9s %6s %5s'
          % ('arm', 'n', 'W%', 'per$1', 'total$', 'maxDD$', 'negday', 'run'))

    print("  -- the row's OWN regime threshold (R8.threshold from rv60) --")
    for k, lab in (('p', 'raw p'), ('p_cal', 'calibrated (pooled a,b)'),
                   ('p_loo', 'calibrated (leave-1-day-out)')):
        line(lab, stat(fires(R, k)))

    print('\n  -- FIXED THRESHOLD GRID, reported whole, not picked --')
    for t in GRID:
        print('   threshold %.2f' % t)
        for k, lab in (('p', 'raw p'), ('p_cal', 'calibrated pooled'),
                       ('p_loo', 'calibrated LOO')):
            line('   ' + lab, stat(fires(R, k, thr=t)))

    print('\n  -- HOW MUCH DOES CALIBRATION ACTUALLY CHANGE UNDER THIS RULE? --')
    for t in [None] + GRID:
        a = {r['ep'] for r in fires(R, 'p', thr=t)}
        b = {r['ep'] for r in fires(R, 'p_cal', thr=t)}
        c = {r['ep'] for r in fires(R, 'p_loo', thr=t)}
        lab = "own regime" if t is None else ('%.2f' % t)
        print('   thr %-10s raw %4d -> pooled %4d (removes %3d, %.1f%%) | LOO %4d (removes %3d, %.1f%%)'
              % (lab, len(a), len(b), len(a - b), 100.0 * len(a - b) / max(1, len(a)),
                 len(c), len(a - c), 100.0 * len(a - c) / max(1, len(a))))

    print('\n  -- DAY BY DAY, own regime threshold --')
    days = sorted({r['day'] for r in R})
    print('  %-8s %12s %12s %12s' % ('day', 'raw $', 'pooled $', 'LOO $'))
    sr = stat(fires(R, 'p')); sp = stat(fires(R, 'p_cal')); sl = stat(fires(R, 'p_loo'))
    for d in days:
        print('  %-8s %+12.2f %+12.2f %+12.2f'
              % (d, sr['byday'].get(d, 0.0), sp['byday'].get(d, 0.0), sl['byday'].get(d, 0.0)))


if __name__ == '__main__':
    main()


def nulls():
    """The R-19 null under the live rule. Calibration removes ~92% of fires, so it is a heavy
    selection rule and must beat the trivial selector at the same fire count."""
    R = loo_cal(load())
    base = fires(R, 'p')
    print('\n  -- THE R-19 NULL at the same fire count, on the same rows --')
    print('  %-30s %5s %6s %9s %10s %9s %6s' % ('arm', 'n', 'W%', 'per$1', 'total$', 'maxDD$', 'negday'))
    line('raw p, own regime threshold', stat(base))
    for k, lab in (('p_cal', 'calibrated pooled'), ('p_loo', 'calibrated LOO')):
        arm = fires(R, k)
        n = len(arm)
        by_ev = sorted(base, key=lambda r: -ev(r['p'], r['ask']))[:n]
        by_cheap = sorted(base, key=lambda r: r['ask'])[:n]
        line(lab, stat(arm))
        line('  null: top-%d by raw ev' % n, stat(by_ev))
        line('  null: %d cheapest asks' % n, stat(by_cheap))

    print('\n  -- WHY CALIBRATION REMOVES SO MUCH (V measured 4%%, I measure 92%%) --')
    mp = np.mean([r['p'] for r in base]); mc = np.mean([r['p_cal'] for r in base])
    e0 = np.mean([ev(r['p'], r['ask']) for r in base])
    e1 = np.mean([ev(r['p_cal'], r['ask']) for r in base])
    print('   mean p %.4f -> p_cal %.4f (-%.1f%% relative)' % (mp, mc, 100 * (1 - mc / mp)))
    print('   mean ev %.4f -> %.4f. ev = p/cost-1, so a %.1f%% cut in p moves ev by about'
          % (e0, e1, 100 * (1 - mc / mp)))
    print('   %.3f at these prices -- larger than the 0.15-0.25 threshold band itself.' % (e0 - e1))
    print('   That is the mechanism; if the engine sees ~4%% removal its hook is not applying')
    print('   this pair to the ev input, or is clamped somewhere I cannot see from here.')


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'nulls':
    nulls()
