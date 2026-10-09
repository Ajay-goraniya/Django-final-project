"""Task 21b (V, REQUEST.md 13:30) - re-price the Polymarket paper on rows whose quote age is KNOWN.

V's v10 runner records `book_age_ms` from 13:28 UTC 09-11. Rows with it non-null are the first
Polymarket paper trades whose entry price can be certified against the at-or-after rule. Everything
before is the set that failed verify.py's quote_age() in Task 24.
"""
import sqlite3, sys, numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
FRESH_MS = 1000


def main():
    c = sqlite3.connect('%s/poly_pnl.sqlite3' % SP)
    rows = [r for r in c.execute(
        'select candle_epoch,side,ask,win,pnl,stake,book_age_ms,actual from trades '
        'where book_age_ms is not null order by candle_epoch') if r[3] is not None and r[5]]
    per = np.array([r[4] / r[5] for r in rows])
    ages = np.array([r[6] for r in rows])
    h = len(per) // 2
    old = np.array([a / b for a, b, in c.execute(
        'select pnl,stake from trades where book_age_ms is null and stake')])

    print('certifiable n=%d  book_age_ms median %.0f p90 %.0f max %.0f  %.0f%% under %dms'
          % (len(per), np.median(ages), np.percentile(ages, 90), ages.max(),
             100 * (ages <= FRESH_MS).mean(), FRESH_MS))
    print('CERTIFIABLE   per $1 %+.3f  (hit %.1f%%)  halves %+.3f / %+.3f'
          % (per.mean(), 100 * np.mean([r[3] for r in rows]), per[:h].mean(), per[h:].mean()))
    print('uncertifiable per $1 %+.3f  (n=%d)' % (old.mean(), len(old)))

    print('\nwithin the certifiable set, by quote age (the confound-free comparison):')
    for nm, m in (('fresh <=1s', ages <= FRESH_MS), ('stale >1s', ages > FRESH_MS)):
        x = per[m]
        print('  %-11s n=%2d  per $1 %+.3f%s'
              % (nm, len(x), x.mean(), '' if len(x) >= 60 else '   <- under the 60 bar, NOT READ'))
    print('\nby side:')
    for side in ('UP', 'DOWN'):
        x = np.array([r[4] / r[5] for r in rows if r[1] == side])
        print('  %-4s n=%2d  per $1 %+.3f%s'
              % (side, len(x), x.mean(), '' if len(x) >= 60 else '   <- under the 60 bar, NOT READ'))

    F = Finding('Task 21b - Polymarket paper on CERTIFIED-FRESH quotes', per_fire=per.mean(), n=len(per))
    F.quote_age('same-instant', 0.0, 'runner-recorded book_age_ms, median %.0f ms' % np.median(ages))
    F.sample({'certifiable graded fires': len(per)})
    F.halves(per[:h].mean(), per[h:].mean())
    print()
    print('  (grading: Polymarket trades settle on Polymarket\'s oracle - checked 429/429 in Task 24)')
    print('VERDICT', F.verdict())


if __name__ == '__main__':
    main()
