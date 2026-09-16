"""Task R-3: does paying up (padding the signed cap price) buy fills worth having?

Data: analysis/h1/r3_submissions.csv - 189 live submission attempts sent by the AWS session
(it cannot push), md5 970d05b79a424116bec936820152f930, 2026-09-12T14:15Z -> 2026-09-14T13:50Z.

VENUE ATTRIBUTION FIRST (the project's signature error is grading on the wrong venue's oracle).
The CSV carries no venue column, so it is established from the two independent book loggers:
  pre_submit_quote vs polybook.pb ask (1 Hz) : median +0.000, MAD 0.010, 52% inside 1c
  pre_submit_quote vs book1s.b1  ask (1 Hz) : median -0.100, MAD 0.100,  9% inside 1c
  pre_submit_quote vs venues.q poly_* (5 s) : median +0.000, MAD 0.030, 42% inside 1c
  pre_submit_quote vs venues.q pred_* (5 s) : median -0.050, MAD 0.080, 10% inside 1c
The two venues' asks differ by a median 6c over 81,148 paired samples, so the test discriminates.
=> these are POLYMARKET orders => grade on venues.outcome, and pay Polymarket's 7% fee.

Order of work is the one V and the user set: the SELECTION test first. If the rejected candles
lose more than the filled ones at the same paper price, paying up buys losses and the pad grid is
moot.
"""
import csv, os, sqlite3, statistics, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL

H1 = os.path.dirname(os.path.abspath(__file__))
DB = '/tmp/claude-0/db'
RATE = 0.07                      # Polymarket taker fee rate (fee_rate_bps 700), verified exactly


def per1(ask, won):
    """Polymarket PnL per $1 staked at `ask`."""
    return ((1.0 / ask) * (1 - RATE * (1 - ask)) - 1.0) if won else -1.0


def load():
    rows = list(csv.DictReader(open(os.path.join(H1, 'r3_submissions.csv'))))
    for r in rows:
        r['ts'] = int(r['ts_ms'])
        r['epoch'] = int(r['candle_epoch'])
        r['q'] = float(r['pre_submit_quote'])
        r['cap'] = float(r['signed_cap_price'])
        r['tick'] = float(r['tick_size'])
        r['fill'] = float(r['avg_fill_price']) if r['avg_fill_price'] else None
    return rows


def book(name, table):
    c = sqlite3.connect(os.path.join(DB, name + '.sqlite3'))
    idx = {}
    for ts, au, ad in c.execute('select ts_ms,ask_up,ask_dn from %s' % table):
        idx[ts // 1000] = (au, ad)
    return idx


def ask_at(idx, sec, side, window=(0,)):
    for o in window:
        t = idx.get(sec + o)
        if t:
            a = t[0] if side == 'UP' else t[1]
            if a is not None:
                return a
    return None


def summarise(rows, price_of, oracle):
    """win rate and per-$1 for a set of rows, priced by `price_of`."""
    pnl, wins, n = [], 0, 0
    for r in rows:
        a = oracle.get(r['epoch'])
        p = price_of(r)
        if a is None or p is None or p <= 0:
            continue
        won = (r['side'] == a)
        n += 1
        wins += won
        pnl.append(per1(p, won))
    if not n:
        return None
    return dict(n=n, win=wins / n, per1=statistics.fmean(pnl),
                med_price=statistics.median([price_of(r) for r in rows
                                             if oracle.get(r['epoch']) and price_of(r)]))


def halves(rows, price_of, oracle):
    s = sorted(rows, key=lambda r: r['ts'])
    h = len(s) // 2
    a, b = summarise(s[:h], price_of, oracle), summarise(s[h:], price_of, oracle)
    return (a['per1'] if a else float('nan')), (b['per1'] if b else float('nan'))


def main():
    rows = load()
    v = sqlite3.connect(os.path.join(DB, 'venues.sqlite3'))
    oracle = dict(v.execute('select epoch,actual from outcome'))

    b11 = sqlite3.connect(os.path.join(DB, 'build11.sqlite3'))
    binance = {cid // 1000: a for cid, a in
               b11.execute('select candle_id,actual from candles where actual is not null')}

    graded = [r for r in rows if r['epoch'] in oracle]
    print('rows %d, graded on venues.outcome %d (%d candles), ungraded %d'
          % (len(rows), len(graded), len({r['epoch'] for r in graded}), len(rows) - len(graded)))
    print()

    fil = [r for r in graded if r['result'] == 'FILLED']
    rej = [r for r in graded if r['result'] == 'REJECTED']

    # ---------------- TABLE 1: the selection test ----------------
    print('=' * 78)
    print('TABLE 1  REJECTED vs FILLED, both priced at their own paper price')
    print('          (pre_submit_quote), graded on venues.outcome, 7% Polymarket fee')
    print('=' * 78)
    print('  %-10s %5s %8s %9s %9s' % ('set', 'n', 'win%', 'med ask', 'per $1'))
    out = {}
    for name, s in (('FILLED', fil), ('REJECTED', rej), ('ALL', graded)):
        d = summarise(s, lambda r: r['q'], oracle)
        out[name] = d
        print('  %-10s %5d %7.1f%% %9.3f %+9.3f' % (name, d['n'], 100 * d['win'], d['med_price'], d['per1']))
    print()
    for name, s in (('FILLED', fil), ('REJECTED', rej)):
        h1, h2 = halves(s, lambda r: r['q'], oracle)
        print('  %-10s halves  h1 %+.3f / h2 %+.3f' % (name, h1, h2))
    gap = out['REJECTED']['per1'] - out['FILLED']['per1']
    print()
    print('  REJECTED minus FILLED at paper price: %+.3f per $1' % gap)
    print()

    # what the filled set actually paid, vs what it was quoted
    d_paid = summarise([r for r in fil if r['fill']], lambda r: r['fill'], oracle)
    print('  FILLED at the price actually paid (avg_fill_price): n=%d win %.1f%% per $1 %+.3f'
          % (d_paid['n'], 100 * d_paid['win'], d_paid['per1']))
    print('  slippage paid vs quoted, median %+.3f'
          % statistics.median([r['fill'] - r['q'] for r in fil if r['fill']]))
    print()

    # ---------------- verification gate ----------------
    f = Finding('R-3 selection: rejected candles vs filled candles at paper price',
                per_fire=gap, n=out['REJECTED']['n'] + out['FILLED']['n'])
    # Provenance, non-circular: venues.outcome against a Polymarket lane's OWN recorded actual.
    lane = {}
    for n in ('v12_poly_lane', 'v12_poly_weekend', 'v10_poly_long4'):
        c = sqlite3.connect(os.path.join(DB, n + '.sqlite3'))
        cols = [d[1] for d in c.execute('pragma table_info(trades)')]
        if 'actual' in cols:
            lane.update(dict(c.execute(
                'select candle_epoch,actual from trades where actual is not null')))
    f.grading(polymarket_venues_outcome={k: oracle[k] for k in oracle if k in lane},
              polymarket_lane_recorded_actual={k: lane[k] for k in lane if k in oracle})
    f.sample({'FILLED': out['FILLED']['n'], 'REJECTED': out['REJECTED']['n']})
    hr1, hr2 = halves(rej, lambda r: r['q'], oracle)
    f.halves(first=hr1, second=hr2)
    f.quote_age(rule='same-instant', max_age_s=0.0,
                source='pre_submit_quote is the engine\'s own pre-submit read')
    f.verdict()

    # the distortion, shown rather than assumed
    print('  venues.outcome vs candles.actual over the shared candles: they are different oracles.')
    dis = sum(1 for k in set(oracle) & set(binance) if oracle[k] != binance[k])
    print('  disagree on %d/%d (%.1f%%). Polymarket settles on venues.outcome, so that is the one used.'
          % (dis, len(set(oracle) & set(binance)), 100 * dis / len(set(oracle) & set(binance))))
    print('  (same two sets graded on candles.actual - the WRONG oracle for Polymarket - for')
    print('   reference only, to show the size of the error the rule prevents:)')
    for name, s in (('FILLED', fil), ('REJECTED', rej)):
        d = summarise([r for r in s if r['epoch'] in binance], lambda r: r['q'], binance)
        if d:
            print('     %-10s n=%3d win %.1f%% per $1 %+.3f' % (name, d['n'], 100 * d['win'], d['per1']))
    print()

    # ---------------- SECTION 2: how far does the ask move after the signal ----------------
    print('=' * 78)
    print('SECTION 2  ask move after the submission instant, same side')
    print('=' * 78)
    pb = book('polybook', 'pb')
    b1 = book('book1s', 'b1')
    cov_pb = sum(1 for r in rows if ask_at(pb, r['ts'] // 1000, r['side']) is not None)
    print('  logger coverage at the submission second: polybook %d/%d rows, book1s %d/%d'
          % (cov_pb, len(rows),
             sum(1 for r in rows if ask_at(b1, r['ts'] // 1000, r['side']) is not None), len(rows)))
    print('  polybook is the Polymarket book and is the one that covers these rows;')
    print('  book1s is the Predict.fun book and is shown only as the venue control.')
    print('  Both loggers are 1 Hz, so +0.35 s IS NOT RESOLVABLE from them - not reported.')
    print()
    print('  %-6s %5s %9s %9s %9s' % ('lag', 'n', 'median', 'mean', '>=1c up'))
    for lag in (1, 2):
        d = []
        for r in rows:
            s = r['ts'] // 1000
            a0 = ask_at(pb, s, r['side'])
            a1 = ask_at(pb, s + lag, r['side'])
            if a0 is not None and a1 is not None:
                d.append(a1 - a0)
        print('  +%-5ds %5d %+9.4f %+9.4f %8.0f%%'
              % (lag, len(d), statistics.median(d), statistics.fmean(d),
                 100 * sum(1 for x in d if x >= 0.0099) / len(d)))
    print()

    # ---------------- SECTION 3: the pad grid on rejected rows ----------------
    print('=' * 78)
    print('SECTION 3  pad grid on REJECTED rows: cap + k ticks')
    print('=' * 78)
    # Before any grid: is the cap even the binding constraint on a reject?
    binding, notbinding, nobook = [], [], []
    for r in rej:
        a = ask_at(pb, r['ts'] // 1000, r['side'], window=(0, -1, 1, -2, 2))
        r['ask'] = a
        (nobook if a is None else (binding if a > r['cap'] + 1e-9 else notbinding)).append(r)
    okf = sum(1 for r in fil
              if (lambda a: a is not None and a <= r['cap'] + 1e-9)(
                  ask_at(pb, r['ts'] // 1000, r['side'], window=(0, -1, 1, -2, 2))))
    print('  fill model check: of FILLED rows with a book, %d/%d had ask <= cap (model holds)'
          % (okf, sum(1 for r in fil if ask_at(pb, r['ts'] // 1000, r['side'], window=(0, -1, 1, -2, 2)) is not None)))
    print('  of REJECTED rows: %d had ask > cap (a pad COULD have bound),' % len(binding))
    print('                    %d had ask <= cap already (the cap was NOT what rejected them),' % len(notbinding))
    print('                    %d had no book sample.' % len(nobook))
    print('  => the pad can only be tested on the %d cap-binding rejects.' % len(binding))
    print()
    print('  %-6s %5s %9s %9s %9s   %s' % ('pad', 'n fill', 'win%', 'med ask', 'per $1', 'n not filled'))
    grid = []
    for k in (1, 2, 3, 5):
        would = [r for r in binding if r['ask'] is not None and r['ask'] <= r['cap'] + k * r['tick'] + 1e-9]
        d = summarise(would, lambda r: r['ask'], oracle)
        grid.append(d['per1'] if d else float('nan'))
        if d:
            print('  +%-5d %5d %7.1f%% %9.3f %+9.3f   %d'
                  % (k, d['n'], 100 * d['win'], d['med_price'], d['per1'], len(binding) - len(would)))
        else:
            print('  +%-5d %5d        -         -         -   %d' % (k, 0, len(binding)))
    print()
    print('  every cell above is under the %d-fire bar => INSUFFICIENT, do not read the numbers.'
          % MIN_CELL)
    print()

    # ---------------- SECTION 4: the same pad on rows that already filled ----------------
    print('=' * 78)
    print('SECTION 4  the same pad applied to rows that ALREADY filled')
    print('=' * 78)
    print('  A pad only changes an already-filled row if it changes the price paid. On this venue')
    print('  the order is a marketable limit: it fills at the book, not at the cap, so a higher cap')
    print('  does not raise the price paid on a row that was already going to fill.')
    paid_now = summarise([r for r in fil if r['fill']], lambda r: r['fill'], oracle)
    cap_worst = summarise([r for r in fil if r['fill']], lambda r: r['cap'], oracle)
    print('  filled rows, priced at avg_fill_price : n=%d per $1 %+.3f' % (paid_now['n'], paid_now['per1']))
    print('  same rows, priced at the signed cap   : n=%d per $1 %+.3f'
          % (cap_worst['n'], cap_worst['per1']))
    for k in (1, 2, 3, 5):
        d = summarise([r for r in fil if r['fill']], lambda r, k=k: r['fill'] + k * r['tick'], oracle)
        print('  if a +%d tick pad were fully paid : n=%d per $1 %+.3f' % (k, d['n'], d['per1']))
    print()


if __name__ == '__main__':
    main()
