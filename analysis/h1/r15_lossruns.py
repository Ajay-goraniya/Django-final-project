"""R-15 -- the user's actual question: do the higher-timeframe features cut the 7-9 same-side loss
runs inside a trend?

User, 09-16 00:5x (via V): "keep working on finding the solution for how the drawdowns can be
stopped." The failure they can see is a run of 7-9 losing fires all on the same side while price
trends against them. This tests whether giving the brain trend STATE as features changes that. It is
not a gate: no rule is added, no threshold is swept, no fire is suppressed by a filter. The same EV
arithmetic fires; only the feature set behind p changes.

ARMS, mirroring r12s3_full_features.py so the numbers are comparable to work already on the branch:
  1 frozen v10 (live)            - what runs today
  2 8 days, 30 feats             - my recipe on the same days without HTF: the control that separates
                                   "the recipe changed" from "the features changed"
  3 8 days, 30 + 16 HTF          - the candidate
Walk-forward BY DAY (train days < d, test d). Nothing in-sample.

BUCKETS ARE FIXED BEFORE ANY RESULT IS READ:
  trend   - |streak| >= 3 completed same-direction 5m candles (the user's "in one trend"), reported
            against |streak| 0-2 and 3-4 and 5+, and separately by |ret_1h| tercile of this window.
  A same-side loss run is a maximal block of CONSECUTIVE fires, in candle order, that all lost and
  were all on the same side. Max run, count of runs >= 5 and >= 7, and per-day max are reported for
  every arm in every bucket; cells under MIN_CELL=60 fires are marked insufficient and not read.
"""
import os, sys, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import Finding, MIN_CELL
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8
from r15_extract import HTF
import r15_live as LV

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
CACHE = os.path.join(T.SP, 'r15_lr_preds.npz')
ST, R1 = HTF.index('streak'), HTF.index('ret_1h')


def runs(fires):
    """Maximal blocks of consecutive losing fires on the same side, in candle order."""
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


def stats(fires):
    if not fires:
        return None
    r = runs(fires)
    pnl = [R8.per1(t['ask'], t['side'] == t['actual']) for t in fires.values()]
    byday = {}
    for e, t in fires.items():
        byday.setdefault(dt.datetime.utcfromtimestamp(e).strftime('%m-%d'), {})[e] = t
    dmax = {d: (max(runs(v)) if runs(v) else 0) for d, v in byday.items()}
    return dict(n=len(fires), hit=float(np.mean([t['side'] == t['actual'] for t in fires.values()])),
                per1=float(np.mean(pnl)), total=float(np.sum(pnl)),
                maxrun=max(r) if r else 0, ge5=sum(1 for x in r if x >= 5),
                ge7=sum(1 for x in r if x >= 7), nruns=len(r),
                dmax=dmax)


def main():
    import joblib
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()
    L = T.lane_ticks(oc)
    days = sorted({r['day'] for r in L})
    HM = LV.build_days(days, secs=range(15, 241))
    ok = [r for r in L if (r['ep'], r['sec']) in HM]
    ok.sort(key=lambda r: r['ts'])
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in ok])
    day = np.array([r['day'] for r in ok])
    dl = sorted(set(day.tolist()))
    X30 = np.nan_to_num(np.array([[r['feat'][k] for k in FEATURES] for r in ok], np.float64))
    HX = np.array([HM[(r['ep'], r['sec'])] for r in ok], np.float64)
    X46 = np.column_stack([X30, HX])
    print('  %d logged rows carry the HTF block, %d days (%s..%s)'
          % (len(ok), len(dl), dl[0], dl[-1]), flush=True)

    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        preds = {k: z[k] for k in ('d30', 'd46')}
        tested = list(z['tested'])
    else:
        preds = {k: np.full(len(ok), np.nan) for k in ('d30', 'd46')}
        tested = []
        for i, d in enumerate(dl):
            if i < 2:
                continue
            tr, te = day < d, day == d
            if tr.sum() < 500 or te.sum() < 20:
                continue
            for key, X in (('d30', X30), ('d46', X46)):
                mm, ii = T.fit(X[tr], y[tr], day[tr])
                preds[key][te] = T.predict(mm, ii, X[te])
            tested.append(d)
            print('    fitted through %s, tested %s' % (dl[i - 1], d), flush=True)
        np.savez_compressed(CACHE, tested=np.array(tested), **preds)

    msk = ~np.isnan(preds['d30'])
    sub = [r for r, k in zip(ok, msk) if k]
    H = HX[msk]
    arms = {
        'frozen v10 (live)': np.array([frozen.p_up(r['feat']) for r in sub]),
        '8 days, 30 feats': preds['d30'][msk],
        '8 days, 30 + 16 HTF': preds['d46'][msk],
    }
    print('\n' + '=' * 104)
    print('R-15  same-side loss runs -- does trend state as FEATURES cut the 7-9 run?')
    print('=' * 104)
    print('  tested days: %s   (%d rows)' % (', '.join(tested), int(msk.sum())))

    q1, q2 = np.quantile(np.abs(H[:, R1]), [1/3, 2/3])
    bucket = {
        'ALL': np.ones(len(sub), bool),
        '|streak| 0-2': np.abs(H[:, ST]) <= 2,
        '|streak| 3-4': (np.abs(H[:, ST]) >= 3) & (np.abs(H[:, ST]) <= 4),
        '|streak| 5+': np.abs(H[:, ST]) >= 5,
        'TREND |streak|>=3': np.abs(H[:, ST]) >= 3,
        '|ret_1h| low': np.abs(H[:, R1]) < q1,
        '|ret_1h| mid': (np.abs(H[:, R1]) >= q1) & (np.abs(H[:, R1]) < q2),
        '|ret_1h| high': np.abs(H[:, R1]) >= q2,
    }
    idx = {id(r): i for i, r in enumerate(sub)}
    print('\n  %-20s %-22s %5s %7s %9s %8s %7s %6s %6s'
          % ('bucket', 'arm', 'n', 'hit%', 'per $1', 'total', 'maxrun', '>=5', '>=7'))
    keep = {}
    for bn, bm in bucket.items():
        rows = [r for r, k in zip(sub, bm) if k]
        for nm, p in arms.items():
            pp = p[np.array([idx[id(r)] for r in rows])] if rows else np.array([])
            f = T.fire_set(rows, pp) if rows else {}
            s = stats(f)
            keep[(bn, nm)] = (f, s)
            if s is None or s['n'] < MIN_CELL:
                print('  %-20s %-22s %5d   insufficient' % (bn, nm, 0 if s is None else s['n']))
                continue
            print('  %-20s %-22s %5d %6.1f%% %+9.3f %+8.2f %7d %6d %6d'
                  % (bn, nm, s['n'], 100 * s['hit'], s['per1'], s['total'],
                     s['maxrun'], s['ge5'], s['ge7']))
        print()

    print('  PER-DAY MAX SAME-SIDE LOSS RUN (all fires, not bucketed) -- every day')
    alld = sorted({d for nm in arms for d in keep[('ALL', nm)][1]['dmax']})
    print('  %-22s %s' % ('arm', ''.join('%8s' % d for d in alld)))
    for nm in arms:
        dm = keep[('ALL', nm)][1]['dmax']
        print('  %-22s %s' % (nm, ''.join('%8s' % dm.get(d, '-') for d in alld)))

    print('\n  PAIRED: candidate vs frozen v10 on the candles where BOTH fire')
    fa, fb = keep[('ALL', '8 days, 30 + 16 HTF')][0], keep[('ALL', 'frozen v10 (live)')][0]
    shared = sorted(set(fa) & set(fb))
    a, b = keep[('ALL', '8 days, 30 + 16 HTF')][1], keep[('ALL', 'frozen v10 (live)')][1]
    h = len(sub) // 2
    hv = []
    for half in (sub[:h], sub[h:]):
        mm = np.array([idx[id(r)] for r in half])
        x = stats(T.fire_set(half, arms['8 days, 30 + 16 HTF'][mm]))
        z = stats(T.fire_set(half, arms['frozen v10 (live)'][mm]))
        hv.append((x['per1'] - z['per1']) if (x and z) else float('nan'))
    F = Finding('R-15 HTF features vs frozen v10', per_fire=a['per1'] - b['per1'], n=a['n'])
    F.sample({'fires': a['n']})
    F.halves(first=hv[0], second=hv[1])
    F.paired(mine_right=[fa[e]['side'] == fa[e]['actual'] for e in shared],
             theirs_right=[fb[e]['side'] == fb[e]['actual'] for e in shared])
    F.costs({k: T.book(fa, k)['per1'] for k in (0, 0.01, 0.02, 0.03, 0.05)})
    F.null(mine=a['total'], null_value=b['total'], null_name='frozen v10 TOTAL PnL')
    F.verdict()
    print('\n  LOSS-RUN VERDICT (the user\'s question, stated plainly):')
    for nm in arms:
        s = keep[('TREND |streak|>=3', nm)][1]
        if s and s['n'] >= MIN_CELL:
            print('    in trend (|streak|>=3): %-22s n=%d maxrun %d, runs>=5 %d, runs>=7 %d, per $1 %+.3f'
                  % (nm, s['n'], s['maxrun'], s['ge5'], s['ge7'], s['per1']))
        else:
            print('    in trend (|streak|>=3): %-22s insufficient (n=%s)'
                  % (nm, s['n'] if s else 0))


if __name__ == '__main__':
    main()
