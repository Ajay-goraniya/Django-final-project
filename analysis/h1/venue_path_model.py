"""Task 12a - the DIRECTION model over new information: the venue's own per-second quote path.

The question the user asked for: can something learn that a move is wrong and will reverse?
The constraint recorded in STATE.md is that a better model over the ENGINE's inputs will not work,
so this uses the one channel that has already produced a live edge (candidate J): the venue quote
path itself, plus the cross-venue Predict/Polymarket spread.

Null hypothesis, tested at every decision second: the ask LEVEL at that second already says
everything, and the path adds nothing. Reported as a full grid over decision second, never one cell.
Both accuracy AND PnL through the quoted ask, because accuracy is not PnL.
"""
import sqlite3, numpy as np, sys

DB = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db/venues.sqlite3'
FEE = 0.98          # same 2% fee model used in every other H1 study
STEP = 5            # quote samples are every 5 s
DECISION_SECS = [30, 60, 90, 120, 150, 180, 210, 240]


def load():
    """One row per epoch: the 60-sample quote path, the outcome, and the epoch timestamp."""
    c = sqlite3.connect(DB)
    out = dict(c.execute("select epoch, actual from outcome"))
    rows = {}
    for ep, sec, pu, pd_, yu, yd, su, sd in c.execute(
            "select epoch, sec, poly_up, poly_dn, pred_up, pred_dn, pred_size_up, pred_size_dn "
            "from q order by epoch, sec"):
        rows.setdefault(ep, []).append((sec, pu, pd_, yu, yd, su, sd))

    eps, paths, ys = [], [], []
    for ep, r in sorted(rows.items()):
        if ep not in out or len(r) < 60:
            continue
        # sec is seconds-into-the-hour-block; normalise to 0..299 within the 5-min candle
        base = min(x[0] for x in r)
        grid = np.full((60, 6), np.nan)
        for sec, pu, pd_, yu, yd, su, sd in r:
            i = (sec - base) // STEP
            if 0 <= i < 60:
                grid[i] = [pu if pu is not None else np.nan,
                           pd_ if pd_ is not None else np.nan,
                           yu if yu is not None else np.nan,
                           yd if yd is not None else np.nan,
                           su if su is not None else np.nan,
                           sd if sd is not None else np.nan]
        eps.append(ep); paths.append(grid); ys.append(1 if out[ep] == 'UP' else 0)
    return np.array(eps), np.array(paths), np.array(ys)


def implied_up(g):
    """Venue implied P(UP) per sample from the two-sided asks; NaN where the quote is missing."""
    yu, yd = g[:, 2], g[:, 3]
    both = ~np.isnan(yu) & ~np.isnan(yd)
    p = np.full(len(g), np.nan)
    p[both] = yu[both] / (yu[both] + yd[both])
    only = ~np.isnan(yu) & np.isnan(yd)
    p[only] = yu[only]
    return p


def ffill(a):
    out = a.copy()
    last = np.nan
    for i in range(len(out)):
        if np.isnan(out[i]):
            out[i] = last
        else:
            last = out[i]
    return out


def features(g, k):
    """Path features available at sample index k (decision second (k+1)*STEP).

    Level = the null. Everything else is the PATH: where the quote came from, not where it is.
    """
    p = ffill(implied_up(g))
    q = ffill(g[:, 0])                    # Polymarket UP
    if np.isnan(p[k]):
        return None
    win = p[:k + 1]
    lvl = p[k]
    def d(n):                             # change over the last n samples
        j = max(0, k - n)
        return lvl - win[j] if not np.isnan(win[j]) else 0.0
    lo, hi = np.nanmin(win), np.nanmax(win)
    sgn = np.sign(np.diff(win[~np.isnan(win)])) if (~np.isnan(win)).sum() > 1 else np.array([0.0])
    flips = int((np.diff(sgn[sgn != 0]) != 0).sum()) if (sgn != 0).sum() > 1 else 0
    cross = (q[k] - lvl) if not np.isnan(q[k]) else 0.0   # cross-venue spread
    return dict(
        level=lvl,
        d6=d(6), d12=d(12), d24=d(24),        # 30 s / 60 s / 120 s drift of the venue's own price
        from_lo=lvl - lo, from_hi=hi - lvl,   # distance from the running extremes
        rng=hi - lo,
        flips=flips,
        cross=cross,
        vol=float(np.nanstd(np.diff(win))) if (~np.isnan(win)).sum() > 2 else 0.0,
    )


FEATS_PATH = ['level', 'd6', 'd12', 'd24', 'from_lo', 'from_hi', 'rng', 'flips', 'cross', 'vol']
FEATS_NULL = ['level']


def build(paths, ys, k):
    X, Y, L = [], [], []
    for g, y in zip(paths, ys):
        f = features(g, k)
        if f is None:
            continue
        X.append([f[n] for n in FEATS_PATH]); Y.append(y); L.append(f['level'])
    return np.array(X), np.array(Y), np.array(L)


def walk_forward(X, Y, cols, n_fold=4):
    """Strictly forward-in-time: train on everything before the fold, predict the fold. No peeking."""
    from sklearn.linear_model import LogisticRegression
    n = len(Y)
    pred = np.full(n, np.nan)
    edges = [int(n * i / n_fold) for i in range(n_fold + 1)]
    for i in range(1, n_fold):
        tr, te = slice(0, edges[i]), slice(edges[i], edges[i + 1])
        if len(set(Y[tr])) < 2 or edges[i] < 60:
            continue
        m = LogisticRegression(max_iter=2000, C=1.0)
        Xtr = X[tr][:, cols]
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        m.fit((Xtr - mu) / sd, Y[tr])
        pred[te] = m.predict_proba((X[te][:, cols] - mu) / sd)[:, 1]
    return pred


def auc(y, p):
    ok = ~np.isnan(p)
    y, p = y[ok], p[ok]
    if len(set(y)) < 2:
        return float('nan')
    r = np.argsort(np.argsort(p)) + 1
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def pnl_of(y, p, lvl, thr):
    """Trade at the quoted ask whenever the model disagrees with the market by more than thr.

    Buy UP  at ask=lvl      when model says UP  and model - market > thr
    Buy DOWN at ask=1-lvl   when model says DOWN and market - model > thr
    Win pays (1/ask)*FEE - 1; loss pays -1.
    """
    ok = ~np.isnan(p)
    y, p, lvl = y[ok], p[ok], lvl[ok]
    tot, n, w = 0.0, 0, 0
    for yi, pi, li in zip(y, p, lvl):
        if pi - li > thr:
            ask = li
            hit = (yi == 1)
        elif li - pi > thr:
            ask = 1 - li
            hit = (yi == 0)
        else:
            continue
        if not (0.02 < ask < 0.98):
            continue
        n += 1; w += hit
        tot += ((1 / ask) * FEE - 1) if hit else -1.0
    return n, (w / n if n else float('nan')), (tot / n if n else float('nan')), tot


if __name__ == '__main__':
    eps, paths, ys = load()
    print('epochs=%d  UP=%d  DOWN=%d  span=%.1f h'
          % (len(ys), ys.sum(), len(ys) - ys.sum(), (eps[-1] - eps[0]) / 3600.0))
    ip = [FEATS_PATH.index(c) for c in FEATS_PATH]
    inull = [FEATS_PATH.index(c) for c in FEATS_NULL]

    print()
    print('%-5s %6s | %-22s | %-22s' % ('sec', 'n', 'NULL (ask level only)', 'PATH (level + path)'))
    print('%-5s %6s | %8s %13s | %8s %13s' % ('', '', 'AUC', 'calib-acc', 'AUC', 'd-AUC'))
    print('-' * 74)
    grid = {}
    for s in DECISION_SECS:
        k = s // STEP - 1
        X, Y, L = build(paths, ys, k)
        if len(Y) < 60:
            print('%-5d %6d | insufficient' % (s, len(Y))); continue
        pn = walk_forward(X, Y, inull)
        pp = walk_forward(X, Y, ip)
        a_n, a_p = auc(Y, pn), auc(Y, pp)
        ok = ~np.isnan(pn)
        cal = ((L[ok] > 0.5).astype(int) == Y[ok]).mean()
        grid[s] = (len(Y), a_n, a_p, cal, Y, pn, pp, L)
        print('%-5d %6d | %8.4f %13.3f | %8.4f %+13.4f' % (s, len(Y), a_n, cal, a_p, a_p - a_n))

    print()
    print('PnL through the quoted ask (per $1, 2%% fee). thr = required disagreement with the market.')
    print('%-5s | %-28s | %-28s' % ('sec', 'NULL', 'PATH'))
    print('%-5s | %5s %6s %8s %6s | %5s %6s %8s %6s' % ('', 'n', 'hit', 'per-fire', 'total', 'n', 'hit', 'per-fire', 'total'))
    print('-' * 70)
    for thr in (0.03, 0.05, 0.08, 0.12):
        print('thr=%.2f' % thr)
        for s in DECISION_SECS:
            if s not in grid:
                continue
            _, _, _, _, Y, pn, pp, L = grid[s]
            n1, h1, f1, t1 = pnl_of(Y, pn, L, thr)
            n2, h2, f2, t2 = pnl_of(Y, pp, L, thr)
            print('  %-3d | %5d %6.3f %+8.3f %+6.1f | %5d %6.3f %+8.3f %+6.1f' % (s, n1, h1, f1, t1, n2, h2, f2, t2))
