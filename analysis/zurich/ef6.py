#!/usr/bin/env python3
"""EF-6 (V, 09-28 16:3x): TRAILING-WINDOW quantile - causal AND rate-stable. READ-ONLY. Master OFF.

Arm E's threshold is yesterday's quantile as a VALUE, carried across a nightly refit that moves the
prediction scale, so the same q lands at a different rank every day: 4 fills one day, 188 the next. A
trailing window fixes that without looking forward - at time t the threshold is the q-quantile of THIS
model's predictions over the candidate rows in the last W hours, all of which are already in the past.
At the start of a day the window reaches back into yesterday, scored under TODAY's model.

ONE IMPLEMENTATION CHOICE WORTH STATING: the threshold is recomputed on a 60 s grid rather than at every
row. That is ~1,440 updates a day instead of ~450,000, and it is also what an implementation would really
do - you do not re-sort a six-hour window on every book message. Between updates the rule uses the most
recent threshold, which is strictly the more conservative reading since the threshold is slightly staler.

STABILITY is reported as V asked, because the point of this variant is rate-stability, not profit:
daily fills min / max, their coefficient of variation, and the share of the total $ from the best day.
"""
import sys, os, collections, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import ROWS, per1, cost, be
from ef3 import FITS, platt, pad_cost, STAKE, MIN_CELL
from ef4 import LEVEL

WS = (1, 3, 6)
QS = (0.80, 0.90, 0.95)
GRID_MS = 60_000
CACHE = '/home/ubuntu/pm_ef3/ef5_preds.npz'


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return cum, mdd, worst


def stats(sel, nd):
    fl = sorted([c for c in sel if c['q'] == c['q']], key=lambda c: c['t'])
    if not fl: return None
    seq = [STAKE * per1(c['win'], c['q']) for c in fl]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float); nbyd = collections.Counter()
    for c, x in zip(fl, seq): byd[c['day']] += x; nbyd[c['day']] += 1
    n = list(nbyd.values())
    cv = (float(np.std(n)) / float(np.mean(n))) if n and np.mean(n) > 0 else float('inf')
    best = (max(byd.values()) / tot) if tot > 0 else float('nan')
    den = sum(cost(c['q']) for c in fl); h = len(fl) // 2
    W = lambda s: sum(per1(c['win'], c['q']) * cost(c['q']) for c in s) / sum(cost(c['q']) for c in s) if s else float('nan')
    rng = random.Random(41); real = W(fl); sims = []
    for _ in range(300):
        acc = []
        for c in fl:
            if rng.random() < 0.5:
                if c['oq'] != c['oq']: continue
                acc.append(dict(win=1 - c['win'], q=c['oq']))
            else: acc.append(c)
        if acc: sims.append(W(acc))
    return dict(tot=tot, mdd=mdd, ratio=(tot / mdd if mdd > 0 else 99.9), n=len(sel), nf=len(fl),
                fill=len(fl) / len(sel), fpd=len(sel) / max(nd, 1), run=worst,
                pos=sum(1 for v in byd.values() if v > 0), days=len(byd),
                fmin=min(n), fmax=max(n), cv=cv, best=best, per1=W(fl), h1=W(fl[:h]), h2=W(fl[h:]),
                perm=(sum(1 for x in sims if x >= real) / len(sims)) if sims else float('nan'))


HDR = (f'  {"cell":18s}{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"f/day":>7}{"fill%":>7}{"days+":>6}{"run":>4}|'
       f'{"fmin":>6}{"fmax":>6}{"CV":>7}{"best%":>7}|{"per$1":>8}{"flipP":>7}')


def line(lab, sel, nd):
    s = stats(sel, nd)
    if not s:
        print(f'  {lab:18s}   (no fills)'); return None
    print(f'  {lab:18s}{s["tot"]:>+8.1f}{s["mdd"]:>7.1f}{s["ratio"]:>7.2f}{s["fpd"]:>7.1f}'
          f'{100*s["fill"]:>6.1f}%{f"{s[chr(112)+chr(111)+chr(115)]}/{s[chr(100)+chr(97)+chr(121)+chr(115)]}":>6}{s["run"]:>4}|'
          f'{s["fmin"]:>6}{s["fmax"]:>6}{s["cv"]:>7.2f}'
          f'{(100*s["best"] if s["best"] == s["best"] else float("nan")):>6.0f}%|'
          f'{s["per1"]:>+8.3f}{s["perm"]:>7.3f}' + ('  *n<60' if s['nf'] < MIN_CELL else ''))
    return s


if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, yw, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    yw = yw.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    ia, ip = names.index('own_ask'), names.index('p_side')
    own, pside = X[:, ia].astype(float), X[:, ip].astype(float)
    days = sorted(set(day.tolist()))
    pwf = np.load(CACHE)['pwf']
    opp = {}
    for i in range(len(yw)): opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if np.isfinite(q[i]) else float('nan')

    # per test day: the day's own rows (pwf) plus yesterday's rows scored under the SAME model
    per_day = {}
    for k, d in enumerate(days):
        if k == 0: continue
        pv = f'/tmp/ef5_pprev_{d}.npy'
        if not os.path.exists(pv): continue
        m_t = day == d; m_p = day == days[k - 1]
        tt = np.concatenate([ts[m_p], ts[m_t]])
        pp = np.concatenate([np.load(pv), pwf[m_t]])
        isday = np.concatenate([np.zeros(m_p.sum(), bool), np.ones(m_t.sum(), bool)])
        o = np.argsort(tt, kind='stable')
        per_day[d] = (tt[o], pp[o], isday[o], np.where(m_t)[0])
    print(f'test days {sorted(per_day)}  (each: yesterday + today, both under today\'s model)')

    def thresholds(d, W, qq):
        """q-quantile over the trailing W hours, refreshed on a 60 s grid. Past rows only."""
        tt, pp, isday, _ = per_day[d]
        t0, t1 = tt[isday].min(), tt[isday].max()
        grid = np.arange(t0, t1 + GRID_MS, GRID_MS)
        lo = np.searchsorted(tt, grid - W * 3600_000, side='left')
        hi = np.searchsorted(tt, grid, side='left')          # strictly past
        out = np.full(len(grid), np.nan)
        for i, (a, b) in enumerate(zip(lo, hi)):
            if b - a >= 500: out[i] = np.quantile(pp[a:b], qq)
        return grid, out

    def fire(W, qq):
        sel = []
        for d in sorted(per_day):
            grid, thr = thresholds(d, W, qq)
            tt, pp, isday, idx = per_day[d]
            tday = tt[isday]; pday = pp[isday]
            g = np.searchsorted(grid, tday, side='right') - 1
            g = np.clip(g, 0, len(grid) - 1)
            th = thr[g]
            ok = np.isfinite(th) & (pday >= th)
            byc = {}
            order = np.argsort(tday, kind='stable')
            for j in order:
                if not ok[j]: continue
                i = idx[j]
                if pside[i] < 0.5: continue
                e = int(ep[i])
                if e in byc: continue
                byc[e] = dict(t=int(ts[i]), q=float(q[i]), win=yw[i], day=d, ask=own[i],
                              oq=opp.get((int(ts[i]), int(isup[i])), float('nan')))
            sel += list(byc.values())
        return sel

    nd = len(per_day)
    print('\n' + '=' * 118)
    print('EF-6 TRAILING-WINDOW QUANTILE  (causal: threshold uses only rows strictly before t)')
    print('=' * 118); print(HDR)
    R = {}
    for W in WS:
        for qq in QS:
            s = line(f'W={W}h q={qq:.2f}', fire(W, qq), nd)
            if s: R[f'W={W}h q={qq:.2f}'] = s
        print('  ' + '-' * 116)

    print('=' * 118); print('CONTROL, same test days'); print('=' * 118); print(HDR)
    Cs = collections.defaultdict(list)
    for i in range(len(yw)):
        if str(day[i]) in per_day:
            Cs[int(ep[i])].append(dict(t=int(ts[i]), p=pside[i], ask=own[i], q=float(q[i]), win=yw[i],
                                       day=str(day[i]), oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
    for e in Cs: Cs[e].sort(key=lambda c: c['t'])
    Csel = [c for c in (next((c for c in l if c['p'] >= 0.5 and
            (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15), None) for l in Cs.values()) if c]
    C = line('C fixed15', Csel, nd)

    print('\n' + '=' * 118)
    print('PER-DAY DETAIL for the three best by $, plus C - because CV over FOUR days is a noisy statistic')
    print('=' * 118)
    for k in [x[0] for x in sorted(R.items(), key=lambda kv: -kv[1]['tot'])[:3]] + ['C fixed15']:
        sel = Csel if k == 'C fixed15' else fire(int(k.split('h')[0].split('=')[1]), float(k.split('q=')[1]))
        fl = [c for c in sel if c['q'] == c['q']]
        bd = collections.defaultdict(float); bn = collections.Counter()
        for c in fl:
            bd[c['day']] += STAKE * per1(c['win'], c['q']); bn[c['day']] += 1
        dd = sorted(bd)
        tot = sum(bd.values()); pos = sum(v for v in bd.values() if v > 0)
        bestd = max(bd, key=lambda x: bd[x])
        print(f'  {k:18s} $ ' + '  '.join(f'{d} {bd[d]:+7.1f}' for d in dd))
        print(f'  {"":18s} n ' + '  '.join(f'{d} {bn[d]:7d}' for d in dd))
        print(f'  {"":18s}   best day {bestd} = {100*bd[bestd]/tot if tot else float("nan"):.0f}% of total, '
              f'but {100*bd[bestd]/pos if pos else float("nan"):.0f}% of the POSITIVE days '
              f'(the robust form); rest of days {tot - bd[bestd]:+.1f}')

    print('\n' + '=' * 118)
    print(f'QUALIFYING FOR E3: $ > C, DD <= C, daily-fills CV < 0.50, best-day share < 50%')
    print('=' * 118)
    win = [(k, v) for k, v in R.items() if v['tot'] > C['tot'] and v['mdd'] <= C['mdd']
           and v['cv'] < 0.50 and v['best'] == v['best'] and v['best'] < 0.50 and v['nf'] >= MIN_CELL]
    if win:
        for k, v in sorted(win, key=lambda kv: -kv[1]['ratio']):
            print(f'  {k:18s} $ {v["tot"]:+7.1f} (C {C["tot"]:+.1f})  DD {v["mdd"]:6.1f} (C {C["mdd"]:.1f})  '
                  f'CV {v["cv"]:.2f}  best {100*v["best"]:.0f}%  fills {v["nf"]}  {v["fmin"]}-{v["fmax"]}/day')
    else:
        print('  NONE.')
        for k, v in sorted(R.items(), key=lambda kv: -kv[1]['tot'])[:3]:
            why = []
            if v['tot'] <= C['tot']: why.append('$')
            if v['mdd'] > C['mdd']: why.append('DD')
            if not (v['cv'] < 0.50): why.append(f'CV {v["cv"]:.2f}')
            if not (v['best'] == v['best'] and v['best'] < 0.50): why.append(f'best {100*v["best"]:.0f}%')
            if v['nf'] < MIN_CELL: why.append(f'n {v["nf"]}')
            print(f'  closest: {k:18s} $ {v["tot"]:+7.1f}  DD {v["mdd"]:6.1f}  CV {v["cv"]:.2f}  '
                  f'best {100*v["best"]:.0f}%  -> fails on {", ".join(why)}')
