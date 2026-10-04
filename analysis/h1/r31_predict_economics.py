"""R-31 -- is Predict.fun actually cheaper, and by how much? Measured, not declared.

BOTH venues charge a fee proportional to SHARES, not to stake. That matters, because shares = stake
/ price, so the same share-rate costs more as a fraction of stake at a cheap ask. Measured from the
two live journals, no model assumed:

  POLYMARKET (zurich_2, n=83): fee/shares mean 0.0167, sd 0.0010 -- charged on WINNERS AND LOSERS.
  PREDICT    (tokyo_orders, n=442): fee = 0.02 * shares, charged on WINNERS ONLY. Losers pay
             exactly the stake: pnl == -stake to 5e-5 on all 200 losing rows.

fee/shares has a far tighter sd than fee/stake on the Polymarket rows (0.0010 vs 0.0053), which is
how the share basis was identified rather than assumed.
"""
import json, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import task_r8_taker_feature as R8
import r12_train as T
import r30_btc_state_switch as R30

POLY_SHARE_FEE = 0.0167     # measured, charged on every fire
PRED_SHARE_FEE = 0.02       # declared 0.02 AND measured: fee_shares total 10.253 == empirical 10.253


def per1_gross(ask, won):
    return (1.0 / ask - 1.0) if won else -1.0


def per1_poly_live(ask, won):
    """Measured Polymarket: gross, minus 1.67% of shares whatever happens."""
    return per1_gross(ask, won) - POLY_SHARE_FEE / ask


def per1_predict(ask, won):
    """Measured Predict: gross, minus 2% of shares ONLY when the trade wins."""
    return per1_gross(ask, won) - (PRED_SHARE_FEE / ask if won else 0.0)


def main():
    S = R30.state_features()
    F = [f for f in R30.fires() if f['ep'] in S]
    ask = np.array([f['ask'] for f in F]); won = np.array([f['win'] == 1 for f in F])
    print('R-31  Predict.fun vs Polymarket, on the same %d graded v10 EF fires' % len(F))
    print('  mean ask %.3f, win rate %.1f%%' % (ask.mean(), 100 * won.mean()))

    print('\n  FEE STRUCTURE, MEASURED FROM LIVE ROWS')
    print('  %-12s %-22s %10s %10s %12s' % ('venue', 'basis', 'winners', 'losers', 'n'))
    print('  %-12s %-22s %10s %10s %12s' % (
        'Polymarket', '1.67%% of SHARES', 'charged', 'CHARGED', '83'))
    print('  %-12s %-22s %10s %10s %12s' % (
        'Predict.fun', '2.00%% of SHARES', 'charged', 'zero', '442'))

    print('\n  WHAT THAT COSTS ON THIS FIRE RECORD, per $1 of stake')
    print('  %-14s %10s %10s %11s %12s' % ('arm', 'per $1', 'total', 'fee/$1', 'fee %% stake'))
    for name, fn in (('gross (no fee)', per1_gross),
                     ('Polymarket live', per1_poly_live),
                     ('Predict.fun', per1_predict)):
        v = np.array([fn(a, w) for a, w in zip(ask, won)])
        g = np.array([per1_gross(a, w) for a, w in zip(ask, won)])
        fee = g.mean() - v.mean()
        print('  %-14s %+10.4f %+10.2f %11.4f %11.2f%%' % (
            name, v.mean(), v.sum(), fee, 100 * fee))

    print('\n  THE DIFFERENCE')
    p = np.array([per1_poly_live(a, w) for a, w in zip(ask, won)])
    q = np.array([per1_predict(a, w) for a, w in zip(ask, won)])
    print('  Predict - Polymarket = %+.4f per $1 (%+.2f total over %d fires)'
          % (q.mean() - p.mean(), q.sum() - p.sum(), len(F)))
    print('  Polymarket fee is %.2f%% of stake, Predict %.2f%% -- Predict is %.0f%% cheaper, not "way"'
          % (100 * (np.array([per1_gross(a, w) for a, w in zip(ask, won)]).mean() - p.mean()),
             100 * (np.array([per1_gross(a, w) for a, w in zip(ask, won)]).mean() - q.mean()),
             100 * (1 - (np.array([per1_gross(a, w) for a, w in zip(ask, won)]).mean() - q.mean())
                    / (np.array([per1_gross(a, w) for a, w in zip(ask, won)]).mean() - p.mean()))))

    print('\n  SENSITIVITY: the share basis means the fee scales with 1/ask, so it is not flat')
    print('  %-8s %6s %10s %10s %10s' % ('ask bkt', 'n', 'gross/$1', 'poly/$1', 'predict/$1'))
    for lo, hi in ((0.0, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 1.0)):
        m = (ask >= lo) & (ask < hi)
        if m.sum() < 60:
            print('  %-8s %6d   INSUFFICIENT (<60), not read' % ('%.2f-%.2f' % (lo, hi), m.sum()))
            continue
        gg = np.array([per1_gross(a, w) for a, w in zip(ask[m], won[m])])
        pp = np.array([per1_poly_live(a, w) for a, w in zip(ask[m], won[m])])
        qq = np.array([per1_predict(a, w) for a, w in zip(ask[m], won[m])])
        print('  %-8s %6d %+10.4f %+10.4f %+10.4f' % (
            '%.2f-%.2f' % (lo, hi), m.sum(), gg.mean(), pp.mean(), qq.mean()))


if __name__ == '__main__':
    main()
