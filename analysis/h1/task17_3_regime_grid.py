"""Task 17.3 - rain-or-sun for the 11.2 fire set, plus hour-of-day / weekend.

Two parts, because the literal ask cannot be answered at the available sample and saying so is the
honest deliverable:

  A. THE LITERAL ASK - the PnL grid over the 91 venue-window fires. Buckets fixed in advance
     (Task 13 trailing-range quartiles, 8-hour blocks, weekday/weekend). Nearly every cell is under
     the 60-fire bar. Reported in full, marked, NOT read.

  B. THE ANSWERABLE VERSION - is the model's DIRECTION SIGNAL regime-stable? Measured out of sample
     on ~14k held-out candles using a DIAGNOSTIC model trained on the first 80% of pre-cutoff data.
     This is NOT the frozen artifact and must never overwrite it. Accuracy, not PnL - labelled as
     such, because accuracy is not PnL.
"""
import numpy as np, sys, datetime as dt, joblib
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1/models')
import task16_market_prior_ef as T, task11_2_direction_model as M
from ef11_2_predict import feats_at, SECS

MIN_N = 60
QCUT = [8.6, 13.0, 19.8]          # Task 13 trailing-12-candle range quartiles, fixed in advance
QNAME = ['Q1 calm', 'Q2', 'Q3', 'Q4 busy']
BLOCKS = [(0, 8, '00-08'), (8, 16, '08-16'), (16, 24, '16-24')]


def qbucket(t):
    for i, c in enumerate(QCUT):
        if t < c:
            return i
    return 3


def cell(tag, vals, unit='per-fire'):
    n = len(vals)
    if n == 0:
        print('    %-16s n=   0' % tag); return
    v = np.array(vals)
    mark = '' if n >= MIN_N else '   << n<%d INSUFFICIENT, not read' % MIN_N
    print('    %-16s n=%4d  %s %+7.3f%s' % (tag, n, unit, v.mean(), mark))


if __name__ == '__main__':
    d = np.load(f'{T.SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    Pmap = {int(c) // 1000: p for c, p in zip(cids, paths)}
    act, books = T.engine_actual(), T.venue_books()
    eps = sorted(set(books) & set(act) & set(Pmap))
    t12 = M.trailing12(paths, paths[:, 0]); idx = {int(c) // 1000: i for i, c in enumerate(cids)}
    m = joblib.load('/home/user/Django-final-project/analysis/h1/models/ef11_2_gbm_seed0.joblib')

    # ---------- A. the literal ask ----------
    fires = []
    for ep in eps:
        i = idx.get(ep)
        if i is None or np.isnan(t12[i]):
            continue
        p_arr, a = Pmap[ep], act[ep]
        for S in SECS:
            pu = float(m.predict_proba(feats_at(p_arr, S, t12[i]).reshape(1, -1))[0, 1])
            side = 'UP' if pu >= 0.5 else 'DOWN'
            p = pu if side == 'UP' else 1 - pu
            au, ad, su, sd = T.book_at(books[ep], S)
            ask = au if side == 'UP' else ad
            size = su if side == 'UP' else sd
            if ask is None or not (0.02 < ask < 0.98) or size is None or size * ask < T.MIN_NOTIONAL:
                continue
            if p * (1 / ask) * (1 - T.FEE) - 1 < 0.15:
                continue
            ts = dt.datetime.utcfromtimestamp(ep)
            fires.append(dict(pnl=T.pnl(side == a, ask), q=qbucket(t12[i]),
                              hour=ts.hour, wknd=ts.weekday() >= 5))
            break

    print('=' * 92)
    print('A. RAIN-OR-SUN GRID FOR THE 11.2 FIRE SET (the literal ask) — %d fires, engine grading' % len(fires))
    print('=' * 92)
    print('  by Task 13 regime quartile (trailing 12-candle range, cuts %s bps fixed in advance):' % QCUT)
    for q in range(4):
        cell(QNAME[q], [f['pnl'] for f in fires if f['q'] == q])
    print('  by 8-hour UTC block:')
    for lo, hi, nm in BLOCKS:
        cell(nm, [f['pnl'] for f in fires if lo <= f['hour'] < hi])
    print('  by day type:')
    cell('weekday', [f['pnl'] for f in fires if not f['wknd']])
    cell('weekend', [f['pnl'] for f in fires if f['wknd']])
    print('  per UTC hour:')
    for h in range(24):
        v = [f['pnl'] for f in fires if f['hour'] == h]
        if v:
            cell('%02d:00' % h, v)
    print()
    print('  VERDICT ON PART A: %d of %d cells reach the 60-fire bar. The rain-or-sun question'
          % (sum(1 for g in
                 [[f['pnl'] for f in fires if f['q'] == q] for q in range(4)] +
                 [[f['pnl'] for f in fires if lo <= f['hour'] < hi] for lo, hi, _ in BLOCKS] +
                 [[f['pnl'] for f in fires if f['wknd']], [f['pnl'] for f in fires if not f['wknd']]]
                 if len(g) >= MIN_N),
             4 + len(BLOCKS) + 2))
    print('  CANNOT be answered for the 11.2 fire set at this sample. It needs the forward test.')

    # ---------- B. the answerable version ----------
    print()
    print('=' * 92)
    print('B. IS THE DIRECTION SIGNAL REGIME-STABLE? out-of-sample ACCURACY (not PnL) at scale')
    print('   DIAGNOSTIC model trained on the first 80% of pre-cutoff candles — NOT the frozen')
    print('   artifact, which is never retrained. Evaluated on the held-out 20%.')
    print('=' * 92)
    from sklearn.ensemble import HistGradientBoostingClassifier
    win = min(eps) * 1000
    mask = cids < win
    P2, C2 = paths[mask], cids[mask]
    cut = int(len(P2) * 0.8)
    Xtr, Ytr, _ = M.build_training(P2[:cut], C2[:cut], C2[cut - 1] + 1)
    diag = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_depth=5,
                                          early_stopping=True, validation_fraction=0.15,
                                          random_state=0).fit(Xtr, Ytr)
    t12b = M.trailing12(P2, P2[:, 0])
    rows = []
    for i in range(cut, len(P2)):
        if np.isnan(t12b[i]):
            continue
        up = P2[i, -1] >= P2[i, 0]
        ts = dt.datetime.utcfromtimestamp(C2[i] // 1000)
        for S in (20, 60, 120):
            pu = float(diag.predict_proba(feats_at(P2[i], S, t12b[i]).reshape(1, -1))[0, 1])
            rows.append(dict(ok=((pu >= 0.5) == up), q=qbucket(t12b[i]), S=S,
                             hour=ts.hour, wknd=ts.weekday() >= 5))
    print('  held-out candles: %d   rows: %d' % (len(P2) - cut, len(rows)))
    for S in (20, 60, 120):
        r = [x for x in rows if x['S'] == S]
        print('  --- decision second S=%d  (overall accuracy %.3f, n=%d)'
              % (S, np.mean([x['ok'] for x in r]), len(r)))
        for q in range(4):
            cell(QNAME[q], [x['ok'] for x in r if x['q'] == q], unit='accuracy')
        cell('weekday', [x['ok'] for x in r if not x['wknd']], unit='accuracy')
        cell('weekend', [x['ok'] for x in r if x['wknd']], unit='accuracy')
        for lo, hi, nm in BLOCKS:
            cell(nm, [x['ok'] for x in r if lo <= x['hour'] < hi], unit='accuracy')
