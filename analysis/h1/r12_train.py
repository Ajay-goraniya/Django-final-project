"""R-12 stages 2-4: pipeline check, big-history train, and the walk-forward test.

Strict walk-forward and NO in-sample numbers in the report:
  stage A  PIPELINE CHECK - retrain on the 8 days v10 was built from, with THIS pipeline, and show
           it reproduces frozen v10 within noise. If it does not, nothing after it is trustworthy.
  stage B  BIG TRAIN - fit on ALL history strictly BEFORE the Polymarket window opens. The test
           rows are never seen, by construction, because they are later in time than every
           training row.
  stage C  TEST - on the labelled Polymarket rows (venues.outcome) and the live Zurich rows:
           paired vs frozen v10 on discordant candles only, halves, permutation, costs, null,
           and the full regime grid.

Model recipe is learner/train.py's own logit arm - StandardScaler -> LogisticRegression(C=0.3) ->
IsotonicRegression fitted on inner GroupKFold OOF - which is what model_v10.json is.

The emitted json keeps all 30 feature names in v10's order so it is a drop-in; the 12 masked
features carry mean 0, scale 1 and coefficient 0, so train == serve exactly (V's addendum).
"""
import glob, json, os, statistics, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import task_r8_taker_feature as R8
from r12_extract import BUILT

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
STORE = os.path.join(SP, 'r12')
H1 = os.path.dirname(os.path.abspath(__file__))
MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
MJ = json.load(open(MODEL_JSON))


def load_hist(upto_epoch=None):
    Xs, Ks = [], []
    for f in sorted(glob.glob(os.path.join(STORE, '*.npz'))):
        d = np.load(f)
        X, K = d['X'], d['K']
        if upto_epoch is not None:
            m = K[:, 0] < upto_epoch
            X, K = X[m], K[m]
        if len(X):
            Xs.append(X)
            Ks.append(K)
    return np.vstack(Xs), np.vstack(Ks)


def fit(X, y, groups):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import GroupKFold
    mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
    inner = np.full(len(y), np.nan)
    ng = len(np.unique(groups))
    for itr, ite in GroupKFold(n_splits=min(4, max(2, ng))).split(X, y, groups):
        inner[ite] = mk().fit(X[itr], y[itr]).predict_proba(X[ite])[:, 1]
    iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds='clip').fit(inner, y)
    m = mk().fit(X, y)
    return m, iso


def predict(m, iso, Z):
    return iso.predict(m.predict_proba(Z)[:, 1])


def to_json(m, iso, path, note):
    """Emit a model_v10.json drop-in: all 30 names in v10's order, masked ones neutralised."""
    sc, lr = m.steps[0][1], m.steps[1][1]
    mean = np.zeros(len(FEATURES))
    scale = np.ones(len(FEATURES))
    coef = np.zeros(len(FEATURES))
    for i, name in enumerate(BUILT):
        j = FEATURES.index(name)
        mean[j], scale[j], coef[j] = sc.mean_[i], sc.scale_[i], lr.coef_[0][i]
    out = dict(MJ)
    out.update(features=FEATURES, scaler_mean=mean.tolist(), scaler_scale=scale.tolist(),
               coef=coef.tolist(), intercept=float(lr.intercept_[0]),
               iso_x=[float(v) for v in iso.X_thresholds_],
               iso_y=[float(v) for v in iso.y_thresholds_],
               r12_note=note, r12_built_features=BUILT,
               r12_masked_features=[f for f in FEATURES if f not in BUILT])
    json.dump(out, open(path, 'w'), indent=1)
    return path
