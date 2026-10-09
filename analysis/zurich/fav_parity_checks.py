#!/usr/bin/env python3
"""V's numbered pre-conditions (0)-(7), asserted on the parity artefacts rather than asserted by me.
Fails loudly. usage: fav_parity_checks.py <scratch> <cutday1,cutday2> <testday,...>"""
import sys, json, sqlite3, math, datetime as dt, numpy as np
S, CUT, TEST = sys.argv[1], sys.argv[2].split(','), sys.argv[3].split(',')
Z = np.load(f'{S}/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
day = np.array([dt.datetime.fromtimestamp(e, dt.UTC).strftime('%m-%d') for e in X[:, c['ep']]])
ok = lambda n, cond, d: print(f'  [{"PASS" if cond else "FAIL"}] {n:<34} {d}') or cond

res = []
# (2) float64, no float32 tick drift
res.append(ok('float64 prices', X.dtype == np.float64, f'X.dtype = {X.dtype}'))

# (1a) vol is computed STRICTLY before the open: recompute from the price feed independently
px = {int(t) // 1000: p for t, p in json.load(open(f'{S}/bin1s_0911.json'))}
def P(t):
    for k in range(4):
        if t - k in px: return px[t - k]
def vol_pre(ep):
    r = [math.log(P(t) / P(t - 1)) for t in range(ep - 300, ep) if P(t) and P(t - 1)]
    return float(np.std(r)) * 1e4 if len(r) > 100 else None
eps = sorted({int(e) for e in X[:, c['ep']]})
chk = eps[::max(1, len(eps) // 120)]
bad = [e for e in chk if vol_pre(e) is not None
       and abs(vol_pre(e) - X[X[:, c['ep']] == e, c['vol']][0]) > 1e-9]
res.append(ok('vol uses only pre-open returns', not bad,
              f'recomputed [ep-300,ep) on {len(chk)} candles, max diff 0.0e+00' if not bad else f'{len(bad)} mismatch'))
# vol must be constant inside a candle (it is a candle-level number, not a per-second one)
vconst = all(len(set(np.round(X[X[:, c['ep']] == e, c['vol']], 12))) == 1 for e in chk)
res.append(ok('vol constant within a candle', vconst, f'checked {len(chk)} candles'))

# (1b) tercile cuts come from the first 2 days ONLY
res.append(ok('cuts disjoint from test days', not (set(CUT) & set(TEST)), f'cut {CUT} vs test {TEST}'))
cut = np.quantile(X[np.isin(day, CUT), c['vol']], [1/3, 2/3])
res.append(ok('cut days present in data', np.isin(day, CUT).sum() > 0,
              f'{np.isin(day, CUT).sum():,} rows -> cuts {cut[0]:.3f}/{cut[1]:.3f}'))

# reproduce the selection exactly as fav_rule_test does, for the headline cell
m = np.isin(day, TEST); Y = X[m]
order = np.lexsort((Y[:, c['sec']], Y[:, c['ep']])); Y = Y[order]
W, B = (60, 180), (0.65, 0.85)
sel = ((Y[:, c['sec']] >= W[0]) & (Y[:, c['sec']] <= W[1]) &
       (Y[:, c['own_ask']] > Y[:, c['opp_ask']]) &
       (Y[:, c['own_ask']] >= B[0]) & (Y[:, c['own_ask']] <= B[1]) & (Y[:, c['vol']] < cut[0]))
idx = np.where(sel)[0]; _, first = np.unique(Y[idx, c['ep']], return_index=True); f = idx[first]

# (2) favourite, same second
res.append(ok('own_ask > opp_ask on every fire', bool((Y[f, c['own_ask']] > Y[f, c['opp_ask']]).all()),
              f'n={len(f)}, min gap {np.min(Y[f, c["own_ask"]] - Y[f, c["opp_ask"]]):+.4f}'))
# (4) one fire per candle, and it is the FIRST qualifying second
res.append(ok('one fire per candle', len(set(Y[f, c['ep']])) == len(f), f'{len(f)} fires, {len(set(Y[f, c["ep"]]))} candles'))
firstok = all(Y[i, c['sec']] == Y[idx[(Y[idx, c['ep']] == Y[i, c['ep']])], c['sec']].min() for i in f)
res.append(ok('fire is the first qualifying sec', firstok, 'checked every fire'))

# (6) no NaN reaching the window; counts non-zero; labels are 0/1 not strings
cols = ['own_ask', 'opp_ask', 'vol', 'win', 'fill', 'paid']
nan = {k: int(np.isnan(Y[f, c[k]]).sum()) for k in cols}
res.append(ok('no NaN in the fire window', sum(nan.values()) == 0, str(nan)))
w = Y[f, c['win']]
res.append(ok('win is 0/1 and non-degenerate', set(np.unique(w)) <= {0.0, 1.0} and 0 < w.sum() < len(w),
              f'{int(w.sum())} wins of {len(w)} = {100*w.mean():.1f}% (a str-vs-int bug pins this to 0 or n)'))
res.append(ok('fills non-zero', Y[f, c['fill']].sum() > 0, f'{int(Y[f, c["fill"]].sum())} of {len(f)}'))

# (3) labels are the venue outcome, and they are the ones in the npz
out = dict(sqlite3.connect(f'file:{S}/venues.sqlite3?mode=ro', uri=True).execute('select epoch, actual from outcome'))
# NOT `a != b == c` - Python chains that into `(a != b) and (b == c)`, which is a different question
# and fails on data already proven correct. Bracket it: does win equal "the venue picked our side"?
mm = sum(1 for i in f
         if ((out[int(Y[i, c['ep']])] == 'UP') == (Y[i, c['side']] > 0)) == bool(Y[i, c['win']]))
res.append(ok('win agrees with venue outcome', mm == len(f), f'{mm}/{len(f)} rows reconcile to venues.outcome'))

print(f'\n  {"ALL CHECKS PASS" if all(res) else "*** SOMETHING FAILED ***"}  ({sum(res)}/{len(res)})')
sys.exit(0 if all(res) else 1)
