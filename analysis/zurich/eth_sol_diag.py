#!/usr/bin/env python3
"""WHY is the ETH/SOL EF shadow negative at 24 h? READ-ONLY on my own shadow DBs. Nothing live.

The 09-28 ledger put three of four arms under water (eth frozen -0.068, sol frozen -0.266, eth platt -0.254,
sol platt +0.093). "It loses" is not a finding; the question is whether the MODEL is wrong on these coins or
whether the fill is. Labels are the venue's own resolution (results.src = gamma.outcomePrices), per the
standing settlement rule.

Five diagnostics, the same ones that worked on BTC:
  1 CALIBRATION   p_side in buckets against the realised win rate. Over-confidence is a model problem.
  2 ASK vs MODEL  AUC of p_side against the win, beside AUC of (1 - ask), which is the venue's own opinion.
                  REV_BRAIN found 31 live features at AUC 0.431 against the venue ask alone at 0.725. If that
                  repeats here, the model is not adding to the price and no amount of staking fixes it.
  3 EV MONOTONE   per $1 by EV bucket. If EV means anything, higher EV pays more. It is the cheapest test of
                  whether the whole quantity is real.
  4 FILL          slip and book_age_s on fires, and per $1 by book age.
  5 SEC           per $1 by second-in-candle, because EF's edge on BTC is concentrated in time.
"""
import sqlite3, collections, numpy as np

ARMS = [('eth frozen', 'shadow_eth'), ('sol frozen', 'shadow_sol'),
        ('eth platt', 'shadow_eth_platt'), ('sol platt', 'shadow_sol_platt')]
RATE = 0.07

def load(tag):
    c = sqlite3.connect(f'file:/home/ubuntu/pm_multi/{tag}.sqlite3?mode=ro', uri=True); c.row_factory = sqlite3.Row
    o = {r['epoch']: r for r in c.execute('SELECT * FROM orders')}
    out = []
    for r in c.execute('SELECT * FROM results ORDER BY epoch'):
        q = o.get(r['epoch'])
        if q is None or r['actual'] is None: continue
        cost = (q['spent'] or 0) + (q['fees'] or 0)
        if cost <= 0: continue
        out.append(dict(ep=r['epoch'], win=1 if q['side'] == r['actual'] else 0, p=q['p_side'],
                        ask=q['ask'], fill=q['fill_price'], slip=q['slip'] or 0.0, ev=q['ev'],
                        sec=q['sec'], age=q['book_age_s'], cost=cost, pay=r['payout'] or 0.0,
                        sz=q['ask_sz'], depth=q['depth_at_cap'], src=r['src']))
    return out

def auc(y, s):
    y = np.asarray(y, float); s = np.asarray(s, float)
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    if len(set(y.tolist())) < 2: return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def per1(rs):
    if not rs: return float('nan')
    return sum(r['pay'] - r['cost'] for r in rs) / sum(r['cost'] for r in rs)

def band(rs, key, edges, lab):
    print(f'    {lab}')
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = [r for r in rs if r[key] is not None and lo <= r[key] < hi]
        if not s: print(f'      [{lo:>6.3g},{hi:<6.3g}) n     0'); continue
        print(f'      [{lo:>6.3g},{hi:<6.3g}) n {len(s):5d}  win {100*np.mean([r["win"] for r in s]):5.1f}%  '
              f'mean p {np.mean([r["p"] for r in s]):.3f}  per$1 {per1(s):+7.3f}'
              + ('  *n<60' if len(s) < 60 else ''))

DATA = {}
for lab, tag in ARMS:
    DATA[lab] = load(tag)
    print(f'{lab:11s} graded fires {len(DATA[lab]):4d}  per$1 {per1(DATA[lab]):+7.3f}  '
          f'src {sorted({r["src"] for r in DATA[lab]})}')
pool = {'ETH (both arms)': DATA['eth frozen'] + DATA['eth platt'],
        'SOL (both arms)': DATA['sol frozen'] + DATA['sol platt'],
        'ALL FOUR ARMS': sum(DATA.values(), [])}

for lab, rs in pool.items():
    if not rs: continue
    print(f'\n{"="*104}\n{lab}: n {len(rs)}, per$1 {per1(rs):+.3f}, win {100*np.mean([r["win"] for r in rs]):.1f}%\n{"="*104}')
    print('  1 CALIBRATION - the model says p, the market delivers:')
    band(rs, 'p', [0.0, 0.3, 0.4, 0.5, 0.6, 0.75, 1.01], 'p_side bucket')
    mp = np.mean([r['p'] for r in rs]); mw = np.mean([r['win'] for r in rs])
    print(f'      OVERALL mean p {mp:.3f} vs realised {mw:.3f}  ->  over-confident by {100*(mp-mw):+.1f} pp')
    a_p, a_ask = auc([r['win'] for r in rs], [r['p'] for r in rs]), auc([r['win'] for r in rs], [1 - r['ask'] for r in rs])
    print(f'  2 ASK vs MODEL - AUC of p_side {a_p:.3f}   AUC of (1-ask) {a_ask:.3f}   '
          + ('the MODEL discriminates better' if a_p > a_ask else 'the VENUE ASK discriminates better')
          + f'  (gap {a_p-a_ask:+.3f})')
    print('  3 EV MONOTONE - does a bigger EV pay more?')
    band(rs, 'ev', [0.0, 0.3, 0.5, 0.8, 1.2, 99.], 'ev bucket')
    sl = np.array([r['slip'] for r in rs], float); ag = np.array([r['age'] for r in rs], float)
    print(f'  4 FILL - slip mean {100*sl.mean():+.2f}c p90 {100*np.percentile(sl,90):+.2f}c max {100*sl.max():+.2f}c; '
          f'book_age_s p50 {np.median(ag):.2f} p90 {np.percentile(ag,90):.2f} max {ag.max():.2f}')
    band(rs, 'age', [0.0, 1.0, 2.0, 3.01], 'book age bucket (s)')
    print('  5 SEC - where in the candle:')
    band(rs, 'sec', [0, 60, 120, 180, 241], 'second-in-candle')

# ---- 6. the honest out-of-sample version of the obvious fix ---------------------------------------
# The diagnosis above says the LEVEL of p is wrong, not its ranking. The obvious fix is a recalibration.
# What is NOT allowed is fitting one on all 620 fires and quoting the result. So: fit a Platt shrink on one
# half's (p, win) pairs, apply it to the OTHER half, and keep only the fires whose recalibrated p still
# clears the bar. This can only VETO existing fires - the non-fired passes are not in these DBs - so it is a
# veto test, the same shape as EF_VETO, and it is reported in both directions.
print(f'\n{"="*104}\n6 OUT-OF-SAMPLE RECALIBRATION AS A VETO (fit one half, veto the other)\n{"="*104}')

def fit_platt(rs, iters=200):
    """Logistic regression of win on logit(p), Newton steps. Returns (a, b) for p' = sigmoid(a*logit(p)+b)."""
    z = np.array([np.log(min(max(r['p'], 1e-3), 1 - 1e-3) / (1 - min(max(r['p'], 1e-3), 1 - 1e-3))) for r in rs])
    y = np.array([r['win'] for r in rs], float)
    X = np.c_[z, np.ones(len(z))]; w = np.zeros(2)
    for _ in range(iters):
        q = 1 / (1 + np.exp(-(X @ w)))
        W = np.clip(q * (1 - q), 1e-9, None)
        H = X.T @ (X * W[:, None]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, X.T @ (y - q))
        w += step
        if np.abs(step).max() < 1e-10: break
    return float(w[0]), float(w[1])

def apply_platt(p, a, b):
    z = np.log(min(max(p, 1e-3), 1 - 1e-3) / (1 - min(max(p, 1e-3), 1 - 1e-3)))
    return 1 / (1 + np.exp(-(a * z + b)))

be = lambda ask: ask * (1 + RATE * (1 - ask))
for lab, rs in pool.items():
    rs = sorted(rs, key=lambda r: r['ep'])
    if len(rs) < 120: continue
    h = len(rs) // 2
    print(f'\n  {lab}  n {len(rs)}, unfiltered per$1 {per1(rs):+.3f}')
    for nm, tr, te in (('fit H1 -> veto H2', rs[:h], rs[h:]), ('fit H2 -> veto H1', rs[h:], rs[:h])):
        a, b = fit_platt(tr)
        mp = np.mean([r['p'] for r in tr]); mw = np.mean([r['win'] for r in tr])
        kept = [r for r in te if (apply_platt(r['p'], a, b) / be(r['ask']) - 1) >= 0.25]
        print(f'    {nm}: a {a:+.4f} b {b:+.4f} (train mean p {mp:.3f} vs win {mw:.3f})')
        print(f'      test n {len(te)} per$1 {per1(te):+.3f}  ->  kept {len(kept)} '
              f'({100*len(kept)/len(te):.0f}%) per$1 {per1(kept):+.3f}'
              + ('  *kept n<60, not a reading' if len(kept) < 60 else '')
              + ('   the veto HELPS' if kept and per1(kept) > per1(te) else '   the veto does NOT help'))
        if kept:
            k = sorted(kept, key=lambda r: r['ep']); m = len(k) // 2
            print(f'      kept halves {per1(k[:m]):+.3f} / {per1(k[m:]):+.3f}'
                  + ('   SIGN FLIPS' if m and per1(k[:m]) * per1(k[m:]) < 0 else ''))
