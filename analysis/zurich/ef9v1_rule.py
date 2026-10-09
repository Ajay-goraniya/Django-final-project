#!/usr/bin/env python3
"""EF-9 v1 decision rule + report. Same rule as E4 and as the INSUF run, so the tables compare."""
import sys, os, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1
from ef3 import platt, pad_cost, STAKE

G, Q, ANCHORS, W_MS = 60_000, 0.90, (0, 15, 30, 45), 3600_000


def strict_thr(sv, qq):
    if len(sv) < 500: return np.inf
    qv = float(np.quantile(sv, qq))
    i = int(np.searchsorted(sv, qv, 'right'))
    return float(sv[i]) if i < len(sv) else np.inf


def dd_run(seq):
    cum = peak = mdd = 0.; run = worst = 0
    for x in seq:
        cum += x; peak = max(peak, cum); mdd = max(mdd, peak - cum)
        run = run + 1 if x < 0 else 0; worst = max(worst, run)
    return cum, mdd, worst


def score(f, nd, hc=0.0):
    fl = [x for x in f if x['q'] == x['q']]
    if not fl: return None
    qs = [min(x['q'] + hc, 0.99) for x in fl]
    seq = [STAKE * per1(x['win'], b) for x, b in zip(fl, qs)]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float)
    for x, v in zip(fl, seq): byd[x['day']] += v
    return dict(tot=tot, mdd=mdd, n=len(f), nf=len(fl), fill=len(fl) / len(f), fpd=len(f) / max(nd, 1),
                win=float(np.mean([x['win'] for x in fl])), ask=float(np.mean([x['ask'] for x in fl])),
                run=worst, byd=dict(byd), pos=sum(1 for v in byd.values() if v > 0), days=len(byd))


if __name__ == '__main__':
    M = np.load('/home/ubuntu/pm_ef3/ef9v1_meta.npz', allow_pickle=True)
    y, q, ep, ts, ps, day, own = (M[k] for k in ('y', 'q', 'ep', 'ts', 'ps', 'day', 'own'))
    pred = np.load('/home/ubuntu/pm_ef3/ef9v1_pred.npy')
    ok = np.isfinite(pred)
    days = sorted(set(day[ok].tolist())); nd = len(days)
    print(f'EF-9 v1 - 10 channels incl. Binance spot+perp price and SIGNED taker flow')
    print(f'  test days {days}   (09-28 has no published aggTrades yet and is excluded)')

    def fire(anch):
        out = []
        for d in days:
            m = np.where((day == d) & ok)[0]
            if not len(m): continue
            o = m[np.argsort(ts[m], kind='stable')]
            t = ts[o]; p = pred[o]
            t0 = (t.min() // G) * G + anch * 1000
            grid = np.arange(t0, t.max() + G, G)
            lo = np.searchsorted(t, grid - W_MS, 'left'); hi = np.searchsorted(t, grid, 'left')
            thr = np.full(len(grid), np.inf)
            for i2, (a, b) in enumerate(zip(lo, hi)):
                if b - a >= 500: thr[i2] = strict_thr(np.sort(p[a:b]), Q)
            g = np.clip(np.searchsorted(grid, t, 'right') - 1, 0, len(grid) - 1)
            good = p >= thr[g]
            seen = set()
            for j in range(len(o)):
                if not good[j]: continue
                i = o[j]
                if ps[i] < 0.5: continue
                e = int(ep[i])
                if e in seen: continue
                seen.add(e)
                out.append(dict(i=i, day=d, q=float(q[i]), win=float(y[i]), ask=float(own[i])))
        return out

    tots = []; favs = []
    for a in ANCHORS:
        f = fire(a); s = score(f, nd)
        if not s: print(f'  anchor {a:2d}s: no fills'); continue
        s1, s2 = score(f, nd, 0.01), score(f, nd, 0.02)
        fav = [dict(q=x['q'] if own[x['i']] <= 1 - own[x['i']] else np.nan,
                    win=x['win'] if own[x['i']] <= 1 - own[x['i']] else 1 - x['win'],
                    day=x['day'], ask=min(own[x['i']], 1 - own[x['i']])) for x in f]
        fv = score([z for z in fav if z['q'] == z['q']] or fav, nd)
        tots.append(s['tot']); favs.append(fv['tot'] if fv else float('nan'))
        print(f'  anchor {a:2d}s  $ {s["tot"]:+8.1f}  DD {s["mdd"]:6.1f}  {s["fpd"]:6.1f}/day  '
              f'fill {100*s["fill"]:5.1f}%  win {100*s["win"]:5.1f}%  ask {s["ask"]:.3f}  '
              f'+1c {s1["tot"]:+7.1f}  +2c {s2["tot"]:+7.1f}  days+ {s["pos"]}/{s["days"]}')
        print(f'            per day $ ' + '  '.join(f'{d} {s["byd"].get(d,0.0):+7.1f}' for d in days))
    if tots:
        print(f'\n  MEAN over anchors $ {np.mean(tots):+.1f}  [min {min(tots):+.1f}, max {max(tots):+.1f}]')
        print(f'  FAVOURITE NULL at the same passes, mean $ {np.nanmean(favs):+.1f}')
    C = []
    for d in days:
        m = np.where((day == d) & ok)[0]
        seen = set()
        for i in m[np.argsort(ts[m], kind='stable')]:
            if ps[i] < 0.5: continue
            if (platt(float(ps[i])) / pad_cost(float(own[i])) - 1) < 0.15: continue
            e = int(ep[i])
            if e in seen: continue
            seen.add(e)
            C.append(dict(q=float(q[i]), win=float(y[i]), ask=float(own[i]), day=d))
    cs = score(C, nd)
    if cs: print(f'  fixed15 control      $ {cs["tot"]:+8.1f}  DD {cs["mdd"]:6.1f}  {cs["fpd"]:6.1f}/day  '
                 f'fill {100*cs["fill"]:5.1f}%  win {100*cs["win"]:5.1f}%  ask {cs["ask"]:.3f}')
