"""Task 15 part 3 - where the CURRENT model's fires land on the distance scale, and the null.

V asked: does the fire set avoid the sub-1-bps coin flips, or inherit the current model's 46%?
That needs a baseline, so this also answers the sharper question the part-2 result makes possible:

  AT THE SAME DISTANCE AND THE SAME SECOND, does the engine beat the trivial rule
  "just bet the direction the price has already moved"?

That is the obvious null for the engine itself and it has never been run. Engine grading throughout
(Binance close >= open, which Tokyo's financial_result confirms is what Predict.fun pays on).
"""
import json, numpy as np

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
LB = '/home/user/Django-final-project/learner/live_backup'
EDGES = [0, 1, 2.5, 5, 10, 25, np.inf]
LBL = ['<1', '1-2.5', '2.5-5', '5-10', '10-25', '25+']
MIN_N = 60


def bucket(b):
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= b < EDGES[i + 1]:
            return i
    return len(LBL) - 1


def main():
    d = np.load(f'{SP}/build/paths.npz')
    P = {int(c): p for c, p in zip(d['cid'], d['paths'].astype(float))}
    orders = [r for r in json.load(open(f'{LB}/tokyo_orders.json'))
              if r.get('filled') and r.get('pnl') is not None and r.get('stake')]

    rows = []
    for r in orders:
        p = P.get(r['candle_id'])
        if p is None:
            continue
        s = int(min(max(r.get('seconds_into_candle') or 0, 0), 299))
        op, px, cl = p[0], p[s], p[-1]
        rows.append(dict(
            kind=r['kind'], dirn=r['direction'],
            bps=abs(px - op) / op * 1e4,
            lead='UP' if px >= op else 'DOWN',
            actual='UP' if cl >= op else 'DOWN',
            pnl=r['pnl'] / r['stake'], sec=s))
    print('Tokyo fills matched to klines: %d of %d filled orders' % (len(rows), len(orders)))
    if not rows:
        return

    for kind in ('EF', 'REVERSAL', 'ALL'):
        g = [r for r in rows if kind == 'ALL' or r['kind'] == kind]
        if len(g) < 20:
            print('\n-- %s: n=%d, insufficient' % (kind, len(g))); continue
        print()
        print('=' * 100)
        print('%s: n=%d   distance from open AT THE FIRE SECOND (median fire %.0f s)'
              % (kind, len(g), np.median([r['sec'] for r in g])))
        print('=' * 100)
        print('%-8s %6s %7s | %8s %9s | %9s %9s | %s'
              % ('bps', 'n', 'share', 'ENGINE', 'per-fire', 'NULL hit', 'engine-null', 'engine agrees w/ move'))
        print('-' * 100)
        for i, lbl in enumerate(LBL):
            c = [r for r in g if bucket(r['bps']) == i]
            if not c:
                continue
            hit = np.mean([r['dirn'] == r['actual'] for r in c])
            null = np.mean([r['lead'] == r['actual'] for r in c])
            agree = np.mean([r['dirn'] == r['lead'] for r in c])
            pf = np.mean([r['pnl'] for r in c])
            tag = '' if len(c) >= MIN_N else '  << n<60'
            print('%-8s %6d %6.0f%% | %7.1f%% %+9.3f | %8.1f%% %+9.1fpp | %18.0f%%%s'
                  % (lbl, len(c), 100 * len(c) / len(g), 100 * hit, pf,
                     100 * null, 100 * (hit - null), 100 * agree, tag))
        hit = np.mean([r['dirn'] == r['actual'] for r in g])
        null = np.mean([r['lead'] == r['actual'] for r in g])
        agree = np.mean([r['dirn'] == r['lead'] for r in g])
        print('-' * 100)
        print('%-8s %6d %6.0f%% | %7.1f%% %+9.3f | %8.1f%% %+9.1fpp | %18.0f%%'
              % ('ALL', len(g), 100, 100 * hit, np.mean([r['pnl'] for r in g]),
                 100 * null, 100 * (hit - null), 100 * agree))

    # Does the fire set over- or under-represent the coin-flip bucket vs the market at large?
    print()
    print('=' * 100)
    print('IS THE FIRE SET SELECTIVE? share of fires per bucket vs share of ALL candles at the')
    print('same second (the market baseline from part 2). Selective = fires avoid the flat bucket.')
    print('=' * 100)
    A = d['paths'].astype(float)
    ef = [r for r in rows if r['kind'] == 'EF']
    s_med = int(np.median([r['sec'] for r in ef]))
    op, px = A[:, 0], A[:, s_med]
    mkt = np.abs(px - op) / op * 1e4
    print('(EF median fire second = %d)' % s_med)
    print('%-8s %14s %14s %10s' % ('bps', 'EF fires', 'all candles', 'ratio'))
    for i, lbl in enumerate(LBL):
        f = np.mean([bucket(r['bps']) == i for r in ef])
        m = np.mean((mkt >= EDGES[i]) & (mkt < EDGES[i + 1]))
        print('%-8s %13.0f%% %13.0f%% %10s'
              % (lbl, 100 * f, 100 * m, ('%.2fx' % (f / m)) if m else '-'))


if __name__ == '__main__':
    main()
