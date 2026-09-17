"""Task 12a, pass 2 - ablation, honest costs, both halves.

Pass 1 showed a large edge for a model over the venue quote path and survived a permutation
control. Three things still had to be settled before it could be called a finding:
  1. Is the edge just the engine's EXISTING signal? The Predict/Polymarket spread is not new
     information - the engine already trades off Polymarket. Only the venue's OWN quote path is new.
     -> feature ablation, reported as the full set, not the winner.
  2. Costs: pass 1 charged the normalised implied probability. You pay the RAW ask, and only if
     there is size. -> raw ask + liquidity floor.
  3. The ship rule needs both halves.
"""
import numpy as np, sys
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from venue_path_model import load, implied_up, ffill, walk_forward, auc, FEATS_PATH

FEE = 0.98
SECS = [30, 60, 90, 120, 150, 180, 210, 240]

# The engine already trades off Polymarket, so 'cross' is NOT new information.
OWN_PATH = ['d6', 'd12', 'd24', 'from_lo', 'from_hi', 'rng', 'flips', 'vol']
SETS = {
    'level only (null)':        ['level'],
    'level + cross (known)':    ['level', 'cross'],
    'level + own path (NEW)':   ['level'] + OWN_PATH,
    'everything':               FEATS_PATH,
}


def build2(paths, ys, k, min_size):
    """Features at index k, plus the RAW asks and sizes actually quoted at that second."""
    from venue_path_model import features
    X, Y, L, AU, AD = [], [], [], [], []
    for g, y in zip(paths, ys):
        f = features(g, k)
        if f is None:
            continue
        au, ad = ffill(g[:, 2])[k], ffill(g[:, 3])[k]
        su, sd = ffill(g[:, 4])[k], ffill(g[:, 5])[k]
        if np.isnan(au) or np.isnan(ad):
            continue
        if min_size > 0 and (np.isnan(su) or np.isnan(sd) or su < min_size or sd < min_size):
            continue
        X.append([f[n] for n in FEATS_PATH]); Y.append(y); L.append(f['level'])
        AU.append(au); AD.append(ad)
    return (np.array(X), np.array(Y), np.array(L), np.array(AU), np.array(AD))


def pnl_raw(Y, p, L, AU, AD, thr, haircut=0.0):
    """Decide on implied prob, PAY THE RAW ASK. haircut = cents added to the ask for staleness."""
    ok = ~np.isnan(p)
    Y, p, L, AU, AD = Y[ok], p[ok], L[ok], AU[ok], AD[ok]
    tot = n = w = 0
    for yi, pi, li, au, ad in zip(Y, p, L, AU, AD):
        if pi - li > thr:
            ask, hit = au + haircut, (yi == 1)
        elif li - pi > thr:
            ask, hit = ad + haircut, (yi == 0)
        else:
            continue
        if not (0.02 < ask < 0.98):
            continue
        n += 1; w += hit
        tot += ((1 / ask) * FEE - 1) if hit else -1.0
    return n, (w / n if n else float('nan')), (tot / n if n else float('nan')), tot


if __name__ == '__main__':
    eps, paths, ys = load()
    THR = 0.05
    for min_size in (0, 50):
        print('=' * 96)
        print('LIQUIDITY FLOOR: %s   (decide on implied prob, pay the RAW ask, 2%% fee, per $1)'
              % ('none' if min_size == 0 else 'both sides >= %d' % min_size))
        print('=' * 96)
        print('%-5s %5s | ' % ('sec', 'n') + ' | '.join('%-22s' % k for k in SETS))
        print('%-5s %5s | ' % ('', '') + ' | '.join('%5s %6s %8s' % ('n', 'hit', 'per-fire') for _ in SETS))
        print('-' * 96)
        for s in SECS:
            k = s // 5 - 1
            X, Y, L, AU, AD = build2(paths, ys, k, min_size)
            if len(Y) < 80:
                print('%-5d %5d | insufficient' % (s, len(Y))); continue
            cells = []
            for name, cols in SETS.items():
                idx = [FEATS_PATH.index(c) for c in cols]
                p = walk_forward(X, Y, idx)
                n, h, f, t = pnl_raw(Y, p, L, AU, AD, THR)
                cells.append('%5d %6.3f %+8.3f' % (n, h, f))
            print('%-5d %5d | ' % (s, len(Y)) + ' | '.join(cells))
        print()

    # ---- both halves + staleness haircut, on the NEW channel only ----
    print('=' * 96)
    print('BOTH HALVES and STALENESS, "level + own path (NEW)", no liquidity floor, thr=0.05')
    print('=' * 96)
    print('%-5s | %-20s | %-20s | %-26s' % ('sec', 'first half', 'second half', 'full, +5c / +10c stale'))
    print('%-5s | %5s %8s | %5s %8s | %11s %13s' % ('', 'n', 'per-fire', 'n', 'per-fire', '+5c', '+10c'))
    print('-' * 96)
    idx = [FEATS_PATH.index(c) for c in SETS['level + own path (NEW)']]
    for s in SECS:
        k = s // 5 - 1
        X, Y, L, AU, AD = build2(paths, ys, k, 0)
        p = walk_forward(X, Y, idx)
        ok = ~np.isnan(p)
        sc = np.where(ok)[0]
        mid = sc[len(sc) // 2]
        h1 = np.zeros(len(Y), bool); h1[sc[sc < mid]] = True
        h2 = np.zeros(len(Y), bool); h2[sc[sc >= mid]] = True
        def sub(m):
            q = p.copy(); q[~m] = np.nan
            return pnl_raw(Y, q, L, AU, AD, THR)
        n1, _, f1, _ = sub(h1); n2, _, f2, _ = sub(h2)
        _, _, f5, _ = pnl_raw(Y, p, L, AU, AD, THR, haircut=0.05)
        _, _, f10, _ = pnl_raw(Y, p, L, AU, AD, THR, haircut=0.10)
        print('%-5d | %5d %+8.3f | %5d %+8.3f | %11.3f %13.3f' % (s, n1, f1, n2, f2, f5, f10))
