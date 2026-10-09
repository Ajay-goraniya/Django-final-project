#!/usr/bin/env python3
"""Last-minute TWAP lock-in vs the Polymarket ask (V, 09-28; owner: "we trade on rules based on twap results").

Settlement: closing TWAP60 [E+240, E+300) vs opening TWAP60 [E-60, E), graded on Polymarket's own resolution
(venues.outcome). Binance 1 s closes stand in for the Chainlink reference (agreement reported first).
At every venue quote row (ts, both asks) the TWAP-implied P(UP) is computed from data strictly before ts:
known part of the closing window + Brownian projection of the rest (sigma = RMS of 1 s returns, last 120 s).
Rule fixed before any result: first row in the window where EV = p/(ask*cost) - 1 >= theta, ask <= 0.97.
Priced at the decision quote AND at the next quote row (~5 s later, no cap) - the executability test.
Fee 0.07*p*(1-p) per share. Permutation: a flipped side pays the OPPOSITE side's ask."""
import sqlite3, zipfile, glob, math, bisect, random, sys
import numpy as np

D = sys.argv[1] if len(sys.argv) > 1 else '.'
close = {}
for z in sorted(glob.glob(f'{D}/BTCUSDT-1s-*.zip')):
    with zipfile.ZipFile(z) as zf:
        for line in zf.open(zf.namelist()[0]):
            f = line.split(b',')
            t = int(f[0]); t = t // 1_000_000 if t > 10**14 else t // 1000
            close[t] = float(f[4])
print(f'closes: {len(close)}')

vc = sqlite3.connect(f'{D}/venues.sqlite3')
OUT = {int(e): a for e, a in vc.execute('select epoch, actual from outcome')}
Q = {}
for ts, ep, sec, up, dn in vc.execute('select ts, epoch, sec, poly_up, poly_dn from q order by ts'):
    Q.setdefault(int(ep), []).append((int(ts), int(sec), up, dn))

def twap(a, b):
    v = [close[t] for t in range(a, b) if t in close]
    return (sum(v) / len(v)) if len(v) >= 45 else None

# 1) does the proxy rule match the venue?
agree = tot = 0
for E, a in OUT.items():
    lo, hi = twap(E - 60, E), twap(E + 240, E + 300)
    if lo is None or hi is None: continue
    tot += 1; agree += (('UP' if hi >= lo else 'DOWN') == a)
print(f'rule agreement (Binance TWAP60 close vs open, vs venue): {agree}/{tot} = {agree/max(tot,1):.4f}')

S2 = sum(min(i, j) for i in range(60) for j in range(60))
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
cost = lambda q: 1 + 0.07 * (1 - q)
per1 = lambda w, q: (w / q - cost(q)) / cost(q)

def sigma(t):
    px = [close[k] for k in range(t - 121, t) if k in close]
    if len(px) < 60: return None
    r = np.diff(np.log(px))
    return float(np.sqrt(np.mean(r * r))) * px[-1]

def p_up(E, t, line):
    """P(closing TWAP60 >= line) using closes of seconds < t only."""
    P = close.get(t - 1)
    s = sigma(t)
    if P is None or s is None: return None
    start = E + 240
    if t - 1 >= start:
        known = [close[k] for k in range(start, t) if k in close]
        m = 60 - (t - start)
        A = sum(known) * 60.0 / max(1, len(known)) * ((t - start) / 60.0) if known else 0.0
        mean = (A + m * P) / 60.0
        var = s * s * m * (m + 1) * (2 * m + 1) / 6.0 if m > 0 else 0.0
    else:
        d = start - (t - 1)
        mean = P
        var = s * s * (3600.0 * d + S2)
    sd = math.sqrt(var) / 60.0
    if sd < 1e-9: return 1.0 if mean >= line else 0.0
    return Phi((mean - line) / sd)

# 2) build decision rows
rows = []
for E, qs in Q.items():
    a = OUT.get(E); line = twap(E - 60, E)
    if a is None or line is None: continue
    for i, (ts, sec, up, dn) in enumerate(qs):
        if sec < 180 or sec > 295 or up is None or dn is None: continue
        p = p_up(E, ts, line)
        if p is None: continue
        nxt = next(((u2, d2, s2) for (t2, s2, u2, d2) in qs[i + 1:] if t2 > ts and u2 is not None and d2 is not None), None)
        rows.append(dict(E=E, ts=ts, sec=sec, p=p, up=float(up), dn=float(dn), win_up=int(a == 'UP'),
                         nup=None if nxt is None else float(nxt[0]), ndn=None if nxt is None else float(nxt[1])))
print(f'decision rows: {len(rows)} on {len({r["E"] for r in rows})} candles')

# 3) calibration: our TWAP p vs the market's implied mid, late seconds
for lo, hi in ((180, 240), (240, 270), (270, 296)):
    R = [r for r in rows if lo <= r['sec'] < hi]
    y = np.array([r['win_up'] for r in R]); pm = np.array([r['p'] for r in R])
    mid = np.array([min(.99, max(.01, (r['up'] + 1 - r['dn']) / 2)) for r in R])
    print(f'sec {lo}-{hi}: n{len(R)}  Brier ours {np.mean((pm-y)**2):.4f}  market {np.mean((mid-y)**2):.4f}  '
          f'dir-acc ours {np.mean((pm>=.5)==y):.4f} market {np.mean((mid>=.5)==y):.4f}')

# 4) the trading grid
def trade(R, theta, lo, hi):
    seen = {}
    for r in sorted(R, key=lambda r: (r['E'], r['ts'])):
        if r['E'] in seen or not (lo <= r['sec'] < hi): continue
        for side, q, pp, w, nq, oq in (('UP', r['up'], r['p'], r['win_up'], r['nup'], r['dn']),
                                       ('DN', r['dn'], 1 - r['p'], 1 - r['win_up'], r['ndn'], r['up'])):
            if q <= 0.97 and q >= 0.02 and pp / (q * cost(q)) - 1 >= theta:
                seen[r['E']] = dict(E=r['E'], sec=r['sec'], side=side, q=q, w=w, nq=nq, oq=oq, p=pp); break
    return [seen[e] for e in sorted(seen)]

rng = random.Random(7)
print('\nwindow     theta   n   win%  ask   per$1@quote  H1/H2          | next-row n  per$1@next  H1/H2        | perm p')
for lo, hi in ((180, 240), (240, 270), (270, 296), (240, 296)):
    for th in (0.02, 0.05, 0.10, 0.15, 0.25, 0.40):
        T = trade(rows, th, lo, hi)
        if not T: print(f'{lo}-{hi} {th:.2f} none'); continue
        v = np.array([per1(t['w'], t['q']) for t in T]); h = len(v) // 2
        N = [t for t in T if t['nq'] is not None and 0.01 < t['nq'] < 1]
        vn = np.array([per1(t['w'], t['nq']) for t in N]); hn = len(vn) // 2
        sims = [np.mean([per1(1 - t['w'], min(.99, max(.01, t['oq']))) if rng.random() < .5 else per1(t['w'], t['q']) for t in T]) for _ in range(300)]
        pp = float(np.mean(np.array(sims) >= v.mean()))
        flag = '*' if len(T) < 60 else ' '
        print(f'{lo}-{hi:<4} {th:5.2f} {len(T):4d}{flag} {100*np.mean([t["w"] for t in T]):5.1f} {np.median([t["q"] for t in T]):.2f}  '
              f'{v.mean():+.3f}      {v[:h].mean():+.3f}/{v[h:].mean():+.3f}  | {len(N):4d}      '
              f'{(vn.mean() if len(vn) else float("nan")):+.3f}     {(vn[:hn].mean() if hn else float("nan")):+.3f}/{(vn[hn:].mean() if len(vn) else float("nan")):+.3f} | {pp:.2f}')
