#!/usr/bin/env python3
"""M22 (V, 10-02) - WHERE IS THE MARKET'S PRICE WRONG? Calibration of real prints vs the venue's resolution.
No fill model: a TAKER who buys when a print shows the price in a band pays (that print + slip) + taker fee.
Grid FIXED before running, all cells reported: price band (0.05 wide, 0.30..0.95) x second window
{0-60, 60-120, 120-180, 180-240, 240-290} x calm {calm, not}, two independent periods (09-11..22, 09-23..10-01).
Per candle and window: the FIRST print on either token inside the band (one entry per candle per cell).
Entry = NEXT print on that token at least 1 s later (latency-honest) + slip; fee 0.07*p*(1-p).
usage: m22_calib.py <bn1s json files,> <tape glob,tape glob>"""
import sys, json, glob, gzip, math
import numpy as np

BN = {}
for f in sys.argv[1].split(','): BN.update({int(k): float(v) for k, v in json.load(open(f)).items()})
TP = {}
for g in sys.argv[2].split(','):
    for f in glob.glob(g):
        for k, v in json.load(gzip.open(f)).items():
            if 'p' in v and 'up_won' in v: TP[int(k)] = v
P1 = (1789084800, 1790121600); P2 = (1790121600, 1790899200)
SLIP = 0.01
MODE = sys.argv[3] if len(sys.argv) > 3 else 'next'  # next | max5 (worst print in the next 5 s: pessimistic)
BANDS = [round(0.30 + 0.05 * i, 2) for i in range(13)]  # lower edges 0.30..0.90
WINS = [(0, 60), (60, 120), (120, 180), (180, 240), (240, 290)]

rows = []  # (period, calm, win_idx, band_lo, won, entry)
for e in sorted(TP):
    per = 1 if P1[0] <= e < P1[1] else 2 if P2[0] <= e < P2[1] else 0
    if not per: continue
    raw = [BN[t] for t in range(e - 300, e) if t in BN]
    if len(raw) < 240: continue
    calm = float(np.std(np.diff(np.log(raw)))) * 1e4 < 0.304
    pr = {0: [], 1: []}
    for t, tok, p, sz in TP[e]['p']:
        s = t - e
        if 0 <= s < 300: pr[int(tok)].append((s, p))
    for tok in (0, 1): pr[tok].sort()
    up = TP[e]['up_won']
    for wi, (a, b) in enumerate(WINS):
        for lo in BANDS:
            hi = lo + 0.05
            hit = None
            for tok in (0, 1):
                for s, p in pr[tok]:
                    if a <= s < b and lo <= p < hi:
                        if hit is None or s < hit[0]: hit = (s, tok)
                        break
            if hit is None: continue
            s0, tok = hit
            nxt = [p for s, p in pr[tok] if s >= s0 + 1]
            if not nxt: continue
            if MODE == 'max5':
                w5 = [p for s, p in pr[tok] if s0 + 1 <= s <= s0 + 5]
                if not w5: continue
                entry = min(max(w5) + SLIP, 0.99)
            else:
                entry = min(nxt[0] + SLIP, 0.99)
            won = (up == 1) == (tok == 1)
            rows.append((per, calm, wi, lo, won, entry, e))

print(f'M22 [{MODE}]: {len(rows)} entries. calm share of candles used shown per cell. * = n<60 INSUFFICIENT')


def cell(R):
    if not R: return None
    n = len(R); w = np.mean([r[4] for r in R])
    cost = sum(r[5] + 0.07 * r[5] * (1 - r[5]) for r in R)
    pnl = sum((1 if r[4] else 0) - r[5] - 0.07 * r[5] * (1 - r[5]) for r in R)
    h = sorted(R, key=lambda r: r[6]); k = n // 2
    hs = [sum((1 if r[4] else 0) - r[5] - 0.07 * r[5] * (1 - r[5]) for r in x) for x in (h[:k], h[k:])]
    return n, w, np.mean([r[5] for r in R]), pnl / cost, hs


for calm in (True, False):
    print(f'\n===== {"CALM (vol<0.304)" if calm else "NOT CALM"} =====  per cell: n win% avg_entry pnl/$ [half1 $/half2 $]')
    for wi, (a, b) in enumerate(WINS):
        print(f'-- sec {a}-{b}')
        for lo in BANDS:
            out = []
            for per in (1, 2):
                c = cell([r for r in rows if r[0] == per and r[1] == calm and r[2] == wi and r[3] == lo])
                out.append('  -' if c is None else
                           f'{c[0]:4d} {c[1]*100:5.1f} {c[2]:.3f} {c[3]:+.3f}{"*" if c[0] < 60 else " "} [{c[4][0]:+6.1f}/{c[4][1]:+6.1f}]')
            print(f'  {lo:.2f}-{lo+0.05:.2f} | P1 {out[0]:42s} | P2 {out[1]}')
