"""R-33 (ask 2) -- run analysis/h1/verify.py's gates over the EF real-score grid CSV.

Every gate V named, on the grid `replay_lanes_1s.py --out` writes. The fee model is Polymarket's
measured live one (R-30b/R-31): 1.67% of SHARES, charged on winners AND losers, which is what the
Zurich journal actually paid -- not per1()'s 7%-of-winnings.

permutation() permutes the predicted SIDES, never the labels -- shuffling labels destroys the
market's calibration and the control prints a fake profit (09-10, cost an hour).
"""
import csv, os, sqlite3, sys, collections
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
POLY_SHARE_FEE = 0.0167


def per1(ask, won, haircut=0.0):
    a = min(0.98, ask + haircut)
    return (1.0 / a - 1.0 - POLY_SHARE_FEE / a) if won else -1.0


def load_grid(path):
    g = collections.defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            if r['win'] == '':
                continue
            g[float(r['theta'])].append(dict(
                ep=int(r['epoch']), sec=int(r['sec']), side=r['side'],
                ask=float(r['ask']), actual=r['actual'], win=int(r['win'])))
    return g


def load_lane(path, lane):
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r['kind'] != lane or r['win'] == '':
                continue
            out.append(dict(ep=int(r['epoch']), side=r['side'], ask=float(r['ask']),
                            win=int(r['win'])))
    return out


def binance_actual():
    d = np.load(os.path.join(T.SP, 'build', 'paths.npz'))
    cid = (d['cid'] // 1000).astype(np.int64)
    p = d['paths'].astype(float)
    return {int(c): ('UP' if p[i, 299] >= p[i, 0] else 'DOWN') for i, c in enumerate(cid)}


def main(grid_csv, rows_csv):
    G = load_grid(grid_csv)
    thetas = sorted(G)
    per = {t: float(np.mean([per1(r['ask'], r['win'] == 1) for r in G[t]])) for t in thetas}
    best = max(thetas, key=lambda t: per[t])
    rows = G[best]
    n = len(rows)

    print('R-33  verify.py gates on the EF grid')
    print('  thetas %s' % ', '.join('%.2f' % t for t in thetas))
    print('  per $1 by theta (measured Polymarket fee, 1.67%% of shares, both outcomes):')
    for t in thetas:
        print('    theta %.2f  n=%-5d per $1 %+7.3f%s'
              % (t, len(G[t]), per[t], '' if len(G[t]) >= MIN_CELL else '   INSUFFICIENT'))
    print('  reading theta=%.2f (the best cell -- named as such, and the sweep gate below is what'
          % best)
    print('   decides whether that peak means anything)')

    F = Finding('EF reversal lane, real-score grid', per_fire=per[best], n=n)

    # grading: the venue's own oracle vs the other venue's, on the same candles
    ven = {r['ep']: r['actual'] for r in rows}
    ba = binance_actual()
    F.grading(polymarket_venues_outcome=ven,
              binance_candles_actual={k: v for k, v in ba.items() if k in ven})

    F.sample({('theta %.2f' % t): len(G[t]) for t in thetas})

    g = sorted(rows, key=lambda r: r['ep'])
    h = len(g) // 2
    F.halves(float(np.mean([per1(r['ask'], r['win'] == 1) for r in g[:h]])),
             float(np.mean([per1(r['ask'], r['win'] == 1) for r in g[h:]])))

    # permutation on the predicted SIDES
    y = np.array([1.0 if r['actual'] == 'UP' else 0.0 for r in rows])
    pred = np.array([1.0 if r['side'] == 'UP' else 0.0 for r in rows])
    price = np.array([r['ask'] for r in rows])

    def pnl_fn(yy, pp, qq):
        return float(np.mean([per1(a, (s == 1.0) == (o == 1.0)) for o, s, a in zip(yy, pp, qq)]))

    F.permutation(y, pred, price, pnl_fn)
    F.sweep([per[t] for t in thetas])
    F.costs({0.0: per[best],
             0.02: float(np.mean([per1(r['ask'], r['win'] == 1, 0.02) for r in rows])),
             0.05: float(np.mean([per1(r['ask'], r['win'] == 1, 0.05) for r in rows]))})

    # two nulls: same side blind at the same ask, and buy the cheap side blind
    same_side = float(np.mean([per1(r['ask'], r['win'] == 1) for r in rows]))
    cheap = []
    for r in rows:
        won = (r['side'] == r['actual'])
        cheap.append(per1(r['ask'], won) if r['ask'] <= 0.5 else -1.0)
    F.null(per[best], same_side, 'same side blind at the same ask (identical by construction)')
    F.null(per[best], float(np.mean(cheap)), 'buy the cheap side blind')

    F.quote_age('venue tape row at or before the read, 1 Hz tape', max_age_s=5.0,
                source='venues.q')

    # paired vs REVERSAL on shared candles
    rev = {r['ep']: r for r in load_lane(rows_csv, 'REVERSAL')}
    shared = [r for r in rows if r['ep'] in rev]
    if len(shared) >= 2:
        F.paired([r['win'] == 1 for r in shared],
                 [rev[r['ep']]['win'] == 1 for r in shared])
    else:
        print('  paired vs REVERSAL: only %d shared candles - not run' % len(shared))

    print()
    print('VERDICT', F.verdict())


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
