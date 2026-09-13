"""Task 20 item 3, continued - re-run Task 16's prior and Task 18's EF-at-Polymarket under NEXT.

Both used an EV filter (p compared directly against the ask), which Task 20 showed is the MAXIMALLY
exposed shape. Task 16's result was already inconclusive and should only get worse. Task 18's
EF-at-Polymarket was POSITIVE (+0.281) and feeds the platform decision, so it is the one that
actually matters here.
"""
import numpy as np, sqlite3, json, sys
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
import task16_market_prior_ef as T
import task18_polymarket_transfer as P
from task20_stale_quote import q_prev, q_next

MARGINS = [0.10, 0.15, 0.20, 0.25, 0.30]


def poly_next(book, S):
    """First Polymarket sample at or after S (the honest rule for a Polymarket trade)."""
    for s in sorted(k for k in book if k >= S):
        a, b = book[s]
        if a is not None and b is not None:
            return a, b, s
    return None, None, None


def show(tag, rows, grading=''):
    if not rows:
        print('  %-30s %s n=   0' % (tag, grading)); return
    pn = np.array([r['pnl'] for r in rows]); h = len(pn) // 2
    flag = '' if len(pn) >= 60 else '  << n<60'
    print('  %-30s %-14s n=%4d hit %4.1f%% per-fire %+7.3f halves %+6.2f/%+6.2f%s'
          % (tag, grading, len(pn), 100 * np.mean([r['hit'] for r in rows]), pn.mean(),
             pn[:h].sum(), pn[h:].sum(), flag))


if __name__ == '__main__':
    d = np.load(f'{T.SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    Pmap = {int(c) // 1000: p for c, p in zip(cids, paths)}
    act, books = T.engine_actual(), T.venue_books()
    eps = sorted(set(books) & set(act) & set(Pmap))
    prior, _ = T.build_prior(paths, cids, min(eps) * 1000)

    print('=' * 104)
    print('A. TASK 16 MARKET PRIOR — EV filter, so maximally exposed. Engine grading.')
    print('=' * 104)
    for margin in MARGINS:
        for rule in ('original', 'next'):
            rows = []
            for ep in eps:
                p_arr, a = Pmap[ep], act[ep]
                for S in T.SECS:
                    op, px = p_arr[0], p_arr[S]
                    side = 'UP' if px >= op else 'DOWN'
                    pr = prior[S][T.bucket(abs(px - op) / op * 1e4)][0]
                    if pr is None:
                        continue
                    if rule == 'original':
                        au, ad, su, sd, _ = q_prev(books[ep], S)
                    else:
                        au, ad, su, sd, _, Sq = q_next(books[ep], S)
                        if Sq is None or Sq >= 300:
                            continue
                    ask = au if side == 'UP' else ad
                    size = su if side == 'UP' else sd
                    if ask is None or not (0.02 < ask < 0.98) or size is None or size * ask < T.MIN_NOTIONAL:
                        continue
                    if pr * (1 / ask) * (1 - T.FEE) - 1 < margin:
                        continue
                    rows.append(dict(hit=(side == a), pnl=T.pnl(side == a, ask)))
                    break
            show('prior m=%.2f %s' % (margin, rule.upper()), rows, '[engine]')

    print()
    print('=' * 104)
    print('B. TASK 18 EF-AT-POLYMARKET — the positive claim that feeds the platform decision.')
    print('   Polymarket asks, 7%% taker fee, graded on POLYMARKET resolution (its settling source).')
    print('=' * 104)
    pb = P.poly_books()
    polyout = dict(sqlite3.connect(f'{T.DBD}/venues.sqlite3').execute('select epoch, actual from outcome'))
    c = sqlite3.connect(f'{T.DBD}/twin_c_thr1.sqlite3')
    cur = {}
    for cid, dirn, feats in c.execute('select candle_id, direction, features from ef_candidates where fired=1'):
        f = json.loads(feats)
        ep, s = cid // 1000, f.get('ef_v11_sec')
        if s is not None:
            cur[ep] = dict(side=dirn, p=f.get('ef_v11_p') or 0.5, S=int(s))
    common = [e for e in cur if e in pb and e in polyout and e in act]
    print('  EF fires with a Polymarket book: %d' % len(common))
    for margin in (0.10, 0.15, 0.25):
        for rule in ('original', 'next'):
            rows = []
            for ep in common:
                S, side, p = cur[ep]['S'], cur[ep]['side'], cur[ep]['p']
                if S >= 300:
                    continue
                if rule == 'original':
                    au, ad = P.poly_at(pb[ep], S)
                else:
                    au, ad, Sq = poly_next(pb[ep], S)
                    if Sq is None or Sq >= 300:
                        continue
                ask = au if side == 'UP' else ad
                if ask is None or not (0.02 < ask < 0.98):
                    continue
                if p * (1 / ask) - 1 - P.POLY_FEE_RATE * (1 - ask) < margin:
                    continue
                rows.append(dict(hit=(side == polyout[ep]), pnl=P.poly_pnl(side == polyout[ep], ask)))
            show('EF@poly m=%.2f %s' % (margin, rule.upper()), rows, '[POLY resolve]')
