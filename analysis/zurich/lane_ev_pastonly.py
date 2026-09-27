#!/usr/bin/env python3
"""MAIN / REV new-EV grid on the Zurich window, priced with PAST-ONLY quotes. READ-ONLY.

V's grid (analysis/v/model/lane_ev_replay.py, 324c704) reports every column the owner asked for but
prices each call with the NEAREST tape row within +-5 s, which can be a future row. V's addition
(815c822) re-prices past-only but drops neg-days, +2c and the permutation. This puts the two together:
the full grid, past-only.

Why it matters here, measured rather than assumed: across the whole call stream only 1.6% (MAIN) and
0.3% (REVERSAL) of nearest-row prices came from a future row - yet 53 of the 102 calls R1 SELECTS in
MAIN were future-priced. R1 fires when the ask is low enough for the lane's p to clear breakeven, so
it seeks out exactly the rows the defect perturbs. A 1.6% contamination becomes 52% of the fires.

Rules and costs are V's, unchanged: cost(ask) = 1 + 0.07(1-ask); per$1 = (win/ask - cost)/cost;
R2/R3 walk-forward logistic fit on prior days only; permutation flips each side with p=0.5 and prices
a flipped trade at the OPPOSITE ask, so the permuted side carries no information.

Grading: results.actual. The venues snapshot on the branch ends 09-16 and covers NONE of this window,
so Polymarket's own oracle is unavailable here and no cross-check is claimed.
"""
import argparse, csv, sqlite3, bisect, math, numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--venues', required=True); ap.add_argument('--main', required=True); ap.add_argument('--rev', required=True)
ap.add_argument('--ages', default='0,1'); ap.add_argument('--sims', type=int, default=500)
a = ap.parse_args()

vc = sqlite3.connect(f'file:{a.venues}?mode=ro', uri=True)
Q = [(int(t), float(u), float(d)) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts')
     if u is not None and d is not None]
QT = [q[0] for q in Q]

def past_quote(ts, side, age):
    i = bisect.bisect_right(QT, ts) - 1
    if i < 0 or ts - QT[i] > age: return None
    u, d = Q[i][1], Q[i][2]
    return (u, d) if side == 'UP' else (d, u)

cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: (w / x - cost(x)) / cost(x)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

def load(fn, kind, age):
    out = []
    for r in csv.DictReader(open(fn)):
        if r['kind'] != kind: continue
        ep, sec = int(r['epoch']), int(r['sec'])
        q = past_quote(ep + sec, r['side'], age)
        if q is None: continue
        out.append(dict(epoch=ep, sec=sec, day=ep // 86400, p=float(r['p']),
                        ask=q[0], opp=q[1], win=int(r['win'])))
    return out

def fit(X, y, l2=1.0, it=300):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        pr = 1 / (1 + np.exp(-X @ w)); g = X.T @ (pr - y); R = np.eye(len(w)) * l2; R[0, 0] = 0
        H = X.T @ (X * (pr * (1 - pr))[:, None]) + R; w -= np.linalg.solve(H, g + R @ w)
    return w
pred = lambda w, X: 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ w)))
feats = lambda c, lane: [lg(c['ask']), c['sec'] / 300] + ([lg(c['p'])] if lane else [])

def first(C, ok):
    seen = {}
    for c in sorted(C, key=lambda c: (c['epoch'], c['sec'])):
        if c['epoch'] not in seen and ok(c): seen[c['epoch']] = c
    return [seen[e] for e in sorted(seen)]

def report(name, R, rng):
    if not R: print(f'  {name:36s} none'); return
    v = np.array([per1(c['win'], c['ask']) for c in R]); h = len(R) // 2
    days = {}
    for c, x in zip(R, v): days.setdefault(c['day'], []).append(x)
    neg = sum(1 for d in days.values() if np.mean(d) < 0)
    sims = [np.mean([per1(1 - c['win'], c['opp']) if fl else per1(c['win'], c['ask'])
                     for c, fl in zip(R, rng.random(len(R)) < 0.5)]) for _ in range(a.sims)]
    p_perm = float(np.mean(np.array(sims) >= v.mean()))
    slip = np.mean([per1(c['win'], min(.99, c['ask'] + .02)) for c in R])
    print(f'  {name:36s} n{len(R):5d}{"*" if len(R) < 60 else " "} hit {100*np.mean([c["win"] for c in R]):4.1f}% '
          f'ask {np.median([c["ask"] for c in R]):.2f} per$1 {v.mean():+.3f}  H1 {v[:h].mean():+.3f} H2 {v[h:].mean():+.3f}  '
          f'neg days {neg}/{len(days)}  +2c {slip:+.3f}  perm p {p_perm:.2f}')

for age in [int(x) for x in a.ages.split(',')]:
    print(f'\n{"="*40} PAST-ONLY QUOTE, age <= {age}s {"="*40}')
    for kind, fn in (('MAIN', a.main), ('REVERSAL', a.rev)):
        rng = np.random.default_rng(7)
        C = load(fn, kind, age); D = sorted({c['day'] for c in C})
        print(f'\n{kind}: {len(C)} calls on {len({c["epoch"] for c in C})} candles, {len(D)} days')
        report('R0 first call, ask<=0.90', first(C, lambda c: c['ask'] <= .90), rng)
        report('R1 lane p breakeven (live)',
               first(C, lambda c: c['ask'] <= .90 and c['p'] / (c['ask'] * cost(c['ask'])) - 1 >= 0), rng)
        if len(D) < 5:
            print(f'  R2/R3 walk-forward needs >3 prior days; this window has {len(D)} day buckets, '
                  f'so only {max(0,len(D)-3)} day(s) would be scored.')
        for lane in (True, False):
            pc = {}
            for d in D[3:]:
                tr = [c for c in C if c['day'] < d]; te = [c for c in C if c['day'] == d]
                if not tr or not te: continue
                w = fit(np.array([feats(c, lane) for c in tr]), np.array([c['win'] for c in tr]))
                for c, p in zip(te, pred(w, np.array([feats(c, lane) for c in te]))): pc[id(c)] = p
            for th in (0.0, 0.03, 0.05, 0.10, 0.15):
                tag = ('R2 calibrated lane+venue' if lane else 'R3 venue-only (null)') + f' ev>={th:.2f}'
                report(tag, first([c for c in C if id(c) in pc],
                                  lambda c: c['ask'] <= .90 and pc[id(c)] / (c['ask'] * cost(c['ask'])) - 1 >= th), rng)
        if len(D) > 3:
            report('R0 on the same walk-forward days',
                   first([c for c in C if c['day'] >= D[3]], lambda c: c['ask'] <= .90), rng)
