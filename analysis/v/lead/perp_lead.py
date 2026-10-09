#!/usr/bin/env python3
"""Perp-vs-spot lead, two ways, from the same data.binance.vision aggTrades as build.py.
(1) cross-correlation of 10 ms and 1 ms log returns (xc10/xc1 saved by build.py), pooled over days;
(2) event timing: for every spot move >= X bps inside 1 s (build.py episodes), the time each tape first
    completes HALF the move (X/2 bps) from its own extreme (spot: the episode's start; perp: its own
    extreme in [start-500 ms, spot crossing]). lead = t_spot_cross - t_perp_cross (+ = perp first).
The same perp rule applied to SPOT itself is the placebo: it measures how much 'lead' the
asymmetric extreme search manufactures on its own. Perp stamps are ms (compared at +500 us, the middle of the ms), spot us."""
import sys, glob, os, json, numpy as np
here = os.path.dirname(os.path.abspath(__file__))
data = sys.argv[1]; out = sys.argv[2]
src = open(os.path.join(here, 'build.py')).read().split('\nfor day in a.days:')[0]
src = src.replace("a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)", "")
g = {}; exec(compile(src, 'build_defs', 'exec'), g)
files = sorted(glob.glob(os.path.join(data, '2026-*.npz')))
res = {'xc10': [], 'xc1': [], 'days': [], 'events': {}}
for f in files:
    day = os.path.basename(f)[:10]; z = np.load(f)
    res['days'].append(day); res['xc10'].append(z['xc10'].tolist()); res['xc1'].append(z['xc1'].tolist())
    sp, pp = g['load'](day)
    sts, slp = sp['ts'], np.log(sp['p']); pts, plp = pp['ts_raw'] + 500, np.log(pp['p'])
    for X in (2, 5, 10):
        rows = []
        for dr, x, st, dn in z['ev']:
            if x != X: continue
            i0 = np.searchsorted(sts, st, 'right'); i1 = np.searchsorted(sts, dn + 10_000, 'right')
            base = slp[max(i0 - 1, 0)]                      # spot last price at the episode start (its extreme)
            mv = dr * (slp[i0:i1] - base) * 1e4; c = np.flatnonzero(mv >= X / 2)
            if not len(c): continue
            ts_cross = sts[i0 + c[0]]
            pair = []
            for qts, qlp in ((pts, plp), (sts, slp)):          # perp, then PLACEBO: spot through the perp rule
                j0 = np.searchsorted(qts, st - 500_000, 'left'); j1 = np.searchsorted(qts, ts_cross, 'right')
                if j1 - j0 < 1: break
                seg = dr * qlp[j0:j1]; e = j0 + np.flatnonzero(seg == seg.min())[-1]
                j2 = np.searchsorted(qts, st + 2_000_000, 'right')
                mvp = dr * (qlp[e:j2] - qlp[e]) * 1e4; cp = np.flatnonzero(mvp >= X / 2)
                if not len(cp): break
                pair.append((ts_cross - qts[e + cp[0]]) / 1000.0)
            if len(pair) == 2: rows.append(pair)
        res['events'].setdefault(str(X), []).append(rows)
    print(day, {X: len(res['events'][str(X)][-1]) for X in ('2', '5', '10')}, flush=True)
json.dump(res, open(os.path.join(out, 'perp_lead.json'), 'w'))
