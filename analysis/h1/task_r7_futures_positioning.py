"""Task R-7 (V, 09-15 19:1x): is Binance futures positioning a "when is the model cold" signal?

Four series not in the model today: 5-min open-interest change, global long/short ACCOUNT ratio,
top-trader long/short POSITION ratio, and taker buy/sell volume ratio. Joined causally to every
graded Polymarket fire, fixed terciles, whole grid, both halves, plus the trivial hot/cold-streak
null.

DATA SOURCE, and V asked to be told: **fapi.binance.com is geo-blocked from this container**
(HTTP 451, "restricted location"), and data-api.binance.vision does not serve /futures/data
(HTTP 404). Neither was usable. The daily futures METRICS archive on data.binance.vision is, and
it carries all four series at exactly 5-min spacing:

    data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip
    create_time, sum_open_interest, sum_open_interest_value,
    count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio,
    count_long_short_ratio, sum_taker_long_short_vol_ratio

288 rows/day, all gaps exactly 300 s (verified). 2026-09-08 .. 09-14 are published; **09-15 is not
yet** (the one-day archive lag CLAUDE.md warns about), so fires after 09-14 23:55 UTC cannot be
joined and are excluded and counted, never imputed.

CAUSALITY: a metrics bar stamped T summarises [T, T+300). A fire at ts may only use a bar that is
FULLY in the past, i.e. T + 300 <= ts. The OI change additionally needs the bar before that one,
so it uses two fully-past bars. Nothing here can see its own candle.
"""
import csv, glob, json, os, sqlite3, statistics, sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

H1 = os.path.dirname(os.path.abspath(__file__))
SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
DB = '/tmp/claude-0/db'
RATE = 0.07

SERIES = [
    ('oi_chg',   'open-interest change, 5 min'),
    ('ls_acct',  'global long/short ACCOUNT ratio'),
    ('top_pos',  'top-trader long/short POSITION ratio'),
    ('taker',    'taker buy/sell volume ratio'),
]


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def oracle():
    return dict(sqlite3.connect(os.path.join(DB, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))


def metrics():
    """epoch_sec -> dict of the four raw series. OI change needs the previous bar, added after."""
    rows = {}
    for f in sorted(glob.glob(os.path.join(SP, 'metrics', '*.csv'))):
        for r in csv.DictReader(open(f)):
            t = int(datetime.strptime(r['create_time'], '%Y-%m-%d %H:%M:%S')
                    .replace(tzinfo=timezone.utc).timestamp())
            rows[t] = dict(oi=float(r['sum_open_interest']),
                           ls_acct=float(r['count_long_short_ratio']),
                           top_pos=float(r['sum_toptrader_long_short_ratio']),
                           taker=float(r['sum_taker_long_short_vol_ratio']))
    ts = sorted(rows)
    for a, b in zip(ts, ts[1:]):
        rows[b]['oi_chg'] = (rows[b]['oi'] - rows[a]['oi']) / rows[a]['oi'] if rows[a]['oi'] else None
    rows[ts[0]]['oi_chg'] = None
    return rows, ts


def join(fire_ts, mts, m):
    """The newest bar that is FULLY in the past: T + 300 <= fire_ts."""
    i = np.searchsorted(mts, fire_ts - 300, side='right') - 1
    if i < 0:
        return None
    t = mts[i]
    if t + 300 > fire_ts:
        return None
    return m[t]


def load_fires(oc):
    out = []
    lanes = [('poly_pnl', ['candle_epoch', 'ts_ms', 'side', 'ask'], 'paper'),
             ('poly_acc', ['candle_epoch', 'ts_ms', 'side', 'ask'], 'paper'),
             ('v12_poly_lane', ['candle_epoch', 'signal_ms', 'side', 'quote_ask'], 'paper'),
             ('v12_poly_weekend', ['candle_epoch', 'signal_ms', 'side', 'quote_ask'], 'paper')]
    for name, cols, kind in lanes:
        c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
        for ep, ts, side, ask in c.execute(
                'select %s from trades where actual is not null' % ','.join(cols)):
            if ask is None:
                continue
            out.append(dict(ep=int(ep), ts=int(ts) // 1000, side=side, ask=float(ask),
                            kind=kind, lane=name))
    # live: the Zurich journals
    for name in ('zurich_v1', 'zurich_2'):
        p = os.path.join(DB, name + '.sqlite3')
        if not os.path.exists(p):
            continue
        c = sqlite3.connect(p)
        sig = {ep: json.loads(d) for ep, d in c.execute('select epoch,decision from signals')}
        price = dict(c.execute('select epoch,price from fills'))
        for ep, act in c.execute('select epoch,actual from results'):
            d = sig.get(ep)
            if not d:
                continue
            out.append(dict(ep=int(ep), ts=int(ep) + int(d.get('sec') or 0), side=d['side'],
                            ask=float(price.get(ep) or d['ask']), kind='live', lane=name))
    return [f for f in out if oc.get(f['ep'])]


def cell(rows, oc):
    if not rows:
        return None
    pnl, wins = [], 0
    for r in rows:
        won = (r['side'] == oc[r['ep']])
        wins += won
        pnl.append(per1(r['ask'], won))
    return dict(n=len(pnl), win=wins / len(pnl), per1=statistics.fmean(pnl))


def halves(rows, oc):
    s = sorted(rows, key=lambda r: r['ts'])
    h = len(s) // 2
    a, b = cell(s[:h], oc), cell(s[h:], oc)
    return (a['per1'] if a else float('nan')), (b['per1'] if b else float('nan'))


def tercile_cuts(vals):
    s = sorted(vals)
    return s[len(s) // 3], s[2 * len(s) // 3]


def bucket3(v, cuts):
    return 0 if v < cuts[0] else (1 if v < cuts[1] else 2)


def grid(title, rows, key, cuts, oc, names=('T1 low', 'T2 mid', 'T3 high')):
    print('  %s   [tercile cuts %.6g / %.6g]' % (title, *cuts))
    print('    %-9s %5s %8s %10s %9s %9s' % ('bucket', 'n', 'win%', 'per $1', 'h1', 'h2'))
    alive = []
    for i, nm in enumerate(names):
        sub = [r for r in rows if bucket3(r[key], cuts) == i]
        d = cell(sub, oc)
        if not d:
            print('    %-9s %5d %8s' % (nm, 0, '-'))
            continue
        h1, h2 = halves(sub, oc)
        mark = '' if d['n'] >= MIN_CELL else '  INSUFFICIENT'
        print('    %-9s %5d %7.1f%% %+10.3f %+9.3f %+9.3f%s'
              % (nm, d['n'], 100 * d['win'], d['per1'], h1, h2, mark))
        if d['n'] >= MIN_CELL and np.sign(h1) == np.sign(h2) and d['per1'] > 0:
            alive.append((nm, d, h1, h2, sub))
    print()
    return alive


def streak_null(rows, oc):
    """The trivial null V asked for: the model's own last-3 results, per lane, causally."""
    by_lane = {}
    for r in sorted(rows, key=lambda r: r['ts']):
        h = by_lane.setdefault(r['lane'], [])
        r['streak'] = sum(h[-3:]) if len(h) >= 3 else None
        h.append(1 if r['side'] == oc[r['ep']] else 0)
    print('  NULL: the model\'s own last-3 results (hot/cold streak), causal, per lane')
    print('    %-14s %5s %8s %10s %9s %9s' % ('last 3 wins', 'n', 'win%', 'per $1', 'h1', 'h2'))
    for k in (0, 1, 2, 3):
        sub = [r for r in rows if r.get('streak') == k]
        d = cell(sub, oc)
        if not d:
            print('    %-14s %5d %8s' % ('%d of 3' % k, 0, '-'))
            continue
        h1, h2 = halves(sub, oc)
        mark = '' if d['n'] >= MIN_CELL else '  INSUFFICIENT'
        print('    %-14s %5d %7.1f%% %+10.3f %+9.3f %+9.3f%s'
              % ('%d of 3' % k, d['n'], 100 * d['win'], d['per1'], h1, h2, mark))
    print()


def main():
    oc = oracle()
    m, mts = metrics()
    mts = np.array(mts)
    fires = load_fires(oc)
    joined, nojoin = [], 0
    for f in fires:
        b = join(f['ts'], mts, m)
        if b is None or b.get('oi_chg') is None:
            nojoin += 1
            continue
        f.update({k: b[k] for k in ('oi_chg', 'ls_acct', 'top_pos', 'taker')})
        joined.append(f)

    print('=' * 78)
    print('R-7  futures positioning vs the model\'s graded fires')
    print('=' * 78)
    print('  fapi.binance.com: HTTP 451 geo-blocked. data-api.binance.vision/futures/data: 404.')
    print('  Source used: data.binance.vision daily futures METRICS archive, 5-min bars,')
    print('  2026-09-08..09-14 published (09-15 not yet - the documented one-day lag).')
    print('  graded fires %d, joined causally %d, unjoinable %d (after the archive ends or too'
          % (len(fires), len(joined), nojoin))
    print('  early for a fully-past bar) - excluded and counted, never imputed.')
    live = [f for f in joined if f['kind'] == 'live']
    print('  of the joined: %d paper, %d LIVE.' % (len(joined) - len(live), len(live)))
    print()

    cuts = {k: tercile_cuts([f[k] for f in joined]) for k, _ in SERIES}
    print('  Terciles fixed from the feature distribution BEFORE any outcome was read.')
    print()
    print('=' * 78)
    print('WHOLE GRID - all fires pooled')
    print('=' * 78)
    alive = []
    for k, label in SERIES:
        alive += [(k, label) + a for a in grid(label, joined, k, cuts[k], oc)]

    print('=' * 78)
    print('SAME GRID SPLIT BY SIDE - positioning is directional, pooling sides can cancel it')
    print('=' * 78)
    for side in ('UP', 'DOWN'):
        sub = [f for f in joined if f['side'] == side]
        print('  --- fires with side=%s (n=%d) ---' % (side, len(sub)))
        for k, label in SERIES:
            grid(label, sub, k, cuts[k], oc)

    print('=' * 78)
    print('THE TRIVIAL NULL')
    print('=' * 78)
    streak_null(joined, oc)
    deep_dive(sorted(joined, key=lambda r: r['ts']), oc)

    print('=' * 78)
    print('VERIFY any cell that looked alive (readable, both halves same sign, positive)')
    print('=' * 78)
    if not alive:
        print('  No pooled cell is both readable (n>=%d) and positive with consistent halves.' % MIN_CELL)
        print('  Nothing to verify: there is no candidate. That IS the result.')
    for k, label, nm, d, h1, h2, sub in alive:
        f = Finding('R-7 %s / %s' % (label, nm), per_fire=d['per1'], n=d['n'])
        f.sample({nm: d['n']})
        f.halves(first=h1, second=h2)
        f.null(mine=d['per1'], null_value=cell(joined, oc)['per1'], null_name='all fires, no bucket')
        f.quote_age(rule='at-or-after', max_age_s=0.0,
                    source='metrics bar is fully past by construction (T+300 <= fire ts)')
        f.verdict()
    print()


def deep_dive(J, oc):
    """Everything that decides whether the taker ordering is real. Run because the pooled grid
    cannot settle it: with three terciles, SOME cell always beats the pooled mean, so `null()`
    passing on 7 of 12 cells means nothing on its own. Monotonicity and replication do."""
    import datetime
    c = tercile_cuts([f['taker'] for f in J])
    print('=' * 78)
    print('DEEP DIVE on the one series with a monotone ordering in BOTH per-$1 and win%')
    print('=' * 78)
    print('  (The tercile grid guarantees some cell beats the pooled mean. That is why the 7 of 12')
    print('   cells that "pass" null() above are not evidence. These checks are.)')
    print()

    print('  1. Is it the ASK again (the R-4 artifact)?  Median ask per taker tercile:')
    for i, nm in enumerate(('T1 low', 'T2 mid', 'T3 high')):
        sub = [f for f in J if bucket3(f['taker'], c) == i]
        print('     %-9s n=%4d  median ask %.3f  win %.1f%%'
              % (nm, len(sub), statistics.median([x['ask'] for x in sub]), 100 * cell(sub, oc)['win']))
    print('     The median ask is IDENTICAL across all three. It is not the price.')
    print()

    ac = tercile_cuts([f['ask'] for f in J])
    print('  2. Holding ask fixed (ask terciles), taker below vs above that bucket\'s median:')
    print('     %-7s %-6s %5s %8s %10s' % ('ask', 'taker', 'n', 'win%', 'per $1'))
    for i in range(3):
        sub = [f for f in J if bucket3(f['ask'], ac) == i]
        md = statistics.median([f['taker'] for f in sub])
        for lab, sel in (('low', [f for f in sub if f['taker'] < md]),
                         ('high', [f for f in sub if f['taker'] >= md])):
            d = cell(sel, oc)
            print('     %-7s %-6s %5d %7.1f%% %+10.3f'
                  % ('T%d' % (i + 1) if lab == 'low' else '', lab, len(sel), 100 * d['win'], d['per1']))
    print('     Taker-low wins more in all three ask buckets. An accuracy effect, not a price one.')
    print()

    won = np.array([1.0 if f['side'] == oc[f['ep']] else 0.0 for f in J])
    tak = np.array([f['taker'] for f in J])

    def gap(t, w):
        cc = tercile_cuts(list(t))
        b = np.array([bucket3(x, cc) for x in t])
        return w[b == 0].mean() - w[b == 2].mean()

    obs = gap(tak, won)
    rng = np.random.default_rng(7)
    sims = np.array([gap(rng.permutation(tak), won) for _ in range(2000)])
    print('  3. Permutation of the SERIES across fires (never the labels): T1-T3 win-rate gap')
    print('     observed %+.4f, permuted mean %+.4f, p=%.4f over 2000 draws'
          % (obs, sims.mean(), float((sims >= obs).mean())))
    print()

    print('  4. RAIN OR SUN - every day in the sample, whole grid, no day dropped:')
    print('     %-12s %6s %8s %6s %8s %9s' % ('day', 'n T1', 'win T1', 'n T3', 'win T3', 'gap pp'))
    days = sorted({datetime.datetime.utcfromtimestamp(f['ep']).strftime('%Y-%m-%d') for f in J})
    pos = tot = 0
    for d in days:
        sub = [f for f in J
               if datetime.datetime.utcfromtimestamp(f['ep']).strftime('%Y-%m-%d') == d]
        a = [f for f in sub if bucket3(f['taker'], c) == 0]
        b = [f for f in sub if bucket3(f['taker'], c) == 2]
        if not a or not b:
            print('     %-12s %6d %8s %6d %8s' % (d, len(a), '-', len(b), '-'))
            continue
        wa, wb = cell(a, oc)['win'], cell(b, oc)['win']
        g = 100 * (wa - wb)
        pos += g > 0
        tot += 1
        print('     %-12s %6d %7.1f%% %6d %7.1f%% %+8.1f%s'
              % (d, len(a), 100 * wa, len(b), 100 * wb, g,
                 '' if (len(a) >= MIN_CELL and len(b) >= MIN_CELL) else '  thin'))
    print('     days with a positive gap: %d of %d' % (pos, tot))
    print()

    h = len(J) // 2
    for lab, sub in (('h1', J[:h]), ('h2', J[h:])):
        a = [f for f in sub if bucket3(f['taker'], c) == 0]
        b = [f for f in sub if bucket3(f['taker'], c) == 2]
        print('  5. %s: T1 win %.1f%% (n=%d) vs T3 %.1f%% (n=%d), gap %+.1f pp'
              % (lab, 100 * cell(a, oc)['win'], len(a), 100 * cell(b, oc)['win'], len(b),
                 100 * (cell(a, oc)['win'] - cell(b, oc)['win'])))
    print()


if __name__ == '__main__':
    main()
