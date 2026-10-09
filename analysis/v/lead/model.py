#!/usr/bin/env python3
"""Stage-1 Binance lead test, step 2: walk-forward by day (train days < k, test day k).

Targets (spot last price, 100 ms grid): up_X_H = max spot move over (t, t+H] >= +X bps; dn_X_H = <= -X bps,
X in 2/5/10 bps, H in 300/500/1000 ms.
Models: lr / gbm on all 53 order-flow features; lr0 / gbm0 = NULL, the same model on s_r1000 only (last 1 s of
spot return = momentum); gbmA = extra null, UNSIGNED activity only (counts, |returns|, dt, max size) - it
separates "knows a move is coming" (volatility timing) from "knows which way".
Thresholds for precision/recall and lead time are FLAG RATES fixed on the TRAIN scores (in-sample), then the
realised test flag rate is reported next to them.
Writes <out>/scores.npz (5 bps scores for the lead analysis) and <out>/metrics.json."""
import argparse, glob, json, os, time, numpy as np, lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser(); ap.add_argument('--data', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--ntrain', type=int, default=2_000_000)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
files = sorted(glob.glob(os.path.join(a.data, '2026-*.npz'))); days = [os.path.basename(f)[:10] for f in files]
Z = [np.load(f) for f in files]
names = [str(x) for x in Z[0]['names']]
KEEP = slice(40, 864000 - 10)                              # 4 s warm-up (r3000 needs 3 s), 1 s of label tail
X = [np.nan_to_num(z['X'][KEEP]) for z in Z]
fwd = [{k: z[k][KEEP] for k in z.files if k[0] in 'rud' and k[1:].isdigit()} for z in Z]
RATES = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2]
TGT = [(d, x, h) for d in ('up', 'dn') for x in (2, 5, 10) for h in (300, 500, 1000)]
I_NULL = [names.index('s_r1000')]
ACT = [n for n in names if n[2] in 'n' or n.endswith(('dt', 'maxq', 'acc100', 'acc250'))]
I_ACT = [names.index(n) for n in ACT]


def lab(i, d, x, h): return (fwd[i][('u' if d == 'up' else 'd') + str(h)] >= x)


def slog(M): return np.sign(M) * np.log1p(np.abs(M))


def act_feats(M):                                          # unsigned: counts/dt/maxq/acc + |r|
    ir = [names.index(n) for n in names if n[2] == 'r' and n[3:].isdigit()]
    return np.column_stack([M[:, I_ACT], np.abs(M[:, ir])])


MODELS = ['lr', 'lr0', 'gbm', 'gbm0', 'gbmA']
GBP = dict(objective='binary', learning_rate=0.05, num_leaves=31, min_child_samples=300, feature_fraction=0.8,
           bagging_fraction=0.8, bagging_freq=1, lambda_l2=10, verbose=-1, num_threads=4)


def fit_predict(kind, Xtr, ytr, w, Xcal, Xte):
    """Train on all positives + sampled negatives (weights undo the sampling); Xcal = uniform train rows
    used only to fix the flag-rate thresholds."""
    if kind.startswith('lr'):
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        m = LogisticRegression(C=1.0, max_iter=400).fit((Xtr - mu) / sd, ytr, sample_weight=w)
        return m.decision_function((Xcal - mu) / sd), m.decision_function((Xte - mu) / sd)
    b = lgb.train(GBP, lgb.Dataset(Xtr, ytr.astype(np.float32), weight=w), num_boost_round=200)
    return b.predict(Xcal, raw_score=True), b.predict(Xte, raw_score=True)


def feats(kind, M):
    if kind == 'lr': return slog(M)
    if kind in ('lr0', 'gbm0'): return M[:, I_NULL]
    if kind == 'gbmA': return act_feats(M)
    return M


rng = np.random.default_rng(7)
res = {'days': days, 'folds': [], 'names': names}
keep_scores = {}                                           # 5 bps, H 500/1000, every model: for lead analysis
test_idx = list(range(1, len(days)))
for k in test_idx:
    t0 = time.time()
    Xtr_all = np.concatenate(X[:k]); ntr = len(Xtr_all); Xte = X[k]
    cal = np.sort(rng.choice(ntr, min(500_000, ntr), replace=False)); Xcal = Xtr_all[cal]
    fold = {'test': days[k], 'train': days[:k], 'n_train': int(ntr), 'cells': {}}
    for (d, x, h) in TGT:
        yall = np.concatenate([lab(i, d, x, h) for i in range(k)]); yte = lab(k, d, x, h)
        pos = np.flatnonzero(yall); neg = np.flatnonzero(~yall)
        nn = min(len(neg), a.ntrain // 4); negs = rng.choice(neg, nn, replace=False)
        sel = np.sort(np.r_[pos, negs]); ytr = yall[sel]
        w = np.where(ytr, 1.0, len(neg) / nn)
        Xtr = Xtr_all[sel]
        cell = {'pos_train': int(len(pos)), 'pos_test': int(yte.sum())}
        lead_t = (h == 1000) or (x == 5 and h == 500)
        for mk in MODELS:
            if len(pos) < 20 or (mk == 'gbmA' and not lead_t):
                cell[mk] = None; continue
            ptr, pte = fit_predict(mk, feats(mk, Xtr), ytr, w, feats(mk, Xcal), feats(mk, Xte))
            thr = [float(np.quantile(ptr, 1 - r)) for r in RATES]
            cell[mk] = {'auc': float(roc_auc_score(yte, pte)) if 0 < yte.sum() < len(yte) else None, 'thr': thr,
                        'flags': [int((pte >= t).sum()) for t in thr],
                        'tp': [int(((pte >= t) & yte).sum()) for t in thr]}
            if lead_t and mk != 'lr0':
                keep_scores[(k, d, x, h, mk)] = pte.astype(np.float32)
        fold['cells'][f'{d}_{x}_{h}'] = cell
    res['folds'].append(fold)
    print(days[k], 'done', round(time.time() - t0), 's', flush=True)
    json.dump(res, open(os.path.join(a.out, 'metrics.json'), 'w'))
np.savez(os.path.join(a.out, 'scores.npz'), **{'|'.join(map(str, key)): v for key, v in keep_scores.items()})
