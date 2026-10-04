#!/usr/bin/env python3
"""Independent check of V's late rule on Zurich's per-pass book (V, 09-28 14:1x). READ-ONLY. Master OFF.

V's rule looks strong on public data, but its price source may be stale: it takes the MAX taker price in
the 3 s BEFORE the decision, while the model sees Binance at the end of the second. An unbiased quote
error becomes one-directional profit the moment the fire rule conditions on it - that is the exact defect
verify.py's quote_age gate exists for. Here the same idea is replayed against the REAL own-side ask at the
pass, with the +250 ms FAK simulator, so the price cannot predate the decision.

MODEL - spot only, as specified: move_bps, ret5, ret30, ret60, rv60, mv_x_sec. No lv, no p_venue, nothing
from the venue book. Walk-forward, day k fitted on days < k, and fitted PER SECOND BUCKET (15 s wide).

A note on what "p_side" can mean for a spot-only model. These features describe BTC, not a side: they are
identical for the UP and DOWN rows of one pass. A model fitted on both sides at once would therefore have
to learn the side from a sign convention it cannot see. So this fits P(UP resolves) on one row per pass
and derives p_side = p_up for UP, 1 - p_up for DOWN. That is a direction model on spot, which is what the
brief describes, and "pinned to the model's side" is then simply p_side >= 0.5.

DECISION LAG - the point of the exercise. Two extra reads per cell:
  lag-decide, real fill : decide on the ask as it was 1 s / 3 s ago, pay the true forward FAK price.
                          This is the honest number and the difference from lag 0 is the selection bias.
  lag-decide, lag fill  : decide AND book at the stale ask, which is what a backtest with a stale price
                          source actually reports. The gap between the two is the inflation.
"""
import sys, os, json, sqlite3, collections, random, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import fit_logistic, predict, per1, cost, be
from ef3 import STAKE, MIN_CELL
from ef3_shadow import load_candles, ARCH, LIVE, TICK, DELAY_MS

SPOT = ['move_bps', 'ret5', 'ret30', 'ret60', 'rv60', 'mv_x_sec']
BUCKET = 15
S0S = (150, 180, 200, 220, 240)
MS = (0.0, 0.02, 0.05, 0.10)
LAGS_MS = (0, 1000, 3000)


def build(cand, vo, keys):
    """One row per PASS, plus each side's FAK fill and the own-side ask at t-1 s and t-3 s."""
    ix = [keys.index(k) for k in SPOT]
    out = collections.defaultdict(list)
    for ep, rs in cand.items():
        rs = sorted(rs, key=lambda r: r[0])
        ts_a = np.array([r[0] for r in rs])
        ua = np.array([r[3] for r in rs]); da = np.array([r[4] for r in rs])
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        up_won = 1 if vo[ep] == 'UP' else 0
        for i, (ts, side_l, p_l, u, d, fire, v) in enumerate(rs):
            j = int(np.searchsorted(ts_a, ts + DELAY_MS, side='left'))
            q = {}
            for nm, own, arr in (('UP', u, ua), ('DOWN', d, da)):
                q[nm] = float('nan')
                if j < len(rs):
                    lat = float(arr[j])
                    if 0.01 < lat < 0.99 and lat <= own + TICK + 1e-12: q[nm] = lat
            lag = {}
            for L in LAGS_MS:
                b = int(np.searchsorted(ts_a, ts - L, side='right')) - 1
                lag[L] = (float(ua[b]), float(da[b])) if 0 <= b < len(rs) else (u, d)
            out[ep].append(dict(ts=ts, sec=int(ts // 1000 - ep), day=day, up_won=up_won,
                                x=np.array([float(v[k]) for k in ix]), ask={'UP': u, 'DOWN': d},
                                q=q, lag=lag))
    return out


def walk_forward(rows, days):
    """day k fitted on days < k; within a day, a separate fit per 15 s bucket."""
    X = np.stack([r['x'] for r in rows]); y = np.array([r['up_won'] for r in rows], float)
    day = np.array([r['day'] for r in rows]); buck = np.array([r['sec'] // BUCKET for r in rows])
    p = np.full(len(rows), np.nan)
    for k, dcur in enumerate(days):
        if k == 0: continue
        tr = np.isin(day, days[:k]); te = day == dcur
        for b in sorted(set(buck[te].tolist())):
            m_tr = tr & (buck == b); m_te = te & (buck == b)
            if m_tr.sum() < 200 or m_te.sum() == 0: continue
            Xt = X[m_tr]; mu, sd = Xt.mean(0), Xt.std(0)
            sd = np.where(sd > 0, sd, 1.0)
            w = fit_logistic((Xt - mu) / sd, y[m_tr])
            p[m_te] = predict(w, (X[m_te] - mu) / sd)
    return p


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return cum, mdd, worst


def fire(R, p, S0, m, lag=0, book_at_lag=False):
    """First pass at sec >= S0 whose model side clears p/be(ask) - 1 >= m. One fire per candle."""
    sel = []
    for ep, rows in R.items():
        for r in rows:
            i = r['i']
            if r['sec'] < S0 or not np.isfinite(p[i]): continue
            pu = p[i]
            side = 'UP' if pu >= 0.5 else 'DOWN'
            ps = pu if side == 'UP' else 1 - pu
            a_dec = r['lag'][lag][0 if side == 'UP' else 1]
            if not (0.01 < a_dec < 0.99): continue
            if (ps / be(a_dec) - 1) < m: continue
            q = a_dec if book_at_lag else r['q'][side]
            sel.append(dict(win=float(r['up_won'] == (1 if side == 'UP' else 0)), q=q,
                            day=r['day'], ts=r['ts'], ask=r['ask'][side],
                            oq=r['q']['DOWN' if side == 'UP' else 'UP']))
            break
    return sel


def perm_flip(fl, draws=300, seed=41):
    if not fl: return float('nan')
    Wf = lambda s: sum(per1(a, b) * cost(b) for a, b in s) / sum(cost(b) for a, b in s) if s else float('nan')
    real = Wf([(c['win'], c['q']) for c in fl]); rng = random.Random(seed); sims = []
    for _ in range(draws):
        acc = []
        for c in fl:
            if rng.random() < 0.5:
                if c['oq'] != c['oq']: continue
                acc.append((1 - c['win'], c['oq']))
            else: acc.append((c['win'], c['q']))
        if acc: sims.append(Wf(acc))
    return (sum(1 for x in sims if x >= real) / len(sims)) if sims else float('nan')


def row(lab, sel, nd):
    fl = sorted([c for c in sel if c['q'] == c['q']], key=lambda c: c['ts'])
    if not fl:
        print(f'  {lab:26s}   (no fills)'); return None
    seq = [STAKE * per1(c['win'], c['q']) for c in fl]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float)
    for c, x in zip(fl, seq): byd[c['day']] += x
    den = sum(cost(c['q']) for c in fl); h = len(fl) // 2
    hw = lambda s: sum(per1(c['win'], c['q']) * cost(c['q']) for c in s) / sum(cost(c['q']) for c in s) if s else float('nan')
    p1 = sum(per1(c['win'], c['q']) * cost(c['q']) for c in fl) / den
    print(f'  {lab:26s}{tot:>+8.1f}{mdd:>7.1f}{(tot/mdd if mdd>0 else 99.9):>7.2f}{len(sel)/max(nd,1):>7.1f}'
          f'{100*len(fl)/len(sel):>6.1f}%{f"{sum(1 for v in byd.values() if v>0)}/{len(byd)}":>7}{worst:>5}|'
          f'{p1:>+8.3f}{hw(fl[:h]):>+8.3f}{hw(fl[h:]):>+8.3f}{perm_flip(fl):>8.3f}'
          + ('  *n<60' if len(fl) < MIN_CELL else ''))
    return dict(tot=tot, mdd=mdd, n=len(sel), nf=len(fl), per1=p1)


HDR = (f'  {"cell":26s}{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"run":>5}|'
       f'{"per$1":>8}{"H1":>8}{"H2":>8}{"flipP":>8}')

if __name__ == '__main__':
    a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    keys = json.loads(a.execute("SELECT v FROM meta WHERE k='decide_log_features'").fetchone()[0])
    cand, vo, nk = load_candles()
    R = build(cand, vo, keys)
    flat = [r for ep in R for r in R[ep]]
    for i, r in enumerate(flat): r['i'] = i
    days = sorted({r['day'] for r in flat})
    print(f'candles {len(R)}, passes {len(flat)}, days {days}')
    print(f'spot features only: {SPOT}   walk-forward by day, refitted per {BUCKET}s bucket')
    p = walk_forward(flat, days)
    ok = np.isfinite(p)
    print(f'scored {ok.sum():,} of {len(flat):,} passes ({100*ok.mean():.1f}%) - day 1 is unscorable by design')
    yv = np.array([r['up_won'] for r in flat], float)
    o = np.argsort(p[ok]); yy = yv[ok][o]
    n1, n0 = yy.sum(), len(yy) - yy.sum()
    auc = (np.arange(1, len(yy) + 1)[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else float('nan')
    print(f'pooled AUC of the spot-only direction model: {auc:.4f}   (0.5 = no skill)\n')
    nd = len(days) - 1
    print('=' * 124); print(f'GRID  S0 x m   [spot-only model, real own-side ask at the pass, +250 ms FAK]')
    print('=' * 124); print(HDR)
    for S0 in S0S:
        for m in MS: row(f'S0={S0} m={m:.2f}', fire(R, p, S0, m), nd)
        print('  ' + '-' * 122)
    print('\n' + '=' * 124)
    print('DECISION LAG - same rule, but the ask used for the DECISION is read 1 s / 3 s before the pass')
    print('=' * 124); print(HDR)
    for S0 in (180, 220):
        for m in (0.0, 0.05):
            for L in LAGS_MS:
                row(f'S0={S0} m={m:.2f} lag{L//1000}s', fire(R, p, S0, m, lag=L), nd)
            row(f'S0={S0} m={m:.2f} lag3s BOOKED', fire(R, p, S0, 0.05 if m else 0.0, lag=3000,
                                                        book_at_lag=True), nd)
            print('  ' + '-' * 122)
    print('\n  lag0 = the honest read. lag1s/lag3s decide on a stale quote but PAY the true forward price:')
    print('  the gap from lag0 is pure selection bias. "BOOKED" also books at the stale price, which is')
    print('  what a backtest with a stale source reports - the gap between it and its lag3s row is the')
    print('  inflation V is asking about.')
