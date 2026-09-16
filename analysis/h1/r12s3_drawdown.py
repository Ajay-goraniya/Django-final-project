"""R-12 step 3 -- DRAWDOWN on exactly the four arms of the r12s3 table (user, 09-16 00:4x).

Same rows, same walk-forward-by-day fits, same EV fire rule, same grading as
`r12s3_full_features.py`. The only new thing is that the per-fire PnL is kept as a CHRONOLOGICAL
SEQUENCE instead of being collapsed to a mean, so the equity path can be read.

Why this is not just "another statistic": per $1 is an average and averages hide path. Two arms with
the same +0.17/fire are not the same business if one of them is 40% underwater at its worst point.
The live engine stakes a FIXED amount, so the drawdown in $1-units multiplies straight through to
whatever the stake is - at the live $10 flat stake, multiply every $1 number below by 10.

Ordering is by candle epoch, which for one-fire-per-candle is also the order the money was at risk.
Predictions are cached to r12s3_preds.npz so re-reading the curve never refits.
"""
import json, os, statistics, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
CACHE = os.path.join(T.SP, 'r12s3_preds.npz')


def curve(fires):
    """(epochs, per-fire pnl) in candle order -- the order the money was actually at risk."""
    eps = sorted(fires)
    return eps, np.array([R8.per1(fires[e]['ask'], fires[e]['side'] == fires[e]['actual'])
                          for e in eps], float)


def drawdown(pnl):
    """Max peak-to-trough on the cumulative curve, plus where it happened and how long it lasted.

    Reported in $1-of-stake units, the same units as the per-$1 column. `depth` is the worst
    peak-to-trough fall; `trough_below_zero` is how far under water the curve ever went from a
    standing start, which is the number that matters for a bankroll that starts at zero profit.
    """
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    dd = peak - eq
    i = int(np.argmax(dd))
    j = int(np.argmax(eq[:i + 1] >= peak[i])) if i >= 0 else 0
    rec = np.where(eq[i:] >= peak[i])[0]
    return dict(depth=float(dd[i]), trough_i=i, peak_i=j,
                n_fires_in_dd=i - j + 1,
                recovered=bool(len(rec) > 1),
                fires_to_recover=(int(rec[1]) if len(rec) > 1 else None),
                trough_below_zero=float(-min(0.0, eq.min())),
                final=float(eq[-1]), eq=eq)


def losing_run(pnl):
    best = run = 0
    for x in pnl:
        run = run + 1 if x < 0 else 0
        best = max(best, run)
    return best


def main():
    import joblib
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()
    L = T.lane_ticks(oc)
    TS = T.test_store(sorted({r['day'] for r in L}))
    ok = [r for r in L if (r['ep'], r['sec']) in TS]
    ok.sort(key=lambda r: r['ts'])
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in ok])
    day = np.array([r['day'] for r in ok])
    days = sorted(set(day.tolist()))

    m, iso = joblib.load(os.path.join(T.SP, 'r12_fit.joblib'))
    p_hist = T.predict(m, iso, np.array([TS[(r['ep'], r['sec'])] for r in ok], np.float64))
    X30 = np.nan_to_num(np.array([[r['feat'][k] for k in FEATURES] for r in ok], np.float64))
    X31 = np.column_stack([X30, p_hist])

    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        preds = {'d8_30': z['d8_30'], 'd8_31': z['d8_31']}
        tested = list(z['tested'])
    else:
        preds = {k: np.full(len(ok), np.nan) for k in ('d8_30', 'd8_31')}
        tested = []
        for i, d in enumerate(days):
            if i < 2:
                continue
            tr, te = day < d, day == d
            if tr.sum() < 500 or te.sum() < 20:
                continue
            for key, X in (('d8_30', X30), ('d8_31', X31)):
                mm, ii = T.fit(X[tr], y[tr], day[tr])
                preds[key][te] = T.predict(mm, ii, X[te])
            tested.append(d)
        np.savez_compressed(CACHE, d8_30=preds['d8_30'], d8_31=preds['d8_31'],
                            tested=np.array(tested))

    msk = ~np.isnan(preds['d8_30'])
    sub = [r for r, k in zip(ok, msk) if k]
    arms = {
        'frozen v10 (live)': np.array([frozen.p_up(r['feat']) for r in sub]),
        '8 days, 30 feats': preds['d8_30'][msk],
        '8 days, 30 + p_hist': preds['d8_31'][msk],
        'p_hist alone (18)': p_hist[msk],
    }

    print('=' * 92)
    print('R-12 step 3 DRAWDOWN  -- same four arms, same fires, now as an equity path')
    print('=' * 92)
    print('  tested days: %s   (%d rows)' % (', '.join(tested), int(msk.sum())))
    print('  units: $1 of stake per fire. LIVE STAKE IS $10 FLAT, so multiply every $ column by 10.')
    print()
    print('  %-22s %6s %9s %9s %9s %8s %7s %7s'
          % ('arm', 'fires', 'total', 'maxDD', 'worst-uw', 'DD/tot', 'lose', 'recov'))
    out = {}
    for nm, p in arms.items():
        f = T.fire_set(sub, p)
        eps, pnl = curve(f)
        d = drawdown(pnl)
        out[nm] = (eps, pnl, d)
        ratio = (d['depth'] / d['final']) if d['final'] > 0 else float('inf')
        print('  %-22s %6d %+9.2f %9.2f %9.2f %8s %7d %7s'
              % (nm, len(pnl), d['final'], d['depth'], d['trough_below_zero'],
                 ('%.2f' % ratio) if np.isfinite(ratio) else 'n/a',
                 losing_run(pnl), 'yes' if d['recovered'] else 'NO'))
    print()
    print('  maxDD    = worst peak-to-trough fall on the cumulative curve, in $1-of-stake units')
    print('  worst-uw = deepest the curve ever went BELOW zero from a standing start')
    print('  DD/tot   = maxDD divided by the final PnL: how much pain per unit of profit')
    print('  lose     = longest consecutive run of losing fires')
    print('  recov    = did the curve ever regain the pre-drawdown peak within the window')
    print()

    for nm, (eps, pnl, d) in out.items():
        import datetime as dt
        t0 = dt.datetime.utcfromtimestamp(eps[d['peak_i']]).strftime('%m-%d %H:%M')
        t1 = dt.datetime.utcfromtimestamp(eps[d['trough_i']]).strftime('%m-%d %H:%M')
        span = (eps[d['trough_i']] - eps[d['peak_i']]) / 3600.0
        print('  %-22s worst run %s -> %s (%.1f h, %d fires, %+.2f)'
              % (nm, t0, t1, span, d['n_fires_in_dd'], -d['depth']))
    print()

    # per-day PnL for every arm: rain or sun on the path, not just the total
    print('  PER-DAY PnL ($1 units) -- every day, never the best one')
    import datetime as dt
    alldays = sorted({dt.datetime.utcfromtimestamp(e).strftime('%m-%d')
                      for eps, _, _ in out.values() for e in eps})
    print('  %-22s %s' % ('arm', ''.join('%9s' % d for d in alldays)))
    for nm, (eps, pnl, d) in out.items():
        by = {}
        for e, v in zip(eps, pnl):
            by.setdefault(dt.datetime.utcfromtimestamp(e).strftime('%m-%d'), []).append(v)
        print('  %-22s %s' % (nm, ''.join('%9s' % (('%+.2f' % sum(by[dd])) if dd in by else '-')
                                          for dd in alldays)))
    print()
    print('  POSITIVE DAYS: ' + ', '.join(
        '%s %d/%d' % (nm.split(' (')[0], sum(1 for dd in alldays
                      if sum(v for e, v in zip(eps, pnl)
                             if dt.datetime.utcfromtimestamp(e).strftime('%m-%d') == dd) > 0),
                      len({dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in eps}))
        for nm, (eps, pnl, d) in out.items()))


if __name__ == '__main__':
    main()
