#!/usr/bin/env python3
"""EF-2 v0 acceptance DETAIL on btc5 - the five breakdowns the owner's bar needs. READ-ONLY, master OFF.

v0 is the one candidate that beat fixed15 on execution and on total dollars. This is the detail behind that:
per day, under realistic cost, by second, by ask, and by calibration decile.

+0.5c / +1c / +1.5c are the haircuts V asked for, because London caps at ask + 1 tick and 1c is therefore
the real bound rather than the 2-3c used earlier.

Decision on the QUOTED ask, economics at the sim fill price, one fire per candle, walk-forward predictions
from the cached v0 fits (day k on days < k, first day never scored).
"""
import sys, math, collections, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, per1, cost, halves, perm_opp, be, MIN_CELL

FITS = '/home/ubuntu/pm_ef2/ef2_fits.npz'
MARG = (0.00, 0.02, 0.03, 0.05)
SECB = [(15, 30), (30, 60), (60, 120), (120, 180), (180, 241)]
ASKB = [(0.0, 0.30), (0.30, 0.45), (0.45, 0.55), (0.55, 0.70), (0.70, 1.0)]
A_P, B_P, TICK, RATE, PAD = 1.0677, -0.3208, 0.01, 0.07, 1
Dc = lambda x: Decimal(str(x))


def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))


def pad_cost(ask):
    # float32 asks out of ef2_rows.npz defeat the `Decimal(str(x))` guard: str() yields
    # '0.3400000035762787', ROUND_CEILING adds a free tick on 44.8% of rows, and only the padded
    # (fixed15) profile is affected. See ef3.py for the full write-up. Snap to the grid first.
    ask = float(Dc(ask).quantize(Dc('0.000001')))
    px = float((Dc(ask) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))


def W(sel, h=0.0):
    fl = [(s['win'], min(s['q'] + h, 0.99)) for s in sel if s['q'] == s['q']]
    if not fl: return float('nan')
    return sum(per1(w, q) * cost(q) for w, q in fl) / sum(cost(q) for w, q in fl)


def tot(sel, h=0.0):
    return sum(10.0 * per1(s['win'], min(s['q'] + h, 0.99)) for s in sel if s['q'] == s['q'])


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    y = y.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    pw = f['pw']; sc = np.isfinite(pw)
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    opp = {}
    for i in np.nonzero(sc)[0]:
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    cands = collections.defaultdict(list)
    for i in np.nonzero(sc)[0]:
        cands[int(ep[i])].append(dict(t=int(ts[i]), p=float(pw[i]), pe=float(X[i, ip]), ask=float(X[i, ia]),
                                      q=float(q[i]), win=float(y[i]), sec=int(X[i, isec]), day=str(day[i]),
                                      oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
    for e in cands: cands[e].sort(key=lambda c: (c['t'], -c['p']))
    days = sorted(set(day[sc].tolist())); nday = len(days)

    def fire(m):
        out = []
        for e, lst in cands.items():
            for c in lst:
                if c['p'] / be(c['ask']) - 1 >= m: out.append(c); break
        return out
    base = []
    for e, lst in cands.items():
        for c in lst:
            if c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(c['ask']) - 1) >= 0.15: base.append(c); break
    A = {m: fire(m) for m in MARG}
    print(f'EF-2 v0 on btc5, walk-forward days {days}, {len(cands)} candles. '
          f'fixed15 on the same days: {len(base)} fires.')

    print(f'\n{"="*128}\n(1) PER DAY - per $1, total $, fills. Rain or sun.\n{"="*128}')
    print(f'  {"arm":14s}' + ''.join(f'{d:>21}' for d in days) + f'{"days +ve":>10}')
    for m in MARG:
        row = f'  m={m:.2f}{"":8s}'; pos = 0
        for d in days:
            s = [c for c in A[m] if c['day'] == d]
            nf = sum(1 for c in s if c['q'] == c['q']); v = W(s)
            pos += (v == v and v > 0)
            row += f'{f"{v:+.3f} {tot(s):+.0f}$ {nf}f":>21}'
        print(row + f'{pos:>10}/{nday}')
    row = f'  {"fixed15":14s}'; pos = 0
    for d in days:
        s = [c for c in base if c['day'] == d]
        nf = sum(1 for c in s if c['q'] == c['q']); v = W(s)
        pos += (v == v and v > 0)
        row += f'{f"{v:+.3f} {tot(s):+.0f}$ {nf}f":>21}'
    print(row + f'{pos:>10}/{nday}')

    print(f'\n{"="*128}\n(2) COST SENSITIVITY per day - +0.5c / +1c / +1.5c. London caps at ask+1 tick, so '
          f'+1c is the real bound.\n{"="*128}')
    print(f'  {"arm":14s}{"haircut":>9}' + ''.join(f'{d:>11}' for d in days) + f'{"ALL":>11}{"days +ve":>10}')
    for m in MARG:
        for h in (0.005, 0.01, 0.015):
            row = f'  m={m:.2f}{"":8s}{f"+{100*h:.1f}c":>9}'; pos = 0
            for d in days:
                s = [c for c in A[m] if c['day'] == d]; v = W(s, h)
                pos += (v == v and v > 0); row += f'{v:>+11.3f}'
            print(row + f'{W(A[m], h):>+11.3f}{pos:>10}/{nday}')
    for h in (0.005, 0.01, 0.015):
        row = f'  {"fixed15":14s}{f"+{100*h:.1f}c":>9}'; pos = 0
        for d in days:
            s = [c for c in base if c['day'] == d]; v = W(s, h)
            pos += (v == v and v > 0); row += f'{v:>+11.3f}'
        print(row + f'{W(base, h):>+11.3f}{pos:>10}/{nday}')

    print(f'\n{"="*128}\n(3) WHERE THE FIRES SIT IN THE CANDLE - the owner has ruled early fires out, so this '
          f'is the test of whether v0 depends on them\n{"="*128}')
    print(f'  {"arm":10s}{"sec p10":>9}{"p50":>7}{"p90":>7}{"<=30s":>8}' +
          ''.join(f'{f"{lo}-{hi if hi<241 else 240}":>18}' for lo, hi in SECB))
    for m in list(MARG) + ['fixed15']:
        s0 = base if m == 'fixed15' else A[m]
        ss = np.array([c['sec'] for c in s0])
        row = f'  {("m="+format(m,".2f")) if m != "fixed15" else "fixed15":10s}' \
              f'{np.percentile(ss,10):>9.0f}{np.percentile(ss,50):>7.0f}{np.percentile(ss,90):>7.0f}' \
              f'{100*np.mean(ss<=30):>7.1f}%'
        for lo, hi in SECB:
            s = [c for c in s0 if lo <= c['sec'] < hi]
            nf = sum(1 for c in s if c['q'] == c['q'])
            row += f'{(f"{W(s):+.3f} ({nf})" if s else "-"):>18}'
        print(row)

    print(f'\n{"="*128}\n(4) ASK AT THE FIRE\n{"="*128}')
    print(f'  {"arm":10s}{"ask p10":>9}{"p50":>7}{"p90":>7}' +
          ''.join(f'{f"{lo:.2f}-{hi:.2f}":>18}' for lo, hi in ASKB))
    for m in list(MARG) + ['fixed15']:
        s0 = base if m == 'fixed15' else A[m]
        aa = np.array([c['ask'] for c in s0])
        row = f'  {("m="+format(m,".2f")) if m != "fixed15" else "fixed15":10s}' \
              f'{np.percentile(aa,10):>9.2f}{np.percentile(aa,50):>7.2f}{np.percentile(aa,90):>7.2f}'
        for lo, hi in ASKB:
            s = [c for c in s0 if lo <= c['ask'] < hi]
            nf = sum(1 for c in s if c['q'] == c['q'])
            row += f'{(f"{W(s):+.3f} ({nf})" if s else "-"):>18}'
        print(row)

    print(f'\n{"="*128}\n(5) CALIBRATION - p_win decile against the realised rate. The decision runs on the '
          f'LEVEL, so this is the one that matters.\n{"="*128}')
    fl = [c for c in A[0.02] if c['q'] == c['q']]
    P = np.array([c['p'] for c in fl]); Y = np.array([c['win'] for c in fl])
    edges = np.percentile(P, np.arange(0, 101, 10))
    print(f'  m=0.02 filled fires, n={len(fl)}')
    print(f'  {"decile":>7}{"n":>6}{"mean p_win":>12}{"realised":>10}{"gap":>9}{"per$1":>9}{"mean ask":>10}')
    for k in range(10):
        lo, hi = edges[k], edges[k + 1]
        m_ = (P >= lo) & (P <= hi if k == 9 else P < hi)
        if m_.sum() < 5: continue
        s = [c for c, t in zip(fl, m_) if t]
        print(f'  {k+1:>7}{int(m_.sum()):>6}{P[m_].mean():>12.3f}{Y[m_].mean():>10.3f}'
              f'{P[m_].mean()-Y[m_].mean():>+9.3f}{W(s):>+9.3f}{np.mean([c["ask"] for c in s]):>10.3f}')
    print(f'  OVERALL mean p_win {P.mean():.3f} vs realised {Y.mean():.3f} -> '
          f'{"over" if P.mean()>Y.mean() else "under"}-confident by {100*abs(P.mean()-Y.mean()):.1f} pp')
