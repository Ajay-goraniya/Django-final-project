"""Late REVERSAL (240-285 s): is the ask real, or dust on a one-sided book?

V (09-22 23:3x): the executor refuses after 240 s (poly_core.Executor.fire deadline), but REVERSAL
calls to 285 s, and the replay says that bucket is ~half of REVERSAL's profit at ask 0.12-0.26.
If those asks are dust, the profit is not collectable and the deadline is protecting the engine.

DEPTH SOURCE: `book1s.b1` (ts_ms, epoch, sec, ask_up/size_up/age_up, ask_dn/size_dn/age_dn),
1 Hz, 09-11 02:01 -> 09-16 17:27, 363,069 rows with both sides quoted and sized.
Cross-checked against `polybook.pb`, an independent 1 Hz logger that also carries bids.

STATED LIMIT, up front: b1 stores TOP-OF-BOOK size only. V asked for depth "at or under ask+0.01";
there is no ladder in any file I hold, so I test the strictly weaker condition -- size AT the touch.
A fire that fails this fails outright; one that passes might still be thin one tick deeper. So the
pass rate below is an UPPER bound on fillability, and I say so rather than implying a ladder exists.

Fires come from my own full-span replay (analysis/v/model/replay_lanes_1s.py over 09-08 -> 09-16).
"""
import csv, os, sqlite3, sys, collections
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import Finding, MIN_CELL
import r12_train as T

D = os.path.join(T.SP, 'db')
CSVP = os.path.join(T.SP, 'ef_full.csv')
FEE = 0.0167
MIN_SHARES, MIN_DOLLARS, TOL_S = 5.0, 5.0, 2.0


def per1(ask, won, haircut=0.0):
    a = min(0.98, ask + haircut)
    return (1.0 / a - 1.0 - FEE / a) if won else -1.0


def fires(kind='REVERSAL'):
    out = []
    with open(CSVP) as f:
        for r in csv.DictReader(f):
            if r['kind'] != kind or r['win'] == '':
                continue
            out.append(dict(ep=int(r['epoch']), ts=int(r['ts']), sec=int(r['sec']),
                            side=r['side'], ask=float(r['ask']), win=int(r['win'])))
    out.sort(key=lambda r: r['ts'])
    return out


def book_at(c, ep, sec):
    """Nearest 1 Hz book row within TOL_S of the fire second, same candle."""
    lo, hi = (ep + sec - TOL_S) * 1000, (ep + sec + TOL_S) * 1000
    r = c.execute('''select ask_up,size_up,ask_dn,size_dn,age_up,age_dn,sec from b1
                     where epoch=? and ts_ms between ? and ?
                     order by abs(ts_ms-?) limit 1''', (ep, lo, hi, (ep + sec) * 1000)).fetchone()
    return r


def stat(rows, haircut=0.0):
    if not rows:
        return None
    v = np.array([per1(r['ask'], r['win'] == 1, haircut) for r in rows])
    return len(rows), float(np.mean([r['win'] for r in rows])), float(v.mean()), float(v.sum())


def halves(rows):
    g = sorted(rows, key=lambda r: r['ts'])
    h = len(g) // 2
    return stat(g[:h]), stat(g[h:])


def main():
    R = fires('REVERSAL')
    c = sqlite3.connect(os.path.join(D, 'book1s.sqlite3'))
    bmin, bmax = c.execute('select min(epoch),max(epoch) from b1').fetchone()
    late = [r for r in R if 240 <= r['sec'] <= 285]
    early = [r for r in R if r['sec'] < 240]
    print('LATE REVERSAL DEPTH CHECK')
    print('  REVERSAL fires %d (early <240s: %d, late 240-285s: %d)' % (len(R), len(early), len(late)))
    s = stat(late); e = stat(early)
    print('  late  : n=%-3d hit %.1f%% per$1 %+.4f total %+.2f  ask med %.3f'
          % (s[0], 100 * s[1], s[2], s[3], float(np.median([r['ask'] for r in late]))))
    print('  early : n=%-3d hit %.1f%% per$1 %+.4f total %+.2f' % (e[0], 100 * e[1], e[2], e[3]))

    inb = [r for r in late if bmin <= r['ep'] <= bmax]
    print('\n  book1s covers %d of the %d late fires (the rest predate the book log)'
          % (len(inb), len(late)))

    cats = collections.Counter()
    ok, fail = [], []
    for r in inb:
        b = book_at(c, r['ep'], r['sec'])
        if not b:
            cats['no book row within %.0fs' % TOL_S] += 1
            continue
        au, su, ad, sd, agu, agd, bsec = b
        side_ask = au if r['side'] == 'UP' else ad
        side_sz = su if r['side'] == 'UP' else sd
        other = ad if r['side'] == 'UP' else au
        if side_ask is None or side_sz is None:
            cats['side not quoted'] += 1; continue
        if other is None:
            cats['ONE-SIDED book'] += 1; continue
        if side_sz < MIN_SHARES:
            cats['< %.0f shares at the touch' % MIN_SHARES] += 1; fail.append(r); continue
        if side_sz * side_ask < MIN_DOLLARS:
            cats['< $%.0f notional' % MIN_DOLLARS] += 1; fail.append(r); continue
        r['bsz'], r['bask'] = side_sz, side_ask
        ok.append(r)
    print('\n  WHY LATE FIRES FAIL A REAL-DEPTH TEST (top-of-book only, upper bound)')
    for k, v in cats.most_common():
        print('    %-34s %4d' % (k, v))
    print('    %-34s %4d' % ('PASS: two-sided, >=5 sh, >=$5', len(ok)))

    print('\n  PER $1 BEFORE AND AFTER REQUIRING REAL DEPTH')
    print('  %-34s %5s %7s %9s %10s' % ('bucket', 'n', 'hit', 'per$1', 'total'))
    for lab, g in (('late 240-285, all', late), ('late, inside book coverage', inb),
                   ('late, PASSES depth test', ok), ('late, FAILS depth test', fail)):
        t = stat(g)
        if not t:
            print('  %-34s %5d   (empty)' % (lab, 0)); continue
        print('  %-34s %5d %6.1f%% %+9.4f %+10.2f%s'
              % (lab, t[0], 100 * t[1], t[2], t[3],
                 '' if t[0] >= MIN_CELL else '   INSUFFICIENT (<%d)' % MIN_CELL))

    if ok:
        print('\n  median size at the touch on passing fires: %.1f shares ($%.2f)'
              % (float(np.median([r['bsz'] for r in ok])),
                 float(np.median([r['bsz'] * r['bask'] for r in ok]))))
        a, b2 = halves(ok)
        print('  halves: %+.4f / %+.4f' % (a[2], b2[2]))
        F = Finding('late REVERSAL 240-285s after a real-depth requirement',
                    per_fire=stat(ok)[2], n=len(ok))
        F.sample({'late passing depth': len(ok)})
        F.halves(a[2], b2[2])
        F.costs({0.0: stat(ok)[2], 0.02: stat(ok, 0.02)[2], 0.05: stat(ok, 0.05)[2]})
        F.null(stat(ok)[2], stat(early)[2], 'REVERSAL before 240s')
        print()
        print('VERDICT', F.verdict())


if __name__ == '__main__':
    main()
