#!/usr/bin/env python3
"""Last-minute TWAP lock-in on the REAL settlement feed (V, 09-28). Read-only. Run on a box's own engine DB.

Why: on the Polymarket 1 Hz tape 09-08..16, a Binance-1s stand-in for the reference failed exactly where
the edge would be (contested late candles: Binance final rule vs venue only 78.9%), while the market was
right 91.8% there. This repeats the test with the recorded Chainlink reference (tape1s.ref_px).

Settlement: closing TWAP60 vs opening TWAP60 of ref_px; the window alignment is checked first against the
venue's resolution (must be >= ~99% on this feed). Decision at the START of second ts: ref_px of seconds
< ts, and the ask from row ts-1 (end of the previous second) - strictly past-only. Executable price: the
ask at row ts+d for d = 1, 2 (no cap). Fee 0.07*p*(1-p)/share. One trade per candle: the first second where
EV = p/(ask*cost) - 1 >= theta, 0.02 <= ask <= 0.97. Permutation: a flipped side pays the opposite ask.

NOTE: smoke-tested on a tape built from the 5 s venue sampler forward-filled to 1 s. That tape printed large
"edges" at +1/+2 s because the fill-forward makes the ask up to 5 s stale while ref_px is fresh. Only a real
per-second book tape (tape1s from the engine's websocket book) is a valid input.

usage: twap_lock_ref.py --db <engine sqlite> --outcomes "<SQL returning epoch, 'UP'|'DOWN' (venue truth)>"
"""
import argparse, sqlite3, math, random
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--db', required=True); ap.add_argument('--outcomes', required=True)
a = ap.parse_args()
c = sqlite3.connect(f'file:{a.db}?mode=ro', uri=True)
REF, UP, DN = {}, {}, {}
for ts, r, u, d in c.execute('SELECT ts, ref_px, up_ask, dn_ask FROM tape1s ORDER BY ts'):
    ts = int(ts)
    if r and r > 0: REF[ts] = float(r)
    if u is not None: UP[ts] = float(u)
    if d is not None: DN[ts] = float(d)
OUT = {int(e): str(x).upper()[:2] for e, x in c.execute(a.outcomes)}      # 'UP' / 'DO'
OUT = {e: ('UP' if x == 'UP' else 'DOWN') for e, x in OUT.items()}
print(f'ref seconds {len(REF)}, ask seconds {len(UP)}/{len(DN)}, outcomes {len(OUT)}')

def twap(lo, hi):
    v = [REF[t] for t in range(lo, hi) if t in REF]
    return (sum(v) / len(v)) if len(v) >= 45 else None

# 1) settlement-rule alignment on this feed (label check, not a trading choice)
best = None
for so in (-1, 0, 1):
    for sc in (-1, 0, 1):
        ag = n = 0
        for E, o in OUT.items():
            lo, hi = twap(E - 60 + so, E + so), twap(E + 240 + sc, E + 300 + sc)
            if lo is None or hi is None: continue
            n += 1; ag += (('UP' if hi >= lo else 'DOWN') == o)
        if n: print(f'  align open{so:+d} close{sc:+d}: {ag}/{n} = {ag/n:.4f}')
        if n and (best is None or ag / n > best[0]): best = (ag / n, so, sc, n)
print(f'rule used: open{best[1]:+d} close{best[2]:+d}, agreement {best[0]:.4f} on {best[3]} candles')
SO, SC = best[1], best[2]

S2 = sum(min(i, j) for i in range(60) for j in range(60))
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
cost = lambda q: 1 + 0.07 * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)

def sigma(t):
    px = [REF[k] for k in range(t - 121, t) if k in REF]
    if len(px) < 60: return None
    r = np.diff(np.log(px)); return float(np.sqrt(np.mean(r * r))) * px[-1]

def p_up(E, t, line):
    last = max((k for k in range(t - 5, t) if k in REF), default=None)
    s = sigma(t)
    if last is None or s is None: return None
    P = REF[last]; start = E + 240 + SC
    if t - 1 >= start:
        known = [REF[k] for k in range(start, t) if k in REF]
        k_n = t - start; m = 60 - k_n
        A = (sum(known) / len(known)) * k_n if known else P * k_n
        mean = (A + m * P) / 60.0; var = s * s * m * (m + 1) * (2 * m + 1) / 6.0
    else:
        d = start - (t - 1); mean = P; var = s * s * (3600.0 * d + S2)
    sd = math.sqrt(max(var, 0.0)) / 60.0
    return (1.0 if mean >= line else 0.0) if sd < 1e-9 else Phi((mean - line) / sd)

rows = []
for E, o in OUT.items():
    line = twap(E - 60 + SO, E + SO)
    if line is None: continue
    for sec in range(180, 296):
        t = E + sec
        if (t - 1) not in UP or (t - 1) not in DN: continue
        p = p_up(E, t, line)
        if p is None: continue
        rows.append(dict(E=E, t=t, sec=sec, p=p, up=UP[t - 1], dn=DN[t - 1], w=int(o == 'UP'),
                         d1=(UP.get(t + 1), DN.get(t + 1)), d2=(UP.get(t + 2), DN.get(t + 2))))
print(f'decision seconds: {len(rows)} on {len({r["E"] for r in rows})} candles')
chg=[(UP.get(t)!=UP.get(t-1)) for t in list(UP)[1:5001]]
print(f'ask freshness: {100*sum(chg)/max(1,len(chg)):.1f}% of seconds change vs the previous second (a forward-filled tape fakes edge; see note)')

for lo, hi in ((180, 240), (240, 270), (270, 296)):
    R = [r for r in rows if lo <= r['sec'] < hi and 0.005 < r['up'] < 0.995 and 0.005 < r['dn'] < 0.995]
    if not R: continue
    y = np.array([r['w'] for r in R]); pm = np.array([r['p'] for r in R])
    mid = np.array([min(.99, max(.01, (r['up'] + 1 - r['dn']) / 2)) for r in R])
    print(f'sec {lo}-{hi} (both sides quoted): n{len(R)} candles {len({r["E"] for r in R})}  Brier ours {np.mean((pm-y)**2):.4f} '
          f'market {np.mean((mid-y)**2):.4f}  dir-acc ours {np.mean((pm>=.5)==y):.4f} market {np.mean((mid>=.5)==y):.4f}')

def trade(theta, lo, hi):
    seen = {}
    for r in rows:
        if r['E'] in seen or not (lo <= r['sec'] < hi): continue
        for side, q, pp, w, i, oq in (('UP', r['up'], r['p'], r['w'], 0, r['dn']), ('DN', r['dn'], 1 - r['p'], 1 - r['w'], 1, r['up'])):
            if 0.02 <= q <= 0.97 and pp / (q * cost(q)) - 1 >= theta:
                seen[r['E']] = dict(t=r['t'], q=q, w=w, oq=oq, q1=r['d1'][i], q2=r['d2'][i]); break
    return [seen[e] for e in sorted(seen)]

rng = random.Random(7)
print('\nwindow   theta    n    win%  ask  | per$1 @ask(t-1) H1/H2 | @+1s  H1/H2 | @+2s  H1/H2 | perm p (+1s)')
for lo, hi in ((180, 240), (240, 270), (270, 296), (240, 296)):
    for th in (0.02, 0.05, 0.10, 0.15, 0.25, 0.40):
        T = trade(th, lo, hi)
        if not T: continue
        def ser(key):
            v = np.array([per1(t['w'], t[key]) for t in T if t[key] is not None and 0.005 < t[key] < 0.995])
            h = len(v) // 2
            return (v.mean(), v[:h].mean() if h else float('nan'), v[h:].mean(), len(v)) if len(v) else (float('nan'),) * 3 + (0,)
        s0, s1, s2 = ser('q'), ser('q1'), ser('q2')
        T1 = [t for t in T if t['q1'] is not None and 0.005 < t['q1'] < 0.995]
        base = np.mean([per1(t['w'], t['q1']) for t in T1]) if T1 else float('nan')
        sims = [np.mean([per1(1 - t['w'], min(.99, max(.01, t['oq']))) if rng.random() < .5 else per1(t['w'], t['q1']) for t in T1]) for _ in range(300)] if T1 else [0]
        pp = float(np.mean(np.array(sims) >= base))
        fl = '*' if len(T) < 60 else ' '
        print(f'{lo}-{hi:<4} {th:5.2f} {len(T):5d}{fl} {100*np.mean([t["w"] for t in T]):5.1f} {np.median([t["q"] for t in T]):.2f} | '
              f'{s0[0]:+.3f} {s0[1]:+.3f}/{s0[2]:+.3f} | {s1[0]:+.3f} {s1[1]:+.3f}/{s1[2]:+.3f} | {s2[0]:+.3f} {s2[1]:+.3f}/{s2[2]:+.3f} | {pp:.2f}')
