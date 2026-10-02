#!/usr/bin/env python3
"""M20 (V, 10-02) - WHY does the live maker probe win while M19 is flat live? Diagnostic, not a new rule.
Grid FIXED before running: pricing {fair (M19, m=0.15, 1 s feed delay), mkt (join: last print - 1c)} x
4 probe ingredients on/off {band 0.60-0.80, calm vol<0.304 (poly_fav definition), sec 60-180,
cancel if Binance moved >=2 bps against the side in the last known second} = 32 cells, ALL reported,
two independent periods (09-11..22, 09-23..10-01), halves within each. Fill = a print strictly below
our bid (same rule as M19), hold to settlement, venue outcome, 5 shares, no fee (maker).
usage: m20_whymaker.py <bn1s json files,> <tape glob,tape glob>"""
import sys, json, glob, gzip, math, itertools
import numpy as np

BN = {}
for f in sys.argv[1].split(','): BN.update({int(k): float(v) for k, v in json.load(open(f)).items()})
TP = {}
for g in sys.argv[2].split(','):
    for f in glob.glob(g):
        for k, v in json.load(gzip.open(f)).items():
            if 'p' in v and 'up_won' in v: TP[int(k)] = v
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
K, M = 1.4, 0.15
CB = 2.0
P1 = (1789084800, 1790121600)  # 09-11 .. 09-23
P2 = (1790121600, 1790899200)  # 09-23 .. 10-02


def series(a, b):
    out, last = [], None
    for t in range(a, b + 1): last = BN.get(t, last); out.append(last)
    return out


C = []
for e in sorted(TP):
    if not (P1[0] <= e < P2[1]): continue
    s = series(e - 300, e + 299)
    if any(x is None for x in s): continue
    raw = [BN[t] for t in range(e - 300, e) if t in BN]  # poly_fav: present points only, >=240
    if len(raw) < 240: continue
    r = np.diff(np.log(raw)); vol = float(np.std(r)) * 1e4
    lr = np.diff(np.log(s)); cur = s[300:]
    pr = {0: {}, 1: {}}
    for t, tok, p, sz in TP[e]['p']:
        sec = int(t) - e
        if -60 <= sec < 300: pr[int(tok)].setdefault(sec, []).append(p)
    f = []
    for t in range(300):
        n = min(t + 1, 60); O = sum(cur[:n]) / n
        sig = float(np.std(lr[t:t + 300])) or 1e-6
        f.append(Phi(math.log(cur[t] / O) / (K * sig * math.sqrt(max(300 - t, 1)))))
    C.append(dict(e=e, up=TP[e]['up_won'], cur=cur, vol=vol, pr=pr, f=f))
print(f'M20: {len(C)} candles. P1 {sum(P1[0] <= c["e"] < P1[1] for c in C)}  P2 {sum(P2[0] <= c["e"] < P2[1] for c in C)}')
print(f'calm share (vol<0.304): {np.mean([c["vol"] < 0.304 for c in C]) * 100:.1f}%')


def run(S, pricing, band, calm, win, cancel):
    out = []
    for c in S:
        if calm and c['vol'] >= 0.304: continue
        lastp = {0: None, 1: None}
        for t in range(-60, 30):
            for tok in (0, 1):
                if c['pr'][tok].get(t): lastp[tok] = c['pr'][tok][t][-1]
        done = {0: False, 1: False}
        lo, hi = (60, 180) if win else (30, 270)
        for t in range(30, 271):
            for tok in (0, 1):
                prev = lastp[tok]
                if c['pr'][tok].get(t - 1): lastp[tok] = c['pr'][tok][t - 1][-1]
            if not (lo <= t <= hi): continue
            mv = math.log(c['cur'][t - 1] / c['cur'][t - 2]) * 1e4  # last second known at t
            for tok in (0, 1):
                if done[tok]: continue
                if pricing == 'fair':
                    pf = c['f'][t - 2] if tok == 1 else 1 - c['f'][t - 2]
                    bid = math.floor((pf - M) * 100 + 1e-9) / 100
                else:
                    if lastp[tok] is None: continue
                    bid = round(round(lastp[tok], 2) - 0.01, 2)
                if not (0.05 <= bid <= 0.90): continue
                if band and not (0.60 <= bid <= 0.80): continue
                if cancel:
                    m2 = mv if cancel == 1 else math.log(c['cur'][t] / c['cur'][t - 1]) * 1e4  # 2 = SAME second (optimistic bound)
                    if (tok == 1 and m2 <= -CB) or (tok == 0 and m2 >= CB): continue
                if any(p < bid - 1e-9 for p in c['pr'][tok].get(t, [])):
                    won = (c['up'] == 1) == (tok == 1)
                    out.append(dict(e=c['e'], bid=bid, won=won, pnl=5 * ((1 - bid) if won else -bid), cost=5 * bid))
                    done[tok] = True
    return out


def s(F):
    if not F: return '   0     -       -  '
    n = len(F); pnl = sum(x['pnl'] for x in F); cost = sum(x['cost'] for x in F)
    return f'{n:4d} {np.mean([x["won"] for x in F]) * 100:5.1f} {pnl / cost:+.3f}{"*" if n < 60 else " "}'


def halves(F):
    h = sorted(F, key=lambda x: x['e']); k = len(h) // 2
    a = sum(x['pnl'] for x in h[:k]) / max(1e-9, sum(x['cost'] for x in h[:k]))
    b = sum(x['pnl'] for x in h[k:]) / max(1e-9, sum(x['cost'] for x in h[k:]))
    return f'{a:+.3f}/{b:+.3f}'


S1 = [c for c in C if P1[0] <= c['e'] < P1[1]]; S2 = [c for c in C if P2[0] <= c['e'] < P2[1]]
if len(sys.argv) > 3:  # cancel bound: probe rule (mkt, band, calm, 60-180), cancel none / prev second / SAME second, at 1 and 2 bps
    print('\nCANCEL BOUND - probe rule. mode 0 none, 1 last known second, 2 same second as the fill (optimistic, a perfect sub-second cancel)')
    for cb in (2.0, 1.0):
        CB = cb
        for mode in (0, 1, 2):
            a, b = run(S1, 'mkt', 1, 1, 1, mode), run(S2, 'mkt', 1, 1, 1, mode)
            print(f'  {cb:.0f} bps mode {mode} | P1 {s(a)} {halves(a) if a else ""} | P2 {s(b)} {halves(b) if b else ""}')
    sys.exit()
print('\n* = n<60 INSUFFICIENT.  cols per period: fills  win%  pnl/$  halves(pnl/$)')
print('pricing band calm win cancel |  P1 09-11..22                    |  P2 09-23..10-01')
for pricing in ('fair', 'mkt'):
    for band, calm, win, cancel in itertools.product((0, 1), repeat=4):
        a, b = run(S1, pricing, band, calm, win, cancel), run(S2, pricing, band, calm, win, cancel)
        print(f'{pricing:5s}    {band}    {calm}    {win}    {cancel}   | {s(a)} {halves(a) if a else "":15s} | {s(b)} {halves(b) if b else ""}')
