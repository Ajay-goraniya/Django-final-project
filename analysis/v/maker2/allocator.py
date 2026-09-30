#!/usr/bin/env python3
"""M12 (V, 09-30, owner: 'many tests worked partially in a day - use that data with proper logic'). Rules fixed BEFORE running:
ARMS (20): taker FAV {calm, mid, all, causal-calm} x session {Asia 00-07, Europe 07-13, US 13-20, Late 20-24} (strict, +1c, fee)
         + passive FAV calm, trade-through fill, +1c, x the same 4 sessions.
Daily $ per arm at $10/trade over 09-11..09-30.
(1) PERSISTENCE: correlation across arms of day-d $ with day-(d-1) $ (does yesterday's winner win today?), all day pairs pooled.
(2) ALLOCATOR (walk-forward, no look-ahead): each day d trade only the arms whose $ over the previous k days is > 0, k in {1,2,3,5};
    $ per day, total, worst drop, days positive. Compared with: trading all 20 arms; the best single arm chosen in HINDSIGHT (not tradeable).
usage: allocator.py <scratch dir>"""
import sys, runpy, io, contextlib, collections, datetime as dt
import numpy as np
S = sys.argv[1]
sys.argv = ['x', '--tape', f'{S}/hist/lean*.json.gz,{S}/wallets_raw.json.gz,{S}/fresh48/fresh_tape.json.gz',
            '--bn', f'{S}/hist/bin1s_0911_0926.json,{S}/bin1s_48h.json,{S}/fresh48/bin1s_fresh.json', '--out', f'{S}/m12tmp']
with contextlib.redirect_stdout(io.StringIO()): h = runpy.run_path('analysis/v/maker2/strict_pfav.py')   # loaded ONCE (memory)
pres = h['res'][('tape', 'fixed0.304', 'thru', 0.01)][0]
T, V, eps, prints, day, CC = h['T'], h['V'], h['eps'], h['prints'], h['day'], h['CC']
def decide(e):                                   # identical to strict_taker_fav.py
    d = T[str(e)]; up, dn, P = prints(d, e)
    if dn is None: return None
    last, j = None, 0
    for s in range(60, 181):
        while j < len(P) and P[j][0] <= s:
            a, p = P[j][1], P[j][2]; last = p if a == up else 1 - p; j += 1
        if last is None: continue
        side, fp = (up, last) if last >= 0.5 else (dn, 1 - last)
        if 0.64 - 1e-9 <= fp <= 0.84 + 1e-9: return dict(e=e, ask=round(fp + 0.01, 2), win=(d['win'] == side), v=V[e])
    return None
rows = [r for r in (decide(e) for e in eps) if r]; del T, h
arms = {'FAV calm<0.304': lambda r: r['v'] is not None and r['v'] < 0.304,
        'FAV_mid 0.304-0.466': lambda r: r['v'] is not None and 0.304 <= r['v'] < 0.466,
        'FAV_all': lambda r: True,
        'calm causal cut': lambda r: r['v'] is not None and CC.get(day(r['e'])) is not None and r['v'] < CC[day(r['e'])]}
SESS = (('Asia', 0, 7), ('Europe', 7, 13), ('US', 13, 20), ('Late', 20, 24))
hr = lambda e: dt.datetime.fromtimestamp(e, dt.timezone.utc).hour
D = collections.defaultdict(lambda: collections.defaultdict(float))   # arm -> day -> $
tk = lambda r: (lambda c: (10 / c - 10) if r['win'] else -10.0)(r['ask'] + 0.07 * r['ask'] * (1 - r['ask']) + 0.01)
for an, f in arms.items():
    for r in rows:
        if not f(r): continue
        for sn, a, b in SESS:
            if a <= hr(r['e']) < b: D[f'{an.split()[0]}{"(causal)" if "causal" in an else ""}|{sn}'][day(r['e'])] += tk(r)
for r in pres:
    if not r['thru']: continue
    x = (10 / (r['b'] + 0.01) - 10) if r['win'] else -10.0
    for sn, a, b in SESS:
        if a <= hr(r['e']) < b: D[f'passive|{sn}'][day(r['e'])] += x
days = sorted({d for a in D.values() for d in a}); A = sorted(D)
M = np.array([[D[a].get(d, 0.0) for d in days] for a in A])     # arms x days
print(f'M12: {len(A)} arms x {len(days)} days ({days[0]}..{days[-1]}), strict, $10/trade')
x, y = M[:, :-1].ravel(), M[:, 1:].ravel()
print(f'(1) persistence: corr(arm $ yesterday, arm $ today) = {np.corrcoef(x, y)[0,1]:+.3f} over {len(x)} arm-day pairs; '
      f'P(today > 0 | yesterday > 0) = {np.mean(y[x > 0] > 0):.2f} vs P(today > 0 | yesterday <= 0) = {np.mean(y[x <= 0] > 0):.2f}')
def run(sel):
    out = []
    for j in range(5, len(days)):                 # common start so every k has history
        out.append(sum(M[i, j] for i in range(len(A)) if sel(i, j)))
    q = np.cumsum(out); dd = float(np.max(np.maximum.accumulate(np.r_[0, q]) - np.r_[0, q]))
    return q[-1], dd, sum(v > 0 for v in out), len(out), out
print(f'(2) allocator, scored {days[5]}..{days[-1]} ({len(days)-5} days):')
for k in (1, 2, 3, 5):
    t, dd, p, n, _ = run(lambda i, j: M[i, j - k:j].sum() > 0)
    print(f'   trade arms positive over last {k} day(s): $ {t:+8.1f}  worst drop {dd:7.1f}  days + {p}/{n}')
t, dd, p, n, _ = run(lambda i, j: True); print(f'   all 20 arms, every day:            $ {t:+8.1f}  worst drop {dd:7.1f}  days + {p}/{n}')
best = max(range(len(A)), key=lambda i: M[i, 5:].sum())
t, dd, p, n, _ = run(lambda i, j: i == best); print(f'   HINDSIGHT best single arm ({A[best]}): $ {t:+8.1f}  worst drop {dd:7.1f}  days + {p}/{n}   <- not tradeable')
t, dd, p, n, _ = run(lambda i, j: M[i, j] > 0); print(f'   HINDSIGHT "only the arms that won that day": $ {t:+8.1f}  <- what "it worked partially in a day" looks like, not tradeable')
