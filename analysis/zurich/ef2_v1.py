#!/usr/bin/env python3
"""EF-2 v1: gradient boosting, same rows, same walk-forward. READ-ONLY, master OFF.

V's brief asked for lightgbm, else sklearn HistGradientBoosting. Neither was on this box. Rather than
substitute something weaker or install into the ENGINE's venv, sklearn 1.9.1 went into a SEPARATE venv at
/home/ubuntu/pm_ml_venv - the engine's interpreter and its numpy are untouched and were checked afterwards.

Identical protocol to v0 so the two rungs are comparable: day k fitted on days < k, first day never scored,
one row per (pass, side), predictions cached to npz for the reporter. No scaling is applied - HistGB splits
on raw values and is invariant to monotone rescaling, so standardising would only add a step that could
silently differ from v0's.

Feature importance for a tree model is not a coefficient, so it is PERMUTATION importance on a held-out
subsample: shuffle one column, measure the AUC it costs. That answers V's question (does the model lean on
ask dynamics rather than move_bps) in units comparable across rungs.
"""
import sys, time, json, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from sklearn.ensemble import HistGradientBoostingClassifier

ROWS = '/home/ubuntu/pm_ef2/ef2_rows.npz'
OUT = '/home/ubuntu/pm_ef2/ef2_fits_v1.npz'
IMP_N = 120_000


def auc(y, s):
    m = np.isfinite(s); y, s = np.asarray(y)[m], np.asarray(s)[m]
    if len(set(y.tolist())) < 2: return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


if __name__ == '__main__':
    t0 = time.time()
    z = np.load(ROWS, allow_pickle=True)
    X, y, day = z['X'], z['y'].astype(np.int8), z['day']
    names = [str(s) for s in z['names']]
    keep = np.all(np.isfinite(X), axis=1)
    X, y, day = X[keep], y[keep], day[keep]
    days = sorted(set(day.tolist()))
    print(f'rows {len(y):,}  features {X.shape[1]}  days {days}', flush=True)
    pw = np.full(len(y), np.nan)
    imp_acc = np.zeros(X.shape[1]); nimp = 0
    rng = np.random.default_rng(11)
    for d in days[1:]:
        tr, te = day < d, day == d
        if tr.sum() < 5000 or te.sum() == 0:
            print(f'  day {d}: skipped (train {int(tr.sum())})', flush=True); continue
        m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                           min_samples_leaf=200, l2_regularization=1.0,
                                           early_stopping=True, validation_fraction=0.1,
                                           random_state=5)
        m.fit(X[tr], y[tr])
        pw[te] = m.predict_proba(X[te])[:, 1]
        a0 = auc(y[te], pw[te])
        print(f'  day {d}: train {int(tr.sum()):,} test {int(te.sum()):,}  AUC {a0:.4f}  '
              f'iters {m.n_iter_}  [{time.time()-t0:.0f}s]', flush=True)
        # permutation importance on a subsample of the SAME held-out day
        idx = np.nonzero(te)[0]
        if len(idx) > IMP_N: idx = rng.choice(idx, IMP_N, replace=False)
        Xi, yi = X[idx].copy(), y[idx]
        base = auc(yi, m.predict_proba(Xi)[:, 1])
        for j in range(X.shape[1]):
            col = Xi[:, j].copy()
            Xi[:, j] = rng.permutation(col)
            imp_acc[j] += base - auc(yi, m.predict_proba(Xi)[:, 1])
            Xi[:, j] = col
        nimp += 1
        print(f'    permutation importance done [{time.time()-t0:.0f}s]', flush=True)
    imp = imp_acc / max(nimp, 1)
    np.savez_compressed(OUT, pw=pw, pg=np.full(len(y), np.nan), keep=keep, imp=imp,
                        names=np.array(names), fitted=np.array(days[1:]))
    sc = np.isfinite(pw)
    print(f'\nsaved {OUT}  [{time.time()-t0:.0f}s]')
    print(f'  pooled AUC {auc(y[sc], pw[sc]):.4f} on {int(sc.sum()):,} scored rows')
    o = np.argsort(-imp)
    DYN = ('d_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30')
    print('  top 18 by permutation importance (AUC lost when the column is shuffled):')
    for r, j in enumerate(o[:18], 1):
        tag = '  <- ASK DYNAMICS' if names[j] in DYN else \
              '  <- the price' if names[j] in ('own_ask', 'opp_ask', 'lv', 'p_venue', '_ask_up', '_ask_dn') else \
              '  <- the move' if names[j] in ('move_bps', 'mv_x_sec') else \
              '  <- the engine p' if names[j] == 'p_side' else ''
        print(f'    {r:>2}. {names[j]:16s} {imp[j]:+.4f}{tag}')
    for lab, ks in (('ask dynamics', DYN), ('the price', ('own_ask', 'opp_ask', 'lv', 'p_venue', '_ask_up', '_ask_dn')),
                    ('the move', ('move_bps', 'mv_x_sec')), ('the engine p', ('p_side',))):
        print(f'    block {lab:14s} {sum(imp[names.index(k)] for k in ks if k in names):+.4f}')
