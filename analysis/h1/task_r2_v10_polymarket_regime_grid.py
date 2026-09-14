"""Task R-2 (V, learner/REQUEST.md 09-14 00:5x) - the R-1 grid on the v10 Polymarket set, 777 graded.

Buckets unchanged from R-1 (V's). Measurement only. Grading on POLYMARKET's oracle - established by
the provenance table below, not assumed. PnL per $1 rebuilt from the venue's 7% fee model, checked
against the runner's own recorded pnl/stake (ask 0.510 win: recorded 0.8935, model 0.8935).
"""
import sqlite3, json, sys, datetime as dt, numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
DB = '%s/db/v10p.sqlite3' % SP
MIN_N, RATE = 60, 0.07
SPAN_CUTS = [31.4, 48.9, 76.4]
SPAN_NAME = ['Q1 calm', 'Q2', 'Q3', 'Q4 busiest']
BLOCKS = [(0, 8, '00-08'), (8, 16, '08-16'), (16, 24, '16-24')]


def oracles():
    bn = {}
    for f in ('build11', 'predict_pnl', 'twin_c_thr1'):
        for cid, o, cl in sqlite3.connect('%s/db/%s.sqlite3' % (SP, f)).execute(
                'select candle_id,open,close from candles'):
            if o:
                bn[cid // 1000] = 'UP' if cl >= o else 'DOWN'
    poly = {e: a for e, a in sqlite3.connect('%s/db/venues.sqlite3' % SP).execute(
        'select epoch,actual from outcome') if a}
    lane = {e: a for e, a in sqlite3.connect(DB).execute(
        'select candle_epoch,actual from trades where actual is not null')}
    return bn, poly, lane


def kline_features():
    d = np.load('%s/build/paths.npz' % SP)
    cid, p = d['cid'], d['paths'].astype(float)
    ep = cid // 1000
    crossed = np.array([bool((p[i] > p[i, 0]).any() and (p[i] < p[i, 0]).any()) for i in range(len(p))])
    return {int(ep[i]): (((p[i - 12:i].max() - p[i - 12:i].min()) / p[i - 12, 0] * 1e4),
                         int(crossed[i - 6:i].sum())) for i in range(12, len(ep))}


def load(act):
    kf = kline_features()
    rows, skipped = [], {'no oracle label': 0, 'no kline features': 0, 'no ask': 0}
    for ep, side, ask, sec, feat in sqlite3.connect(DB).execute(
            'select candle_epoch,side,ask,sec,feat from trades where win is not null order by candle_epoch'):
        if ask is None:
            skipped['no ask'] += 1; continue
        if ep not in act:
            skipped['no oracle label'] += 1; continue
        if ep not in kf:
            skipped['no kline features'] += 1; continue
        fb = json.loads(feat) if feat else {}
        au, ad = fb.get('_ask_up'), fb.get('_ask_dn')
        won = (act[ep] == side)
        t = dt.datetime.utcfromtimestamp(ep)
        span, flips = kf[ep]
        rows.append(dict(ep=ep, side=side, ask=ask, won=won,
                         pnl=((1 / ask) * (1 - RATE * (1 - ask)) - 1) if won else -1.0,
                         hour=t.hour, wknd=t.weekday() >= 5, day=t.strftime('%m-%d %a'),
                         span=span, flips=flips,
                         width=(au + ad - 1.0) if (au is not None and ad is not None) else None))
    return rows, skipped


def cell(tag, rows):
    n = len(rows)
    if n == 0:
        return '| %s | 0 | — | — | — | — |' % tag
    v = np.array([r['pnl'] for r in rows]); h = n // 2
    h1, h2 = v[:h].mean(), v[h:].mean()
    verdict = ('INSUFFICIENT (n<%d), not read' % MIN_N if n < MIN_N else
               'halves FAIL' if np.sign(h1) != np.sign(h2) else
               'halves pass, %s' % ('positive' if v.mean() > 0 else 'NEGATIVE'))
    return '| %s | %d | %+.3f | %.1f%% | %+.3f / %+.3f | %s |' % (
        tag, n, v.mean(), 100 * np.mean([r['won'] for r in rows]), h1, h2, verdict)


HEAD = '| cell | n | per $1 | hit | halves | verdict |\n|---|---|---|---|---|---|'


def main():
    bn, poly, lane = oracles()
    print('## provenance (run before any cell)')
    for a, b, na, nb in ((lane, poly, 'v10 trades.actual', 'venues.outcome (POLYMARKET)'),
                         (lane, bn, 'v10 trades.actual', 'candles.actual (BINANCE)')):
        ov = set(a) & set(b); d = sum(1 for e in ov if a[e] != b[e])
        print('  %-20s vs %-28s n=%4d  disagree %3d  %.1f%%' % (na, nb, len(ov), d, 100 * d / len(ov)))

    rows, skipped = load(poly)
    print('\nusable: %d   excluded: %s' % (len(rows), {k: v for k, v in skipped.items() if v}))
    v = np.array([r['pnl'] for r in rows]); h = len(v) // 2
    print('\n### pooled'); print(HEAD); print(cell('all', rows))

    print('\n### Q4 busiest (R-1 reported it first; now readable?)')
    print(HEAD); print(cell('Q4 busiest', [r for r in rows if r['span'] >= SPAN_CUTS[2]]))

    def grid(name, keyfn, order):
        print('\n### %s' % name); print(HEAD)
        for k in order:
            print(cell(str(k), [r for r in rows if keyfn(r) == k]))

    grid('trailing-12 SPAN quartile (31.4 / 48.9 / 76.4 bps)',
         lambda r: SPAN_NAME[sum(r['span'] >= c for c in SPAN_CUTS)], SPAN_NAME)
    grid('UTC 8-hour block', lambda r: next(n for a, b, n in BLOCKS if a <= r['hour'] < b),
         [n for _, _, n in BLOCKS])
    grid('weekday / weekend', lambda r: 'weekend' if r['wknd'] else 'weekday', ['weekday', 'weekend'])
    grid('the weekend, split by DAY (V asked for separate windows, not pooled)',
         lambda r: r['day'] if r['wknd'] else None, sorted({r['day'] for r in rows if r['wknd']}))
    grid('every UTC day, for the record', lambda r: r['day'], sorted({r['day'] for r in rows}))
    grid('flips of the open in the last 6 candles',
         lambda r: '0-1' if r['flips'] <= 1 else ('2-3' if r['flips'] <= 3 else '4+'),
         ['0-1', '2-3', '4+'])
    wid = [r['width'] for r in rows if r['width'] is not None]
    med = float(np.median(wid))
    print('\n### book width at the fire, cut at the median %.4f (stated, not tuned)' % med)
    print(HEAD)
    print(cell('tight', [r for r in rows if r['width'] is not None and r['width'] <= med]))
    print(cell('wide', [r for r in rows if r['width'] is not None and r['width'] > med]))

    F = Finding('Task R-2 - v10 Polymarket paper, pooled', per_fire=v.mean(), n=len(v))
    F.grading(polymarket_venues_outcome=poly, v10_recorded_actual=lane)
    F.sample({'all graded': len(v)})
    F.halves(v[:h].mean(), v[h:].mean())
    print(); print('VERDICT', F.verdict())


if __name__ == '__main__':
    main()
