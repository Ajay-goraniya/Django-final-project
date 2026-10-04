"""R-26 EV grid, arm (c) -- the walk-forward one. V runs frozen and (b); this is my half.

Same grid as analysis/v/ev_grid.py and ev_costs.py so the three tables read side by side:
thresholds 0.05..0.60, slippage 0..5 cents, per day as well as pooled, EVERY cell reported.

(c) can only be evaluated here because it is a different model per test day - week 1 plus the week-2
days before that day. A single pooled (c) json would leak the test day into its own fit.

WHAT THE GRID IS FOR, and it is not a better threshold. R-26 found that a median 0.0077 probability
shift - an isotonic fitted on 4 folds instead of 8, same coefficients - moved $36 across 1,033 fires.
So the question here is SHAPE: if total PnL is flat across 0.10-0.30 while the fire count swings
hard, the threshold is not a lever, and the sensitivity is a fragility to design out rather than a
dial to tune.
"""
import json, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

OUT = '/home/user/Django-final-project/analysis/h1/r26'
THR = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
SLIP = [0.0, 0.01, 0.02, 0.03, 0.05]
FEE = 0.07
cost = lambda q: q / (1 - FEE * (1 - q))


def ev_of(ps, ask):
    k = cost(ask)
    return ps * (1 / k - 1) - (1 - ps) if 0 < k < 1 else -9.0


def main():
    L = [r for r in T.lane_ticks(R8.oracle()) if r.get('ask') and r['feat'].get('p_venue') is not None]
    L.sort(key=lambda r: r['ts'])
    day = np.array([r['day'] for r in L])
    days = sorted(set(day.tolist()))
    p = np.full(len(L), np.nan)
    for d in days:
        f = os.path.join(OUT, 'model_c_%s.json' % d)
        if not os.path.exists(f):
            continue
        m = Model(f)
        te = np.where(day == d)[0]
        for i in te:
            p[i] = m.p_up(L[i]['feat'])
    ok = ~np.isnan(p)
    L = [r for r, k in zip(L, ok) if k]
    p, day = p[ok], day[ok]
    print('=' * 100)
    print('R-26 EV GRID, arm (c) week 1 + week 2, walk-forward by day')
    print('=' * 100)
    print('  %d ticks, %d candles, %d days, graded on venues.outcome' % (len(L), len({r['ep'] for r in L}), len(set(day.tolist()))))

    def fires(thr, slip):
        by = {}
        for r, q in zip(L, p):
            if r['ep'] in by:
                continue
            side = 'UP' if q >= 0.5 else 'DOWN'
            ps = q if side == 'UP' else 1 - q
            if ev_of(ps, r['ask']) >= thr:
                by[r['ep']] = (r, side, min(0.98, r['ask'] + slip))
        return by

    print('\n  TOTAL PnL, whole grid. rows = EV threshold, cols = cents paid over the quoted ask.')
    print('  %-7s %8s' % ('thr', 'fires') + ''.join('%11s' % ('+%.0fc' % (100 * s)) for s in SLIP))
    table = {}
    for t in THR:
        f0 = fires(t, 0.0)
        row = '  %-7.2f %8d' % (t, len(f0))
        for s in SLIP:
            f = fires(t, s)
            tot = sum(R8.per1(a, sd == r['actual']) for r, sd, a in f.values())
            table[(t, s)] = (len(f), tot)
            row += '%11s' % ('%+.2f' % tot)
        print(row)

    print('\n  PER $1, same grid')
    print('  %-7s' % 'thr' + ''.join('%11s' % ('+%.0fc' % (100 * s)) for s in SLIP))
    for t in THR:
        row = '  %-7.2f' % t
        for s in SLIP:
            n, tot = table[(t, s)]
            row += '%11s' % (('%+.3f' % (tot / n)) if n else '-')
        print(row)

    print('\n  THE SHAPE QUESTION: how flat is total PnL across 0.10-0.30, and how much does the')
    print('  fire count swing over the same range?')
    for s in SLIP:
        band = [table[(t, s)] for t in (0.10, 0.15, 0.20, 0.25, 0.30)]
        tots = [b[1] for b in band]; ns = [b[0] for b in band]
        print('    +%.0fc: total %+.2f .. %+.2f (spread %.2f, %.0f%% of max) | fires %d .. %d (%.0f%% swing)'
              % (100 * s, min(tots), max(tots), max(tots) - min(tots),
                 100 * (max(tots) - min(tots)) / max(abs(max(tots)), 1e-9),
                 min(ns), max(ns), 100 * (max(ns) - min(ns)) / max(ns)))

    print('\n  PER DAY at the live threshold band, 0 cents. Every day, never the best one.')
    print('  %-8s' % 'day' + ''.join('%14s' % ('thr %.2f' % t) for t in (0.10, 0.15, 0.20, 0.25, 0.30)))
    for d in sorted(set(day.tolist())):
        row = '  %-8s' % d[-5:]
        for t in (0.10, 0.15, 0.20, 0.25, 0.30):
            f = {e: v for e, v in fires(t, 0.0).items() if v[0]['day'] == d}
            if len(f) < 30:
                row += '%14s' % ('insuf(%d)' % len(f))
            else:
                tot = sum(R8.per1(a, sd == r['actual']) for r, sd, a in f.values())
                row += '%14s' % ('%+.2f(n%d)' % (tot, len(f)))
        print(row)


if __name__ == '__main__':
    main()
