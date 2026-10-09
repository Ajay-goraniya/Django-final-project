"""R-12 step 2 item (c) -- "the all-regimes deliverable" (V, learner/REQUEST.md; reduced at 00:1x to
this item only: "deliver only the per-regime OOS grid (cheap)").

The per-regime OUT-OF-SAMPLE grid of the STAGE-1 model itself: era x vol x trend, n / hit% / logloss.
Stage 1 is the 109-month history logistic on the 18 BUILT features - no venue input at all - fitted
walk-forward BY YEAR (train on every year strictly before Y, predict Y). Nothing here is in-sample.

This is the large-sample version of the question the user asked on the 5 logged days ("who is safe in
all regimes?"). There the biggest regime cell was n=76; here every cell is tens of thousands of
candles, so a regime reading is actually readable.

BUCKET CUTS ARE FIXED BEFORE ANY RESULT IS READ, and they are fixed WITHOUT TOUCHING TEST DATA:
  vol   - rv60 at 0.35 / 0.75, the same cuts used everywhere else in this task.
  trend - ret60 terciles computed on the EARLIEST TRAINING BLOCK ONLY (years < 2019). Using whole-
          store quantiles would let the test years define their own buckets, which is peeking even
          for a reporting grid.
  era   - the test year. Era is a REPORTING axis only; it is never a model input, because a calendar
          feature is out of range in every test fold by construction (see r12s2_lgbm.py).

OOS predictions are cached to r12s2c_oof.npz so the grid can be re-cut without refitting.
"""
import glob, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r12_extract import BUILT
import r12_train as T
from verify import MIN_CELL

STORE = os.path.join(T.SP, 'r12')
CACHE = os.path.join(T.SP, 'r12s2c_oof.npz')
RV, RET = BUILT.index('rv60'), BUILT.index('ret60')
VOL_CUTS = [0.35, 0.75]
VOL_NAMES = ['rv<0.35', 'rv0.35-0.75', 'rv>0.75']
TREND_NAMES = ['down', 'flat', 'up']


def load_all():
    Xs, Ks = [], []
    for f in sorted(glob.glob(os.path.join(STORE, '*.npz'))):
        d = np.load(f)
        Xs.append(d['X']); Ks.append(d['K'])
    X, K = np.vstack(Xs), np.vstack(Ks)
    yr = np.array([int(time.strftime('%Y', time.gmtime(int(e)))) for e in K[:, 0]])
    return X, K, yr


def main():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, K, yr = load_all()
    y = K[:, 2].astype(float)
    years = sorted(set(yr.tolist()))

    # trend cuts from the earliest training block only -- never from a test year
    base = yr < 2019
    tcuts = [float(np.quantile(X[base, RET], 1 / 3)), float(np.quantile(X[base, RET], 2 / 3))]

    if os.path.exists(CACHE):
        z = np.load(CACHE)
        oof, tested = z['oof'], list(z['tested'])
    else:
        oof = np.full(len(y), np.nan)
        tested = []
        for Y in years:
            tr, te = yr < Y, yr == Y
            if tr.sum() < 200000 or te.sum() < 20000:
                continue
            m = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
            m.fit(X[tr], y[tr])
            oof[te] = m.predict_proba(X[te])[:, 1]
            tested.append(Y)
            print('  fitted through %d, tested %d (%d rows)' % (Y - 1, Y, int(te.sum())), flush=True)
        np.savez_compressed(CACHE, oof=oof, tested=np.array(tested))

    m = ~np.isnan(oof)
    p, yy = oof[m], y[m]
    vb = np.digitize(X[m, RV], VOL_CUTS)
    tb = np.digitize(X[m, RET], tcuts)
    ye = yr[m]

    hit = lambda a, b: float(((a >= 0.5).astype(float) == b).mean())
    ll = lambda a, b: float(-np.mean(b * np.log(np.clip(a, 1e-6, 1 - 1e-6))
                                     + (1 - b) * np.log(np.clip(1 - a, 1e-6, 1 - 1e-6))))

    print('=' * 100)
    print('R-12 step 2 (c)  STAGE-1 per-regime OOS grid  -- era x vol x trend')
    print('=' * 100)
    print('  %d OOS rows, test years %s. 18 BUILT features, no venue input.'
          % (int(m.sum()), ', '.join(str(t) for t in tested)))
    print('  trend cuts from years < 2019 only: ret60 %.4f / %.4f. vol cuts 0.35 / 0.75.'
          % (tcuts[0], tcuts[1]))
    print('  baseline to beat: always-UP on the same rows = %.4f hit, and logloss of the base rate.'
          % max(yy.mean(), 1 - yy.mean()))
    print('  MIN_CELL=%d. Full grid, every cell, never the best one.' % MIN_CELL)

    print('\n  1-D: VOL')
    print('  %-14s %10s %8s %9s' % ('bucket', 'n', 'hit%', 'logloss'))
    for i, nm in enumerate(VOL_NAMES):
        k = vb == i
        print('  %-14s %10d %7.2f%% %9.4f' % (nm, int(k.sum()), 100 * hit(p[k], yy[k]), ll(p[k], yy[k]))
              if k.sum() >= MIN_CELL else '  %-14s %10d   insufficient' % (nm, int(k.sum())))

    print('\n  1-D: TREND')
    print('  %-14s %10s %8s %9s' % ('bucket', 'n', 'hit%', 'logloss'))
    for i, nm in enumerate(TREND_NAMES):
        k = tb == i
        print('  %-14s %10d %7.2f%% %9.4f' % (nm, int(k.sum()), 100 * hit(p[k], yy[k]), ll(p[k], yy[k]))
              if k.sum() >= MIN_CELL else '  %-14s %10d   insufficient' % (nm, int(k.sum())))

    print('\n  1-D: ERA (test year)')
    print('  %-14s %10s %8s %9s' % ('year', 'n', 'hit%', 'logloss'))
    for Y in tested:
        k = ye == Y
        print('  %-14d %10d %7.2f%% %9.4f' % (Y, int(k.sum()), 100 * hit(p[k], yy[k]), ll(p[k], yy[k])))

    print('\n  2-D: VOL x TREND (pooled over all eras)')
    print('  %-14s %-8s %10s %8s %9s' % ('vol', 'trend', 'n', 'hit%', 'logloss'))
    for i, vn in enumerate(VOL_NAMES):
        for j, tn in enumerate(TREND_NAMES):
            k = (vb == i) & (tb == j)
            if k.sum() < MIN_CELL:
                print('  %-14s %-8s %10d   insufficient' % (vn, tn, int(k.sum()))); continue
            print('  %-14s %-8s %10d %7.2f%% %9.4f'
                  % (vn, tn, int(k.sum()), 100 * hit(p[k], yy[k]), ll(p[k], yy[k])))
        print()

    print('  3-D: ERA x VOL x TREND -- hit%% (logloss), every cell')
    hdr = '  %-6s' % 'year'
    for vn in VOL_NAMES:
        for tn in TREND_NAMES:
            hdr += '%18s' % ('%s/%s' % (vn.replace('rv', ''), tn))
    print(hdr)
    worst = []
    for Y in tested:
        line = '  %-6d' % Y
        for i in range(3):
            for j in range(3):
                k = (ye == Y) & (vb == i) & (tb == j)
                if k.sum() < MIN_CELL:
                    line += '%18s' % ('insuff(%d)' % int(k.sum())); continue
                h, l = hit(p[k], yy[k]), ll(p[k], yy[k])
                worst.append((h, Y, VOL_NAMES[i], TREND_NAMES[j], int(k.sum())))
                line += '%18s' % ('%.3f (%.3f)' % (h, l))
        print(line)

    print('\n  READABLE CELLS: %d. Below 50%% hit: %d.'
          % (len(worst), sum(1 for w in worst if w[0] < 0.5)))
    for w in sorted(worst)[:5]:
        print('    worst: %d %s/%s  hit %.3f  n=%d' % (w[1], w[2], w[3], w[0], w[4]))
    for w in sorted(worst)[-3:]:
        print('    best:  %d %s/%s  hit %.3f  n=%d' % (w[1], w[2], w[3], w[0], w[4]))


if __name__ == '__main__':
    main()


def null_grid():
    """THE OBVIOUS NULL, run on the same cells. A 72%% hit rate means nothing on its own here: most
    of it is the clock. By second 210 a candle already up 30 bps is nearly decided, so "the candle is
    up so far" (sign of move_bps) is a strong rule by construction. The only number worth reading is
    the MODEL MINUS THAT NULL, per cell. Rule: accuracy is not PnL, and always test the obvious null.
    """
    import glob, time
    Xs, Ks = [], []
    for f in sorted(glob.glob(os.path.join(STORE, '*.npz'))):
        d = np.load(f); Xs.append(d['X']); Ks.append(d['K'])
    X, K = np.vstack(Xs), np.vstack(Ks)
    yr = np.array([int(time.strftime('%Y', time.gmtime(int(e)))) for e in K[:, 0]])
    y = K[:, 2].astype(float)
    z = np.load(CACHE); oof, tested = z['oof'], list(z['tested'])
    m = ~np.isnan(oof)
    base = yr < 2019
    tcuts = [float(np.quantile(X[base, RET], 1/3)), float(np.quantile(X[base, RET], 2/3))]
    p, yy = oof[m], y[m]
    MV = BUILT.index('move_bps')
    nullp = (X[m, MV] >= 0).astype(float)
    vb, tb, ye = np.digitize(X[m, RV], VOL_CUTS), np.digitize(X[m, RET], tcuts), yr[m]
    hit = lambda a, b: float(((a >= 0.5).astype(float) == b).mean())
    print('\n' + '=' * 100)
    print('  THE OBVIOUS NULL: "the candle is up so far" (move_bps >= 0), same cells.')
    print('  Only MODEL - NULL is a real number; the raw 72%% is mostly the clock.')
    print('=' * 100)
    print('  overall: model %.4f  null %.4f  delta %+.4f' % (hit(p, yy), hit(nullp, yy),
                                                            hit(p, yy) - hit(nullp, yy)))
    print('\n  %-6s' % 'year' + ''.join('%17s' % ('%s/%s' % (v.replace('rv',''), t))
                                        for v in VOL_NAMES for t in TREND_NAMES))
    deltas = []
    for Y in tested:
        line = '  %-6d' % Y
        for i in range(3):
            for j in range(3):
                k = (ye == Y) & (vb == i) & (tb == j)
                if k.sum() < MIN_CELL:
                    line += '%17s' % 'insuff'; continue
                d_ = hit(p[k], yy[k]) - hit(nullp[k], yy[k])
                deltas.append((d_, Y, VOL_NAMES[i], TREND_NAMES[j], int(k.sum())))
                line += '%17s' % ('%+.4f' % d_)
        print(line)
    neg = [d for d in deltas if d[0] <= 0]
    print('\n  cells where the model does NOT beat the dumb rule: %d of %d' % (len(neg), len(deltas)))
    for d_ in sorted(deltas)[:4]:
        print('    worst: %d %s/%s  %+.4f  n=%d' % (d_[1], d_[2], d_[3], d_[0], d_[4]))
    for d_ in sorted(deltas)[-2:]:
        print('    best:  %d %s/%s  %+.4f  n=%d' % (d_[1], d_[2], d_[3], d_[0], d_[4]))
