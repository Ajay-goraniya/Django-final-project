"""Task 22 - what does an order delay actually cost, and does the quote-age damage scale with it?

The user's question (13:55 UTC 09-11): "check the pollymarket book few milliseconds after the signal
fired? i mean if predict has 300ms delay in order then you check pollymarket book 300ms later?"

That is the right correction and it is the at-or-after rule from Task 20, applied at the venue's real
latency instead of at zero. Both 1 Hz loggers can answer it: measure what an ask does `lag` seconds
after it is observed, CONDITIONAL on it being a cheap print - because an EV filter only ever takes
cheap prints, and Task 20 showed that conditioning is what turns unbiased quote noise into a
one-directional cost.

No outcome labels enter this measurement, so verify.py's grading() does not apply; the checks that
do are sample size, both halves and sweep monotonicity in the lag.
"""
import sqlite3, sys, numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
LAGS = (1, 2, 3, 5, 10)
CHEAP = 0.02          # 2c below that candle's median for that side = a print an EV filter would take


def series(db, tbl, cols):
    c = sqlite3.connect('%s/%s.sqlite3' % (SP, db))
    d = {}
    for ep, sec, au, ad in c.execute('select %s from %s' % (cols, tbl)):
        if ep is None or sec is None:
            continue
        d.setdefault(int(ep), {})[int(sec)] = (au, ad)
    return d


def reversion(d, lag, thresh=CHEAP, which='cheap'):
    """ask(S+lag) - ask(S) for prints `thresh` below (or above) that candle's median for their side."""
    out = []
    for ep, b in sorted(d.items()):
        for i in (0, 1):
            v = {s: x[i] for s, x in b.items() if x[i] is not None}
            if len(v) < 30:
                continue
            med = np.median(list(v.values()))
            for s, a in sorted(v.items()):
                nx = v.get(s + lag)
                if nx is None:
                    continue
                if which == 'all' or (which == 'cheap' and a <= med - thresh) \
                        or (which == 'rich' and a >= med + thresh):
                    out.append(nx - a)
    return np.array(out)


if __name__ == '__main__':
    books = (('Polymarket', series('polybook', 'pb', 'epoch,sec,ask_up,ask_dn')),
             ('Predict.fun', series('book1s', 'b1', 'epoch,sec,ask_up,ask_dn')))
    curves = {}
    for nm, d in books:
        print('==', nm)
        for which in ('all', 'cheap', 'rich'):
            row = []
            for lag in LAGS:
                x = reversion(d, lag, which=which)
                row.append(x.mean() if len(x) >= 60 else float('nan'))
                if len(x) >= 60:
                    h = len(x) // 2
                    print('  %-5s %2ds n=%6d  %+.2fc +- %.2f   halves %+.2fc / %+.2fc'
                          % (which, lag, len(x), 100 * x.mean(), 100 * x.std() / np.sqrt(len(x)),
                             100 * x[:h].mean(), 100 * x[h:].mean()))
                else:
                    print('  %-5s %2ds n=%d INSUFFICIENT' % (which, lag, len(x)))
            if which == 'cheap':
                curves[nm] = (row, reversion(d, 1))
        print()

    for nm, (row, x1) in curves.items():
        h = len(x1) // 2
        F = Finding('Task 22 - %s cheap-print reversion (cost of an order delay)' % nm,
                    per_fire=x1.mean(), n=len(x1))
        F.sample({'cheap prints at lag 1s': len(x1)})
        F.halves(x1[:h].mean(), x1[h:].mean())
        F.sweep(row)
        print('  (grading provenance N/A - no outcome label enters this measurement)')
        print('VERDICT', F.verdict(), '\n')
