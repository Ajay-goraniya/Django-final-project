"""EF (B) -- is v10 EF's `p` an honest probability on the venue's own outcome?

Graded on `venues.outcome` (Polymarket's own resolution), never candles.actual.

`p` in `trades` is the CHOSEN-SIDE probability, not P(up) -- verified R-28: ev_of(p, ask) matches
the stored `ev` to 4e-4 median 3.7e-5, while flipping it for DOWN is off by a median of 0.048.
So the calibration question is simply: when the lane says p, does it win p of the time?

Reported per ask bucket and per UTC day. Nothing is fitted here, so "walk-forward" means the days
are shown separately and never pooled into one flattering average.
"""
import os, sqlite3, sys, collections, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
BUCKETS = [(0.30, 0.40), (0.40, 0.50), (0.50, 0.60)]


def rows():
    out = []
    ven = dict(sqlite3.connect(os.path.join(D, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))
    c = sqlite3.connect(os.path.join(D, 'poly_pnl.sqlite3'))
    miss = 0
    for ep, side, p, ask, sec, actual in c.execute(
            'select candle_epoch,side,p,ask,sec,actual from trades where win is not null'):
        v = ven.get(int(ep))
        if v is None:
            miss += 1
            continue
        if actual is not None and actual != v:
            miss += 1     # lane's own label disagrees with the venue oracle: drop, do not guess
            continue
        out.append(dict(ep=int(ep), side=side, p=float(p), ask=float(ask), sec=sec,
                        won=(side == v),
                        day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d')))
    return out, miss


def cal(g):
    """mean predicted p vs realised win rate."""
    if not g:
        return None
    p = np.array([r['p'] for r in g])
    w = np.array([r['won'] for r in g], float)
    return len(g), float(p.mean()), float(w.mean()), float(w.mean() - p.mean())


def main():
    R, miss = rows()
    print('EF (B)  v10 EF `p` calibration on venues.outcome')
    print('  %d graded fires kept, %d dropped (no venue outcome, or lane label != venue oracle)'
          % (len(R), miss))
    s = cal(R)
    print('  ALL: n=%d  mean p %.4f  realised %.4f  gap %+.4f' % s)

    print('\n  BY ASK BUCKET (the lane\'s own price band)')
    print('  %-12s %6s %9s %10s %9s' % ('ask', 'n', 'mean p', 'realised', 'gap'))
    for lo, hi in BUCKETS:
        g = [r for r in R if lo <= r['ask'] < hi]
        s = cal(g)
        if not s:
            continue
        print('  %-12s %6d %9.4f %10.4f %+9.4f%s'
              % ('%.2f-%.2f' % (lo, hi), s[0], s[1], s[2], s[3],
                 '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))
    g = [r for r in R if r['ask'] < 0.30 or r['ask'] >= 0.60]
    s = cal(g)
    if s:
        print('  %-12s %6d %9.4f %10.4f %+9.4f%s'
              % ('outside', s[0], s[1], s[2], s[3], '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))

    print('\n  BY DAY x ASK BUCKET -- whole grid, cells under %d marked' % MIN_CELL)
    days = sorted({r['day'] for r in R})
    print('  %-7s %-12s %6s %9s %10s %9s' % ('day', 'ask', 'n', 'mean p', 'realised', 'gap'))
    for d in days:
        for lo, hi in BUCKETS:
            g = [r for r in R if r['day'] == d and lo <= r['ask'] < hi]
            s = cal(g)
            if not s:
                continue
            print('  %-7s %-12s %6d %9.4f %10.4f %+9.4f%s'
                  % (d, '%.2f-%.2f' % (lo, hi), s[0], s[1], s[2], s[3],
                     '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))

    print('\n  THE PRICE IS THE OTHER FORECAST -- is `p` better than just reading the ask?')
    print('  %-12s %6s %11s %11s %11s' % ('ask', 'n', 'Brier(p)', 'Brier(ask)', 'winner'))
    for lo, hi in BUCKETS + [(0.0, 1.0)]:
        g = [r for r in R if lo <= r['ask'] < hi]
        if len(g) < MIN_CELL:
            if g:
                print('  %-12s %6d   INSUFFICIENT' % ('%.2f-%.2f' % (lo, hi), len(g)))
            continue
        y = np.array([r['won'] for r in g], float)
        bp = float(np.mean((np.array([r['p'] for r in g]) - y) ** 2))
        ba = float(np.mean((np.array([r['ask'] for r in g]) - y) ** 2))
        print('  %-12s %6d %11.4f %11.4f %11s'
              % ('%.2f-%.2f' % (lo, hi), len(g), bp, ba,
                 'p' if bp < ba else ('ask' if ba < bp else 'tie')))


if __name__ == '__main__':
    main()
