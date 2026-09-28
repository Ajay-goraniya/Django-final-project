#!/usr/bin/env python3
"""EF-3: every arm judged on the OWNER's columns first. READ-ONLY. Master OFF, London untouched.

Owner, 09-28 13:4x, standing until met: an EF with good profit, SMALL max drawdown, good frequency and fill
rate. fixed15 made money then gave it back. So the primary columns are his, in his order:

    $ total at $10 | worst drawdown $ | profit/drawdown | fires/day | sim fill% | % days positive | losing run

and only then per $1, win%, halves and the permutation. A high per $1 on six trades is not what he asked for.

ALL arms are scored on the SAME candles with the SAME per-pass FAK simulator. EF-2 v0 only exists on the
walk-forward days (day k fitted on days < k, so the first day is unscorable), so the RANKING in section 5 is
run on those 4 days where every arm exists; sections 1-4 also show the 5-day read for the rule-based arms,
which need no training.
"""
import sys, math, collections, random, statistics as st, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, per1, cost, be

FITS = '/home/ubuntu/pm_ef2/ef2_fits.npz'
SS = (0, 60, 120, 150, 180, 200, 220, 230)
MARG = (0.00, 0.02, 0.05)
BANDS = ((0.30, 0.70), (0.40, 0.70), (0.50, 0.80))
A_P, B_P, TICK, RATE, PAD, STAKE = 1.0677, -0.3208, 0.01, 0.07, 1, 10.0
MIN_CELL = 60
Dc = lambda x: Decimal(str(x))


def platt(p):
    if not (0. < p < 1.): return p
    z = math.log(p / (1 - p))
    return min(p, max(0.01, 1 / (1 + math.exp(-(A_P * z + B_P)))))


def pad_cost(a):
    px = float((Dc(a) / Dc(TICK)).to_integral_value(rounding=ROUND_CEILING) * Dc(TICK) + Dc(PAD) * Dc(TICK))
    px = min(px, float(Dc(1) - Dc(TICK)))
    f = RATE * px * (1 - px)
    return max(px + f, px / (1 - f / px))


ARMS = {'fixed15': lambda c: (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15 and c['p'] >= 0.5,
        'raw25': lambda c: (c['p'] / be(c['ask']) - 1) >= 0.25 and c['p'] >= 0.5}


def perm_opp(sel, draws=300, seed=41):
    fl = [c for c in sel if c['q'] == c['q']]
    if not fl: return float('nan')
    W = lambda s: (sum(per1(a, b) * cost(b) for a, b in s) / sum(cost(b) for a, b in s)) if s else float('nan')
    real = W([(c['win'], c['q']) for c in fl])
    rng = random.Random(seed); sims = []
    for _ in range(draws):
        acc = []
        for c in fl:
            if rng.random() < 0.5:
                if c['oq'] != c['oq']: continue
                acc.append((1 - c['win'], c['oq']))
            else: acc.append((c['win'], c['q']))
        if acc: sims.append(W(acc))
    if not sims: return float('nan')
    return sum(1 for x in sims if x >= real) / len(sims)


def score(sel, ndays):
    fl = sorted([c for c in sel if c['q'] == c['q']], key=lambda c: c['t'])
    if not fl:
        return None
    seq = [STAKE * per1(c['win'], c['q']) for c in fl]
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    byd = collections.defaultdict(float)
    for c, x in zip(fl, seq): byd[c['day']] += x
    den = sum(cost(c['q']) for c in fl)
    h = len(fl) // 2
    hw = lambda s: (sum(per1(c['win'], c['q']) * cost(c['q']) for c in s) / sum(cost(c['q']) for c in s)) if s else float('nan')
    return dict(n=len(sel), nf=len(fl), fill=len(fl) / len(sel), tot=cum, mdd=mdd,
                ratio=(cum / mdd if mdd > 0 else float('inf')), fpd=len(sel) / max(ndays, 1),
                pos=sum(1 for v in byd.values() if v > 0), days=len(byd), run=worst,
                per1=sum(per1(c['win'], c['q']) * cost(c['q']) for c in fl) / den,
                win=np.mean([c['win'] for c in fl]), h1=hw(fl[:h]), h2=hw(fl[h:]), perm=perm_opp(sel),
                byd=dict(byd))


HDR = (f'  {"arm":30s}{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"run":>5}|'
       f'{"per$1":>8}{"win%":>7}{"H1":>8}{"H2":>8}{"perm":>7}')


def line(lab, sel, ndays, store=None):
    s = score(sel, ndays)
    if not s:
        print(f'  {lab:30s}{0:>8}   (no fills)'); return None
    print(f'  {lab:30s}{s["tot"]:>+8.1f}{s["mdd"]:>7.1f}'
          f'{(s["ratio"] if s["ratio"] != float("inf") else 99.9):>7.2f}{s["fpd"]:>7.1f}{100*s["fill"]:>6.1f}%'
          f'{f"{s[chr(112)+chr(111)+chr(115)]}/{s[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}{s["run"]:>5}|'
          f'{s["per1"]:>+8.3f}{100*s["win"]:>6.1f}%{s["h1"]:>+8.3f}{s["h2"]:>+8.3f}{s["perm"]:>7.3f}'
          + ('  *n<60' if s['nf'] < MIN_CELL else ''))
    if store is not None: store[lab] = s
    return s


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    y = y.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    pw = f['pw']; wf = np.isfinite(pw)
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    opp = {}
    for i in range(len(y)):
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    C5, C4 = collections.defaultdict(list), collections.defaultdict(list)
    for i in range(len(y)):
        d = dict(t=int(ts[i]), p=float(X[i, ip]), ask=float(X[i, ia]), q=float(q[i]), win=float(y[i]),
                 sec=int(X[i, isec]), day=str(day[i]), up=int(isup[i]),
                 pw=(float(pw[i]) if wf[i] else float('nan')),
                 oq=opp.get((int(ts[i]), int(isup[i])), float('nan')))
        C5[int(ep[i])].append(d)
        if wf[i]: C4[int(ep[i])].append(d)
    for D in (C5, C4):
        for e in D: D[e].sort(key=lambda c: c['t'])
    d5 = sorted(set(day.tolist())); d4 = sorted(set(day[wf].tolist()))
    print(f'EF-3. All arms on the same candles and the same per-pass FAK simulator.')
    print(f'  5-day set (rule arms, no training): {len(C5)} candles, days {d5}')
    print(f'  4-day set (every arm, EF-2 included): {len(C4)} candles, days {d4}')
    print(f'\nColumns are the owner\'s, in his order: total $, worst drawdown $, profit/drawdown, fires/day,')
    print(f'sim fill%, days positive, longest losing run - then per $1, win%, halves, permutation.')

    def first(D, pred):
        out = []
        for e, lst in D.items():
            c = next((c for c in lst if pred(c)), None)
            if c is not None: out.append(c)
        return out

    RANK = {}
    for tag, D, dd in (('5-day', C5, d5), ('4-day', C4, d4)):
        nd = len(dd)
        print(f'\n{"="*136}\n(1) START-SECOND CURVE - the arm may only fire from sec S   [{tag}]\n{"="*136}')
        print(HDR)
        for arm, qual in ARMS.items():
            for S in SS:
                line(f'{arm} S>={S}', first(D, lambda c, q_=qual, S_=S: c['sec'] >= S_ and q_(c)), nd,
                     RANK if tag == '4-day' else None)
            print('  ' + '-' * 134)

        print(f'\n{"="*136}\n(3) SKIP-WINDOW - fire normally but never in 60-120 s   [{tag}]\n{"="*136}')
        print(HDR)
        for arm, qual in ARMS.items():
            line(f'{arm} normal', first(D, qual), nd, RANK if tag == '4-day' else None)
            line(f'{arm} skip 60-120', first(D, lambda c, q_=qual: q_(c) and not (60 <= c['sec'] < 120)), nd,
                 RANK if tag == '4-day' else None)

        print(f'\n{"="*136}\n(4) ASK BAND x START SECOND, fixed15 and raw25   [{tag}]\n{"="*136}')
        print(HDR)
        for arm, qual in ARMS.items():
            for lo, hi in BANDS:
                for S in (150, 200):
                    line(f'{arm} ask{lo:.2f}-{hi:.2f} S>={S}',
                         first(D, lambda c, q_=qual, l_=lo, h_=hi, S_=S:
                               c['sec'] >= S_ and l_ <= c['ask'] <= h_ and q_(c)), nd,
                         RANK if tag == '4-day' else None)
            print('  ' + '-' * 134)

    print(f'\n{"="*136}\n(2) EF-2 v0 x START SECOND   [4-day, walk-forward]\n{"="*136}')
    print(HDR)
    # v0 is the MODEL'S SIDE ONLY (ef2_v0b.py: `if c['pe'] < 0.5: continue`). Without that clause the rule
    # degenerates late in the candle: one side's ask collapses to 0.05, be(0.05) = 0.053, so ANY pw above
    # 0.053 clears m=0.00 and the rule just buys the long shot - which is why the unrestricted version below
    # falls to a 29% win rate at S>=230. That is not the model inverting, it is the rule buying the underdog.
    for m in MARG:
        for S in SS:
            line(f'EF-2 m={m:.2f} S>={S}',
                 first(C4, lambda c, m_=m, S_=S: c['sec'] >= S_ and c['pw'] == c['pw'] and c['pw'] >= 0.5
                       and (c['pw'] / be(c['ask']) - 1) >= m_), len(d4), RANK)
        print('  ' + '-' * 134)

    print(f'\n  diagnostic - v0 WITHOUT the side restriction (not an arm, it explains the win% collapse):')
    print(HDR)
    for S in (0, 120, 230):
        sel = first(C4, lambda c, S_=S: c['sec'] >= S_ and c['pw'] == c['pw'] and (c['pw'] / be(c['ask']) - 1) >= 0.0)
        line(f'no-side m=0.00 S>={S}', sel, len(d4))
        fl = [c for c in sel if c['q'] == c['q']]
        if fl: print(f'      mean ask paid {np.mean([c[chr(97)+chr(115)+chr(107)] for c in fl]):.3f}, '
                     f'mean pw {np.mean([c[chr(112)+chr(119)] for c in fl]):.3f}, '
                     f'share of fires on the side pw<0.5: {np.mean([c[chr(112)+chr(119)] < 0.5 for c in fl]):.1%}')

    print(f'\n{"="*136}\n(5) TOP 3 BY PROFIT/DRAWDOWN with n>=60 fills, on the 4-day set where every arm exists'
          f'\n{"="*136}')
    ok = {k: v for k, v in RANK.items() if v['nf'] >= MIN_CELL and v['tot'] > 0}
    top = sorted(ok.items(), key=lambda kv: -kv[1]['ratio'])[:3]
    if not top:
        print('  NO ARM qualifies: no cell has n>=60 fills AND positive total $ on the 4-day set.')
        alt = sorted([kv for kv in RANK.items() if kv[1]['nf'] >= MIN_CELL], key=lambda kv: -kv[1]['ratio'])[:3]
        print('  The three with n>=60 and the best ratio regardless of sign, for the record:')
        for k, v in alt:
            print(f'    {k:30s} $tot {v["tot"]:+.1f}  DD {v["mdd"]:.1f}  P/DD {v["ratio"]:+.2f}  '
                  f'fills {v["nf"]}  days+ {v["pos"]}/{v["days"]}')
    else:
        for k, v in top:
            print(f'\n  --- {k}: $tot {v["tot"]:+.1f}, DD {v["mdd"]:.1f}, P/DD {v["ratio"]:.2f}, '
                  f'{v["nf"]} fills, {v["fpd"]:.1f}/day, days+ {v["pos"]}/{v["days"]} ---')
            print(f'      per day $: ' + '  '.join(f'{d} {v["byd"].get(d, 0.0):+.1f}' for d in d4))
    import json
    json.dump({k: {kk: (vv if not isinstance(vv, dict) else vv) for kk, vv in v.items()}
               for k, v in RANK.items()}, open('/tmp/ef3_rank.json', 'w'), default=float)
    print(f'\n  ranking table written to /tmp/ef3_rank.json for the verify step')
