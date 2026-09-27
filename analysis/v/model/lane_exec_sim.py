#!/usr/bin/env python3
"""MAIN / REVERSAL under London-like execution (V, 09-27; owner: "simulate it as live ... order failure and slippage").

Input: the call streams written by lane_ev_replay.py (calls_main.csv, calls_rev.csv) + venues.sqlite3.
1. RE-PRICE every call with a PAST-ONLY quote (tape row at or before the call second, age <= --age s). lane_ev_replay's
   quote() takes the nearest row within +-5 s, which can be a FUTURE row - lookahead, worst in the fast last minute.
2. Rules, one trade per candle, first call where the rule holds: R0 ask<=0.90; R1 lane p breakeven (p/(ask*cost) >= 1).
3. Windows: 0-240 s (what London's order engine allows today), 240-295 s (MAIN only, the owner's question), all.
4. London execution (analysis/v/rawfixed/LONDON_EXEC_MODEL.md, 155 real EF fills): P(fill|would win) 54.1%,
   P(fill|would lose) 65.0%; slippage cents p10/p50/p90 -1/+2/+11 (piecewise-linear inverse CDF); fee 0.07*sh*p*(1-p);
   $10 stake; 1000 Monte Carlo runs. Caveat: the model is fitted on EF fills at asks 0.35-0.55; MAIN buys at ~0.8.
Output per cell: n, hit, paper per$1 (every order fills at the quote), London-exec expected per$1, expected total $,
p05/p95 of the total, halves of the paper series."""
import argparse, csv, sqlite3, bisect, random, numpy as np
ap = argparse.ArgumentParser(); ap.add_argument('--venues', required=True); ap.add_argument('--main', required=True)
ap.add_argument('--rev', required=True); ap.add_argument('--age', type=int, default=2); ap.add_argument('--runs', type=int, default=1000)
a = ap.parse_args()

vc = sqlite3.connect(a.venues)
Q = [(int(t), u, d) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts') if u is not None and d is not None]
QT = [q[0] for q in Q]
def past_quote(ts, side):
    i = bisect.bisect_right(QT, ts) - 1
    if i < 0 or ts - QT[i] > a.age: return None
    u, d = float(Q[i][1]), float(Q[i][2])
    return (u, d) if side == 'UP' else (d, u)

cost = lambda x: 1 + 0.07 * (1 - x)
per1 = lambda w, x: (w / x - cost(x)) / cost(x)
SLIP = [(0.10, -0.01), (0.50, 0.02), (0.90, 0.11)]
def slip(rng):
    u = rng.random(); (q1, v1), (q2, v2), (q3, v3) = SLIP
    if u <= q1: return v1
    if u >= q3: return v3
    return v1 + (v2 - v1) * (u - q1) / (q2 - q1) if u <= q2 else v2 + (v3 - v2) * (u - q2) / (q3 - q2)

def load(fn, kind):
    out = []
    for r in csv.DictReader(open(fn)):
        if r['kind'] != kind: continue
        ep, sec = int(r['epoch']), int(r['sec']); q = past_quote(ep + sec, r['side'])
        if q is None: continue
        out.append(dict(epoch=ep, sec=sec, day=ep // 86400, p=float(r['p']), ask=q[0], opp=q[1], win=int(r['win'])))
    return out

def first(C, ok):
    seen = {}
    for c in sorted(C, key=lambda c: (c['epoch'], c['sec'])):
        if c['epoch'] not in seen and ok(c): seen[c['epoch']] = c
    return [seen[e] for e in sorted(seen)]

def cell(name, R):
    if not R: print(f'  {name:32s} none'); return
    v = np.array([per1(c['win'], c['ask']) for c in R]); h = len(R) // 2; s = np.sort(v)
    rng = random.Random(11); tots = []; spent_all = []
    for _ in range(a.runs):
        tot = spent = 0.0
        for c in R:
            if rng.random() > (0.541 if c['win'] else 0.650): continue          # order refused / not filled
            px = min(0.99, max(0.01, c['ask'] + slip(rng))); sh = 10 / px; fee = 0.07 * sh * px * (1 - px)
            spent += 10 + fee; tot += (sh if c['win'] else 0) - 10 - fee
        tots.append(tot); spent_all.append(spent)
    tots = np.array(tots); ex = tots.mean() / max(1e-9, np.mean(spent_all))
    print(f'  {name:32s} n{len(R):4d}{"*" if len(R) < 60 else " "} hit {100*np.mean([c["win"] for c in R]):4.1f}% ask {np.median([c["ask"] for c in R]):.2f} '
          f'| paper {v.mean():+.3f} (H1 {v[:h].mean():+.3f} H2 {v[h:].mean():+.3f}, w/o top3 {s[:-3].mean():+.3f}) '
          f'| LONDON-EXEC {ex:+.3f}/$1, total ${tots.mean():+.1f} [p05 {np.percentile(tots,5):+.1f}, p95 {np.percentile(tots,95):+.1f}]')

R0 = lambda c: c['ask'] <= .90
R1 = lambda c: c['ask'] <= .90 and c['p'] / (c['ask'] * cost(c['ask'])) >= 1
for kind, fn in (('MAIN', a.main), ('REVERSAL', a.rev)):
    C = load(fn, kind); print(f'\n{kind}: {len(C)} calls with a past-only quote <= {a.age}s old')
    for wname, lo, hi in (('0-240 s', 0, 240), ('240-295 s', 241, 300), ('all', 0, 300)):
        W = [c for c in C if lo <= c['sec'] <= hi]
        for rname, rule in (('R0 first call', R0), ('R1 lane-p breakeven', R1)):
            cell(f'{wname:9s} {rname}', first(W, rule))
