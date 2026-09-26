"""EF drawdown -- does pausing help, or is it random removal with a story attached?

Owner (09-22 22:5x): "i want profitable ef that has no drawdowns by tomorrow. You can stop trading
in drawdown period or when market is wrong for us or something else but don't waste profit."

A pause IS a regime switch, so every bucket and every grid cell below was fixed by V BEFORE any
number was read, and all of them are reported.

THE ORDER MATTERS. (1) comes first because it decides whether the rest can mean anything: if EF
losses do not cluster, then removing fires after a losing run is statistically the same as removing
fires at random, and every pause cell must be read against that null.

Stake $3. Fees: the measured Polymarket live fee, 1.67% of shares, winners AND losers (R-30b).
Calibration: the pooled Platt pair from r37 (a=1.0677, b=-0.3208), clamped to never raise p.
Grading: venues.outcome, the venue's own oracle.
"""
import csv, json, os, sqlite3, sys, datetime as dt
import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
STAKE = 3.0
MARGIN, FEE, MAX_ASK = 0.06, 0.0167, 0.60
LS = [2, 3, 4]
MS = [15, 30, 60, 120]
XS = [2, 3, 4]
SHUFFLES = 100


def per1(ask, won):
    return (1.0 / ask - 1.0 - FEE / ask) if won else -1.0


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
            'where win is not null'):
        v = ven.get(int(ep))
        if v is None or (actual is not None and actual != v):
            continue
        f = json.loads(feat) if feat else {}
        s = int(sec) if sec is not None else int(ts) // 1000 - int(ep)
        out.append(dict(ep=int(ep), ts=int(ep) + s, sec=s, side=side, p=float(p), ask=float(ask),
                        actual=v, won=(side == v), rv60=float(rv60 or 0.0),
                        body=abs(float(f.get('move_bps', 0.0))),
                        hour=dt.datetime.utcfromtimestamp(int(ep)).hour,
                        day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d')))
    out.sort(key=lambda r: r['ts'])
    for r in out:
        r['pnl'] = per1(r['ask'], r['won'])
        r['settle'] = r['ep'] + 300
    return out


def calibrate(rows):
    z = logit(np.array([r['p'] for r in rows])).reshape(-1, 1)
    y = np.array([r['won'] for r in rows], float)
    m = LogisticRegression(max_iter=1000).fit(z, y)
    a, b = float(m.coef_[0][0]), float(m.intercept_[0])
    for r in rows:
        q = 1.0 / (1.0 + np.exp(-(a * logit(r['p']) + b)))
        r['p_cal'] = float(min(q, r['p']))
    return a, b


def stat(rows):
    if not rows:
        return dict(n=0, w=0.0, per1=0.0, total=0.0, dd=0.0, run=0)
    v = np.array([r['pnl'] for r in rows]) * STAKE
    eq = np.cumsum(v)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    run = mx = 0
    for r in rows:
        run = run + 1 if not r['won'] else 0
        mx = max(mx, run)
    return dict(n=len(rows), w=float(np.mean([r['won'] for r in rows])),
                per1=float(np.mean([r['pnl'] for r in rows])), total=float(v.sum()),
                dd=dd, run=mx)


# ---------------- (1) clustering ----------------
def clustering(rows, label):
    y = np.array([1 if r['won'] else 0 for r in rows])
    n1, n0 = int(y.sum()), int(len(y) - y.sum())
    runs = 1 + int(np.sum(y[1:] != y[:-1]))
    mu = 1 + 2.0 * n1 * n0 / (n1 + n0)
    var = (mu - 1) * (mu - 2) / (n1 + n0 - 1)
    z = (runs - mu) / np.sqrt(var) if var > 0 else 0.0
    from scipy.stats import norm
    p = 2 * (1 - norm.cdf(abs(z)))
    # The verdict must depend on SIGNIFICANCE, not on the sign of z. The first version of this
    # line printed "clustering" for any z < 0, which would have called z=-0.33 / p=0.741 a finding.
    if p >= 0.05:
        verdict = 'NO CLUSTERING (p >= 0.05) -- losses are independent'
    else:
        verdict = 'FEWER runs than chance = clustering' if z < 0 else 'MORE runs than chance = alternation'
    print('  %s  n=%d  runs=%d (expected %.1f)  z=%+.2f  p=%.3f  %s'
          % (label, len(y), runs, mu, z, p, verdict))
    return z, p


def autocorr(x, label, lags=5):
    x = np.asarray(x, float)
    x = x - x.mean()
    d = float(np.dot(x, x))
    out = []
    for k in range(1, lags + 1):
        out.append(float(np.dot(x[:-k], x[k:]) / d) if d > 0 else 0.0)
    se = 1.0 / np.sqrt(len(x))
    print('  %-26s lag1..%d: %s   (2se = %.3f)'
          % (label, lags, ' '.join('%+.3f' % v for v in out), 2 * se))
    return out, se


# ---------------- (2) pause simulation ----------------
def run_pause(rows, mode, L=None, M=None, X=None):
    """Causal: a pause can only use results SETTLED strictly before the fire time."""
    kept, settled = [], []      # settled: (settle_ts, won, pnl)
    si = 0
    streak, streak_end = 0, None
    for r in rows:
        while si < len(rows) and rows[si]['settle'] <= r['ts']:
            s = rows[si]
            settled.append((s['settle'], s['won'], s['pnl']))
            if not s['won']:
                streak += 1
                streak_end = s['settle']
            else:
                streak, streak_end = 0, None
            si += 1
        skip = False
        if mode == 'runs':
            if streak >= L and streak_end is not None and (r['ts'] - streak_end) <= M * 60:
                skip = True
        elif mode == 'trail':
            last = settled[-10:]
            if len(last) == 10 and sum(p for _, _, p in last) < -X:
                skip = True
        if not skip:
            kept.append(r)
    return kept


def null_removal(rows, k, seed=0):
    """Remove k fires at random, SHUFFLES times. Returns mean/p95 of dd and mean per$1/total."""
    rng = np.random.default_rng(seed)
    n = len(rows)
    dds, tots, pers = [], [], []
    idx = np.arange(n)
    for _ in range(SHUFFLES):
        drop = set(rng.choice(idx, size=min(k, n), replace=False).tolist())
        g = [r for i, r in enumerate(rows) if i not in drop]
        s = stat(g)
        dds.append(s['dd']); tots.append(s['total']); pers.append(s['per1'])
    return (float(np.mean(dds)), float(np.percentile(dds, 95)),
            float(np.mean(tots)), float(np.mean(pers)))


def terciles(rows, key):
    v = np.array([r[key] for r in rows], float)
    return float(np.percentile(v, 33)), float(np.percentile(v, 67))


def main():
    R = load()
    a, b = calibrate(R)
    CAL = [r for r in R if r['ask'] <= MAX_ASK and r['p_cal'] >= r['ask'] + MARGIN + FEE]
    print('EF DRAWDOWN -- pause rules vs random removal')
    print('  %d venue-graded v10 EF fires, %s -> %s, stake $%.0f'
          % (len(R), dt.datetime.utcfromtimestamp(R[0]['ep']),
             dt.datetime.utcfromtimestamp(R[-1]['ep']), STAKE))
    print('  pooled Platt a=%.4f b=%+.4f -> calibrated subset n=%d' % (a, b, len(CAL)))
    for lab, g in (('RAW 1108', R), ('CALIBRATED', CAL)):
        s = stat(g)
        print('  %-12s n=%-5d W=%.1f%%  per$1 %+.4f  total $%+.2f  maxDD $%.2f  longest loss run %d'
              % (lab, s['n'], 100 * s['w'], s['per1'], s['total'], s['dd'], s['run']))

    print('\n(1) DO EF LOSSES CLUSTER?  -- this decides whether any pause rule can work')
    for lab, g in (('RAW 1108  ', R), ('CALIBRATED', CAL)):
        clustering(g, lab)
    for lab, g in (('RAW 1108', R), ('CALIBRATED', CAL)):
        autocorr([1 if r['won'] else 0 for r in g], '%s win/loss' % lab)
        autocorr([(1 if r['won'] else 0) - r['p_cal'] for r in g], '%s residual (win-p_cal)' % lab)

    print('\n(2) PAUSE GRID -- every cell, vs NULL = random removal of the SAME number of fires')
    for base_lab, base in (('RAW', R), ('CALIBRATED', CAL)):
        print('\n  --- %s (n=%d, per$1 %+.4f, total $%+.2f, maxDD $%.2f) ---'
              % (base_lab, len(base), stat(base)['per1'], stat(base)['total'], stat(base)['dd']))
        print('  %-22s %5s %6s %9s %10s %9s %5s %10s %10s'
              % ('cell', 'n', 'W%', 'per$1', 'total$', 'maxDD$', 'run', 'null DD mean', 'null p95'))
        for L in LS:
            for M in MS:
                g = run_pause(base, 'runs', L=L, M=M)
                s = stat(g)
                nm, n95, nt, npr = null_removal(base, len(base) - len(g))
                print('  %-22s %5d %5.1f%% %+9.4f %+10.2f %9.2f %5d %10.2f %10.2f%s'
                      % ('L=%d pause %dm' % (L, M), s['n'], 100 * s['w'], s['per1'], s['total'],
                         s['dd'], s['run'], nm, n95,
                         '' if s['n'] >= MIN_CELL else '  INSUFFICIENT'))
        for X in XS:
            g = run_pause(base, 'trail', X=X)
            s = stat(g)
            nm, n95, nt, npr = null_removal(base, len(base) - len(g))
            print('  %-22s %5d %5.1f%% %+9.4f %+10.2f %9.2f %5d %10.2f %10.2f%s'
                  % ('trail10 < -%d stk' % X, s['n'], 100 * s['w'], s['per1'], s['total'],
                     s['dd'], s['run'], nm, n95,
                     '' if s['n'] >= MIN_CELL else '  INSUFFICIENT'))

    print('\n(3) MARKET-WRONG BUCKETS -- per$1 and maxDD, raw and calibrated')
    for key, lab in (('rv60', 'realised vol'), ('body', '|body| bps')):
        lo, hi = terciles(R, key)
        print('  %s terciles at %.4f / %.4f' % (lab, lo, hi))
        for bl, f in (('LO', lambda r: r[key] < lo), ('MID', lambda r: lo <= r[key] < hi),
                      ('HI', lambda r: r[key] >= hi)):
            sr, sc = stat([r for r in R if f(r)]), stat([r for r in CAL if f(r)])
            print('    %-4s raw n=%-4d per$1 %+7.4f DD %6.2f | cal n=%-4d per$1 %+7.4f DD %6.2f%s'
                  % (bl, sr['n'], sr['per1'], sr['dd'], sc['n'], sc['per1'], sc['dd'],
                     '' if sc['n'] >= MIN_CELL else '  cal INSUFFICIENT'))
    print('  hour-of-day blocks')
    for b0, b1 in ((0, 6), (6, 12), (12, 18), (18, 24)):
        f = lambda r: b0 <= r['hour'] < b1
        sr, sc = stat([r for r in R if f(r)]), stat([r for r in CAL if f(r)])
        print('    %02d-%02d raw n=%-4d per$1 %+7.4f DD %6.2f | cal n=%-4d per$1 %+7.4f DD %6.2f%s'
              % (b0, b1, sr['n'], sr['per1'], sr['dd'], sc['n'], sc['per1'], sc['dd'],
                 '' if sc['n'] >= MIN_CELL else '  cal INSUFFICIENT'))
    print('  EF ask buckets')
    for lo, hi in ((0.0, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 1.01)):
        f = lambda r: lo <= r['ask'] < hi
        sr, sc = stat([r for r in R if f(r)]), stat([r for r in CAL if f(r)])
        print('    %.2f-%.2f raw n=%-4d per$1 %+7.4f DD %6.2f | cal n=%-4d per$1 %+7.4f DD %6.2f%s'
              % (lo, hi, sr['n'], sr['per1'], sr['dd'], sc['n'], sc['per1'], sc['dd'],
                 '' if sc['n'] >= MIN_CELL else '  cal INSUFFICIENT'))
    print('  phase (sec into candle) buckets')
    for lo, hi in ((0, 30), (30, 60), (60, 120), (120, 300)):
        f = lambda r: lo <= r['sec'] < hi
        sr, sc = stat([r for r in R if f(r)]), stat([r for r in CAL if f(r)])
        print('    %3d-%3d raw n=%-4d per$1 %+7.4f DD %6.2f | cal n=%-4d per$1 %+7.4f DD %6.2f%s'
              % (lo, hi, sr['n'], sr['per1'], sr['dd'], sc['n'], sc['per1'], sc['dd'],
                 '' if sc['n'] >= MIN_CELL else '  cal INSUFFICIENT'))


def export(path):
    R = load()
    a, b = calibrate(R)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['ts', 'epoch', 'sec', 'side', 'ask', 'p', 'p_cal', 'actual', 'win', 'day',
                    'rv60', 'abs_move_bps', 'hour', 'pnl_per1_fee_adj'])
        for r in R:
            w.writerow([r['ts'], r['ep'], r['sec'], r['side'], '%.4f' % r['ask'], '%.6f' % r['p'],
                        '%.6f' % r['p_cal'], r['actual'], 1 if r['won'] else 0, r['day'],
                        '%.4f' % r['rv60'], '%.2f' % r['body'], r['hour'], '%.6f' % r['pnl']])
    print('wrote %s (%d fires, pooled Platt a=%.4f b=%+.4f)' % (path, len(R), a, b))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'export':
        export(sys.argv[2])
    else:
        main()


def part4():
    """(4) Is ANY pause cell monotone in its own sweep AND beating its null?"""
    R = load(); calibrate(R)
    CAL = [r for r in R if r['ask'] <= MAX_ASK and r['p_cal'] >= r['ask'] + MARGIN + FEE]
    base = stat(CAL)
    print('\n(4) THE ONE HONEST COMBINATION?')
    print('  calibrated baseline: n=%d per$1 %+.4f total $%+.2f maxDD $%.2f'
          % (base['n'], base['per1'], base['total'], base['dd']))

    print('\n  SWEEP SHAPE -- maxDD as each knob moves (non-monotone = noise)')
    for L in LS:
        dds = [stat(run_pause(CAL, 'runs', L=L, M=M))['dd'] for M in MS]
        d = np.diff(dds)
        mono = bool((d >= -1e-9).all() or (d <= 1e-9).all())
        print('    L=%d over M: %s   %s' % (L, ' '.join('%.2f' % v for v in dds),
                                            'monotone' if mono else 'NON-MONOTONE'))
    for M in MS:
        dds = [stat(run_pause(CAL, 'runs', L=L, M=M))['dd'] for L in LS]
        d = np.diff(dds)
        mono = bool((d >= -1e-9).all() or (d <= 1e-9).all())
        print('    M=%dm over L: %s   %s' % (M, ' '.join('%.2f' % v for v in dds),
                                             'monotone' if mono else 'NON-MONOTONE'))

    print('\n  HOW MANY FIRES DOES EACH CELL ACTUALLY REMOVE?  (this is the whole story)')
    print('    %-20s %8s %10s %10s' % ('cell', 'removed', 'maxDD$', 'dDD vs base'))
    for L in LS:
        for M in MS:
            g = run_pause(CAL, 'runs', L=L, M=M)
            s = stat(g)
            print('    %-20s %8d %10.2f %+10.2f'
                  % ('L=%d pause %dm' % (L, M), len(CAL) - len(g), s['dd'], s['dd'] - base['dd']))

    best = run_pause(CAL, 'runs', L=4, M=15)
    s = stat(best)
    print('\n  BEST-LOOKING CELL: L=4 pause 15m -> n=%d (removes %d fires), DD $%.2f vs $%.2f'
          % (s['n'], len(CAL) - len(best), s['dd'], base['dd']))
    print('    day-by-day per$1:')
    for d in sorted({r['day'] for r in CAL}):
        g = [r for r in best if r['day'] == d]
        t = stat(g)
        print('      %-7s n=%-4d per$1 %+8.4f  total $%+7.2f%s'
              % (d, t['n'], t['per1'], t['total'], '' if t['n'] >= MIN_CELL else '   INSUFFICIENT'))


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'part4':
    part4()
