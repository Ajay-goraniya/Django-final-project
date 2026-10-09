"""R-12b (user, 09-16 00:5x): "did you test our live model with the same data?"

On the R-12 TEST WINDOW, yes - frozen v10 was scored on identical rows through the same EV rule,
which is what made the paired McNemar test possible. Over the 109 months of HISTORY, no. This runs
that, because it is the sharper question: does the model actually running on live money hold up
across every regime since 2017, or only across the 8 days it was fitted on?

Two honest constraints, both handled rather than ducked:

1. Frozen v10 needs 30 features; history supports 18. So over history it must run with the same 12
   masked. That is NOT the live model, so the masking cost is MEASURED FIRST on the logged window -
   where both versions can be run - and the historical numbers are read against that calibration.
2. There was no Polymarket before September, so there is no ask, no EV and no PnL over history.
   Only DIRECTION ACCURACY is measurable. Accuracy is not PnL; this reports accuracy and says so.
"""
import glob, json, os, statistics, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import MIN_CELL
from btc_model_v10 import FEATURES, Model
from r12_extract import BUILT
import r12_train as T
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
SP = T.SP


def masked_vec(row18):
    """An 18-vector in BUILT order -> a 30-dict in v10's order, the other 12 zeroed."""
    d = {f: 0.0 for f in FEATURES}
    for i, name in enumerate(BUILT):
        d[name] = float(row18[i])
    return d


def main():
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()

    # ---- 1. what does masking cost? Measured where BOTH versions can run.
    L = T.lane_ticks(oc)
    TS = T.test_store(sorted({r['day'] for r in L}))
    both = [r for r in L if (r['ep'], r['sec']) in TS]
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in both])
    p_full = np.array([frozen.p_up(r['feat']) for r in both])
    p_mask = np.array([frozen.p_up(masked_vec(TS[(r['ep'], r['sec'])])) for r in both])
    acc = lambda p: float((((p >= 0.5).astype(float)) == y).mean())
    brier = lambda p: float(np.mean((p - y) ** 2))
    print('=' * 78)
    print('R-12b  frozen v10 over ALL history - and first, what the masking costs')
    print('=' * 78)
    print('  On the logged window (%d rows) where BOTH versions can be run:' % len(both))
    print('    frozen v10, all 30 features : direction accuracy %.4f   Brier %.4f'
          % (acc(p_full), brier(p_full)))
    print('    frozen v10, 12 masked       : direction accuracy %.4f   Brier %.4f'
          % (acc(p_mask), brier(p_mask)))
    print('    masking costs %+.4f of accuracy and %+.4f of Brier. Every historical number below'
          % (acc(p_mask) - acc(p_full), brier(p_mask) - brier(p_full)))
    print('    is the MASKED model, so read it against that gap, not against the live one.')
    print()

    # ---- 2. the masked model over every month of history
    print('  Direction accuracy by YEAR, every year, nothing dropped:')
    print('    %-6s %10s %9s %9s %s' % ('year', 'rows', 'acc', 'base UP', 'delta'))
    by_year, by_month = {}, {}
    for f in sorted(glob.glob(os.path.join(SP, 'r12', '*.npz'))):
        d = np.load(f)
        X, K = d['X'], d['K']
        p = np.array([frozen.p_up(masked_vec(x)) for x in X])
        yy = K[:, 2].astype(float)
        mon = os.path.basename(f)[:-4]
        yr = mon[:4]
        pred = (p >= 0.5).astype(float)
        by_month[mon] = (len(yy), float((pred == yy).mean()), float(yy.mean()))
        a = by_year.setdefault(yr, [0, 0.0, 0.0])
        a[0] += len(yy)
        a[1] += float((pred == yy).sum())
        a[2] += float(yy.sum())
    tot_n = tot_hit = 0
    for yr in sorted(by_year):
        n, hit, up = by_year[yr]
        tot_n += n
        tot_hit += hit
        print('    %-6s %10d %8.4f %8.4f %+9.4f'
              % (yr, n, hit / n, up / n, hit / n - 0.5))
    print('    %-6s %10d %8.4f' % ('ALL', tot_n, tot_hit / tot_n))
    print()
    ms = sorted(by_month)
    above = sum(1 for m in ms if by_month[m][1] > 0.5)
    print('  months above 50%%: %d of %d' % (above, len(ms)))
    worst = sorted(ms, key=lambda m: by_month[m][1])[:5]
    best = sorted(ms, key=lambda m: -by_month[m][1])[:5]
    print('  worst 5 months: %s' % ', '.join('%s %.3f' % (m, by_month[m][1]) for m in worst))
    print('  best  5 months: %s' % ', '.join('%s %.3f' % (m, by_month[m][1]) for m in best))
    print()
    print('  ACCURACY IS NOT PnL. There was no Polymarket before September, so there is no ask, no')
    print('  EV and no PnL to compute here. A direction accuracy near 0.500 across nine years means')
    print('  the model has no standing directional edge outside the window it was fitted on.')
    print()


if __name__ == '__main__':
    main()
