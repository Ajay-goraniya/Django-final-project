"""Task 11.2 - the direction model, scored the way Task 16 says it must be.

V's ack (01:40): evaluate as PnL at the recorded ask on the venue window (engine grading), NEVER
accuracy, and report the fire-distance profile next to the Task 15 part-3 baseline.

The model is a DIRECTION model, not a gate (the user's rule). It outputs p(UP) for every candle at
every decision second; firing is then the engine's own EV arithmetic at the recorded ask, exactly as
in Task 16, so the model and the prior are compared on identical machinery.

Walk-forward by construction: trained ONLY on candles that end before the venue window opens.
Features are all computable live by the engine from its own price path at the fire second.
"""
import numpy as np, sqlite3, json, sys
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import task16_market_prior_ef as T

SECS = T.SECS
LBL, EDGES = T.LBL, T.EDGES
FEATS = ['move_bps', 'abs_move', 'ret5', 'ret15', 'ret30', 'rvol', 'rng', 'pos_in_rng',
         'crossings', 'sec', 'trail12']


def feats_at(path, S, trail12):
    op = path[0]
    px = path[S]
    w = path[:S + 1]
    hi, lo = w.max(), w.min()
    d = np.diff(w)
    cross = int((np.diff(np.sign(w - op)[np.sign(w - op) != 0]) != 0).sum()) if (np.sign(w - op) != 0).sum() > 1 else 0
    bps = lambda a, b: (a - b) / op * 1e4
    return [bps(px, op), abs(bps(px, op)),
            bps(px, w[max(0, S - 5)]), bps(px, w[max(0, S - 15)]), bps(px, w[max(0, S - 30)]),
            (d.std() / op * 1e4) if len(d) > 1 else 0.0,
            bps(hi, lo), ((px - lo) / (hi - lo)) if hi > lo else 0.5,
            cross, float(S), trail12]


def trailing12(paths, op):
    rng = (paths.max(1) - paths.min(1)) / op * 1e4
    out = np.full(len(paths), np.nan)
    cs = np.concatenate([[0.0], np.cumsum(rng)])
    for i in range(12, len(paths)):
        out[i] = (cs[i] - cs[i - 12]) / 12.0
    return out


def build_training(paths, cids, before_ms):
    m = cids < before_ms
    P, C = paths[m], cids[m]
    op = P[:, 0]
    t12 = trailing12(P, op)
    up = (P[:, -1] >= op).astype(int)
    X, Y = [], []
    for i in range(12, len(P)):
        if np.isnan(t12[i]):
            continue
        for S in SECS:
            X.append(feats_at(P[i], S, t12[i])); Y.append(up[i])
    return np.array(X, np.float32), np.array(Y), int(m.sum())


if __name__ == '__main__':
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression

    d = np.load(f'{T.SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    Pmap = {int(c) // 1000: p for c, p in zip(cids, paths)}
    act, books = T.engine_actual(), T.venue_books()
    eps = sorted(set(books) & set(act) & set(Pmap))
    win_start = min(eps) * 1000

    X, Y, n_tr = build_training(paths, cids, win_start)
    print('training rows %d from %d candles (all strictly before the venue window)' % (len(Y), n_tr))

    models = {
        'logistic': LogisticRegression(max_iter=1000),
        'gbm': HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_depth=5,
                                              early_stopping=True, validation_fraction=0.15,
                                              random_state=0),
    }
    mu, sd = X.mean(0), X.std(0) + 1e-9
    fitted = {}
    for name, m in models.items():
        m.fit((X - mu) / sd if name == 'logistic' else X, Y)
        fitted[name] = m
        print('  %s trained' % name)

    # model p for every eval candle at every second
    t12_all = trailing12(paths, paths[:, 0])
    idx = {int(c) // 1000: i for i, c in enumerate(cids)}
    pmap = {name: {} for name in fitted}
    for ep in eps:
        i = idx.get(ep)
        if i is None or np.isnan(t12_all[i]):
            continue
        F = np.array([feats_at(Pmap[ep], S, t12_all[i]) for S in SECS], np.float32)
        for name, m in fitted.items():
            pr = m.predict_proba((F - mu) / sd if name == 'logistic' else F)[:, 1]
            pmap[name][ep] = dict(zip(SECS, pr))

    prior, _ = T.build_prior(paths, cids, win_start)

    def replay_model(pm, margin):
        out = []
        for ep in eps:
            if ep not in pm:
                continue
            p_arr, a = Pmap[ep], act[ep]
            for S in SECS:
                op, px = p_arr[0], p_arr[S]
                pu = pm[ep][S]
                side = 'UP' if pu >= 0.5 else 'DOWN'
                p = pu if side == 'UP' else 1 - pu
                au, ad, su, sd_ = T.book_at(books[ep], S)
                ask = au if side == 'UP' else ad
                size = su if side == 'UP' else sd_
                if ask is None or not (0.02 < ask < 0.98):
                    continue
                if size is None or size * ask < T.MIN_NOTIONAL:
                    continue
                if p * (1 / ask) * (1 - T.FEE) - 1 < margin:
                    continue
                out.append(dict(ep=ep, S=S, side=side, ask=ask,
                                bi=T.bucket(abs(px - op) / op * 1e4),
                                hit=(side == a), pnl=T.pnl(side == a, ask)))
                break
        return out

    print()
    print('=' * 118)
    print('TASK 11.2 - DIRECTION MODEL vs MARKET PRIOR vs CURRENT EF, PnL at the recorded ask')
    print('=' * 118)
    for name in fitted:
        print('-- %s' % name)
        for m in T.EV_MARGINS:
            T.summarise('   %s margin %.2f' % (name, m), replay_model(pmap[name], m),
                        show_profile=(m == 0.25))
    print('-- market prior (Task 16)')
    for m in T.EV_MARGINS:
        T.summarise('   prior margin %.2f' % m, T.replay(eps, Pmap, act, books, prior, m))
