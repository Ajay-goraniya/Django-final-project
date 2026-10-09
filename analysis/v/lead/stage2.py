#!/usr/bin/env python3
"""Stage-2 line (V's settlement rule): what a >= 5 bps spot move is WORTH on the Polymarket settlement quantity,
closing TWAP60 (last 60 s of the candle) vs opening TWAP60 (60 s ending at the open; fixed before the candle starts).

(1) persistence: of every >= X bps-in-1 s spot episode (build.py), how much is still there 1/5/30/60 s after the start
    (log path rebuilt exactly as the cumulative sum of the 100 ms returns s_r100).
(2) weight on the closing TWAP60 of a move at second tau of the 300 s candle: w = 1 for tau <= 240, (300 - tau)/60 after.
(3) shift in P(side wins) = Phi((m + D*w)/sig) - Phi(m/sig), D = 5 bps x mean persistence at min(60 s, time left),
    m = projected margin of that side vs the line (bps), sig = sd of what is still unknown about the closing TWAP60
    under a random walk with the measured per-second vol s1:  tau <= 240: s1^2 * ((240 - tau) + 20);
    tau > 240: s1^2 * r^3 / (3 * 3600), r = 300 - tau.  Binance proxy only (Chainlink basis cancels in close - open)."""
import sys, os, glob, numpy as np
from math import erf, sqrt

data = sys.argv[1]
Phi = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
OFF = 0; files = sorted(glob.glob(os.path.join(data, '2026-*.npz')))
pers = {X: {h: [] for h in (1, 5, 30, 60)} for X in (5, 10)}; s1d = []
for f in files:
    z = np.load(f); nm = [str(x) for x in z['names']]
    r100 = np.nan_to_num(z['X'][:, nm.index('s_r100')].astype(np.float64)); lp = np.cumsum(r100)  # bps path
    s1d.append(np.std(lp[10::10][1:] - lp[10::10][:-1]))
    day0 = int(np.datetime64(os.path.basename(f)[:10] + 'T00:00:00', 'us').astype(np.int64))
    for dr, X, st, dn in z['ev']:
        if X not in pers: continue
        r0 = (st - day0) // 100_000
        for h in (1, 5, 30, 60):
            r1 = r0 + h * 10
            if r1 < len(lp): pers[X][h].append(dr * (lp[r1] - lp[r0]) / X)
s1 = float(np.median(s1d))
print(f'per-second spot vol (median of {len(s1d)} days): {s1:.3f} bps; per-day {np.round(s1d, 3).tolist()}\n')
print('### Persistence of the move (share of X still there h s after the episode start; mean / median)\n')
print('| X | n | 1 s | 5 s | 30 s | 60 s |'); print('|---|---|---|---|---|---|')
for X in pers:
    print(f'| {X} bps | {len(pers[X][1])} | ' + ' | '.join(f'{np.mean(pers[X][h]):.2f} / {np.median(pers[X][h]):.2f}' for h in (1, 5, 30, 60)) + ' |')
keep = {h: np.mean(pers[5][h]) for h in (1, 5, 30, 60)}
print('\n### Shift in P(the side the 5 bps move favours wins), probability points, by second of candle and margin\n')
print('m = that side\'s projected margin vs the opening line before the move (bps; negative = it is losing).\n')
M = [-20, -10, -5, 0, 5, 10, 20]; TAU = [60, 120, 180, 240, 255, 270, 285, 295]
print('| tau (s) | w | sig (bps) | ' + ' | '.join(f'm={m}' for m in M) + ' |'); print('|---' * (3 + len(M)) + '|')
for tau in TAU:
    left = 300 - tau
    hold = keep[60] if left >= 60 else keep[30] if left >= 30 else keep[5] if left >= 5 else keep[1]
    w = 1.0 if tau <= 240 else left / 60
    var = s1 ** 2 * ((240 - tau) + 20) if tau <= 240 else s1 ** 2 * left ** 3 / (3 * 3600)
    sig = sqrt(var); D = 5 * hold * w
    print(f'| {tau} | {w:.2f} | {sig:.2f} | ' + ' | '.join(f'{100 * (Phi((m + D) / sig) - Phi(m / sig)):+.1f}' for m in M) + ' |')

# what the model can actually catch after landing (latency.py alarm tables: +0.1..+0.4 bps mean), assumed to persist
print('\n### Shift in P(predicted side wins), probability points, for the move the alarms actually CATCH after +300 ms\n')
print('| tau (s) | sig (bps) | ' + ' | '.join(f'D={D} m={m}' for D in (0.1, 0.2, 0.4) for m in (-5, 0, 5)) + ' |'); print('|---' * 11 + '|')
for tau in TAU:
    left = 300 - tau; w = 1.0 if tau <= 240 else left / 60
    sig = sqrt(s1 ** 2 * ((240 - tau) + 20) if tau <= 240 else s1 ** 2 * left ** 3 / (3 * 3600))
    print(f'| {tau} | {sig:.2f} | ' + ' | '.join(f'{100 * (Phi((m + D * w) / sig) - Phi(m / sig)):+.1f}' for D in (0.1, 0.2, 0.4) for m in (-5, 0, 5)) + ' |')
