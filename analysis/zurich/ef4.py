#!/usr/bin/env python3
"""EF-4 (V, 09-28 14:5x): stop modelling P(side wins) and model the money AFTER the fill. READ-ONLY.

Everything so far learned P(this side resolves). The 10-day read says the loss is not there: paper is
positive and London-exec negative in every single cell, so what is being got wrong is WHICH fires fill and
at what price. So the target here is the realised return of the candidate AS EXECUTED:

    target_i = 0                     if the +250 ms FAK does not fill
             = per1(win_i, q_i)      if it does, at the price it actually filled at

per1(w, q) = (w/q - cost(q)) / cost(q) with cost(q) = 1 + 0.07(1 - q) - i.e. net profit per $1 SPENT
including the fee, which is V's "(win ? 1/fill_cost - 1 : -1)" in the units the rest of this work uses.

A model on this target is not a better direction model. It is a model of a different quantity: it can
learn to avoid a candidate whose side is likely right but whose quote is about to vanish, which is exactly
the failure the London execution model keeps exposing and which no P(win) model can express.

FEATURES: the 52 already carry the fill-relevant ones V listed - dip30, d_ask_1s/5s/30s, sec, own/opp ask.
BOOK AGE IS NOT AMONG THEM: the engine does not log a book-age field in decide_log_features, so it is
absent here rather than approximated. Said plainly because its absence is a real limit on this test.

Both targets are fitted with the SAME ridge linear on the SAME standardised features, so the coefficient
masses at the end are comparable. A squared-loss stump booster runs alongside as the capacity check -
ef2_model.gb_fit is a logistic classifier and cannot take a continuous target.
"""
import sys, os, math, collections, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import ROWS, per1, cost, be
from ef3 import FITS, platt, pad_cost, STAKE, MIN_CELL, score, HDR, line

TS = (0.0, 0.01, 0.02, 0.05)
S0S = (0, 60, 150)
LAM = 30.0


def ridge(X, y, lam=LAM):
    Xa = np.c_[np.ones(len(X)), X]
    A = Xa.T @ Xa + lam * np.eye(Xa.shape[1]); A[0, 0] -= lam
    return np.linalg.solve(A, Xa.T @ y)


def rpred(w, X):
    return np.c_[np.ones(len(X)), X] @ w


def gb_reg(X, y, rounds=80, lr=0.1, bins=24, sub=0.5, seed=7):
    """Squared-loss stump booster. Same shape as ef2_model.gb_fit but on a continuous target."""
    rng = np.random.default_rng(seed)
    n, d = X.shape
    edges = [np.quantile(X[:, j], np.linspace(0, 1, bins + 1)[1:-1]) for j in range(d)]
    B = np.empty((n, d), dtype=np.int16)
    for j in range(d): B[:, j] = np.searchsorted(edges[j], X[:, j])
    F = np.full(n, float(y.mean())); base = float(F[0]); trees = []
    for _ in range(rounds):
        g = y - F
        idx = rng.random(n) < sub
        best = None
        for j in range(d):
            gs = np.bincount(B[idx, j], weights=g[idx], minlength=bins)
            cs = np.bincount(B[idx, j], minlength=bins).astype(float)
            cg = np.cumsum(gs); cc = np.cumsum(cs)
            tg, tc = cg[-1], cc[-1]
            gain = cg[:-1] ** 2 / np.maximum(cc[:-1], 1.0) + (tg - cg[:-1]) ** 2 / np.maximum(tc - cc[:-1], 1.0)
            k = int(np.argmax(gain))
            if best is None or gain[k] > best[0]: best = (float(gain[k]), j, k, cg, cc, tg, tc)
        _, j, k, cg, cc, tg, tc = best
        vl = float(cg[k] / max(cc[k], 1.0)); vr = float((tg - cg[k]) / max(tc - cc[k], 1.0))
        vl = max(min(vl, 2.0), -2.0); vr = max(min(vr, 2.0), -2.0)
        F = F + lr * np.where(B[:, j] <= k, vl, vr)
        trees.append((j, float(edges[j][k]) if k < len(edges[j]) else float('inf'), lr * vl, lr * vr))
    return dict(base=base, trees=trees)


def gb_reg_pred(m, X):
    F = np.full(len(X), m['base'])
    for j, thr, vl, vr in m['trees']:
        F += np.where(X[:, j] <= thr, vl, vr)
    return F


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, yw, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    yw = yw.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    pw = f['pw']; wf = np.isfinite(pw)
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    filled = np.isfinite(q)
    tgt = np.where(filled, per1(yw, np.where(filled, q, 0.5)), 0.0)
    days = sorted(set(day.tolist()))
    print(f'rows {len(yw):,}  features {len(names)}  days {days}')
    print(f'fill rate over all candidate rows {100*filled.mean():.1f}%   '
          f'target mean {tgt.mean():+.4f}  sd {tgt.std():.3f}  '
          f'(filled rows only: mean {tgt[filled].mean():+.4f})')

    # ---- the check that decides whether EF-4 is a signal or a level fit -------------------------
    # ref_open and bn_line_open are ABSOLUTE BTC prices (~$84,000) correlated at +0.999886. The first
    # run put -2.6881 and +2.4082 on them: a huge opposed pair on two near-identical regressors, which
    # is the ridge amplifying the numerical difference between two copies of the same number by ~10^4.
    # That is not a tradeable feature, it is a per-day offset with no forward meaning, and it would
    # extrapolate wildly the moment BTC leaves the training range. --nolevel drops the six absolute
    # price columns and re-runs; if the result survives, EF-4 is real, and if it collapses it was this.
    LEVEL = ['_price', 'ref_open', 'ref_now', 'ref_inst', 'bn_line_open', 'bn_line_now']
    if '--nolevel' in sys.argv:
        drop = [names.index(k) for k in LEVEL if k in names]
        keepc = [i for i in range(len(names)) if i not in drop]
        X = X[:, keepc]; names = [names[i] for i in keepc]
        print(f'--nolevel: dropped {len(drop)} absolute-price columns, {len(names)} features remain')
        ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    X64 = X.astype(np.float64)
    pl = np.full(len(yw), np.nan); pg = np.full(len(yw), np.nan)
    COEF = {}
    for k, dcur in enumerate(days):
        if k == 0: continue
        tr = np.isin(day, days[:k]); te = day == dcur
        mu, sd = X64[tr].mean(0), X64[tr].std(0); sd = np.where(sd > 0, sd, 1.0)
        Zt = (X64[tr] - mu) / sd
        w_money = ridge(Zt, tgt[tr]); w_win = ridge(Zt, yw[tr])
        Ze = (X64[te] - mu) / sd
        pl[te] = rpred(w_money, Ze)
        g = gb_reg(Zt, tgt[tr]); pg[te] = gb_reg_pred(g, Ze)
        COEF[dcur] = (w_money, w_win)
        print(f'  day {dcur}: train {tr.sum():,} test {te.sum():,}  '
              f'corr(pred, target) linear {np.corrcoef(pl[te], tgt[te])[0,1]:.4f}  '
              f'stumps {np.corrcoef(pg[te], tgt[te])[0,1]:.4f}')

    # candidates, 4 walk-forward days so EF-4 / A / C are on identical candles
    ok = np.isfinite(pl) & wf
    opp = {}
    for i in range(len(yw)): opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if filled[i] else float('nan')
    C4 = collections.defaultdict(list)
    for i in np.where(ok)[0]:
        C4[int(ep[i])].append(dict(t=int(ts[i]), p=float(X[i, ip]), ask=float(X[i, ia]),
                                   q=float(q[i]), win=float(yw[i]), sec=int(X[i, isec]),
                                   day=str(day[i]), pm=float(pl[i]), pg=float(pg[i]),
                                   pw=float(pw[i]), oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
    for e in C4: C4[e].sort(key=lambda c: c['t'])
    d4 = sorted({c['day'] for l in C4.values() for c in l}); nd = len(d4)
    print(f'\ncandles {len(C4)}, days {d4}')

    def first(pred):
        out = []
        for e, lst in C4.items():
            c = next((c for c in lst if pred(c)), None)
            if c is not None: out.append(c)
        return out

    print('\n' + '=' * 136)
    print('EF-4 GRID: fire at the first pass with p_side >= 0.5, sec >= S0, predicted after-fill $ >= t')
    print('=' * 136); print(HDR)
    R = {}
    for S0 in S0S:
        for t in TS:
            s = line(f'EF-4 t={t:.2f} S0={S0}',
                     first(lambda c, t_=t, S_=S0: c['sec'] >= S_ and c['p'] >= 0.5 and c['pm'] >= t_), nd)
            if s: R[f'EF-4 t={t:.2f} S0={S0}'] = s
        print('  ' + '-' * 134)
    print('  stumps (capacity check), same grid at S0=0:')
    for t in TS:
        s = line(f'EF-4gb t={t:.2f} S0=0', first(lambda c, t_=t: c['p'] >= 0.5 and c['pg'] >= t_), nd)
        if s: R[f'EF-4gb t={t:.2f} S0=0'] = s          # the first run left these OUT of the qualify check
    for S0 in (60, 150):
        for t in TS:
            s = line(f'EF-4gb t={t:.2f} S0={S0}',
                     first(lambda c, t_=t, S_=S0: c['sec'] >= S_ and c['p'] >= 0.5 and c['pg'] >= t_), nd)
            if s: R[f'EF-4gb t={t:.2f} S0={S0}'] = s
        print('  ' + '-' * 134)

    print('\n' + '=' * 136); print('THE SAME DAYS, the arms already in the shadow'); print('=' * 136)
    print(HDR)
    C = line('C fixed15 (control)',
             first(lambda c: c['p'] >= 0.5 and (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15), nd)
    A = line('A v0 m=0.02 S>=150',
             first(lambda c: c['sec'] >= 150 and c['pw'] >= 0.5 and (c['pw'] / be(c['ask']) - 1) >= 0.02), nd)
    B = line('B raw25 S>=60',
             first(lambda c: c['sec'] >= 60 and c['p'] >= 0.5 and (c['p'] / be(c['ask']) - 1) >= 0.25), nd)

    print('\n' + '=' * 136); print('DOES ANY EF-4 CELL BEAT C ON $ AND DRAWDOWN?'); print('=' * 136)
    win = [(k, v) for k, v in R.items() if v['tot'] > C['tot'] and v['mdd'] <= C['mdd'] and v['nf'] >= MIN_CELL]
    if win:
        for k, v in sorted(win, key=lambda kv: -kv[1]['ratio']):
            print(f'  {k:24s} $ {v["tot"]:+8.1f} (C {C["tot"]:+.1f})   DD {v["mdd"]:6.1f} (C {C["mdd"]:.1f})   '
                  f'P/DD {v["ratio"]:5.2f}   fills {v["nf"]}   fill% {100*v["fill"]:.1f}   days+ {v["pos"]}/{v["days"]}')
            print(f'      per day $: ' + '  '.join(f'{d} {v["byd"].get(d, 0.0):+7.1f}' for d in d4))
            o = sorted(v['byd'].values(), reverse=True)
            if len(o) >= 2 and v['tot'] > 0:
                print(f'      best two days {o[0]:+.1f} {o[1]:+.1f} = {o[0]+o[1]:+.1f} '
                      f'({100*(o[0]+o[1])/v["tot"]:.0f}% of the total), rest {sum(o[2:]):+.1f}')
        print(f'\n  -> {len(win)} cell(s) qualify for pre-registration as arm D.')
    else:
        print(f'  NONE. C is $ {C["tot"]:+.1f} with drawdown ${C["mdd"]:.1f}; no EF-4 cell with >= {MIN_CELL} '
              f'fills beats it on both.')
        best = max(R.items(), key=lambda kv: kv[1]['tot'])
        print(f'  best EF-4 cell by $: {best[0]} at {best[1]["tot"]:+.1f} / DD {best[1]["mdd"]:.1f} '
              f'/ {best[1]["nf"]} fills')

    print('\n' + '=' * 136); print('WHAT THE MODEL LEARNED - same ridge, same features, two targets')
    print('=' * 136)
    wm, ww = COEF[days[-1]]
    im = np.argsort(-np.abs(wm[1:]))[:15]; iw = np.argsort(-np.abs(ww[1:]))[:15]
    print(f'  {"after-fill $ target":34s}  |  {"P(win) target":34s}')
    for a, b in zip(im, iw):
        print(f'  {names[a]:22s}{wm[1+a]:+10.4f}  |  {names[b]:22s}{ww[1+b]:+10.4f}')
    blocks = {'the price': ['own_ask', 'opp_ask'], 'the engine p': ['p_side'],
              'ask dynamics': ['d_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30'], 'the clock': ['sec']}
    print(f'\n  {"block":16s}{"after-fill $":>16}{"P(win)":>12}   (sum |coef|, standardised)')
    for nm, ks in blocks.items():
        idx = [names.index(x) for x in ks if x in names]
        print(f'  {nm:16s}{sum(abs(wm[1+i]) for i in idx):>16.4f}{sum(abs(ww[1+i]) for i in idx):>12.4f}')
