#!/usr/bin/env python3
"""EF-11 rule + report. Side pinned to the MODEL's own preference (tape1s has no engine p)."""
import sys, os, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1
from ef3 import STAKE
from ef11 import CACHE, Q, ANCHORS, G_MS, W_MS, strict_thr, dd_run


def sc(f, nd, hc=0.0):
    fl = [x for x in f if x['q'] == x['q']]
    if not fl: return None
    qs = [min(x['q'] + hc, 0.99) for x in fl]
    seq = [STAKE * per1(x['win'], b) for x, b in zip(fl, qs)]
    tot, mdd = dd_run(seq)
    byd = collections.defaultdict(float)
    for x, v in zip(fl, seq): byd[x['day']] += v
    return dict(tot=tot, mdd=mdd, n=len(f), nf=len(fl), fill=len(fl) / len(f), fpd=len(f) / max(nd, 1),
                win=float(np.mean([x['win'] for x in fl])), ask=float(np.mean([x['ask'] for x in fl])),
                byd=dict(byd), pos=sum(1 for v in byd.values() if v > 0), days=len(byd))


if __name__ == '__main__':
    D = np.load(CACHE, allow_pickle=True)
    ep, ts, day, own, y, q, up = (D[x] for x in ('ep', 'ts', 'day', 'own', 'y', 'q', 'up'))
    pred = np.load('/home/ubuntu/pm_ef3/ef11_pred.npz')['pred']
    ok = np.isfinite(pred)
    days = sorted(set(day[ok].tolist())); nd = len(days)
    # the model's own side: of the two rows at a (candle, second), keep the higher prediction
    key = ep.astype(np.int64) * 1000 + ts % 1000 if False else (ep.astype(np.int64) << 20) + (ts // 1000 - ep)
    best = {}
    for i in np.where(ok)[0]:
        kk = int(key[i])
        if kk not in best or pred[i] > pred[best[kk]]: best[kk] = i
    keep = np.zeros(len(pred), bool); keep[list(best.values())] = True
    print(f'EF-11, 1 s tape, {nd} test days {days}')
    print(f'  side pinned to the MODEL\'s own preference (tape1s carries no engine p) - a DIFFERENT rule '
          f'from EF-9 v1\'s p_side pin')
    print(f'  rows {len(pred):,}  scored {int(ok.sum()):,}  model-side rows {int(keep.sum()):,}')

    def fire(anch):
        out = []
        for d in days:
            m = np.where((day == d) & ok & keep)[0]
            if not len(m): continue
            o = m[np.argsort(ts[m], kind='stable')]
            t = ts[o]; p = pred[o]
            t0 = (t.min() // G_MS) * G_MS + anch * 1000
            grid = np.arange(t0, t.max() + G_MS, G_MS)
            lo = np.searchsorted(t, grid - W_MS, 'left'); hi = np.searchsorted(t, grid, 'left')
            thr = np.full(len(grid), np.inf)
            for i2, (a, b) in enumerate(zip(lo, hi)):
                if b - a >= 500: thr[i2] = strict_thr(np.sort(p[a:b]), Q)
            g = np.clip(np.searchsorted(grid, t, 'right') - 1, 0, len(grid) - 1)
            good = p >= thr[g]
            seen = set()
            for j in range(len(o)):
                if not good[j]: continue
                i = o[j]; e = int(ep[i])
                if e in seen: continue
                seen.add(e)
                out.append(dict(i=i, day=d, q=float(q[i]), win=float(y[i]), ask=float(own[i])))
        return out

    tots, favs = [], []
    for a in ANCHORS:
        f = fire(a); s = sc(f, nd)
        if not s: print(f'  anchor {a:2d}s: no fills'); continue
        s1, s2 = sc(f, nd, 0.01), sc(f, nd, 0.02)
        fav = [dict(q=x['q'] if own[x['i']] <= 1 - own[x['i']] else np.nan,
                    win=x['win'] if own[x['i']] <= 1 - own[x['i']] else 1 - x['win'],
                    day=x['day'], ask=min(own[x['i']], 1 - own[x['i']])) for x in f]
        fv = sc([z for z in fav if z['q'] == z['q']] or fav, nd)
        tots.append(s['tot']); favs.append(fv['tot'] if fv else np.nan)
        print(f'  anchor {a:2d}s  $ {s["tot"]:+8.1f}  DD {s["mdd"]:6.1f}  {s["fpd"]:5.1f}/day  '
              f'fill {100*s["fill"]:5.1f}%  win {100*s["win"]:5.1f}%  ask {s["ask"]:.3f}  '
              f'+1c {s1["tot"]:+7.1f}  +2c {s2["tot"]:+7.1f}  days+ {s["pos"]}/{s["days"]}')
        print(f'            per day $ ' + '  '.join(f'{d} {s["byd"].get(d,0.0):+6.1f}' for d in days))
    if tots:
        print(f'\n  MEAN over anchors $ {np.mean(tots):+.1f}  [min {min(tots):+.1f}, max {max(tots):+.1f}]')
        print(f'  FAVOURITE NULL at the same passes, mean $ {np.nanmean(favs):+.1f}')
