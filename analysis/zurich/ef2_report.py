#!/usr/bin/env python3
"""EF-2 steps 2b/3/5: every table, built from the cached walk-forward fits. READ-ONLY, master OFF.

THE ACCEPTANCE BAR (V, owner, 09-28 11:2x): London is NOT paused and keeps fixed15 until EF-2 beats it on
PROFIT and on EXECUTION, on the same days, walk-forward. So every arm below - EF-2 at each margin, fixed15,
the S=15 placebo, raw25 - is scored through one function with one set of columns, on one candidate table, so
that the only thing differing between rows is the rule.

  profit    per $1 (capital-weighted), total $ at $10 nominal, win% of fills
  execution fires/day, sim fill%, reject/no-fill rate, mean slippage of the fill price against the QUOTED ask
  evidence  H1/H2, permutation (flip priced at the opposite side's real ask, same FAK test on both arms)

DECISION PRICE is the quoted ask, never the fill price; the lookahead variant is printed separately so the
size of that choice is visible rather than argued about.
"""
import sys, math, collections, numpy as np
from decimal import Decimal, ROUND_CEILING
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, per1, cost, halves, perm_opp, auc, be, MIN_CELL, MARGINS

FITS = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/pm_ef2/ef2_fits.npz'
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


HDR = (f'  {"arm":26s}{"fires":>6}{"/day":>6}{"fills":>6}{"fill%":>7}{"nofill%":>8}{"slip c":>8}'
       f'{"win%":>7}{"per$1":>9}{"total$":>9}{"H1":>8}{"H2":>8}{"permP":>7}')


def line(label, sel, nday):
    if not sel:
        print(f'  {label:26s}{0:>6}   (no fires)'); return None
    fl = [s for s in sel if s['q'] == s['q']]
    tup = [(s['win'], s['q'], s['t'], s['oq']) for s in sel]
    h1, h2 = halves(tup)
    slip = [100 * (s['q'] - s['ask']) for s in fl]
    tot = sum(10.0 * per1(s['win'], s['q']) for s in fl)
    v = Wsel(sel)
    print(f'  {label:26s}{len(sel):>6}{len(sel)/max(nday,1):>6.0f}{len(fl):>6}'
          f'{100*len(fl)/len(sel):>6.1f}%{100*(1-len(fl)/len(sel)):>7.1f}%'
          f'{(np.mean(slip) if slip else float("nan")):>+8.2f}'
          f'{(100*np.mean([s["win"] for s in fl]) if fl else float("nan")):>6.1f}%'
          f'{v:>+9.3f}{tot:>+9.1f}{(h1 if h1==h1 else 0):>+8.3f}{(h2 if h2==h2 else 0):>+8.3f}'
          f'{perm_opp(tup):>7.3f}' + ('  *n<60' if len(fl) < MIN_CELL else ''))
    return dict(n=len(sel), nf=len(fl), fill=len(fl)/len(sel), slip=(np.mean(slip) if slip else float('nan')),
                per1=v, total=tot, h1=h1, h2=h2,
                win=(np.mean([s['win'] for s in fl]) if fl else float('nan')))


def fire(cands, rule, use_fill=False):
    out = []
    for ep, lst in cands.items():
        for c in sorted(lst, key=lambda c: (c['t'], -c['p'])):
            px = c['q'] if use_fill else c['ask']
            if px != px: continue
            if not rule(c, px): continue
            out.append(c); break
    return out


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    y = y.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    pw = f['pw']
    pg = f['pg'] if 'pg' in f.files else np.full(len(pw), np.nan)
    sc = np.isfinite(pw)
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    dayset = sorted(set(day[sc].tolist())); nday = len(dayset)
    print(f'walk-forward days {dayset}; scored rows {int(sc.sum()):,}; candles {len(set(ep[sc].tolist()))}')
    print(f'AUC  logistic {auc(y[sc], pw[sc]):.4f}   stumps {auc(y[sc], pg[sc]):.4f}   '
          f'own_ask alone {auc(y[sc], -X[sc, ia]):.4f}   p_side alone {auc(y[sc], X[sc, ip]):.4f}')

    # AUC rises mechanically with the second, because by sec 240 the ask is nearly the answer. Reporting it
    # by bucket stops a high pooled AUC being read as skill that is really just late-candle certainty.
    print(f'  AUC by second bucket (logistic / own_ask alone / p_side alone):')
    for lo, hi in ((15, 30), (30, 60), (60, 120), (120, 180), (180, 241)):
        m2 = sc & (X[:, isec] >= lo) & (X[:, isec] < hi)
        if m2.sum() < 200: continue
        print(f'    sec {lo:>3}-{hi-1:<3} n {int(m2.sum()):>9,}  {auc(y[m2], pw[m2]):.4f}  '
              f'{auc(y[m2], -X[m2, ia]):.4f}  {auc(y[m2], X[m2, ip]):.4f}')

    opp = {}
    for i in np.nonzero(sc)[0]:
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    cands = collections.defaultdict(list)
    for i in np.nonzero(sc)[0]:
        cands[int(ep[i])].append(dict(t=int(ts[i]), p=float(pw[i]), pe=float(X[i, ip]),
                                      ask=float(X[i, ia]), q=float(q[i]), win=float(y[i]),
                                      sec=int(X[i, isec]),
                                      oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))

    print(f'\n{"="*126}\nACCEPTANCE TABLE [' + FITS.split('/')[-1] + '] - fixed15 vs EF-2, same candles, same fill simulator, same days\n{"="*126}')
    print(HDR)
    base = line('fixed15 (London, live)',
                fire(cands, lambda c, px: c['pe'] >= 0.5 and (platt(c['pe']) / pad_cost(px) - 1) >= 0.15), nday)
    print('  ' + '-' * 124)
    res = {}
    for m in MARGINS:
        res[m] = line(f'EF-2 margin {m:.2f}', fire(cands, lambda c, px, m=m: c['p'] / be(px) - 1 >= m), nday)
    print('  ' + '-' * 124)
    line('S=15 placebo', fire(cands, lambda c, px: c['pe'] >= 0.5 and c['sec'] >= 15 and px <= 0.60), nday)
    line('raw25 (EV>=0.25)', fire(cands, lambda c, px: c['pe'] >= 0.5 and (c['pe'] / be(px) - 1) >= 0.25), nday)

    print(f'\n  VERDICT against the owner\'s bar - a version must win PROFIT and EXECUTION, not one of them:')
    if base:
        for m in MARGINS:
            r = res[m]
            if not r: continue
            prof = (r['per1'] > base['per1']) and (r['total'] > base['total'])
            exe = (r['fill'] > base['fill']) and (r['slip'] <= base['slip'])
            ok = prof and exe
            print(f'    margin {m:.2f}: profit {"WIN " if prof else "lose"} '
                  f'(per$1 {r["per1"]:+.3f} vs {base["per1"]:+.3f}, total {r["total"]:+.1f} vs {base["total"]:+.1f})'
                  f'   execution {"WIN " if exe else "lose"} '
                  f'(fill {100*r["fill"]:.1f}% vs {100*base["fill"]:.1f}%, slip {r["slip"]:+.2f}c vs '
                  f'{base["slip"]:+.2f}c)   -> {"PASSES BOTH" if ok else "does not pass"}')

    print(f'\n  LOOKAHEAD VARIANT (decision taken at the fill price) - to size that choice, not to be quoted:')
    print(HDR)
    for m in MARGINS:
        line(f'lookahead {m:.2f}', fire(cands, lambda c, px, m=m: c['p'] / be(px) - 1 >= m, use_fill=True), nday)

    # v0 exports coefficients, v1 exports permutation importance. Permutation is the better measure of
    # whether the model LEANS on a feature - a coefficient can be large only because its feature is
    # collinear with another - so where the two disagree the permutation number is the one to believe.
    # a refit on a CUT feature list ships its own names; using the row table's 52 against a 44-wide
    # coefficient matrix is how this section broke on the London refit.
    fnames = [str(x) for x in f['names']] if 'names' in f.files else names
    if 'coef' in f.files and f['coef'].shape[1] == len(fnames) + 1:
        print(f'\n{"="*126}\nFEATURE IMPORTANCE - |standardised coefficient|, mean over the walk-forward '
              f'fits\n{"="*126}')
        A = np.mean(np.abs(f['coef'][:, 1:]), axis=0)
    elif 'imp' in f.files and len(f['imp']) == len(fnames):
        print(f'\n{"="*126}\nFEATURE IMPORTANCE - PERMUTATION (AUC lost when the column is shuffled)\n{"="*126}')
        A = f['imp']
    else:
        print(f'\n(no importance vector matching {len(fnames)} features in this fits file)')
        A = None
    names = fnames
    DYN = ('d_ask_1s', 'd_ask_5s', 'd_ask_30s', 'dip30')
    PRICE = ('own_ask', 'opp_ask', 'lv', 'p_venue', '_ask_up', '_ask_dn')
    MOVE = ('move_bps', 'mv_x_sec')
    if A is not None:
        order = np.argsort(-A)
        for r, j in enumerate(order[:18], 1):
            tag = '  <- ASK DYNAMICS' if names[j] in DYN else '  <- the price' if names[j] in PRICE else \
                  '  <- the move' if names[j] in MOVE else '  <- the engine p' if names[j] == 'p_side' else ''
            print(f'    {r:>2}. {names[j]:16s} {A[j]:.4f}{tag}')
        print(f'\n  block totals - V\'s question is whether the first line beats the third:')
        for lab, ks in (('ask dynamics (d1,d5,d30,dip30)', DYN), ('the price (ask/lv/p_venue)', PRICE),
                        ('the move (move_bps,mv_x_sec)', MOVE), ('the engine model p (p_side)', ('p_side',))):
            print(f'    {lab:34s} {sum(A[names.index(k)] for k in ks if k in names):.4f}')
