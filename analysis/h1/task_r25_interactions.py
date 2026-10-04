"""R-25 -- does an interaction term close the representability gap V identified?

Task 97 (Mumbai) separated drawdown runs from normal fires on four book features: signed imb5
-0.630 vs -0.136, imb20 0.63 SD, pos_in_range 0.326 vs 0.524, ofi15 -0.242 vs -0.070. All four are
already inputs to model_v10. V's point is architectural: the model is L2 logistic then isotonic, so
it is linear in those four and monotone in p, and it cannot represent "ofi15 signed by the side we
are about to take". That is a representability gap, not a missing input.

NON-CIRCULAR CONSTRUCTION, stated explicitly as the brief requires.
The banned version signs the flow by the model's own output, sign(p - 0.5) - circular, and unusable
at training time because the target of the fit appears in its own input. I use two signings, both
computed from INPUTS the engine already has before the model runs:

  A  venue-signed   s_v = sign(p_venue - 0.5)
     The side we take is, by R-13, the venue's side on 92% of candles, so this is the closest honest
     proxy for "our side" available without the model's output. It is feature x feature.
  B  move-signed    s_m = sign(move_bps)
     The candle's own direction so far. Independent of the venue entirely, so if A and B disagree
     the result is not an artifact of one choice.

Interactions, four per signing: imb5*s, imb20*s, ofi15*s, (pos_in_range - 0.5)*s.

A PRIOR AGAINST, recorded before the run so the result is not read as a surprise: a gradient booster
finds interactions like these automatically, and R-15 measured lgbm against the same logistic on
4.75M rows - it won 8 of 8 years by +0.0049 logloss and moved the direction call by +0.0004 against
the momentum null. If feature x feature interactions carried real direction information, those arms
would already have shown it. This test is cheap and worth running anyway, because R-15 was on the
18-feature history store and never had imb5/imb20/ofi15 at all - they are among the 12 masked there.
"""
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

MODEL = '/home/user/Django-final-project/learner/v12_2/model_v10.json'
BOOK = ['imb5', 'imb20', 'ofi15']


def inter(f, s):
    """The four Task-97 separators, signed by s."""
    return [(f.get(n) or 0.0) * s for n in BOOK] + [((f.get('pos_in_range') or 0.5) - 0.5) * s]


def runs(fires):
    out, cur, side = [], 0, None
    for e in sorted(fires):
        t = fires[e]
        lost = t['side'] != t['actual']
        if lost and (cur == 0 or t['side'] == side):
            cur += 1; side = t['side']
        else:
            if cur:
                out.append(cur)
            cur = 1 if lost else 0
            side = t['side'] if lost else None
    if cur:
        out.append(cur)
    return out


def main():
    frozen = Model(MODEL)
    oc = R8.oracle()
    L = [r for r in T.lane_ticks(oc) if r.get('ask') and r['feat'].get('p_venue') is not None]
    L.sort(key=lambda r: r['ts'])
    day = np.array([r['day'] for r in L])
    days = sorted(set(day.tolist()))
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in L])
    X30 = np.nan_to_num(np.array([[r['feat'][n] for n in FEATURES] for r in L], np.float64))
    sv = np.array([1.0 if (r['feat']['p_venue'] or 0.5) >= 0.5 else -1.0 for r in L])
    sm = np.array([1.0 if (r['feat'].get('move_bps') or 0.0) >= 0 else -1.0 for r in L])
    IA = np.nan_to_num(np.array([inter(r['feat'], s) for r, s in zip(L, sv)], np.float64))
    IB = np.nan_to_num(np.array([inter(r['feat'], s) for r, s in zip(L, sm)], np.float64))
    print('=' * 96)
    print('R-25  interaction terms for the Task-97 separators')
    print('=' * 96)
    print('  %d ticks, %d candles, %d days. Signings: venue sign(p_venue-0.5), move sign(move_bps).'
          % (len(L), len({r['ep'] for r in L}), len(days)))
    print('  the two signings agree on %.1f%% of ticks' % (100 * np.mean(sv == sm)))

    arms = {'plain 30': X30,
            '+4 venue-signed': np.column_stack([X30, IA]),
            '+4 move-signed': np.column_stack([X30, IB]),
            '+8 both': np.column_stack([X30, IA, IB])}
    pred = {k: np.full(len(L), np.nan) for k in arms}
    tested = []
    for i, d in enumerate(days):
        if i < 2:
            continue
        tr, te = day < d, day == d
        if tr.sum() < 500 or te.sum() < 20:
            continue
        for k, X in arms.items():
            m, ii = T.fit(X[tr], y[tr], day[tr])
            pred[k][te] = T.predict(m, ii, X[te])
        tested.append(d)
        print('    fitted through %s, tested %s' % (days[i - 1], d), flush=True)
    msk = ~np.isnan(pred['plain 30'])
    sub = [r for r, k in zip(L, msk) if k]
    yy = y[msk]
    print('\n  tested days: %s  (%d rows)' % (', '.join(tested), int(msk.sum())))
    print('\n  %-20s %9s %9s %7s %7s %9s %9s %8s'
          % ('arm', 'logloss', 'Brier', 'fires', 'hit%', 'per $1', 'total', 'maxrun'))
    keep = {}
    base = np.array([frozen.p_up(r['feat']) for r in sub])
    for nm, p in [('frozen v10 (live)', base)] + [(k, pred[k][msk]) for k in arms]:
        ll = float(-np.mean(yy * np.log(np.clip(p, 1e-6, 1 - 1e-6))
                            + (1 - yy) * np.log(np.clip(1 - p, 1e-6, 1 - 1e-6))))
        br = float(np.mean((p - yy) ** 2))
        f = T.fire_set(sub, p)
        eps = sorted(f)
        pnl = np.array([R8.per1(f[e]['ask'], f[e]['side'] == f[e]['actual']) for e in eps])
        rr = runs(f)
        keep[nm] = (f, pnl, p)
        print('  %-20s %9.4f %9.4f %7d %6.1f%% %+9.3f %+9.2f %8d'
              % (nm, ll, br, len(pnl), 100 * np.mean([f[e]['side'] == f[e]['actual'] for e in eps]),
                 pnl.mean(), pnl.sum(), max(rr) if rr else 0))
    print('\n  loss-run counts (same-side, consecutive): ' + ' | '.join(
        '%s >=3:%d >=5:%d' % (nm, sum(1 for x in runs(keep[nm][0]) if x >= 3),
                              sum(1 for x in runs(keep[nm][0]) if x >= 5)) for nm in keep))

    idx = {id(r): i for i, r in enumerate(sub)}
    h = len(sub) // 2
    for cand in ('+4 venue-signed', '+4 move-signed', '+8 both'):
        fa, fb = keep[cand][0], keep['plain 30'][0]
        sh = sorted(set(fa) & set(fb))
        hv = []
        for half in (sub[:h], sub[h:]):
            mm = np.array([idx[id(r)] for r in half])
            x = T.book(T.fire_set(half, keep[cand][2][mm]))
            z = T.book(T.fire_set(half, keep['plain 30'][2][mm]))
            hv.append((x['per1'] - z['per1']) if (x and z) else float('nan'))
        F = Finding('R-25 %s vs plain 30' % cand,
                    per_fire=float(keep[cand][1].mean() - keep['plain 30'][1].mean()),
                    n=len(keep[cand][1]))
        F.sample({'fires': len(keep[cand][1])})
        F.halves(first=hv[0], second=hv[1])
        F.paired(mine_right=[fa[e]['side'] == fa[e]['actual'] for e in sh],
                 theirs_right=[fb[e]['side'] == fb[e]['actual'] for e in sh])
        F.null(mine=float(keep[cand][1].sum()), null_value=float(keep['plain 30'][1].sum()),
               null_name='plain 30-feature TOTAL PnL')
        F.verdict()


if __name__ == '__main__':
    main()
