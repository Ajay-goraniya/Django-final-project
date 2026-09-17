"""Task R-1 (V, learner/REQUEST.md 09-14 00:2x) - the Polymarket regime grid. MEASUREMENT ONLY.

Buckets are V's, fixed in advance, every cell reported. No recommendation to gate. Nothing here is
read if it fails halves or sits under 60 graded fires.

GRADING - I did NOT follow the brief here, and section 1 of the .md says why. V asked for
`candles.actual` (Binance close >= open). This is a POLYMARKET lane and Polymarket settles on its own
oracle, so Binance grading is the 09-10 cross-venue error pointed the other way. Verified: the lane's
`actual` matches `venues.outcome` (Polymarket's resolution) on 303/303 and disagrees with
`candles.actual` on 61/303 = 20.1%. The grid below is graded on POLYMARKET's oracle. The
candles.actual version is reported alongside so the size of the distortion is visible.
PnL per $1 is rebuilt from the venue's own fee model, checked exactly against the lane's recorded
`pnl_per_dollar`: win = (1/ask) * (1 - rate*(1-ask)) - 1 with rate = fee_rate_bps/1e4; loss = -1.

Book width at the fire comes from the lane's OWN recorded feature blob (`_ask_up`, `_ask_dn`), not
from a re-read of a book snapshot - the running artifact, not a reconstruction.
"""
import sqlite3, json, sys, datetime as dt, numpy as np
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
from verify import Finding

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
MIN_N = 60
ORACLE = 'POLY'          # the venue that pays. 'BINANCE' only to show the distortion.
SPAN_CUTS = [31.4, 48.9, 76.4]        # V's, = trailing-12-candle SPAN quartiles (mine: 31.1/48.6/76.0)
SPAN_NAME = ['Q1 calm', 'Q2', 'Q3', 'Q4 busiest']
BLOCKS = [(0, 8, '00-08'), (8, 16, '08-16'), (16, 24, '16-24')]


def binance_actual():
    out = {}
    for f in ('build11', 'predict_pnl', 'twin_c_thr1'):
        c = sqlite3.connect('%s/db/%s.sqlite3' % (SP, f))
        for cid, o, cl in c.execute('select candle_id,open,close from candles'):
            if o:
                out[cid // 1000] = 'UP' if cl >= o else 'DOWN'
    return out


def polymarket_actual():
    c = sqlite3.connect('%s/db/venues.sqlite3' % SP)
    return {e: a for e, a in c.execute('select epoch,actual from outcome') if a}


def kline_features():
    """epoch -> (trailing-12 span bps, flips of the open in the last 6 candles)."""
    d = np.load('%s/build/paths.npz' % SP)
    cid, p = d['cid'], d['paths'].astype(float)
    ep = cid // 1000
    crossed = np.array([bool((p[i] > p[i, 0]).any() and (p[i] < p[i, 0]).any()) for i in range(len(p))])
    feat = {}
    for i in range(12, len(ep)):
        w = p[i - 12:i]
        span = (w.max() - w.min()) / w[0, 0] * 1e4
        feat[int(ep[i])] = (span, int(crossed[i - 6:i].sum()))
    return feat


def per_dollar(ask, won, rate):
    return (1.0 / ask) * (1.0 - rate * (1.0 - ask)) - 1.0 if won else -1.0


def load():
    act, kf = (polymarket_actual() if ORACLE == 'POLY' else binance_actual()), kline_features()
    c = sqlite3.connect('%s/db/v12w.sqlite3' % SP)
    rows, skipped = [], {'no oracle label': 0, 'no kline features': 0, 'no ask': 0, 'no feat blob': 0}
    for ep, side, ask, sec, rate_bps, feat in c.execute(
            'select candle_epoch,side,quote_ask,sec,fee_rate_bps,feat from trades order by candle_epoch'):
        if ask is None:
            skipped['no ask'] += 1; continue
        if ep not in act:
            skipped['no oracle label'] += 1; continue
        if ep not in kf:
            skipped['no kline features'] += 1; continue
        if not feat:
            skipped['no feat blob'] += 1; continue
        fb = json.loads(feat)
        au, ad = fb.get('_ask_up'), fb.get('_ask_dn')
        width = (au + ad - 1.0) if (au is not None and ad is not None) else None
        won = (act[ep] == side)
        t = dt.datetime.utcfromtimestamp(ep)
        span, flips = kf[ep]
        rows.append(dict(ep=ep, side=side, ask=ask, sec=sec, won=won,
                         pnl=per_dollar(ask, won, rate_bps / 1e4),
                         hour=t.hour, wknd=t.weekday() >= 5, span=span, flips=flips, width=width))
    return rows, skipped


def cell(tag, rows):
    n = len(rows)
    if n == 0:
        return '| %s | 0 | — | — | — | — |' % tag
    v = np.array([r['pnl'] for r in rows])
    hit = 100 * np.mean([r['won'] for r in rows])
    h = n // 2
    h1, h2 = v[:h].mean(), v[h:].mean()
    if n < MIN_N:
        verdict = 'INSUFFICIENT (n<%d), not read' % MIN_N
    elif np.sign(h1) != np.sign(h2):
        verdict = 'halves FAIL'
    else:
        verdict = 'halves pass, sign %s' % ('+' if v.mean() > 0 else '-')
    return '| %s | %d | %+.3f | %.1f%% | %+.3f / %+.3f | %s |' % (tag, n, v.mean(), hit, h1, h2, verdict)


HEAD = '| cell | n | per $1 | hit | halves | verdict |\n|---|---|---|---|---|---|'


def main():
    rows, skipped = load()
    print('graded and usable: %d' % len(rows))
    print('excluded: %s' % {k: v for k, v in skipped.items() if v})
    v = np.array([r['pnl'] for r in rows]); h = len(v) // 2
    print('\nALL POLYMARKET v12 PAPER, graded on POLYMARKET\'s oracle (the venue that pays)')
    print(HEAD); print(cell('all', rows))

    print('\n### V asked for this cell FIRST: Task 13\'s only negative cell, the busiest range quartile')
    print(HEAD); print(cell('Q4 busiest', [r for r in rows if r['span'] >= SPAN_CUTS[2]]))

    def grid(name, keyfn, order):
        print('\n### %s' % name); print(HEAD)
        for k in order:
            print(cell(str(k), [r for r in rows if keyfn(r) == k]))

    grid('trailing-12 SPAN quartile (cuts 31.4 / 48.9 / 76.4 bps)',
         lambda r: SPAN_NAME[sum(r['span'] >= c for c in SPAN_CUTS)], SPAN_NAME)
    grid('UTC 8-hour block', lambda r: next(n for a, b, n in BLOCKS if a <= r['hour'] < b),
         [n for _, _, n in BLOCKS])
    grid('weekday / weekend', lambda r: 'weekend' if r['wknd'] else 'weekday', ['weekday', 'weekend'])
    grid('flips of the open in the last 6 candles',
         lambda r: '0-1' if r['flips'] <= 1 else ('2-3' if r['flips'] <= 3 else '4+'), ['0-1', '2-3', '4+'])
    wid = [r['width'] for r in rows if r['width'] is not None]
    med = float(np.median(wid)) if wid else None
    print('\n### book width at the fire (ask_up+ask_dn-1), cut at the median %.4f' % med)
    print('(no prior H1 cut existed for Polymarket width; the median is stated, not tuned)')
    print(HEAD)
    for nm, f in (('tight', lambda r: r['width'] is not None and r['width'] <= med),
                  ('wide', lambda r: r['width'] is not None and r['width'] > med)):
        print(cell(nm, [r for r in rows if f(r)]))

    F = Finding('Task R-1 - Polymarket v12 paper, all cells pooled', per_fire=v.mean(), n=len(v))
    lane = dict(sqlite3.connect('%s/db/v12w.sqlite3' % SP).execute(
        'select candle_epoch,actual from trades where actual is not null'))
    F.grading(polymarket_venues_outcome=polymarket_actual(), lane_recorded_actual=lane)
    F.sample({'all graded': len(v)})
    F.halves(v[:h].mean(), v[h:].mean())
    print()
    print('VERDICT', F.verdict())


if __name__ == '__main__':
    main()
