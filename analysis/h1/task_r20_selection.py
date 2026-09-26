"""R-20 -- fit WHICH CANDLES are worth trading. The last untried route.

User's goal, restated: accuracy + PnL (PnL first) + adaptive frequency + no session like the 09-15
evening. R-13 closed the direction forecast, R-18 closed paying less than the touch. What is left is
selection: of the candles the EV rule already fires on, which are worth the money?

This is NOT a gate on a weak score. A gate takes an existing number and puts a hand-set threshold on
it. Here the target is the thing we care about - realized pnl per $1 at the price actually paid,
graded on venues.outcome - and the ranker is fitted to it from fire-second observables only,
walk-forward by day. The frequency dial falls out of the ranking instead of being chosen.

THE COMPARISONS THAT DECIDE IT, and the first one is the one that kills most selection results:
  RANDOM  - a random subset of the same size on the same days. Firing less raises per-$1 by luck
            whenever the mean is positive and the variance is large, which is exactly this data.
  EV      - the incumbent ranker at the SAME count. "Better than firing everything" is not the
            claim; "better than the rule we already run, at equal frequency" is.
  halves, permutation of the ranker's own scores, costs at the paid price.
  Per 3-hour window: worst-window pnl and worst same-side loss run per day, candidate vs current.
            That last one is the user's actual complaint. A model that lifts the mean without
            changing the evening shape has not answered it, and this script says so explicitly.

Accuracy is reported, never optimised.
"""
import json, os, sqlite3, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8

DB = '/tmp/claude-0/db'
MODEL = '/home/user/Django-final-project/learner/v12_2/model_v10.json'
PX = '/tmp/claude-0/r16_px.npz'
IN = ['p_side', 'ask', 'ev', 'sec_left', 'rv60', 'move_bps', 'spread_bps', 'lv',
      'imb5', 'imb20', 'micro_bps', 'ret60', 'pos_in_range', 'ref_open_bps', 'ref_move_bps']
FRACS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]


def build():
    z = np.load(PX); LO, P = int(z['lo']), z['px']
    twap = lambda a, b: float(P[a - LO:b - LO].mean()) if 0 <= a - LO and b - LO <= len(P) else np.nan
    oc = R8.oracle()
    frozen = Model(MODEL)
    L = T.lane_ticks(oc)
    pup = np.array([frozen.p_up(r['feat']) for r in L])
    fires = T.fire_set(L, pup)
    rows = []
    for e, t in fires.items():
        f = t['feat']
        i = e - LO
        ro = twap(e - 60, e) if i - 60 >= 0 else np.nan
        rn = twap(e + t['sec'] - 60, e + t['sec']) if i + t['sec'] - 60 >= 0 else np.nan
        op = P[i] if 0 <= i < len(P) else np.nan
        ps = t['ps']
        rows.append(dict(
            ep=e, day=t['day'], sec=t['sec'], side=t['side'], actual=t['actual'], ask=t['ask'],
            pnl=R8.per1(t['ask'], t['side'] == t['actual']),
            win=1.0 if t['side'] == t['actual'] else 0.0,
            x=dict(p_side=ps, ask=t['ask'], ev=R8.ev_of(ps, t['ask']), sec_left=f.get('sec_left') or 0,
                   rv60=f.get('rv60') or 0, move_bps=f.get('move_bps') or 0,
                   spread_bps=f.get('spread_bps') or 0, lv=f.get('lv') or 0,
                   imb5=f.get('imb5') or 0, imb20=f.get('imb20') or 0,
                   micro_bps=f.get('micro_bps') or 0, ret60=f.get('ret60') or 0,
                   pos_in_range=f.get('pos_in_range') or 0.5,
                   ref_open_bps=((op / ro - 1) * 1e4) if (ro == ro and ro > 0 and op == op) else 0.0,
                   ref_move_bps=((rn / ro - 1) * 1e4) if (ro == ro and rn == rn and ro > 0) else 0.0)))
    rows.sort(key=lambda r: (r['ep'], r['sec']))
    return rows


def main():
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    rows = build()
    days = sorted({r['day'] for r in rows})
    X = np.array([[r['x'][k] for k in IN] for r in rows], float)
    y = np.array([r['pnl'] for r in rows])
    day = np.array([r['day'] for r in rows])
    print('=' * 100)
    print('R-20  selection: fit which candles are worth trading (target = realized pnl per $1)')
    print('=' * 100)
    print('  %d fires, %d days (%s..%s), mean pnl/$1 %+.3f, total %+.2f'
          % (len(rows), len(days), days[0], days[-1], y.mean(), y.sum()))
    print('  inputs (fire-second only): %s' % ', '.join(IN))

    score = np.full(len(rows), np.nan)
    for i, d in enumerate(days):
        if i < 2:
            continue
        tr, te = day < d, day == d
        if tr.sum() < 100 or te.sum() < 10:
            continue
        m = make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(X[tr], y[tr])
        score[te] = m.predict(X[te])
    ok = ~np.isnan(score)
    R = [r for r, k in zip(rows, ok) if k]
    s, yy = score[ok], y[ok]
    dd = day[ok]
    ev = np.array([r['x']['ev'] for r in R])
    print('  scored %d fires on %d held-out days' % (len(R), len(set(dd.tolist()))))

    def topk(rank, frac):
        keep = np.zeros(len(R), bool)
        for d in sorted(set(dd.tolist())):
            m = dd == d
            idx = np.where(m)[0]
            n = max(1, int(round(frac * len(idx))))
            keep[idx[np.argsort(-rank[idx])[:n]]] = True
        return keep

    rng = np.random.default_rng(7)
    print('\n  FREQUENCY SWEEP. Each row keeps the top X%% of each day by that ranker.')
    print('  %-6s %6s %9s %10s %9s %10s %9s' % ('keep', 'n', 'model/$1', 'model tot', 'EV/$1', 'random/$1', 'win%'))
    for f in FRACS:
        km = topk(s, f)
        ke = topk(ev, f)
        rnd = np.mean([yy[topk(rng.random(len(R)), f)].mean() for _ in range(200)])
        print('  %-6.0f%% %6d %+9.3f %+10.2f %+9.3f %+10.3f %8.1f%%'
              % (100 * f, km.sum(), yy[km].mean(), yy[km].sum(), yy[ke].mean(), rnd,
                 100 * np.mean([R[i]['win'] for i in np.where(km)[0]])))
    print('\n  model/$1 must beat BOTH the EV column (same count, incumbent ranker) and the random')
    print('  column (same count, no information). Beating only random means "fire less", not "choose".')

    # the user's complaint: the shape of a bad session
    print('\n  THE EVENING TEST -- worst 3-hour window and worst same-side loss run, per day')
    def shape(keep, lbl):
        out = []
        for d in sorted(set(dd.tolist())):
            idx = [i for i in np.where(keep & (dd == d))[0]]
            if len(idx) < 10:
                out.append((d, None, None, len(idx))); continue
            by = {}
            for i in idx:
                h = time.gmtime(R[i]['ep']).tm_hour // 3
                by.setdefault(h, []).append(yy[i])
            worst = min(sum(v) for v in by.values())
            run = cur = 0; side = None
            for i in sorted(idx, key=lambda j: R[j]['ep']):
                lost = R[i]['win'] == 0
                if lost and (cur == 0 or R[i]['side'] == side):
                    cur += 1; side = R[i]['side']
                else:
                    run = max(run, cur); cur = 1 if lost else 0; side = R[i]['side'] if lost else None
            run = max(run, cur)
            out.append((d, worst, run, len(idx)))
        print('  %-22s %s' % (lbl, '  '.join('%s w%s r%s(n%d)' % (d, ('%+.1f' % w) if w is not None else '-',
                                                                  r if r is not None else '-', n)
                                             for d, w, r, n in out)))
        return out
    cur = shape(np.ones(len(R), bool), 'current (all fires)')
    for f in (0.5, 0.3):
        shape(topk(s, f), 'model top %d%%' % (100 * f))
        shape(topk(ev, f), 'EV top %d%%' % (100 * f))

    # verify.py on the best-behaved readable frac vs EV at the same count
    f = 0.5
    km, ke = topk(s, f), topk(ev, f)
    h = len(R) // 2
    F = Finding('R-20 fitted selection at top 50%% vs EV top 50%%',
                per_fire=float(yy[km].mean() - yy[ke].mean()), n=int(km.sum()))
    F.sample({'kept fires': int(km.sum())})
    F.halves(first=float(yy[:h][km[:h]].mean() - yy[:h][ke[:h]].mean()),
             second=float(yy[h:][km[h:]].mean() - yy[h:][ke[h:]].mean()))
    # verify.py's permutation() permutes model predictions against a price; the right control for a
    # SELECTOR is a random subset of the same size, which is already computed above. Reported here
    # rather than forcing permutation() into a shape it was not written for.
    rr = np.array([yy[topk(rng.random(len(R)), f)].mean() for _ in range(500)])
    print('  subset control at top %d%%: model %+.4f vs random mean %+.4f, P(random >= model) = %.3f'
          % (100 * f, yy[km].mean(), rr.mean(), float((rr >= yy[km].mean()).mean())))
    F.null(mine=float(yy[km].sum()), null_value=float(yy[ke].sum()),
           null_name='EV ranker at the same count, TOTAL PnL')
    F.verdict()


if __name__ == '__main__':
    main()
