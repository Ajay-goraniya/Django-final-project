"""Task 16 (V, 01:05) - the market-prior EF replay: the baseline 11.2 must beat.

Rule under test, fully specified by V, nothing hand-tuned. At each decision second S:
  side   = the side price is on at S (from the Binance kline path)
  p      = P(same side | S, |price(S)-open| bucket), the Task 15 part 2 prior, estimated ONLY on
           candles BEFORE the venue window (walk-forward - the prior never sees the eval candles)
  ask    = the recorded raw Predict.fun ask for that side at S (skip if missing, or notional < $10)
  fire  iff p*(1/ask)*(1-fee) - 1 >= margin, at the FIRST S that clears; one fire per candle.

Grading: the engine's own `candles` table from the snapshots (close >= open), which is what
Predict.fun settles on. NEVER the venues `outcome` table (that is Polymarket's oracle).
"""
import sqlite3, json, numpy as np

DBD = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad/db'
SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
FEE, EV_MARGINS = 0.02, [0.15, 0.20, 0.25, 0.30, 0.40]
SECS = [15, 20, 30, 45, 60, 90, 120]
EDGES = [0, 1, 2.5, 5, 10, 25, np.inf]
LBL = ['<1', '1-2.5', '2.5-5', '5-10', '10-25', '25+']
MIN_NOTIONAL = 10.0


def bucket(b):
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= b < EDGES[i + 1]:
            return i
    return len(LBL) - 1


def engine_actual():
    out = {}
    for f in ('build11.sqlite3', 'predict_pnl.sqlite3', 'twin_c_thr1.sqlite3'):
        c = sqlite3.connect(f'{DBD}/{f}')
        for cid, o, cl in c.execute('select candle_id, open, close from candles'):
            if o:
                out[cid // 1000] = 'UP' if cl >= o else 'DOWN'
    return out


def venue_books():
    """epoch -> {sec: (ask_up, ask_dn, size_up, size_dn)}"""
    c = sqlite3.connect(f'{DBD}/venues.sqlite3')
    q = {}
    for ep, sec, yu, yd, su, sd in c.execute(
            'select epoch, sec, pred_up, pred_dn, pred_size_up, pred_size_dn from q order by epoch, sec'):
        q.setdefault(ep, {})[sec] = (yu, yd, su, sd)
    return q


def book_at(book, S):
    """Forward-fill each field independently up to second S."""
    au = ad = su = sd = None
    for s in sorted(k for k in book if k <= S):
        a, b, c, d = book[s]
        if a is not None: au = a
        if b is not None: ad = b
        if c is not None: su = c
        if d is not None: sd = d
    return au, ad, su, sd


def build_prior(paths, cids, before_ms):
    """P(close on the side price is on at S | S, bucket), from candles strictly before the window."""
    m = cids < before_ms
    P = paths[m]
    op, cl = P[:, 0], P[:, -1]
    up = cl >= op
    prior = {}
    for S in SECS:
        px = P[:, S]
        bps = np.abs(px - op) / op * 1e4
        same = (px >= op) == up
        prior[S] = {}
        for i in range(len(LBL)):
            sel = (bps >= EDGES[i]) & (bps < EDGES[i + 1])
            prior[S][i] = (float(same[sel].mean()), int(sel.sum())) if sel.sum() >= 60 else (None, int(sel.sum()))
    return prior, int(m.sum())


def pnl(hit, ask):
    return ((1 / ask) * (1 - FEE) - 1) if hit else -1.0


def replay(eps, P, act, books, prior, margin, use_model_p=None):
    """One fire per candle at the first S whose EV clears `margin`."""
    out = []
    for ep in eps:
        p_arr, a = P.get(ep), act.get(ep)
        if p_arr is None or a is None or ep not in books:
            continue
        for S in SECS:
            op, px = p_arr[0], p_arr[S]
            side = 'UP' if px >= op else 'DOWN'
            bi = bucket(abs(px - op) / op * 1e4)
            p = prior[S][bi][0] if use_model_p is None else use_model_p.get(ep)
            if p is None:
                continue
            au, ad, su, sd = book_at(books[ep], S)
            ask = au if side == 'UP' else ad
            size = su if side == 'UP' else sd
            if ask is None or not (0.02 < ask < 0.98):
                continue
            if size is None or size * ask < MIN_NOTIONAL:
                continue
            if p * (1 / ask) * (1 - FEE) - 1 < margin:
                continue
            out.append(dict(ep=ep, S=S, side=side, ask=ask, bi=bi, hit=(side == a),
                            pnl=pnl(side == a, ask)))
            break
    return out


def summarise(tag, rows, show_profile=False):
    if not rows:
        print('  %-30s n=0' % tag); return
    pn = np.array([r['pnl'] for r in rows])
    h = len(pn) // 2
    flag = '' if len(rows) >= 60 else '  << n<60'
    print('  %-30s n=%4d  hit %4.1f%%  per-fire %+7.3f  total %+8.2f  halves %+7.2f/%+7.2f  ask~%.2f%s'
          % (tag, len(rows), 100 * np.mean([r['hit'] for r in rows]), pn.mean(), pn.sum(),
             pn[:h].sum(), pn[h:].sum(), np.median([r['ask'] for r in rows]), flag))
    if show_profile:
        print('      distance profile of fires: ', end='')
        for i, l in enumerate(LBL):
            c = [r for r in rows if r['bi'] == i]
            if c:
                print('%s %.0f%% (%+.2f)  ' % (l, 100 * len(c) / len(rows), np.mean([r['pnl'] for r in c])), end='')
        print()


if __name__ == '__main__':
    d = np.load(f'{SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    P = {int(c) // 1000: p for c, p in zip(cids, paths)}
    act, books = engine_actual(), venue_books()
    eps = sorted(set(books) & set(act) & set(P))
    win_start = min(eps) * 1000
    prior, n_prior = build_prior(paths, cids, win_start)
    print('eval candles (venue x engine x kline): %d   prior trained on %d earlier candles' % (len(eps), n_prior))
    print('prior P(same side) at S=20: ' + '  '.join(
        '%s=%s' % (LBL[i], ('%.3f' % prior[20][i][0]) if prior[20][i][0] else 'n/a') for i in range(len(LBL))))

    # comparator (a): the current EF fire set, at its own recorded ask
    c = sqlite3.connect(f'{DBD}/twin_c_thr1.sqlite3')
    cur = []
    model_p = {}
    for cid, dirn, feats in c.execute('select candle_id, direction, features from ef_candidates where fired=1'):
        f = json.loads(feats)
        ep, ask, p = cid // 1000, f.get('ef_v11_ask'), f.get('ef_v11_p')
        if ep in act and ask and 0.02 < ask < 0.98:
            model_p[ep] = p
            bi = bucket(abs(f.get('ef_v11_f', {}).get('move_bps', 0.0)))
            cur.append(dict(ep=ep, S=f.get('ef_v11_sec'), side=dirn, ask=ask, bi=bi,
                            hit=(dirn == act[ep]), pnl=pnl(dirn == act[ep], ask)))

    print()
    print('=' * 118)
    print('THE MARKET-PRIOR RULE, EV margin sweep (full curve, never one cell)')
    print('=' * 118)
    for m in EV_MARGINS:
        summarise('prior, margin %.2f' % m, replay(eps, P, act, books, prior, m), show_profile=(m == 0.25))

    print()
    print('=' * 118)
    print('COMPARATORS on the same candle set')
    print('=' * 118)
    summarise('(a) CURRENT EF fire set', cur, show_profile=True)
    for m in EV_MARGINS:
        summarise('(b) model p, margin %.2f' % m, replay(eps, P, act, books, prior, m, use_model_p=model_p))
    naive = []
    for ep in eps:
        p_arr, a = P.get(ep), act.get(ep)
        if p_arr is None or a is None:
            continue
        op, px = p_arr[0], p_arr[20]
        side = 'UP' if px >= op else 'DOWN'
        au, ad, su, sd = book_at(books[ep], 20)
        ask = au if side == 'UP' else ad
        if ask and 0.02 < ask < 0.98:
            naive.append(dict(ep=ep, S=20, side=side, ask=ask, bi=bucket(abs(px - op) / op * 1e4),
                              hit=(side == a), pnl=pnl(side == a, ask)))
    summarise('(c) NAIVE null: every candle S=20', naive, show_profile=True)
