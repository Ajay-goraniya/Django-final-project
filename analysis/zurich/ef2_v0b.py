#!/usr/bin/env python3
"""EF-2 v0b: TIMING ONLY. The one thing that has survived twice. READ-ONLY, master OFF.

V, 09-28: "the ask alone matches any model at every horizon, so there is no private information in the inputs
and no model beats the price. The only survivor twice now is TIMING."

The rule: fire at the FIRST pass with sec >= S, on the MODEL'S SIDE, buy at the quoted ask if ask <= cap.
One fire per candle. No p bar, no training, nothing fitted - so unlike v0/v1 this needs no walk-forward and
every day in the sample can be used, fixed15 included, which makes the comparison like-for-like on 5 days
rather than 4.

The model still picks the SIDE. That is the whole remaining content of the model in this arm, and it is worth
being explicit that v0b is not model-free.

WHY IT MIGHT PAY, which is V's real question: if the ask on the model's chosen side RISES from second 15 to
45 to 120, the venue is catching up to the model - the model leads the crowd at candle open and the rule is
buying before the price moves. If the ask is flat or falls, the rule is just buying cheap and the timing is
incidental. That is section 3 and it is the part that would distinguish a mechanism from a coincidence.
"""
import sys, collections, math, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, per1, cost, halves, perm_opp, be, MIN_CELL

SS = (15, 20, 25, 30)
CAPS = (0.50, 0.55, 0.60, 0.65)
A_P, B_P, TICK, RATE, PAD = 1.0677, -0.3208, 0.01, 0.07, 1
Dc = lambda x: Decimal(str(x))


def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))


def pad_cost(ask):
    px = float((Dc(ask) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))


def Wsel(sel):
    fl = [(s['win'], s['q']) for s in sel if s['q'] == s['q']]
    if not fl: return float('nan')
    return sum(per1(w, q) * cost(q) for w, q in fl) / sum(cost(q) for w, q in fl)


def hair(sel, c):
    fl = [(s['win'], min(s['q'] + c, 0.99)) for s in sel if s['q'] == s['q']]
    if not fl: return float('nan')
    return sum(per1(w, q) * cost(q) for w, q in fl) / sum(cost(q) for w, q in fl)


HDR = (f'  {"cell":18s}{"fires":>6}{"/day":>6}{"fill%":>7}{"win%":>7}{"per$1":>9}{"total$":>9}'
       f'{"H1":>8}{"H2":>8}{"flipP":>7}{"+1c":>8}{"+2c":>8}{"+3c":>8}'
       f'{"ask p10":>8}{"p50":>6}{"p90":>6}')


def line(lab, sel, nday, days):
    if not sel:
        print(f'  {lab:18s}{0:>6}  (no fires)'); return None
    fl = [s for s in sel if s['q'] == s['q']]
    tup = [(s['win'], s['q'], s['t'], s['oq']) for s in sel]
    h1, h2 = halves(tup)
    a = np.array([s['ask'] for s in sel])
    tot = sum(10.0 * per1(s['win'], s['q']) for s in fl)
    print(f'  {lab:18s}{len(sel):>6}{len(sel)/max(nday,1):>6.0f}{100*len(fl)/len(sel):>6.1f}%'
          f'{(100*np.mean([s["win"] for s in fl]) if fl else float("nan")):>6.1f}%'
          f'{Wsel(sel):>+9.3f}{tot:>+9.1f}{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
          f'{perm_opp(tup):>7.3f}{hair(sel,0.01):>+8.3f}{hair(sel,0.02):>+8.3f}{hair(sel,0.03):>+8.3f}'
          f'{np.percentile(a,10):>8.2f}{np.percentile(a,50):>6.2f}{np.percentile(a,90):>6.2f}'
          + ('  *n<60' if len(fl) < MIN_CELL else ''))
    return dict(sel=sel, per1=Wsel(sel), n=len(sel), nf=len(fl))


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True)
    X, y, q, ep, ts, day = z['X'], z['y'].astype(float), z['q'], z['ep'], z['ts'], z['day']
    names = [str(s) for s in z['names']]
    isup = z['is_up']
    fin = np.all(np.isfinite(X), axis=1)
    X, y, q, ep, ts, day, isup = X[fin], y[fin], q[fin], ep[fin], ts[fin], day[fin], isup[fin]
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    days = sorted(set(day.tolist())); nday = len(days)
    opp = {}
    for i in range(len(y)):
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    cands = collections.defaultdict(list)
    for i in range(len(y)):
        cands[int(ep[i])].append(dict(t=int(ts[i]), pe=float(X[i, ip]), ask=float(X[i, ia]),
                                      q=float(q[i]), win=float(y[i]), sec=int(X[i, isec]),
                                      day=str(day[i]), up=int(isup[i]),
                                      oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
    for e in cands: cands[e].sort(key=lambda c: c['t'])
    print(f'v0b on ALL {nday} days {days}: {len(cands)} candles, {len(y):,} candidate rows. '
          f'No training, so no day has to be held out.')

    def fire(S, cap):
        out = []
        for e, lst in cands.items():
            for c in lst:
                if c['pe'] < 0.5: continue              # the model's side only
                if c['sec'] < S: continue
                if c['ask'] > cap: continue
                out.append(c); break
        return out

    print(f'\n{"="*150}\n1. THE GRID - all 16 cells, execution first\n{"="*150}')
    print(HDR)
    cells = {}
    for S in SS:
        for cap in CAPS:
            cells[(S, cap)] = line(f'S={S} cap={cap:.2f}', fire(S, cap), nday, days)
        print('  ' + '-' * 148)
    base = [c for e, lst in cands.items() for c in lst
            if c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(c['ask']) - 1) >= 0.15][:0]
    bl = []
    for e, lst in cands.items():
        for c in lst:
            if c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(c['ask']) - 1) >= 0.15:
                bl.append(c); break
    line('fixed15 (same days)', bl, nday, days)

    print(f'\n{"="*150}\n2. PER DAY per $1 - rain or sun\n{"="*150}')
    print(f'  {"cell":18s}' + ''.join(f'{d:>12}' for d in days) + f'{"days +ve":>10}')
    for S in SS:
        for cap in CAPS:
            r = cells[(S, cap)]
            if not r: continue
            row = f'  {f"S={S} cap={cap:.2f}":18s}'
            pos = 0
            for d in days:
                s2 = [c for c in r['sel'] if c['day'] == d]
                v = Wsel(s2) if s2 else float('nan')
                pos += (v == v and v > 0)
                row += f'{v:>+12.3f}' if v == v else f'{"-":>12}'
            print(row + f'{pos:>10}/{nday}')
    row = f'  {"fixed15":18s}'; pos = 0
    for d in days:
        s2 = [c for c in bl if c['day'] == d]
        v = Wsel(s2) if s2 else float('nan')
        pos += (v == v and v > 0)
        row += f'{v:>+12.3f}' if v == v else f'{"-":>12}'
    print(row + f'{pos:>10}/{nday}')

    print(f'\n{"="*150}\n3. DOES THE VENUE CATCH UP TO THE MODEL? the model-side ask at sec 15 vs 45 vs 120'
          f'\n{"="*150}')
    print('  For each candle: take the side the model favours at the FIRST pass at sec >= 15, then follow')
    print('  THAT SAME side\'s ask forward. If the venue is catching up, the ask should rise.')
    print(f'  {"":6}{"n":>6}{"ask@15":>9}{"ask@45":>9}{"ask@120":>10}{"d15->45":>10}{"d15->120":>11}'
          f'{"% risen@45":>12}{"% risen@120":>13}')
    rec = []
    for e, lst in cands.items():
        f15 = next((c for c in lst if c['pe'] >= 0.5 and c['sec'] >= 15), None)
        if not f15: continue
        side = f15['up']
        def at(sec):
            return next((c['ask'] for c in lst if c['up'] == side and c['sec'] >= sec), None)
        a45, a120 = at(45), at(120)
        if a45 is None or a120 is None: continue
        rec.append((f15['ask'], a45, a120, f15['win']))
    if rec:
        A = np.array(rec)
        print(f'  {"all":6}{len(A):>6}{A[:,0].mean():>9.3f}{A[:,1].mean():>9.3f}{A[:,2].mean():>10.3f}'
              f'{100*(A[:,1]-A[:,0]).mean():>+10.2f}{100*(A[:,2]-A[:,0]).mean():>+11.2f}'
              f'{100*np.mean(A[:,1]>A[:,0]):>11.1f}%{100*np.mean(A[:,2]>A[:,0]):>12.1f}%')
        for lab, m in (('won', A[:, 3] == 1), ('lost', A[:, 3] == 0)):
            B = A[m]
            if not len(B): continue
            print(f'  {lab:6}{len(B):>6}{B[:,0].mean():>9.3f}{B[:,1].mean():>9.3f}{B[:,2].mean():>10.3f}'
                  f'{100*(B[:,1]-B[:,0]).mean():>+10.2f}{100*(B[:,2]-B[:,0]).mean():>+11.2f}'
                  f'{100*np.mean(B[:,1]>B[:,0]):>11.1f}%{100*np.mean(B[:,2]>B[:,0]):>12.1f}%')
        print('\n  A rise on BOTH won and lost candles is the venue catching up to the model.')
        print('  A rise only on the won ones is just the price following the outcome, which is not a lead.')
