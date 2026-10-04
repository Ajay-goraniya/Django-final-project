#!/usr/bin/env python3
"""
train.py -- offline learners for the BTC 5m UP/DOWN outcome, evaluated honestly.

Protocol
  * leave-one-DAY-out: for each of the 8 days, train on the other 7, predict
    this one. Every prediction is out-of-sample; nothing ever sees its own day.
  * calibration is fitted INSIDE the training fold (inner grouped CV), so the
    probability the model reports is what it would report live.
  * the benchmark is not accuracy, it is the venue's own implied probability:
    a model that cannot beat the market's price on log-loss has no edge.
  * the trading test buys the side the model favours at the venue's ask at
    that second, only when the fee-adjusted expected value clears a threshold.
    The threshold is the frequency dial.
"""
import json, pathlib, sys, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import GroupKFold
from sklearn.metrics import log_loss, brier_score_loss
import lightgbm as lgb
warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parent
df = pd.read_parquet(ROOT / "features.parquet")
FEE = 0.07
cost = lambda q: q / (1 - FEE * (1 - q))

BASE = ["move_bps", "ret5", "ret15", "ret30", "ret60", "rv60", "range_bps", "pos_in_range",
        "dist_hi_bps", "dist_lo_bps", "spot_imb15", "spot_imb60", "ofi5", "ofi15", "ofi60",
        "perp_n15", "basis_bps", "spread_bps", "imb5", "imb20", "micro_bps", "prev1_bps",
        "prev2_bps", "sec_left", "hod_sin", "hod_cos"]
FEATURE_SETS = {
    "btc_only": BASE,                       # no venue information at all
    "btc+venue": BASE + ["p_venue"],        # market's opinion as one more input
}


def make_model(kind):
    if kind == "logit":
        return make_pipeline(StandardScaler(),
                             LogisticRegression(C=0.3, max_iter=2000))
    if kind == "lgbm":
        return lgb.LGBMClassifier(n_estimators=350, learning_rate=0.03, num_leaves=15,
                                  min_child_samples=60, subsample=0.8, subsample_freq=1,
                                  colsample_bytree=0.8, reg_lambda=5.0, verbose=-1)
    raise ValueError(kind)


def lodo_predict(X, y, groups, kind):
    """Leave-one-day-out with isotonic calibration fitted INSIDE each training
    fold on grouped inner held-out predictions, so the calibrator never sees
    the day being predicted."""
    from sklearn.isotonic import IsotonicRegression
    oof = np.full(len(y), np.nan)
    for d in np.unique(groups):
        tr, te = groups != d, groups == d
        Xtr, ytr, gtr = X[tr], y[tr], groups[tr]
        inner_p = np.full(len(ytr), np.nan)
        for itr, ite in GroupKFold(n_splits=4).split(Xtr, ytr, gtr):
            m = make_model(kind).fit(Xtr[itr], ytr[itr])
            inner_p[ite] = m.predict_proba(Xtr[ite])[:, 1]
        iso = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip").fit(inner_p, ytr)
        m = make_model(kind).fit(Xtr, ytr)
        oof[te] = iso.predict(m.predict_proba(X[te])[:, 1])
    return oof


def trade_sim(sub, p, thr, one_per_candle=True):
    """Buy the favoured side at the venue ask when fee-adjusted EV > thr."""
    s = sub.assign(p_up=p).sort_values(["epoch", "offset"])
    out = []
    taken = set()
    for r in s.itertuples():
        if one_per_candle and r.epoch in taken:
            continue
        if r.p_up >= 0.5:
            side, ps, ask = "UP", r.p_up, r.ask_up
        else:
            side, ps, ask = "DOWN", 1 - r.p_up, r.ask_dn
        if not (isinstance(ask, float) and np.isfinite(ask) and 0 < ask < 1):
            continue
        ev = ps * (1 / cost(ask) - 1) - (1 - ps)
        if ev < thr:
            continue
        taken.add(r.epoch)
        win = (side == "UP") == bool(r.y)
        out.append(dict(epoch=r.epoch, offset=r.offset, side=side, p=ps, ask=ask,
                        win=win, pnl=10 * ((1 / cost(ask) - 1) if win else -1.0),
                        is_book=r.is_book))
    return pd.DataFrame(out)


def summarize(t, n_candles):
    if len(t) == 0:
        return dict(trades=0)
    se = np.std(t.pnl, ddof=1) / np.sqrt(len(t)) if len(t) > 1 else np.nan
    return dict(trades=len(t), freq=round(100 * len(t) / n_candles, 1),
                acc=round(100 * t.win.mean(), 1), ask=round(t.ask.mean(), 3),
                pnl=round(t.pnl.sum(), 2), per_trade=round(t.pnl.mean(), 3),
                t=round(t.pnl.mean() / se, 2) if se and se > 0 else None,
                book_pnl=round(t[t.is_book == 1].pnl.sum(), 2), book_n=int((t.is_book == 1).sum()))


if __name__ == "__main__":
    y = df.y.values
    groups = df.date.values
    results = {}
    preds = {}
    print(f"{len(df):,} rows, {df.epoch.nunique()} candles, {len(np.unique(groups))} days\n")

    # ---- benchmark: the venue's own probability
    m = df.p_venue.notna()
    pv = df.p_venue.clip(0.01, 0.99)
    mb = m & (df.is_book == 1)
    print("BENCHMARK  venue-implied probability")
    print(f"   all quoted rows   logloss {log_loss(y[m], pv[m]):.4f}   brier {brier_score_loss(y[m], pv[m]):.4f}   (n={m.sum():,})")
    print(f"   real-book rows    logloss {log_loss(y[mb], pv[mb]):.4f}   brier {brier_score_loss(y[mb], pv[mb]):.4f}   (n={mb.sum():,})\n")

    for fs_name, feats in FEATURE_SETS.items():
        X = df[feats].fillna(0.0).values
        for kind in ("logit", "lgbm"):
            name = f"{kind}/{fs_name}"
            oof = lodo_predict(X, y, groups, kind)
            preds[name] = oof
            ok = ~np.isnan(oof)
            ll_all = log_loss(y[ok], oof[ok]); br_all = brier_score_loss(y[ok], oof[ok])
            ll_book = log_loss(y[mb & ok], oof[mb & ok])
            acc_all = ((oof[ok] >= 0.5) == y[ok]).mean()
            print(f"MODEL {name:18} logloss all {ll_all:.4f}  book {ll_book:.4f}   brier {br_all:.4f}   "
                  f"dir-acc {100*acc_all:.1f}%   beats venue on book rows: {'YES' if ll_book < log_loss(y[mb], pv[mb]) else 'no'}")
            results[name] = dict(logloss_all=ll_all, logloss_book=ll_book, brier=br_all, acc=acc_all)
        # blend of the two model families
        name = f"blend/{fs_name}"
        oof = 0.5 * preds[f"logit/{fs_name}"] + 0.5 * preds[f"lgbm/{fs_name}"]
        preds[name] = oof
        ok = ~np.isnan(oof)
        ll_book = log_loss(y[mb & ok], oof[mb & ok])
        print(f"MODEL {name:18} logloss all {log_loss(y[ok], oof[ok]):.4f}  book {ll_book:.4f}   brier {brier_score_loss(y[ok], oof[ok]):.4f}   "
              f"dir-acc {100*((oof[ok]>=0.5)==y[ok]).mean():.1f}%   beats venue on book rows: {'YES' if ll_book < log_loss(y[mb], pv[mb]) else 'no'}")
        results[name] = dict(logloss_book=ll_book)
        print()

    # ---- calibration table for the best-by-logloss model
    best = min(results, key=lambda k: results[k]["logloss_book"])
    print(f"BEST by real-book log-loss: {best}\n")
    p = preds[best]
    cal = df.assign(p=p, bin=pd.cut(p, [0, .2, .35, .45, .55, .65, .8, 1]))
    print("calibration of", best)
    print(cal.groupby("bin", observed=True).agg(n=("y", "size"), claimed=("p", "mean"), actual=("y", "mean")).round(3).to_string(), "\n")

    # ---- trading test: one trade per candle, EV threshold = frequency dial
    n_candles = df.epoch.nunique()
    print(f"TRADING TEST  ({best}), $10 flat, one trade per candle, buy at venue ask")
    print(f"{'EV thr':>7}{'trades':>8}{'freq%':>7}{'acc':>7}{'ask':>7}{'PnL $':>10}{'per trade':>11}{'t':>7}{'book PnL':>10}{'book n':>7}")
    for thr in (0.00, 0.03, 0.06, 0.10, 0.15, 0.20, 0.30):
        t = trade_sim(df, p, thr)
        s = summarize(t, n_candles)
        if s["trades"]:
            print(f"{thr:>7.2f}{s['trades']:>8}{s['freq']:>7}{s['acc']:>6}%{s['ask']:>7}{s['pnl']:>+10.2f}{s['per_trade']:>+11.3f}{str(s['t']):>7}{s['book_pnl']:>+10.2f}{s['book_n']:>7}")
    # the same, venue-only "model" (buy whatever the market favours) for contrast
    print(f"\nCONTRAST: same rule using the venue's own probability instead of the model")
    t = trade_sim(df[m], pv[m].values, 0.0)
    s = summarize(t, n_candles)
    print(f"   thr 0.00  trades {s['trades']}  acc {s['acc']}%  PnL ${s['pnl']:+.2f}  per trade {s['per_trade']:+.3f}")

    # ---- persist OOF predictions for the 100-candle and full-week reports
    out = df[["date", "epoch", "offset", "y", "ask_up", "ask_dn", "p_venue", "is_book"]].copy()
    for k, v in preds.items():
        out[k.replace("/", "__")] = v
    out.to_parquet(ROOT / "oof_predictions.parquet", index=False)
    json.dump({"best": best, "results": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in results.items()}},
              open(ROOT / "train_summary.json", "w"), indent=1)
    print(f"\nwrote oof_predictions.parquet  ({len(out):,} rows)")
