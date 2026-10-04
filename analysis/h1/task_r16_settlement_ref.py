"""R-16 -- is the Binance/venue settlement disagreement a different ORACLE, or a near-tie?

V's lead (verified on 76 live fills): losses concentrate where the Binance direction disagrees with
the venue settlement - 12 lost that Binance called wins, 2 the reverse, disagreement 18% vs ~10% base.
The brief asks for the venue's price-to-beat / Chainlink reference so the distance to it can become a
feature.

BEFORE asking V to log a new field, the cheaper question: HOW BIG is the disagreement? If the two
references differ by a hair, then "disagreement" is not a second oracle the model is blind to - it is
the label flipping on candles that barely moved, and a distance-to-reference feature would be
measuring rounding noise.

Grading rule, applied as the project's own: Polymarket settles on `venues.outcome` (2,036 candles,
independent file). Binance direction is the 5-minute kline close >= open from data-api.binance.vision
(api.binance.com is geo-blocked; the vision host serves the same /api/v3).

The obvious null is stated up front, because the whole finding turns on it: a near-tie candle is a
coin flip for ANY model. If the loss concentration on disagreement candles vanishes once near-ties
are controlled for, then "disagreement" carries no information of its own and the lead is a proxy.
"""
import json, os, sqlite3, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL

DB = '/tmp/claude-0/db'
KL = '/tmp/claude-0/r16_klines.npy'
LANES = [('poly_pnl', 'trades', 'ts_ms'), ('v10_poly_long4', 'trades', 'ts_ms'),
         ('v12_poly_lane', 'trades', 'signal_ms')]


def klines():
    a = np.load(KL)
    return {int(r[0]): (r[1], r[2]) for r in a}


def main():
    K = klines()
    v = sqlite3.connect(os.path.join(DB, 'venues.sqlite3'))
    settle, bmove, bdir = {}, {}, {}
    for e, a in v.execute('select epoch,actual from outcome'):
        e = int(e)
        if e not in K:
            continue
        o, c = K[e]
        settle[e] = str(a).upper()
        bmove[e] = (c / o - 1) * 1e4
        bdir[e] = 'UP' if c >= o else 'DOWN'
    dis = {e: bdir[e] != settle[e] for e in settle}
    print('=' * 92)
    print('R-16  settlement reference -- is the disagreement an oracle gap or a near-tie?')
    print('=' * 92)
    print('  %d candles carry both a venue settlement and a Binance 5m kline.' % len(settle))
    print('  overall disagreement %.2f%%' % (100 * np.mean(list(dis.values()))))

    m = np.array([abs(bmove[e]) for e in settle])
    d = np.array([dis[e] for e in settle])
    print('\n  DISAGREEMENT BY |BINANCE MOVE| (bps) -- the whole question in one table')
    print('  %-16s %8s %12s' % ('|move| bps', 'n', 'disagree%'))
    edges = [0, 1, 2, 5, 10, 20, 50, 1e9]
    for i in range(len(edges) - 1):
        k = (m >= edges[i]) & (m < edges[i + 1])
        lbl = '%.0f-%.0f' % (edges[i], edges[i + 1]) if edges[i + 1] < 1e8 else '50+'
        if k.sum() < MIN_CELL:
            print('  %-16s %8d   insufficient' % (lbl, k.sum())); continue
        print('  %-16s %8d %11.2f%%' % (lbl, k.sum(), 100 * d[k].mean()))
    print('  median |move|: agree %.2f bps, disagree %.2f bps'
          % (np.median(m[~d]), np.median(m[d])))

    print('\n  PER LANE: does the loss concentrate on disagreement candles,')
    print('  and does it SURVIVE controlling for the near-tie? (|move| < 2 bps = near-tie)')
    for name, tab, tcol in LANES:
        p = os.path.join(DB, name + '.sqlite3')
        if not os.path.exists(p):
            print('  %-16s missing' % name); continue
        c = sqlite3.connect(p)
        rows = [(int(e), s, int(w)) for e, s, w in c.execute(
            'select candle_epoch,side,win from %s where win is not null order by candle_epoch,%s'
            % (tab, tcol)) if int(e) in settle]
        if len(rows) < MIN_CELL:
            print('  %-16s n=%d insufficient' % (name, len(rows))); continue
        ep = np.array([r[0] for r in rows])
        won = np.array([r[2] for r in rows], bool)
        dd = np.array([dis[e] for e in ep])
        tie = np.array([abs(bmove[e]) < 2.0 for e in ep])
        print('\n  %s  n=%d  overall win %.3f  disagreement rate %.3f (base %.3f)'
              % (name, len(rows), won.mean(), dd.mean(), np.mean(list(dis.values()))))
        print('    %-26s %7s %9s' % ('cell', 'n', 'win%'))
        for lbl, k in (('agree', ~dd), ('disagree', dd),
                       ('near-tie & agree', tie & ~dd), ('near-tie & disagree', tie & dd),
                       ('moved & agree', ~tie & ~dd), ('moved & disagree', ~tie & dd)):
            if k.sum() < MIN_CELL:
                print('    %-26s %7d   insufficient' % (lbl, k.sum())); continue
            print('    %-26s %7d %8.1f%%' % (lbl, k.sum(), 100 * won[k].mean()))
        # halves and per day on the headline split
        h = len(rows) // 2
        f = lambda s, k: (won[s][k[s]].mean() if k[s].sum() >= 30 else float('nan'))
        s1, s2 = slice(0, h), slice(h, len(rows))
        print('    halves win%% on disagreement: h1 %.3f  h2 %.3f'
              % (f(s1, dd), f(s2, dd)))
        print('    halves win%% on agreement:    h1 %.3f  h2 %.3f'
              % (f(s1, ~dd), f(s2, ~dd)))
        day = np.array([time.strftime('%m-%d', time.gmtime(e)) for e in ep])
        print('    %-8s %6s %8s %6s %8s' % ('day', 'n_dis', 'win_dis', 'n_ag', 'win_ag'))
        for dy in sorted(set(day.tolist())):
            kd, ka = (day == dy) & dd, (day == dy) & ~dd
            print('    %-8s %6d %7s %6d %8s'
                  % (dy, kd.sum(), ('%.3f' % won[kd].mean()) if kd.sum() >= 30 else 'insuf',
                     ka.sum(), ('%.3f' % won[ka].mean()) if ka.sum() >= 30 else 'insuf'))

    print('\n  IS "DISAGREEMENT" KNOWABLE AT DECISION TIME?')
    print('  It is not: it depends on the close. What a live engine could know is the chance the')
    print('  candle ENDS near a tie. Correlation of |move at close| with |move so far| is the')
    print('  practical ceiling on any such feature:')
    import sqlite3 as s3
    c = s3.connect(os.path.join(DB, 'poly_pnl.sqlite3'))
    xs, ys = [], []
    for e, feat in c.execute('select candle_epoch,feat from trades where feat is not null'):
        e = int(e)
        if e not in bmove:
            continue
        try:
            ft = json.loads(feat)
        except Exception:
            continue
        if 'move_bps' in ft:
            xs.append(abs(float(ft['move_bps']))); ys.append(abs(bmove[e]))
    if len(xs) >= MIN_CELL:
        xs, ys = np.array(xs), np.array(ys)
        print('    n=%d  corr(|move so far|, |move at close|) = %.4f' % (len(xs), np.corrcoef(xs, ys)[0, 1]))
        for thr in (1, 2, 5):
            k = xs < thr
            if k.sum() >= MIN_CELL:
                print('    when |move so far| < %d bps (n=%d): P(|close move| < 2 bps) = %.3f  (base %.3f)'
                      % (thr, k.sum(), (ys[k] < 2).mean(), (ys < 2).mean()))


if __name__ == '__main__':
    main()
