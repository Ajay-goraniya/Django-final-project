"""EF (C) -- a retrained EF brain, walk-forward, against v10 EF on the SAME candles.

THE TRADE RULE AND ITS MARGIN ARE FIXED BEFORE ANY RESULT IS READ, and they are the lane's own:
    fire iff  ask <= 0.60  AND  p >= ask + MARGIN + FEE,   MARGIN = 0.06, FEE = 0.0167
MARGIN is the 0.06 in poly_ef's own price rule; FEE is the measured Polymarket share fee (R-30b).
Neither is swept, tuned, or revisited. No gates.

TWO CANDIDATE ARMS, both trained on days 1..k and read on day k+1 only:
  (cal)  calibration only -- Platt-scale v10's own `p`. This is the minimal fix implied by (B),
         which found `p` overconfident by ~7pp uniformly across every ask bucket.
  (fit)  a fresh logistic on the 30 features v10 EF sees at fire time, same label.

THE LABEL IS THE VENUE'S OWN ORACLE, `venues.outcome`. Never candles.actual.

STATED LIMIT, up front: every row here is a candle v10 EF ALREADY CHOSE to fire on. Retraining on
that set can only re-rank or drop v10's own fires; it cannot discover fires v10 never took. So this
answers "can the brain be made honest on the trades it takes", not "is there a better EF".
"""
import json, os, sqlite3, sys, collections, datetime as dt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from scipy.stats import binomtest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
MARGIN, FEE, MAX_ASK = 0.06, 0.0167, 0.60        # FIXED BEFORE THE TEST. Not swept.
FEATS = ['basis_bps', 'dist_hi_bps', 'dist_lo_bps', 'hod_cos', 'hod_sin', 'imb20', 'imb5', 'lv',
         'lv_x_sec', 'micro_bps', 'move_bps', 'mv_x_sec', 'ofi15', 'ofi5', 'ofi60', 'p_venue',
         'perp_n15', 'pos_in_range', 'prev1_bps', 'prev2_bps', 'range_bps', 'ret15', 'ret30',
         'ret5', 'ret60', 'rv60', 'sec_left', 'spot_imb15', 'spot_imb60', 'spread_bps']


def per1(ask, won):
    return (1.0 / ask - 1.0 - FEE / ask) if won else -1.0


def load():
    ven = dict(sqlite3.connect(os.path.join(D, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))
    out = []
    c = sqlite3.connect(os.path.join(D, 'poly_pnl.sqlite3'))
    for ep, side, p, ask, actual, feat in c.execute(
            'select candle_epoch,side,p,ask,actual,feat from trades '
            'where win is not null and feat is not null'):
        v = ven.get(int(ep))
        if v is None or (actual is not None and actual != v):
            continue
        f = json.loads(feat)
        if any(f.get(k) is None for k in FEATS):
            continue
        out.append(dict(ep=int(ep), side=side, p=float(p), ask=float(ask), won=(side == v),
                        x=np.array([float(f[k]) for k in FEATS]),
                        day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d')))
    return sorted(out, key=lambda r: r['ep'])


def fires(rows, pkey):
    return [r for r in rows if r['ask'] <= MAX_ASK and r[pkey] >= r['ask'] + MARGIN + FEE]


def stat(rows, pkey=None):
    if not rows:
        return None
    v = np.array([per1(r['ask'], r['won']) for r in rows])
    eq = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0
    return len(rows), float(np.mean([r['won'] for r in rows])), float(v.mean()), float(v.sum()), dd


def main():
    R = load()
    days = sorted({r['day'] for r in R})
    print('EF (C)  retrained EF brain, walk-forward by day')
    print('  %d graded fires with a full feature vector, days %s' % (len(R), ' '.join(days)))
    print('  RULE FIXED BEFORE THE TEST: ask <= %.2f and p >= ask + %.2f + %.4f. Not swept.'
          % (MAX_ASK, MARGIN, FEE))

    for r in R:
        r['p_v10'] = r['p']
    preds = {'cal': [], 'fit': []}
    tested = []
    for i in range(1, len(days)):
        tr = [r for r in R if r['day'] in days[:i]]
        te = [r for r in R if r['day'] == days[i]]
        if len(tr) < 60 or not te:
            continue
        ytr = np.array([r['won'] for r in tr], float)
        # (cal) Platt on v10's own p, in logit space
        ptr = np.clip(np.array([r['p_v10'] for r in tr]), 1e-4, 1 - 1e-4)
        ztr = np.log(ptr / (1 - ptr)).reshape(-1, 1)
        try:
            m = LogisticRegression(max_iter=1000).fit(ztr, ytr)
            pte = np.clip(np.array([r['p_v10'] for r in te]), 1e-4, 1 - 1e-4)
            zte = np.log(pte / (1 - pte)).reshape(-1, 1)
            for r, q in zip(te, m.predict_proba(zte)[:, 1]):
                r['p_cal'] = float(q)
        except Exception:
            for r in te:
                r['p_cal'] = r['p_v10']
        # (fit) fresh logistic on the 30 features
        try:
            s = StandardScaler().fit(np.array([r['x'] for r in tr]))
            g = LogisticRegression(C=0.3, max_iter=2000).fit(s.transform(np.array([r['x'] for r in tr])), ytr)
            for r, q in zip(te, g.predict_proba(s.transform(np.array([r['x'] for r in te])))[:, 1]):
                r['p_fit'] = float(q)
        except Exception:
            for r in te:
                r['p_fit'] = r['p_v10']
        tested.extend(te)

    print('  walk-forward tested days: %s (%d rows; day 1 is training-only)'
          % (' '.join(sorted({r['day'] for r in tested})), len(tested)))

    print('\n  CALIBRATION OF EACH BRAIN on the tested rows (mean p vs realised)')
    for k, lab in (('p_v10', 'v10 EF (as shipped)'), ('p_cal', 'Platt-recalibrated'), ('p_fit', 'fresh 30-feature fit')):
        g = [r for r in tested if k in r]
        if not g:
            continue
        mp = float(np.mean([r[k] for r in g])); rw = float(np.mean([r['won'] for r in g]))
        print('    %-22s n=%-5d mean p %.4f  realised %.4f  gap %+.4f' % (lab, len(g), mp, rw, rw - mp))

    print('\n  THE TRADE RULE APPLIED, whole picture, cells under %d marked' % MIN_CELL)
    print('    %-22s %6s %7s %10s %10s %9s' % ('arm', 'n', 'W%', 'per $1', 'total', 'maxDD'))
    res = {}
    for k, lab in (('p_v10', 'v10 EF (as shipped)'), ('p_cal', 'Platt-recalibrated'), ('p_fit', 'fresh 30-feature fit')):
        g = fires([r for r in tested if k in r], k)
        res[k] = g
        s = stat(g)
        if not s:
            print('    %-22s  fires 0' % lab)
            continue
        print('    %-22s %6d %6.1f%% %+10.4f %+10.2f %9.2f%s'
              % (lab, s[0], 100 * s[1], s[2], s[3], s[4],
                 '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))

    print('\n  PAIRED vs v10 EF on SHARED candles (discordant pairs only)')
    base = {r['ep'] for r in res['p_v10']}
    for k, lab in (('p_cal', 'Platt-recalibrated'), ('p_fit', 'fresh 30-feature fit')):
        mine = {r['ep']: r for r in res[k]}
        sh = sorted(base & set(mine))
        if len(sh) < 2:
            print('    %-22s only %d shared candles - not run' % (lab, len(sh)))
            continue
        bym = {r['ep']: r for r in res['p_v10']}
        a = sum(1 for e in sh if mine[e]['won'] and not bym[e]['won'])
        b = sum(1 for e in sh if bym[e]['won'] and not mine[e]['won'])
        p = binomtest(a, a + b, 0.5).pvalue if a + b else 1.0
        print('    %-22s shared %d, discordant %d (mine %d / v10 %d), McNemar p=%.3f%s'
              % (lab, len(sh), a + b, a, b, p,
                 '' if a + b >= MIN_CELL else '   %d pairs under the %d bar - NOT a finding' % (a + b, MIN_CELL)))


if __name__ == '__main__':
    main()


def nulls():
    """THE DECISIVE TEST. The paired() gate came back with ZERO discordant pairs, which is not a
    pass -- it means every candidate fire set is a strict SUBSET of v10's fires and no call ever
    changed side. So these arms are not brains, they are selection rules, and R-19/R-28/R-29 all
    established that a selection rule which raises per-$1 is usually just buying cheaper.

    So: at each arm's own fire count, compare against trivial selectors on the SAME rows -- take the
    top n by v10's own margin (p - ask), and take the n cheapest asks. If the retrain cannot beat
    those, it has added nothing.
    """
    R = load()
    days = sorted({r['day'] for r in R})
    for r in R:
        r['p_v10'] = r['p']
    tested = []
    for i in range(1, len(days)):
        tr = [r for r in R if r['day'] in days[:i]]
        te = [r for r in R if r['day'] == days[i]]
        if len(tr) < 60 or not te:
            continue
        ytr = np.array([r['won'] for r in tr], float)
        ptr = np.clip(np.array([r['p_v10'] for r in tr]), 1e-4, 1 - 1e-4)
        m = LogisticRegression(max_iter=1000).fit(np.log(ptr / (1 - ptr)).reshape(-1, 1), ytr)
        pte = np.clip(np.array([r['p_v10'] for r in te]), 1e-4, 1 - 1e-4)
        for r, q in zip(te, m.predict_proba(np.log(pte / (1 - pte)).reshape(-1, 1))[:, 1]):
            r['p_cal'] = float(q)
        s = StandardScaler().fit(np.array([r['x'] for r in tr]))
        g = LogisticRegression(C=0.3, max_iter=2000).fit(s.transform(np.array([r['x'] for r in tr])), ytr)
        for r, q in zip(te, g.predict_proba(s.transform(np.array([r['x'] for r in te])))[:, 1]):
            r['p_fit'] = float(q)
        tested.extend(te)

    base = fires(tested, 'p_v10')
    print('\n  THE R-19 NULL -- at the same fire count, on the same rows')
    print('    %-26s %6s %8s %10s %10s %9s' % ('arm', 'n', 'W%', 'per $1', 'total', 'maxDD'))
    s = stat(base)
    print('    %-26s %6d %7.1f%% %+10.4f %+10.2f %9.2f' % ('v10 EF (all its fires)', s[0], 100 * s[1], s[2], s[3], s[4]))
    for k, lab in (('p_cal', 'Platt-recalibrated'), ('p_fit', 'fresh 30-feature fit')):
        arm = fires(tested, k)
        n = len(arm)
        if not n:
            continue
        by_margin = sorted(base, key=lambda r: -(r['p_v10'] - r['ask']))[:n]
        by_cheap = sorted(base, key=lambda r: r['ask'])[:n]
        for nm, rows in ((lab, arm), ('  null: top-%d by margin' % n, by_margin),
                         ('  null: %d cheapest asks' % n, by_cheap)):
            t = stat(rows)
            print('    %-26s %6d %7.1f%% %+10.4f %+10.2f %9.2f%s'
                  % (nm, t[0], 100 * t[1], t[2], t[3], t[4],
                     '' if t[0] >= MIN_CELL else '  INSUFFICIENT'))
    print('\n    Sides: the retrain NEVER changes a side -- it only drops fires. 0 discordant pairs')
    print('    in the paired test is the proof, not a pass.')
