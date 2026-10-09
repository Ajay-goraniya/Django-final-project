#!/usr/bin/env python3
"""R-12 LITERAL PIPELINE CHECK.

V pushed v10's OWN training table (learner/live_backup/v10_features_8days.parquet.gz,
22,720 rows x 46 cols, 2026-08-29..09-06). model_v10.json says n_rows=22720 and lists
exactly those 8 dates, so this is the real input, not a reconstruction of it.

The question this answers is NOT "is a big-history model better" - R-12/R-12c/step-3
already answered that (it is not). It is the narrower one that has to pass before any
of those comparisons mean anything: DOES MY REPRODUCTION OF THE RECIPE ACTUALLY
REPRODUCE THE DEPLOYED ARTIFACT? Every earlier R-12 arm trained "v10's recipe" from my
own reading of train.py/finalize.py. If that reading were wrong, every A/B in R-12 was
comparing a big model against something that is not v10.

So this refits finalize.py's export path on finalize.py's own input and compares the
resulting scaler / coefficients / isotonic knots against the shipped model_v10.json
number by number. A match means the recipe I have been using is v10's recipe.
"""
import json, pathlib, sys
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss, brier_score_loss

ROOT = pathlib.Path('/home/user/Django-final-project')
F = pd.read_parquet('/tmp/claude-0/r12p/feat8.parquet')
SHIP = json.load(open(ROOT / 'learner/model_v10.json'))

BASE = ["move_bps","ret5","ret15","ret30","ret60","rv60","range_bps","pos_in_range",
        "dist_hi_bps","dist_lo_bps","spot_imb15","spot_imb60","ofi5","ofi15","ofi60",
        "perp_n15","basis_bps","spread_bps","imb5","imb20","micro_bps","prev1_bps",
        "prev2_bps","sec_left","hod_sin","hod_cos"]
FEATS = BASE + ["p_venue","lv","mv_x_sec","lv_x_sec"]
C = 0.3
FEE = 0.07


def add_derived(d):                       # verbatim from learner/finalize.py
    d = d.copy()
    pv = d.p_venue.clip(0.02, 0.98)
    d["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
    d["mv_x_sec"] = d.move_bps * d.sec_left / 300.0
    d["lv_x_sec"] = d.lv * d.sec_left / 300.0
    return d


def mk():
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000))


F = add_derived(F)
y = F.y.values
g = F.date.values
X = F[FEATS].fillna(0.0).values
print("=" * 78)
print("R-12 pipeline check  -- refit finalize.py's export path on v10's own table")
print("=" * 78)
print(f"  rows {len(y)} (model_v10.json says {SHIP['n_rows']}), candles {F.epoch.nunique()} "
      f"(says {SHIP['n_candles']}), days {len(set(g))}")
print(f"  feature order identical to the shipped list: {FEATS == SHIP['features']}")

# ---- the export fit: inner GroupKFold(8) OOF -> isotonic, then full-data logistic
inner = np.full(len(y), np.nan)
for itr, ite in GroupKFold(n_splits=8).split(X, y, g):
    inner[ite] = mk().fit(X[itr], y[itr]).predict_proba(X[ite])[:, 1]
iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip").fit(inner, y)
pipe = mk().fit(X, y)
sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]

def cmp(name, mine, theirs):
    a, b = np.asarray(mine, float), np.asarray(theirs, float)
    if a.shape != b.shape:
        print(f"  {name:16} SHAPE MISMATCH {a.shape} vs {b.shape}")
        return None
    d = np.abs(a - b)
    rel = d / np.maximum(np.abs(b), 1e-12)
    print(f"  {name:16} max abs diff {d.max():.3e}   max rel diff {rel.max():.3e}")
    return d.max()

print("\n  PARAMETER PARITY vs the shipped model_v10.json")
worst = max(x for x in [
    cmp("scaler_mean", sc.mean_, SHIP['scaler_mean']),
    cmp("scaler_scale", sc.scale_, SHIP['scaler_scale']),
    cmp("coef", lr.coef_[0], SHIP['coef']),
    cmp("intercept", [lr.intercept_[0]], [SHIP['intercept']]),
    cmp("iso_x", iso.X_thresholds_, SHIP['iso_x']),
    cmp("iso_y", iso.y_thresholds_, SHIP['iso_y']),
] if x is not None)
print(f"  WORST over every exported number: {worst:.3e}")

# ---- the two derived numbers the file also carries, recomputed the same way
def lodo(X, y, g):
    oof = np.full(len(y), np.nan)
    for d in np.unique(g):
        tr, te = g != d, g == d
        Xtr, ytr, gtr = X[tr], y[tr], g[tr]
        ip = np.full(len(ytr), np.nan)
        for itr, ite in GroupKFold(n_splits=4).split(Xtr, ytr, gtr):
            ip[ite] = mk().fit(Xtr[itr], ytr[itr]).predict_proba(Xtr[ite])[:, 1]
        cal = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip").fit(ip, ytr)
        oof[te] = cal.predict(mk().fit(Xtr, ytr).predict_proba(X[te])[:, 1])
    return oof

oof = lodo(X, y, g)
mb = (F.is_book == 1) & F.p_venue.notna()
pv = F.p_venue.clip(0.01, 0.99)
ll_mine = log_loss(y[mb], oof[mb])
ll_venue = log_loss(y[mb], pv[mb])
print("\n  DERIVED NUMBERS (leave-one-day-out, real-book rows only)")
print(f"    oos_logloss_book   mine {ll_mine:.6f}   shipped {SHIP['oos_logloss_book']:.6f}   "
      f"diff {abs(ll_mine - SHIP['oos_logloss_book']):.3e}")
print(f"    venue_logloss_book mine {ll_venue:.6f}   shipped {SHIP['venue_logloss_book']:.6f}   "
      f"diff {abs(ll_venue - SHIP['venue_logloss_book']):.3e}")
e = [float(F.rv60.quantile(1/3)), float(F.rv60.quantile(2/3))]
print(f"    rv60_edges         mine {e[0]:.10f}/{e[1]:.10f}")
print(f"                    shipped {SHIP['regime']['rv60_edges'][0]:.10f}/{SHIP['regime']['rv60_edges'][1]:.10f}")

# ---- and the thing the user keeps asking: on v10's OWN days, out of sample,
#      how does this model do against the venue price alone?  (R-13's question)
print("\n  R-13 CROSS-CHECK on v10's own training window, out of sample (LODO):")
b_mine = brier_score_loss(y[mb], oof[mb])
b_ven = brier_score_loss(y[mb], pv[mb])
acc_mine = ((oof[mb] >= .5).astype(int) == y[mb]).mean()
acc_ven = ((pv[mb] >= .5).astype(int) == y[mb]).mean()
agree = ((oof[mb] >= .5) == (pv[mb] >= .5)).mean()
print(f"    n={int(mb.sum())} real-book rows")
print(f"    model   acc {acc_mine:.4f}  Brier {b_mine:.4f}  logloss {ll_mine:.4f}")
print(f"    venue   acc {acc_ven:.4f}  Brier {b_ven:.4f}  logloss {ll_venue:.4f}")
print(f"    they point the same way on {agree*100:.1f}% of rows; corr(p, p_venue) "
      f"{np.corrcoef(oof[mb], pv[mb])[0,1]:.4f}")
