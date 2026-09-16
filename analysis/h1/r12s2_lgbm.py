"""R-12 step 2 (V, 09-15 23:5x): lightgbm on the 4.75M store, walk-forward BY YEAR.

Context V did not have when this was written: R-13 (00:0x) showed the LIVE model's direction call is
statistically identical to reading the venue price. That does NOT make this redundant - the
historical stage-1 model has no venue input at all, so "can a stronger learner predict BTC direction
from price history alone?" is still open, and R-12 B2 only tested the LOGISTIC history model against
the venue stage. A materially better history model might not end in a dead heat.

Walk-forward BY YEAR: train on every year strictly before Y, test on Y. Nothing in-sample.

"Explicit regime inputs" are added as OBSERVABLE regime state - the rv60 bucket and the ret60
tercile - NOT calendar era. A year or era feature would be out of range in every test fold by
construction, which is a leak dressed as a feature.
"""
import glob, os, sys, time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r12_extract import BUILT
import r12_train as T

STORE = os.path.join(T.SP, 'r12')
RV = BUILT.index('rv60')
RET = BUILT.index('ret60')


def load_all():
    Xs, Ks = [], []
    for f in sorted(glob.glob(os.path.join(STORE, '*.npz'))):
        d = np.load(f)
        Xs.append(d['X'])
        Ks.append(d['K'])
    X, K = np.vstack(Xs), np.vstack(Ks)
    yr = np.array([int(time.strftime('%Y', time.gmtime(int(e)))) for e in K[:, 0]])
    return X, K, yr


def add_regime(X, cuts):
    """Observable regime state, fixed from the TRAINING data only and passed in."""
    vb = np.digitize(X[:, RV], [0.35, 0.75]).astype(np.float32)
    tb = np.digitize(X[:, RET], cuts).astype(np.float32)
    return np.column_stack([X, vb, tb])


def main():
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, log_loss

    X, K, yr = load_all()
    y = K[:, 2].astype(float)
    years = sorted(set(yr.tolist()))
    print('=' * 78)
    print('R-12 step 2  lightgbm vs the stage-1 logistic, walk-forward BY YEAR')
    print('=' * 78)
    print('  %d rows, %d candles, years %d..%d. Train on years < Y, test on Y.'
          % (len(X), len(np.unique(K[:, 0])), years[0], years[-1]))
    print('  Regime inputs are OBSERVABLE state (rv60 bucket, ret60 tercile), not calendar era -')
    print('  an era feature would be out of range in every test fold, which is a leak.')
    print()
    print('  %-6s %10s %9s %9s   %9s %9s   %s'
          % ('test Y', 'test rows', 'logit LL', 'lgbm LL', 'logit AUC', 'lgbm AUC', 'lgbm better?'))
    rows = []
    for Y in years:
        tr, te = yr < Y, yr == Y
        if tr.sum() < 200000 or te.sum() < 20000:
            continue
        cuts = list(np.quantile(X[tr][:, RET], [1 / 3, 2 / 3]))
        Xtr, Xte = add_regime(X[tr], cuts), add_regime(X[te], cuts)
        ytr, yte = y[tr], y[te]
        lg = make_pipeline(StandardScaler(),
                           LogisticRegression(C=0.3, max_iter=2000)).fit(Xtr, ytr)
        p_lg = lg.predict_proba(Xte)[:, 1]
        gb = lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=15,
                                min_child_samples=60, subsample=0.8, subsample_freq=1,
                                colsample_bytree=0.8, reg_lambda=5.0, verbose=-1).fit(Xtr, ytr)
        p_gb = gb.predict_proba(Xte)[:, 1]
        a, b = log_loss(yte, p_lg), log_loss(yte, p_gb)
        c, d = roc_auc_score(yte, p_lg), roc_auc_score(yte, p_gb)
        rows.append((Y, int(te.sum()), a, b, c, d))
        print('  %-6d %10d %9.4f %9.4f   %9.4f %9.4f   %s'
              % (Y, te.sum(), a, b, c, d, 'yes' if b < a else 'no'), flush=True)
    if rows:
        wins = sum(1 for r in rows if r[3] < r[2])
        dll = statistics_mean([r[2] - r[3] for r in rows])
        dauc = statistics_mean([r[5] - r[4] for r in rows])
        print()
        print('  lgbm beats the logistic on logloss in %d of %d test years.' % (wins, len(rows)))
        print('  mean logloss gain %+.4f, mean AUC gain %+.4f' % (dll, dauc))
    print()


def statistics_mean(v):
    return float(sum(v) / len(v))


if __name__ == '__main__':
    main()
