"""Task 12a REGRADE - V refuted the cross-venue result (commit afcdf4f) and V is right.

The `outcome` table in venues.sqlite3 is POLYMARKET's resolution. Predict.fun settles on the
engine's source (Binance close >= open). I graded Predict.fun trades with Polymarket's answer.
Independently confirmed here: 66 of 627 common candles disagree, 10.5%.

This re-runs the WHOLE of 12a on the engine's actual - not only the positive claim V refuted, but
also my NEGATIVE claim ("the venue's own quote path is dead, 16/16"), which rested on the same bad
labels and therefore was not safe either.
"""
import sqlite3, numpy as np, sys
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import venue_path_model as V
from venue_path_model import implied_up, ffill, walk_forward, FEATS_PATH, auc

DBD = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
FEE = 0.98
SECS = [30, 60, 90, 120, 150, 180, 210, 240]
OWN_PATH = ['d6', 'd12', 'd24', 'from_lo', 'from_hi', 'rng', 'flips', 'vol']
SETS = {'level only (null)': ['level'],
        'level + cross': ['level', 'cross'],
        'level + own path': ['level'] + OWN_PATH,
        'everything': FEATS_PATH}


def engine_actual():
    eng = {}
    for f in ('build11.sqlite3', 'predict_pnl.sqlite3'):
        c = sqlite3.connect(f'{DBD}/{f}')
        for cid, o, cl in c.execute('select candle_id, open, close from candles'):
            eng[cid // 1000] = 'UP' if cl >= o else 'DOWN'
    return eng


def load(source):
    """source: 'poly' (the venues outcome table) or 'engine' (Binance close >= open)."""
    c = sqlite3.connect(f'{DBD}/venues.sqlite3')
    out = dict(c.execute('select epoch, actual from outcome')) if source == 'poly' else engine_actual()
    rows = {}
    for ep, sec, pu, pd_, yu, yd, su, sd in c.execute(
            'select epoch, sec, poly_up, poly_dn, pred_up, pred_dn, pred_size_up, pred_size_dn '
            'from q order by epoch, sec'):
        rows.setdefault(ep, []).append((sec, pu, pd_, yu, yd, su, sd))
    eps, paths, ys = [], [], []
    for ep, r in sorted(rows.items()):
        if ep not in out or len(r) < 60:
            continue
        base = min(x[0] for x in r)
        g = np.full((60, 6), np.nan)
        for sec, pu, pd_, yu, yd, su, sd in r:
            i = (sec - base) // 5
            if 0 <= i < 60:
                g[i] = [np.nan if pu is None else pu, np.nan if pd_ is None else pd_,
                        np.nan if yu is None else yu, np.nan if yd is None else yd,
                        np.nan if su is None else su, np.nan if sd is None else sd]
        eps.append(ep); paths.append(g); ys.append(1 if out[ep] == 'UP' else 0)
    return np.array(eps), np.array(paths), np.array(ys)


def build(paths, ys, k):
    X, Y, L, AU, AD = [], [], [], [], []
    for g, y in zip(paths, ys):
        f = V.features(g, k)
        if f is None:
            continue
        au, ad = ffill(g[:, 2])[k], ffill(g[:, 3])[k]
        if np.isnan(au) or np.isnan(ad):
            continue
        X.append([f[n] for n in FEATS_PATH]); Y.append(y); L.append(f['level'])
        AU.append(au); AD.append(ad)
    return map(np.array, (X, Y, L, AU, AD))


def pnl(Y, p, L, AU, AD, thr, haircut=0.0, mask=None):
    ok = ~np.isnan(p) if mask is None else (~np.isnan(p) & mask)
    Y, p, L, AU, AD = Y[ok], p[ok], L[ok], AU[ok], AD[ok]
    tot = n = w = 0
    for yi, pi, li, au, ad in zip(Y, p, L, AU, AD):
        if pi - li > thr:
            ask, hit = au + haircut, yi == 1
        elif li - pi > thr:
            ask, hit = ad + haircut, yi == 0
        else:
            continue
        if not (0.02 < ask < 0.98):
            continue
        n += 1; w += hit
        tot += ((1 / ask) * FEE - 1) if hit else -1.0
    return n, (w / n if n else float('nan')), (tot / n if n else float('nan'))


if __name__ == '__main__':
    THR = 0.05
    for source in ('poly', 'engine'):
        eps, paths, ys = load(source)
        print('=' * 100)
        print('GRADED ON: %s   (%s)   n_candles=%d'
              % (source.upper(),
                 'Polymarket resolution - WRONG for Predict.fun' if source == 'poly'
                 else "engine actual, Binance close>=open - what Predict.fun settles on", len(ys)))
        print('=' * 100)
        print('%-5s %5s | ' % ('sec', 'n') + ' | '.join('%-21s' % k for k in SETS))
        print('%-5s %5s | ' % ('', '') + ' | '.join('%4s %6s %8s' % ('n', 'hit', 'per-fire') for _ in SETS))
        print('-' * 100)
        for s in SECS:
            k = s // 5 - 1
            X, Y, L, AU, AD = build(paths, ys, k)
            cells = []
            for name, cols in SETS.items():
                idx = [FEATS_PATH.index(c) for c in cols]
                p = walk_forward(X, Y, idx)
                n, h, f = pnl(Y, p, L, AU, AD, THR)
                cells.append('%4d %6.3f %+8.3f' % (n, h, f))
            print('%-5d %5d | ' % (s, len(Y)) + ' | '.join(cells))
        print()

    # halves + staleness on the engine grading, for both the cross set and the own-path set
    eps, paths, ys = load('engine')
    print('=' * 100)
    print('ENGINE GRADING - halves and staleness')
    print('=' * 100)
    for name in ('level + cross', 'level + own path'):
        idx = [FEATS_PATH.index(c) for c in SETS[name]]
        print('-- %s' % name)
        print('   %-5s | %5s %8s | %5s %8s | %8s %8s' % ('sec', 'n1', 'half1', 'n2', 'half2', '+5c', '+10c'))
        for s in SECS:
            k = s // 5 - 1
            X, Y, L, AU, AD = build(paths, ys, k)
            p = walk_forward(X, Y, idx)
            sc = np.where(~np.isnan(p))[0]
            mid = sc[len(sc) // 2]
            m1 = np.zeros(len(Y), bool); m1[sc[sc < mid]] = True
            m2 = np.zeros(len(Y), bool); m2[sc[sc >= mid]] = True
            n1, _, f1 = pnl(Y, p, L, AU, AD, THR, mask=m1)
            n2, _, f2 = pnl(Y, p, L, AU, AD, THR, mask=m2)
            _, _, f5 = pnl(Y, p, L, AU, AD, THR, haircut=0.05)
            _, _, f10 = pnl(Y, p, L, AU, AD, THR, haircut=0.10)
            print('   %-5d | %5d %+8.3f | %5d %+8.3f | %+8.3f %+8.3f' % (s, n1, f1, n2, f2, f5, f10))
