#!/usr/bin/env python3
"""finalize.py -- lock the chosen design, export it, and produce the reports.

Design (chosen by out-of-sample real-book log-loss, not by PnL):
  L2 logistic regression on 26 causal BTC microstructure features + the venue's
  implied probability (raw and as a logit) + two interactions with time left,
  followed by isotonic calibration. Small, convex, no hidden state, cannot
  overfit its way to false confidence the way the in-engine learners did.

Everything reported as out-of-sample uses leave-one-day-out predictions.
The exported parameters are fitted on all 8 days for live use.
"""
import json, pathlib, sys
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import train as T
from train import trade_sim, summarize, df as F, BASE, cost
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss

ROOT = pathlib.Path(__file__).resolve().parent
C = 0.3


def add_derived(d):
    d = d.copy()
    pv = d.p_venue.clip(0.02, 0.98)
    d["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
    d["mv_x_sec"] = d.move_bps * d.sec_left / 300.0
    d["lv_x_sec"] = d.lv * d.sec_left / 300.0
    return d


FEATS = BASE + ["p_venue", "lv", "mv_x_sec", "lv_x_sec"]
F = add_derived(F)
y = F.y.values; g = F.date.values
T.make_model = lambda kind: make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000))
X = F[FEATS].fillna(0.0).values

# ---------------- out-of-sample predictions (leave-one-day-out)
oof = T.lodo_predict(X, y, g, "final")
mb = (F.is_book == 1) & F.p_venue.notna()
pv = F.p_venue.clip(0.01, 0.99)
print(f"FINAL DESIGN  logloss real-book {log_loss(y[mb], oof[mb]):.4f}   venue {log_loss(y[mb], pv[mb]):.4f}   "
      f"all rows {log_loss(y, oof):.4f}   venue all {log_loss(y[F.p_venue.notna()], pv[F.p_venue.notna()]):.4f}")
cal = F.assign(p=oof, bin=pd.cut(oof, [0, .2, .35, .45, .55, .65, .8, 1]))
print("calibration (claimed vs actual):")
print(cal.groupby("bin", observed=True).agg(n=("y", "size"), claimed=("p", "mean"), actual=("y", "mean")).round(3).to_string())

# ---------------- regime: does the edge depend on volatility? (sets the frequency dial per regime)
print("\nREGIME  realized vol (rv60, bps) tercile at decision time -> best threshold per regime")
F["rv_bin"] = pd.qcut(F.rv60, 3, labels=["low", "mid", "high"])
regime_thr = {}
for r, gsub in F.groupby("rv_bin", observed=True):
    best = None
    for thr in (0.10, 0.15, 0.20, 0.25, 0.30, 0.40):
        t = trade_sim(gsub, oof[gsub.index.values], thr)
        s = summarize(t, gsub.epoch.nunique())
        if s["trades"] >= 30 and (best is None or (s["t"] or -9) > best[1]):
            best = (thr, s["t"], s)
    if best:
        regime_thr[r] = best[0]
        s = best[2]
        print(f"   {r:5} rv60 <= {gsub.rv60.max():.2f}: thr {best[0]:.2f}  n={s['trades']} acc {s['acc']}% PnL ${s['pnl']:+.0f} t={s['t']}")
rv_edges = [float(F.rv60.quantile(1/3)), float(F.rv60.quantile(2/3))]

# ---------------- reports: week (OOF) and the fixed 100-candle sample (OOF)
sel = json.load(open(ROOT.parent / "week_replay" / "candles100.json"))["candles"]
eps = {int(c["epoch"]) for c in sel}
print("\nREPORT  out-of-sample, $10 flat, one trade per candle, buy at the venue ask")
print(f"{'':14}{'thr':>5}{'trades':>8}{'freq/day':>9}{'acc':>7}{'ask':>7}{'PnL $':>9}{'/trade':>8}{'t':>6}{'book$':>8}")
for lbl, sub, pp, ncand, ndays in (("FULL 8 DAYS", F, oof, F.epoch.nunique(), 8),
                                    ("100 CANDLES", F[F.epoch.isin(eps)], oof[F.epoch.isin(eps).values], 100, 8)):
    for thr in (0.0, 0.15, 0.20, 0.30):
        s = summarize(trade_sim(sub, pp, thr), ncand)
        if s["trades"]:
            print(f"{lbl:14}{thr:>5.2f}{s['trades']:>8}{s['trades']/ndays:>9.1f}{s['acc']:>6}%{s['ask']:>7}{s['pnl']:>+9.2f}{s['per_trade']:>+8.3f}{str(s['t']):>6}{s['book_pnl']:>+8.2f}")
    print()

# ---------------- fit on everything and export for live use
inner = np.full(len(y), np.nan)
for itr, ite in GroupKFold(n_splits=8).split(X, y, g):
    inner[ite] = T.make_model("x").fit(X[itr], y[itr]).predict_proba(X[ite])[:, 1]
iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip").fit(inner, y)
pipe = T.make_model("x").fit(X, y)
sc, lr = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
export = dict(
    design="L2 logistic on causal BTC microstructure + venue implied probability, isotonic-calibrated",
    features=FEATS, scaler_mean=sc.mean_.tolist(), scaler_scale=sc.scale_.tolist(),
    coef=lr.coef_[0].tolist(), intercept=float(lr.intercept_[0]),
    iso_x=iso.X_thresholds_.tolist(), iso_y=iso.y_thresholds_.tolist(),
    fee_rate=T.FEE, ev_threshold_default=0.25,
    regime=dict(rv60_edges=rv_edges, thresholds={k: float(v) for k, v in regime_thr.items()}),
    oos_logloss_book=float(log_loss(y[mb], oof[mb])), venue_logloss_book=float(log_loss(y[mb], pv[mb])),
    trained_on=sorted(set(g.tolist())), n_rows=int(len(y)), n_candles=int(F.epoch.nunique()),
)
json.dump(export, open(ROOT / "model_v10.json", "w"), indent=1)
out = pd.read_parquet(ROOT / "oof_predictions.parquet"); out["final"] = oof
out.to_parquet(ROOT / "oof_predictions.parquet", index=False)
print("coefficients (standardized; sign = direction of effect on P(UP)):")
for f_, c_ in sorted(zip(FEATS, lr.coef_[0]), key=lambda x: -abs(x[1]))[:12]:
    print(f"   {f_:14} {c_:+.3f}")
print(f"\nexported model_v10.json  |  oof column 'final' saved")
