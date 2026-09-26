"""R-12 step 4: the venue stage for the GBM history model, as V's own brief requires.

Step 2 found lgbm beats the stage-1 logistic on OOS logloss in 8 of 8 test years (mean +0.0171,
AUC +0.0111). V's brief: "if no gain, say so and close honestly; if gain, venue stage + paired test
+ verify.py". There is a gain, so this runs it.

It also reopens something step 3 closed too early: step 3 measured the history contribution using
the LOGISTIC history model. A better history model deserves the same test before it is called dead.

Same four-arm harness as step 3, walk-forward BY DAY, but with p_hist from the GBM.
"""
import os, sys, time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding
from btc_model_v10 import FEATURES, Model
import r12_train as T
import r12s2_lgbm as S2
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'


def main():
    import joblib, lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import GroupKFold

    oc = R8.oracle()
    L = T.lane_ticks(oc)
    TS = T.test_store(sorted({r['day'] for r in L}))
    ok = sorted([r for r in L if (r['ep'], r['sec']) in TS], key=lambda r: r['ts'])
    cutoff = min(r['ep'] for r in L)

    cache = os.path.join(T.SP, 'r12_gbm.joblib')
    if os.path.exists(cache):
        gb, iso, cuts = joblib.load(cache)
        print('  loaded cached GBM fit', flush=True)
    else:
        X, K, yr = S2.load_all()
        m = K[:, 0] < cutoff
        X, K, yr = X[m], K[m], yr[m]
        y = K[:, 2].astype(float)
        cuts = list(np.quantile(X[:, S2.RET], [1 / 3, 2 / 3]))
        Xr = S2.add_regime(X, cuts)
        print('  fitting GBM on %d history rows (all strictly before the test window)...' % len(Xr),
              flush=True)
        mk = lambda: lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=15,
                                        min_child_samples=60, subsample=0.8, subsample_freq=1,
                                        colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
        inner = np.full(len(y), np.nan)
        grp = yr.astype(str)
        for itr, ite in GroupKFold(n_splits=4).split(Xr, y, grp):
            inner[ite] = mk().fit(Xr[itr], y[itr]).predict_proba(Xr[ite])[:, 1]
        iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip').fit(inner, y)
        gb = mk().fit(Xr, y)
        joblib.dump((gb, iso, cuts), cache)

    Z = np.array([TS[(r['ep'], r['sec'])] for r in ok], np.float64)
    p_gbm = iso.predict(gb.predict_proba(S2.add_regime(Z, cuts))[:, 1])
    p_log = T.predict(*joblib.load(os.path.join(T.SP, 'r12_fit.joblib')), Z)

    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in ok])
    day = np.array([r['day'] for r in ok])
    days = sorted(set(day.tolist()))
    X30 = np.nan_to_num(np.array([[r['feat'][k] for k in FEATURES] for r in ok], np.float64))

    print('=' * 78)
    print('R-12 step 4  GBM history + the venue stage (V: "if gain, venue stage + paired test")')
    print('=' * 78)
    br = lambda p, yy: float(np.mean((p - yy) ** 2))
    print('  history models ALONE on the test window: logistic Brier %.4f, GBM Brier %.4f'
          % (br(p_log, y), br(p_gbm, y)))
    print()

    preds = {k: np.full(len(ok), np.nan) for k in ('base', 'gbm')}
    for i, d in enumerate(days):
        if i < 2:
            continue
        tr, te = day < d, day == d
        if tr.sum() < 500 or te.sum() < 20:
            continue
        for key, X in (('base', X30), ('gbm', np.column_stack([X30, p_gbm]))):
            mm, ii = T.fit(X[tr], y[tr], day[tr])
            preds[key][te] = T.predict(mm, ii, X[te])
    msk = ~np.isnan(preds['base'])
    sub = [r for r, k in zip(ok, msk) if k]
    yy = y[msk]
    frozen = Model(MODEL_JSON)
    arms = {'frozen v10 (live)': np.array([frozen.p_up(r['feat']) for r in sub]),
            '8 days, 30 feats': preds['base'][msk],
            '8 days, 30 + GBM hist': preds['gbm'][msk]}
    print('  %-24s %8s %9s %8s %9s %10s %10s'
          % ('arm', 'acc', 'Brier', 'fires', 'hit%', 'per $1', 'total'))
    res = {}
    for nm, p in arms.items():
        b = T.book(T.fire_set(sub, p))
        res[nm] = (b, p)
        print('  %-24s %8.4f %9.4f %8d %8.1f%% %+10.3f %+10.2f'
              % (nm, float((((p >= 0.5).astype(float)) == yy).mean()), br(p, yy),
                 b['n'], 100 * b['win'], b['per1'], b['total']))
    print()
    print('  GBM history on top of all 30 features: Brier %+.4f vs without it'
          % (br(arms['8 days, 30 + GBM hist'], yy) - br(arms['8 days, 30 feats'], yy)))
    print()

    a, b = res['8 days, 30 + GBM hist'], res['8 days, 30 feats']
    fa, fb = T.fire_set(sub, a[1]), T.fire_set(sub, b[1])
    shared = sorted(set(fa) & set(fb))
    idx = {id(r): i for i, r in enumerate(sub)}
    h = len(sub) // 2
    hv = []
    for half in (sub[:h], sub[h:]):
        mm = np.array([idx[id(r)] for r in half])
        x, z = T.book(T.fire_set(half, a[1][mm])), T.book(T.fire_set(half, b[1][mm]))
        hv.append((x['per1'] - z['per1']) if (x and z) else float('nan'))
    F = Finding('R-12s4 GBM history on top of all 30 features',
                per_fire=a[0]['per1'] - b[0]['per1'], n=a[0]['n'])
    F.sample({'fires': a[0]['n']})
    F.halves(first=hv[0], second=hv[1])
    F.paired(mine_right=[fa[e]['side'] == fa[e]['actual'] for e in shared],
             theirs_right=[fb[e]['side'] == fb[e]['actual'] for e in shared])
    F.costs({k: T.book(fa, k)['per1'] for k in (0, 0.01, 0.02, 0.03, 0.05)})
    F.null(mine=a[0]['total'], null_value=b[0]['total'],
           null_name='the same 8 days WITHOUT the GBM history input')
    F.verdict()


if __name__ == '__main__':
    main()
