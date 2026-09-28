#!/usr/bin/env python3
"""EF-2 step 2-3-5: walk-forward model, margin grid, comparisons, feature importance. READ-ONLY, master OFF.

No sklearn, lightgbm, xgboost or scipy on this box - numpy only - and I am not installing into the engine's
venv to get one. So the primary model is a ridge-regularised LOGISTIC (Newton steps, intercept unpenalised),
which V's brief allows, and a small hand-rolled gradient-boosted stump ensemble runs beside it purely as a
CAPACITY CHECK: if trees do not beat the linear fit on held-out days, the logistic is not the limiting factor
and its coefficients are the honest thing to export.

DECISION RULE, and this is a deliberate reading of the brief. V wrote "buy when p_win / cost > 1 + margin at
the SIM fill price". The economics are computed at the sim fill price, but the DECISION is taken on the
QUOTED ask, because deciding on the fill price would use a quote from 250 ms in the future - the exact
lookahead this session has caught three times. Both are reported: the sound version as the headline, and the
lookahead version beside it so the size of the difference is visible rather than argued about.

ONE FIRE PER CANDLE, the first qualifying (pass, side), so the numbers are comparable with the fixed15 rule
and the S=15 placebo from EF_FIRE_TIME.md.

WALK-FORWARD: day k is fitted on days < k, scaler fitted on the training rows alone, first day never scored.
"""
import sys, json, math, random, time, collections, statistics as st, numpy as np

ROWS = '/home/ubuntu/pm_ef2/ef2_rows.npz'
RATE, TICK = 0.07, 0.01
MARGINS = (0.0, 0.02, 0.05, 0.10)
cost = lambda q: 1 + RATE * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)
MIN_CELL = 60


def fit_logistic(X, y, lam=2.0, iters=60):
    X = np.c_[np.ones(len(X), dtype=np.float64), X.astype(np.float64)]
    w = np.zeros(X.shape[1]); R = np.eye(X.shape[1]) * lam; R[0, 0] = 0.0
    for _ in range(iters):
        z = np.clip(X @ w, -30, 30); q = 1 / (1 + np.exp(-z))
        W = np.clip(q * (1 - q), 1e-7, None)
        H = X.T @ (X * W[:, None]) + R
        g = X.T @ (y - q) - R @ w
        try: step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError: break
        w += step
        if np.abs(step).max() < 1e-8: break
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


def auc(y, s):
    m = np.isfinite(s); y, s = y[m], s[m]
    if len(set(y.tolist())) < 2: return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


# ---- a compact gradient-boosted STUMP ensemble, numpy only, capacity check ------------------------
def gb_fit(X, y, rounds=120, lr=0.1, bins=24, sub=0.5, seed=7):
    rng = np.random.default_rng(seed)
    n, d = X.shape
    edges = [np.quantile(X[:, j], np.linspace(0, 1, bins + 1)[1:-1]) for j in range(d)]
    B = np.empty((n, d), dtype=np.int16)
    for j in range(d): B[:, j] = np.searchsorted(edges[j], X[:, j])
    F = np.full(n, math.log(max(y.mean(), 1e-6) / max(1 - y.mean(), 1e-6)))
    base = float(F[0]); trees = []
    for _ in range(rounds):
        p = 1 / (1 + np.exp(-F)); g = y - p; h = np.clip(p * (1 - p), 1e-6, None)
        idx = rng.random(n) < sub
        best = None
        for j in range(d):
            gs = np.bincount(B[idx, j], weights=g[idx], minlength=bins)
            hs = np.bincount(B[idx, j], weights=h[idx], minlength=bins)
            cg = np.cumsum(gs); ch = np.cumsum(hs)
            tg, th = cg[-1], ch[-1]
            gain = cg[:-1] ** 2 / np.maximum(ch[:-1], 1e-6) + (tg - cg[:-1]) ** 2 / np.maximum(th - ch[:-1], 1e-6)
            k = int(np.argmax(gain))
            if best is None or gain[k] > best[0]: best = (float(gain[k]), j, k, cg, ch, tg, th)
        _, j, k, cg, ch, tg, th = best
        vl = float(cg[k] / max(ch[k], 1e-6)); vr = float((tg - cg[k]) / max(th - ch[k], 1e-6))
        vl = max(min(vl, 4.0), -4.0); vr = max(min(vr, 4.0), -4.0)
        left = B[:, j] <= k
        F = F + lr * np.where(left, vl, vr)
        trees.append((j, float(edges[j][k]) if k < len(edges[j]) else float('inf'), lr * vl, lr * vr))
    return dict(base=base, trees=trees)


def gb_predict(m, X):
    F = np.full(len(X), m['base'])
    for j, thr, vl, vr in m['trees']:
        F += np.where(X[:, j] <= thr, vl, vr)
    return 1 / (1 + np.exp(-F))


def W(sel):
    fl = [(w, q) for w, q, *_ in sel if q == q]
    if not fl: return float('nan')
    return sum(per1(w, q) * cost(q) for w, q in fl) / sum(cost(q) for w, q in fl)


def halves(sel):
    fl = sorted([s for s in sel if s[1] == s[1]], key=lambda s: s[2])
    h = len(fl) // 2
    return W(fl[:h]), W(fl[h:])


def perm_opp(sel, draws=400, seed=31):
    """Flip priced at the OPPOSITE side's real ask at the same pass, both arms through the same FAK test."""
    fl = [s for s in sel if s[1] == s[1]]
    if not fl: return float('nan')
    real = W(fl); rng = random.Random(seed); sims = []
    for _ in range(draws):
        acc = []
        for w, q, t, oq in fl:
            if rng.random() < 0.5:
                if oq != oq: continue
                acc.append((1 - w, oq, t, q))
            else: acc.append((w, q, t, oq))
        if acc: sims.append(W(acc))
    if not sims: return float('nan')
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims)


be = lambda a: a * (1 + RATE * (1 - a))


def first_fire(cands, margin, use_fill=False):
    """One fire per candle: the first (pass, side) whose EV clears the margin. Ties at the same pass go to
    the higher EV. `use_fill` is the LOOKAHEAD variant, reported only to size the difference."""
    out = {}
    for ep, lst in cands.items():
        best = None
        for t, p, ask, q, win, oq in lst:
            px = q if use_fill else ask
            if px != px: continue
            ev = p / be(px) - 1
            if ev < margin: continue
            if best is None or t < best[0] or (t == best[0] and ev > best[1]):
                best = (t, ev, q, win, oq)
        if best is not None:
            out[ep] = (best[3], best[2], best[0], best[4])      # win, fill price, ts, opposite fill price
    return out


if __name__ == '__main__':
    t0 = time.time()
    z = np.load(ROWS, allow_pickle=True)
    X, y, q, filled = z['X'], z['y'].astype(float), z['q'], z['filled']
    ep, ts, sec, day = z['ep'], z['ts'], z['sec'], z['day']
    names = [str(s) for s in z['names']]
    days = sorted(set(day.tolist()))
    print(f'rows {len(y):,}  features {X.shape[1]}  candles {len(set(ep.tolist()))}  days {days}')

    keep = np.all(np.isfinite(X), axis=1)
    print(f'  rows with every feature finite: {keep.sum():,} ({100*keep.mean():.1f}%) - the rest cannot be '
          f'scored by a linear model and are dropped from FIT and SCORE alike')
    X, y, q, filled, ep, ts, sec, day = (v[keep] for v in (X, y, q, filled, ep, ts, sec, day))

    # ---------- walk-forward ----------
    pw = np.full(len(y), np.nan); pg = np.full(len(y), np.nan)
    models = {}
    for d in days[1:]:
        tr, te = day < d, day == d
        if tr.sum() < 5000 or te.sum() == 0: continue
        mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd < 1e-9, 1.0, sd)
        Xt = ((X[tr] - mu) / sd).astype(np.float32)
        w = fit_logistic(Xt, y[tr])
        pw[te] = predict(w, ((X[te] - mu) / sd).astype(np.float64))
        gm = gb_fit(Xt, y[tr])
        pg[te] = gb_predict(gm, ((X[te] - mu) / sd).astype(np.float32))
        models[d] = (mu, sd, w)
        print(f'  fit day {d}: train {int(tr.sum()):,} test {int(te.sum()):,}  '
              f'AUC logistic {auc(y[te], pw[te]):.4f}  AUC stumps {auc(y[te], pg[te]):.4f}  '
              f'[{time.time()-t0:.0f}s]', flush=True)
    sc = np.isfinite(pw)
    print(f'\nscored rows {int(sc.sum()):,} on {len(days)-1} days')
    print(f'  AUC  logistic {auc(y[sc], pw[sc]):.4f}   stumps {auc(y[sc], pg[sc]):.4f}   '
          f'own_ask alone {auc(y[sc], -X[sc, names.index("own_ask")]):.4f}   '
          f'p_side alone {auc(y[sc], X[sc, names.index("p_side")]):.4f}')

    # ---------- the margin grid ----------
    cands = collections.defaultdict(list)
    isup = z['is_up'][keep]
    # opp_lookup is keyed by (pass, THE OTHER SIDE'S flag) so that a candidate can find what the opposite
    # side would have filled at in the same pass - that is what prices the permutation flip.
    opp_lookup = {}
    for i in np.nonzero(sc)[0]:
        opp_lookup[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    for i in np.nonzero(sc)[0]:
        oq = opp_lookup.get((int(ts[i]), int(isup[i])), float('nan'))
        cands[int(ep[i])].append((int(ts[i]), float(pw[i]), float(X[i, names.index('own_ask')]),
                                  float(q[i]), float(y[i]), oq))
    nday = len({d for d in day[sc].tolist()})
    HDR = (f'  {"arm":30s}{"fires":>7}{"/day":>7}{"fills":>7}{"fill%":>7}{"win%":>7}{"per$1":>9}'
           f'{"total$":>9}{"H1":>8}{"H2":>8}{"permP":>7}')
    print(f'\n{"="*120}\nMARGIN GRID - decision on the QUOTED ask (no lookahead), money at the sim fill price\n{"="*120}')
    print(HDR)
    grid = {}
    for m in MARGINS:
        fr = first_fire(cands, m)
        sel = [(w, fq, t, oq) for (w, fq, t, oq) in fr.values()]
        nf = sum(1 for s in sel if s[1] == s[1])
        h1, h2 = halves(sel)
        wins = [s[0] for s in sel if s[1] == s[1]]
        tot = sum(10.0 * per1(w_, qq) for w_, qq, *_ in sel if qq == qq)
        grid[m] = (len(sel), nf, W(sel))
        print(f'  {f"EF-2 margin {m:.2f}":30s}{len(sel):>7}{len(sel)/max(nday,1):>7.0f}{nf:>7}'
              f'{100*nf/max(len(sel),1):>6.1f}%{100*np.mean(wins) if wins else float("nan"):>6.1f}%'
              f'{W(sel):>+9.3f}{tot:>+9.1f}{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
              f'{perm_opp(sel):>7.3f}' + ('  *n<60' if nf < MIN_CELL else ''))
    print(f'\n  LOOKAHEAD VARIANT (decision taken at the fill price) - reported only to size the difference:')
    print(HDR)
    for m in MARGINS:
        fr = first_fire(cands, m, use_fill=True)
        sel = [(w, fq, t, oq) for (w, fq, t, oq) in fr.values()]
        nf = sum(1 for s in sel if s[1] == s[1])
        wins = [s[0] for s in sel if s[1] == s[1]]
        h1, h2 = halves(sel)
        print(f'  {f"lookahead margin {m:.2f}":30s}{len(sel):>7}{len(sel)/max(nday,1):>7.0f}{nf:>7}'
              f'{100*nf/max(len(sel),1):>6.1f}%{100*np.mean(wins) if wins else float("nan"):>6.1f}%'
              f'{W(sel):>+9.3f}{0:>+9.1f}{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
              f'{perm_opp(sel):>7.3f}' + ('  *n<60' if nf < MIN_CELL else ''))

    # ---------- feature importance ----------
    print(f'\n{"="*120}\nFEATURE IMPORTANCE - |standardised coefficient|, averaged over the walk-forward fits\n{"="*120}')
    if models:
        A = np.mean([abs(w[1:]) for _, _, w in models.values()], axis=0)
        order = np.argsort(-A)
        print(f'  top 18 of {len(names)}:')
        for r, j in enumerate(order[:18], 1):
            tag = '  <- ASK DYNAMICS' if names[j] in ('d_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30') else \
                  '  <- the price itself' if names[j] in ('own_ask', 'opp_ask', '_ask_up', '_ask_dn', 'lv', 'p_venue') else \
                  '  <- the move' if names[j] in ('move_bps', 'mv_x_sec') else ''
            print(f'    {r:>2}. {names[j]:16s} {A[j]:.4f}{tag}')
        blocks = {'ask dynamics (d1,d5,d30,dip30)': ['d_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30'],
                  'the price (own_ask,opp_ask,lv,p_venue,_ask_up,_ask_dn)':
                      ['own_ask', 'opp_ask', 'lv', 'p_venue', '_ask_up', '_ask_dn'],
                  'the move (move_bps,mv_x_sec)': ['move_bps', 'mv_x_sec'],
                  'the engine model p (p_side)': ['p_side']}
        print(f'\n  block totals of |standardised coefficient| - V\'s question is the first two lines:')
        for lab, ks in blocks.items():
            tot = sum(A[names.index(k)] for k in ks if k in names)
            print(f'    {lab:56s} {tot:.4f}')
    print(f'\n[{time.time()-t0:.0f}s]')
