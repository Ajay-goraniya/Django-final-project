"""R-16 retrain on the settlement line -- train == serve, to engine 12.11.1's definitions.

Spec from V/the user (02:0x): the signal must run on the official settlement feed. Engine
`learner/v12_2/btc_model_v10.py` serves `open_reference="twap60"`, under which every open-relative
feature measures from L_open (the 60 s TWAP line at the candle open) instead of the first trade.

I do NOT re-simulate the engine's features. The logged `feat` already holds what the engine computed
live from its own trade tape; under `twap60` the transform is exact algebra, so the recentred values
are derived from it rather than rebuilt:

    k = first_trade_open / ref_open
    move_bps      -> k*(1e4 + move_bps) - 1e4        (p is unchanged; only the denominator moves)
    range_bps     -> range_bps * k
    dist_hi_bps   -> dist_hi_bps * k
    dist_lo_bps   -> dist_lo_bps * k
    mv_x_sec      -> move_new * sec_left / 300
    pos_in_range  -> unchanged (a ratio inside the range, open cancels)
    prev1/prev2   -> unchanged (first-trade based; the engine leaves these alone too)

Verified against the running artifact before use: reconstructing the engine's own `move_bps` from my
1 s grid on the same first-trade line gives median difference 0.0000 bps, p90 |diff| 0.81 bps,
corr 0.9893 over 32,014 ticks. That residual is the 1 s-grid-vs-trade-tape proxy error and it is the
error budget on everything below.

TWO OF THE FOUR EXTRA FEATURES ARE DELIBERATELY EXCLUDED, and both exclusions matter:

  ref_gap_bps = (p/ref_open - 1)*1e4. Under open_reference="twap60" this is EXACTLY move_bps -- the
    same number twice. Including both would hand the fit a perfectly collinear pair for nothing.

  ref_src. It is 0 on every historical row (Binance proxies Chainlink) and will be 1 in live serving
    once Task 98's feed is up. A feature that is constant in training and takes a different value at
    serve time is out of range by construction -- the same mistake as an era feature in a
    walk-forward fold (r12s2_lgbm.py), and here it would ship into live money. Excluded until there
    is history with ref_src=1 in it.

So: 30 recentred features + ref_open_bps + ref_move_bps = 32.

LABELS. CORRECTED after V caught a handicap here. This script's twap60 arm trains on the settlement
rule computed from the Binance TWAP proxy, which matches `venues.outcome` only 95.54% of the time,
while the other two arms train on the venue label directly -- so the candidate carried ~4.5% of label
noise its competitors did not. The fair re-run (same features, `venues.outcome` labels) is recorded
in `task_r16_retrain.md`: it lifts the arm to +0.183/fire and leaves the verdict unchanged.

Also corrected: v10 is NOT trained on `close >= open`. `learner/build_features.py:244` sets `y=S[ep]`
from `load_settlement()`, the venue's own resolved market file. The `close >= open` label belongs to
the engine's `candles.actual` column, not to v10's fit.

ARMS (walk-forward BY DAY, train days < d, test d):
  1 frozen v10 (live)        - as deployed, first-trade features, its own json
  2 my recipe / old centring - the control that separates "my recipe" from "the recentring"
  3 my recipe / twap60       - the candidate
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_2/model_v10.json'
PX_CACHE = '/tmp/claude-0/r16_px.npz'
OPEN_REL = ['move_bps', 'range_bps', 'dist_hi_bps', 'dist_lo_bps']
EXTRA = ['ref_open_bps', 'ref_move_bps']


def load_px():
    z = np.load(PX_CACHE)
    return int(z['lo']), z['px']


def recentre(feat, k, sec_left):
    """The engine's twap60 algebra, applied to a logged first-trade feature dict."""
    f = dict(feat)
    f['move_bps'] = k * (1e4 + feat['move_bps']) - 1e4
    for n in OPEN_REL[1:]:
        f[n] = feat[n] * k
    f['mv_x_sec'] = f['move_bps'] * sec_left / 300.0
    return f


def main():
    LO, PX = load_px()
    twap = lambda t0, t1: float(PX[t0 - LO:t1 - LO].mean())
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()
    L = T.lane_ticks(oc)
    rows = []
    for r in L:
        e, s = r['ep'], r['sec']
        i = e - LO
        if i - 60 < 0 or i + 300 > len(PX) or i + s >= len(PX):
            continue
        ro, rn = twap(e - 60, e), twap(e + s - 60, e + s)
        if not (ro > 0 and rn > 0):
            continue
        lab = 1.0 if twap(e + 240, e + 300) >= ro else 0.0      # the settlement rule
        rows.append(dict(r, _open=PX[i], _ro=ro, _rn=rn, _lab=lab))
    rows.sort(key=lambda r: r['ts'])
    day = np.array([r['day'] for r in rows])
    days = sorted(set(day.tolist()))
    y_rule = np.array([r['_lab'] for r in rows])                # what the model is trained on
    y_venue = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in rows])   # what money is graded on
    print('=' * 100)
    print('R-16 retrain on the settlement line (open_reference="twap60"), engine 12.11.1 definitions')
    print('=' * 100)
    print('  %d logged ticks carry a reference window, %d days (%s..%s)'
          % (len(rows), len(days), days[0], days[-1]))
    print('  training label = TWAP60(end) >= TWAP60(open); PnL graded on venues.outcome')
    print('  label agreement rule-vs-venue on these rows: %.4f' % (y_rule == y_venue).mean())

    Xold = np.nan_to_num(np.array([[r['feat'][n] for n in FEATURES] for r in rows], np.float64))
    NEW = FEATURES + EXTRA
    Xnew = []
    for r in rows:
        k = r['_open'] / r['_ro']
        f = recentre(r['feat'], k, r['feat']['sec_left'])
        Xnew.append([f[n] for n in FEATURES] + [(k - 1) * 1e4, (r['_rn'] / r['_ro'] - 1) * 1e4])
    Xnew = np.nan_to_num(np.array(Xnew, np.float64))
    print('  features: old %d, new %d (= 30 recentred + %s)' % (len(FEATURES), len(NEW), ', '.join(EXTRA)))
    print('  move_bps sign flips under recentring on %.2f%% of ticks'
          % (100 * np.mean((Xnew[:, FEATURES.index('move_bps')] >= 0)
                           != (Xold[:, FEATURES.index('move_bps')] >= 0))))

    preds = {k: np.full(len(rows), np.nan) for k in ('old', 'new')}
    tested = []
    for i, d in enumerate(days):
        if i < 2:
            continue
        tr, te = day < d, day == d
        if tr.sum() < 500 or te.sum() < 20:
            continue
        for key, X, yy in (('old', Xold, y_venue), ('new', Xnew, y_rule)):
            mm, ii = T.fit(X[tr], yy[tr], day[tr])
            preds[key][te] = T.predict(mm, ii, X[te])
        tested.append(d)
        print('    fitted through %s, tested %s' % (days[i - 1], d), flush=True)
    msk = ~np.isnan(preds['old'])
    sub = [r for r, k in zip(rows, msk) if k]
    arms = {
        'frozen v10 (live)': np.array([frozen.p_up(r['feat']) for r in sub]),
        'recipe, old centring': preds['old'][msk],
        'recipe, twap60 line': preds['new'][msk],
    }
    print('\n  tested days: %s  (%d rows)' % (', '.join(tested), int(msk.sum())))
    print('\n  %-24s %8s %8s %8s %9s %10s  (PnL graded on venues.outcome)'
          % ('arm', 'fires', 'hit%', 'per $1', 'total', 'maxDD'))
    keep = {}
    for nm, p in arms.items():
        f = T.fire_set(sub, p)
        eps = sorted(f)
        pnl = np.array([R8.per1(f[e]['ask'], f[e]['side'] == f[e]['actual']) for e in eps])
        eq = np.cumsum(pnl)
        dd = float((np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq).max()) if len(eq) else 0.0
        keep[nm] = (f, pnl)
        print('  %-24s %8d %7.1f%% %+8.3f %+9.2f %10.2f'
              % (nm, len(pnl), 100 * np.mean([f[e]['side'] == f[e]['actual'] for e in eps]),
                 pnl.mean(), pnl.sum(), dd))

    fa, fb = keep['recipe, twap60 line'][0], keep['frozen v10 (live)'][0]
    shared = sorted(set(fa) & set(fb))
    idx = {id(r): i for i, r in enumerate(sub)}
    h = len(sub) // 2
    hv = []
    for half in (sub[:h], sub[h:]):
        mm = np.array([idx[id(r)] for r in half])
        x, z2 = T.book(T.fire_set(half, arms['recipe, twap60 line'][mm])), \
                T.book(T.fire_set(half, arms['frozen v10 (live)'][mm]))
        hv.append((x['per1'] - z2['per1']) if (x and z2) else float('nan'))
    a, b = keep['recipe, twap60 line'][1], keep['frozen v10 (live)'][1]
    F = Finding('R-16 twap60-line retrain vs frozen v10',
                per_fire=float(a.mean() - b.mean()), n=len(a))
    F.sample({'fires': len(a)})
    F.halves(first=hv[0], second=hv[1])
    F.paired(mine_right=[fa[e]['side'] == fa[e]['actual'] for e in shared],
             theirs_right=[fb[e]['side'] == fb[e]['actual'] for e in shared])
    F.costs({c: T.book(fa, c)['per1'] for c in (0, 0.01, 0.02, 0.03, 0.05)})
    F.null(mine=float(a.sum()), null_value=float(b.sum()), null_name='frozen v10 TOTAL PnL')
    F.verdict()

    import datetime as dt
    print('\n  PER DAY per $1 (rain or sun) -- every day')
    alld = sorted({dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for nm in keep for e in keep[nm][0]})
    print('  %-24s %s' % ('arm', ''.join('%9s' % d for d in alld)))
    for nm in arms:
        f, pnl = keep[nm]
        eps = sorted(f)
        by = {}
        for e, v in zip(eps, pnl):
            by.setdefault(dt.datetime.utcfromtimestamp(e).strftime('%m-%d'), []).append(v)
        print('  %-24s %s' % (nm, ''.join('%9s' % (('%+.3f' % np.mean(by[d])) if d in by else '-')
                                          for d in alld)))
    np.savez_compressed('/tmp/claude-0/r16_retrain_preds.npz',
                        old=preds['old'], new=preds['new'], msk=msk)


if __name__ == '__main__':
    main()
