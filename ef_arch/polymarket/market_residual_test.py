#!/usr/bin/env python3
"""Does our BTC-microstructure P add information beyond the real Polymarket price?
(1) market calibration: realized reversal win rate by real ask-price bucket
(2) walk-forward logistic of Chainlink outcome on [logit(q_mid)] vs [logit(q_mid), logit(P)]
    -> AUC / logloss gain from adding P, candle-clustered CI on the coefficient sign."""
import sys, pathlib, numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent; sys.path.insert(0, str(HERE.parent))
from clean_grid_harness import decision_points, walk_forward, auc
W0 = 1785542400
g = np.load(HERE.parent / "grid.npz"); g = {k: g[k] for k in ("mid","micro","b15","b610","b1120","spr","flow","tcnt","spot")}
d = decision_points(g); P = walk_forward(d["X"], d["win_contr"].astype(float), d["hour"])
L = pq.read_table(HERE / "polymarket_btc5m_2026-08-01_books.parquet").to_pandas(); L = L[L.has_book]
lad = {(int(r.window_epoch), r.side, int(r.offset_s)): (r.mid, r.best_ask, r.outcome) for r in L.itertuples()}
rows = []
for k in range(len(d["ci"])):
    if d["hour"][k] < 4: continue
    ep = W0 + 300 * int(d["ci"][k]); side = "UP" if d["contr_up"][k] else "DOWN"; o = int(d["off"][k])
    r = lad.get((ep, side, o))
    if r is None or not np.isfinite(r[0]): continue
    rows.append(dict(c=int(d["ci"][k]), hour=int(d["hour"][k]), q_mid=float(r[0]), q_ask=float(r[1]), p=float(P[k]), y=1.0 if r[2] == side else 0.0, left=float(d["left"][k])))
R = pd.DataFrame(rows); print(f"rows {len(R):,}  candles {R.c.nunique()}  reversal base rate (Chainlink) {100*R.y.mean():.1f}%")

print("\n(1) MARKET CALIBRATION -- realized reversal win rate by real mid price bucket")
print(f"{'mid bucket':<12}{'n':>7}{'mean mid':>10}{'realized':>10}{'diff':>8}")
for lo, hi in ((0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.8),(.8,1.01)):
    m = (R.q_mid >= lo) & (R.q_mid < hi)
    if m.sum(): print(f"[{lo:.1f},{hi:.1f})   {int(m.sum()):>7}{R.q_mid[m].mean():>10.3f}{R.y[m].mean():>10.3f}{R.y[m].mean()-R.q_mid[m].mean():>+8.3f}")
print("  (diff < 0 => market price ABOVE realized rate => reversal side overpriced)")

print("\n(2) MARKET-RESIDUAL TEST -- walk-forward logistic, hour h trained on hours < h")
def lg(p): p = np.clip(p, 1e-4, 1-1e-4); return np.log(p/(1-p))
def wf(X, y, hour):
    out = np.full(len(y), np.nan); coefs = []
    for h in range(4, 24):
        tr = hour < h; te = hour == h
        if tr.sum() < 500: continue
        mu, sd = X[tr].mean(0), np.maximum(X[tr].std(0), 1e-9)
        A = np.column_stack([np.ones(tr.sum()), (X[tr]-mu)/sd]); w = np.zeros(A.shape[1]); yt = y[tr]
        for _ in range(400): pr = 1/(1+np.exp(-A@w)); w += 0.5*(A.T@(yt-pr)/len(yt) - 0.01*w)
        out[te] = 1/(1+np.exp(-(np.column_stack([np.ones(te.sum()), (X[te]-mu)/sd])@w))); coefs.append(w.copy())
    return out, np.array(coefs)
y = R.y.to_numpy(); hour = R.hour.to_numpy()
Xm = lg(R.q_mid.to_numpy()).reshape(-1,1); Xmp = np.column_stack([lg(R.q_mid), lg(R.p)]); Xp = lg(R.p.to_numpy()).reshape(-1,1)
def ll(p, y): p = np.clip(p,1e-6,1-1e-6); return float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p)))
res = {}
for name, X in (("market mid only", Xm), ("our P only", Xp), ("market + our P", Xmp)):
    pr, co = wf(X, y, hour); m = ~np.isnan(pr); res[name] = (auc(pr[m], y[m]), ll(pr[m], y[m]), co)
    print(f"  {name:<18} AUC {res[name][0]:.3f}   logloss {res[name][1]:.4f}   n={int(m.sum()):,}")
co = res["market + our P"][2]
print(f"  standardized coef on our P (per hour, market+P model): mean {co[:,2].mean():+.3f}  min {co[:,2].min():+.3f}  max {co[:,2].max():+.3f}   hours with coef>0: {(co[:,2]>0).sum()}/{len(co)}")
print(f"  standardized coef on market mid:                    mean {co[:,1].mean():+.3f}")
gain = res["market mid only"][1] - res["market + our P"][1]
print(f"  logloss improvement from adding P to the market price: {gain:+.4f}  ({'P adds information' if gain > 0.002 else 'P adds ~nothing beyond the price'})")
