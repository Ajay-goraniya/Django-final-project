"""R-28 (V, 09-16 20:5x) -- does the adapt_ratio carry EF information?

12.16.0 ports build 11's fast/slow (180 s / 3600 s) vol ratio into the lanes. Before it touches EF,
this measures it on the same graded fires as R-27.

THE RATIO IS RECONSTRUCTED FROM THE ENGINE'S OWN CODE, not from a description of it:
`btc_model_v10_live.py` `_adapt_rms` / `_refresh_adapt_ratio` / `_engaged_adapt_ratio`, constants at
lines 875-889. Per-second buckets; r = log(c_t/c_{t-gap})/sqrt(gap); a gap over ADAPT_STALE_BUCKETS
breaks the chain and forces ratio 1.0; robust RMS = sqrt(mean(winsorised^2)) with the winsor cap at
ADAPT_WINSOR_SIGMAS * 1.4826 * median|r|; fast needs 60 returns, slow 600, else the window is 0 and
the ratio is 1.0. raw = clamp(fast/slow, 0.30, 6.00).

BUCKETS FIRST, and they are V's, fixed before any number is read: raw < 0.85, 0.85-1.15, > 1.15.
Those cuts are not arbitrary -- they are ADAPT_IDENTITY_LO/HI, so the middle bucket is exactly where
the engine's engaged factor is 1.0 and the ratio does nothing. LOW/HIGH are where it would act.

Prices: scratchpad/build/paths.npz, 1 s Binance closes, concatenated into one absolute-second series.
Fires: the R-27 set (Polymarket lanes on venues.outcome; Predict.fun excluded, never pooled).
"""
import math, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8
import r12_train as T

SP = T.SP

FAST_SEC, SLOW_SEC = 180, 3600
MIN_FAST, MIN_SLOW = 60, 600
RATIO_LO, RATIO_HI = 0.30, 6.00
IDENT_LO, IDENT_HI = 0.85, 1.15
FULL_LO, FULL_HI = 0.67, 1.50
WINSOR = 5.0
STALE = 5
KS = [0.0, 0.5, 1.0, 2.0]


def clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def engaged(raw):
    """Verbatim port of _engaged_adapt_ratio."""
    raw = clamp(raw, RATIO_LO, RATIO_HI)
    if IDENT_LO <= raw <= IDENT_HI:
        return 1.0
    if raw > IDENT_HI:
        width = math.log(FULL_HI) - math.log(IDENT_HI)
        eng = clamp((math.log(raw) - math.log(IDENT_HI)) / width, 0.0, 1.0)
    else:
        width = math.log(IDENT_LO) - math.log(FULL_LO)
        eng = clamp((math.log(IDENT_LO) - math.log(raw)) / width, 0.0, 1.0)
    return math.exp(math.log(raw) * eng)


def second_series():
    """One absolute-second close series from the 5-minute path grid."""
    d = np.load(os.path.join(SP, 'build', 'paths.npz'))
    cid = (d['cid'] // 1000).astype(np.int64)
    p = d['paths'].astype(float)
    o = np.argsort(cid)
    cid, p = cid[o], p[o]
    t0, t1 = int(cid[0]), int(cid[-1]) + 300
    px = np.full(t1 - t0, np.nan)
    for i in range(len(cid)):
        s = int(cid[i]) - t0
        px[s:s + 300] = p[i]
    return t0, px


def returns_series(t0, px):
    """r_t = log(c_t / c_{t-1}); NaN where either end is missing (the chain break)."""
    r = np.full(len(px), np.nan)
    with np.errstate(invalid='ignore', divide='ignore'):
        r[1:] = np.log(px[1:] / px[:-1])
    r[~np.isfinite(r)] = np.nan
    return r


def robust_rms(vals, minimum):
    """Verbatim port of _adapt_rms's statistics on an already-windowed array."""
    v = vals[np.isfinite(vals)]
    if len(v) < minimum:
        return 0.0
    mag = np.sort(np.abs(v))
    if len(mag) < minimum:
        return 0.0
    med = float(mag[len(mag) // 2])
    if med <= 0.0:
        pos = mag[mag > 0.0]
        need = max(8, int(math.ceil(len(mag) * 0.10)))
        if len(pos) < need:
            return 0.0
        med = float(pos[len(pos) // 2])
    cap = WINSOR * 1.4826 * med
    cl = np.clip(v, -cap, cap)
    return float(math.sqrt(float(np.mean(cl * cl))))


def ratio_at(t0, r, ts):
    """raw and engaged ratio as the engine would hold them at absolute second `ts`."""
    i = int(ts) - t0
    if i - SLOW_SEC < 0 or i >= len(r):
        return None, None
    win = r[max(0, i - SLOW_SEC + 1):i + 1]
    # A stale gap longer than STALE seconds forces the identity, as the engine does.
    fin = np.isfinite(win)
    if fin.size and not fin[-1]:
        return None, None
    runs = 0
    for k in range(len(fin) - 1, -1, -1):
        if fin[k]:
            runs = 0
        else:
            runs += 1
            if runs > STALE:
                break
    fast = robust_rms(r[max(0, i - FAST_SEC + 1):i + 1], MIN_FAST)
    slow = robust_rms(win, MIN_SLOW)
    if fast <= 0.0 or slow <= 0.0:
        return 1.0, 1.0
    raw = clamp(fast / slow, RATIO_LO, RATIO_HI)
    return raw, engaged(raw)


def fires():
    """The R-27 fire set, plus rv60 and the raw ask pair needed to re-price a re-fire."""
    out = []
    for lane, tcol, acol, ecol in (('poly_pnl', 'ts_ms', 'ask', 'ev'),
                                   ('v12_poly_lane', 'signal_ms', 'quote_ask', 'signal_ev'),
                                   ('v12_poly_weekend', 'signal_ms', 'quote_ask', 'signal_ev')):
        f = os.path.join(SP, 'db', lane + '.sqlite3')
        if not os.path.exists(f):
            continue
        c = sqlite3.connect(f)
        for ep, ts, side, p, ask, ev, sec, rv60, win in c.execute(
                'select candle_epoch,%s,side,p,%s,%s,sec,rv60,win from trades where win is not null'
                % (tcol, acol, ecol)):
            if not ask or p is None:
                continue
            s = int(sec) if sec is not None else int(ts) // 1000 - int(ep)
            out.append(dict(ep=int(ep), side=side, p=float(p), ask=float(ask), sec=s,
                            rv60=float(rv60) if rv60 is not None else 0.0,
                            win=int(win), lane=lane))
    return out


def stat(rows):
    if not rows:
        return None
    v = np.array([R8.per1(r['ask'], r['win'] == 1) for r in rows])
    return len(rows), float(np.mean([r['win'] for r in rows])), float(v.mean()), float(v.sum())


def halves(rows):
    g = sorted(rows, key=lambda r: r['ep'])
    h = len(g) // 2
    a, b = stat(g[:h]), stat(g[h:])
    return a, b


def perm(rows, n=2000, seed=7):
    """Permute the PREDICTIONS (here: the bucket assignment), never the labels."""
    if not rows:
        return None
    rng = np.random.default_rng(seed)
    v = np.array([R8.per1(r['ask'], r['win'] == 1) for r in rows])
    obs = v.mean()
    pool = np.array(ALLPNL)
    hits = sum(1 for _ in range(n) if rng.choice(pool, len(v), replace=False).mean() >= obs)
    return (hits + 1) / (n + 1)


ALLPNL = []


def main():
    t0, px = second_series()
    r = returns_series(t0, px)
    F = fires()
    keep = []
    for f in F:
        raw, eng = ratio_at(t0, r, f['ep'] + f['sec'])
        if raw is None:
            continue
        f['raw'], f['eng'] = raw, eng
        keep.append(f)
    F = keep
    global ALLPNL
    ALLPNL = [R8.per1(x['ask'], x['win'] == 1) for x in F]

    print('R-28  does the adapt_ratio carry EF information?')
    print('  %d graded Polymarket fires with a reconstructable ratio (of %d)' % (len(F), len(fires())))
    q = np.percentile([f['raw'] for f in F], [5, 25, 50, 75, 95])
    print('  raw ratio distribution: p5 %.3f p25 %.3f med %.3f p75 %.3f p95 %.3f' % tuple(q))
    ident = sum(1 for f in F if f['eng'] == 1.0)
    print('  engaged factor is exactly 1.0 (ratio does nothing) on %d/%d = %.1f%% of fires'
          % (ident, len(F), 100.0 * ident / len(F)))

    def bucket(f):
        return 'LOW' if f['raw'] < IDENT_LO else ('MID' if f['raw'] <= IDENT_HI else 'HIGH')

    print('\n  BUCKETS FIXED FIRST (V): raw < 0.85 / 0.85-1.15 / > 1.15 = the identity band')
    print('  %-6s %6s %7s %9s %10s %9s %9s %8s' % (
        'bucket', 'n', 'W%', 'per $1', 'total', 'h1', 'h2', 'perm p'))
    for b in ('LOW', 'MID', 'HIGH'):
        g = [f for f in F if bucket(f) == b]
        s = stat(g)
        if not s:
            print('  %-6s  (empty)' % b)
            continue
        a, c = halves(g)
        flag = '' if s[0] >= MIN_CELL else '   INSUFFICIENT (<%d)' % MIN_CELL
        print('  %-6s %6d %6.1f%% %+9.3f %+10.2f %+9.3f %+9.3f %8.3f%s' % (
            b, s[0], 100 * s[1], s[2], s[3], a[2], c[2], perm(g), flag))

    print('\n  THE p-SCALING GRID: p\' = 0.5 + (p-0.5)/raw^k, refired through the real EV rule')
    print('  (`p` in trades is ALREADY the chosen-side probability -- verified: ev_of(p, ask) matches')
    print('   the stored ev to 4e-4, while flipping it for DOWN is off by a median of 0.048. The k=0')
    print('   row below is the identity and MUST reproduce the real fire count; that is the guard.)')
    print('  %-6s %6s %7s %9s %10s %9s %9s' % ('k', 'n', 'W%', 'per $1', 'total', 'h1', 'h2'))
    for k in KS:
        g = []
        for f in F:
            ps = 0.5 + (f['p'] - 0.5) / (f['raw'] ** k)
            if R8.ev_of(ps, f['ask']) >= R8.threshold(f['rv60']):
                g.append(f)
        s = stat(g)
        if not s:
            print('  %-6.1f  (no fires)' % k)
            continue
        a, c = halves(g)
        print('  %-6.1f %6d %6.1f%% %+9.3f %+10.2f %+9.3f %+9.3f%s' % (
            k, s[0], 100 * s[1], s[2], s[3], a[2], c[2],
            '' if s[0] >= MIN_CELL else '   INSUFFICIENT'))

    print('\n  THE SAME GRID INSIDE EACH BUCKET (whole grid, never the best cell)')
    print('  %-6s %-6s %6s %9s %9s %9s' % ('bucket', 'k', 'n', 'per $1', 'h1', 'h2'))
    for b in ('LOW', 'MID', 'HIGH'):
        for k in KS:
            g = []
            for f in F:
                if bucket(f) != b:
                    continue
                ps = 0.5 + (f['p'] - 0.5) / (f['raw'] ** k)
                if R8.ev_of(ps, f['ask']) >= R8.threshold(f['rv60']):
                    g.append(f)
            s = stat(g)
            if not s:
                print('  %-6s %-6.1f %6d      (no fires)' % (b, k, 0))
                continue
            a, c = halves(g)
            print('  %-6s %-6.1f %6d %+9.3f %+9.3f %+9.3f%s' % (
                b, k, s[0], s[2], a[2], c[2], '' if s[0] >= MIN_CELL else '  INSUFFICIENT'))


if __name__ == '__main__':
    main()


def null_grid():
    """THE DECISIVE NULL (R-19): every k>0 cell is a SUBSET of the k=0 fires, so it is a selection
    rule. R-19 established that any selection which raises per-$1 is usually just buying cheaper.
    So for each cell size n, compare the ratio's pick against the obvious dumb rule -- take the n
    fires with the highest stored EV, ratio ignored -- and against a random n. If the ratio carries
    information, it must beat the EV null at the same n. Totals are shown because per-$1 rises
    mechanically as n falls and money is what the owner is counting.
    """
    t0, px = second_series()
    r = returns_series(t0, px)
    F = []
    for f in fires():
        raw, eng = ratio_at(t0, r, f['ep'] + f['sec'])
        if raw is None:
            continue
        f['raw'], f['eng'] = raw, eng
        f['ev_s'] = R8.ev_of(f['p'], f['ask'])
        F.append(f)
    rng = np.random.default_rng(11)
    by_ev = sorted(F, key=lambda z: -z['ev_s'])
    print('\n  NULL TEST -- ratio pick vs "just take the top-n by EV", same n')
    print('  %-5s %6s %9s %10s %9s %10s %9s' % (
        'k', 'n', 'ratio/$1', 'ratio tot', 'topEV/$1', 'topEV tot', 'rand/$1'))
    for k in KS:
        g = [f for f in F
             if R8.ev_of(0.5 + (f['p'] - 0.5) / (f['raw'] ** k), f['ask']) >= R8.threshold(f['rv60'])]
        n = len(g)
        if not n:
            continue
        a = stat(g)
        b = stat(by_ev[:n])
        rr = np.mean([np.mean([R8.per1(x['ask'], x['win'] == 1)
                               for x in rng.choice(np.array(F, dtype=object), n, replace=False)])
                      for _ in range(200)])
        print('  %-5.1f %6d %+9.3f %+10.2f %+9.3f %+10.2f %+9.3f' % (
            k, n, a[2], a[3], b[2], b[3], rr))

    print('\n  THE SAME NULL ON THE HIGH BUCKET, where the ratio looks strongest')
    H = [f for f in F if f['raw'] > IDENT_HI]
    H_ev = sorted(H, key=lambda z: -z['ev_s'])
    print('  %-5s %6s %9s %10s %9s %10s' % ('k', 'n', 'ratio/$1', 'ratio tot', 'topEV/$1', 'topEV tot'))
    for k in KS:
        g = [f for f in H
             if R8.ev_of(0.5 + (f['p'] - 0.5) / (f['raw'] ** k), f['ask']) >= R8.threshold(f['rv60'])]
        n = len(g)
        if not n:
            continue
        a, b = stat(g), stat(H_ev[:n])
        print('  %-5.1f %6d %+9.3f %+10.2f %+9.3f %+10.2f%s' % (
            k, n, a[2], a[3], b[2], b[3], '' if n >= MIN_CELL else '  INSUFFICIENT'))
