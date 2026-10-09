#!/usr/bin/env python3
"""M4 (V, 09-30, owner: 'combine the models and switch by volatility/regime'). Rules fixed BEFORE running:
Regimes = the FAV vol buckets fixed earlier (Binance 1 s trailing 5-min std: calm < 0.304, mid 0.304-0.466, high >= 0.466).
Models = passive FAV, taker FAV, and SKIP. Periods = 6 h blocks over 09-26..09-30 (both tapes, contiguous, ~1,000 candles).
WALK-FORWARD switch: in each block, per regime, trade the model with the best cumulative $ over ALL PRIOR blocks, only if that is > 0,
else skip the regime. Compared with: fixed passive-all, fixed taker-all, and the HINDSIGHT oracle (best model per regime per block,
chosen after seeing the block - not tradeable, shown only to measure the gap). Columns: $ total, max DD, P/DD, blocks positive.
usage: regime_switch.py <tape1.json.gz> <bn1.json> <tape2.json.gz> <bn2.json>"""
import sys, runpy, io, contextlib, collections
import numpy as np
F, V, pnl = {'passive': {}, 'taker': {}}, {}, None
for tp, bn in ((sys.argv[1], sys.argv[2]), (sys.argv[3], sys.argv[4])):
    sys_argv = sys.argv; sys.argv = ['x', tp, bn]
    with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path(__file__.replace('regime_switch.py', 'passive_fav.py'))
    sys.argv = sys_argv
    for a in F: F[a].update(g['fires'][a])
    V.update(g['V']); pnl = g['pnl']
reg = lambda v: None if v is None else ('calm' if v < 0.304 else 'mid' if v < 0.466 else 'high')
blk = lambda e: (e - 1790000000) // 21600
eps = sorted(set(F['passive']) | set(F['taker']))
B = sorted({blk(e) for e in eps})
res = collections.defaultdict(lambda: collections.defaultdict(float))   # (model, regime) -> block -> $
for m in ('passive', 'taker'):
    for e, (p, w) in F[m].items():
        r = reg(V.get(e))
        if r: res[(m, r)][blk(e)] += pnl(m, p, w)
def seq(choice):   # choice(block, regime) -> model or None; returns per-candle pnl list in time order
    out = []
    for e in eps:
        r = reg(V.get(e)); b = blk(e)
        if not r: continue
        m = choice(b, r)
        if m and e in F[m]: out.append(pnl(m, *F[m][e]))
    return out
def wf(b, r):
    best, bm = 0.0, None
    for m in ('passive', 'taker'):
        s = sum(v for bb, v in res[(m, r)].items() if bb < b)
        if s > best: best, bm = s, m
    return bm
def oracle(b, r):
    best, bm = 0.0, None
    for m in ('passive', 'taker'):
        if res[(m, r)][b] > best: best, bm = res[(m, r)][b], m
    return bm
def line(name, p, choice):
    p = np.array(p); c = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    bp = sum(1 for b in B[1:] if sum(pnl_b for pnl_b in [sum(res[(choice(b, r), r)][b] for r in ('calm', 'mid', 'high') if choice(b, r))]) > 0)
    print(f'{name:34s} n{len(p):4d}  ${c[-1]:+8.1f}  maxDD {dd:6.1f}  P/DD {c[-1]/dd if dd else 0:5.2f}  blocks+ {bp}/{len(B)-1}')
print(f'{len(eps)} candles, {len(B)} blocks of 6 h (the first block has no history, so the switch skips it).')
line('fixed passive, all regimes', seq(lambda b, r: 'passive' if b > B[0] else None), lambda b, r: 'passive')
line('fixed taker, all regimes', seq(lambda b, r: 'taker' if b > B[0] else None), lambda b, r: 'taker')
line('fixed passive, calm only', seq(lambda b, r: 'passive' if (b > B[0] and r == 'calm') else None), lambda b, r: 'passive' if r == 'calm' else None)
line('WALK-FORWARD regime switch', seq(wf), wf)
line('HINDSIGHT oracle (not tradeable)', seq(lambda b, r: oracle(b, r) if b > B[0] else None), oracle)
print('\nper block, per regime: which model the switch picked (from the past) vs the one that actually won that block:')
for b in B[1:]:
    print('  block', b, '  '.join(f"{r}: picked {wf(b, r) or 'skip':7s} won {oracle(b, r) or 'none':7s}" for r in ('calm', 'mid', 'high')))
