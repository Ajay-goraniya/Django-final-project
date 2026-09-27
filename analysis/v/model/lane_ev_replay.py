#!/usr/bin/env python3
"""MAIN / REVERSAL: does a new EV logic make them pay? (V, 09-27, owner: "test new ev or better signal logics for main and rev")

Drives the REAL lane engine (learner/v12_2/poly_lanes.LaneEngine) over Binance 1 s klines + the 1 Hz Polymarket
tape, exactly as replay_lanes_1s.py does, but never places: every lane call is refused and its attempt counter reset,
so the lane keeps calling and we get the FULL stream of calls per candle (every read, its side, lane p, both asks).
Rules are then applied offline, one trade per candle = the first read where the rule says buy.

Rules (fixed before any result was seen):
  R0  as replayed so far: first call with ask <= 0.90 (LANE_MAX_ASK)
  R1  live EV logic: first call with p*(1)/cost - 1 >= 0 (LANE_EV_FLOOR = 0, breakeven on the lane's own p)
  R2  CALIBRATED EV (the Fixed idea that beat Raw on EF): walk-forward by day, logistic on
      [logit p_lane, logit ask, sec/300] fit on all PRIOR days' calls; buy first read with p_cal/cost - 1 >= theta
  R3  venue-only calibrated EV (null for R2): same, features [logit ask, sec/300] - does the lane's p add anything?
Fee: crypto taker 0.07*shares*p*(1-p). per$1 = (win/ask - 1 - 0.07(1-ask)) / (1 + 0.07(1-ask)).
Grading: venues.outcome (Polymarket's own resolution). Permutation flips the side and prices it at the OPPOSITE ask."""
import argparse, sqlite3, sys, os, bisect, math, csv, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'learner', 'v12_2'))
import poly_lanes as L

ap = argparse.ArgumentParser(); ap.add_argument('--klines', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--reads', type=int, default=2); ap.add_argument('--open', choices=('first', 'twap60'), default='twap60')
ap.add_argument('--calls', default='calls.csv')
ap.add_argument('--mode', choices=('main', 'rev'), default='main',
                help="main: MAIN refused every read (full MAIN stream). rev: MAIN called once then BLOCKED as on London (switch off,\n"
                     "prediction kept), so REVERSAL watches a fixed MAIN call exactly as live")
a = ap.parse_args()

rows = {int(ts // 1000): (o, h, l, cl, v, tb) for ts, o, h, l, cl, v, n, tb in
        sqlite3.connect(a.klines).execute('select ts,o,h,l,cl,v,n,tb from k1s')}
vc = sqlite3.connect(a.venues)
Q = [(int(t), u, d) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts')]; QT = [q[0] for q in Q]
OUT = {int(e): x for e, x in vc.execute('select epoch,actual from outcome')}
T = sorted(t for t in rows if QT[0] - 86400 <= t <= QT[-1])

def quote(ts):
    i = bisect.bisect_left(QT, ts - 5); best = None
    for j in range(i, min(len(Q), i + 6)):
        if abs(Q[j][0] - ts) <= 5 and Q[j][1] is not None and Q[j][2] is not None:
            if best is None or abs(Q[j][0] - ts) < abs(best[0] - ts): best = Q[j]
    return (float(best[1]), float(best[2])) if best else None

def twap60(ep):
    seg = [rows[t][3] for t in range(ep - 60, ep) if t in rows]
    return (sum(seg) / len(seg)) if len(seg) >= 45 else None

calls = []
if not os.path.exists(a.calls):
    eng = L.LaneEngine(); cur = None; closed_n = 0
    for ts in T:
        o, h, l, cl, v, tb = rows[ts]; ep = ts // 300 * 300; ms = ts * 1000
        if cur is None or cur['time'] != ep * 1000:
            if cur is not None: eng.on_closed_candle(cur); closed_n += 1
            line = twap60(ep)
            cur = dict(time=ep * 1000, open=(line if (a.open == 'twap60' and line) else o), high=h, low=l, close=cl, volume=0.0)
            if a.open == 'twap60': eng.set_line(line)
        cur['high'] = max(cur['high'], h); cur['low'] = min(cur['low'], l); cur['close'] = cl; cur['volume'] += v
        eng.on_candle(cur)
        if tb > 0: eng.on_spot_trade(ms, cl, tb, False)
        if v - tb > 0: eng.on_spot_trade(ms, cl, v - tb, True)
        if closed_n < 24: continue
        for k in range(a.reads):
            d = eng.evaluate(ms + k * (1000 // a.reads))
            if not d: continue
            q = quote(ts); act = OUT.get(ep)
            if q and act is not None and not (a.mode == 'rev' and d['kind'] == 'MAIN'):
                ask, opp = (q[0], q[1]) if d['side'] == 'UP' else (q[1], q[0])
                calls.append(dict(kind=d['kind'], epoch=ep, day=ep // 86400, sec=ts - ep, side=d['side'], p=round(float(d['p']), 5),
                                  ask=ask, opp=opp, win=int(act == d['side'])))
            if a.mode == 'rev' and d['kind'] == 'MAIN': eng.block('MAIN'); continue   # London: MAIN off, call kept
            eng.confirm(d['kind'], False, 'replay: stream only')       # refused -> lane keeps calling
            eng.main_attempts = 0; eng.reversal_attempts = 0          # never exhaust: we want every call
    with open(a.calls, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(calls[0].keys())); w.writeheader(); w.writerows(calls)
calls = [dict(r, epoch=int(r['epoch']), day=int(r['day']), sec=int(r['sec']), p=float(r['p']), ask=float(r['ask']),
              opp=float(r['opp']), win=int(r['win'])) for r in csv.DictReader(open(a.calls))]

cost = lambda x: 1 + 0.07 * (1 - x)
def per1(win, ask): return (win / ask - cost(ask)) / cost(ask)
lg = lambda x: math.log(min(max(x, 1e-3), 1 - 1e-3) / (1 - min(max(x, 1e-3), 1 - 1e-3)))

def fit(X, y, l2=1.0, it=300):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):                                           # Newton, ridge on non-intercept
        pr = 1 / (1 + np.exp(-X @ w)); g = X.T @ (pr - y); R = np.eye(len(w)) * l2; R[0, 0] = 0
        H = X.T @ (X * (pr * (1 - pr))[:, None]) + R; w -= np.linalg.solve(H, g + R @ w)
    return w
def pred(w, X): return 1 / (1 + np.exp(-(np.c_[np.ones(len(X)), X] @ w)))

def feats(c, lane): return [lg(c['ask']), c['sec'] / 300] + ([lg(c['p'])] if lane else [])

def first_per_candle(C, ok):
    seen = {};
    for c in sorted(C, key=lambda c: (c['epoch'], c['sec'])):
        if c['epoch'] not in seen and ok(c): seen[c['epoch']] = c
    return [seen[e] for e in sorted(seen)]

def report(name, R, rng=np.random.default_rng(7)):
    if not R: print(f'  {name:34s} none'); return
    v = np.array([per1(c['win'], c['ask']) for c in R]); h = len(R) // 2
    days = {}
    for c, x in zip(R, v): days.setdefault(c['day'], []).append(x)
    neg = sum(1 for d in days.values() if np.mean(d) < 0)
    # permutation: flip sides at random with the same flip rate as a coin; a flipped trade pays the OPPOSITE ask
    sims = []
    for _ in range(500):
        f = rng.random(len(R)) < 0.5
        sims.append(np.mean([per1(1 - c['win'], c['opp']) if fl else per1(c['win'], c['ask']) for c, fl in zip(R, f)]))
    p_perm = float(np.mean(np.array(sims) >= v.mean()))
    slip = np.mean([per1(c['win'], min(.99, c['ask'] + .02)) for c in R])
    print(f'  {name:34s} n{len(R):5d}{"*" if len(R)<60 else " "} hit {100*np.mean([c["win"] for c in R]):4.1f}% ask {np.median([c["ask"] for c in R]):.2f} '
          f'per$1 {v.mean():+.3f}  H1 {v[:h].mean():+.3f} H2 {v[h:].mean():+.3f}  neg days {neg}/{len(days)}  '
          f'+2c {slip:+.3f}  perm p {p_perm:.2f}')

for kind in (('MAIN',) if a.mode == 'main' else ('REVERSAL',)):
    C = [c for c in calls if c['kind'] == kind]; D = sorted({c['day'] for c in C})
    print(f'\n{kind}: {len(C)} calls on {len({c["epoch"] for c in C})} candles, {len(D)} days')
    report('R0 first call, ask<=0.90', first_per_candle(C, lambda c: c['ask'] <= .90))
    report('R1 lane p breakeven (live)', first_per_candle(C, lambda c: c['ask'] <= .90 and c['p'] / cost(c['ask']) / c['ask'] - 1 >= 0))
    for lane in (True, False):
        pc = {}
        for i, d in enumerate(D[3:], 3):                           # walk-forward: >= 3 prior days
            tr = [c for c in C if c['day'] < d]; te = [c for c in C if c['day'] == d]
            w = fit(np.array([feats(c, lane) for c in tr]), np.array([c['win'] for c in tr]))
            for c, p in zip(te, pred(w, np.array([feats(c, lane) for c in te]))): pc[id(c)] = p
        for th in (0.0, 0.03, 0.05, 0.10, 0.15):
            tag = ('R2 calibrated lane+venue' if lane else 'R3 venue-only (null)') + f' ev>={th:.2f}'
            report(tag, first_per_candle([c for c in C if id(c) in pc], lambda c: c['ask'] <= .90 and pc[id(c)] / c['ask'] / cost(c['ask']) - 1 >= th))
    report('R0 on the same walk-forward days', first_per_candle([c for c in C if c['day'] >= D[3]], lambda c: c['ask'] <= .90))
