"""EF (D) -- the pooled Platt pair (a,b) for the engine's _calibrate hook.

p' = sigmoid(a * logit(p) + b), then CLAMPED to never exceed p (the hook may only lower).
Rule unchanged and still fixed before the test: ask <= 0.60 and p' >= ask + 0.06 + 0.0167.

TWO POOLED FITS ARE REPORTED, because "fit on all 1108 then read the days" is in-sample:
  POOLED      - a,b fitted on all 1108. This is the pair that would ship.
  LEAVE-1-DAY - for each day d, a,b refitted on every day EXCEPT d, then read on d. This is the
                honest estimate of what that shipped pair is worth on a day it has not seen.
The gap between the two is the in-sample flattery, and it is stated rather than hidden.
"""
import json, os, sqlite3, sys, datetime as dt
import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
MARGIN, FEE, MAX_ASK = 0.06, 0.0167, 0.60
BUCKETS = [(0.30, 0.40), (0.40, 0.50), (0.50, 0.60)]


def per1(ask, won):
    return (1.0 / ask - 1.0 - FEE / ask) if won else -1.0


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def load():
    ven = dict(sqlite3.connect(os.path.join(D, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))
    out = []
    for ep, side, p, ask, actual in sqlite3.connect(os.path.join(D, 'poly_pnl.sqlite3')).execute(
            'select candle_epoch,side,p,ask,actual from trades where win is not null'):
        v = ven.get(int(ep))
        if v is None or (actual is not None and actual != v):
            continue
        out.append(dict(ep=int(ep), p=float(p), ask=float(ask), won=(side == v),
                        day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d')))
    return sorted(out, key=lambda r: r['ep'])


def fit_ab(rows):
    z = logit(np.array([r['p'] for r in rows])).reshape(-1, 1)
    y = np.array([r['won'] for r in rows], float)
    m = LogisticRegression(max_iter=1000).fit(z, y)
    return float(m.coef_[0][0]), float(m.intercept_[0])


def apply_ab(p, a, b):
    q = 1.0 / (1.0 + np.exp(-(a * logit(p) + b)))
    return float(min(q, p))          # the hook may only LOWER


def stat(rows):
    if not rows:
        return None
    v = np.array([per1(r['ask'], r['won']) for r in rows])
    eq = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    return len(rows), float(np.mean([r['won'] for r in rows])), float(v.mean()), float(v.sum()), dd


def main():
    R = load()
    days = sorted({r['day'] for r in R})
    A, B = fit_ab(R)
    print('EF (D)  pooled Platt pair for the _calibrate hook')
    print('  n=%d venue-graded v10 EF fires, days %s' % (len(R), ' '.join(days)))
    print('  POOLED FIT (all %d rows):  a = %.4f   b = %+.4f' % (len(R), A, B))
    print('  p\' = sigmoid(a*logit(p)+b), clamped to <= p')

    for r in R:
        r['pp'] = apply_ab(r['p'], A, B)
    mp = np.mean([r['p'] for r in R]); mq = np.mean([r['pp'] for r in R]); rw = np.mean([r['won'] for r in R])
    print('  in-sample: mean p %.4f -> p\' %.4f, realised %.4f (gap %+.4f -> %+.4f)'
          % (mp, mq, rw, rw - mp, rw - mq))

    print('\n  (1a) LEAVE-ONE-DAY-OUT: pair refitted without day d, read on day d')
    print('  %-7s %6s %9s %9s %11s %11s %10s' % ('day', 'n', 'a', 'b', 'gap p', "gap p'", "per$1 p'"))
    lo_rows = []
    for d in days:
        tr = [r for r in R if r['day'] != d]
        te = [r for r in R if r['day'] == d]
        a, b = fit_ab(tr)
        for r in te:
            r['pp_lo'] = apply_ab(r['p'], a, b)
        g0 = np.mean([r['won'] for r in te]) - np.mean([r['p'] for r in te])
        g1 = np.mean([r['won'] for r in te]) - np.mean([r['pp_lo'] for r in te])
        f = [r for r in te if r['ask'] <= MAX_ASK and r['pp_lo'] >= r['ask'] + MARGIN + FEE]
        s = stat(f)
        print('  %-7s %6d %9.4f %+9.4f %+11.4f %+11.4f %10s%s'
              % (d, len(te), a, b, g0, g1, ('%+.4f' % s[2]) if s else '  no fires',
                 '' if len(te) >= MIN_CELL else '   day n<60'))
        lo_rows.extend(te)

    print('\n  (1b) PER ASK BUCKET, pooled pair applied (in-sample) vs leave-one-day-out')
    print('  %-12s %6s %10s %12s %12s' % ('ask', 'n', 'gap p', "gap p' pooled", "gap p' LOO"))
    for lo, hi in BUCKETS:
        g = [r for r in R if lo <= r['ask'] < hi]
        if not g:
            continue
        y = np.mean([r['won'] for r in g])
        print('  %-12s %6d %+10.4f %+12.4f %+12.4f%s'
              % ('%.2f-%.2f' % (lo, hi), len(g), y - np.mean([r['p'] for r in g]),
                 y - np.mean([r['pp'] for r in g]),
                 y - np.mean([r['pp_lo'] for r in g if 'pp_lo' in r]),
                 '' if len(g) >= MIN_CELL else '   INSUFFICIENT'))

    print('\n  (2) THE RULE with the POOLED pair: ask<=%.2f and p\'>=ask+%.2f+%.4f'
          % (MAX_ASK, MARGIN, FEE))
    print('  %-26s %6s %7s %10s %10s %9s' % ('arm', 'n', 'W%', 'per $1', 'total', 'maxDD'))
    base = [r for r in R if r['ask'] <= MAX_ASK and r['p'] >= r['ask'] + MARGIN + FEE]
    pool = [r for r in R if r['ask'] <= MAX_ASK and r['pp'] >= r['ask'] + MARGIN + FEE]
    loo = [r for r in R if 'pp_lo' in r and r['ask'] <= MAX_ASK and r['pp_lo'] >= r['ask'] + MARGIN + FEE]
    for lab, g in (('v10 EF, raw p', base), ("pooled a,b (in-sample)", pool),
                   ("leave-one-day-out", loo)):
        s = stat(g)
        if not s:
            print('  %-26s  no fires' % lab); continue
        print('  %-26s %6d %6.1f%% %+10.4f %+10.2f %9.2f%s'
              % (lab, s[0], 100 * s[1], s[2], s[3], s[4],
                 '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))
    nul = sorted(base, key=lambda r: -(r['p'] - r['ask']))[:len(pool)]
    s = stat(nul)
    print('  %-26s %6d %6.1f%% %+10.4f %+10.2f %9.2f   <- the null that beat the daily refit'
          % ('null: top-n by p-ask', s[0], 100 * s[1], s[2], s[3], s[4]))

    print('\n  (2b) DAY BY DAY with the pooled pair -- rain or sun')
    print('  %-7s %6s %7s %10s %10s' % ('day', 'n', 'W%', 'per $1', 'total'))
    for d in days:
        g = [r for r in pool if r['day'] == d]
        s = stat(g)
        if not s:
            print('  %-7s %6d   no fires' % (d, 0)); continue
        print('  %-7s %6d %6.1f%% %+10.4f %+10.2f%s'
              % (d, s[0], 100 * s[1], s[2], s[3], '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))

    print('\n  (3) DOES (a,b) DRIFT? per-day fits, and the pooled pair for reference')
    print('  %-7s %6s %10s %10s' % ('day', 'n', 'a', 'b'))
    aa, bb = [], []
    for d in days:
        g = [r for r in R if r['day'] == d]
        if len(g) < 30:
            print('  %-7s %6d      too few to fit' % (d, len(g))); continue
        a, b = fit_ab(g)
        aa.append(a); bb.append(b)
        print('  %-7s %6d %10.4f %+10.4f%s' % (d, len(g), a, b, '' if len(g) >= MIN_CELL else '   n<60'))
    print('  pooled  %6d %10.4f %+10.4f' % (len(R), A, B))
    if aa:
        print('  spread: a %.4f..%.4f (sd %.4f)   b %+.4f..%+.4f (sd %.4f)'
              % (min(aa), max(aa), float(np.std(aa)), min(bb), max(bb), float(np.std(bb))))


if __name__ == '__main__':
    main()
