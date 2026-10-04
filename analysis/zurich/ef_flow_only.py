#!/usr/bin/env python3
"""Part 5: a FLOW-ONLY model, and the Chainlink-vs-Binance divergence. READ-ONLY. Master OFF.

V, 09-28, agreeing on part 4's conclusion: the input has to be something the venue is not watching. So drop
every price and move feature and keep only order flow, book shape and the perp basis.

FEATURES KEPT (all that decide_log holds of V's list)
  ofi5, ofi15, ofi60     aggressor order-flow imbalance over 5/15/60 s. The engine carries 5/15/60, not the
                         5/30/60 in the brief - these are the same quantity on the windows that exist.
  spot_imb15, spot_imb60 spot buy-minus-sell volume imbalance
  imb5, imb20            venue book depth imbalance at 5 and 20 levels
  perp_n15               perp trade count over 15 s (flow intensity, not direction)
  basis_bps              perp minus spot
  rv60                   realised vol over 60 s
EXCLUDED: move_bps, mv_x_sec, ret5/15/30/60, prev1/prev2_bps, range_bps, pos_in_range, dist_hi/lo_bps,
  ref_move_bps, ref_open_bps (all price or move), lv, lv_x_sec, p_venue (the venue's own opinion), micro_bps
  (a book-derived PRICE, so it is the venue's view under another name), hod_sin/hod_cos (clock, not flow).

Same harness as part 4: walk-forward by day, day k fitted on days < k with the scaler fitted on the training
rows alone, first day never scored; one row per candle at exactly sec == S; label is the venue's own
resolution; the model predicts P(UP) so p_side is symmetric and a disagreement cell can pick either side.

CHAINLINK. tape1s.ref_px is the venue's own RTDS `crypto_prices_chainlink` topic (poly_feeds.py:90-94) - the
Chainlink BTC/USD the market settles on - and tape1s.spot_px is Binance, both at 1 Hz. That gives a direct
read on whether the settlement reference leads the exchange the model actually watches.
"""
import sys, sqlite3, math, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef_persist import load, per1, cost, TICK, MIN_CELL, LIVE
from ef_fire_time import augment
from ef_spot_only import fit_logistic, predict, auc, own, sim_fill, W, halves, perm_opp

SECS = (20, 30, 45, 60)
FLOW = ['ofi5', 'ofi15', 'ofi60', 'spot_imb15', 'spot_imb60', 'imb5', 'imb20', 'perp_n15',
        'basis_bps', 'rv60']
CELLS = [(0.60, 0.50), (0.65, 0.45)]
lgt = lambda x: math.log(min(max(x, 1e-4), 1 - 1e-4) / (1 - min(max(x, 1e-4), 1 - 1e-4)))


def rows_at(cand, S, cols):
    out = []
    for ep, rs in cand.items():
        at = [r for r in rs if r['sec'] == S]
        if not at: continue
        r = at[0]
        if r['feats'] is None or any(r['feats'][i] is None for i in cols): continue
        if not (0.01 < r['ua'] < 0.99 and 0.01 < r['da'] < 0.99): continue
        out.append(r)
    return out


def walk(X, y, dt, days):
    pred = np.full(len(X), np.nan)
    for d in days[1:]:
        tr, te = dt < d, dt == d
        if tr.sum() < 50 or te.sum() == 0: continue
        mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
        pred[te] = predict(fit_logistic((X[tr] - mu) / sd, y[tr]), (X[te] - mu) / sd)
    return pred


def chainlink():
    print(f'\n{"="*132}\nTHE CHAINLINK ANGLE - does the settlement reference lead the exchange the model watches?\n{"="*132}')
    a = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    sp, rf = {}, {}
    for ts, s, r in a.execute('SELECT ts,spot_px,ref_px FROM tape1s WHERE ref_px IS NOT NULL ORDER BY ts'):
        rf[int(ts)] = float(r)
        if s is not None: sp[int(ts)] = float(s)
    both = sorted(set(sp) & set(rf))
    print(f'  tape1s rows with BOTH the Chainlink RTDS reference and Binance spot: {len(both)} seconds '
          f'= {(both[-1]-both[0])/3600:.1f} h span')
    d = np.array([(rf[t] - sp[t]) / sp[t] * 1e4 for t in both])
    print(f'  divergence (chainlink - binance), bps: mean {d.mean():+.3f}  p10 {np.percentile(d,10):+.2f}  '
          f'p50 {np.percentile(d,50):+.2f}  p90 {np.percentile(d,90):+.2f}  sd {d.std():.2f}')
    print(f'  the reference moves MORE often than the 1 s Binance tape: unchanged second-to-second on '
          f'{100*np.mean(np.diff([rf[t] for t in both])==0):.1f}% of seconds vs '
          f'{100*np.mean(np.diff([sp[t] for t in both])==0):.1f}% for Binance')
    print(f'\n  NOTE the raw divergence is a drifting OFFSET, not a centred signal: it is negative on more '
          f'than 90% of\n  seconds and its mean moved from -0.25 bps over the first 20k seconds to '
          f'{d.mean():+.2f} bps over the whole span.\n  Testing the raw level would mostly test that offset, '
          f'so everything below is reported BOTH raw and de-meaned\n  against the median divergence over the '
          f'previous 600 s (past-only).')
    print(f'\n  corr(divergence at sec s, the NEXT 60 s Binance return) - one observation per candle, so the '
          f'observations\n  at a given s do not overlap:')
    print(f'    {"sec":>5}{"n candles":>11}{"corr raw":>10}{"corr demean":>13}{"rank demean":>13}'
          f'{"fwd60 bps sd":>14}{"div_z bps sd":>14}')
    eps = sorted({t // 300 * 300 for t in both})
    divz = {}
    bl = np.array(both)
    dv = {t: (rf[t] - sp[t]) / sp[t] * 1e4 for t in both}
    win = collections.deque()
    for t in both:                                    # past-only rolling median over the previous 600 s
        while win and win[0][0] < t - 600: win.popleft()
        divz[t] = dv[t] - (np.median([v for _, v in win]) if len(win) >= 60 else np.nan)
        win.append((t, dv[t]))
    for S in SECS:
        X, Z, Y = [], [], []
        for ep in eps:
            t = ep + S
            if t not in sp or t not in rf or (t + 60) not in sp: continue
            if not np.isfinite(divz.get(t, np.nan)): continue
            X.append(dv[t]); Z.append(divz[t]); Y.append(math.log(sp[t + 60] / sp[t]) * 1e4)
        if len(X) < 30: print(f'    {S:>5}{len(X):>11}   too few'); continue
        X = np.array(X); Z = np.array(Z); Y = np.array(Y)
        rk = np.corrcoef(np.argsort(np.argsort(Z)), np.argsort(np.argsort(Y)))[0, 1]
        print(f'    {S:>5}{len(X):>11}{np.corrcoef(X,Y)[0,1]:+10.3f}{np.corrcoef(Z,Y)[0,1]:+13.3f}'
              f'{rk:+13.3f}{Y.std():14.2f}{Z.std():14.2f}')
    globals()['DIVZ'] = divz
    print(f'\n  and the question that actually matters - does the divergence predict the VENUE OUTCOME?')
    return sp, rf


if __name__ == '__main__':
    cand, names = load(); augment(cand)
    IDX = [names.index(k) for k in FLOW]
    days = sorted({r['day'] for rs in cand.values() for r in rs})
    print(f'candles {len(cand)}, days {days}; walk-forward scores {days[1:]}')
    print(f'flow features ({len(FLOW)}): ' + ', '.join(FLOW))

    for S in SECS:
        rows = rows_at(cand, S, IDX)
        if not rows: print(f'S={S}: no rows'); continue
        X = np.array([[r['feats'][i] for i in IDX] for r in rows], float)
        yUP = np.array([1.0 if (r['win'] == 1) == (r['side'] == 'UP') else 0.0 for r in rows])
        dt = np.array([r['day'] for r in rows])
        mid = np.array([(r['ua'] + (1 - r['da'])) / 2.0 for r in rows])

        print(f'\n{"="*132}\nS = {S}s   {len(rows)} candles with a pass at that second\n{"="*132}')
        print('  (a) correlation of each flow feature with the VENUE MID - a LOW number is the point')
        cs = [(k, abs(np.corrcoef(X[:, j], mid)[0, 1])) for j, k in enumerate(FLOW)]
        for k, c in sorted(cs, key=lambda z: z[1]):
            print(f'      {k:12s} |corr| {c:.3f}' + ('   <- as venue-correlated as a price feature'
                                                     if c > 0.4 else ''))
        print(f'      for scale: move_bps |corr| 0.717, lv |corr| 0.981 (both measured on all 785,924 passes)')

        pf = walk(X, yUP, dt, days)
        Xm = np.c_[[lgt(m) for m in mid]]
        pm = walk(Xm, yUP, dt, days)
        Xmf = np.c_[[lgt(m) for m in mid], X]
        pmf = walk(Xmf, yUP, dt, days)
        sc = ~(np.isnan(pf) | np.isnan(pm) | np.isnan(pmf))
        a_f, a_m, a_mf = (auc(yUP[sc], pf[sc]), auc(yUP[sc], mid[sc]), auc(yUP[sc], pmf[sc]))
        print(f'\n  (b) AUC on {int(sc.sum())} scored candles')
        print(f'      flow-only          {a_f:.3f}')
        print(f'      venue mid alone    {a_m:.3f}')
        print(f'      venue mid + flow   {a_mf:.3f}   -> flow ADDS {a_mf-a_m:+.3f} to the price'
              + ('  (an improvement)' if a_mf > a_m else '  (no improvement)'))

        print(f'\n  (c) DISAGREEMENT cells - flow model likes a side the venue prices cheap')
        print(f'      {"rule":22s}{"n cand":>8}{"fills":>6}{"fill%":>7}{"win%":>7}{"per$1":>9}'
              f'{"H1":>8}{"H2":>8}{"permP":>7}{"ask":>7}')
        for PT, AT in CELLS:
            ent = []
            for r, p, ok in zip(rows, pf, sc):
                if not ok: continue
                for side in ('UP', 'DOWN'):
                    ps = p if side == 'UP' else 1 - p
                    aa = own(r, side)
                    if ps >= PT and aa <= AT:
                        ent.append(dict(r=r, side=side, ask=aa, q=sim_fill(r, side), t=r['t'],
                                        win=1 if (r['win'] == 1) == (side == r['side']) else 0,
                                        day=r['day'], ep=r['ep'], p=ps))
                        break
            if not ent:
                print(f'      p>={PT:.2f} & ask<={AT:.2f}       0       -      -      -        -       -       -      -      -')
                continue
            nf = sum(1 for e in ent if e['q'] is not None)
            h1, h2 = halves(ent); pp, _ = perm_opp(ent)
            wins = [e['win'] for e in ent if e['q'] is not None]
            print(f'      p>={PT:.2f} & ask<={AT:.2f} {len(ent):8d}{nf:6d}{100*nf/len(ent):6.1f}%'
                  f'{(100*np.mean(wins) if wins else float("nan")):6.1f}%{W(ent):+9.3f}'
                  f'{(h1 if h1==h1 else 0):+8.3f}{(h2 if h2==h2 else 0):+8.3f}{pp:7.3f}'
                  f'{np.mean([e["ask"] for e in ent]):7.3f}' + ('  *n<60' if nf < MIN_CELL else ''))

    sp, rf = chainlink()
    divz = globals().get('DIVZ', {})
    print(f'      {"sec":>5}{"n":>7}{"AUC div raw":>13}{"AUC div demean":>16}{"AUC mid":>10}'
          f'{"div_z |corr| mid":>19}')
    for S in SECS:
        rows = rows_at(cand, S, IDX)
        X, Z, Y, M = [], [], [], []
        for r in rows:
            t = r['ep'] + S
            if t not in sp or t not in rf: continue
            if not np.isfinite(divz.get(t, np.nan)): continue
            X.append((rf[t] - sp[t]) / sp[t] * 1e4); Z.append(divz[t])
            Y.append(1.0 if (r['win'] == 1) == (r['side'] == 'UP') else 0.0)
            M.append((r['ua'] + (1 - r['da'])) / 2.0)
        if len(X) < 30: print(f'      {S:>5}{len(X):>7}   too few'); continue
        X = np.array(X); Z = np.array(Z); Y = np.array(Y); M = np.array(M)
        print(f'      {S:>5}{len(X):>7}{auc(Y, X):13.3f}{auc(Y, Z):16.3f}{auc(Y, M):10.3f}'
              f'{abs(np.corrcoef(Z, M)[0,1]):19.3f}')
