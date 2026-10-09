"""R-14 (V, 09-16 00:1x): the edge is execution. Real data only.

R-13 established the engine is a spread-capture strategy: its EV is the book spread, not a forecast.
So this looks at where the spread is actually won or lost - the ask you get, whether you are filled,
and when you fire.

Sources: the Zurich live journals (orders.plan carries cap / quote / max_shares / age_ms, fills
carry the price actually paid, results carry the venue's own resolution) and the 1 Hz polybook.
Live rows are graded on the journal's own `actual` - that IS the venue resolution, verified from
grade_loop, and my venues snapshot does not reach these days.
"""
import json, os, sqlite3, statistics, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

DB = '/tmp/claude-0/db'
RATE = 0.07


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def book():
    c = sqlite3.connect(os.path.join(DB, 'polybook.sqlite3'))
    out = {}
    for t, au, su, bu, ad, sd, bd in c.execute(
            'select ts_ms,ask_up,size_up,bid_up,ask_dn,size_dn,bid_dn from pb'):
        out[t // 1000] = (au, su, bu, ad, sd, bd)
    return out


def side_view(b, side):
    """(ask, displayed size, bid) on the side we are buying."""
    if b is None:
        return None
    au, su, bu, ad, sd, bd = b
    return (au, su, bu) if side == 'UP' else (ad, sd, bd)


def orders():
    out = []
    for n in ('zurich_v1', 'zurich_2'):
        p = os.path.join(DB, n + '.sqlite3')
        if not os.path.exists(p):
            continue
        c = sqlite3.connect(p)
        sig = {e: json.loads(d) for e, d in c.execute('select epoch,decision from signals')}
        fill = {e: pr for e, pr in c.execute('select epoch,price from fills')}
        res = {e: a for e, a in c.execute('select epoch,actual from results')}
        for oid, ep, status, plan, ts, reason in c.execute(
                'select id,epoch,status,plan,ts,reason from orders'):
            try:
                pl = json.loads(plan)
            except Exception:
                continue
            d = sig.get(ep) or {}
            # ts is stored in SECONDS in these journals, not ms - computing `sec` only for the
            # ms case left it None on every row and silently emptied the whole fire-second grid.
            tsec = (int(ts) // 1000) if (ts and ts > 1e11) else int(ts or ep)
            out.append(dict(
                lane=n, ep=int(ep), ts=tsec, sec=tsec - int(ep),
                side=d.get('side'), status=status,
                filled=(status == 'FILLED'), fak=('FAK' in (reason or '')),
                cap=pl.get('cap'), quote=pl.get('quote'), presub=pl.get('pre_submit_quote'),
                max_shares=pl.get('max_shares'), age_ms=pl.get('age_ms'),
                paid=fill.get(ep), actual=res.get(ep)))
    return [o for o in out if o['side'] and o['quote']]


def cell(rows):
    g = [r for r in rows if r['actual'] and r['filled'] and r['paid']]
    if not g:
        return None
    pnl = [per1(r['paid'], r['side'] == r['actual']) for r in g]
    return dict(n=len(g), win=sum(1 for r in g if r['side'] == r['actual']) / len(g),
                per1=statistics.fmean(pnl), total=sum(pnl))


def main():
    B, O = book(), orders()
    for o in O:
        for lag, key in ((0, 'm0'), (1, 'm1'), (5, 'm5'), (60, 'm60')):
            v = side_view(B.get(o['ts'] + lag), o['side'])
            o[key] = ((v[0] + v[2]) / 2) if (v and v[0] is not None and v[2] is not None) else None
        v0 = side_view(B.get(o['ts']), o['side'])
        o['ask0'], o['disp'] = (v0[0], v0[1]) if v0 else (None, None)
    fills = [o for o in O if o['filled']]
    rej = [o for o in O if not o['filled']]
    print('=' * 78)
    print('R-14  execution anatomy. %d live orders: %d filled, %d rejected (%d FAK-killed).'
          % (len(O), len(fills), len(rej), sum(1 for r in rej if r['fak'])))
    print('=' * 78)

    print('\n(1) WHAT YOU PAY vs THE VENUE MID, and where the cheap ask comes from')
    print('    %-18s %6s %9s %9s %9s %9s' % ('', 'n', 'vs mid0', 'vs mid+1s', 'vs mid+5s', 'vs mid+60s'))
    for nm, s in (('FILLED (paid)', fills), ('REJECTED (cap)', rej)):
        row = []
        for key in ('m0', 'm1', 'm5', 'm60'):
            d = [(o['paid'] if o['filled'] else o['cap']) - o[key]
                 for o in s if o[key] is not None and (o['paid'] if o['filled'] else o['cap'])]
            row.append(statistics.median(d) if d else float('nan'))
        print('    %-18s %6d %+9.4f %+9.4f %+9.4f %+9.4f' % (nm, len(s), *row))
    print('    Negative = you are buying BELOW the venue mid, i.e. under fair by the book\'s own')
    print('    reckoning. Positive = paying up.')
    d = [o['ask0'] - o['m0'] for o in O if o['ask0'] and o['m0']]
    print('    For reference the ASK sits %+.4f above the mid (median half-spread).'
          % (statistics.median(d) / 1 if d else float('nan')))

    print('\n(2) REJECT ANATOMY - order size vs displayed size at the signal second')
    print('    %-22s %6s %8s %9s %10s' % ('size / displayed', 'n', 'fill%', 'median', 'pnl/$1'))
    bins = [(0, 0.25, 'under 25%'), (0.25, 0.5, '25-50%'), (0.5, 1.0, '50-100%'),
            (1.0, 2.0, '1-2x'), (2.0, 1e9, 'over 2x')]
    have = [o for o in O if o['disp'] and o['max_shares']]
    print('    orders with a book sample and a size: %d of %d' % (len(have), len(O)))
    for lo, hi, nm in bins:
        s = [o for o in have if lo <= o['max_shares'] / o['disp'] < hi]
        if not s:
            continue
        c = cell(s)
        fr = sum(1 for o in s if o['filled']) / len(s)
        print('    %-22s %6d %7.1f%% %9.2f %10s%s'
              % (nm, len(s), 100 * fr,
                 statistics.median([o['max_shares'] / o['disp'] for o in s]),
                 ('%+.3f' % c['per1']) if c else '-',
                 '' if len(s) >= MIN_CELL else '  insufficient'))

    print('\n(3) FIRE-SECOND x ASK BUCKET - full grid, never the best cell')
    secs = [(15, 60), (60, 120), (120, 180), (180, 241)]
    asks = [(0, 0.40), (0.40, 0.50), (0.50, 1.0)]
    print('    %-12s %-12s %6s %8s %10s' % ('second', 'ask', 'n', 'fill%', 'pnl/$1'))
    for a, b in secs:
        for x, z in asks:
            s = [o for o in O if o['sec'] is not None and a <= o['sec'] < b
                 and o['quote'] and x <= o['quote'] < z]
            if not s:
                continue
            c = cell(s)
            print('    %-12s %-12s %6d %7.1f%% %10s%s'
                  % ('%d-%d' % (a, b), '%.2f-%.2f' % (x, z), len(s),
                     100 * sum(1 for o in s if o['filled']) / len(s),
                     ('%+.3f' % c['per1']) if c else '-',
                     '' if len(s) >= MIN_CELL else '  insufficient'))
    print()


if __name__ == '__main__':
    main()
