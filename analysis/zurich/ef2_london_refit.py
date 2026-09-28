#!/usr/bin/env python3
"""Refit EF-2 on ONLY the features London actually has. READ-ONLY, master OFF.

WHY THIS EXISTS. ef2_london.py imputed the 8 missing features at their training mean and the AUC barely moved
- 0.8608 to 0.8573 - but the acceptance table INVERTED: win rate 65.9% -> 32.5%, per $1 +0.016 -> -0.076.
AUC is rank-based and survived; the DECISION does not depend on rank, it depends on the calibrated LEVEL of
p_win against the price, and imputing 34.2% of the coefficient mass moves the level. It is the same failure
ETH_SOL_DIAG found on ETH/SOL - the ranking transfers, the level does not - arriving here through imputation
instead of through a different coin.

So scoring London's 654 attempts with the imputed 52-feature model would have produced a confidently wrong
answer, and it would have looked like EF-2 failing rather than the imputation failing.

The fix is not a better imputer. It is to TRAIN ON WHAT LONDON WILL HAVE, so the model is calibrated on its
own feature set. Same walk-forward protocol, same rows, same everything - only the feature list is cut.
"""
import sys, time, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import fit_logistic, predict, auc, ROWS
from ef2_london import ABSENT

OUT = '/home/ubuntu/pm_ef2/ef2_fits_london.npz'

if __name__ == '__main__':
    t0 = time.time()
    z = np.load(ROWS, allow_pickle=True)
    X, y, day = z['X'], z['y'].astype(float), z['day']
    names = [str(s) for s in z['names']]
    keep = np.all(np.isfinite(X), axis=1)
    X, y, day = X[keep], y[keep], day[keep]
    cols = [j for j, n in enumerate(names) if n not in ABSENT]
    sub = [names[j] for j in cols]
    print(f'refitting on {len(cols)} of {len(names)} features (dropped: {sorted(ABSENT)})', flush=True)
    Xs = X[:, cols]
    days = sorted(set(day.tolist()))
    pw = np.full(len(y), np.nan)
    C = np.zeros((len(days) - 1, len(cols) + 1)); MU = np.zeros((len(days) - 1, len(cols)))
    SD = np.zeros((len(days) - 1, len(cols))); fitted = []
    for i, d in enumerate(days[1:]):
        tr, te = day < d, day == d
        if tr.sum() < 5000 or te.sum() == 0: continue
        mu, sd = Xs[tr].mean(0), Xs[tr].std(0); sd = np.where(sd < 1e-9, 1.0, sd)
        w = fit_logistic(((Xs[tr] - mu) / sd).astype(np.float32), y[tr])
        pw[te] = predict(w, ((Xs[te] - mu) / sd).astype(np.float64))
        C[i], MU[i], SD[i] = w, mu, sd; fitted.append(d)
        print(f'  day {d}: AUC {auc(y[te], pw[te]):.4f}  [{time.time()-t0:.0f}s]', flush=True)
    np.savez_compressed(OUT, pw=pw, keep=keep, coef=C, mean=MU, sd=SD, fitted=np.array(fitted),
                        names=np.array(sub), cols=np.array(cols))
    sc = np.isfinite(pw)
    print(f'\nsaved {OUT}  [{time.time()-t0:.0f}s]   pooled AUC {auc(y[sc], pw[sc]):.4f}')
