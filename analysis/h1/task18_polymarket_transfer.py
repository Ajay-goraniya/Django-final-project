"""Task 18 - does the frozen 11.2 model transfer to Polymarket? (the user is weighing the platform)

GRADING IS THE WHOLE POINT HERE, so it is stated on every table:
  * Trading Predict.fun -> grade on the ENGINE's candles (Binance close >= open).
  * Trading POLYMARKET  -> grade on the venues `outcome` table. Polymarket settles on its own
    Chainlink 60-s TWAP, so its own resolution IS the settling source. This is the one place the
    outcome table is correct, and the one place using engine grading would be the error.
Both gradings are reported side by side so the resolution-source gap is visible, not assumed.

Polymarket taker fee: fee = shares x 0.07 x p x (1-p), makers free. Charged on the position, so a
$1 stake buying at ask p gets shares = 1/p and pays 0.07 x p x (1-p) / p = 0.07 x (1-p) per $1.
"""
import numpy as np, sqlite3, json, sys, joblib
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1')
sys.path.insert(0, '/home/user/Django-final-project/analysis/h1/models')
import task16_market_prior_ef as T, task11_2_direction_model as M
from ef11_2_predict import feats_at, SECS

MARGINS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
POLY_FEE_RATE = 0.07


def poly_books():
    """epoch -> {sec: (poly_up, poly_dn)}  (Polymarket asks, 5 s samples)."""
    c = sqlite3.connect(f'{T.DBD}/venues.sqlite3')
    q = {}
    for ep, sec, pu, pd_ in c.execute('select epoch, sec, poly_up, poly_dn from q order by epoch, sec'):
        q.setdefault(ep, {})[sec] = (pu, pd_)
    return q


def poly_at(book, S):
    pu = pd_ = None
    for s in sorted(k for k in book if k <= S):
        a, b = book[s]
        if a is not None: pu = a
        if b is not None: pd_ = b
    return pu, pd_


def poly_pnl(hit, ask):
    """Per $1 staked at `ask`, Polymarket taker fee = 0.07 * (1 - ask) per $1."""
    fee = POLY_FEE_RATE * (1.0 - ask)
    return (1.0 / ask - 1.0 - fee) if hit else (-1.0 - fee)


def summarise(tag, rows, grading, profile=False):
    if not rows:
        print('  %-34s [%s] n=0' % (tag, grading)); return
    pn = np.array([r['pnl'] for r in rows]); h = len(pn) // 2
    flag = '' if len(rows) >= 60 else '  << n<60'
    print('  %-34s [%-14s] n=%4d hit %4.1f%% per-fire %+7.3f total %+8.2f halves %+6.2f/%+6.2f ask~%.2f%s'
          % (tag, grading, len(pn), 100 * np.mean([r['hit'] for r in rows]), pn.mean(), pn.sum(),
             pn[:h].sum(), pn[h:].sum(), np.median([r['ask'] for r in rows]), flag))
    if profile:
        print('      fire-distance profile: ', end='')
        for i, l in enumerate(T.LBL):
            c = [r for r in rows if r['bi'] == i]
            if c:
                print('%s %.0f%% (%+.2f)  ' % (l, 100 * len(c) / len(rows), np.mean([r['pnl'] for r in c])), end='')
        print()


if __name__ == '__main__':
    m = joblib.load('/home/user/Django-final-project/analysis/h1/models/ef11_2_gbm_seed0.joblib')
    d = np.load(f'{T.SP}/build/paths.npz')
    cids, paths = d['cid'], d['paths'].astype(float)
    Pmap = {int(c) // 1000: p for c, p in zip(cids, paths)}
    eng = T.engine_actual()
    pb = poly_books()
    polyout = dict(sqlite3.connect(f'{T.DBD}/venues.sqlite3').execute('select epoch, actual from outcome'))
    eps = sorted(set(pb) & set(eng) & set(Pmap) & set(polyout))
    t12 = M.trailing12(paths, paths[:, 0]); idx = {int(c) // 1000: i for i, c in enumerate(cids)}
    print('candles with Polymarket book + BOTH resolutions + kline path: %d' % len(eps))
    dis = sum(1 for e in eps if polyout[e] != eng[e])
    print('the two resolutions disagree on %d of %d (%.1f%%) - this is why grading is labelled everywhere'
          % (dis, len(eps), 100 * dis / len(eps)))

    def replay(margin, haircut=0.0, model_side=True, cur=None):
        out = []
        for ep in eps:
            i = idx.get(ep)
            if i is None or np.isnan(t12[i]):
                continue
            p_arr = Pmap[ep]
            secs = SECS if model_side else [cur[ep]['S']]
            for S in secs:
                if S is None or S >= 300:
                    continue
                if model_side:
                    pu_p = float(m.predict_proba(feats_at(p_arr, S, t12[i]).reshape(1, -1))[0, 1])
                    side = 'UP' if pu_p >= 0.5 else 'DOWN'
                    p = pu_p if side == 'UP' else 1 - pu_p
                else:
                    side = cur[ep]['side']; p = cur[ep]['p']
                au, ad = poly_at(pb[ep], S)
                ask = au if side == 'UP' else ad
                if ask is None or not (0.02 < ask < 0.98):
                    continue
                ask = ask + haircut
                if not (0.02 < ask < 0.98):
                    continue
                fee = POLY_FEE_RATE * (1 - ask)
                if p * (1 / ask) - 1 - fee < margin:
                    continue
                op, px = p_arr[0], p_arr[S]
                out.append(dict(ep=ep, side=side, ask=ask, bi=T.bucket(abs(px - op) / op * 1e4),
                                hit_poly=(side == polyout[ep]), hit_eng=(side == eng[ep])))
                break
        return out

    def graded(rows, which):
        return [dict(pnl=poly_pnl(r['hit_' + which], r['ask']), hit=r['hit_' + which],
                     ask=r['ask'], bi=r['bi']) for r in rows]

    print()
    print('=' * 130)
    print('1. FROZEN 11.2 AT POLYMARKET ASKS, 7%% taker fee. EV-margin curve, both gradings.')
    print('=' * 130)
    for mg in MARGINS:
        r = replay(mg)
        summarise('11.2 @ poly, margin %.2f' % mg, graded(r, 'poly'), 'POLY resolve', profile=(mg == 0.15))
        summarise('11.2 @ poly, margin %.2f' % mg, graded(r, 'eng'), 'engine actual')
    print()
    print('=' * 130)
    print('2. CURRENT EF FIRE SET AT POLYMARKET ASKS (same direction and second, Polymarket price)')
    print('=' * 130)
    c = sqlite3.connect(f'{T.DBD}/twin_c_thr1.sqlite3')
    cur = {}
    for cid, dirn, feats in c.execute('select candle_id, direction, features from ef_candidates where fired=1'):
        f = json.loads(feats)
        ep = cid // 1000
        s = f.get('ef_v11_sec')
        if ep in eng and s is not None:
            cur[ep] = dict(side=dirn, p=f.get('ef_v11_p') or 0.5, S=int(s))
    eps_cur = [e for e in eps if e in cur]
    print('   (current EF fires with a Polymarket book on the same candle: %d)' % len(eps_cur))
    saved = eps
    eps = eps_cur
    for mg in (0.10, 0.15, 0.25):
        r = replay(mg, model_side=False, cur=cur)
        summarise('current EF @ poly, margin %.2f' % mg, graded(r, 'poly'), 'POLY resolve')
        summarise('current EF @ poly, margin %.2f' % mg, graded(r, 'eng'), 'engine actual')
    eps = saved
    print()
    print('=' * 130)
    print('3. STALENESS - on Polymarket the signal IS the venue price, so the ask can be gone on arrival')
    print('=' * 130)
    for hc in (0.0, 0.05, 0.10):
        r = replay(0.15, haircut=hc)
        summarise('11.2 @ poly +%.0fc' % (100 * hc), graded(r, 'poly'), 'POLY resolve')
