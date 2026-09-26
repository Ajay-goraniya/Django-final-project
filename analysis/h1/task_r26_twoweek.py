"""R-26 -- the owner's ask: "train it on 2 weeks", WITH the venue price this time.

V is right that R-12 did not answer this. The 109-month run masked 12 of 30 features including
p_venue / lv / lv_x_sec, so it was blind to the market price - and by R-13 that is where the signal
is. A two-week fit that can see the venue has never been run.

ONE CORRECTION TO THE BRIEF, and it makes the test better rather than worse.
V says 4 of the 30 (spread_bps, imb5, imb20, micro_bps) cannot be rebuilt for week 2 because we never
logged Binance depth, so the design should drop to 26 common features. That is true of REBUILDING
week 2 from the archives - and unnecessary, because the engine already logged all four live. Measured
on the 34,121 logged ticks: spread_bps, imb5, imb20 and micro_bps are present on 100.0% of rows and
non-zero on 100.0%, with medians (0.0129 / 0.0211 / 0.0323 / 0.0002) beside week 1's own
(0.0127 / 0.0492 / 0.0561 / 0.0003). Nothing needs downloading and the disk constraint does not bind.

So the full 30-feature arm is runnable, and it is the better comparison because it matches frozen
v10's input set exactly. Both are reported: 30 features as the primary, and V's 26-feature version
alongside so the specified design is honoured and the two can be compared.

ARMS, all tested on the same held-out slice, walk-forward BY DAY through week 2:
  (a) frozen v10                    - the agreed benchmark, fixed
  (b) week 1 only                   - fixed, never sees week 2
  (c) week 1 + week 2 days before d - the two-week fit
(b) vs (c) isolates the second week with the feature set held constant. (a) vs (c) decides shipping.

GAP, stated rather than papered over: 09-07 has no venue quotes, so the two weeks are 08-29..09-06
and 09-08..09-16 with one day missing between them.
"""
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
from verify import Finding
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

MODEL = '/home/user/Django-final-project/learner/v12_2/model_v10.json'
W1 = '/tmp/claude-0/r12p/feat8.parquet'
DEPTH = ['spread_bps', 'imb5', 'imb20', 'micro_bps']      # V's four; kept, not dropped
F26 = [f for f in FEATURES if f not in DEPTH]


def week1():
    import pandas as pd
    d = pd.read_parquet(W1)
    pv = d.p_venue.clip(0.02, 0.98)
    d = d.assign(lv=np.log(pv / (1 - pv)).fillna(0.0))
    d = d.assign(mv_x_sec=d.move_bps * d.sec_left / 300.0, lv_x_sec=lambda x: x.lv * d.sec_left / 300.0)
    return d


def main():
    frozen = Model(MODEL)
    d1 = week1()
    X1 = np.nan_to_num(d1[FEATURES].astype(float).values)
    y1 = d1.y.values.astype(float)
    g1 = np.array(['w1:' + s for s in d1.date.values])

    L = [r for r in T.lane_ticks(R8.oracle()) if r.get('ask') and r['feat'].get('p_venue') is not None]
    L.sort(key=lambda r: r['ts'])
    X2 = np.nan_to_num(np.array([[r['feat'][n] for n in FEATURES] for r in L], float))
    y2 = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in L])
    d2 = np.array([r['day'] for r in L])
    days2 = sorted(set(d2.tolist()))
    print('=' * 100)
    print('R-26  two weeks, WITH the venue price')
    print('=' * 100)
    print('  week 1: %d rows, %d candles, %s .. %s' % (len(X1), d1.epoch.nunique(),
                                                       min(d1.date), max(d1.date)))
    print('  week 2: %d rows, %d candles, %s .. %s' % (len(X2), len({r['ep'] for r in L}),
                                                       days2[0], days2[-1]))
    print('  GAP: 09-07 carries no venue quotes, so the two weeks are not contiguous.')
    print('  all 30 features present in both weeks - V\'s 4 "unrebuildable" ones were logged live.')

    for nm, cols in (('30 features (primary)', FEATURES), ("26 features (V's design)", F26)):
        ix = [FEATURES.index(c) for c in cols]
        A1, A2 = X1[:, ix], X2[:, ix]
        pred = {'b': np.full(len(A2), np.nan), 'c': np.full(len(A2), np.nan)}
        for i, dd in enumerate(days2):
            te = d2 == dd
            if te.sum() < 20:
                continue
            mb, ib = T.fit(A1, y1, g1)                              # week 1 only
            pred['b'][te] = T.predict(mb, ib, A2[te])
            pri = d2 < dd
            Xc = np.vstack([A1, A2[pri]]) if pri.sum() else A1
            yc = np.concatenate([y1, y2[pri]]) if pri.sum() else y1
            gc = np.concatenate([g1, d2[pri]]) if pri.sum() else g1
            mc, ic = T.fit(Xc, yc, gc)                              # week 1 + week 2 so far
            pred['c'][te] = T.predict(mc, ic, A2[te])
        msk = ~np.isnan(pred['c'])
        sub = [r for r, k in zip(L, msk) if k]
        yy = y2[msk]
        base = np.array([frozen.p_up(r['feat']) for r in sub])
        print('\n  %s  -- tested on %d rows, %d days' % (nm, int(msk.sum()), len(set(d2[msk].tolist()))))
        print('  %-26s %9s %9s %7s %7s %9s %10s'
              % ('arm', 'logloss', 'Brier', 'fires', 'hit%', 'per $1', 'total'))
        keep = {}
        for a, p in (('(a) frozen v10', base), ('(b) week 1 only', pred['b'][msk]),
                     ('(c) week 1 + week 2', pred['c'][msk])):
            ll = float(-np.mean(yy * np.log(np.clip(p, 1e-6, 1 - 1e-6))
                                + (1 - yy) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))))
            br = float(np.mean((p - yy) ** 2))
            f = T.fire_set(sub, p)
            eps = sorted(f)
            pnl = np.array([R8.per1(f[e]['ask'], f[e]['side'] == f[e]['actual']) for e in eps])
            keep[a] = (f, pnl, p)
            print('  %-26s %9.4f %9.4f %7d %6.1f%% %+9.3f %+10.2f'
                  % (a, ll, br, len(pnl), 100 * np.mean([f[e]['side'] == f[e]['actual'] for e in eps]),
                     pnl.mean(), pnl.sum()))
        if nm.startswith('30'):
            idx = {id(r): i for i, r in enumerate(sub)}
            h = len(sub) // 2
            for cand in ('(c) week 1 + week 2',):
                for comp in ('(a) frozen v10', '(b) week 1 only'):
                    hv = []
                    for half in (sub[:h], sub[h:]):
                        mm = np.array([idx[id(r)] for r in half])
                        x = T.book(T.fire_set(half, keep[cand][2][mm]))
                        z = T.book(T.fire_set(half, keep[comp][2][mm]))
                        hv.append((x['per1'] - z['per1']) if (x and z) else float('nan'))
                    fa, fb = keep[cand][0], keep[comp][0]
                    sh = sorted(set(fa) & set(fb))
                    F = Finding('R-26 (c) two weeks vs %s' % comp,
                                per_fire=float(keep[cand][1].mean() - keep[comp][1].mean()),
                                n=len(keep[cand][1]))
                    F.sample({'fires': len(keep[cand][1])})
                    F.halves(first=hv[0], second=hv[1])
                    F.paired(mine_right=[fa[e]['side'] == fa[e]['actual'] for e in sh],
                             theirs_right=[fb[e]['side'] == fb[e]['actual'] for e in sh])
                    F.null(mine=float(keep[cand][1].sum()), null_value=float(keep[comp][1].sum()),
                           null_name='%s TOTAL PnL' % comp)
                    F.verdict()


if __name__ == '__main__':
    main()
