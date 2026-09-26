"""Task 24 - checking V's "the venue IS the finding, stop testing and build" (commit 5f96d1e).

It drives live money, so it gets the full gate. Three things V's note does not establish are tested
here: (1) are the extra candles real, or did Predict.fun's book simply not exist for them;
(2) is Polymarket's cheaper ask fair value for a different settlement rule; (3) does the number
survive verify.py - in particular quote_age(), the check that caught my own +0.266.
"""
import sqlite3, sys, numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'


def main():
    v = sqlite3.connect('%s/venues.sqlite3' % SP)
    pp = sqlite3.connect('%s/poly_pnl.sqlite3' % SP)
    tr = list(pp.execute('select candle_epoch,side,ask,win,pnl,stake from trades'))
    per = np.array([r[4] / r[5] for r in tr if r[5]])
    h = len(per) // 2

    # grading: Polymarket trades settle on Polymarket's oracle - that IS the venues outcome table.
    poly = {e: a for e, a in v.execute('select epoch,actual from outcome') if a}
    logged = {r[0]: ('UP' if (r[3] and r[1] == 'UP') or (not r[3] and r[1] == 'DOWN') else 'DOWN')
              for r in tr if r[3] is not None}

    # cost sensitivity: Task 23 says a 5-s stale cheap print on Polymarket is worth 0.88c.
    by_h = {}
    for hc in (0.0, 0.005, 0.01, 0.02):
        tot = []
        for ep, side, ask, win, pnl, stake in tr:
            if not stake or ask is None:
                continue
            fee = (1.0 / ask - 1.0) - (pnl / stake) if win else 0.0
            a2 = min(0.99, ask + hc)
            tot.append((1.0 / a2 - 1.0 - fee) if win else -1.0)
        by_h[hc] = float(np.mean(tot))

    F = Finding("V's claim: Polymarket paper +0.187/$1, 'stop testing and build'",
                per_fire=per.mean(), n=len(per))
    F.grading(polymarket_outcome_table=poly, polymarket_paper_own_labels=logged)
    F.quote_age('stale', 5.0, 'poly paper ask: only 23 of 427 match the collector at the same second')
    F.sample({'all fires': len(per),
              'UP': sum(1 for r in tr if r[1] == 'UP'),
              'DOWN': sum(1 for r in tr if r[1] == 'DOWN')})
    F.halves(per[:h].mean(), per[h:].mean())
    F.costs(by_h)
    F.null(per.mean(), -0.276, 'always-buy-the-cheap-side (V, 13:45)')
    print('VERDICT', F.verdict())


if __name__ == '__main__':
    main()
