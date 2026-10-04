"""R-26 artifacts for V's EV grid, plus the (c) walk-forward grid that only my harness can run.

Exports, all under analysis/h1/r26/:
  model_b_week1.json         arm (b): week-1-only fit, 30 features. Same coefficients as the shipped
                             model_v10.json (verified 0.000e+00 on coef/scaler/intercept) with the
                             152-knot isotonic from GroupKFold(4). This is the arm worth $36.
  model_c_<day>.json         arm (c): one fit per tested day, trained on week 1 + week-2 days BEFORE
                             that day. Walk-forward is the whole point - a single (c) json would leak.
  week2_features.parquet     34,121 rows / 1,906 candles, column names matching
                             v10_features_8days.parquet so V's harness loads it unchanged.

`y` IS `venues.outcome`. Verified at source, not assumed: task_r8_taker_feature.oracle() is
`select epoch,actual from outcome` against venues.sqlite3, and lane_ticks carries that through as
`actual`. Polymarket settles on that oracle, so this is the right label for these rows.
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
from btc_model_v10 import FEATURES
import r12_train as T
import task_r8_taker_feature as R8
import task_r26_twoweek as R26

OUT = '/home/user/Django-final-project/analysis/h1/r26'
SHIP = '/home/user/Django-final-project/learner/v12_2/model_v10.json'
DERIVED = {'lv', 'mv_x_sec', 'lv_x_sec'}


def to_json(m, iso, note):
    sc = m.named_steps['standardscaler']
    lr = m.named_steps['logisticregression']
    ship = json.load(open(SHIP))
    return dict(design=note, features=FEATURES,
                scaler_mean=sc.mean_.tolist(), scaler_scale=sc.scale_.tolist(),
                coef=lr.coef_[0].tolist(), intercept=float(lr.intercept_[0]),
                iso_x=iso.X_thresholds_.tolist(), iso_y=iso.y_thresholds_.tolist(),
                fee_rate=ship['fee_rate'], ev_threshold_default=ship['ev_threshold_default'],
                regime=ship['regime'])


def main():
    os.makedirs(OUT, exist_ok=True)
    d1 = R26.week1()
    X1 = np.nan_to_num(d1[FEATURES].astype(float).values)
    y1 = d1.y.values.astype(float)
    g1 = np.array(['w1:' + s for s in d1.date.values])

    L = [r for r in T.lane_ticks(R8.oracle()) if r.get('ask') and r['feat'].get('p_venue') is not None]
    L.sort(key=lambda r: r['ts'])
    X2 = np.nan_to_num(np.array([[r['feat'][n] for n in FEATURES] for r in L], float))
    y2 = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in L])
    d2 = np.array([r['day'] for r in L])
    days2 = sorted(set(d2.tolist()))

    mb, ib = T.fit(X1, y1, g1)
    json.dump(to_json(mb, ib, 'R-26 arm (b): week-1-only, 30 features; coefficients identical to '
                              'model_v10.json, isotonic from GroupKFold(4)'),
              open(os.path.join(OUT, 'model_b_week1.json'), 'w'), indent=1)
    print('wrote model_b_week1.json')

    for i, dd in enumerate(days2):
        te = d2 == dd
        if te.sum() < 20:
            continue
        pri = d2 < dd
        Xc = np.vstack([X1, X2[pri]]) if pri.sum() else X1
        yc = np.concatenate([y1, y2[pri]]) if pri.sum() else y1
        gc = np.concatenate([g1, d2[pri]]) if pri.sum() else g1
        mc, ic = T.fit(Xc, yc, gc)
        json.dump(to_json(mc, ic, 'R-26 arm (c) fold for test day %s: week 1 + week-2 days < %s '
                                  '(%d training rows)' % (dd, dd, len(yc))),
                  open(os.path.join(OUT, 'model_c_%s.json' % dd), 'w'), indent=1)
        print('wrote model_c_%s.json  (%d training rows)' % (dd, len(yc)))

    import pandas as pd
    cols = {'date': d2, 'epoch': [r['ep'] for r in L], 'offset': [r['sec'] for r in L],
            'y': y2.astype(int)}
    for j, n in enumerate(FEATURES):
        if n in DERIVED:
            continue                      # V's harness derives these from p_venue/move_bps/sec_left
        cols[n] = X2[:, j]
    cols['ask_up'] = [r['feat'].get('_ask_up', np.nan) for r in L]
    cols['ask_dn'] = [r['feat'].get('_ask_dn', np.nan) for r in L]
    df = pd.DataFrame(cols)
    df.to_parquet(os.path.join(OUT, 'week2_features.parquet'), index=False)
    print('wrote week2_features.parquet  %d rows, %d candles, %d cols'
          % (len(df), df.epoch.nunique(), len(df.columns)))
    print('  y = venues.outcome (oracle() reads venues.sqlite3 outcome directly)')
    print('  columns:', ', '.join(df.columns))
    ok = np.isfinite(df.ask_up) & np.isfinite(df.ask_dn)
    print('  ask_up/ask_dn finite on %.1f%% of rows' % (100 * ok.mean()))


if __name__ == '__main__':
    main()
