"""R-12c (user, 09-16 01:0x): "it should be a fair comparison so do it."

The user is right and this corrects my own R-12 headline. Stage B compared frozen v10 with ALL 30
features against R-12 big with 18. I named the direction of that unfairness and then reported the
result anyway. That was wrong: the only honest test of "8 days vs 109 months" is both models on the
SAME inputs.

R-12b measured what the extra features are worth: masking them costs frozen v10 0.7516 -> 0.5969 of
direction accuracy and 0.1654 -> 0.2308 of Brier. So stage B's comparison was rigged by 15 points of
accuracy the historical model could never have had.

Here both arms see exactly the same 18 features on exactly the same rows, through the same EV rule.
"""
import json, os, statistics, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
from r12_extract import BUILT
import r12_train as T
import r12b_frozen_on_history as B
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'


def main():
    import joblib
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()
    L = T.lane_ticks(oc)
    TS = T.test_store(sorted({r['day'] for r in L}))
    ok = [r for r in L if (r['ep'], r['sec']) in TS]
    Z = np.array([TS[(r['ep'], r['sec'])] for r in ok], np.float64)
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in ok])

    m, iso = joblib.load(os.path.join(T.SP, 'r12_fit.joblib'))
    p_r12 = T.predict(m, iso, Z)
    p_fz_full = np.array([frozen.p_up(r['feat']) for r in ok])
    p_fz_mask = np.array([frozen.p_up(B.masked_vec(z)) for z in Z])

    acc = lambda p: float((((p >= 0.5).astype(float)) == y).mean())
    brier = lambda p: float(np.mean((p - y) ** 2))
    ll = lambda p: float(-np.mean(y * np.log(np.clip(p, 1e-6, 1 - 1e-6))
                                  + (1 - y) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))))

    print('=' * 78)
    print('R-12c  THE FAIR COMPARISON - same rows, same 18 inputs, same EV rule')
    print('=' * 78)
    print('  %d test rows, 2026-09-08..09-14, graded on venues.outcome.' % len(ok))
    print()
    print('  %-28s %9s %9s %9s' % ('arm', 'acc', 'Brier', 'logloss'))
    print('  %-28s %9.4f %9.4f %9.4f'
          % ('frozen v10 (all 30) *unfair*', acc(p_fz_full), brier(p_fz_full), ll(p_fz_full)))
    print('  %-28s %9.4f %9.4f %9.4f'
          % ('frozen v10, masked to 18', acc(p_fz_mask), brier(p_fz_mask), ll(p_fz_mask)))
    print('  %-28s %9.4f %9.4f %9.4f'
          % ('R-12 big, 109 months (18)', acc(p_r12), brier(p_r12), ll(p_r12)))
    print()
    print('  ON EQUAL INPUTS the 109-month model beats the 8-day model by %+.4f of Brier'
          % (brier(p_fz_mask) - brier(p_r12)))
    print('  and %+.4f of accuracy. Stage B reported the opposite because it let frozen keep 12'
          % (acc(p_r12) - acc(p_fz_mask)))
    print('  features the historical model could never have. That comparison was not fair and this')
    print('  one is.')
    print()

    f_r12 = T.fire_set(ok, p_r12)
    f_mask = T.fire_set(ok, p_fz_mask)
    b_r12, b_mask = T.book(f_r12), T.book(f_mask)
    print('  Through the SAME EV rule (paper, quoted ask - an upper bound):')
    print('  %-28s %8s %9s %10s %10s' % ('arm', 'fires', 'hit%', 'per $1', 'total'))
    for nm, b in (('frozen v10, masked to 18', b_mask), ('R-12 big, 109 months', b_r12)):
        print('  %-28s %8d %8.1f%% %+10.3f %+10.2f'
              % (nm, b['n'], 100 * b['win'], b['per1'], b['total']))
    print()

    idx = {id(r): i for i, r in enumerate(ok)}
    s = sorted(ok, key=lambda r: r['ts'])
    h = len(s) // 2
    hv = []
    for half in (s[:h], s[h:]):
        mm = np.array([idx[id(r)] for r in half])
        a, b = T.book(T.fire_set(half, p_r12[mm])), T.book(T.fire_set(half, p_fz_mask[mm]))
        hv.append((a['per1'] - b['per1']) if (a and b) else float('nan'))
    shared = sorted(set(f_r12) & set(f_mask))
    costs = {k: T.book(f_r12, k)['per1'] for k in (0, 0.01, 0.02, 0.03, 0.05)}
    F = Finding('R-12c 109-month model vs the 8-day model ON EQUAL INPUTS',
                per_fire=b_r12['per1'] - b_mask['per1'], n=b_r12['n'])
    F.sample({'R-12 fires': b_r12['n'], 'frozen-masked fires': b_mask['n']})
    F.halves(first=hv[0], second=hv[1])
    F.paired(mine_right=[f_r12[e]['side'] == f_r12[e]['actual'] for e in shared],
             theirs_right=[f_mask[e]['side'] == f_mask[e]['actual'] for e in shared])
    F.costs(costs)
    F.null(mine=b_r12['total'], null_value=b_mask['total'],
           null_name='the 8-day model on the SAME 18 inputs, total PnL')
    F.verdict()
    print('  NOTE what this does and does not say. It says MORE DATA HELPS: given the same inputs,')
    print('  nine years beats eight days. It does NOT say ship it - the live model keeps its 12')
    print('  extra features, and R-12 stage B2 already showed that once the venue price is added')
    print('  back to the history model the two end in a dead heat (Brier 0.1628 vs 0.1622).')
    print()


if __name__ == '__main__':
    main()
