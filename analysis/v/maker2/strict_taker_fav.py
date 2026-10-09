#!/usr/bin/env python3
"""M6 (V, 09-30, owner: 'new model test') - the SAME strict harness on the TAKER FAV family now in Zurich's paper shadow.
Decide first: at the first second s in [60,180] where the favourite's last traded price (tape, ts - 2.2 s, mint mirror) is in [0.64,0.84],
buy at ask = that price + 0.01 (one tick over), 1 s later; pay ask + taker fee 0.07 p(1-p); a +1c slippage column on top.
Fill: taker FAK at the ask - assume filled (fill risk only helps a taker avoid runs, so this is not the lenient side for losses).
Vol arms: calm < 0.304 (FAV), mid 0.304-0.466 (FAV_mid), all (FAV_all); plus the causal 45th-pct cut. $100 start, $10, ruin at < $10.
usage: strict_taker_fav.py <scratch dir>"""
import sys, runpy, io, contextlib, collections, datetime as dt, numpy as np
S = sys.argv[1]
sys.argv = ['x', '--tape', f'{S}/hist/lean*.json.gz,{S}/wallets_raw.json.gz,{S}/fresh48/fresh_tape.json.gz',
            '--bn', f'{S}/hist/bin1s_0911_0926.json,{S}/bin1s_48h.json,{S}/fresh48/bin1s_fresh.json', '--out', f'{S}/m6tmp']
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path(__file__.replace('strict_taker_fav.py', 'strict_pfav.py'))
T, V, eps, prints, day, CC = g['T'], g['V'], g['eps'], g['prints'], g['day'], g['CC']
def decide(e):
    d = T[str(e)]; up, dn, P = prints(d, e)
    if dn is None: return None
    last, j = None, 0
    for s in range(60, 181):
        while j < len(P) and P[j][0] <= s:
            a, p = P[j][1], P[j][2]; last = p if a == up else 1 - p; j += 1
        if last is None: continue
        side, fp = (up, last) if last >= 0.5 else (dn, 1 - last)
        if 0.64 - 1e-9 <= fp <= 0.84 + 1e-9:
            return dict(e=e, ask=round(fp + 0.01, 2), win=(d['win'] == side), v=V[e])
    return None
rows = [r for r in (decide(e) for e in eps) if r]
arms = {'FAV calm<0.304': lambda r: r['v'] is not None and r['v'] < 0.304,
        'FAV_mid 0.304-0.466': lambda r: r['v'] is not None and 0.304 <= r['v'] < 0.466,
        'FAV_all': lambda r: True,
        'calm causal cut': lambda r: r['v'] is not None and CC.get(day(r['e'])) is not None and r['v'] < CC[day(r['e'])]}
print(f'M6 strict TAKER FAV family, {len(eps)} candles 09-11..09-30; $100 start, $10 per trade, ruin < $10.')
print(f"{'arm':22s} {'slip':>4s} {'n':>5s} {'win%':>5s} {'total$ (no stop)':>16s} {'worst drop$':>11s} {'days+':>6s} {'$100 account':>22s}")
out = {}
for name, f in arms.items():
    for slip in (0.0, 0.01):
        sel = [r for r in rows if f(r)]; x = []
        for r in sel:
            c = r['ask'] + 0.07 * r['ask'] * (1 - r['ask']) + slip; x.append((10 / c - 10) if r['win'] else -10.0)
        q = np.cumsum(x); dd = float(np.max(np.maximum.accumulate(np.r_[0, q]) - np.r_[0, q]))
        byd = collections.defaultdict(float)
        for r, v in zip(sel, x): byd[day(r['e'])] += v
        eq, broke = 100.0, None
        for r, v in zip(sel, x):
            if eq < 10: broke = day(r['e']); break
            eq += v
        acct = f'broke on {broke}' if broke else f'ends {eq:.0f}'
        print(f"{name:22s} {slip:4.2f} {len(sel):5d} {100*np.mean([r['win'] for r in sel]):5.1f} {q[-1]:+16.1f} {dd:11.1f} {sum(v>0 for v in byd.values()):3d}/{len(byd):<2d} {acct:>22s}")
        if slip == 0.01: out[name] = byd
print('\nper day, +1c slip:')
for name, byd in out.items(): print(f"  {name:22s} " + ' '.join(f"{d[8:]}:{v:+.0f}" for d, v in sorted(byd.items())))
