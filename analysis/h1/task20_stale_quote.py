"""Task 20 (V, URGENT) - is the 11.2 replay a stale-quote artifact?

V's charge: the replay reads the price path at second S (fresh) but pays an ask forward-filled from
a collector sample up to 5 s EARLIER (pre-move). If so the model buys at prices that no longer
existed, and the +0.266 is look-ahead in the COST rather than skill in the signal.

Three quote rules, same fire logic, same grading (engine candles):

  ORIGINAL  quote = last sample with sec <= S     (what the replay did; quote age 0-5 s, unknown)
  NEXT      quote = first sample with sec >= S    (quote at or AFTER the price observation)
  STRICT    quote = first sample with sec >= S, AND the features are recomputed at that sample's
            own second, so observation and quote are the same instant. No look-ahead anywhere.

Reports the full margin sweep for all three, plus which fires vanish and what they were worth.
"""
import numpy as np, sqlite3, sys, joblib, json
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1/models')
import task16_market_prior_ef as T, task11_2_direction_model as M
from ef11_2_predict import feats_at, SECS, EV_MARGIN

MARGINS = [0.10, 0.15, 0.20, 0.25, 0.30]


def q_prev(book, S):
    """ORIGINAL: last sample at or before S, each field forward-filled. Age 0-5 s, unknown."""
    au = ad = su = sd = None; age = None
    for s in sorted(k for k in book if k <= S):
        a, b, c, d = book[s]
        if a is not None: au = a
        if b is not None: ad = b
        if c is not None: su = c
        if d is not None: sd = d
        age = S - s
    return au, ad, su, sd, age


def q_next(book, S):
    """NEXT: first sample at or after S."""
    for s in sorted(k for k in book if k >= S):
        a, b, c, d = book[s]
        if a is not None and b is not None:
            return a, b, c, d, s - S, s
    return None, None, None, None, None, None


def run(rule, margin, m, Pmap, act, books, t12, idx, eps):
    out = []
    for ep in eps:
        i = idx.get(ep)
        if i is None or np.isnan(t12[i]):
            continue
        p_arr, a = Pmap[ep], act[ep]
        for S in SECS:
            if rule == 'original':
                au, ad, su, sd, age = q_prev(books[ep], S)
                Sobs = S
            else:
                au, ad, su, sd, age, Sq = q_next(books[ep], S)
                if au is None or Sq is None or Sq >= 300:
                    continue
                Sobs = Sq if rule == 'strict' else S
            if au is None or ad is None:
                continue
            pu = float(m.predict_proba(feats_at(p_arr, Sobs, t12[i]).reshape(1, -1))[0, 1])
            side = 'UP' if pu >= 0.5 else 'DOWN'
            p = pu if side == 'UP' else 1 - pu
            ask = au if side == 'UP' else ad
            size = su if side == 'UP' else sd
            if ask is None or not (0.02 < ask < 0.98) or size is None or size * ask < T.MIN_NOTIONAL:
                continue
            if p * (1 / ask) * (1 - T.FEE) - 1 < margin:
                continue
            out.append(dict(ep=ep, S=S, side=side, ask=ask, hit=(side == a),
                            pnl=T.pnl(side == a, ask)))
            break
    return out


def show(tag, rows):
    if not rows:
        print('  %-26s n=   0' % tag); return
    pn = np.array([r['pnl'] for r in rows]); h = len(pn) // 2
    flag = '' if len(pn) >= 60 else '  << n<60'
    print('  %-26s n=%4d  hit %4.1f%%  per-fire %+7.3f  total %+8.2f  halves %+6.2f/%+6.2f  ask~%.2f%s'
          % (tag, len(pn), 100 * np.mean([r['hit'] for r in rows]), pn.mean(), pn.sum(),
             pn[:h].sum(), pn[h:].sum(), np.median([r['ask'] for r in rows]), flag))


if __name__ == '__main__':
    m = joblib.load('/home/user/Django-final-project/analysis/h1/models/ef11_2_gbm_seed0.joblib')
    d = np.load(f'{T.SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    Pmap = {int(c) // 1000: p for c, p in zip(cids, paths)}
    act, books = T.engine_actual(), T.venue_books()
    eps = sorted(set(books) & set(act) & set(Pmap))
    t12 = M.trailing12(paths, paths[:, 0]); idx = {int(c) // 1000: i for i, c in enumerate(cids)}
    print('eval candles: %d' % len(eps))

    # how different are the two quotes, on the same candles/seconds?
    diffs, ages = [], []
    for ep in eps:
        for S in SECS:
            a1, b1, _, _, ag = q_prev(books[ep], S)
            a2, b2, _, _, ag2, _ = q_next(books[ep], S)
            if a1 and a2:
                diffs.append(a2 - a1); ages.append(ag if ag is not None else np.nan)
    diffs = np.array(diffs)
    print('UP ask, NEXT minus ORIGINAL: mean %+.4f  median %+.4f  |diff|>0.05 on %.1f%% of samples'
          % (diffs.mean(), np.median(diffs), 100 * np.mean(np.abs(diffs) > 0.05)))
    print('ORIGINAL quote age (s): median %.1f  p90 %.1f' % (np.nanmedian(ages), np.nanpercentile(ages, 90)))

    print()
    print('=' * 118)
    print('11.2 REPLAY UNDER THREE QUOTE RULES (engine grading, same fire logic)')
    print('=' * 118)
    keep = {}
    for margin in MARGINS:
        print('-- EV margin %.2f' % margin)
        for rule in ('original', 'next', 'strict'):
            rows = run(rule, margin, m, Pmap, act, books, t12, idx, eps)
            show(rule.upper(), rows)
            keep[(margin, rule)] = rows
        o = {r['ep'] for r in keep[(margin, 'original')]}
        s = {r['ep'] for r in keep[(margin, 'strict')]}
        gone = [r for r in keep[(margin, 'original')] if r['ep'] not in s]
        if gone:
            g = np.array([r['pnl'] for r in gone])
            print('     fires that VANISH under STRICT: %d of %d, worth %+.2f (%+.3f/fire) in the original'
                  % (len(gone), len(o), g.sum(), g.mean()))
