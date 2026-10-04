#!/usr/bin/env python3
"""EF-2 step 2a: the walk-forward FITS, cached to disk. READ-ONLY, master OFF.

Split out from the reporting deliberately. The fits are the expensive part (minutes per day on 1.6M rows) and
the tables built on top of them changed twice while the first run was in flight, so the predictions are
computed once and cached; every table downstream reads the cache and is instant to rebuild.

day k is fitted on days < k, the scaler is fitted on the TRAINING rows alone, and the first day is never
scored. The stump ensemble is a CAPACITY CHECK only - it answers "is a linear model the limiting factor" -
so its training set is capped at 400k rows to keep it cheap; the logistic always sees every training row.
"""
import sys, time, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import fit_logistic, predict, auc, gb_fit, gb_predict, ROWS

OUT = '/home/ubuntu/pm_ef2/ef2_fits.npz'
GB_CAP = 400_000

if __name__ == '__main__':
    t0 = time.time()
    z = np.load(ROWS, allow_pickle=True)
    X, y, day = z['X'], z['y'].astype(float), z['day']
    names = [str(s) for s in z['names']]
    keep = np.all(np.isfinite(X), axis=1)
    print(f'rows {len(y):,}, finite on every feature {int(keep.sum()):,} ({100*keep.mean():.1f}%)', flush=True)
    X, y, day = X[keep], y[keep], day[keep]
    days = sorted(set(day.tolist()))
    pw = np.full(len(y), np.nan); pg = np.full(len(y), np.nan)
    W_ = np.zeros((len(days) - 1, X.shape[1] + 1)); MU = np.zeros((len(days) - 1, X.shape[1]))
    SD = np.zeros((len(days) - 1, X.shape[1])); fitted = []
    rng = np.random.default_rng(3)
    for i, d in enumerate(days[1:]):
        tr, te = day < d, day == d
        if tr.sum() < 5000 or te.sum() == 0:
            print(f'  day {d}: skipped (train {int(tr.sum())})', flush=True); continue
        mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd < 1e-9, 1.0, sd)
        Xt = ((X[tr] - mu) / sd).astype(np.float32); yt = y[tr]
        w = fit_logistic(Xt, yt)
        pw[te] = predict(w, ((X[te] - mu) / sd).astype(np.float64))
        sub = slice(None) if len(yt) <= GB_CAP else rng.choice(len(yt), GB_CAP, replace=False)
        gm = gb_fit(Xt[sub], yt[sub])
        pg[te] = gb_predict(gm, ((X[te] - mu) / sd).astype(np.float32))
        W_[i], MU[i], SD[i] = w, mu, sd; fitted.append(d)
        print(f'  day {d}: train {int(tr.sum()):,} test {int(te.sum()):,}  '
              f'AUC logistic {auc(y[te], pw[te]):.4f}  stumps {auc(y[te], pg[te]):.4f}  '
              f'[{time.time()-t0:.0f}s]', flush=True)
    np.savez_compressed(OUT, pw=pw, pg=pg, keep=keep, coef=W_, mean=MU, sd=SD,
                        fitted=np.array(fitted), names=np.array(names))
    sc = np.isfinite(pw)
    print(f'\nsaved {OUT}  [{time.time()-t0:.0f}s]')
    print(f'  scored {int(sc.sum()):,} rows on {len(fitted)} days')
    print(f'  AUC pooled: logistic {auc(y[sc], pw[sc]):.4f}  stumps {auc(y[sc], pg[sc]):.4f}  '
          f'own_ask alone {auc(y[sc], -X[sc, names.index("own_ask")]):.4f}  '
          f'p_side alone {auc(y[sc], X[sc, names.index("p_side")]):.4f}')
