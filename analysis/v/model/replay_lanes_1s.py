#!/usr/bin/env python3
"""Drive the REAL lane engine (learner/v12_2/poly_lanes.LaneEngine) over stored data and price every
call on Polymarket's own book at that second, graded on Polymarket's own outcome.

Inputs: Binance 1 s klines (k1s: ts,o,h,l,cl,v,n,tb) -> two synthetic trades per second (taker-buy
volume as a buy, the rest as a sell); the 1 Hz venue tape (venues.q: poly_up/poly_dn asks); venues.outcome.
No depth stream is stored, so depth-derived features (imbalance, OFI, clusters) read zero - stated, not hidden.
Accepted iff ask(side) <= LANE_MAX_ASK; fee 1.67% both ways; one placement per kind per candle (confirm()).
Usage: replay_lanes_1s.py --klines k_*.sqlite3 --venues venues.sqlite3 [--reads 5] [--start EPOCH --end EPOCH] [--out rows.csv]"""
import argparse, sqlite3, sys, os, bisect, csv, statistics as st, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'learner', 'v12_2'))
import poly_lanes as L

ap = argparse.ArgumentParser(); ap.add_argument('--klines', nargs='+', required=True); ap.add_argument('--venues', required=True)
ap.add_argument('--reads', type=int, default=5); ap.add_argument('--start', type=int, default=0); ap.add_argument('--end', type=int, default=2**40)
ap.add_argument('--out', default=''); ap.add_argument('--cap', type=float, default=L.LANE_MAX_ASK)
ap.add_argument('--ef', action='store_true', help='enable the 12.22.0 EF reversal lane (poly_ef) with the Binance TWAP60 line')
ap.add_argument('--open', choices=('first', 'twap60'), default='first',
                help="the candle open the MAIN/REVERSAL lanes measure from: 'first' = Binance first trade (as shipped through 12.23.x); "
                     "'twap60' = the settlement line, TWAP60 ending at the open (Polymarket settles TWAP60 close vs TWAP60 open)")
a = ap.parse_args()
FEE = 0.0167

rows = {}
for kp in a.klines:
    for ts, o, h, l, cl, v, n, tb in sqlite3.connect(kp).execute('select ts,o,h,l,cl,v,n,tb from k1s'):
        rows[int(ts // 1000)] = (o, h, l, cl, v, tb)
T = sorted(t for t in rows if a.start <= t < a.end)
vc = sqlite3.connect(a.venues)
Q = [(int(t), u, d) for t, u, d in vc.execute('select ts,poly_up,poly_dn from q order by ts')]
QT = [q[0] for q in Q]
OUT = {int(e): x for e, x in vc.execute('select epoch,actual from outcome')}
def quote(ts, side):
    i = bisect.bisect_left(QT, ts - 5); best = None
    for j in range(i, min(len(Q), i + 6)):
        if abs(Q[j][0] - ts) <= 5:
            v = Q[j][1] if side == 'UP' else Q[j][2]
            if v is not None and (best is None or abs(Q[j][0] - ts) < abs(best[0] - ts)): best = (Q[j][0], float(v))
    return best[1] if best else None

from collections import Counter
blocks = Counter(); dbg = []; GRID = (0.30, 0.35, 0.40, 0.45, 0.50, 0.56, 0.60); gfired = set(); grid_rows = []
eng = L.LaneEngine(); trades = []; cur = None; closed_n = 0
eng.ef_enabled = bool(a.ef); now_ts = [0]
eng.ef_quote = lambda side: quote(now_ts[0], side)
def twap60(ep):
    seg = [rows[t][3] for t in range(ep - 60, ep) if t in rows]
    return (sum(seg) / len(seg)) if len(seg) >= 45 else None
for ts in T:
    o, h, l, cl, v, tb = rows[ts]; ep = ts // 300 * 300; ms = ts * 1000; now_ts[0] = ts
    if cur is None or cur['time'] != ep * 1000:
        if cur is not None: eng.on_closed_candle(cur); closed_n += 1
        line = twap60(ep)                                       # the settlement line: TWAP60 ending at the open
        cur = dict(time=ep * 1000, open=(line if (a.open == 'twap60' and line) else o), high=h, low=l, close=cl, volume=0.0)
        if a.ef: eng.set_line(line)
    cur['high'] = max(cur['high'], h); cur['low'] = min(cur['low'], l); cur['close'] = cl; cur['volume'] += v
    eng.on_candle(cur)
    if tb > 0: eng.on_spot_trade(ms, cl, tb, False)
    if v - tb > 0: eng.on_spot_trade(ms, cl, v - tb, True)     # same instant: a 500 ms flow bucket sees the NET of the second
    if closed_n < 24: continue                                  # volume_ratio needs the closed-candle median
    for k in range(a.reads):
        d = eng.evaluate(ms + k * (1000 // a.reads))
        if a.ef and eng.ef.fired is None: blocks[eng.ef.block.split(' ')[0] + (' ' + eng.ef.block.split(' ')[1] if eng.ef.block.startswith('gate') else '')] += 1
        if a.ef and k == 0 and ts % 10 == 0 and eng.ef.last: dbg.append(dict(eng.ef.last, sigma=L.poly_ef.sigma_per_root_second(eng.price_history, ts)))
        # the whole grid over the classifier's own real-reversal score (the anchor is 0.56): at the first read
        # of a candle where real >= theta AND the price rule holds, record one call per theta. Reported whole.
        m = eng.ef.last if a.ef else None
        if m and L.poly_ef.EF_MIN_PHASE_S <= m['phase'] <= L.poly_ef.EF_LAST_PHASE_S:
            askg = quote(ts, m['ef_dir'])
            if askg is not None and askg <= L.poly_ef.EF_MAX_ASK and m['settlement_probability'] >= min(0.98, askg + L.poly_ef.EF_EV_MARGIN + askg * 0.02):
                for th in GRID:
                    if m['real'] >= th and (ep, th) not in gfired:
                        gfired.add((ep, th)); act = OUT.get(ep)
                        grid_rows.append(dict(theta=th, epoch=ep, sec=ts - ep, side=m['ef_dir'], ask=askg, actual=act, win=(None if act is None else int(act == m['ef_dir']))))
        if not d: continue
        ask = quote(ts, d['side'])
        if ask is None: eng.confirm(d['kind'], False, 'no venue quote'); continue
        if ask > a.cap + 1e-9: eng.confirm(d['kind'], False, 'above cap'); continue
        eng.confirm(d['kind'], True)
        act = OUT.get(ep)
        trades.append(dict(epoch=ep, ts=ts, sec=ts - ep, kind=d['kind'], side=d['side'], ask=ask, p=d.get('p'), actual=act,
                           win=(None if act is None else int(act == d['side']))))
print(f'seconds {len(T)} candles ~{len(T)//300} closed {closed_n}; venue tape rows {len(Q)}; outcomes {len(OUT)}; placements {len(trades)}')
if a.ef:
    print('EF block census (reads):', ', '.join(f'{k} {n}' for k, n in blocks.most_common(8)))
    if dbg:
        qs = lambda k: ' '.join(f'{x:.2f}' for x in np.percentile([d[k] for d in dbg], [10, 50, 90]))
        print('EF metric p10/p50/p90 over', len(dbg), 'samples:', ' | '.join(f'{k} {qs(k)}' for k in ('sigma', 'body', 'distance', 'reachability', 'opposite_flow', 'old_flow', 'new_eff', 'old_eff', 'rejection', 'recovery', 'path_quality', 'control_transfer', 'old_side_exhaustion', 'persistence', 'settlement_feasibility', 'real', 'fake', 'chop', 'extension_sigma')))
if a.out:
    with open(a.out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(trades[0].keys()) if trades else ['epoch']); w.writeheader(); w.writerows(trades)
def per1(t): return ((1 - FEE) / t['ask'] - 1) if t['win'] else (-1 - FEE)
if a.ef:
    print('EF real-score grid (first read per candle with the price rule true; * = n<60):')
    print(' theta    n   hit   ask_med sec_med per$1   H1     H2')
    for th in GRID:
        R = sorted([t for t in grid_rows if t['theta'] == th and t['win'] is not None], key=lambda t: t['epoch'])
        if not R: print(f' {th:.2f}  none'); continue
        h = len(R) // 2; v = [per1(t) for t in R]; f = lambda z: (st.mean(z) if z else float('nan'))
        print(f' {th:.2f} {len(R):4d} {100*st.mean(t["win"] for t in R):5.1f}%  {st.median(t["ask"] for t in R):.2f}   {st.median(t["sec"] for t in R):4.0f}  {f(v):+.3f} {f(v[:h]):+.3f} {f(v[h:]):+.3f}{"*" if len(R)<60 else ""}')
    if a.out:
        with open(a.out.replace('.csv', '_grid.csv'), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=['theta', 'epoch', 'sec', 'side', 'ask', 'actual', 'win']); w.writeheader(); w.writerows(grid_rows)
for kind in ('MAIN', 'REVERSAL', 'EF'):
    R = [t for t in trades if t['kind'] == kind and t['win'] is not None]
    if not R: print(f'{kind}: none'); continue
    h = len(R) // 2; v = [per1(t) for t in R]
    f = lambda z: (st.mean(z) if z else float('nan'))
    print(f'{kind}: n={len(R)} hit={100*st.mean(t["win"] for t in R):.1f}% ask_med={st.median(t["ask"] for t in R):.2f} sec_med={st.median(t["sec"] for t in R):.0f} '
          f'per$1={f(v):+.3f} H1={f(v[:h]):+.3f} H2={f(v[h:]):+.3f}{"*" if len(R)<60 else ""}')
    for lo, hi in ((0, .3), (.3, .5), (.5, .7), (.7, 1.01)):
        S = [t for t in R if lo <= t['ask'] < hi]
        if S: print(f'   ask {lo:.1f}-{hi:.1f}: n={len(S)} hit={100*st.mean(t["win"] for t in S):.0f}% per$1={f([per1(t) for t in S]):+.3f}{"*" if len(S)<60 else ""}')
