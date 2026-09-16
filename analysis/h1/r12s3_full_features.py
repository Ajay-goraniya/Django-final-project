"""R-12 step 3 (user, 09-16 01:2x): "test this training model with the 8 days data we have,
it has all features."

Right, and it corrects something I said. v10's ORIGINAL training window (2026-08-29..09-06) is not
on this branch - I checked again for features.parquet and it is absent - but the LOGGED POLYMARKET
WINDOW is 8 days (09-08..09-15) and it DOES carry all 30 features in the engine's own `feat`.

So the question that has been circling this whole task is finally runnable:

    DOES THE 109-MONTH HISTORY ADD ANYTHING ONCE THE FULL FEATURE SET IS PRESENT?

Four arms, same rows, same EV rule, walk-forward BY DAY (train days < d, test day d):
  1. frozen v10                       - the live model, as shipped
  2. 8 days, all 30 features          - my pipeline given only what v10 had
  3. 8 days, 30 features + p_hist     - the same, plus the 109-month model's output as one input
  4. p_hist alone (18 features)       - the history model on its own, for reference

Arm 2 vs arm 1 is V's pipeline check in the only form the data allows: same days, same features,
same recipe - does my pipeline reproduce the live model within noise?
Arm 3 vs arm 2 is the user's question: history on top of everything else.
"""
import json, os, statistics, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'


def main():
    import joblib
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()
    L = T.lane_ticks(oc)
    TS = T.test_store(sorted({r['day'] for r in L}))
    ok = [r for r in L if (r['ep'], r['sec']) in TS]
    ok.sort(key=lambda r: r['ts'])
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in ok])
    day = np.array([r['day'] for r in ok])
    days = sorted(set(day.tolist()))

    m, iso = joblib.load(os.path.join(T.SP, 'r12_fit.joblib'))
    p_hist = T.predict(m, iso, np.array([TS[(r['ep'], r['sec'])] for r in ok], np.float64))
    X30 = np.nan_to_num(np.array([[r['feat'][k] for k in FEATURES] for r in ok], np.float64))
    X31 = np.column_stack([X30, p_hist])

    print('=' * 78)
    print('R-12 step 3  does the 109-month history add anything when ALL 30 features are present?')
    print('=' * 78)
    print('  %d rows, %d days (%s..%s), all 30 features from the engine\'s own feat.'
          % (len(ok), len(days), days[0], days[-1]))
    print('  v10\'s ORIGINAL training days (08-29..09-06) are NOT on this branch - no')
    print('  features.parquet - so this is the only 8-day all-feature window available.')
    print('  Walk-forward BY DAY: train on days < d, test on d. Nothing in-sample.')
    print()

    preds = {k: np.full(len(ok), np.nan) for k in ('d8_30', 'd8_31')}
    tested = []
    for i, d in enumerate(days):
        if i < 2:
            continue
        tr, te = day < d, day == d
        if tr.sum() < 500 or te.sum() < 20:
            continue
        for key, X in (('d8_30', X30), ('d8_31', X31)):
            mm, ii = T.fit(X[tr], y[tr], day[tr])
            preds[key][te] = T.predict(mm, ii, X[te])
        tested.append(d)
    msk = ~np.isnan(preds['d8_30'])
    sub = [r for r, k in zip(ok, msk) if k]
    yy = y[msk]
    print('  tested days: %s  (%d rows)' % (', '.join(tested), int(msk.sum())))
    print()

    arms = {
        'frozen v10 (live)': np.array([frozen.p_up(r['feat']) for r in sub]),
        '8 days, 30 feats': preds['d8_30'][msk],
        '8 days, 30 + p_hist': preds['d8_31'][msk],
        'p_hist alone (18)': p_hist[msk],
    }
    acc = lambda p: float((((p >= 0.5).astype(float)) == yy).mean())
    br = lambda p: float(np.mean((p - yy) ** 2))
    ll = lambda p: float(-np.mean(yy * np.log(np.clip(p, 1e-6, 1 - 1e-6))
                                  + (1 - yy) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))))
    print('  %-22s %8s %9s %9s %8s %9s %10s %10s'
          % ('arm', 'acc', 'Brier', 'logloss', 'fires', 'hit%', 'per $1', 'total'))
    res = {}
    for nm, p in arms.items():
        b = T.book(T.fire_set(sub, p))
        res[nm] = (b, p)
        print('  %-22s %8.4f %9.4f %9.4f %8d %8.1f%% %+10.3f %+10.2f'
              % (nm, acc(p), br(p), ll(p), b['n'], 100 * b['win'], b['per1'], b['total']))
    print()
    print('  PIPELINE CHECK (arm 2 vs arm 1): does my recipe on 8 days reproduce the live model?')
    print('    Brier %.4f vs %.4f, difference %+.4f'
          % (br(arms['8 days, 30 feats']), br(arms['frozen v10 (live)']),
             br(arms['8 days, 30 feats']) - br(arms['frozen v10 (live)'])))
    print('  THE USER\'S QUESTION (arm 3 vs arm 2): does the 109-month history add anything?')
    print('    Brier %.4f vs %.4f, difference %+.4f'
          % (br(arms['8 days, 30 + p_hist']), br(arms['8 days, 30 feats']),
             br(arms['8 days, 30 + p_hist']) - br(arms['8 days, 30 feats'])))
    print()

    a, b = res['8 days, 30 + p_hist'], res['8 days, 30 feats']
    fa, fb = T.fire_set(sub, a[1]), T.fire_set(sub, b[1])
    shared = sorted(set(fa) & set(fb))
    idx = {id(r): i for i, r in enumerate(sub)}
    h = len(sub) // 2
    hv = []
    for half in (sub[:h], sub[h:]):
        mm = np.array([idx[id(r)] for r in half])
        x, z = T.book(T.fire_set(half, a[1][mm])), T.book(T.fire_set(half, b[1][mm]))
        hv.append((x['per1'] - z['per1']) if (x and z) else float('nan'))
    F = Finding('R-12s3 history ON TOP of all 30 features', per_fire=a[0]['per1'] - b[0]['per1'],
                n=a[0]['n'])
    F.sample({'fires': a[0]['n']})
    F.halves(first=hv[0], second=hv[1])
    F.paired(mine_right=[fa[e]['side'] == fa[e]['actual'] for e in shared],
             theirs_right=[fb[e]['side'] == fb[e]['actual'] for e in shared])
    F.costs({k: T.book(fa, k)['per1'] for k in (0, 0.01, 0.02, 0.03, 0.05)})
    F.null(mine=a[0]['total'], null_value=b[0]['total'],
           null_name='the same 8 days WITHOUT the history input, total PnL')
    F.verdict()


if __name__ == '__main__':
    main()
