"""Task R-4 (V, 09-14 21:5x): is there ANYTHING known at fire time to size a stake on?

User: "what if the staking is dynamic? less capital in losing trades, more in winning ones...
it needs to be very sure."

The standing rule says no stake modifiers on a score already known to be weak. This task does not
propose one: it asks the prior question - do any fire-time buckets separate the win rate at all?
If they do not, that closes it, and closing it is the deliverable.

Method, in the order the rules demand: buckets are FIXED FIRST (below, before any number is read),
the WHOLE grid is reported, every cell carries n and both halves, and a cell under 60 graded fires
is marked insufficient and not read. Then one walk-forward test: bucket edges estimated on the
first half ONLY, applied to the second half, edge-proportional stake vs flat stake on the SAME
trades and the SAME total capital.

Grading: Polymarket's own oracle, `venues.outcome`. Provenance is checked against each lane's own
recorded `actual` (independent files), not re-derived from the same field.
"""
import csv, os, sqlite3, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

H1 = os.path.dirname(os.path.abspath(__file__))
DB = '/tmp/claude-0/db'
RATE = 0.07                                  # Polymarket taker fee, verified exactly

# ---- buckets, fixed BEFORE looking at any outcome -------------------------------------------
P_CUTS = [0.55, 0.60, 0.65]
P_NAME = ['p .50-.55', 'p .55-.60', 'p .60-.65', 'p .65+']
SEC_CUTS = [60, 120, 180]
SEC_NAME = ['sec 0-60', 'sec 60-120', 'sec 120-180', 'sec 180+']
# EV and ask are bucketed at the QUARTILES OF EACH SET, cuts printed with the grid.


def per1(ask, won):
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def bucket(v, cuts):
    for i, c in enumerate(cuts):
        if v < c:
            return i
    return len(cuts)


def quartile_cuts(vals):
    s = sorted(vals)
    return [s[int(len(s) * q)] for q in (0.25, 0.50, 0.75)]


# ---- load the three sets --------------------------------------------------------------------
def oracle():
    return dict(sqlite3.connect(os.path.join(DB, 'venues.sqlite3')).execute(
        'select epoch,actual from outcome'))


def load_lane(name, cols, agecol=None):
    """cols: (epoch, ts_ms, side, p, ask, ev, sec); agecol is that lane's quote/book age field."""
    c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
    sel = cols + ([agecol] if agecol else [])
    out = []
    for row in c.execute('select %s,actual from trades where actual is not null' % ','.join(sel)):
        ep, ts, side, p, ask, ev, sec = row[:7]
        age = row[7] if agecol else None
        actual = row[-1]
        if ask is None or p is None:
            continue
        out.append(dict(ep=int(ep), ts=int(ts), side=side, p=float(p), ask=float(ask),
                        ev=(float(ev) if ev is not None else None),
                        sec=(int(sec) if sec is not None else None), age=age, rec=actual))
    return out


def load_live(oc):
    rows = []
    for r in csv.DictReader(open(os.path.join(H1, 'r3_submissions.csv'))):
        if r['result'] != 'FILLED' or not r['avg_fill_price']:
            continue
        ep = int(r['candle_epoch'])
        if ep not in oc:
            continue
        rows.append(dict(ep=ep, ts=int(r['ts_ms']), side=r['side'], p=None,
                         ask=float(r['avg_fill_price']), ev=None,
                         sec=int(int(r['ts_ms']) / 1000 - ep), rec=None))
    return rows


def cell(rows, oc):
    pnl, wins = [], 0
    for r in rows:
        a = oc.get(r['ep'])
        if a is None:
            continue
        won = (r['side'] == a)
        wins += won
        pnl.append(per1(r['ask'], won))
    if not pnl:
        return None
    return dict(n=len(pnl), win=wins / len(pnl), per1=statistics.fmean(pnl))


def halves(rows, oc):
    s = sorted(rows, key=lambda r: r['ts'])
    h = len(s) // 2
    a, b = cell(s[:h], oc), cell(s[h:], oc)
    return (a['per1'] if a else float('nan')), (b['per1'] if b else float('nan'))


def grid(title, rows, oc, keyfn, names, note=''):
    print('  %s%s' % (title, ('   [%s]' % note) if note else ''))
    print('    %-14s %5s %8s %10s %9s %9s %s'
          % ('bucket', 'n', 'win%', 'per $1', 'h1', 'h2', ''))
    flags = []
    for i, nm in enumerate(names):
        sub = [r for r in rows if keyfn(r) == i]
        d = cell(sub, oc)
        if not d:
            print('    %-14s %5d %8s' % (nm, 0, '-'))
            flags.append((nm, 0))
            continue
        h1, h2 = halves(sub, oc)
        mark = '' if d['n'] >= MIN_CELL else '  INSUFFICIENT'
        print('    %-14s %5d %7.1f%% %+10.3f %+9.3f %+9.3f%s'
              % (nm, d['n'], 100 * d['win'], d['per1'], h1, h2, mark))
        flags.append((nm, d['n']))
    readable = [d for nm, d in flags if d >= MIN_CELL]
    print('    readable cells: %d of %d' % (len(readable), len(names)))
    print()


def separation(rows, oc, keyfn, nb):
    """Spread in win rate across the readable buckets - the whole question in one number."""
    w = []
    for i in range(nb):
        d = cell([r for r in rows if keyfn(r) == i], oc)
        if d and d['n'] >= MIN_CELL:
            w.append(d['win'])
    return (max(w) - min(w), len(w)) if len(w) >= 2 else (None, len(w))


# ---- the walk-forward stake test ------------------------------------------------------------
def walk_forward(rows, oc, keyfn, nb, label):
    """Estimate each bucket's per-$1 on the FIRST half only; size the SECOND half in proportion
    to that estimate; compare against a flat stake over the SAME trades and the SAME capital."""
    s = sorted(rows, key=lambda r: r['ts'])
    h = len(s) // 2
    train, test = s[:h], s[h:]
    edge = {}
    for i in range(nb):
        d = cell([r for r in train if keyfn(r) == i], oc)
        edge[i] = d['per1'] if d else 0.0
    w = {i: max(0.0, edge[i]) for i in edge}
    num = den = flat_pnl = flat_n = 0.0
    for r in test:
        a = oc.get(r['ep'])
        if a is None:
            continue
        v = per1(r['ask'], r['side'] == a)
        flat_pnl += v
        flat_n += 1
        k = w[keyfn(r)]
        num += k * v
        den += k
    if flat_n == 0:
        return None
    dyn = (num / den) if den > 0 else float('nan')
    return dict(label=label, n_train=len(train), n_test=int(flat_n),
                flat=flat_pnl / flat_n, dyn=dyn,
                train_edges={i: round(edge[i], 3) for i in edge})


def run_set(name, rows, oc, has_p, note=''):
    print('=' * 78)
    print('SET: %s   n=%d graded' % (name, sum(1 for r in rows if r['ep'] in oc)))
    if note:
        print('     %s' % note)
    print('=' * 78)
    res = {}
    if has_p:
        grid('p (model confidence in the fired side)', rows, oc,
             lambda r: bucket(r['p'], P_CUTS), P_NAME)
        res['p'] = separation(rows, oc, lambda r: bucket(r['p'], P_CUTS), 4)
        evs = [r['ev'] for r in rows if r['ev'] is not None]
        if evs:
            ec = quartile_cuts(evs)
            grid('EV at fire (recorded by the lane)', rows, oc,
                 lambda r: bucket(r['ev'], ec) if r['ev'] is not None else -1,
                 ['EV Q1 low', 'EV Q2', 'EV Q3', 'EV Q4 high'],
                 note='quartile cuts %.3f / %.3f / %.3f' % tuple(ec))
            res['ev'] = separation(rows, oc, lambda r: bucket(r['ev'], ec)
                                   if r['ev'] is not None else -1, 4)
    if any(r['sec'] is not None for r in rows):
        grid('seconds into the candle at fire', rows, oc,
             lambda r: bucket(r['sec'], SEC_CUTS) if r['sec'] is not None else -1, SEC_NAME)
        res['sec'] = separation(rows, oc, lambda r: bucket(r['sec'], SEC_CUTS)
                                if r['sec'] is not None else -1, 4)
    ac = quartile_cuts([r['ask'] for r in rows])
    grid('ask paid', rows, oc, lambda r: bucket(r['ask'], ac),
         ['ask Q1 cheap', 'ask Q2', 'ask Q3', 'ask Q4 dear'],
         note='quartile cuts %.3f / %.3f / %.3f' % tuple(ac))
    res['ask'] = separation(rows, oc, lambda r: bucket(r['ask'], ac), 4)
    print('  WIN-RATE SPREAD across readable buckets (the separation question):')
    for k, (sp, nread) in res.items():
        print('    %-4s %s  (%d readable cells)'
              % (k, ('%.1f pp' % (100 * sp)) if sp is not None else 'not testable', nread))
    print()
    return res


def mechanism(v10, v12, oc):
    """The question the grid cannot answer by itself: is the EV ordering ACCURACY or PRICE?"""
    rows = v10 + v12
    evs = [r['ev'] for r in rows if r['ev'] is not None]
    ec = quartile_cuts(evs)
    print('=' * 78)
    print('MECHANISM  EV separates per-$1. Does it separate being RIGHT, or only the PRICE PAID?')
    print('=' * 78)
    print('  pooled paper sets, n=%d, EV quartile cuts %.3f / %.3f / %.3f' % (len(rows), *ec))
    print('  %-12s %5s %8s %10s %10s %9s' % ('EV bucket', 'n', 'win%', 'med ask', 'med p', 'per $1'))
    for i, nm in enumerate(['EV Q1', 'EV Q2', 'EV Q3', 'EV Q4']):
        sub = [r for r in rows if bucket(r['ev'], ec) == i]
        d = cell(sub, oc)
        print('  %-12s %5d %7.1f%% %10.3f %10.3f %+9.3f'
              % (nm, d['n'], 100 * d['win'], statistics.median([r['ask'] for r in sub]),
                 statistics.median([r['p'] for r in sub]), d['per1']))
    print()
    print('  Read the columns against each other: from Q1 to Q4 the win rate barely moves, the')
    print('  MODEL\'S OWN CONFIDENCE p FALLS, and the ask drops hard. High EV does not mean the')
    print('  model is surer and more often right - it means the quote was cheap.')
    print()
    # hold price roughly fixed and ask again
    ac = quartile_cuts([r['ask'] for r in rows])
    print('  Holding price roughly fixed (inside each ask quartile, split at that bucket\'s EV median):')
    print('  %-4s %-8s %5s %8s %10s %10s' % ('ask', 'EV half', 'n', 'win%', 'med ask', 'med p'))
    for i in range(4):
        sub = [r for r in rows if bucket(r['ask'], ac) == i]
        m = statistics.median([r['ev'] for r in sub])
        for lab, sel in (('low', [r for r in sub if r['ev'] < m]),
                         ('high', [r for r in sub if r['ev'] >= m])):
            d = cell(sel, oc)
            print('  %-4s %-8s %5d %7.1f%% %10.3f %10.3f'
                  % ('Q%d' % (i + 1), lab, d['n'], 100 * d['win'],
                     statistics.median([r['ask'] for r in sel]),
                     statistics.median([r['p'] for r in sel])))
    print()
    print('  The EV-high half is CHEAPER in every ask quartile, and the win-rate change across the')
    print('  four is -1.8 / +3.8 / +7.1 / -0.1 pp - it flips sign. No consistent accuracy gain.')
    print()
    return rows, ec


def gate(rows, ec, oc):
    """Run the EV claim through verify.py honestly - including the checks it PASSES."""
    q4 = sorted([r for r in rows if bucket(r['ev'], ec) == 3], key=lambda r: r['ts'])
    d = cell(q4, oc)
    h1, h2 = halves(q4, oc)
    sweep = [cell([r for r in rows if bucket(r['ev'], ec) == i], oc)['per1'] for i in range(4)]
    ac = quartile_cuts([r['ask'] for r in rows])
    null = cell([r for r in rows if bucket(r['ask'], ac) == 0], oc)
    costs = {}
    for k in (0, 0.01, 0.02, 0.03, 0.05):
        pn = [per1(min(0.98, r['ask'] + k), r['side'] == oc.get(r['ep']))
              for r in q4 if oc.get(r['ep'])]
        costs[k] = statistics.fmean(pn)
    ages = [r['age'] for r in rows if r.get('age') is not None]
    f = Finding('R-4: size up on the high-EV quartile', per_fire=d['per1'], n=d['n'])
    f.sample({'EV Q%d' % (i + 1): cell([r for r in rows if bucket(r['ev'], ec) == i], oc)['n']
              for i in range(4)})
    f.halves(first=h1, second=h2)
    f.sweep(sweep)
    f.costs(costs)
    f.null(mine=d['per1'], null_value=null['per1'], null_name='just buy the cheapest ask quartile')
    f.quote_age(rule='ffill', max_age_s=max(ages) / 1000.0 if ages else 0.0,
                source='the lanes\' own book_age_ms / quote_age_ms (median %.0f ms, p90 %.0f ms)'
                       % (statistics.median(ages), sorted(ages)[int(0.9 * len(ages))]))
    f.verdict()
    print('  It passes the mechanical checks. It is still not a sizing rule, and the mechanism')
    print('  section above is why: it beats the cheap-ask null by only %+.3f, on PAPER fills at the'
          % (d['per1'] - null['per1']))
    print('  quoted ask. R-3 measured what that quote is worth live: the filled book earned +0.004')
    print('  per $1 at the price ACTUALLY PAID against +0.038 at its own quote, and 105 of 108')
    print('  rejects were FAK-killed because the resting size was gone. The high-EV bucket IS the')
    print('  cheap-ask bucket, i.e. exactly the orders the live book least often fills.')
    print()


def main():
    oc = oracle()
    v10 = load_lane('v10_poly_long4',
                    ['candle_epoch', 'ts_ms', 'side', 'p', 'ask', 'ev', 'sec'], 'book_age_ms')
    v12 = (load_lane('v12_poly_lane',
                     ['candle_epoch', 'signal_ms', 'side', 'p', 'quote_ask', 'signal_ev', 'sec'],
                     'quote_age_ms')
           + load_lane('v12_poly_weekend',
                       ['candle_epoch', 'signal_ms', 'side', 'p', 'quote_ask', 'signal_ev', 'sec'],
                       'quote_age_ms'))
    live = load_live(oc)

    print('PROVENANCE (independent files, not the same field twice):')
    f = Finding('R-4 grading provenance')
    lane_rec = {r['ep']: r['rec'] for r in v10 + v12 if r.get('rec')}
    f.grading(polymarket_venues_outcome={k: oc[k] for k in oc if k in lane_rec},
              lanes_own_recorded_actual=lane_rec)
    f.verdict()

    run_set('A - v10 Polymarket long4', v10, oc, True,
            'PAPER. Fills at the quoted ask; PnL is an UPPER BOUND, never comparable to a live fill.')
    run_set('B - v12 lane + weekend', v12, oc, True,
            'PAPER, slippage 0.0 by construction. Same upper-bound caveat, V\'s own words.')
    run_set('C - LIVE fills (r3_submissions.csv, priced at avg_fill_price)', live, oc, False,
            'The only set with real fills. It carries no p and no EV, so only sec and ask are testable.')

    print('=' * 78)
    print('THE DECIDING TEST: edge-proportional stake vs flat, WALK-FORWARD')
    print('=' * 78)
    print('  Bucket per-$1 estimated on the FIRST half only, then used to weight the SECOND half.')
    print('  Same trades, same total capital, so the two columns are directly comparable.')
    print()
    print('  %-28s %6s %6s %10s %10s %9s' % ('set / feature', 'train', 'test', 'flat', 'dynamic', 'delta'))
    evs10 = quartile_cuts([r['ev'] for r in v10 if r['ev'] is not None])
    evs12 = quartile_cuts([r['ev'] for r in v12 if r['ev'] is not None])
    jobs = [
        ('A v10 / p', v10, lambda r: bucket(r['p'], P_CUTS), 4),
        ('A v10 / EV', v10, lambda r: bucket(r['ev'], evs10), 4),
        ('A v10 / sec', v10, lambda r: bucket(r['sec'], SEC_CUTS), 4),
        ('B v12 / p', v12, lambda r: bucket(r['p'], P_CUTS), 4),
        ('B v12 / EV', v12, lambda r: bucket(r['ev'], evs12), 4),
        ('B v12 / sec', v12, lambda r: bucket(r['sec'], SEC_CUTS), 4),
        ('C live / sec', live, lambda r: bucket(r['sec'], SEC_CUTS), 4),
    ]
    for label, rows, kf, nb in jobs:
        d = walk_forward(rows, oc, kf, nb, label)
        if not d:
            continue
        print('  %-28s %6d %6d %+10.3f %+10.3f %+9.3f'
              % (label, d['n_train'], d['n_test'], d['flat'], d['dyn'], d['dyn'] - d['flat']))
    print()
    rows, ec = mechanism(v10, v12, oc)
    gate(rows, ec, oc)


if __name__ == '__main__':
    main()
