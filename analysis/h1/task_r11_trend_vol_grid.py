"""Task R-11 (V, 09-15 23:0x): trend x volatility x side grid.

Today 13-22 UTC the live lane took -0.131/$1 on 36 results during a -2.8% BTC selloff with rv60
median 0.75, against +0.717/$1 on the 29 results before 13:00. rv60 ALONE is not a losing bucket
(every rv60 bucket is positive on poly_pnl and v10_long4). The question is whether
"selling into a selloff at high vol" is a cell that loses EVERY day - rain or sun - or whether
today is variance.

Buckets are fixed BEFORE any outcome is read, exactly as V specified:
    ret60  tercile of the sample            -> down / flat / up
    rv60   FIXED cuts   < 0.35 / 0.35-0.75 / > 0.75
    side   UP / DOWN
3 x 3 x 2 = 18 cells. Every cell reported: n, hit%, per $1, both halves, and "insufficient" under
60. Never the best cell.

Sample: every graded Polymarket fire - poly_pnl, poly_acc, v12 lane + weekend - plus the live
Zurich rows. Graded on venues.outcome. Paper fills at the quoted ask are an upper bound; the
Zurich rows are real fills and are shown separately as well as pooled.
"""
import json, os, sqlite3, statistics, sys
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

DB = '/tmp/claude-0/db'
RATE = 0.07
RV_CUTS = [0.35, 0.75]                      # fixed by the brief, not fitted
RV_NAME = ['rv<0.35', 'rv0.35-0.75', 'rv>0.75']
RET_NAME = ['ret60 down', 'ret60 flat', 'ret60 up']


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def oracle():
    return dict(sqlite3.connect(os.path.join(DB, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))


def fires(oc):
    out = []
    lanes = [('poly_pnl', 'ts_ms', 'ask'), ('poly_acc', 'ts_ms', 'ask'),
             ('v12_poly_lane', 'signal_ms', 'quote_ask'),
             ('v12_poly_weekend', 'signal_ms', 'quote_ask')]
    for name, tcol, acol in lanes:
        c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
        for ep, ts, side, ask, feat in c.execute(
                'select candle_epoch,%s,side,%s,feat from trades where actual is not null' % (tcol, acol)):
            if ask is None or feat is None or int(ep) not in oc:
                continue
            f = json.loads(feat)
            if f.get('ret60') is None or f.get('rv60') is None:
                continue
            out.append(dict(ep=int(ep), ts=int(ts) // 1000, side=side, ask=float(ask),
                            ret60=float(f['ret60']), rv60=float(f['rv60']), kind='paper', lane=name))
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
            ft = d.get('features') or {}
            if ft.get('ret60') is None:
                continue
            # My venues.sqlite3 snapshot ends before today's live rows, so requiring it here would
            # silently drop the very fires that prompted this task. The Zurich journal's own
            # `actual` IS the venue's resolution - verified from grade_loop in
            # learner/v12_polymarket/btc_model_v12_polymarket.py, which reads the Gamma market's
            # outcomePrices and never touches candles (STATE.md CLOSED 09-15 02:37). So live rows
            # are graded on it, and `own_actual` records that they were.
            out.append(dict(ep=int(ep), ts=int(ep) + int(d.get('sec') or 0), side=d['side'],
                            ask=float(price.get(ep) or d['ask']), ret60=float(ft['ret60']),
                            rv60=float(d.get('rv60') or ft.get('rv60')), kind='live', lane=name,
                            own_actual=act))
    return sorted(out, key=lambda r: r['ts'])


def actual_of(r, oc):
    """Each row on the oracle its own venue settles on. Paper rows: venues.outcome. Live Zurich
    rows: the journal's own `actual`, which IS the venue resolution (code-verified) and reaches
    days my venues snapshot does not."""
    return r.get('own_actual') or oc.get(r['ep'])


def cell(rows, oc):
    rows = [r for r in rows if actual_of(r, oc)]
    if not rows:
        return None
    pnl, wins = [], 0
    for r in rows:
        won = (r['side'] == actual_of(r, oc))
        wins += won
        pnl.append(per1(r['ask'], won))
    return dict(n=len(pnl), win=wins / len(pnl), per1=statistics.fmean(pnl), total=sum(pnl))


def halves(rows, oc):
    s = sorted(rows, key=lambda r: r['ts'])
    h = len(s) // 2
    a, b = cell(s[:h], oc), cell(s[h:], oc)
    return (a['per1'] if a else float('nan')), (b['per1'] if b else float('nan'))


def rvb(v):
    return 0 if v < RV_CUTS[0] else (1 if v <= RV_CUTS[1] else 2)


def main():
    oc = oracle()
    F = fires(oc)
    rc = sorted(r['ret60'] for r in F)
    RET_CUTS = [rc[len(rc) // 3], rc[2 * len(rc) // 3]]
    for r in F:
        r['rb'] = 0 if r['ret60'] < RET_CUTS[0] else (1 if r['ret60'] < RET_CUTS[1] else 2)
        r['vb'] = rvb(r['rv60'])
        r['day'] = datetime.utcfromtimestamp(r['ep']).strftime('%Y-%m-%d')

    live = [r for r in F if r['kind'] == 'live']
    print('=' * 78)
    print('R-11  trend x vol x side. Buckets fixed before any outcome was read.')
    print('=' * 78)
    print('  %d graded fires (%d paper, %d LIVE Zurich), %d days.'
          % (len(F), len(F) - len(live), len(live), len({r['day'] for r in F})))
    print('  ret60 tercile cuts %.3f / %.3f bps (from the sample). rv60 cuts 0.35 / 0.75 (fixed by'
          % tuple(RET_CUTS))
    print('  the brief, not fitted). Paper is at the quoted ask - an upper bound; live is real fills.')
    print()
    print('  %-12s %-13s %-5s %6s %8s %10s %9s %9s'
          % ('ret60', 'rv60', 'side', 'n', 'hit%', 'per $1', 'h1', 'h2'))
    cells = {}
    for i in range(3):
        for j in range(3):
            for side in ('UP', 'DOWN'):
                sub = [r for r in F if r['rb'] == i and r['vb'] == j and r['side'] == side]
                d = cell(sub, oc)
                cells[(i, j, side)] = (d, sub)
                if not d:
                    print('  %-12s %-13s %-5s %6d %8s' % (RET_NAME[i], RV_NAME[j], side, 0, '-'))
                    continue
                h1, h2 = halves(sub, oc)
                mark = '' if d['n'] >= MIN_CELL else '  insufficient'
                print('  %-12s %-13s %-5s %6d %7.1f%% %+10.3f %+9.3f %+9.3f%s'
                      % (RET_NAME[i], RV_NAME[j], side, d['n'], 100 * d['win'], d['per1'],
                         h1, h2, mark))
    print()
    readable = [k for k, (d, _) in cells.items() if d and d['n'] >= MIN_CELL]
    print('  readable cells (n>=%d): %d of 18' % (MIN_CELL, len(readable)))
    print()

    key = (0, 2, 'DOWN')                       # selling into a selloff at high vol
    d, sub = cells[key]
    print('=' * 78)
    print('THE CELL IN QUESTION: %s / %s / DOWN - "selling into a selloff at high vol"'
          % (RET_NAME[0], RV_NAME[2]))
    print('=' * 78)
    if not d:
        print('  no fires in this cell at all.')
    else:
        h1, h2 = halves(sub, oc)
        print('  n=%d  hit %.1f%%  per $1 %+.3f  total %+.2f  halves %+.3f / %+.3f%s'
              % (d['n'], 100 * d['win'], d['per1'], d['total'], h1, h2,
                 '' if d['n'] >= MIN_CELL else '   INSUFFICIENT - not read'))
        print()
        print('  RAIN OR SUN - this cell, every day it fires, nothing dropped:')
        print('    %-12s %5s %8s %10s' % ('day', 'n', 'hit%', 'per $1'))
        pos = tot = 0
        for day in sorted({r['day'] for r in sub}):
            s2 = [r for r in sub if r['day'] == day]
            dd = cell(s2, oc)
            pos += dd['per1'] > 0
            tot += 1
            print('    %-12s %5d %7.1f%% %+10.3f%s'
                  % (day, dd['n'], 100 * dd['win'], dd['per1'],
                     '' if dd['n'] >= MIN_CELL else '  thin'))
        print('    days positive: %d of %d' % (pos, tot))
        print()
        allc = cell(F, oc)
        f = Finding('R-11 %s / %s / DOWN loses' % (RET_NAME[0], RV_NAME[2]),
                    per_fire=d['per1'], n=d['n'])
        f.sample({'the cell': d['n']})
        f.halves(first=h1, second=h2)
        f.null(mine=-d['per1'], null_value=-allc['per1'],
               null_name='NEGATED: does this cell lose MORE than the book as a whole')
        f.quote_age(rule='at-or-after', max_age_s=0.0,
                    source='ret60/rv60 are the engine\'s own fire-time features')
        f.verdict()

    print('=' * 78)
    print('TODAY (09-15) vs the rest, same cells, since that is what prompted the question')
    print('=' * 78)
    t = [r for r in F if r['day'] == '2026-09-15']
    o = [r for r in F if r['day'] != '2026-09-15']
    for nm, s in (('2026-09-15', t), ('all other days', o)):
        dd = cell(s, oc)
        if dd:
            print('  %-16s n=%4d hit %.1f%% per $1 %+.3f%s'
                  % (nm, dd['n'], 100 * dd['win'], dd['per1'],
                     '' if dd['n'] >= MIN_CELL else '  insufficient'))
    if t:
        print('  today by rv60 bucket:')
        for j in range(3):
            s2 = [r for r in t if r['vb'] == j]
            dd = cell(s2, oc)
            if dd:
                print('    %-13s n=%4d hit %.1f%% per $1 %+.3f%s'
                      % (RV_NAME[j], dd['n'], 100 * dd['win'], dd['per1'],
                         '' if dd['n'] >= MIN_CELL else '  insufficient'))
    print()


if __name__ == '__main__':
    main()
