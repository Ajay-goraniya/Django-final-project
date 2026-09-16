"""Task 20 item 3 - does candidate J have the same stale-quote exposure?

J: a second EF entry at t~120 s, on EF's OWN side, only if that side's ask is still <= cap.
It is not an EV filter, but it still SELECTS ON CHEAPNESS (ask <= cap), which is the exact
mechanism that inflated 11.2: among stale quotes the rule preferentially takes the randomly low
ones. So J has the same exposure and must be re-run the same way.

Important context that 11.2 did NOT have: V replayed J against Tokyo's REAL FILLS and got
+0.153/fire on 128 fills. Real fills are unaffected by this artifact. So if the recorded-quote
version collapses, the real-fill evidence is what J actually rests on.
"""
import numpy as np, sqlite3, json, sys
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import task16_market_prior_ef as T
from task20_stale_quote import q_prev, q_next

T_J = 120
CAPS = [0.50, 0.55, 0.60, 0.65, 0.70, None]


def run(rule, cap, ef, act, books):
    out = []
    for ep, side in ef.items():
        if ep not in books or ep not in act:
            continue
        if rule == 'original':
            au, ad, su, sd, age = q_prev(books[ep], T_J)
        else:
            au, ad, su, sd, age, Sq = q_next(books[ep], T_J)
            if Sq is None or Sq >= 300:
                continue
        ask = au if side == 'UP' else ad
        size = su if side == 'UP' else sd
        if ask is None or not (0.02 < ask < 0.98):
            continue
        if size is None or size * ask < T.MIN_NOTIONAL:
            continue
        if cap is not None and ask > cap:
            continue
        out.append(dict(ep=ep, ask=ask, hit=(side == act[ep]), pnl=T.pnl(side == act[ep], ask)))
    return out


def show(tag, rows):
    if not rows:
        print('  %-24s n=   0' % tag); return
    pn = np.array([r['pnl'] for r in rows]); h = len(pn) // 2
    flag = '' if len(pn) >= 60 else '  << n<60'
    print('  %-24s n=%4d  hit %4.1f%%  per-fire %+7.3f  total %+8.2f  halves %+6.2f/%+6.2f  ask~%.2f%s'
          % (tag, len(pn), 100 * np.mean([r['hit'] for r in rows]), pn.mean(), pn.sum(),
             pn[:h].sum(), pn[h:].sum(), np.median([r['ask'] for r in rows]), flag))


if __name__ == '__main__':
    act, books = T.engine_actual(), T.venue_books()
    ef = {}
    for db in ('twin_c_thr1.sqlite3', 'build11.sqlite3'):
        c = sqlite3.connect(f'{T.DBD}/{db}')
        for cid, dirn in c.execute('select candle_id, direction from ef_predictions'):
            ef.setdefault(cid // 1000, dirn)
    print('EF first-fire candles available: %d' % len(ef))
    print('Candidate J = second entry at t=%d s on EF\'s own side, ask <= cap. Engine grading.' % T_J)
    print()
    print('=' * 112)
    print('CANDIDATE J UNDER THE TWO QUOTE RULES (STRICT is not separable here: the rule has no')
    print('model features, so NEXT already removes the look-ahead)')
    print('=' * 112)
    for cap in CAPS:
        lbl = 'no cap' if cap is None else 'cap %.2f' % cap
        print('-- %s' % lbl)
        o = run('original', cap, ef, act, books)
        n = run('next', cap, ef, act, books)
        show('ORIGINAL (<=120s ffill)', o)
        show('NEXT (>=120s)', n)
        so = {r['ep'] for r in o}; sn = {r['ep'] for r in n}
        gone = [r for r in o if r['ep'] not in sn]
        if gone:
            g = np.array([r['pnl'] for r in gone])
            print('     fires that VANISH under NEXT: %d of %d, worth %+.2f (%+.3f/fire)'
                  % (len(gone), len(o), g.sum(), g.mean()))
