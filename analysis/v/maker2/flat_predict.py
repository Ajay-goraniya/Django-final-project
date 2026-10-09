#!/usr/bin/env python3
"""M15 (V, 09-30, owner: 'something must tell a flat candle in advance - volume, trades, depth, previous candles, market read').
Rules fixed BEFORE running. Every BTC 5m candle 09-11..30. TARGET: 'flat' = |close-open| (Binance 1 s) in the bottom third.
FEATURES known at the open: 1 s vol over 1/5/15/60 min; previous candles' |move| and range (last 1, mean of 3, mean of 12);
Binance 1 m volume and trade count over 5/15/60 min, 5m/60m volume ratio, taker-buy share over 5 min; hour of day.
MODEL: logistic regression (standardised), fit on 09-11..20, scored on 09-21..30 (sealed): AUC for 'flat', and each feature alone.
THEN London's 296 real fixed15 fills (all in the test window): P&L by predicted-P(flat) tercile, and 'skip the top 10/20/30%'
vs baseline ($ lost, $ PnL). Depth/order-book history is not available for these days (only Zurich's live book) - not tested.
usage: flat_predict.py <scratch dir>"""
import sys, json, csv, math, datetime as dt
import numpy as np
S = sys.argv[1]
BN = {}
for f in ('hist/bin1s_0911_0926.json', 'bin1s_48h.json', 'fresh48/bin1s_fresh.json'): BN.update({int(k): v for k, v in json.load(open(f'{S}/{f}')).items()})
M1 = {int(k): v for k, v in json.load(open(f'{S}/bn1m_vol.json')).items()}
def px(a, b): r = [BN.get(t) for t in range(a, b)]; return [x for x in r if x]
def sd(p): return float(np.std(np.diff(np.log(p))) * 1e4) if len(p) > 30 else np.nan
def mv(e):
    p = px(e, e + 300); return (abs(p[-1] / p[0] - 1) * 1e4, (max(p) - min(p)) / p[0] * 1e4) if len(p) > 240 else (np.nan, np.nan)
def vol1m(a, b, i): return sum(M1[t][i] for t in range(a, b, 60) if t in M1)
E = list(range(1789084800, (max(BN) // 300) * 300 - 300, 300)); X, Y, D = [], [], []
cache = {e: mv(e) for e in range(E[0] - 3600, E[-1] + 300, 300)}
for e in E:
    m, r = cache[e]
    if math.isnan(m): continue
    pm = [cache[e - 300 * k] for k in range(1, 13)]
    if any(math.isnan(a) for a, _ in pm): continue
    v5, v15, v60 = vol1m(e - 300, e, 0), vol1m(e - 900, e, 0), vol1m(e - 3600, e, 0)
    tb = vol1m(e - 300, e, 2)
    X.append([sd(px(e - 60, e)), sd(px(e - 300, e)), sd(px(e - 900, e)), sd(px(e - 3600, e)),
              pm[0][0], np.mean([a for a, _ in pm[:3]]), np.mean([a for a, _ in pm]),
              pm[0][1], np.mean([b for _, b in pm[:3]]), np.mean([b for _, b in pm]),
              math.log1p(v5), math.log1p(v15), math.log1p(v60), math.log1p(vol1m(e - 300, e, 1)), v5 / max(1e-9, v60 / 12),
              tb / max(1e-9, v5) - 0.5, math.sin(2 * math.pi * (e % 86400) / 86400), math.cos(2 * math.pi * (e % 86400) / 86400)])
    Y.append(m); D.append(e)
NAMES = ['vol1m', 'vol5m', 'vol15m', 'vol60m', 'prev1 move', 'prev3 move', 'prev12 move', 'prev1 range', 'prev3 range', 'prev12 range',
         'volume5m', 'volume15m', 'volume60m', 'trades5m', 'volume 5m/60m', 'taker-buy share', 'hour sin', 'hour cos']
X, Y, D = np.array(X), np.array(Y), np.array(D); X = np.nan_to_num(X)
tr = D < 1789948800; te = ~tr                                   # 09-21 00:00 UTC
cut = np.percentile(Y[tr], 33.3); flat = (Y < cut).astype(float)
mu, sg = X[tr].mean(0), X[tr].std(0) + 1e-9; Z = (X - mu) / sg
w = np.zeros(Z.shape[1]); b = 0.0
for _ in range(3000):                                           # plain logistic regression, L2 1e-3
    p = 1 / (1 + np.exp(-(Z[tr] @ w + b))); g = p - flat[tr]
    w -= 0.1 * (Z[tr].T @ g / tr.sum() + 1e-3 * w); b -= 0.1 * g.mean()
P = 1 / (1 + np.exp(-(Z @ w + b)))
def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
print(f'M15: {len(Y)} candles; train {tr.sum()} (09-11..20), test {te.sum()} (09-21..30); flat = |move| < {cut:.2f} bps (bottom third on train)')
print(f'COMBINED model AUC for "flat": train {auc(P[tr], flat[tr]):.3f}  TEST {auc(P[te], flat[te]):.3f}   (0.5 = coin flip)')
print('single features, TEST AUC (lower value -> flatter):')
for i, n in sorted(enumerate(NAMES), key=lambda t: -abs(auc(-X[te][:, t[0]], flat[te]) - 0.5)):
    print(f'   {n:16s} {auc(-X[te][:, i], flat[te]):.3f}')
q = np.percentile(P[te], [33.3, 66.7])
for nm, f in (('predicted CALM (flat likely)', P[te] >= q[1]), ('middle', (P[te] >= q[0]) & (P[te] < q[1])), ('predicted ACTIVE', P[te] < q[0])):
    print(f'   test candles {nm:30s}: actually flat {100*flat[te][f].mean():.0f}%, median |move| {np.median(Y[te][f]):.1f} bps')
PD = dict(zip(D.tolist(), P.tolist()))
R = [(int(r['candle_epoch']), float(r['pnl_usd'])) for r in csv.DictReader(open('analysis/v/combo/london_ef_real.csv'))]
R = [(e, p, PD[e]) for e, p in R if e in PD]
base = sum(p for _, p, _ in R); lost = -sum(p for _, p, _ in R if p < 0)
print(f'\nLondon real fixed15 fills scored: {len(R)}; baseline PnL {base:+.2f}, $ lost {lost:.2f}')
qq = np.percentile([s for *_, s in R], [33.3, 66.7])
for nm, f in (('predicted CALM', lambda s: s >= qq[1]), ('middle', lambda s: qq[0] <= s < qq[1]), ('predicted ACTIVE', lambda s: s < qq[0])):
    s = [(e, p) for e, p, x in R if f(x)]; print(f'   {nm:18s} n {len(s):3d}  win {100*np.mean([p > 0 for _, p in s]):.1f}%  $ {sum(p for _, p in s):+8.2f}')
for k in (10, 20, 30):
    c = np.percentile([s for *_, s in R], 100 - k); keep = [p for _, p, s in R if s < c]; sk = [p for _, p, s in R if s >= c]
    print(f'   skip top {k}% predicted-flat: PnL {sum(keep):+8.2f} (vs {base:+.2f}), $ lost {-sum(p for p in keep if p < 0):7.2f} (vs {lost:.2f}, {100*(1+sum(p for p in keep if p<0)/lost):+.1f}% cut), skipped {len(sk)} fires net {sum(sk):+.2f}')
