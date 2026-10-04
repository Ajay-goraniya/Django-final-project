"""R-30 -- BTC-side market state at the candle OPEN -> can EF be switched off in a bad state?

Owner: "if we can identify this Monday and Tuesday and stop... it would have ended up in same profit."

This is the rain-or-sun path and it is allowed only that way. Every feature and every bucket cut is
fixed before a single PnL number is read; every bucket is reported; the switch is walk-forward with
its threshold frozen on the early days and applied to the later ones; and the losing-day check in
step 3 is deliberately last, because choosing a state by looking at the two bad days first is the
exact fit this task is most at risk of.

STATE IS MEASURED FROM BTC ONLY, STRICTLY BEFORE THE CANDLE OPENS. No venue price, no book, no
feature from the fire second -- a switch that needs the fire second is not a switch, it is a filter.
"""
import datetime as dt, math, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import task_r8_taker_feature as R8
import r12_train as T
import r28_adapt_ef as A

SP = T.SP
D24, D1, D6 = 288, 12, 72          # 5-minute candles in 24 h, 1 h, 6 h


def grid():
    """5-minute OHLC from the 1 s path grid, indexed by candle epoch."""
    d = np.load(os.path.join(SP, 'build', 'paths.npz'))
    cid = (d['cid'] // 1000).astype(np.int64)
    p = d['paths'].astype(float)
    o = np.argsort(cid)
    cid, p = cid[o], p[o]
    return cid, p[:, 0], p[:, 299], p.max(axis=1), p.min(axis=1), {int(c): i for i, c in enumerate(cid)}


def state_features():
    """Seven BTC-only state readings per candle, all from candles strictly BEFORE it."""
    cid, op, cl, hi, lo, idx = grid()
    ret = np.zeros(len(cl))
    ret[1:] = cl[1:] / cl[:-1] - 1.0
    out = {}
    for i in range(D24 + 1, len(cid)):
        # contiguity: the 24 h window must actually be 288 consecutive candles
        if cid[i] - cid[i - D24] != D24 * 300:
            continue
        w = slice(i - D24, i)
        r24, r6, r1 = ret[w], ret[i - D6:i], ret[i - D1:i]
        sd24, sd1 = float(r24.std()), float(r1.std())
        h24, l24 = float(hi[w].max()), float(lo[w].min())
        atr = float(np.mean(hi[w] - lo[w]))
        a = float(np.corrcoef(r6[:-1], r6[1:])[0, 1]) if r6[:-1].std() > 0 and r6[1:].std() > 0 else 0.0
        up = float(np.mean(cl[i - D1:i] > op[i - D1:i]))
        out[int(cid[i])] = dict(
            ret24=float(cl[i - 1] / cl[i - D24 - 1] - 1.0) * 100.0,
            rv24=sd24 * 1e4,
            volratio=(sd1 / sd24) if sd24 > 0 else 1.0,
            rangeatr=((h24 - l24) / atr) if atr > 0 else 0.0,
            autocorr=a if math.isfinite(a) else 0.0,
            samedir=max(up, 1.0 - up),
            posrange=((float(cl[i - 1]) - l24) / (h24 - l24)) if h24 > l24 else 0.5,
        )
    return out


FEATS = ['ret24', 'rv24', 'volratio', 'rangeatr', 'autocorr', 'samedir', 'posrange']


def fires():
    out = []
    for lane, tcol, acol in (('poly_pnl', 'ts_ms', 'ask'),
                             ('v12_poly_lane', 'signal_ms', 'quote_ask'),
                             ('v12_poly_weekend', 'signal_ms', 'quote_ask')):
        f = os.path.join(SP, 'db', lane + '.sqlite3')
        if not os.path.exists(f):
            continue
        for ep, ts, p, ask, sec, win in sqlite3.connect(f).execute(
                'select candle_epoch,%s,p,%s,sec,win from trades where win is not null' % (tcol, acol)):
            if not ask or p is None:
                continue
            out.append(dict(ep=int(ep), p=float(p), ask=float(ask), win=int(win),
                            sec=int(sec) if sec is not None else int(ts) // 1000 - int(ep),
                            day=dt.datetime.utcfromtimestamp(int(ep)).strftime('%m-%d'), lane=lane))
    return out


def cell(rows):
    if not rows:
        return None
    v = np.array([R8.per1(r['ask'], r['win'] == 1) for r in rows])
    return len(rows), float(np.mean([r['win'] for r in rows])), float(v.mean()), float(v.sum())


def halves(rows):
    g = sorted(rows, key=lambda r: r['ep'])
    h = len(g) // 2
    return cell(g[:h]), cell(g[h:])


def perm(rows, pool, n=2000, seed=5):
    if not rows:
        return None
    rng = np.random.default_rng(seed)
    obs = np.mean([R8.per1(r['ask'], r['win'] == 1) for r in rows])
    k = len(rows)
    hits = sum(1 for _ in range(n) if rng.choice(pool, k, replace=False).mean() >= obs)
    return (hits + 1) / (n + 1)


def main():
    S = state_features()
    F = [f for f in fires() if f['ep'] in S]
    for f in F:
        f.update(S[f['ep']])
    pool = np.array([R8.per1(f['ask'], f['win'] == 1) for f in F])

    print('R-30  BTC-side market state at the candle open -> can EF be switched off?')
    print('  %d graded Polymarket fires with a full 24 h of prior BTC candles' % len(F))

    print('\n  STEP 0 -- THE DAILY TABLE (this comes first, before any bucket)')
    print('  %-7s %6s %7s %8s %9s %10s' % ('day', 'n', 'W%', 'avg ask', 'per $1', 'total'))
    days = sorted({f['day'] for f in F})
    for d in days:
        g = [f for f in F if f['day'] == d]
        s = cell(g)
        print('  %-7s %6d %6.1f%% %8.3f %+9.3f %+10.2f' % (
            d, s[0], 100 * s[1], np.mean([x['ask'] for x in g]), s[2], s[3]))
    s = cell(F)
    print('  %-7s %6d %6.1f%% %8.3f %+9.3f %+10.2f' % (
        'ALL', s[0], 100 * s[1], np.mean([x['ask'] for x in F]), s[2], s[3]))

    zf = os.path.join(SP, 'db', 'zurich_2.sqlite3')
    if os.path.exists(zf):
        print('\n  Zurich live per day (its own results table, live money)')
        z = {}
        for ep, pnl in sqlite3.connect(zf).execute(
                'select epoch,pnl from results where pnl is not null'):
            k = dt.datetime.utcfromtimestamp(ep).strftime('%m-%d')
            a = z.setdefault(k, [0, 0.0, 0])
            a[0] += 1; a[1] += pnl; a[2] += (1 if pnl > 0 else 0)
        for k in sorted(z):
            print('  %-7s n=%-4d total %+8.2f  W=%.1f%%' % (k, z[k][0], z[k][1], 100 * z[k][2] / z[k][0]))

    print('\n  STEP 1 -- EVERY FEATURE, EVERY BUCKET. Terciles fixed on the full sample.')
    print('  %-9s %-5s %8s %6s %9s %10s %9s %9s %8s' % (
        'feature', 'bkt', 'range', 'n', 'per $1', 'total', 'h1', 'h2', 'perm p'))
    cuts, buckets = {}, {}
    for k in FEATS:
        v = np.array([f[k] for f in F])
        lo, hi = np.percentile(v, 33), np.percentile(v, 67)
        cuts[k] = (lo, hi)
        for f in F:
            f[k + '_b'] = 'LO' if f[k] < lo else ('MID' if f[k] < hi else 'HI')
        for b in ('LO', 'MID', 'HI'):
            g = [f for f in F if f[k + '_b'] == b]
            s = cell(g)
            if not s:
                continue
            a, c = halves(g)
            rng = ('<%.3f' % lo) if b == 'LO' else (('%.3f-%.3f' % (lo, hi)) if b == 'MID' else '>%.3f' % hi)
            neg = a[2] < 0 and c[2] < 0 and s[0] >= MIN_CELL
            buckets[(k, b)] = (s, a, c, neg)
            print('  %-9s %-5s %8s %6d %+9.3f %+10.2f %+9.3f %+9.3f %8.3f%s' % (
                k, b, rng, s[0], s[2], s[3], a[2], c[2], perm(g, pool),
                '   <-- NEGATIVE IN BOTH HALVES' if neg else
                ('   insufficient' if s[0] < MIN_CELL else '')))

    bad = [(k, b) for (k, b), (s, a, c, neg) in buckets.items() if neg]
    print('\n  STEP 2 -- THE SWITCH')
    if not bad:
        print('  NO BUCKET is negative in both halves at n>=60. There is nothing to switch off.')
        print('  Every one of the %d buckets tested is either positive in at least one half or too' % len(buckets))
        print('  small to read. A switch built on any of them would be fitted to a single half.')
    else:
        print('  candidates negative in both halves: %s' % ', '.join('%s.%s' % x for x in bad))
        cal, app = days[:3], days[3:]
        print('  walk-forward: state cuts and the choice of bucket are FROZEN on %s, applied to %s'
              % (','.join(cal), ','.join(app)))
        print('  %-14s %6s %9s %10s %12s' % ('switch', 'n', 'per $1', 'total', 'vs always-on'))
        base = [f for f in F if f['day'] in app]
        bs = cell(base)
        print('  %-14s %6d %+9.3f %+10.2f %12s' % ('always on', bs[0], bs[2], bs[3], '--'))
        for k, b in bad:
            keep = [f for f in base if f[k + '_b'] != b]
            s = cell(keep)
            if not s:
                continue
            print('  %-14s %6d %+9.3f %+10.2f %+12.2f' % (
                'off %s.%s' % (k, b), s[0], s[2], s[3], s[3] - bs[3]))
            nul = sorted(base, key=lambda z: -R8.ev_of(z['p'], z['ask']))[:s[0]]
            ns = cell(nul)
            print('  %-14s %6d %+9.3f %+10.2f %+12.2f' % (
                '  topEV null', ns[0], ns[2], ns[3], ns[3] - bs[3]))

    print('\n  STEP 3 -- WHAT THE SWITCH WOULD HAVE DONE ON THE LOSING DAYS (last, on purpose)')
    losers = [d for d in days if cell([f for f in F if f['day'] == d])[3] < 0]
    print('  losing days: %s' % (', '.join(losers) if losers else 'none'))
    if bad:
        for k, b in bad:
            for d in days:
                g = [f for f in F if f['day'] == d]
                off = [f for f in g if f[k + '_b'] == b]
                s, so = cell(g), cell(off)
                print('  %s.%s  %s: %d of %d fires suppressed, %+.2f of %+.2f total removed'
                      % (k, b, d, so[0] if so else 0, s[0], so[3] if so else 0.0, s[3]))
    else:
        print('  Not applicable: step 2 found no bucket to switch off.')
        print('  For the record, the losing days\' state readings vs the winning days:')
        print('  %-7s %9s %9s %9s %9s %9s %9s %9s' % tuple(['day'] + FEATS))
        for d in days:
            g = [f for f in F if f['day'] == d]
            print('  %-7s %9.3f %9.3f %9.3f %9.3f %9.3f %9.3f %9.3f' % tuple(
                [d] + [float(np.median([x[k] for x in g])) for k in FEATS]))


if __name__ == '__main__':
    main()
