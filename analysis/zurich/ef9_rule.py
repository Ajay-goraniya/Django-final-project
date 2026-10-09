#!/usr/bin/env python3
"""EF-9 decision rule + report. READ-ONLY. PAPER. Master OFF.

Strict q.90 trailing-1h cut (smallest distinct prediction above the sample quantile), pinned p_side>=0.5,
first qualifying pass, one fire per candle, grid anchors 0/15/30/45 s - the same rule E4 runs, so EF-9 is
compared to the stump family on the decision rule rather than on a different one.

FAVOURITE NULL: at the SAME fired passes, buy the cheaper side instead of the model's. London closed its
own architecture as a favourite-buyer that dies at +1c, so if EF-9's money is the favourite's money the
null says so at the same passes rather than on a different sample.
"""
import sys, os, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1, cost
from ef3 import platt, pad_cost, STAKE, MIN_CELL
from ef9 import CACHE, STEP_MS

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


def score(fires, nd, hc=0.0):
    fl = [f for f in fires if f['q'] == f['q']]
    if not fl: return None
    qs = [min(f['q'] + hc, 0.99) for f in fl]
    seq = [STAKE * per1(f['win'], b) for f, b in zip(fl, qs)]
    tot, mdd, worst = dd_run(seq)
    byd = collections.defaultdict(float)
    for f, x in zip(fl, seq): byd[f['day']] += x
    return dict(tot=tot, mdd=mdd, n=len(fires), nf=len(fl), fill=len(fl) / len(fires),
                fpd=len(fires) / max(nd, 1), win=float(np.mean([f['win'] for f in fl])),
                ask=float(np.mean([f['ask'] for f in fl])), run=worst, byd=dict(byd),
                pos=sum(1 for v in byd.values() if v > 0), days=len(byd))


if __name__ == '__main__':
    D = np.load(CACHE, allow_pickle=True)
    y, q, ep, ts, up, ps, day = (D[k] for k in ('y', 'q', 'ep', 'ts', 'up', 'ps', 'day'))
    pred = np.load('/home/ubuntu/pm_ef3/ef9_pred.npy')
    ok = np.isfinite(pred)
    days = sorted(set(day[ok].tolist())); nd = len(days)
    ask_by = {}
    for i in np.where(ok)[0]: ask_by[(int(ts[i]), int(up[i]))] = None
    # own ask per row is not stored separately; recover it from the sequence's last own_ask step
    S = D['S']
    own = S[:, 0, -1].astype(float)
    print(f'EF-9 INSUF - decision on the SAME rule as E4 (strict q.90 trailing 1 h, anchors 0/15/30/45)')
    print(f'  test days {days}')

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
                out.append(dict(i=i, day=d, q=float(q[i]), win=float(y[i]), ask=own[i], ts=int(ts[i]),
                                up=int(up[i])))
        return out

    rows = []
    for a in ANCHORS:
        f = fire(a); s = score(f, nd)
        if not s: print(f'  anchor {a:2d}s: no fills'); continue
        s1 = score(f, nd, 0.01); s2 = score(f, nd, 0.02)
        # favourite null: same passes, buy the cheaper side instead
        fav = []
        for x in f:
            i = x['i']
            same = (own[i] <= 1.0 - own[i])
            fav.append(dict(q=x['q'] if same else np.nan, win=x['win'] if same else 1.0 - x['win'],
                            day=x['day'], ask=own[i] if same else 1.0 - own[i]))
        fv = score([z for z in fav if z['q'] == z['q']] or fav, nd)
        rows.append((a, s, s1, s2, fv))
        print(f'  anchor {a:2d}s  $ {s["tot"]:+8.1f}  DD {s["mdd"]:6.1f}  {s["fpd"]:6.1f}/day  '
              f'fill {100*s["fill"]:5.1f}%  win {100*s["win"]:5.1f}%  ask {s["ask"]:.3f}  '
              f'+1c {s1["tot"]:+7.1f}  +2c {s2["tot"]:+7.1f}  days+ {s["pos"]}/{s["days"]}')
        print(f'            per day $ ' + '  '.join(f'{d} {s["byd"].get(d,0.0):+7.1f}' for d in days))
    if rows:
        tots = [r[1]['tot'] for r in rows]
        print(f'\n  MEAN over anchors $ {np.mean(tots):+.1f}  [min {min(tots):+.1f}, max {max(tots):+.1f}]  '
              f'mean DD {np.mean([r[1]["mdd"] for r in rows]):.1f}')
        print(f'  FAVOURITE NULL at the same passes, mean $ {np.mean([r[4]["tot"] for r in rows]):+.1f}')
    # fixed15 control on the same passes/days
    C = []
    for d in days:
        m = np.where((day == d) & ok)[0]
        o = m[np.argsort(ts[m], kind='stable')]
        seen = set()
        for i in o:
            if ps[i] < 0.5: continue
            if (platt(float(ps[i])) / pad_cost(float(own[i])) - 1) < 0.15: continue
            e = int(ep[i])
            if e in seen: continue
            seen.add(e)
            C.append(dict(q=float(q[i]), win=float(y[i]), ask=own[i], day=d))
    cs = score(C, nd)
    if cs: print(f'  fixed15 control      $ {cs["tot"]:+8.1f}  DD {cs["mdd"]:6.1f}  {cs["fpd"]:6.1f}/day  '
                 f'fill {100*cs["fill"]:5.1f}%  win {100*cs["win"]:5.1f}%  ask {cs["ask"]:.3f}')
