#!/usr/bin/env python3
"""EF-8 evaluation (V, 09-28). Rules fixed BEFORE the first run (grid reported in full, never the best cell):
  model  : HistGradientBoosting stumps (max_leaf_nodes=2), squared loss on the after-fill pnl per $1, refit each night on ALL earlier days.
  pin    : none | phys (TWAP-projection z >= 0 for the side, the model-free stand-in for EF's p_side >= 0.5).
  thr    : E5 = strict q-quantile of YESTERDAY's rows scored by today's model (one value per day);
           E4 = strict q-quantile of the trailing 1 h of candidate scores, 60 s grid, seeded with yesterday's last hour.
  q      : 0.80 / 0.90 / 0.95.  fire: first second with pred >= thr, once per candle, $10, fill/paid from the 1 s tape.
  nulls  : FAV120 (buy the higher-priced side at sec 120, every candle), RAND (same fires per day at random candle/second/pinned side, 200 draws).
  flip p : each fire's side flipped at the same second, priced at THAT side's own tape (its ask, its fill), 2000 draws.
usage: ef8_eval.py <scratch dir with ef8_rows.npz> > EF8_EVAL.txt"""
import sys, math, bisect, datetime as dt
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

S = sys.argv[1]
Z = np.load(f'{S}/ef8_rows.npz'); X = Z['X']; cols = list(Z['cols'])
c = {k: i for i, k in enumerate(cols)}
FEATS = [k for k in cols if k not in ('ep', 'side', 'win', 'fill', 'paid', 'pnl')]
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in X[:, c['ep']]])
t_abs = X[:, c['ep']] + X[:, c['sec']]
days = sorted(set(day)); TEST = [d for d in days if days.index(d) >= 2]
rng = np.random.default_rng(7)


def strict(vals, q):
    vals = np.sort(vals); k = q * (len(vals) - 1); lo = int(k); hi = min(lo + 1, len(vals) - 1)
    qv = vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
    i = np.searchsorted(vals, qv, side='right')
    return vals[i] if i < len(vals) else np.inf


def fit(mask):
    idx = np.where(mask)[0][::2]
    m = HistGradientBoostingRegressor(max_leaf_nodes=2, max_iter=300, learning_rate=0.05, min_samples_leaf=200, random_state=0)
    m.fit(X[idx][:, [c[k] for k in FEATS]], X[idx, c['pnl']]); return m


def stats(fired, label):
    """fired: list of row indices (one per candle, time order)."""
    if not fired: return f'{label:34s} n0'
    f = np.array(fired); pnl = 10 * X[f, c['pnl']]; fl = X[f, c['fill']] > 0
    cum = np.cumsum(pnl); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], cum])) - np.concatenate([[0], cum])))
    per = {d: pnl[day[f] == d].sum() for d in TEST}
    win = X[f[fl], c['win']].mean() if fl.any() else float('nan')
    ask = X[f[fl], c['paid']].mean() if fl.any() else float('nan')
    h = len(TEST) // 2
    hv = [sum(per[d] for d in TEST[:h]), sum(per[d] for d in TEST[h:])]
    return (f'{label:34s} n{len(f):4d} /day {len(f)/len(TEST):5.1f} fill {100*fl.mean():4.0f}% win {100*win:4.1f}% paid {ask:.2f} '
            f'$ {pnl.sum():+7.1f} DD {dd:6.1f} days+ {sum(v > 0 for v in per.values())}/{len(TEST)} halves {hv[0]:+.1f}/{hv[1]:+.1f} '
            f'| ' + ' '.join(f'{per[d]:+.0f}' for d in TEST))


def flip_p(fired, twin):
    f = np.array(fired); a = X[f, c['pnl']]; b = np.array([X[twin[i], c['pnl']] if twin.get(i) is not None else 0.0 for i in f])
    tot = a.sum(); sims = [(np.where(rng.random(len(f)) < 0.5, b, a)).sum() for _ in range(2000)]
    return float(np.mean(np.array(sims) >= tot))


# twin row (other side, same candle-second)
key = {(X[i, c['ep']], X[i, c['sec']], X[i, c['side']]): i for i in range(len(X))}
twin = {i: key.get((X[i, c['ep']], X[i, c['sec']], -X[i, c['side']])) for i in range(len(X))}
pred = np.full(len(X), np.nan); yday_pred = {}
import os
EVERY = int(os.environ.get('REFIT_EVERY', '1')); m = None
for j, d in enumerate(TEST):
    if m is None or j % EVERY == 0: m = fit(np.isin(day, [x for x in days if x < d])); fitted_for = d
    te = day == d; pred[te] = m.predict(X[te][:, [c[k] for k in FEATS]])
    py = days[days.index(d) - 1]; yv = day == py
    yday_pred[d] = (t_abs[yv], m.predict(X[yv][:, [c[k] for k in FEATS]]))
    print(f'# {d}: model fitted for {fitted_for}; trained on {sum(np.isin(day, [x for x in days if x < d]))} rows, test rows {te.sum()}, '
          f'pred p50 {np.median(pred[te]):+.4f} p90 {np.quantile(pred[te], .9):+.4f} p99 {np.quantile(pred[te], .99):+.4f}')

order = np.lexsort((X[:, c['side']], t_abs)); order = order[np.isin(day[order], TEST)]
pin_ok = {'none': np.ones(len(X), bool), 'phys': np.nan_to_num(X[:, c['z']], nan=-1) >= 0}
print('\n# cell                              fires, fires/day, fill%, win% of fills, mean paid, $ at $10, max DD, days+, halves | per day', TEST)
res = {}
for rule in ('E5', 'E4'):
    for q in (0.80, 0.90, 0.95):
        for pin in ('none', 'phys'):
            fired, done = [], set(); thr_day = {}
            for d in TEST: thr_day[d] = strict(yday_pred[d][1], q)
            win_t, win_v = [], []; cur_d = None; nxt = None; thr = np.inf
            for i in order:
                d = day[i]; t = t_abs[i]
                if rule == 'E4':
                    if d != cur_d:                                     # new model: reseed with yesterday's last hour under it
                        cur_d = d; yt, yp = yday_pred[d]; sel = yt >= yt.max() - 3600
                        win_t = list(yt[sel]); win_v = list(yp[sel]); nxt = None
                    step = math.floor(t / 60) * 60
                    if nxt is None or step >= nxt:
                        lo = bisect.bisect_left(win_t, step - 3600); win_t = win_t[lo:]; win_v = win_v[lo:]
                        k = bisect.bisect_left(win_t, step)
                        thr = strict(np.array(win_v[:k]), q) if k >= 500 else np.inf; nxt = step + 60
                    win_t.append(t); win_v.append(pred[i])
                else:
                    thr = thr_day[d]
                ep = X[i, c['ep']]
                if ep in done or not pin_ok[pin][i] or pred[i] < thr: continue
                done.add(ep); fired.append(i)
            fired.sort(key=lambda i: t_abs[i])
            lab = f'{rule} q{q:.2f} pin={pin}'
            print(stats(fired, lab) + f' | flip p {flip_p(fired, twin):.3f}'); res[lab] = fired

# nulls
cand = {}
for i in order:
    cand.setdefault(X[i, c['ep']], []).append(i)
fav = []
for ep, rows in cand.items():
    r = [i for i in rows if X[i, c['sec']] == 120]
    if len(r) == 2: fav.append(max(r, key=lambda i: X[i, c['own_ask']]))
fav.sort(key=lambda i: t_abs[i]); print(stats(fav, 'NULL FAV120'))
for lab in ('E5 q0.90 pin=phys', 'E4 q0.90 pin=phys'):
    per_day = {d: sum(day[i] == d for i in res[lab]) for d in TEST}
    tots = []
    for _ in range(200):
        pick = []
        for d in TEST:
            eps = [e for e in cand if day[cand[e][0]] == d]
            for e in rng.choice(eps, size=min(per_day[d], len(eps)), replace=False):
                rows = [i for i in cand[e] if pin_ok['phys'][i] and 15 <= X[i, c['sec']] <= 240]
                if rows: pick.append(rows[rng.integers(len(rows))])
        tots.append(10 * X[pick, c['pnl']].sum())
    tots = np.array(tots); act = 10 * X[res[lab], c['pnl']].sum()
    print(f'NULL RAND matched to {lab}: mean $ {tots.mean():+.1f} p95 {np.quantile(tots, .95):+.1f}  actual {act:+.1f}  p {np.mean(tots >= act):.3f}')
np.savez_compressed(f'{S}/ef8_fired.npz', **{k.replace(' ', '_'): np.array(v) for k, v in res.items()})
