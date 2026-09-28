#!/usr/bin/env python3
"""Part 4 of the fire-time brief: can a SPOT-ONLY model find what the crowd does not see?

V, 09-28: model_v10.json's two largest inputs are move_bps +1.663 and lv +1.551 - lv being the VENUE's own
logit. The model half-copies the price, so it agrees with the crowd by construction. Test a model that cannot
see the price at all, and look only at the cells where it DISAGREES with the venue.

READ-ONLY on the Zurich research archive's decide_log. Labels are the venue's own resolution. Fills use
ef_persist's simulator. Master OFF, nothing live, nothing deployed.

DESIGN
  features   move_bps, mv_x_sec, imb20, ret5, ret30, ret60, rv60, basis_bps.   NO lv, NO p_venue.
             sec_left is in the brief but is not usable here: ef_persist's loader drops it, AND each model is
             fitted at one fixed second, where it is constant. Dropping a constant changes nothing.
             imb20 is carried because the brief names it, but see the ROBUSTNESS row - on this engine imb20
             looks like a VENUE book imbalance, not a spot feature, so the whole table is also reported
             without it. If the two disagree, the no-imb20 row is the one that answers the question asked.
  label      1 if the venue resolved UP. The model predicts P(UP), so p_side is symmetric by construction -
             p_DOWN = 1 - p_UP - unlike the engine's own p, and that is what lets a disagreement cell pick
             EITHER side rather than inheriting the engine's choice.
  walk-fwd   day k is fitted on days < k only, standardisation included (fitted on the training rows alone -
             the leakage EF_VETO had to fix). The first day is never scored.
  one row    per candle per second: the FIRST pass at exactly sec == S. ~4 passes land in each second.
  fit        ridge-regularised logistic, Newton steps, intercept unpenalised.
"""
import sys, math, random, collections, statistics as st, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef_persist import load, per1, cost, TICK, MIN_CELL, DELAY_MS, STAKE
from ef_fire_time import augment

SECS = (20, 30, 45, 60)
SPOT = ['move_bps', 'mv_x_sec', 'imb20', 'ret5', 'ret30', 'ret60', 'rv60', 'basis_bps']
CELLS = [(0.60, 0.50), (0.65, 0.45)]
DRAWS = 500


def fit_logistic(X, y, lam=1.0, iters=100):
    X = np.c_[np.ones(len(X)), X]
    w = np.zeros(X.shape[1])
    R = np.eye(X.shape[1]) * lam; R[0, 0] = 0.0
    for _ in range(iters):
        q = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        W = np.clip(q * (1 - q), 1e-9, None)
        H = X.T @ (X * W[:, None]) + R
        g = X.T @ (y - q) - R @ w
        try: step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError: break
        w += step
        if np.abs(step).max() < 1e-9: break
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


def auc(y, s):
    y = np.asarray(y, float); s = np.asarray(s, float)
    m = ~(np.isnan(s) | np.isnan(y)); y, s = y[m], s[m]
    if len(set(y.tolist())) < 2: return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def own(r, side):     return r['ua'] if side == 'UP' else r['da']
def opp(r, side):     return r['da'] if side == 'UP' else r['ua']
def own_later(r, side):
    return r['later'] if side == r['side'] else r.get('opp_later')
def opp_later(r, side):
    return r.get('opp_later') if side == r['side'] else r['later']


def sim_fill(r, side):
    a, l = own(r, side), own_later(r, side)
    if l is None or not (0.01 < a < 0.99): return None
    return l if l <= a + TICK + 1e-12 else None


def sim_fill_opp(r, side):
    a, l = opp(r, side), opp_later(r, side)
    if l is None or not (0.01 < a < 0.99): return None
    return l if l <= a + TICK + 1e-12 else None


def W(ent):
    fl = [e for e in ent if e['q'] is not None]
    if not fl: return float('nan')
    return sum(per1(e['win'], e['q']) * cost(e['q']) for e in fl) / sum(cost(e['q']) for e in fl)


def halves(ent):
    fl = sorted([e for e in ent if e['q'] is not None], key=lambda e: e['t'])
    h = len(fl) // 2
    return W(fl[:h]), W(fl[h:])


def perm_opp(ent, draws=DRAWS, seed=17):
    """V's control: a flipped draw is priced at the OPPOSITE side's real ask, same FAK test on both arms."""
    fl = [e for e in ent if e['q'] is not None]
    if not fl: return float('nan'), float('nan')
    real = W(fl); rng = random.Random(seed); sims = []
    for _ in range(draws):
        num = den = 0.0
        for e in fl:
            if rng.random() < 0.5:
                qo = sim_fill_opp(e['r'], e['side'])
                if qo is None: continue
                w, q = 1 - e['win'], qo
            else:
                w, q = e['win'], e['q']
            num += per1(w, q) * cost(q); den += cost(q)
        if den > 0: sims.append(num / den)
    if not sims: return float('nan'), float('nan')
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims), st.mean(sims)


if __name__ == '__main__':
    cand, names = load(); augment(cand)
    IDX = [names.index(k) for k in SPOT]
    NOIMB = [i for i, k in zip(IDX, SPOT) if k != 'imb20']
    days = sorted({r['day'] for rs in cand.values() for r in rs})
    print(f'candles {len(cand)}, days {days}; walk-forward scores {days[1:]} '
          f'({len(days)-1} of {len(days)} days), each fitted on the days before it')
    print(f'features ({len(SPOT)}): ' + ', '.join(SPOT) + '   |   EXCLUDED: lv, p_venue, sec_left')

    for tag, cols in (('spot-only (as briefed)', IDX), ('spot-only WITHOUT imb20', NOIMB)):
        print(f'\n{"="*140}\n{tag}\n{"="*140}')
        for S in SECS:
            rows = []
            for ep, rs in cand.items():
                at = [r for r in rs if r['sec'] == S]
                if not at: continue
                r = at[0]
                if r['feats'] is None or any(r['feats'][i] is None for i in cols): continue
                if not (0.01 < r['ua'] < 0.99 and 0.01 < r['da'] < 0.99): continue
                rows.append(r)
            if not rows: print(f'  S={S}: no usable rows'); continue
            X = np.array([[r['feats'][i] for i in cols] for r in rows], float)
            yUP = np.array([1.0 if (r['win'] == 1) == (r['side'] == 'UP') else 0.0 for r in rows])
            dt = np.array([r['day'] for r in rows])
            pred = np.full(len(rows), np.nan)
            ntr = {}
            for d in days[1:]:
                tr = dt < d; te = dt == d
                if tr.sum() < 50 or te.sum() == 0: continue
                mu, sd = X[tr].mean(0), X[tr].std(0); sd = np.where(sd < 1e-12, 1.0, sd)
                w = fit_logistic((X[tr] - mu) / sd, yUP[tr])
                pred[te] = predict(w, (X[te] - mu) / sd)
                ntr[d] = int(tr.sum())
            sc = ~np.isnan(pred)
            mid = np.array([(r['ua'] + (1 - r['da'])) / 2.0 for r in rows])
            a_spot, a_mid = auc(yUP[sc], pred[sc]), auc(yUP[sc], mid[sc])
            print(f'\n  S={S}s   scored rows {int(sc.sum())} of {len(rows)}   train n by day '
                  f'{ {k: v for k, v in ntr.items()} }')
            print(f'    (a) AUC spot-only {a_spot:.3f}   vs   AUC venue mid alone {a_mid:.3f}   '
                  f'gap {a_spot-a_mid:+.3f}  -> '
                  + ('the SPOT model discriminates better' if a_spot > a_mid else 'the VENUE MID discriminates better'))
            print(f'    (b) DISAGREEMENT cells - the spot model likes a side the venue prices cheap')
            print(f'        {"rule":24s}{"n cand":>7}{"fills":>6}{"fill%":>7}{"win%":>7}{"per$1":>9}'
                  f'{"H1":>8}{"H2":>8}{"permP":>7}{"ask":>7}')
            for PT, AT in CELLS:
                ent = []
                for r, p, ok in zip(rows, pred, sc):
                    if not ok: continue
                    for side in ('UP', 'DOWN'):
                        ps = p if side == 'UP' else 1 - p
                        a = own(r, side)
                        if ps >= PT and a <= AT:
                            ent.append(dict(r=r, side=side, ask=a, q=sim_fill(r, side), t=r['t'],
                                            win=1 if (r['win'] == 1) == (side == r['side']) else 0,
                                            day=r['day'], ep=r['ep']))
                            break
                if not ent:
                    print(f'        p>={PT:.2f} & ask<={AT:.2f}      0      -      -      -        -       -       -      -      -')
                    continue
                nf = sum(1 for e in ent if e['q'] is not None)
                h1, h2 = halves(ent); pp, pm = perm_opp(ent)
                wins = [e['win'] for e in ent if e['q'] is not None]
                print(f'        p>={PT:.2f} & ask<={AT:.2f} {len(ent):9d}{nf:6d}{100*nf/len(ent):6.1f}%'
                      f'{(100*np.mean(wins) if wins else float("nan")):6.1f}%{W(ent):+9.3f}'
                      f'{(h1 if h1==h1 else 0):+8.3f}{(h2 if h2==h2 else 0):+8.3f}{pp:7.3f}'
                      f'{np.mean([e["ask"] for e in ent]):7.3f}'
                      + ('  *n<60' if nf < MIN_CELL else ''))
