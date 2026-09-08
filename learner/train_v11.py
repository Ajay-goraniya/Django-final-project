#!/usr/bin/env python3
"""train_v11.py -- compare designs on the extended feature set, same honest
protocol as v10 (leave-one-day-out, isotonic fitted inside the fold, judged
first on real-book log-loss against the venue's own price, then on the
out-of-sample trading frontier). Exports the winner if it beats v10."""
import json, pathlib, sys, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss
import lightgbm as lgb
warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from train import trade_sim, summarize, cost, BASE

ROOT = pathlib.Path(__file__).resolve().parent
F = pd.read_parquet(ROOT / "features.parquet")
pv = F.p_venue.clip(0.02, 0.98)
F["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
F["mv_x_sec"] = F.move_bps * F.sec_left / 300.0
F["lv_x_sec"] = F.lv * F.sec_left / 300.0
pp = F.phys_p.clip(0.02, 0.98)
F["lphys"] = np.log(pp / (1 - pp))
F["phys_minus_venue"] = (F.phys_p - F.p_venue).fillna(0.0)     # fair value vs market: the disagreement
F["dpv_x_sec"] = F.dpv30.fillna(0.0) * F.sec_left / 300.0
F["venue_spread"] = F.venue_spread.fillna(F.venue_spread.median())
y = F.y.values; g = F.date.values
mb = ((F.is_book == 1) & F.p_venue.notna()).values
pvc = F.p_venue.clip(0.01, 0.99).values
VENUE_LL = log_loss(y[mb], pvc[mb])

V10 = BASE + ["p_venue", "lv", "mv_x_sec", "lv_x_sec"]
NEW = ["dpv15", "dpv30", "dpv60", "venue_spread", "phys_p", "lphys", "phys_minus_venue",
       "ret120", "ret180", "vwap_dev", "dpv_x_sec"]
V11 = V10 + NEW


def logit(C=0.3):
    return lambda: make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=4000))


def gbm():
    return lambda: lgb.LGBMClassifier(n_estimators=600, learning_rate=0.02, num_leaves=7,
                                      min_child_samples=120, subsample=0.7, subsample_freq=1,
                                      colsample_bytree=0.7, reg_lambda=20.0, reg_alpha=1.0, verbose=-1)


def lodo(X, mk, per_offset=None):
    """LODO with inner-grouped isotonic. per_offset: array of offsets -> one
    model per decision second (captures time-varying coefficients)."""
    oof = np.full(len(y), np.nan)
    for d in np.unique(g):
        tr, te = g != d, g == d
        keys = [None] if per_offset is None else np.unique(per_offset)
        for k in keys:
            trk = tr if k is None else tr & (per_offset == k)
            tek = te if k is None else te & (per_offset == k)
            Xtr, ytr, gtr = X[trk], y[trk], g[trk]
            inner = np.full(len(ytr), np.nan)
            for itr, ite in GroupKFold(n_splits=4).split(Xtr, ytr, gtr):
                inner[ite] = mk().fit(Xtr[itr], ytr[itr]).predict_proba(Xtr[ite])[:, 1]
            iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip").fit(inner, ytr)
            oof[tek] = iso.predict(mk().fit(Xtr, ytr).predict_proba(X[tek])[:, 1])
    return oof


def report(name, oof):
    llb = log_loss(y[mb], oof[mb]); lla = log_loss(y, oof)
    s = summarize(trade_sim(F, oof, 0.20), F.epoch.nunique())
    print(f"  {name:32} book {llb:.4f} {'BEATS venue' if llb < VENUE_LL else 'no'}   all {lla:.4f}   "
          f"thr.20: n={s['trades']} acc {s['acc']}% PnL ${s['pnl']:+.0f} t={s['t']} book${s['book_pnl']:+.0f}")
    return llb


if __name__ == "__main__":
    print(f"{len(F):,} rows   venue real-book logloss {VENUE_LL:.4f}   v10 reference 0.5042\n")
    designs = {}
    designs["A logit v10 feats"] = lodo(F[V10].fillna(0).values, logit(0.3))
    designs["B logit v11 feats"] = lodo(F[V11].fillna(0).values, logit(0.3))
    designs["C logit v11 C=0.1"] = lodo(F[V11].fillna(0).values, logit(0.1))
    designs["D lgbm v11"] = lodo(F[V11].fillna(0).values, gbm())
    designs["E per-offset logit v11"] = lodo(F[V11].fillna(0).values, logit(0.3), per_offset=F.offset.values)
    scores = {k: report(k, v) for k, v in designs.items()}
    best_logit = min([k for k in scores if "logit" in k], key=scores.get)
    designs["F blend best-logit + lgbm"] = 0.5 * designs[best_logit] + 0.5 * designs["D lgbm v11"]
    scores["F blend best-logit + lgbm"] = report("F blend best-logit + lgbm", designs["F blend best-logit + lgbm"])
    best = min(scores, key=scores.get)
    print(f"\nWINNER by real-book log-loss: {best}  ({scores[best]:.4f}) vs v10 0.5042\n")
    oof = designs[best]

    # ---------------- frontiers: EV threshold (frequency dial) and accuracy-first
    n_c = F.epoch.nunique()
    print("EV-THRESHOLD FRONTIER (out-of-sample, $10 flat, 1 trade/candle)")
    print(f"  {'thr':>5}{'trades/day':>11}{'acc':>8}{'ask':>7}{'PnL 8d':>9}{'/trade':>8}{'t':>6}{'book$':>8}{'days+':>6}")
    days = F[["epoch", "date"]].drop_duplicates()
    for thr in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50):
        t = trade_sim(F, oof, thr); s = summarize(t, n_c)
        if s["trades"] < 10: continue
        dp = (t.merge(days, on="epoch").groupby("date").pnl.sum() > 0).sum()
        print(f"  {thr:>5.2f}{s['trades']/8:>11.1f}{s['acc']:>7.1f}%{s['ask']:>7}{s['pnl']:>+9.0f}{s['per_trade']:>+8.2f}{str(s['t']):>6}{s['book_pnl']:>+8.0f}{dp:>4}/8")
    print("\nACCURACY-FIRST FRONTIER: trade only when model confidence p_side >= P (then still require EV > 0)")
    print(f"  {'P':>5}{'trades/day':>11}{'acc':>8}{'ask':>7}{'PnL 8d':>9}{'/trade':>8}{'t':>6}")
    for P in (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        ps = np.maximum(oof, 1 - oof)
        sub = F[ps >= P]
        if len(sub) < 10: continue
        t = trade_sim(sub, oof[ps >= P], 0.0); s = summarize(t, n_c)
        if s["trades"] < 10: continue
        print(f"  {P:>5.2f}{s['trades']/8:>11.1f}{s['acc']:>7.1f}%{s['ask']:>7}{s['pnl']:>+9.0f}{s['per_trade']:>+8.2f}{str(s['t']):>6}")

    out = pd.read_parquet(ROOT / "oof_predictions.parquet")
    for k, v in designs.items():
        out["v11_" + k.split()[0]] = v
    out["v11_best"] = oof
    out.to_parquet(ROOT / "oof_predictions.parquet", index=False)
    json.dump({"winner": best, "scores": {k: float(v) for k, v in scores.items()}, "venue": VENUE_LL,
               "features_v11": V11}, open(ROOT / "train_v11_summary.json", "w"), indent=1)
    print("\nsaved oof + summary")
