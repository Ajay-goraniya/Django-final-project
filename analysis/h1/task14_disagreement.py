"""Task 14 (V, 23:40) - where and why the two venues resolve differently. DESCRIPTION ONLY.

Everything grades on the ENGINE's actual (Binance close >= open), which Tokyo's real
financial_result confirms is what Predict.fun pays on. No rule proposals, no thresholds.

Buckets are defined HERE, before any outcome is looked at:
  |close - open| at Binance close, in bps: [0,1) [1,2.5) [2.5,5) [5,10) [10,25) [25,inf)
"""
import sqlite3, json, numpy as np
from collections import Counter

DBD = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
LB = '/home/user/Django-final-project/learner/live_backup'
BPS_EDGES = [0, 1, 2.5, 5, 10, 25, np.inf]
BPS_LBL = ['<1', '1-2.5', '2.5-5', '5-10', '10-25', '25+']


def bucket(b):
    for i in range(len(BPS_EDGES) - 1):
        if BPS_EDGES[i] <= b < BPS_EDGES[i + 1]:
            return i
    return len(BPS_LBL) - 1


def engine_candles():
    """epoch -> (actual, |close-open| in bps, close-open signed)."""
    out = {}
    for f in ('build11.sqlite3', 'predict_pnl.sqlite3', 'twin_c_thr1.sqlite3'):
        try:
            c = sqlite3.connect(f'{DBD}/{f}')
        except Exception:
            continue
        for cid, o, cl in c.execute('select candle_id, open, close from candles'):
            if o:
                out[cid // 1000] = ('UP' if cl >= o else 'DOWN', abs(cl - o) / o * 1e4, cl - o)
    return out


def venue_quotes():
    """epoch -> {sec_index: (poly_up, pred_up, pred_dn)} on the 5 s grid."""
    c = sqlite3.connect(f'{DBD}/venues.sqlite3')
    rows = {}
    for ep, sec, pu, yu, yd in c.execute(
            'select epoch, sec, poly_up, pred_up, pred_dn from q order by epoch, sec'):
        rows.setdefault(ep, {})[sec] = (pu, yu, yd)
    return rows, dict(c.execute('select epoch, actual from outcome'))


def at(qs, target, field=None):
    """Last quote at or before `target` seconds (forward fill), per field.

    Fields are filled independently because poly_up and the two Predict.fun asks go missing at
    different times; requiring one sample where all three are present throws away most of the data.
    """
    secs = sorted(s for s in qs if s <= target)
    if not secs:
        return None
    pu = yu = yd = None
    for s in secs:
        a, b, c = qs[s]
        if a is not None: pu = a
        if b is not None: yu = b
        if c is not None: yd = c
    return (pu, yu, yd)


if __name__ == '__main__':
    eng = engine_candles()
    qrows, poly = venue_quotes()
    common = sorted(set(eng) & set(poly))
    disp = [e for e in common if poly[e] != eng[e][0]]
    print('engine candles=%d  polymarket outcomes=%d  common=%d  DISPUTED=%d (%.1f%%)'
          % (len(eng), len(poly), len(common), len(disp), 100 * len(disp) / len(common)))
    print('direction of disagreement (poly -> engine):',
          dict(Counter((poly[e], eng[e][0]) for e in disp)))

    # ---------- 1. Is the disagreement concentrated in near-zero candles? ----------
    print()
    print('=' * 88)
    print('1. DISPUTED RATE BY |close-open| BUCKET (buckets fixed in advance), both halves')
    print('=' * 88)
    mid = common[len(common) // 2]
    print('%-8s %7s %9s %9s | %9s %9s | %s' % ('bps', 'n', 'disputed', 'rate', 'rate h1', 'rate h2', 'share of all disputes'))
    print('-' * 88)
    for i, lbl in enumerate(BPS_LBL):
        grp = [e for e in common if bucket(eng[e][1]) == i]
        if not grp:
            continue
        d = [e for e in grp if poly[e] != eng[e][0]]
        h1 = [e for e in grp if e < mid]; h2 = [e for e in grp if e >= mid]
        r1 = np.mean([poly[e] != eng[e][0] for e in h1]) if h1 else float('nan')
        r2 = np.mean([poly[e] != eng[e][0] for e in h2]) if h2 else float('nan')
        print('%-8s %7d %9d %8.1f%% | %8.1f%% %8.1f%% | %5.1f%%'
              % (lbl, len(grp), len(d), 100 * len(d) / len(grp), 100 * r1, 100 * r2,
                 100 * len(d) / len(disp)))
    allb = [eng[e][1] for e in common]; dsb = [eng[e][1] for e in disp]
    print('median |close-open|: all candles %.2f bps, disputed %.2f bps' % (np.median(allb), np.median(dsb)))

    # ---------- Polymarket's own price on the disputed candles ----------
    print()
    print('=' * 88)
    print('   POLYMARKET UP PRICE ON DISPUTED vs AGREED CANDLES (its own book, late in the candle)')
    print('=' * 88)
    print('%-10s %-9s %7s %10s %10s %10s' % ('group', 'sec', 'n', 'median', 'p25', 'p75'))
    for grp, name in ((disp, 'disputed'), ([e for e in common if poly[e] == eng[e][0]], 'agreed')):
        for tgt in (237, 287):
            v = [at(qrows.get(e, {}), tgt) for e in grp]
            pu = np.array([x[0] for x in v if x and x[0] is not None], float)
            if len(pu):
                print('%-10s %-9s %7d %10.3f %10.3f %10.3f'
                      % (name, 't=%d' % tgt, len(pu), np.median(pu), *np.percentile(pu, [25, 75])))
    # how confident was Polymarket on the candles it got "wrong" by Predict.fun's rule
    conf = []
    for e in disp:
        v = at(qrows.get(e, {}), 287)
        if v and v[0] is not None:
            conf.append(v[0] if poly[e] == 'UP' else 1 - v[0])
    if conf:
        conf = np.array(conf)
        print('On disputed candles, Polymarket\'s price for ITS OWN winning side at t=287: '
              'median %.3f, p90 %.3f, share >= 0.90: %.0f%%'
              % (np.median(conf), np.percentile(conf, 90), 100 * (conf >= 0.90).mean()))

    # ---------- 2. Loss share by bucket, on real fires ----------
    print()
    print('=' * 88)
    print('2. WHERE THE LOSSES SIT, by |close-open| bucket (engine grading)')
    print('=' * 88)
    orders = json.load(open(f'{LB}/tokyo_orders.json'))
    srcs = [('TOKYO ' + k, [r for r in orders if r.get('filled') and r.get('pnl') is not None
                            and (k == 'ALL' or r.get('kind') == k)]) for k in ('EF', 'REVERSAL', 'ALL')]
    for kind, rows in srcs:
        rows = [r for r in rows if (r['candle_id'] // 1000) in eng]
        if len(rows) < 20:
            print('-- %s: n=%d, insufficient' % (kind, len(rows))); continue
        tot = sum(r['pnl'] for r in rows)
        loss = sum(r['pnl'] for r in rows if r['pnl'] < 0)
        print('-- %s: n=%d  total PnL %+.2f  (gross losses %+.2f)' % (kind, len(rows), tot, loss))
        print('   %-8s %6s %7s %10s %10s %12s' % ('bps', 'n', 'hit', 'PnL', 'per-fire', 'share of loss'))
        for i, lbl in enumerate(BPS_LBL):
            g = [r for r in rows if bucket(eng[r['candle_id'] // 1000][1]) == i]
            if not g:
                continue
            p = sum(r['pnl'] for r in g)
            l = sum(r['pnl'] for r in g if r['pnl'] < 0)
            hit = np.mean([bool(r.get('correct')) for r in g])
            print('   %-8s %6d %6.0f%% %+10.2f %+10.3f %11.0f%%'
                  % (lbl, len(g), 100 * hit, p, p / len(g), 100 * l / loss if loss else 0))

    # ---------- 3. Does the late Predict.fun ask price the near-zero risk? ----------
    print()
    print('=' * 88)
    print('3. IS THE LATE PREDICT.FUN ASK FAIR IN THE NEAR-ZERO BUCKET? (t>=237, engine grading)')
    print('   ask = what you pay for the favoured side; realised = how often that side actually won')
    print('=' * 88)
    print('%-8s %7s %10s %12s %10s' % ('bps', 'n', 'mean ask', 'realised win', 'gap'))
    print('-' * 88)
    for i, lbl in enumerate(BPS_LBL):
        asks, wins = [], []
        for e in common:
            if bucket(eng[e][1]) != i:
                continue
            v = at(qrows.get(e, {}), 237)
            if not v or v[1] is None or v[2] is None:
                continue
            pu, yu, yd = v
            imp = yu / (yu + yd)
            side = 'UP' if imp >= 0.5 else 'DOWN'
            asks.append(yu if side == 'UP' else yd)
            wins.append(eng[e][0] == side)
        if len(asks) >= 20:
            a, w = np.mean(asks), np.mean(wins)
            print('%-8s %7d %10.3f %11.3f %10.3f' % (lbl, len(asks), a, w, w - a))
        elif asks:
            print('%-8s %7d   (insufficient, <20)' % (lbl, len(asks)))

    # ---------- 2b. Twin ACCURACY by bucket (no PnL: the twin tables carry the BTC signal
    # price, not the entry ask, so PnL is not reconstructable from them - hit rate is) ----------
    print()
    print('=' * 88)
    print('2b. HIT RATE BY BUCKET on the paper twins (A + C pooled) - fills the REVERSAL gap,')
    print('    where Tokyo has only 18 fills. Accuracy only; these tables carry no entry ask.')
    print('=' * 88)
    tw = {'EF': [], 'REVERSAL': []}
    for db in ('twin_c_thr1.sqlite3', 'build11.sqlite3'):
        c = sqlite3.connect(f'{DBD}/{db}')
        for tbl in ('ef_predictions', 'predictions'):
            for cid, kind, d in c.execute(f'select candle_id, kind, direction from {tbl}'):
                ep = cid // 1000
                if kind in tw and ep in eng:
                    tw[kind].append((ep, eng[ep][0] == d))
    for kind, rows in tw.items():
        print('-- %s pooled twins: n=%d  overall hit %.0f%%'
              % (kind, len(rows), 100 * np.mean([h for _, h in rows])))
        print('   %-8s %6s %8s' % ('bps', 'n', 'hit'))
        for i, lbl in enumerate(BPS_LBL):
            g = [h for e, h in rows if bucket(eng[e][1]) == i]
            if len(g) >= 20:
                print('   %-8s %6d %7.0f%%' % (lbl, len(g), 100 * np.mean(g)))
            elif g:
                print('   %-8s %6d   (insufficient, <20)' % (lbl, len(g)))
