#!/usr/bin/env python3
"""The EF delay VETO, with the leakage fixed, on both selections — and exported so London can test it.
READ-ONLY. Zurich data, London untouched, nothing live.

V is right about the leak: `ef_delay_brain.featmat` standardised over ALL rows, so every fold's scaler saw
its own test day. It is only a mean/sd, so the effect is mild, but it is leakage and it is fixed here: the
scaler is fitted on the TRAINING rows of each fold alone and then applied to the test rows.

Target is the +250 ms delayed ask throughout, which is London's latency.

Two selections, both priced twice:
  (a) raw25   - first pass with raw EV >= 0.25 (what Zurich runs)
  (b) FIXED15 - first pass with Platt-calibrated EV >= 0.15 taken at ask + 1 tick, which is how London's
                engine judges it (poly_core.EV_REFERENCE_PAD). Judging it at the raw ask would loosen the
                bar ~0.02 and change which fires exist.
Pricing: (i) at the +250 ms delayed ask, (ii) through the London exec model - P(fill|win) 0.541,
P(fill|lose) 0.650, slippage p10/p50/p90 -1/+2/+11c on top of that delayed ask.

Export: analysis/zurich/ef_veto_brain.json carries the feature order, and for every fold (test day d,
trained on days < d) plus an all-days fit, the training-only scaler, the ridge weights and the train-day
list - enough for London to score its own real fills without re-deriving anything.
"""
import sqlite3, json, math, random, statistics as st, datetime as dt, collections, numpy as np
from decimal import Decimal, ROUND_CEILING
import sys
sys.path.insert(0, 'analysis/zurich')
from ef_delay_brain import load, cost, per1, be, lg, fit_ridge, pred, RATE, DELAYS

D_MS = 250
STAKE, RUNS, MIN_CELL = 10.0, 1000, 60
A, B, TICK, PAD = 1.0677, -0.3208, 0.01, 1
Dc = lambda x: Decimal(str(x))

def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A * z + B)))))

def ev_at_pad(q, ask):
    px = float((Dc(ask) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    c = max(px + f, px / (1 - f / px))
    return q / c - 1

def raw_matrix(rows, names):
    """UNSCALED features, in the exported order."""
    F = np.array([r['feats'] for r in rows], float)
    extra = np.array([[lg(r['ask']), lg(r['p_raw']), r['sec'] / 300.0] for r in rows], float)
    return np.c_[F, extra]

SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def price_delayed(sel):
    if not sel: return None
    num = sum(per1(r['win'], r[f'ask{D_MS}']) * cost(r[f'ask{D_MS}']) for r in sel)
    den = sum(cost(r[f'ask{D_MS}']) for r in sel)
    return num / den

def price_london(sel, seed=17, runs=RUNS):
    if not sel: return None, None
    rng = random.Random(seed); tots = []; spent = []
    for _ in range(runs):
        t = s = 0.
        for r in sel:
            if rng.random() > (0.541 if r['win'] else 0.650): continue
            px = min(0.99, max(0.01, r[f'ask{D_MS}'] + slip(rng))); sh = STAKE / px
            fee = RATE * sh * px * (1 - px); s += STAKE + fee
            t += (sh if r['win'] else 0) - STAKE - fee
        tots.append(t); spent.append(s)
    return (np.mean(tots) / max(1e-9, np.mean(spent))), float(np.mean(tots))

def halves(sel, fn):
    h = len(sel) // 2; s = sorted(sel, key=lambda r: r['t'])
    return (fn(s[:h]) if h else None), (fn(s[h:]) if len(s) - h else None)

def perm(sel, fn_flip, draws=600, seed=11):
    """A flip pays the OPPOSITE side's DELAYED ask (c299e19). Returns (p, mean, p95)."""
    if not sel: return (float('nan'),) * 3
    real = fn_flip(sel)
    rng = random.Random(seed); sims = []
    for _ in range(draws):
        alt = []
        for r in sel:
            if rng.random() < 0.5:
                q = min(0.99, max(0.01, 1 - r[f'ask{D_MS}'] + 0.01))
                alt.append(dict(r, win=1 - r['win'], **{f'ask{D_MS}': q}))
            else: alt.append(r)
        sims.append(fn_flip(alt))
    sims.sort()
    return sum(1 for x in sims if x >= real) / len(sims), st.mean(sims), sims[int(.95 * len(sims))]

if __name__ == '__main__':
    rows, names = load()
    feat_names = list(names) + ['logit_ask', 'logit_p_raw', 'sec_over_300']
    Xraw = raw_matrix(rows, names)
    y = np.array([per1(r['win'], r[f'ask{D_MS}']) for r in rows])
    dayarr = np.array([r['day'] for r in rows])
    days = sorted(set(dayarr))
    print(f'candidate passes {len(rows)} on {len({r["ep"] for r in rows})} candles, days {days}')
    print(f'features {len(feat_names)}: target = per$1 at the +{D_MS} ms delayed ask')

    # ---- walk-forward with the scaler fitted on TRAINING ROWS ONLY (V's leakage fix)
    folds = []
    p = np.full(len(rows), np.nan)
    for d in days[1:]:
        tr, te = dayarr < d, dayarr == d
        if tr.sum() < 500 or te.sum() == 0: continue
        mu, sd = Xraw[tr].mean(0), Xraw[tr].std(0)
        sd = np.where(sd < 1e-12, 1.0, sd)
        w = fit_ridge((Xraw[tr] - mu) / sd, y[tr])
        p[te] = pred(w, (Xraw[te] - mu) / sd)
        folds.append(dict(test_day=d, train_days=[x for x in days if x < d], n_train=int(tr.sum()),
                          n_test=int(te.sum()), mean=mu.tolist(), sd=sd.tolist(), weights=w.tolist()))
        print(f'  fold test {d}: trained on {len(folds[-1]["train_days"])} days, {tr.sum()} rows')
    mu_a, sd_a = Xraw.mean(0), Xraw.std(0); sd_a = np.where(sd_a < 1e-12, 1.0, sd_a)
    w_all = fit_ridge((Xraw - mu_a) / sd_a, y)
    export = dict(
        created=dt.datetime.now(dt.timezone.utc).isoformat(), target=f'per$1 at the +{D_MS} ms delayed ask',
        rule='fire/keep when predicted delayed EV >= 0 (sweep in EF_VETO.md; the exact bar is NOT established)',
        intercept_first=True, feature_names=feat_names,
        note=('weights[0] is the intercept; features are standardised with the fold mean/sd BEFORE the dot '
              'product. Scalers are fitted on TRAINING rows only. Use the fold whose train_days precede the '
              'day you are scoring, or all_days for a single frozen model.'),
        exec_model=dict(fill_win=0.541, fill_lose=0.650, slippage_cents_p10_p50_p90=[-1, 2, 11],
                        fee='0.07*shares*p*(1-p)'),
        folds=folds,
        all_days=dict(train_days=days, n_train=len(rows), mean=mu_a.tolist(), sd=sd_a.tolist(),
                      weights=w_all.tolist()))
    open('analysis/zurich/ef_veto_brain.json', 'w').write(json.dumps(export, indent=1))
    print(f'  exported analysis/zurich/ef_veto_brain.json: {len(folds)} folds + all_days, '
          f'{len(feat_names)} features')

    for r, pv in zip(rows, p): r['pred'] = pv
    sub = [r for r in rows if not np.isnan(r['pred'])]
    print(f'  scored rows {len(sub)} on {len({r["day"] for r in sub})} test days')

    def first_per_candle(rs, ok):
        seen = {}
        for r in sorted(rs, key=lambda r: (r['ep'], r['t'])):
            if r['ep'] not in seen and ok(r): seen[r['ep']] = r
        return [seen[e] for e in sorted(seen)]

    SELS = (('raw25  (Zurich: raw EV>=0.25)', lambda r: r['ev'] >= 0.25),
            ('FIXED15 (London: platt EV>=0.15 at ask+1)', lambda r: ev_at_pad(platt(r['p_raw']), r['ask']) >= 0.15))
    for lab, ok in SELS:
        fires = first_per_candle(sub, ok)
        print(f'\n{"="*132}\n{lab}: {len(fires)} fires on the scored days\n{"="*132}')
        print(f'  {"cell":28s}{"n":>5}{"":2s}{"hit":>7}{"delayed":>10}{"H1":>9}{"H2":>9}{"permP":>8}'
              f'{"permMean":>10}{"LONDON":>9}{"lonTot$":>9}')
        cells = (('KEEP  (pred >= 0)', [r for r in fires if r['pred'] >= 0]),
                 ('VETO  (pred <  0)', [r for r in fires if r['pred'] < 0]),
                 ('ALL fires', fires))
        for nm, sel in cells:
            if not sel: print(f'  {nm:28s}    0     (none)'); continue
            v = price_delayed(sel); a, b = halves(sel, price_delayed)
            pp, pm, _ = perm(sel, price_delayed)
            lon, tot = price_london(sel)
            print(f'  {nm:28s}{len(sel):5d}{"" if len(sel)>=MIN_CELL else " *":2s}'
                  f'{100*np.mean([r["win"] for r in sel]):6.1f}%{v:+10.3f}{(a or 0):+9.3f}{(b or 0):+9.3f}'
                  f'{pp:8.3f}{pm:+10.3f}{lon:+9.3f}{tot:+9.1f}')
        print(f'\n  PER DAY (delayed ask / London-exec per$1, n):')
        byday = collections.defaultdict(lambda: {'KEEP': [], 'VETO': []})
        for r in fires: byday[r['day']]['KEEP' if r['pred'] >= 0 else 'VETO'].append(r)
        print(f'    {"day":8s}{"keep n":>8}{"keep dly":>10}{"keep LON":>10}{"veto n":>8}{"veto dly":>10}{"veto LON":>10}')
        for d in sorted(byday):
            k, vv = byday[d]['KEEP'], byday[d]['VETO']
            kd = price_delayed(k); kl = price_london(k, runs=200)[0] if k else None
            vd = price_delayed(vv); vl = price_london(vv, runs=200)[0] if vv else None
            f2 = lambda x: f'{x:+10.3f}' if x is not None else f'{"-":>10}'
            print(f'    {d:8s}{len(k):>8}{f2(kd)}{f2(kl)}{len(vv):>8}{f2(vd)}{f2(vl)}')
