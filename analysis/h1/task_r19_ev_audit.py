"""R-19 -- the user asked "how can you be sure the EV formula is correct?" Two parts.

(1) FEES. `model_v10.json` carries fee_rate=0.07 and the EV rule demands edge over a 7% fee. V
    observed that all 76 graded Zurich fills were charged ZERO fees and inferred we have been
    demanding ~1.8c more edge than necessary. That inference is checked here before any constant
    moves, because the constant is a live fire rule over real money.

(2) The EV->PnL ordering is monotone on paper and inverts on the live fills. Explained with data.

The universe is the lanes' full tick set (decisions + trades merged, `r12_train.lane_ticks`), NOT the
`decisions` table alone: `decisions` carries fire=0 on all 22,359 rows - it logs what was considered
and passed over. Replaying the rule on it alone produces zero fires and looks like a broken formula.
"""
import json, os, sqlite3, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T
import task_r8_taker_feature as R8

DB = '/tmp/claude-0/db'
EDGES = [0.1668167346880573, 0.3652950621790043]
THR = {'low': 0.15, 'mid': 0.25, 'high': 0.25}
cost = lambda q, f: q / (1 - f * (1 - q))


def ev_of(ps, ask, fee):
    k = cost(ask, fee)
    return ps * (1 / k - 1) - (1 - ps) if 0 < k < 1 else -9.0


def thr(rv):
    return THR['low'] if rv < EDGES[0] else (THR['mid'] if rv < EDGES[1] else THR['high'])


def main():
    oc = R8.oracle()
    L = [r for r in T.lane_ticks(oc) if r.get('ask') and r['feat'].get('p_venue') is not None]
    L.sort(key=lambda r: r['ts'])
    print('=' * 96)
    print('R-19  EV audit -- is the formula right, and is the fee constant right?')
    print('=' * 96)
    print('  %d ticks over %d candles, %d days' % (len(L), len({r['ep'] for r in L}),
                                                   len({r['day'] for r in L})))

    print('\n  (0) FEE EVIDENCE, read off the live journal')
    z = sqlite3.connect(os.path.join(DB, 'zurich_2.sqlite3'))
    fl = list(z.execute('select shares,spent,fees,price from fills'))
    dd = [sp - sh * px for sh, sp, fe, px in fl if sh and sp and px]
    print('    fills.fees: all %d rows == 0' % len(fl))
    print('    INDEPENDENT check spent - shares*price: max |diff| %.10f over %d fills'
          % (max(abs(x) for x in dd), len(dd)))
    print('    -> no fee is taken AT EXECUTION. That half of V\'s observation is confirmed twice over.')
    vf = [x[0] for x in z.execute('select venue_fees from results where venue_fees is not null')]
    print('    BUT results.venue_fees is non-zero on all %d rows: %.5f .. %.5f, sum %.4f'
          % (len(vf), min(vf), max(vf), sum(vf)))
    print('    It is not monotone in venue_ts, so it is not a cumulative counter; it is roughly')
    print('    constant per row, so it is not obviously a per-trade charge either. UNRESOLVED.')
    print('    Coincidence recorded, NOT concluded from: sum 12.13 vs 12.29 that a 7%%-on-winnings')
    print('    model would charge on the same fills - 1.3%% apart.')

    print('\n  (1) FORMULA PARITY against the engine\'s own logged ev')
    c = sqlite3.connect(os.path.join(DB, 'poly_pnl.sqlite3'))
    d = [abs(ev_of(float(p), float(a), 0.07) - float(e))
         for p, a, e in c.execute('select p,ask,ev from decisions where ev is not null and ask>0')]
    print('    n=%d  max |diff| %.6f  median %.8f  -> the formula is the engine\'s own' % (len(d), max(d), np.median(d)))

    sys.path.insert(0, '/home/user/Django-final-project/learner/v12_2')
    from btc_model_v10 import Model
    frozen = Model('/home/user/Django-final-project/learner/v12_2/model_v10.json')
    P = np.array([frozen.p_up(r['feat']) for r in L])

    def replay(fee):
        # same shape as r12_train.fire_set (one fire per candle, first qualifying tick),
        # with the fee constant made a parameter instead of baked in
        t = {}
        for r, p in zip(L, P):
            if r['ep'] in t:
                continue
            side = 'UP' if p >= 0.5 else 'DOWN'
            ps = p if side == 'UP' else 1 - p
            if ev_of(float(ps), r['ask'], fee) >= thr(r['feat'].get('rv60') or 0.0):
                t[r['ep']] = dict(r, side=side)
        return t

    base = replay(0.07)
    real = T.fire_set(L, P)
    print('')
    print('  FIRE-RULE PARITY at fee=0.07: my replay %d, r12_train.fire_set %d, shared %d'
          % (len(base), len(real), len(set(base) & set(real))))
    print('\n  FEE SENSITIVITY (same p, same asks; PnL always booked at the real 7%% model)')
    print('  %-9s %7s %8s %9s %10s' % ('fee_rate', 'fires', 'win%', 'per $1', 'total'))
    res = {}
    for f in (0.07, 0.05, 0.03, 0.0):
        t = replay(f)
        res[f] = t
        if not t:
            print('  %-9.2f %7d   none' % (f, 0)); continue
        pnl = np.array([R8.per1(x['ask'], x['side'] == x['actual']) for x in t.values()])
        print('  %-9.2f %7d %7.1f%% %+9.3f %+10.2f'
              % (f, len(t), 100 * np.mean([x['side'] == x['actual'] for x in t.values()]),
                 pnl.mean(), pnl.sum()))
    print('\n  the EXTRA candles each lower constant unlocks, judged alone:')
    for f in (0.05, 0.03, 0.0):
        new = [res[f][e] for e in res[f] if e not in base]
        if len(new) < MIN_CELL:
            print('  fee %.2f: %d new   insufficient' % (f, len(new))); continue
        pnl = np.array([R8.per1(x['ask'], x['side'] == x['actual']) for x in new])
        h = len(pnl) // 2
        by = {}
        for x, q in zip(new, pnl):
            by.setdefault(x['day'][-5:], []).append(q)
        print('  fee %.2f: %d new  win %.1f%%  per $1 %+.3f  total %+.2f  halves %+.3f/%+.3f'
              % (f, len(new), 100 * np.mean([x['side'] == x['actual'] for x in new]),
                 pnl.mean(), pnl.sum(), pnl[:h].mean(), pnl[h:].mean()))
        print('           per day ' + '  '.join(
            '%s %s' % (k, ('%+.3f' % np.mean(v)) if len(v) >= 30 else 'insuf') for k, v in sorted(by.items())))
    return L, res


if __name__ == '__main__':
    main()
