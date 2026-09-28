#!/usr/bin/env python3
"""EF-3 follow-up (V, 09-28 14:1x): is S0=60 a plateau or an isolated spike? READ-ONLY. Master OFF.

(a) fine start-second curve for raw25 AND fixed15 at 30/45/60/75/90/105/120
(b) the full column set for raw25 S0=60, plus verify.py
(c) paired test against raw25 S0=0 on the DISCORDANT candles only

The whole point of (a) is that one cell out of a coarse grid is not a finding. If 45-90 sits at a level
and 30 and 120 fall away, the clock is doing something. If 60 stands alone between neighbours that look
like nothing, the grid picked it and there is no rule there.
"""
import sys, os, sqlite3, collections, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/h1')
from verify import Finding
from ef2_model import ROWS, per1, cost, be, halves, perm_opp
from ef3 import FITS, platt, pad_cost, STAKE, MIN_CELL, score, HDR, line

FINE = (30, 45, 60, 75, 90, 105, 120)


def load():
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, y, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    y = y.astype(float); isup = z['is_up'][keep]; names = [str(s) for s in z['names']]
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    opp = {}
    for i in range(len(y)):
        opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if q[i] == q[i] else float('nan')
    C = collections.defaultdict(list)
    for i in range(len(y)):
        C[int(ep[i])].append(dict(t=int(ts[i]), p=float(X[i, ip]), ask=float(X[i, ia]), q=float(q[i]),
                                  win=float(y[i]), sec=int(X[i, isec]), day=str(day[i]), up=int(isup[i]),
                                  oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
    for e in C: C[e].sort(key=lambda c: c['t'])
    return C, sorted(set(day.tolist()))


QUAL = {'raw25': lambda c: c['p'] >= 0.5 and (c['p'] / be(c['ask']) - 1) >= 0.25,
        'fixed15': lambda c: c['p'] >= 0.5 and (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15}


def fire(C, arm, S):
    out = []
    for e, lst in C.items():
        c = next((c for c in lst if c['sec'] >= S and QUAL[arm](c)), None)
        if c is not None: out.append(c)
    return out


def W(sel, hc=0.0):
    fl = [s for s in sel if s['q'] == s['q']]
    if not fl: return float('nan')
    qs = [min(s['q'] + hc, 0.99) for s in fl]
    return sum(per1(s['win'], b) * cost(b) for s, b in zip(fl, qs)) / sum(cost(b) for b in qs)


if __name__ == '__main__':
    C, days = load()
    nd = len(days)
    # guard: this loader must reproduce the published EF-3 table, or the curve below is not comparable
    base = score(fire(C, 'raw25', 0), nd)
    assert len(C) == 1015, f'candle count {len(C)} != 1015'
    assert abs(base['tot'] - 107.3) < 0.15 and abs(base['mdd'] - 98.4) < 0.15, \
        f'raw25 S>=0 is {base["tot"]:+.1f}/{base["mdd"]:.1f}, EF3.md published +107.3/98.4'
    print(f'loader check OK: {len(C)} candles, days {days}, raw25 S>=0 reproduces +107.3 / DD 98.4\n')

    print('=' * 136)
    print('(a) FINE START-SECOND CURVE - plateau or spike?   [5 days, per-pass FAK]')
    print('=' * 136)
    print(HDR)
    curves = {}
    for arm in ('raw25', 'fixed15'):
        cur = []
        for S in FINE:
            s = line(f'{arm} S>={S}', fire(C, arm, S), nd)
            cur.append(s['tot'] if s else float('nan'))
        curves[arm] = cur
        print('  ' + '-' * 134)
    for arm in ('raw25', 'fixed15'):
        v = curves[arm]
        i = int(np.nanargmax(v))
        nb = [v[j] for j in (i - 1, i + 1) if 0 <= j < len(v)]
        print(f'  {arm}: peak at S={FINE[i]} (${v[i]:+.1f}); neighbours ' +
              ', '.join(f'${x:+.1f}' for x in nb) +
              f'  -> {"PLATEAU, the neighbours hold" if nb and min(nb) > 0.6 * v[i] else "ISOLATED SPIKE"}')

    print('\n' + '=' * 136)
    print('(b) raw25 S0=60 in full   [5 days]')
    print('=' * 136)
    sel = fire(C, 'raw25', 60); fl = [s for s in sel if s['q'] == s['q']]
    s = score(sel, nd)
    print(f'  fires {s["n"]}  fills {s["nf"]}  fill% {100*s["fill"]:.1f}  win% {100*s["win"]:.1f}  '
          f'per$1 {s["per1"]:+.3f}')
    print(f'  $ total {s["tot"]:+.1f} at ${STAKE:.0f}   worst DD ${s["mdd"]:.1f}   P/DD {s["ratio"]:.2f}   '
          f'{s["fpd"]:.1f} fires/day   days+ {s["pos"]}/{s["days"]}   longest losing run {s["run"]}')
    print(f'  per day $:     ' + '  '.join(f'{d} {s["byd"].get(d, 0.0):+7.1f}' for d in days))
    ndd = collections.Counter(x['day'] for x in fl)
    print(f'  per day fills: ' + '  '.join(f'{d} {ndd.get(d, 0):7d}' for d in days))
    wd = {d: np.mean([x['win'] for x in fl if x['day'] == d]) for d in days if ndd.get(d)}
    print(f'  per day win%:  ' + '  '.join(f'{d} {100*wd[d]:6.1f}%' if d in wd else f'{d}      -' for d in days))
    print(f'  H1 {s["h1"]:+.3f}  H2 {s["h2"]:+.3f}   mean ask {np.mean([x["ask"] for x in fl]):.3f}')
    print(f'  opposite-ask flip p = {s["perm"]:.3f}')
    print(f'  cost:  +0c {W(sel):+.3f}   +1c {W(sel, 0.01):+.3f}   +2c {W(sel, 0.02):+.3f}')

    print('\n' + '=' * 136)
    print('(c) PAIRED vs raw25 S0=0, discordant candles only')
    print('=' * 136)
    b0 = fire(C, 'raw25', 0)
    m60 = {s['t'] // 1000 // 300 * 300: s for s in fl}
    m00 = {s['t'] // 1000 // 300 * 300: s for s in b0 if s['q'] == s['q']}
    both = sorted(set(m60) & set(m00))
    same = sum(1 for e in both if m60[e]['t'] == m00[e]['t'])
    disc = [e for e in both if m60[e]['win'] != m00[e]['win']]
    a_win = sum(1 for e in disc if m60[e]['win'] == 1)
    print(f'  candles where both fire and fill: {len(both)}   of which the SAME pass: {same} '
          f'({100*same/max(len(both),1):.0f}%)  <- S0=60 changes the trade in only {len(both)-same} of them')
    print(f'  discordant on the outcome: {len(disc)}   S0=60 right {a_win}, S0=0 right {len(disc)-a_win}')
    if disc:
        d60 = sum(STAKE * per1(m60[e]['win'], m60[e]['q']) for e in disc)
        d00 = sum(STAKE * per1(m00[e]['win'], m00[e]['q']) for e in disc)
        print(f'  $ on the discordant set only: S0=60 {d60:+.1f}  vs  S0=0 {d00:+.1f}')

    print('\n' + '=' * 136)
    print('verify.py on raw25 S0=60')
    print('=' * 136)
    g = []
    for p in ('/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3'):
        try:
            c = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
            g.append({int(e): o for e, o in c.execute(
                "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
        except Exception: g.append({})

    def pnl_fn(yv, pv, price):
        fq = price[:, 0]; k = pv >= 0.5
        if k.sum() == 0: return float('nan')
        return sum(per1(a, b) * cost(b) for a, b in zip(yv[k], fq[k])) / sum(cost(b) for b in fq[k])

    F = Finding('raw25 S0=60 (fire no earlier than second 60)', per_fire=W(sel), n=len(fl))
    F.grading(gamma_btc5=g[0], gamma_btc5b=g[1])
    F.quote_age('at-or-after', 0.0, source='decide_log own-side ask at >= t+250 ms; DECISION on the quoted ask')
    F.sample({'fires': len(sel), 'filled': len(fl)})
    F.sample(dict(ndd))
    F.halves(s['h1'], s['h2'])
    F.permutation(np.array([x['win'] for x in fl]), np.array([x['p'] for x in fl]),
                  np.c_[np.array([x['q'] for x in fl]), np.array([x['ask'] for x in fl])], pnl_fn, draws=400)
    print(f"    V's control - flip priced at the OPPOSITE real ask: p = {s['perm']:.3f}")
    sw = [W(fire(C, 'raw25', S)) for S in FINE]
    print(f'    fine sweep {FINE} -> ' + ' '.join(f'{v:+.3f}' for v in sw))
    F.sweep(sw)
    F.costs({h: W(sel, h) for h in (0.0, 0.005, 0.01, 0.02)})
    F.null(W(sel), W(b0), 'raw25 with no start-second bar')
    if disc:
        F.paired([m60[e]['win'] == 1 for e in both], [m00[e]['win'] == 1 for e in both])
    F.verdict()
