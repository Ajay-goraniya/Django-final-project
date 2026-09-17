"""R-12 step 3 -- "who is safe in ALL regimes?" (user, 09-16 00:5x)

BUCKETS ARE DEFINED BEFORE ANY RESULT IS LOOKED AT, and they are the ones already in use elsewhere
in this task (R-12 stage C, R-11): rv60 cut at 0.35 / 0.75, ret60 by tercile of THIS window, plus
the two 1-D views those come from and a time-of-day view. Every cell is reported, never the best one,
and any cell under MIN_CELL=60 graded fires is printed as `insufficient` and must not be read.

"Safe" is not one number, so three are reported per cell and a cell only counts as safe if all three
hold: per-$1 >= 0, the cell's own max drawdown is not larger than its total PnL, and the cell is
readable at all (n >= 60). A strategy is "safe in all regimes" only if every readable cell passes.
Units are $1 of stake per fire; live stake is $10 flat.
"""
import os, sys, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner/v12_checkpoint')
from verify import MIN_CELL
from btc_model_v10 import FEATURES, Model
import r12_train as T
import task_r8_taker_feature as R8
from r12s3_drawdown import curve, drawdown, losing_run, CACHE

MODEL_JSON = '/home/user/Django-final-project/learner/v12_checkpoint/model_v10.json'
RV_EDGES = (0.35, 0.75)          # pre-set, same as R-12 stage C


def rv_bucket(v):
    return 'rv<0.35' if v < RV_EDGES[0] else ('rv0.35-0.75' if v < RV_EDGES[1] else 'rv>0.75')


def cell_stats(trades):
    """trades: list of (epoch, pnl). Returns the three numbers a cell is judged on."""
    if not trades:
        return None
    trades = sorted(trades)
    pnl = np.array([p for _, p in trades], float)
    d = drawdown(pnl)
    return dict(n=len(pnl), per1=float(pnl.mean()), total=float(pnl.sum()),
                dd=d['depth'], uw=d['trough_below_zero'], lose=losing_run(pnl))


def show(title, keys, per_arm):
    print('\n  ' + title)
    print('  %-16s %-22s %5s %9s %9s %9s %6s' %
          ('bucket', 'arm', 'n', 'per $1', 'total', 'maxDD', 'safe'))
    for k in keys:
        for nm in per_arm:
            s = per_arm[nm].get(k)
            if s is None:
                print('  %-16s %-22s %5s' % (k, nm, '0')); continue
            if s['n'] < MIN_CELL:
                print('  %-16s %-22s %5d   insufficient' % (k, nm, s['n'])); continue
            ok = 'yes' if (s['per1'] >= 0 and s['dd'] <= s['total']) else 'NO'
            print('  %-16s %-22s %5d %+9.3f %+9.2f %9.2f %6s'
                  % (k, nm, s['n'], s['per1'], s['total'], s['dd'], ok))
        print()


def main():
    import joblib
    frozen = Model(MODEL_JSON)
    oc = R8.oracle()
    L = T.lane_ticks(oc)
    TS = T.test_store(sorted({r['day'] for r in L}))
    ok = [r for r in L if (r['ep'], r['sec']) in TS]
    ok.sort(key=lambda r: r['ts'])
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in ok])
    m, iso = joblib.load(os.path.join(T.SP, 'r12_fit.joblib'))
    p_hist = T.predict(m, iso, np.array([TS[(r['ep'], r['sec'])] for r in ok], np.float64))
    z = np.load(CACHE, allow_pickle=True)
    preds = {'d8_30': z['d8_30'], 'd8_31': z['d8_31']}
    msk = ~np.isnan(preds['d8_30'])
    sub = [r for r, k in zip(ok, msk) if k]
    arms = {
        'frozen v10 (live)': np.array([frozen.p_up(r['feat']) for r in sub]),
        '8 days, 30 feats': preds['d8_30'][msk],
        '8 days, 30 + p_hist': preds['d8_31'][msk],
        'p_hist alone (18)': p_hist[msk],
    }

    # ret60 terciles fixed ONCE, on the whole evaluated set, so every arm sees identical buckets
    r60 = np.array([r['feat']['ret60'] for r in sub], float)
    q1, q2 = float(np.quantile(r60, 1 / 3)), float(np.quantile(r60, 2 / 3))
    ret_b = lambda v: 'down' if v < q1 else ('flat' if v < q2 else 'up')

    print('=' * 92)
    print('R-12 step 3  REGIME SAFETY  -- who survives every bucket, on PnL *and* drawdown?')
    print('=' * 92)
    print('  buckets pre-set: rv60 at %.2f/%.2f, ret60 terciles of this window (%.4f / %.4f),'
          % (RV_EDGES[0], RV_EDGES[1], q1, q2))
    print('  UTC day, and hour-of-day in 6h blocks. MIN_CELL=%d. Units $1/fire, live stake $10.' % MIN_CELL)
    print('  safe = per $1 >= 0 AND the cell\'s own max drawdown <= the cell\'s total PnL.')

    per_arm = {nm: {} for nm in arms}
    keysets = {'rv60': [], 'ret60': [], 'rv60 x ret60': [], 'UTC day': [], 'hour block': []}
    for nm, p in arms.items():
        f = T.fire_set(sub, p)
        buckets = {}
        for e, t in f.items():
            pnl = R8.per1(t['ask'], t['side'] == t['actual'])
            rb, tb = rv_bucket(t['feat']['rv60']), ret_b(t['feat']['ret60'])
            h = dt.datetime.utcfromtimestamp(e)
            for grp, k in (('rv60', rb), ('ret60', tb), ('rv60 x ret60', '%s/%s' % (tb, rb)),
                           ('UTC day', h.strftime('%m-%d')),
                           ('hour block', '%02d-%02dh' % (h.hour // 6 * 6, h.hour // 6 * 6 + 6))):
                buckets.setdefault((grp, k), []).append((e, pnl))
        for (grp, k), v in buckets.items():
            per_arm[nm][k] = cell_stats(v)
            if k not in keysets[grp]:
                keysets[grp].append(k)

    for grp in ('rv60', 'ret60', 'rv60 x ret60', 'UTC day', 'hour block'):
        show(grp, sorted(keysets[grp]), per_arm)

    print('  VERDICT PER ARM -- readable cells only (n >= %d), across every bucket above' % MIN_CELL)
    allk = [k for g in keysets.values() for k in g]
    print('  %-22s %8s %8s %8s   %s' % ('arm', 'readable', 'safe', 'unsafe', 'cells that fail'))
    for nm in arms:
        rd = [(k, per_arm[nm][k]) for k in allk if per_arm[nm].get(k) and per_arm[nm][k]['n'] >= MIN_CELL]
        bad = [k for k, s in rd if not (s['per1'] >= 0 and s['dd'] <= s['total'])]
        print('  %-22s %8d %8d %8d   %s'
              % (nm, len(rd), len(rd) - len(bad), len(bad), ', '.join(bad) if bad else '-'))
    print()
    print('  unreadable cells (n < %d) per arm: %s' % (MIN_CELL, ', '.join(
        '%s %d/%d' % (nm.split(' (')[0],
                      sum(1 for k in allk if per_arm[nm].get(k) and per_arm[nm][k]['n'] < MIN_CELL),
                      sum(1 for k in allk if per_arm[nm].get(k))) for nm in arms)))


if __name__ == '__main__':
    main()
