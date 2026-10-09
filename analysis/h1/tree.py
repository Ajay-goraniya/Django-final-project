"""Task 7: continuous intra-candle reversal model, evaluated at every second.

Walk-forward: fit on the first half of the days, evaluate on the second half only.
Target: P(close > open | path up to t).  No fixed offsets - every t is modelled.
"""
import numpy as np, datetime
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

d = np.load('paths.npz'); cid = d['cid']; P = d['paths'].astype(np.float64)
o, c = P[:, 0], P[:, -1]
graded = c != o
s = np.sign(P - o[:, None])
nz = np.where(s == 0, np.nan, s)
for i in range(1, 300):
    nz[:, i] = np.where(np.isnan(nz[:, i]), nz[:, i - 1], nz[:, i])
nz = np.nan_to_num(nz)
# crossings AFTER the opening side is established (so k=0 means "never left it")
first = np.argmax(nz != 0, axis=1)
chg = np.zeros_like(nz)
chg[:, 1:] = (np.diff(nz, axis=1) != 0)
for i in range(len(chg)):
    chg[i, :first[i] + 1] = 0
cum = np.cumsum(chg, axis=1)
y = (c > o).astype(int)
dist = (P - o[:, None]) / o[:, None] * 1e4           # signed bps from open
run = np.zeros_like(P)                                # seconds since last crossing
for t in range(1, 300):
    run[:, t] = np.where(chg[:, t] > 0, 0, run[:, t - 1] + 1)
hi = np.maximum.accumulate(P, axis=1); lo = np.minimum.accumulate(P, axis=1)
rng = (hi - lo) / o[:, None] * 1e4                    # realised range so far, bps

mid = cid[len(cid) // 2]
tr = graded & (cid < mid); te = graded & (cid >= mid)
print(f"train {tr.sum()} candles (07-01..), test {te.sum()} (..09-09) - walk-forward, no refit on test")

def feats(t, m):
    return np.column_stack([nz[m, t], dist[m, t], np.minimum(cum[m, t], 6),
                            np.log1p(run[m, t]), rng[m, t], np.full(m.sum(), t / 300.0)])

print(f"\n{'t':>4} {'AUC sign only':>14} {'AUC model':>10} {'acc sign':>9} {'acc model':>10} {'P(flip)':>8} {'n test':>7}")
rows = []
for t in list(range(5, 60, 5)) + list(range(60, 301, 20)):
    t = min(t, 299)
    Xtr, ytr = feats(t, tr), y[tr]
    Xte, yte = feats(t, te), y[te]
    m = LogisticRegression(max_iter=2000).fit(Xtr, ytr)
    p = m.predict_proba(Xte)[:, 1]
    auc_m = roc_auc_score(yte, p)
    auc_s = roc_auc_score(yte, nz[te, t])
    acc_s = np.mean((nz[te, t] > 0) == (yte == 1))
    acc_m = np.mean((p > 0.5) == (yte == 1))
    rows.append((t, auc_s, auc_m, acc_s, acc_m))
    print(f"{t:>4} {auc_s:>14.4f} {auc_m:>10.4f} {acc_s*100:>8.1f}% {acc_m*100:>9.1f}% "
          f"{(1-acc_s)*100:>7.1f}% {te.sum():>7}")
np.save('auc_by_t.npy', np.array(rows))
