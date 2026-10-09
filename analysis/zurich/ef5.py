#!/usr/bin/env python3
"""EF-5 (V, 09-28 15:5x): the EF-4 stumps with a CAUSAL QUANTILE cut instead of an absolute threshold.

EF-4's rule died on freezing because `pred >= t` is a cut into the tail of an UNCALIBRATED score: the
same t lands at a different quantile for a 213k-row fit than for a 1.58M-row fit. A quantile cut is
scale-free, so it should survive. This tests that.

THREE READINGS, because the gap between them is the whole point and two of them are easy to conflate:

  IN-DAY   t = the q-quantile of the model's predictions on day k ITSELF. This is what a naive grid does
           and it is NOT causal - it needs the whole test day before it can fire on the first candle.
           Reported only as the upper bound, i.e. how much the threshold choice was peeking.
  CAUSAL   t = the q-quantile on day k-1, scored by the SAME model (fitted on days < k). This is what V
           specified and it is implementable: at the start of day k everything it needs already exists.
  FROZEN   ONE model, fitted on days < the last day, applied to every day, threshold still from day k-1.
           This is exactly what ef3_shadow would run. Arm D died in the step from walk-forward to here.

If CAUSAL ~ IN-DAY the threshold was not peeking. If FROZEN ~ CAUSAL the rule is portable. EF-4 failed
the second comparison; a quantile cut is meant to fix precisely that, so FROZEN vs CAUSAL is the test.

Level features are excluded by CONSTRUCTION, not by a follow-up check - that is what killed the linear.
"""
import sys, os, json, collections, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import ROWS, per1, cost, be
from ef3 import FITS, platt, pad_cost, STAKE, MIN_CELL
from ef4 import gb_reg, gb_reg_pred, LEVEL

QS = (0.70, 0.80, 0.90, 0.95)
DETAIL = set()   # cells to expand, set per mode in __main__
S0S = (0, 60)
CACHE = '/home/ubuntu/pm_ef3/ef5_preds.npz'


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return cum, mdd, worst


def score(sel, nd):
    fl = sorted([c for c in sel if c['q'] == c['q']], key=lambda c: c['t'])
    if not fl: return None
    seq = [STAKE * per1(c['win'], c['q']) for c in fl]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float)
    for c, x in zip(fl, seq): byd[c['day']] += x
    o = sorted(byd.values(), reverse=True)
    den = sum(cost(c['q']) for c in fl); h = len(fl) // 2
    W = lambda s: sum(per1(c['win'], c['q']) * cost(c['q']) for c in s) / sum(cost(c['q']) for c in s) if s else float('nan')
    rng = random.Random(41); sims = []
    real = W(fl)
    for _ in range(300):
        acc = []
        for c in fl:
            if rng.random() < 0.5:
                if c['oq'] != c['oq']: continue
                acc.append(dict(win=1 - c['win'], q=c['oq']))
            else: acc.append(c)
        if acc: sims.append(W(acc))
    return dict(tot=tot, mdd=mdd, ratio=(tot / mdd if mdd > 0 else 99.9), n=len(sel), nf=len(fl),
                byd=dict(byd), win=float(np.mean([c['win'] for c in fl])),
                nbyd={k: sum(1 for c in fl if c['day'] == k) for k in byd},
                fill=len(fl) / len(sel), fpd=len(sel) / max(nd, 1),
                pos=sum(1 for v in byd.values() if v > 0), days=len(byd), run=worst,
                rest=sum(o[2:]), per1=W(fl), h1=W(fl[:h]), h2=W(fl[h:]),
                perm=(sum(1 for x in sims if x >= real) / len(sims)) if sims else float('nan'))


def line(lab, sel, nd):
    s = score(sel, nd)
    if not s:
        print(f'  {lab:30s}  (no fills)'); return None
    print(f'  {lab:30s}{s["tot"]:>+8.1f}{s["mdd"]:>7.1f}{s["ratio"]:>7.2f}{s["fpd"]:>7.1f}'
          f'{100*s["fill"]:>6.1f}%{f"{s[chr(112)+chr(111)+chr(115)]}/{s[chr(100)+chr(97)+chr(121)+chr(115)]}":>7}'
          f'{s["run"]:>5}{s["rest"]:>+9.1f}|{s["per1"]:>+8.3f}{s["h1"]:>+8.3f}{s["h2"]:>+8.3f}{s["perm"]:>7.3f}'
          + ('  *n<60' if s['nf'] < MIN_CELL else ''))
    if DETAIL and lab in DETAIL:
        dd = sorted(s['byd'])
        print(f'      per day $:     ' + '  '.join(f'{k} {s["byd"][k]:+7.1f}' for k in dd))
        print(f'      per day fills: ' + '  '.join(f'{k} {s["nbyd"][k]:7d}' for k in dd))
        print(f'      fires {s["n"]}  fills {s["nf"]}  fill% {100*s["fill"]:.1f}  win% {100*s["win"]:.1f}  '
              f'per$1 {s["per1"]:+.3f}  H1 {s["h1"]:+.3f}  H2 {s["h2"]:+.3f}  run {s["run"]}  '
              f'flip p {s["perm"]:.3f}')
    return s


HDR = (f'  {"cell":30s}{"$tot":>8}{"DD$":>7}{"P/DD":>7}{"f/day":>7}{"fill%":>7}{"days+":>7}{"run":>5}'
       f'{"rest$":>9}|{"per$1":>8}{"H1":>8}{"H2":>8}{"flipP":>7}')

if __name__ == '__main__':
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    X, yw, q, ep, ts, day = (z[k][keep] for k in ('X', 'y', 'q', 'ep', 'ts', 'day'))
    yw = yw.astype(float); isup = z['is_up'][keep]
    names = [str(s) for s in z['names']]
    ia, ip, isec = names.index('own_ask'), names.index('p_side'), names.index('sec')
    own, pside, sec = X[:, ia].astype(float), X[:, ip].astype(float), X[:, isec].astype(int)
    drop = {names.index(k) for k in LEVEL if k in names}
    cols = [i for i in range(len(names)) if i not in drop]
    Xm = X[:, cols].astype(np.float64); fnames = [names[i] for i in cols]
    filled = np.isfinite(q)
    tgt = np.where(filled, per1(yw, np.where(filled, q, 0.5)), 0.0)
    days = sorted(set(day.tolist()))
    print(f'rows {len(yw):,}  features {len(fnames)} (levels excluded by construction)  days {days}')

    if os.path.exists(CACHE):
        C = np.load(CACHE); pwf, pfr = C['pwf'], C['pfr']
        print('loaded cached predictions')
    else:
        pwf = np.full(len(yw), np.nan)        # walk-forward: day k and k-1 by the model fitted on days<k
        pprev = np.full(len(yw), np.nan)      # day k-1 scored by the SAME model that scores day k
        for k, dcur in enumerate(days):
            if k == 0: continue
            tr = np.isin(day, days[:k]); te = day == dcur; pv = day == days[k - 1]
            mu, sd = Xm[tr].mean(0), Xm[tr].std(0); sd = np.where(sd > 0, sd, 1.0)
            g = gb_reg((Xm[tr] - mu) / sd, tgt[tr])
            pwf[te] = gb_reg_pred(g, (Xm[te] - mu) / sd)
            pprev[pv] = gb_reg_pred(g, (Xm[pv] - mu) / sd)   # overwritten per k on purpose
            np.save('/tmp/ef5_pprev_%s.npy' % dcur, pprev[pv])
            print(f'  fitted for {dcur} on {tr.sum():,} rows')
        trf = np.isin(day, days[:-1])
        muf, sdf = Xm[trf].mean(0), Xm[trf].std(0); sdf = np.where(sdf > 0, sdf, 1.0)
        gf = gb_reg((Xm[trf] - muf) / sdf, tgt[trf])
        pfr = gb_reg_pred(gf, (Xm - muf) / sdf)
        print(f'  frozen model fitted on {trf.sum():,} rows, days {days[:-1]}')
        np.savez_compressed(CACHE, pwf=pwf, pfr=pfr)

    opp = {}
    for i in range(len(yw)): opp[(int(ts[i]), 1 - int(isup[i]))] = float(q[i]) if filled[i] else float('nan')

    def build(pred, thr_by_day):
        C = collections.defaultdict(list)
        for i in range(len(yw)):
            d = str(day[i])
            if d not in thr_by_day or not np.isfinite(pred[i]): continue
            C[int(ep[i])].append(dict(t=int(ts[i]), p=pside[i], ask=own[i], q=float(q[i]), win=yw[i],
                                      sec=int(sec[i]), day=d, pr=float(pred[i]), thr=thr_by_day[d],
                                      oq=opp.get((int(ts[i]), int(isup[i])), float('nan'))))
        for e in C: C[e].sort(key=lambda c: c['t'])
        return C

    def fire(C, S0):
        out = []
        for e, lst in C.items():
            c = next((c for c in lst if c['sec'] >= S0 and c['p'] >= 0.5 and c['pr'] >= c['thr']), None)
            if c is not None: out.append(c)
        return out

    test = days[1:]; nd = len(test)
    print(f'\ntest days {test}\n')
    for mode in ('IN-DAY (not causal, upper bound)', 'CAUSAL (t from day k-1)', 'FROZEN (one model)'):
        print('=' * 130); print(f'{mode}'); print('=' * 130); print(HDR)
        for qq in QS:
            thr = {}
            for k, dcur in enumerate(days):
                if k == 0: continue
                if mode.startswith('IN-DAY'):
                    v = pwf[day == dcur]
                elif mode.startswith('CAUSAL'):
                    p = np.load('/tmp/ef5_pprev_%s.npy' % dcur) if os.path.exists(
                        '/tmp/ef5_pprev_%s.npy' % dcur) else None
                    v = p if p is not None else pwf[day == days[k - 1]]
                else:
                    v = pfr[day == days[k - 1]]
                v = v[np.isfinite(v)]
                if len(v): thr[dcur] = float(np.quantile(v, qq))
            pred = pfr if mode.startswith('FROZEN') else pwf
            globals()['DETAIL'] = ({'q=0.90 S0=0', 'q=0.95 S0=0'} if mode.startswith('CAUSAL') else set())
            for S0 in S0S:
                line(f'q={qq:.2f} S0={S0}', fire(build(pred, thr), S0), nd)
            print('  ' + '-' * 128)

    print('=' * 130); print('CONTROL on the same test days'); print('=' * 130); print(HDR)
    thrall = {d: -9e9 for d in test}
    Call = build(pwf, thrall)
    line('C fixed15', [c for c in (next((c for c in l if c['p'] >= 0.5 and
         (platt(c['p']) / pad_cost(c['ask']) - 1) >= 0.15), None) for l in Call.values()) if c], nd)
    line('B raw25 S>=60', [c for c in (next((c for c in l if c['sec'] >= 60 and c['p'] >= 0.5 and
         (c['p'] / be(c['ask']) - 1) >= 0.25), None) for l in Call.values()) if c], nd)
