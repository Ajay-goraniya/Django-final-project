#!/usr/bin/env python3
"""train_v12.py -- more days. Same design as v10, trained across every day on
disk (original 8 + extra days without order-book depth), leave-one-day-out.
Scored ONLY on the original 8 days so the comparison with v10 is like-for-like.

Depth features are absent on the extra days, so the candidate feature set
drops them; the cost of dropping them is measured on the 8 days first."""
import json, pathlib, sys, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss
warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from train import trade_sim, summarize, cost, BASE

ROOT = pathlib.Path(__file__).resolve().parent
ORIG = ["2026-08-29", "2026-08-30", "2026-08-31", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
F = pd.read_parquet(ROOT / (sys.argv[1] if len(sys.argv) > 1 else "features_all.parquet"))
pv = F.p_venue.clip(0.02, 0.98)
F["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
F["mv_x_sec"] = F.move_bps * F.sec_left / 300.0
F["lv_x_sec"] = F.lv * F.sec_left / 300.0
DEPTH = ["spread_bps", "imb5", "imb20", "micro_bps"]
V10 = BASE + ["p_venue", "lv", "mv_x_sec", "lv_x_sec"]
NODEPTH = [c for c in V10 if c not in DEPTH]
y = F.y.values; g = F.date.values
orig = F.date.isin(ORIG).values
mb = ((F.is_book == 1) & F.p_venue.notna()).values & orig
pvc = F.p_venue.clip(0.01, 0.99).values
VENUE_LL = log_loss(y[mb], pvc[mb])
mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=4000))


def lodo(X, rows_mask):
    """LODO over the days present in rows_mask; predictions for every row in it."""
    oof = np.full(len(y), np.nan)
    days = np.unique(g[rows_mask])
    for d in days:
        tr = rows_mask & (g != d); te = rows_mask & (g == d)
        Xtr, ytr, gtr = X[tr], y[tr], g[tr]
        inner = np.full(len(ytr), np.nan)
        for itr, ite in GroupKFold(n_splits=min(4, len(np.unique(gtr)))).split(Xtr, ytr, gtr):
            inner[ite] = mk().fit(Xtr[itr], ytr[itr]).predict_proba(Xtr[ite])[:, 1]
        iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip").fit(inner, ytr)
        oof[te] = iso.predict(mk().fit(Xtr, ytr).predict_proba(X[te])[:, 1])
    return oof


def score(name, oof):
    m = orig & ~np.isnan(oof)
    llb = log_loss(y[mb & m], oof[mb & m]); lla = log_loss(y[m], oof[m])
    sub = F[m]; po = oof[m]
    s20 = summarize(trade_sim(sub, po, 0.20), sub.epoch.nunique())
    ps = np.maximum(po, 1 - po); a = ps >= 0.85
    sa = summarize(trade_sim(sub[a], po[a], 0.02), sub.epoch.nunique())
    print(f"  {name:36} book {llb:.4f} {'BEATS' if llb < VENUE_LL else 'no   '}  all {lla:.4f}  "
          f"| pnl.20 n={s20['trades']} acc {s20['acc']}% ${s20['pnl']:+.0f} t={s20['t']} "
          f"| acc.85/.02 n={sa['trades']} acc {sa['acc']}% ${sa['pnl']:+.0f}")
    return llb, oof


if __name__ == "__main__":
    extra = sorted(set(g) - set(ORIG))
    print(f"{len(F):,} rows, {F.epoch.nunique()} candles, {len(np.unique(g))} days ({len(extra)} extra)   venue book logloss {VENUE_LL:.4f}\n")
    res = {}
    res["v10 feats, 8 days (reference)"] = score("v10 feats, 8 days (reference)", lodo(F[V10].fillna(0).values, orig))
    res["no-depth feats, 8 days"] = score("no-depth feats, 8 days", lodo(F[NODEPTH].fillna(0).values, orig))
    if extra:
        allm = np.ones(len(y), bool)
        res[f"no-depth feats, {len(np.unique(g))} days"] = score(f"no-depth feats, {len(np.unique(g))} days", lodo(F[NODEPTH].fillna(0).values, allm))
        # depth features kept, zero on extra days (lets the model use depth when present)
        res[f"v10 feats (depth=0 on extra), {len(np.unique(g))} days"] = score(f"v10 feats (depth=0 on extra), {len(np.unique(g))} days", lodo(F[V10].fillna(0).values, allm))
    best = min(res, key=lambda k: res[k][0])
    print(f"\nBEST on the 8 original days by real-book log-loss: {best}  ({res[best][0]:.4f})")
    np.save(ROOT / "v12_best_oof.npy", res[best][1])
    json.dump({"best": best, "scores": {k: float(v[0]) for k, v in res.items()}, "venue": VENUE_LL,
               "extra_days": extra}, open(ROOT / "train_v12_summary.json", "w"), indent=1)
