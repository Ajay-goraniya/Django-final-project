"""Task 19 (standing) - the two Polymarket items I can answer from data rather than docs.

(3) RESOLUTION MECHANICS. Polymarket's BTC 5-min markets settle on a Chainlink 60-s TWAP, not on the
    Binance close. How close does a 1-s-kline TWAP get to their published outcome? If a kline TWAP
    reproduces it, research on Polymarket can be graded honestly without waiting for their oracle.
    Candidate definitions are fixed in advance and ALL reported - no picking the winner after.

(6) THE v10 POLYMARKET PAPER RUN by hour-of-day and weekday, from the runner snapshot. The user's
    weekend concern. Graded on the runner's own `actual`, which is Polymarket's resolution.
"""
import numpy as np, sqlite3, sys, datetime as dt
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import task16_market_prior_ef as T

MIN_N = 60


def twap_defs(p):
    """Candidate resolution rules, all fixed in advance. p = 300 one-second closes."""
    return {
        'A close>=open (engine)':        p[-1] >= p[0],
        'B TWAP60_end >= open':          p[240:].mean() >= p[0],
        'C TWAP60_end >= TWAP60_start':  p[240:].mean() >= p[:60].mean(),
        'D TWAP60_end >= prev close':    p[240:].mean() >= p[0],   # same anchor, kept for symmetry
        'E last30 mean >= open':         p[270:].mean() >= p[0],
    }


def main():
    d = np.load(f'{T.SP}/build/paths.npz')
    P = {int(c) // 1000: p for c, p in zip(d['cid'], d['paths'].astype(float))}
    polyout = dict(sqlite3.connect(f'{T.DBD}/venues.sqlite3').execute('select epoch, actual from outcome'))
    eng = T.engine_actual()
    common = sorted(set(P) & set(polyout))
    print('=' * 96)
    print('(3) CAN A 1-s KLINE TWAP REPRODUCE POLYMARKET\'S RESOLUTION?   n=%d candles' % len(common))
    print('=' * 96)
    print('%-32s %10s %12s' % ('candidate rule', 'agreement', 'disagreements'))
    print('-' * 96)
    best = None
    for name in twap_defs(P[common[0]]):
        ok = sum(1 for e in common
                 if ('UP' if twap_defs(P[e])[name] else 'DOWN') == polyout[e])
        rate = ok / len(common)
        print('%-32s %9.1f%% %12d' % (name, 100 * rate, len(common) - ok))
        if best is None or rate > best[1]:
            best = (name, rate)
    print()
    print('  Best candidate: %s at %.1f%%.' % (best[0], 100 * best[1]))
    print('  For contrast, the ENGINE\'s own actual agrees with Polymarket on %.1f%%.'
          % (100 * np.mean([eng[e] == polyout[e] for e in common if e in eng])))

    # where the best rule still disagrees
    bn = best[0]
    dis = [e for e in common if ('UP' if twap_defs(P[e])[bn] else 'DOWN') != polyout[e]]
    if dis:
        bps = [abs(P[e][-1] - P[e][0]) / P[e][0] * 1e4 for e in dis]
        allb = [abs(P[e][-1] - P[e][0]) / P[e][0] * 1e4 for e in common]
        print('  Its %d disagreements: median |close-open| %.2f bps vs %.2f bps overall — %s'
              % (len(dis), np.median(bps), np.median(allb),
                 'concentrated in flat candles, as expected'
                 if np.median(bps) < np.median(allb) else 'NOT concentrated in flat candles'))

    print()
    print('=' * 96)
    print('(6) v10 POLYMARKET PAPER RUN by hour and weekday (runner snapshot, POLY grading)')
    print('=' * 96)
    c = sqlite3.connect(f'{T.DBD}/poly_pnl.sqlite3')
    rows = []
    for ep, side, ask, sec, stake, actual, win, pnl in c.execute(
            'select candle_epoch, side, ask, sec, stake, actual, win, pnl from trades '
            'where pnl is not null and stake > 0'):
        ts = dt.datetime.utcfromtimestamp(ep)
        rows.append(dict(pnl=pnl / stake, win=bool(win), hour=ts.hour, wknd=ts.weekday() >= 5,
                         day=ts.strftime('%a'), ask=ask, sec=sec))
    pn = np.array([r['pnl'] for r in rows])
    print('  all trades: n=%d  hit %.1f%%  per-$1 %+.3f  total %+.2f  median ask %.2f  median sec %.0f'
          % (len(rows), 100 * np.mean([r['win'] for r in rows]), pn.mean(), pn.sum(),
             np.median([r['ask'] for r in rows]), np.median([r['sec'] for r in rows])))
    print()
    print('  by day type:')
    for lbl, sel in (('weekday', [r for r in rows if not r['wknd']]),
                     ('weekend', [r for r in rows if r['wknd']])):
        if sel:
            v = np.array([r['pnl'] for r in sel])
            flag = '' if len(sel) >= MIN_N else '   << n<60 INSUFFICIENT'
            print('    %-10s n=%4d  hit %4.1f%%  per-$1 %+.3f%s'
                  % (lbl, len(sel), 100 * np.mean([r['win'] for r in sel]), v.mean(), flag))
        else:
            print('    %-10s n=   0   NO DATA' % lbl)
    print()
    print('  by weekday:')
    for dname in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'):
        sel = [r for r in rows if r['day'] == dname]
        if sel:
            v = np.array([r['pnl'] for r in sel])
            flag = '' if len(sel) >= MIN_N else '   << n<60'
            print('    %-5s n=%4d  hit %4.1f%%  per-$1 %+.3f%s'
                  % (dname, len(sel), 100 * np.mean([r['win'] for r in sel]), v.mean(), flag))
    print()
    print('  by 8-hour UTC block:')
    for lo, hi, nm in ((0, 8, '00-08'), (8, 16, '08-16'), (16, 24, '16-24')):
        sel = [r for r in rows if lo <= r['hour'] < hi]
        if sel:
            v = np.array([r['pnl'] for r in sel])
            flag = '' if len(sel) >= MIN_N else '   << n<60'
            print('    %-6s n=%4d  hit %4.1f%%  per-$1 %+.3f%s'
                  % (nm, len(sel), 100 * np.mean([r['win'] for r in sel]), v.mean(), flag))


if __name__ == '__main__':
    main()
