"""R-15 stage 1 -- do the new features carry direction information the 18 do not?

Four arms, identical folds, identical learner, walk-forward BY YEAR (train every year strictly
before Y, test Y):
    base    stage-1 as r12s2 defined it: the 18 BUILT features + the two observable regime buckets
    +a      base + 16 higher-timeframe features (r15_extract.py)
    +b      base + 4 futures metrics features  (r15_futures.py)
    +ab     base + both

The learner and its hyper-parameters are lifted unchanged from r12s2_lgbm.py so that any difference
between arms is the FEATURES and not the model. The stage-1 logistic is also reported per year as the
reference the brief asks for.

THREE THINGS THIS SCRIPT REFUSES TO DO SILENTLY, each of which has cost time on this project before:

1. It never zero-fills a missing feature. A row without a usable futures metrics bar is DROPPED from
   the (b) arms, not filled with 0 - filling teaches the model that "no data" is a real market state
   and it is the same class of error as the masked-feature handicap in R-12b. Because of that the (b)
   arms run on fewer rows and a shorter span, and every table says which.
2. It never pools arms measured on different rows. (a) spans 2019-2026; (b) starts when the metrics
   archive does. Each comparison is made on the INTERSECTION of the arms being compared, refitted for
   that intersection, and the row count is printed next to it.
3. It reports the obvious null on every fold. R-12 step 2(c) showed a 72%% hit rate that was beaten by
   "the candle is up so far". Any arm here is measured against that same null, per year, or the
   number means nothing.
"""
import glob, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r12_extract import BUILT
import r12_train as T
from r15_extract import HTF
from r15_futures import FUT

SP = T.SP
STORE, ASTORE = os.path.join(SP, 'r12'), os.path.join(SP, 'r15a')
BSTORE = os.path.join(SP, 'r15b.npz')
CACHE = os.path.join(SP, 'r15_joined.npz')
RV, RET, MV = BUILT.index('rv60'), BUILT.index('ret60'), BUILT.index('move_bps')
LGB = dict(n_estimators=350, learning_rate=0.03, num_leaves=15, min_child_samples=60,
           subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)


def join():
    """(epoch, S) join of the 18-feature store, the HTF block and the futures bars."""
    if os.path.exists(CACHE):
        d = np.load(CACHE)
        return d['X'], d['H'], d['B'], d['K']
    Xs, Ks = [], []
    for f in sorted(glob.glob(os.path.join(STORE, '*.npz'))):
        d = np.load(f); Xs.append(d['X']); Ks.append(d['K'])
    X, K = np.vstack(Xs), np.vstack(Ks)
    Hs, HKs = [], []
    for f in sorted(glob.glob(os.path.join(ASTORE, '*.npz'))):
        d = np.load(f); Hs.append(d['H']); HKs.append(d['K'])
    H, HK = np.vstack(Hs), np.vstack(HKs)
    key = lambda k: k[:, 0].astype(np.int64) * 1000 + k[:, 1].astype(np.int64)
    kx, kh = key(K), key(HK)
    order = np.argsort(kh)
    kh, H = kh[order], H[order]
    pos = np.searchsorted(kh, kx)
    pos[pos >= len(kh)] = 0
    hit = kh[pos] == kx
    Hf = np.full((len(kx), H.shape[1]), np.nan, np.float32)
    Hf[hit] = H[pos[hit]]
    bz = np.load(BSTORE)
    bt, BF = bz['T'], bz['F']
    bo = np.argsort(bt); bt, BF = bt[bo], BF[bo]
    want = K[:, 0].astype(np.int64) - 300           # the PREVIOUS COMPLETED 5-min bar
    bp = np.searchsorted(bt, want)
    bp[bp >= len(bt)] = 0
    bhit = bt[bp] == want
    Bf = np.full((len(kx), BF.shape[1]), np.nan, np.float32)
    Bf[bhit] = BF[bp[bhit]]
    np.savez_compressed(CACHE, X=X, H=Hf, B=Bf, K=K)
    return X, Hf, Bf, K


def add_regime(X, cuts):
    vb = np.digitize(X[:, RV], [0.35, 0.75]).astype(np.float32)
    tb = np.digitize(X[:, RET], cuts).astype(np.float32)
    return np.column_stack([X, vb, tb])


def main():
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, log_loss

    X, H, B, K = join()
    y = K[:, 2].astype(float)
    yr = np.array([int(time.strftime('%Y', time.gmtime(int(e)))) for e in K[:, 0]])
    okH = np.isfinite(H).all(1)
    okB = np.isfinite(B).all(1)
    nullp = (X[:, MV] >= 0).astype(float)

    print('=' * 104)
    print('R-15 stage 1  new-feature arms vs stage-1, lightgbm, walk-forward BY YEAR')
    print('=' * 104)
    print('  %d store rows. HTF block present on %d (%.1f%%), futures bars on %d (%.1f%%).'
          % (len(X), int(okH.sum()), 100 * okH.mean(), int(okB.sum()), 100 * okB.mean()))
    print('  futures coverage starts %s' % time.strftime('%Y-%m', time.gmtime(
        int(K[okB, 0].min()))) if okB.any() else '  futures: NONE')
    print('  arms: base=18+2 regime, +a=+%d HTF, +b=+%d futures, +ab=both' % (len(HTF), len(FUT)))
    print('  missing features are DROPPED, never zero-filled; each arm says its row count.')
    print()

    arms = {
        'base': (lambda m: [X[m]], np.ones(len(X), bool)),
        '+a': (lambda m: [X[m], H[m]], okH),
        '+b': (lambda m: [X[m], B[m]], okB),
        '+ab': (lambda m: [X[m], H[m], B[m]], okH & okB),
    }
    years = sorted(set(yr.tolist()))
    res = {k: {} for k in arms}
    nullres = {}
    for name, (build, mask) in arms.items():
        for Y in years:
            tr, te = mask & (yr < Y), mask & (yr == Y)
            if tr.sum() < 200000 or te.sum() < 20000:
                continue
            cuts = list(np.quantile(X[tr][:, RET], [1 / 3, 2 / 3]))
            Xtr = add_regime(np.column_stack(build(tr)), cuts)
            Xte = add_regime(np.column_stack(build(te)), cuts)
            g = lgb.LGBMClassifier(**LGB).fit(Xtr, y[tr])
            p = g.predict_proba(Xte)[:, 1]
            res[name][Y] = dict(n=int(te.sum()), ll=log_loss(y[te], p),
                                auc=roc_auc_score(y[te], p),
                                hit=float(((p >= .5).astype(float) == y[te]).mean()),
                                null=float((nullp[te] == y[te]).mean()))
            if name == 'base':
                lgm = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
                pl = lgm.fit(Xtr, y[tr]).predict_proba(Xte)[:, 1]
                nullres[Y] = dict(ll=log_loss(y[te], pl), auc=roc_auc_score(y[te], pl),
                                  hit=float(((pl >= .5).astype(float) == y[te]).mean()))
            print('  %-5s %d  n=%d  LL %.4f  AUC %.4f  hit %.4f  null %.4f'
                  % (name, Y, te.sum(), res[name][Y]['ll'], res[name][Y]['auc'],
                     res[name][Y]['hit'], res[name][Y]['null']), flush=True)
        del_ = None
    np.save(os.path.join(SP, 'r15_stage1.npy'), np.array([res, nullres], dtype=object),
            allow_pickle=True)

    print('\n  PER YEAR, all arms (LL / AUC / hit - null)')
    hdr = '  %-6s %10s' % ('year', 'test rows')
    for k in arms:
        hdr += '%26s' % k
    print(hdr + '%14s' % 'logit base')
    for Y in years:
        if Y not in res['base']:
            continue
        line = '  %-6d %10d' % (Y, res['base'][Y]['n'])
        for k in arms:
            r = res[k].get(Y)
            line += '%26s' % ('-' if not r else '%.4f/%.3f/%+.4f'
                              % (r['ll'], r['auc'], r['hit'] - r['null']))
        line += '%14s' % ('%.4f' % nullres[Y]['ll'] if Y in nullres else '-')
        print(line)

    print('\n  ARM vs base, on the SAME years each arm ran (never pooled across different spans)')
    for k in ('+a', '+b', '+ab'):
        ys = sorted(set(res[k]) & set(res['base']))
        if not ys:
            print('  %-5s no common years' % k); continue
        dll = float(np.mean([res['base'][Y]['ll'] - res[k][Y]['ll'] for Y in ys]))
        dau = float(np.mean([res[k][Y]['auc'] - res['base'][Y]['auc'] for Y in ys]))
        wins = sum(1 for Y in ys if res[k][Y]['ll'] < res['base'][Y]['ll'])
        bn = float(np.mean([res[k][Y]['hit'] - res[k][Y]['null'] for Y in ys]))
        print('  %-5s years %s  logloss gain %+.4f (%d/%d)  AUC gain %+.4f  hit-null %+.4f'
              % (k, '%d-%d' % (ys[0], ys[-1]), dll, wins, len(ys), dau, bn))


if __name__ == '__main__':
    main()
