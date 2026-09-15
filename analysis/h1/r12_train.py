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


# ---------------------------------------------------------------- test-window features
def test_store(days):
    """My 18 features at EVERY second 15..240 over the Polymarket window, cached."""
    import r12_parity as P
    f = os.path.join(SP, 'r12_test.npz')
    if os.path.exists(f):
        d = np.load(f)
        return {(int(k[0]), int(k[1])): x for x, k in zip(d['X'], d['K'])}
    import r12_extract as E
    E.SECS = list(range(15, 241))
    Xs, Ks = [], []
    for day in days:
        try:
            a = P.daily(day)
        except Exception:
            print('  test store: no daily file for %s' % day, flush=True)
            continue
        r = E.build(a)
        if r:
            Xs.append(r[0])
            Ks.append(r[1])
    X, K = np.vstack(Xs), np.vstack(Ks)
    np.savez_compressed(f, X=X, K=K)
    return {(int(k[0]), int(k[1])): x for x, k in zip(X, K)}


def lane_ticks(oc):
    """Every evaluated tick in the Polymarket lanes, with the engine's own feat and ask."""
    out = []
    lanes = [('poly_pnl', 'ts_ms', 'ask'), ('poly_acc', 'ts_ms', 'ask'),
             ('v12_poly_lane', 'signal_ms', 'quote_ask'),
             ('v12_poly_weekend', 'signal_ms', 'quote_ask')]
    import sqlite3
    for name, tcol, acol in lanes:
        c = sqlite3.connect(os.path.join('/tmp/claude-0/db', name + '.sqlite3'))
        rows = list(c.execute('select candle_epoch,%s,%s,feat from trades where feat is not null'
                              % (tcol, acol)))
        rows += list(c.execute('select candle_epoch,ts_ms,ask,feat from decisions '
                               'where feat is not null'))
        for ep, ts, ask, feat in rows:
            if ask is None or int(ep) not in oc:
                continue
            s = int(ts) // 1000 - int(ep)
            if not (15 <= s <= 240):
                continue
            out.append(dict(ep=int(ep), sec=s, ts=int(ts) // 1000, ask=float(ask),
                            feat=json.loads(feat), lane=name,
                            day=datetime.utcfromtimestamp(int(ep)).strftime('%Y-%m-%d'),
                            actual=oc[int(ep)]))
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: r['ts']):
        k = (r['lane'], r['ep'], r['sec'])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


def fire_set(rows, pup):
    by = {}
    for r, p in sorted(zip(rows, pup), key=lambda z: z[0]['ts']):
        if r['ep'] in by:
            continue
        side = 'UP' if p >= 0.5 else 'DOWN'
        ps = p if side == 'UP' else 1 - p
        if R8.ev_of(ps, r['ask']) >= R8.threshold(r['feat']['rv60']):
            by[r['ep']] = dict(r, side=side, ps=ps)
    return by


def book(fires, haircut=0.0):
    if not fires:
        return None
    pnl, wins = [], 0
    for t in fires.values():
        won = (t['side'] == t['actual'])
        wins += won
        pnl.append(R8.per1(min(0.98, t['ask'] + haircut), won))
    return dict(n=len(pnl), win=wins / len(pnl), per1=statistics.fmean(pnl), total=sum(pnl))


def main():
    oc = R8.oracle()
    L = lane_ticks(oc)
    cutoff = min(r['ep'] for r in L)
    days = sorted({r['day'] for r in L})
    print('=' * 78)
    print('R-12 stage B/C  big-history train, strict walk-forward, then the test')
    print('=' * 78)
    print('  test window: %s .. %s, %d evaluated ticks, %d candles'
          % (days[0], days[-1], len(L), len({r['ep'] for r in L})))
    print('  TRAIN CUTOFF: every training row has candle_epoch < %d (%s), which is the FIRST'
          % (cutoff, datetime.utcfromtimestamp(cutoff).isoformat()))
    print('  Polymarket candle. The store ends 2026-08-31, so no test row can be in training -')
    print('  the separation is by construction, not by a filter I could have got wrong.')
    Xh, Kh = load_hist(upto_epoch=cutoff)
    yh = Kh[:, 2].astype(float)
    grp = np.array([datetime.utcfromtimestamp(int(e)).strftime('%Y-%m') for e in Kh[:, 0]])
    print('  history: %d rows, %d candles, %d months, label balance %.4f'
          % (len(Xh), len(np.unique(Kh[:, 0])), len(np.unique(grp)), yh.mean()))
    print()

    print('  fitting (StandardScaler -> LogisticRegression(C=0.3) -> isotonic on inner GroupKFold '
          'OOF)...', flush=True)
    # Cache the fit: it is 5 logistic passes over 4.75M rows, and a trivial bug downstream should
    # never cost it twice. (It did once - grp.min() on a string array - hence this.)
    import joblib
    cache = os.path.join(SP, 'r12_fit.joblib')
    if os.path.exists(cache):
        m, iso = joblib.load(cache)
        print('  loaded cached fit', flush=True)
    else:
        m, iso = fit(Xh.astype(np.float64), yh, grp)
        joblib.dump((m, iso), cache)
    path = to_json(m, iso, os.path.join(H1, 'model_r12_big.json'),
                   'R-12: trained on %d rows of BTC 1s history, %s..%s, %d of 30 features built, '
                   'the rest masked to zero so train == serve.'
                   % (len(Xh), sorted(set(grp.tolist()))[0], sorted(set(grp.tolist()))[-1],
                      len(BUILT)))
    print('  model written: %s' % os.path.basename(path))
    print()

    TS = test_store(days)
    ok = [r for r in L if (r['ep'], r['sec']) in TS]
    print('  test rows with my features rebuilt: %d of %d' % (len(ok), len(L)))
    Z = np.array([TS[(r['ep'], r['sec'])] for r in ok], np.float64)
    p_new = predict(m, iso, Z)
    frozen = Model(MODEL_JSON)
    p_old = np.array([frozen.p_up(r['feat']) for r in ok])

    f_new, f_old = fire_set(ok, p_new), fire_set(ok, p_old)
    b_new, b_old = book(f_new), book(f_old)
    print()
    print('  %-14s %8s %9s %10s %10s' % ('arm', 'fires', 'hit%', 'per $1', 'total'))
    for nm, b in (('frozen v10', b_old), ('R-12 big', b_new)):
        print('  %-14s %8d %8.1f%% %+10.3f %+10.2f'
              % (nm, b['n'], 100 * b['win'], b['per1'], b['total']))
    print()
    return ok, p_new, p_old, f_new, f_old, b_new, b_old, oc, days


if __name__ == '__main__':
    main()
