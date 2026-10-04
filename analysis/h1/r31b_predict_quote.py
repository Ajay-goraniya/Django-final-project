"""R-31b -- v10's p_venue/lv were trained on POLYMARKET prices. Does the port survive on Predict?

p_venue is reconstructed exactly as the live engine builds it when only asks are logged
(btc_model_v10.py:173-179): p_venue = (ask_up + (1 - ask_dn)) / 2, clamped to [0.02,0.98];
lv = logit(p_venue); lv_x_sec = lv * sec_left/300. Same formula applied to both venues' asks from
venues.q, so the two columns differ only by the prices themselves.

ORACLES ARE NOT POOLED. Polymarket scores against venues.outcome, Predict against candles.actual
(Binance close >= open, from paths.npz). The agreement rate between the two is reported first,
because a comparison across two oracles is only readable once you know how far apart they are.
"""
import math, os, sqlite3, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/user/Django-final-project/learner')
import task_r8_taker_feature as R8
import r12_train as T

SP = T.SP
SEC_AT = 60          # one row per candle at a fixed decision second, so n is candles not ticks


def pv(au, ad):
    if au is None or ad is None or not (np.isfinite(au) and np.isfinite(ad)):
        return None
    p = (au + (1.0 - ad)) / 2.0
    return min(0.98, max(0.02, p))


def binance_actual():
    d = np.load(os.path.join(SP, 'build', 'paths.npz'))
    cid = (d['cid'] // 1000).astype(np.int64)
    p = d['paths'].astype(float)
    return {int(c): bool(p[i, 299] >= p[i, 0]) for i, c in enumerate(cid)}


def rows_both():
    c = sqlite3.connect(os.path.join(SP, 'db', 'venues.sqlite3'))
    return c.execute('''select epoch,sec,poly_up,poly_dn,pred_up,pred_dn from q
                        where poly_up is not null and poly_dn is not null
                          and pred_up is not null and pred_dn is not null''').fetchall()


def main():
    R = rows_both()
    BA = binance_actual()
    c = sqlite3.connect(os.path.join(SP, 'db', 'venues.sqlite3'))
    OUT = {e: (a == 'UP') for e, a in c.execute('select epoch,actual from outcome')}

    print('R-31b  Predict quote vs Polymarket quote, and what it does to v10')
    print('  %d two-venue tick rows, %d distinct candles' % (R and len(R), len({r[0] for r in R})))

    ov = [e for e in {r[0] for r in R} if e in OUT and e in BA]
    agree = sum(1 for e in ov if OUT[e] == BA[e])
    print('\n  ORACLE AGREEMENT FIRST: venues.outcome vs candles.actual on %d shared candles: %d = %.1f%%'
          % (len(ov), agree, 100.0 * agree / len(ov)))
    print('  The two venues settle differently on %.1f%% of candles, so any cross-venue PnL'
          % (100.0 - 100.0 * agree / len(ov)))
    print('  comparison below carries that much irreducible noise. It is not a rounding detail.')

    print('\n  (a) PREDICT ASK MINUS POLYMARKET ASK, by Polymarket ask decile (UP side)')
    a = np.array([(r[2], r[4]) for r in R], float)
    q = np.percentile(a[:, 0], np.arange(0, 101, 10))
    print('  %-14s %8s %10s %10s %10s' % ('poly ask', 'n', 'mean diff', 'med diff', '|diff|>2c'))
    for i in range(10):
        m = (a[:, 0] >= q[i]) & (a[:, 0] < q[i + 1] if i < 9 else a[:, 0] <= q[i + 1])
        if m.sum() < 60:
            print('  %-14s %8d   INSUFFICIENT' % ('%.3f-%.3f' % (q[i], q[i + 1]), m.sum()))
            continue
        d = a[m, 1] - a[m, 0]
        print('  %-14s %8d %+10.4f %+10.4f %9.1f%%' % (
            '%.3f-%.3f' % (q[i], q[i + 1]), m.sum(), d.mean(), np.median(d), 100 * np.mean(np.abs(d) > 0.02)))
    d = a[:, 1] - a[:, 0]
    print('  %-14s %8d %+10.4f %+10.4f %9.1f%%' % ('ALL', len(d), d.mean(), np.median(d), 100 * np.mean(np.abs(d) > 0.02)))

    print('\n  (b) IS PREDICT\'S PRICE AS CALIBRATED A FORECAST? Each on ITS OWN oracle.')
    per = {}
    for ep, sec, pu, pd_, ru, rd in R:
        if sec != SEC_AT:
            continue
        per[ep] = (pv(pu, pd_), pv(ru, rd))
    print('  one row per candle at sec=%d: %d candles' % (SEC_AT, len(per)))
    for name, idx, oracle in (('Polymarket', 0, OUT), ('Predict.fun', 1, BA)):
        g = [(v[idx], oracle[e]) for e, v in per.items() if e in oracle and v[idx] is not None]
        if len(g) < 60:
            print('  %-12s INSUFFICIENT (n=%d)' % (name, len(g)))
            continue
        p = np.array([x[0] for x in g]); y = np.array([x[1] for x in g], float)
        br = float(np.mean((p - y) ** 2))
        ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
        print('  %-12s n=%-5d Brier %.4f  logloss %.4f  mean p %.4f  base rate %.4f'
              % (name, len(g), br, ll, p.mean(), y.mean()))
    print('  Null for scale: a constant 0.5 forecast scores Brier 0.2500, logloss 0.6931.')

    print('\n  (c) REFIRE FROZEN v10 WITH PREDICT\'S p_venue/lv ON THE SAME FIRES')
    from btc_model_v10 import Model
    import json
    m = Model(T.MODEL_JSON)
    qmap = {}
    for ep, sec, pu, pd_, ru, rd in R:
        qmap[(ep, sec)] = (pv(pu, pd_), pv(ru, rd), ru, rd, pu, pd_)
    db = sqlite3.connect(os.path.join(SP, 'db', 'poly_pnl.sqlite3'))
    orig, port, miss = [], [], 0
    for ep, p, ask, sec, win, feat in db.execute(
            'select candle_epoch,p,ask,sec,win,feat from trades where win is not null and feat is not null'):
        k = (int(ep), int(sec))
        if k not in qmap or int(ep) not in BA:
            miss += 1
            continue
        pvp, pvr, ru, rd, pu, pd_ = qmap[k]
        if pvr is None or pvp is None:
            miss += 1
            continue
        f = json.loads(feat)
        side = 'UP' if f.get('p_venue', 0.5) is not None and p >= 0 else 'UP'
        # rebuild the feature vector with Predict's venue block, everything else untouched
        g = dict(f)
        g['p_venue'] = pvr
        g['lv'] = math.log(pvr / (1 - pvr))
        g['lv_x_sec'] = g['lv'] * f.get('sec_left', 300 - int(sec)) / 300.0
        try:
            pup = float(m.p_up(g))
        except Exception:
            miss += 1
            continue
        s2 = 'UP' if pup >= 0.5 else 'DOWN'
        ask2 = ru if s2 == 'UP' else rd
        ps2 = pup if s2 == 'UP' else 1 - pup
        if not (0 < ask2 < 1):
            miss += 1
            continue
        orig.append((float(ask), int(win) == 1))
        if R8.ev_of(ps2, ask2) >= R8.threshold(f.get('rv60', 0.0)):
            won2 = (s2 == 'UP') == BA[int(ep)]
            port.append((float(ask2), won2))
    def stat(rows, fee_share):
        if not rows:
            return None
        v = np.array([(1.0 / a - 1.0 - fee_share / a) if w else -1.0 for a, w in rows])
        return len(rows), float(np.mean([w for _, w in rows])), float(v.mean()), float(v.sum())
    o = stat(orig, 0.0167); q2 = stat(port, 0.02)
    print('  %d fires matched to a two-venue quote at their own fire second (%d dropped)' % (len(orig), miss))
    print('  %-28s %6s %7s %10s %10s' % ('arm', 'n', 'W%', 'per $1', 'total'))
    print('  %-28s %6d %6.1f%% %+10.4f %+10.2f' % (
        'original, Poly price+oracle', o[0], 100 * o[1], o[2], o[3]))
    print('  %-28s %6d %6.1f%% %+10.4f %+10.2f' % (
        'ported, Predict price+oracle', q2[0], 100 * q2[1], q2[2], q2[3]))
    print('  (each priced with its own venue fee: Poly 1.67%% of shares always, Predict 2%% on wins)')


if __name__ == '__main__':
    main()
