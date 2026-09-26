"""R-18 -- would RESTING limit orders beat the FAK takers we actually send?

User's restated goal (via V, 02:5x): accuracy + PnL (PnL first) + adaptive frequency + no evening
where nearly every trade loses. Premise from my own results: the direction forecast equals the book
(R-13, closed), so the money is in the PRICE PAID. R-14 found the killed orders - the ones whose cap
sat under the ask - would have won 65% against 51% for the fills we pay mid+half-spread for.

We have only ever sent FAK takers at the touch. This simulates the other thing: put the order in the
book at ask - k ticks and let the market come to us.

THE WHOLE QUESTION IS ADVERSE SELECTION, and it is why R-14's 65% is not the answer. A resting buy
fills precisely when the ask falls to meet it, and the ask falls because the market has changed its
mind about our side. So the fills we WOULD have got are a biased sample of the fills we wanted, and
the bias points against us. The grid below therefore never reports a resting arm on its own: every
cell is reported against what the SAME signals did when taken at the touch, and against what they
would have paid if every one of them had filled.

Fill model: our buy limit at `cap` sits in the book from fire second S. It fills at second s in
(S, S+TTL] when the best ask on our side trades down to cap or below (best_ask <= cap), and it fills
at CAP - our own price - not at the lower ask. Book tape is polybook `status='live websocket'`,
1 s snapshots. Grading: venues.outcome, the oracle Polymarket settles on.
"""
import os, sqlite3, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL
import task_r8_taker_feature as R8

DB = '/tmp/claude-0/db'
TICK = 0.01
KS = [0, 1, 2, 3, 4, 5]
TTLS = [15, 30, 60, 120, 299]          # seconds the order rests; 299 = to the candle's end


def book_tape():
    c = sqlite3.connect(os.path.join(DB, 'polybook.sqlite3'))
    tape = {}
    for e, s, au, ad in c.execute(
            "select epoch,sec,ask_up,ask_dn from pb where status='live websocket'"):
        tape.setdefault(int(e), {})[int(s)] = (au, ad)
    return tape


def outcomes():
    v = sqlite3.connect(os.path.join(DB, 'venues.sqlite3'))
    return {int(e): str(a).upper() for e, a in v.execute('select epoch,actual from outcome')}


def fires(tape, oc):
    c = sqlite3.connect(os.path.join(DB, 'poly_pnl.sqlite3'))
    out = []
    for e, ts, side, ask, sec in c.execute(
            'select candle_epoch,ts_ms,side,ask,sec from trades where win is not null'):
        e = int(e)
        if e not in tape or e not in oc or not ask:
            continue
        S = int(sec) if sec is not None else int(ts) // 1000 - e
        if not (0 <= S <= 299):
            continue
        out.append(dict(ep=e, sec=S, side=side, ask=float(ask), actual=oc[e],
                        day=time.strftime('%m-%d', time.gmtime(e))))
    out.sort(key=lambda r: (r['ep'], r['sec']))
    return out


def simulate(r, tape, k, ttl):
    """Returns (filled, fill_price). A resting buy at cap fills at CAP when the ask reaches it."""
    cap = round(r['ask'] - k * TICK, 4)
    if cap <= 0.01:
        return False, None
    if k == 0:
        return True, r['ask']                    # k=0 with any TTL is the taker we send today
    j = 0 if r['side'] == 'UP' else 1
    for s in range(r['sec'] + 1, min(r['sec'] + ttl, 299) + 1):
        q = tape[r['ep']].get(s)
        if q is None:
            continue
        a = q[j]
        if a is not None and np.isfinite(a) and 0 < a <= cap:
            return True, cap
    return False, None


def cell(rows, tape, k, ttl):
    took = [(r, p) for r in rows for f, p in [simulate(r, tape, k, ttl)] if f]
    if not took:
        return None
    pnl = np.array([R8.per1(p, r['side'] == r['actual']) for r, p in took])
    win = np.mean([r['side'] == r['actual'] for r, _ in took])
    return dict(n=len(took), fill=len(took) / len(rows), win=float(win),
                per1=float(pnl.mean()), total=float(pnl.sum()),
                px=float(np.mean([p for _, p in took])),
                eps=[r['ep'] for r, _ in took], pnl=pnl,
                took=took)


def main():
    tape, oc = book_tape(), outcomes()
    rows = fires(tape, oc)
    days = sorted({r['day'] for r in rows})
    print('=' * 104)
    print('R-18  resting limit orders vs the FAK taker we actually send')
    print('=' * 104)
    print('  %d fires have a live 1 s book tape, %d days (%s)' % (len(rows), len(days), ', '.join(days)))
    print('  per day: %s' % '  '.join('%s:%d' % (d, sum(1 for r in rows if r['day'] == d)) for d in days))
    base = cell(rows, tape, 0, 299)
    print('\n  BASELINE, what we do now (k=0, taken at the touch):')
    print('    n=%d  win %.1f%%  per $1 %+.3f  total %+.2f  mean price %.3f'
          % (base['n'], 100 * base['win'], base['per1'], base['total'], base['px']))

    print('\n  GRID: k ticks below the ask x TTL seconds. Cells under %d fills are insufficient.' % MIN_CELL)
    print('  %-4s %-6s %7s %8s %7s %9s %9s %8s' % ('k', 'ttl', 'fills', 'fill%', 'win%', 'per $1', 'total', 'price'))
    grid = {}
    for k in KS:
        for ttl in TTLS:
            c = cell(rows, tape, k, ttl)
            grid[(k, ttl)] = c
            if c is None:
                print('  %-4d %-6d %7d   no fills' % (k, ttl, 0)); continue
            mark = '' if c['n'] >= MIN_CELL else '  insufficient'
            print('  %-4d %-6d %7d %7.1f%% %6.1f%% %+9.3f %+9.2f %8.3f%s'
                  % (k, ttl, c['n'], 100 * c['fill'], 100 * c['win'], c['per1'], c['total'], c['px'], mark))
        print()

    print('  ADVERSE SELECTION, decomposed.')
    print('  THE FIRST VERSION OF THIS TABLE WAS A FAKE PASS and is recorded so it is not rebuilt:')
    print('  it compared the filled orders\' win rate against THE SAME ORDERS taken at the touch,')
    print('  which is the identical row set, so the gap was +0.000 in all 25 cells by construction.')
    print('  Selection is a statement about WHICH signals fill, so the comparison has to be against')
    print('  ALL signals (win %.1f%%), not against the filled ones priced differently.' % (100 * base['win']))
    print('  %-4s %-6s %7s %9s %11s %10s %10s %9s'
          % ('k', 'ttl', 'fills', 'win_rest', 'win_ALL', 'selection', 'price gain', 'net'))
    for k in KS:
        if k == 0:
            continue
        for ttl in TTLS:
            c = grid[(k, ttl)]
            if c is None or c['n'] < MIN_CELL:
                continue
            same = [r for r, _ in c['took']]
            pf = np.mean([R8.per1(r['ask'], r['side'] == r['actual']) for r in same])
            print('  %-4d %-6d %7d %8.1f%% %10.1f%% %+10.3f %+10.3f %+9.3f'
                  % (k, ttl, c['n'], 100 * c['win'], 100 * base['win'],
                     c['win'] - base['win'], c['per1'] - pf, c['per1'] - base['per1']))
    print()
    print('  selection  = win%% of the orders that filled MINUS win%% of every signal we had')
    print('  price gain = what resting k ticks lower is worth on the rows that filled')
    print('  net        = this cell per $1 MINUS the taker baseline per $1')

    print('\n  PER DAY, k=1..3 at TTL=299 (rain or sun; the taker baseline is on the top row)')
    print('  %-14s %s' % ('arm', ''.join('%10s' % d for d in days)))
    def byday(c):
        out = {}
        for (r, p) in c['took']:
            out.setdefault(r['day'], []).append(R8.per1(p, r['side'] == r['actual']))
        return out
    for lbl, c in [('taker k=0', base)] + [('rest k=%d' % k, grid[(k, 299)]) for k in (1, 2, 3)]:
        d = byday(c)
        print('  %-14s %s' % (lbl, ''.join('%10s' % (('%+.3f' % np.mean(d[x])) if x in d and len(d[x]) >= 30
                                                     else 'insuf') for x in days)))

    print()
    a = grid[(1, 299)]
    shared = sorted(set(a['eps']) & set(base['eps']))
    ia = {r['ep']: (r, p) for r, p in a['took']}
    ib = {r['ep']: (r, p) for r, p in base['took']}
    h = len(rows) // 2
    def half_net(sl):
        eps = {r['ep'] for r in rows[sl]}
        x = [R8.per1(p, r['side'] == r['actual']) for r, p in a['took'] if r['ep'] in eps]
        z = [R8.per1(p, r['side'] == r['actual']) for r, p in base['took'] if r['ep'] in eps]
        return (np.mean(x) - np.mean(z)) if (len(x) >= 30 and len(z) >= 30) else float('nan')
    F = Finding('R-18 resting at ask-1 tick (TTL to candle end) vs the FAK taker',
                per_fire=a['per1'] - base['per1'], n=a['n'])
    F.sample({'filled orders': a['n']})
    F.halves(first=half_net(slice(0, h)), second=half_net(slice(h, len(rows))))
    F.paired(mine_right=[ia[e][0]['side'] == ia[e][0]['actual'] for e in shared],
             theirs_right=[ib[e][0]['side'] == ib[e][0]['actual'] for e in shared])
    F.null(mine=a['total'], null_value=base['total'], null_name='the FAK taker TOTAL PnL')
    F.verdict()
    np.save('/tmp/claude-0/r18_grid.npy',
            np.array([{ (k, t): (None if grid[(k, t)] is None else
                        {x: grid[(k, t)][x] for x in ('n', 'fill', 'win', 'per1', 'total', 'px')})
                        for k in KS for t in TTLS }], dtype=object), allow_pickle=True)
    return rows, tape, grid, base


if __name__ == '__main__':
    main()
