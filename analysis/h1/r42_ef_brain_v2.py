"""EF BRAIN v2 -- context-aware and adaptive calibration, walk-forward.

Owner (09-23 01:3x): "more accuracy, more pnl, less drawdowns and adjustable frequency (low
frequency in drawdowns/bad market)". NO GATES: frequency must fall because the brain's p falls, not
because a switch blocks it. Every arm below changes only `p`; the trade rule never changes.

RULE, FIXED BEFORE ANY RESULT AND NEVER SWEPT:
    fire iff  ev_cal >= 0.15  AND  ask <= 0.60,   ev = p/cost - 1, cost(q) = q/(1-0.07*(1-q))
    stake $5.   (ev form verified against the stored `ev` column: median |diff| 3.7e-5.)
Calibrated p is CLAMPED to never exceed raw p, matching the live hook ("may only lower").

ARMS
  A  pooled Platt on logit(p)                  -- what is live now; the null every other arm must beat
  B  context-aware: logistic on [logit(p), sec_left, rv60, |move_bps|, p_venue, logit(p)*sec_left]
  C  adaptive Platt on a ROLLING window of the last N graded fires, N in {200,400,800,all} -- whole grid
  D  B fitted on the same rolling window as C

WALK-FORWARD ONLY: every arm is fitted on fires strictly BEFORE the test day and read on that day.
Day 1 is training-only and never scored.

Grading: venues.outcome (Polymarket's own). Fee: measured live 1.67% of shares, winners AND losers.
"""
import json, os, sqlite3, sys, collections, datetime as dt
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from scipy.stats import binomtest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8
import r12_train as T

D = os.path.join(T.SP, 'db')
STAKE, EV_BAR, MAX_ASK, FEE = 5.0, 0.15, 0.60, 0.0167
NS = [200, 400, 800, None]          # None = all prior fires
BFEATS = ['lp', 'sec_left', 'rv60', 'absmove', 'p_venue', 'lp_x_sec']


def per1(ask, won, haircut=0.0):
    a = min(0.98, ask + haircut)
    return (1.0 / a - 1.0 - FEE / a) if won else -1.0


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def load():
    ven = dict(sqlite3.connect(os.path.join(D, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))
    out = []
    for ep, ts, side, p, ask, sec, rv60, actual, feat in sqlite3.connect(
            os.path.join(D, 'poly_pnl.sqlite3')).execute(
            'select candle_epoch,ts_ms,side,p,ask,sec,rv60,actual,feat from trades '
            'where win is not null and feat is not null'):
        v = ven.get(int(ep))
        if v is None or (actual is not None and actual != v):
            continue
        f = json.loads(feat)
        pv = f.get('p_venue')
        if pv is None or not (0 < pv < 1):
            continue
        s = int(sec) if sec is not None else int(ts) // 1000 - int(ep)
        lp = float(logit(float(p)))
        out.append(dict(ep=int(ep), ts=int(ep) + s, sec=s, side=side, p=float(p), ask=float(ask),
                        won=(side == v), rv60=float(rv60 or 0.0),
                        absmove=abs(float(f.get('move_bps', 0.0))), p_venue=float(pv),
                        sec_left=300.0 - s, lp=lp, lp_x_sec=lp * (300.0 - s) / 300.0,
                        day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d')))
    out.sort(key=lambda r: r['ts'])
    return out


def fit_platt(rows):
    m = LogisticRegression(max_iter=1000).fit(
        np.array([[r['lp']] for r in rows]), np.array([r['won'] for r in rows], float))
    return ('platt', float(m.coef_[0][0]), float(m.intercept_[0]))


def apply_platt(model, r):
    _, a, b = model
    q = 1.0 / (1.0 + np.exp(-(a * r['lp'] + b)))
    return float(min(q, r['p']))


def fit_ctx(rows):
    X = np.array([[r[k] for k in BFEATS] for r in rows], float)
    s = StandardScaler().fit(X)
    m = LogisticRegression(C=1.0, max_iter=3000).fit(s.transform(X),
                                                     np.array([r['won'] for r in rows], float))
    return ('ctx', s, m)


def apply_ctx(model, r):
    _, s, m = model
    q = float(m.predict_proba(s.transform(np.array([[r[k] for k in BFEATS]], float)))[0, 1])
    return float(min(q, r['p']))


def fires(rows, key):
    return [r for r in rows if r['ask'] <= MAX_ASK and R8.ev_of(r[key], r['ask']) >= EV_BAR]


def stat(rows, haircut=0.0):
    if not rows:
        return dict(n=0, w=0.0, per1=0.0, total=0.0, dd=0.0, run=0, byday={})
    v = np.array([per1(r['ask'], r['won'], haircut) for r in rows]) * STAKE
    eq = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    byday = collections.defaultdict(float)
    cnt = collections.Counter()
    for r, x in zip(rows, v):
        byday[r['day']] += x; cnt[r['day']] += 1
    run = mx = 0
    for r in rows:
        run = run + 1 if not r['won'] else 0
        mx = max(mx, run)
    return dict(n=len(rows), w=float(np.mean([r['won'] for r in rows])),
                per1=float(np.mean([per1(r['ask'], r['won'], haircut) for r in rows])),
                total=float(v.sum()), dd=dd, run=mx, byday=dict(byday), cnt=dict(cnt))


def walk(rows, kind, N=None):
    """Fit strictly on prior fires (optionally only the last N), read on the test day."""
    days = sorted({r['day'] for r in rows})
    key = 'q_%s_%s' % (kind, N)
    for i in range(1, len(days)):
        te = [r for r in rows if r['day'] == days[i]]
        tr = [r for r in rows if r['day'] in days[:i]]
        if N:
            tr = tr[-N:]
        if len(tr) < 60 or not te:
            continue
        try:
            model = fit_platt(tr) if kind == 'platt' else fit_ctx(tr)
        except Exception:
            continue
        ap = apply_platt if kind == 'platt' else apply_ctx
        for r in te:
            r[key] = ap(model, r)
    return key


def report(lab, rows, key, arm_a_key=None, A=None):
    g = fires(rows, key)
    s = stat(g)
    flag = '' if s['n'] >= MIN_CELL else '  INSUFFICIENT'
    print('  %-26s %5d %6.1f%% %+9.4f %+10.2f %8.2f %5d%s'
          % (lab, s['n'], 100 * s['w'], s['per1'], s['total'], s['dd'], s['run'], flag))
    return g, s


def paired_vs_a(arm, a_rows):
    am = {r['ep'] for r in arm}; bm = {r['ep'] for r in a_rows}
    sh = am & bm
    ao = am - bm; bo = bm - am
    byA = {r['ep']: r for r in a_rows}; byB = {r['ep']: r for r in arm}
    x = sum(1 for e in sh if byB[e]['won'] and not byA[e]['won'])
    y = sum(1 for e in sh if byA[e]['won'] and not byB[e]['won'])
    p = binomtest(x, x + y, 0.5).pvalue if x + y else 1.0
    return len(sh), x + y, p, len(ao), len(bo)


def main():
    R = load()
    days = sorted({r['day'] for r in R})
    print('EF BRAIN v2 -- rule FIXED BEFORE: ev_cal >= %.2f, ask <= %.2f, stake $%.0f'
          % (EV_BAR, MAX_ASK, STAKE))
    print('  %d venue-graded fires, days %s; day 1 is training-only' % (len(R), ' '.join(days)))
    print('  calibrated p is clamped to <= raw p, matching the live hook')

    ka = walk(R, 'platt', None)
    kb = walk(R, 'ctx', None)
    keys = {'A pooled Platt (live)': ka, 'B context-aware': kb}
    for N in NS:
        keys['C adaptive Platt N=%s' % (N or 'all')] = walk(R, 'platt', N)
    for N in NS:
        keys['D ctx + rolling N=%s' % (N or 'all')] = walk(R, 'ctx', N)

    print('\n  %-26s %5s %6s %9s %10s %8s %5s'
          % ('arm', 'n', 'right', 'per$1', 'total$', 'maxDD$', 'run'))
    raw = [r for r in R if r['day'] != days[0]]
    for r in raw:
        r['p_raw'] = r['p']
    report('raw p (no calibration)', raw, 'p_raw')
    out = {}
    for lab in sorted(keys):
        rows = [r for r in R if keys[lab] in r]
        out[lab] = report(lab, rows, keys[lab])

    A_rows = out['A pooled Platt (live)'][0]
    print('\n  VERIFY vs arm A (the live null): halves, costs, paired on shared candles')
    print('  %-26s %14s %20s %26s' % ('arm', 'halves', 'costs +0/+2/+5c', 'paired vs A'))
    for lab in sorted(keys):
        g, s = out[lab]
        if not g:
            continue
        q = sorted(g, key=lambda r: r['ts']); h = len(q) // 2
        h1 = stat(q[:h])['per1']; h2 = stat(q[h:])['per1']
        c0, c2, c5 = s['per1'], stat(g, 0.02)['per1'], stat(g, 0.05)['per1']
        sh, disc, p, ao, bo = paired_vs_a(g, A_rows)
        print('  %-26s %+6.3f/%+6.3f %6.3f/%6.3f/%6.3f  shared %3d disc %2d p=%.3f (+%d/-%d)'
              % (lab, h1, h2, c0, c2, c5, sh, disc, p, ao, bo))

    print('\n  ADJUSTABLE FREQUENCY -- fires/day on A\'s 3 WORST vs 3 BEST days')
    ad = stat(A_rows)['byday']
    worst = sorted(ad, key=lambda d: ad[d])[:3]
    best = sorted(ad, key=lambda d: -ad[d])[:3]
    print('  A\'s worst days %s ($%s) | best %s ($%s)'
          % (','.join(worst), ','.join('%+.0f' % ad[d] for d in worst),
             ','.join(best), ','.join('%+.0f' % ad[d] for d in best)))
    print('  %-26s %14s %14s %10s' % ('arm', 'fires/day worst', 'fires/day best', 'worst/best'))
    for lab in sorted(keys):
        g, s = out[lab]
        c = s.get('cnt', {})
        w = np.mean([c.get(d, 0) for d in worst]); b = np.mean([c.get(d, 0) for d in best])
        print('  %-26s %14.1f %14.1f %10s'
              % (lab, w, b, ('%.2f' % (w / b)) if b else '-'))

    print('\n  DAY BY DAY per$1 (walk-forward)')
    print('  %-26s %s' % ('arm', ' '.join('%7s' % d for d in days[1:])))
    for lab in sorted(keys):
        g, _ = out[lab]
        bd = collections.defaultdict(list)
        for r in g:
            bd[r['day']].append(per1(r['ask'], r['won']))
        print('  %-26s %s' % (lab, ' '.join(
            ('%+7.3f' % np.mean(bd[d])) if bd.get(d) else '      -' for d in days[1:])))


if __name__ == '__main__':
    main()
