"""EF (A) -- the LIVE vs PAPER gap. Is the loss fill price, fill rate, or signal?

Owner (09-22 22:1x): "work on ef i need that signal to work". V's framing: paper says +0.22/$1,
live lost -45.87. This decomposes the difference per candle instead of arguing about it.

METHOD. Live EF fires come from the Zurich journals (`signals.side` + `fills.price` + `results`).
Paper EF fires come from the v10 Polymarket lane (`poly_pnl.trades`). Both are Polymarket, so both
are graded on `venues.outcome` -- never candles.actual (that is the 09-10 cross-venue error).

Candles are split three ways and each part is priced separately, because "the loss" is three
different questions:
  BOTH   - live and paper both fired: same side? same outcome? what did each PAY?  -> fill price
  PAPER  - paper fired, live did not:                                              -> fill rate
  LIVE   - live fired, paper did not:                                              -> extra risk

FEES. Live pays the measured Polymarket fee, 1.67% of shares on winners AND losers (R-30b, verified
pnl - venue_pnl - venue_fees == 0 on every row). Paper's own `pnl` column uses 7%-of-winnings, which
the live journal proves the venue does not charge. So the like-for-like comparison below is done on
GROSS outcomes at each side's own paid ask, and the fee is added back as a separate line.
"""
import os, sqlite3, sys, collections, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
POLY_SHARE_FEE = 0.0167


def gross(ask, won):
    return (1.0 / ask - 1.0) if won else -1.0


def net(ask, won):
    return gross(ask, won) - POLY_SHARE_FEE / ask


def live():
    """Settled live EF fires with the side taken and the price actually paid."""
    out = {}
    for z in ('zurich_v1', 'zurich_2', 'zurich_3'):
        p = os.path.join(D, z + '.sqlite3')
        if not os.path.exists(p):
            continue
        c = sqlite3.connect(p)
        for ep, side, kind, px, spent, actual, g, n, fee in c.execute('''
                select r.epoch, s.side, s.kind, f.price, f.spent, r.actual,
                       r.pnl, r.venue_pnl, r.venue_fees
                from results r
                left join signals s on s.epoch = r.epoch
                left join fills   f on f.epoch = r.epoch
                where r.pnl is not null'''):
            if kind and kind != 'EF':
                continue
            if px is None or side is None:
                continue
            out[int(ep)] = dict(ep=int(ep), side=side, ask=float(px), actual=actual,
                                gross=float(g), net=float(n if n is not None else g),
                                fee=float(fee or 0.0), stake=float(spent or 0.0), src=z)
    return out


def paper():
    out = {}
    c = sqlite3.connect(os.path.join(D, 'poly_pnl.sqlite3'))
    for ep, side, ask, sec, actual, win in c.execute(
            'select candle_epoch,side,ask,sec,actual,win from trades where win is not null'):
        if not ask:
            continue
        out[int(ep)] = dict(ep=int(ep), side=side, ask=float(ask), sec=sec,
                            actual=actual, win=int(win))
    return out


def blk(rows, keyask, keywon):
    if not rows:
        return None
    g = np.array([gross(keyask(r), keywon(r)) for r in rows])
    nt = np.array([net(keyask(r), keywon(r)) for r in rows])
    return len(rows), float(np.mean([keywon(r) for r in rows])), float(g.mean()), float(nt.mean()), \
        float(np.mean([keyask(r) for r in rows]))


def main():
    L, P = live(), paper()
    # THE WINDOW MUST BE THE INTERSECTION, NOT THE PAPER SPAN. Paper ran 09-08 -> 09-16; live only
    # from 09-15. Comparing live against all of paper's fires counts ~6 days when live was not
    # running at all and inflates "fires live missed" from a real number into a meaningless one.
    lo = max(min(L), min(P))
    hi = min(max(L), max(P))
    Lw = {e: v for e, v in L.items() if lo <= e <= hi}
    Pw = {e: v for e, v in P.items() if lo <= e <= hi}
    P = Pw
    pmin, pmax = lo, hi

    both = sorted(set(Lw) & set(Pw))
    ponly = sorted(set(Pw) - set(Lw))
    lonly = sorted(set(Lw) - set(Pw))

    print('EF (A)  LIVE vs PAPER, per candle')
    print('  live EF fires %d (%s -> %s); paper fires %d (%s -> %s)'
          % (len(L), dt.datetime.utcfromtimestamp(min(L)), dt.datetime.utcfromtimestamp(max(L)),
             len(P), dt.datetime.utcfromtimestamp(pmin), dt.datetime.utcfromtimestamp(pmax)))
    print('  OVERLAP WINDOW (intersection, not the paper span): %s -> %s'
          % (dt.datetime.utcfromtimestamp(lo), dt.datetime.utcfromtimestamp(hi)))
    print('  in that window: live fired %d, paper fired %d (live %d of %d total excluded as outside)'
          % (len(Lw), len(Pw), len(L) - len(Lw), len(L)))
    print('  BOTH fired %d | PAPER only %d | LIVE only %d' % (len(both), len(ponly), len(lonly)))

    print('\n  1. SIGNAL -- on the %d shared candles, did live and paper pick the SAME SIDE?' % len(both))
    same = [e for e in both if L[e]['side'] == P[e]['side']]
    print('     same side %d/%d = %.1f%%' % (len(same), len(both), 100.0 * len(same) / len(both)))
    lw = sum(1 for e in both if L[e]['side'] == L[e]['actual'])
    pw = sum(1 for e in both if P[e]['side'] == P[e]['actual'])
    print('     live right %d/%d = %.1f%%   paper right %d/%d = %.1f%%'
          % (lw, len(both), 100.0 * lw / len(both), pw, len(both), 100.0 * pw / len(both)))

    print('\n  2. FILL PRICE -- on the shared candles, what did each PAY?')
    dl = np.array([L[e]['ask'] for e in both]); dp = np.array([P[e]['ask'] for e in both])
    print('     live mean ask %.4f   paper mean ask %.4f   live pays %+.4f more (median %+.4f)'
          % (dl.mean(), dp.mean(), (dl - dp).mean(), float(np.median(dl - dp))))

    print('\n  3. THE MONEY, same candles, each at its own paid ask')
    print('     %-22s %5s %7s %10s %10s %9s' % ('arm', 'n', 'W%', 'gross/$1', 'net/$1', 'mean ask'))
    for lab, rows, ka, kw in (
            ('live (as filled)', [L[e] for e in both], lambda r: r['ask'], lambda r: r['side'] == r['actual']),
            ('paper (same candles)', [P[e] for e in both], lambda r: r['ask'], lambda r: r['side'] == r['actual']),
            ('live side @ paper ask', [dict(L[e], ask=P[e]['ask']) for e in both], lambda r: r['ask'], lambda r: r['side'] == r['actual']),
            ('paper side @ live ask', [dict(P[e], ask=L[e]['ask']) for e in both], lambda r: r['ask'], lambda r: r['side'] == r['actual'])):
        s = blk(rows, ka, kw)
        print('     %-22s %5d %6.1f%% %+10.4f %+10.4f %9.4f%s'
              % (lab, s[0], 100 * s[1], s[2], s[3], s[4],
                 '' if s[0] >= MIN_CELL else '  INSUFFICIENT'))

    print('\n  4. FILL RATE -- the %d candles paper took and live did NOT' % len(ponly))
    s = blk([P[e] for e in ponly], lambda r: r['ask'], lambda r: r['side'] == r['actual'])
    if s:
        print('     %5d %6.1f%% gross %+.4f net %+.4f mean ask %.4f%s'
              % (s[0], 100 * s[1], s[2], s[3], s[4], '' if s[0] >= MIN_CELL else '  INSUFFICIENT'))
        print('     -> these are the fires live MISSED. Positive here means the misses cost money.')
    s = blk([L[e] for e in lonly], lambda r: r['ask'], lambda r: r['side'] == r['actual'])
    if s:
        print('  5. LIVE ONLY -- %d candles live took and paper did not' % len(lonly))
        print('     %5d %6.1f%% gross %+.4f net %+.4f mean ask %.4f%s'
              % (s[0], 100 * s[1], s[2], s[3], s[4], '' if s[0] >= MIN_CELL else '  INSUFFICIENT'))

    print('\n  6. THE LIVE ACCOUNT, all %d settled EF fires, from the journal\'s own columns' % len(L))
    G = sum(v['gross'] for v in L.values()); N = sum(v['net'] for v in L.values())
    FE = sum(v['fee'] for v in L.values()); ST = sum(v['stake'] for v in L.values())
    print('     gross %+.2f  fees %.2f  NET %+.2f  staked %.2f  -> net %.2f%% of stake'
          % (G, FE, N, ST, 100 * N / ST))


if __name__ == '__main__':
    main()


def diagnose():
    """Why do live and paper barely overlap, and is the shared-candle gap real or 3 coin flips?"""
    from scipy.stats import binomtest
    L, P = live(), paper()
    lo, hi = max(min(L), min(P)), min(max(L), max(P))
    Lw = {e: v for e, v in L.items() if lo <= e <= hi}
    Pw = {e: v for e, v in P.items() if lo <= e <= hi}
    both = sorted(set(Lw) & set(Pw))

    print('\n  7. PAIRED TEST on the %d shared candles (only DISCORDANT pairs carry information)' % len(both))
    lr = [Lw[e]['side'] == Lw[e]['actual'] for e in both]
    pr = [Pw[e]['side'] == Pw[e]['actual'] for e in both]
    a = sum(1 for x, y in zip(lr, pr) if x and not y)
    b = sum(1 for x, y in zip(lr, pr) if y and not x)
    print('     live right / paper wrong: %d      paper right / live wrong: %d      discordant: %d'
          % (a, b, a + b))
    if a + b:
        p = binomtest(a, a + b, 0.5).pvalue
        print('     exact McNemar p = %.3f on %d discordant pairs%s'
              % (p, a + b, '' if a + b >= MIN_CELL else
                 '   -- %d pairs is far under the %d bar: THE SHARED-CANDLE GAP IS NOT A FINDING'
                 % (a + b, MIN_CELL)))
    print('     The whole live-vs-paper per-$1 gap on shared candles (+0.038 vs +0.127) is these')
    print('     %d candles. At a ~0.43 ask each flip moves the mean by ~1/0.43/%d = %.3f.'
          % (a + b, len(both), (1 / 0.43) / len(both)))

    print('\n  8. WHY THE FIRE SETS DIFFER -- live took %d, paper took %d, only %d shared'
          % (len(Lw), len(Pw), len(both)))
    print('     %-14s %5s %9s %9s' % ('group', 'n', 'mean ask', 'mean sec'))
    for lab, rows, asec in (('both (live)', [Lw[e] for e in both], None),
                            ('both (paper)', [Pw[e] for e in both], 'sec'),
                            ('paper only', [Pw[e] for e in sorted(set(Pw) - set(Lw))], 'sec'),
                            ('live only', [Lw[e] for e in sorted(set(Lw) - set(Pw))], None)):
        sec = np.mean([r['sec'] for r in rows if r.get('sec') is not None]) if asec else float('nan')
        print('     %-14s %5d %9.4f %9s' % (lab, len(rows), np.mean([r['ask'] for r in rows]),
                                            ('%.0f' % sec) if sec == sec else '-'))
    print('     Live fired on %.0f%% of the candles paper fired on. They are not the same rule'
          % (100.0 * len(both) / len(Pw)))
    print('     running twice -- any "paper says +0.22" number is measuring different trades.')


if __name__ == '__main__':
    diagnose()
