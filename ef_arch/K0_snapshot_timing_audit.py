#!/usr/bin/env python3
"""
K0 -- snapshot-timing audit for any table of candidate feature vectors.

Run BEFORE K1/K2/K3. Those tests assume the feature vector was captured at a
causal decision moment. This one checks that assumption.

What it does on a Build36-style ef_candidates table:
  1. Compares the row timestamp with the timestamp encoded INSIDE the feature
     dict (ef_phase_second / ef_seconds_left). A gap means the features were
     captured later than the row claims.
  2. Reports the base hit-rate as a function of snapshot delay after birth.
     A monotone relationship means snapshot timing is a label proxy.
  3. Fits a ONE-feature model on `seconds_left` alone, train early / test
     late, and reports AUC and precision@K. If this rivals the full model,
     the full model is learning the snapshot timing, not the market.

Usage:  python3 K0_snapshot_timing_audit.py <candidates.sqlite3> [train_candles=120] [K=55]
"""
import json, sqlite3, sys
import numpy as np

CANDLE_MS = 300_000

def auc(p, y):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    npos = y.sum(); nneg = len(y) - npos
    return (r[y == 1].sum() - npos * (npos + 1) / 2) / max(npos * nneg, 1)

def logistic(Xtr, ytr, Xte, l2=0.01, iters=500, lr=0.5):
    mu, sd = Xtr.mean(0), np.maximum(Xtr.std(0), 1e-9)
    A = np.column_stack([np.ones(len(Xtr)), (Xtr - mu) / sd])
    B = np.column_stack([np.ones(len(Xte)), (Xte - mu) / sd])
    w = np.zeros(A.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-A @ w)); w += lr * (A.T @ (ytr - p) / len(ytr) - l2 * w)
    return 1 / (1 + np.exp(-B @ w))

def main(db, train_candles=120, K=55):
    c = sqlite3.connect(db)
    rows = c.execute("select candle_id, direction, actual, ts_ms, features from ef_candidates").fetchall()
    if not rows:
        print("no ef_candidates rows"); return
    W0 = min(r[0] for r in rows); H0 = W0 + train_candles * CANDLE_MS
    R = []
    for cid, d, a, ts, feat in rows:
        f = json.loads(feat) if feat else {}
        ph = f.get("ef_phase_second"); left = f.get("ef_seconds_left"); birth = f.get("ef_candidate_birth_seconds")
        if ph is None or left is None:
            continue
        R.append(dict(cid=cid, y=1.0 if d == a else 0.0, hold=cid >= H0,
                      row_off=(ts - cid) / 1000.0, ph=float(ph), left=float(left),
                      delay=float(ph) - float(birth if birth is not None else ph)))
    row_off = np.array([r["row_off"] for r in R]); ph = np.array([r["ph"] for r in R])
    delay = np.array([r["delay"] for r in R]); y = np.array([r["y"] for r in R])

    print("=" * 70); print("K0  SNAPSHOT TIMING AUDIT"); print("=" * 70)
    print(f"rows: {len(R)}   train candles: {train_candles}   holdout rows: {sum(r['hold'] for r in R)}")
    print("\n1. row timestamp vs feature-dict timestamp (seconds into candle)")
    gap = ph - row_off
    for q in (50, 75, 90, 99):
        print(f"   p{q:<3} row_off={np.percentile(row_off,q):6.1f}  feature_phase={np.percentile(ph,q):6.1f}  gap={np.percentile(gap,q):6.1f}")
    print(f"   rows whose features are >60s later than the row timestamp: {int((gap>60).sum())} ({100*(gap>60).mean():.1f}%)")
    print("   -> any gap means the stored features are NOT from the row's own moment.")

    print("\n2. base hit-rate by snapshot delay after candidate birth")
    for lo, hi in ((0, 5), (5, 30), (30, 60), (60, 120), (120, 400)):
        m = (delay >= lo) & (delay < hi)
        if m.sum():
            print(f"   delay {lo:>3}-{hi:<3}s  n={int(m.sum()):>4}  hit-rate={100*y[m].mean():5.1f}%")
    print("   -> a monotone trend means snapshot timing is a label proxy.")

    tr = np.array([not r["hold"] for r in R]); te = ~tr
    left = np.array([r["left"] for r in R])
    p1 = logistic(left[tr].reshape(-1, 1), y[tr], left[te].reshape(-1, 1))
    top = np.argsort(-p1)[:K]
    print(f"\n3. ONE-feature model, seconds_left only, train<{train_candles} candles / test rest")
    print(f"   AUC={auc(p1, y[te]):.3f}   precision@{K}={100*y[te][top].mean():5.1f}%   holdout base={100*y[te].mean():.1f}%")
    print("   -> if this rivals your full model, the full model learned snapshot timing.")

    print("\nVERDICT:")
    bad = (gap > 60).mean() > 0.10 or abs(np.corrcoef(delay, y)[0, 1]) > 0.2
    print("   FAIL - this table cannot evaluate a decision-time ranker; re-capture features at birth"
          if bad else "   PASS - snapshot timing does not look like a label proxy")

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], int(a[1]) if len(a) > 1 else 120, int(a[2]) if len(a) > 2 else 55)
