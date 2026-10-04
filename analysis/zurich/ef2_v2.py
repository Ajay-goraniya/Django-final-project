#!/usr/bin/env python3
"""EF-2 v2: does MILLISECOND ask dynamics add anything? READ-ONLY, master OFF.

V's brief: "own-ask lifetime, count of ask changes in the last 1/5 s, depth at touch, ask reversion after
+250 ms - the record of being picked off; train on that span, test on the tape days."

WHY THIS IS NOT THE BRIEFED EXPERIMENT, and what it is instead. The probe covers 09-28 02:25-06:45 - 53 BTC
5m candles. The tape days have NO ms data at all, so a model trained on ms features cannot be scored there;
and 53 candles is not a training set for 57 features. Training on the span and testing on the tape days is
therefore not possible with this data, and pretending otherwise would produce a number with nothing behind it.

The answerable version of the same question, which is what this runs: FREEZE the v0 walk-forward model (whose
predictions on 09-28 are already out-of-sample, fitted on 09-24..09-27), and ask whether the ms features add
AUC ON TOP of it, by fitting only a small incremental logistic on [logit(p_base), ms features] with 5-fold
cross-validation BY CANDLE. That tests whether the record of being picked off is information the 250 ms
features have not already captured. It cannot tell us the answer generalises across days - the sample is one
morning - and every table says so.

MS FEATURES, per (candle, second, side), from the probe's own event stream:
  ms_life      ms since the best ask PRICE last changed
  ms_chg1      number of best-ask price changes in the last 1 s
  ms_chg5      ... in the last 5 s
  ms_depth     size resting at the touch
  ms_rev250    best ask 250 ms LATER minus best ask now, in cents - the reversion itself
"""
import sys, sqlite3, math, collections, json, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import ROWS, auc, fit_logistic, predict

PROBE = '/home/ubuntu/pm_probe2/arb_ms.sqlite3'
FITS = '/home/ubuntu/pm_ef2/ef2_fits.npz'
OUT = '/home/ubuntu/pm_ef2/ef2_v2_ms.npz'
SEC_LO, SEC_HI = 15, 240
MSF = ['ms_life', 'ms_chg1', 'ms_chg5', 'ms_depth', 'ms_rev250']
lg = lambda p: math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6)))


def build():
    p = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True)
    mk = {int(e): (u, d) for _m, e, u, d in p.execute(
        "SELECT market,epoch,token_up,token_dn FROM markets WHERE market='btc5'")}
    print(f'probe btc5 epochs {len(mk)}', flush=True)
    out = {}
    for ep, (tu, td) in sorted(mk.items()):
        for side, tok in (('UP', tu), ('DOWN', td)):
            rows = p.execute('SELECT rx_ns,ask,ask_sz FROM top WHERE token=? AND rx_ns BETWEEN ? AND ? '
                             'ORDER BY rx_ns', (tok, (ep - 5) * 10**9, (ep + 305) * 10**9)).fetchall()
            if len(rows) < 50: continue
            t = np.array([r[0] for r in rows], dtype=np.int64)
            a = np.array([r[1] if r[1] is not None else np.nan for r in rows], dtype=np.float64)
            szv = np.array([r[2] if r[2] is not None else np.nan for r in rows], dtype=np.float64)
            chg = np.r_[True, a[1:] != a[:-1]]           # events where the best ask PRICE moved
            ct = t[chg]
            for s in range(SEC_LO, SEC_HI + 1):
                now = (ep + s) * 10**9
                i = int(np.searchsorted(t, now, side='right')) - 1
                if i < 0 or not np.isfinite(a[i]): continue
                k = int(np.searchsorted(ct, now, side='right')) - 1
                life = (now - ct[k]) / 1e6 if k >= 0 else float('nan')
                c1 = int(np.searchsorted(ct, now, 'right') - np.searchsorted(ct, now - 10**9, 'left'))
                c5 = int(np.searchsorted(ct, now, 'right') - np.searchsorted(ct, now - 5 * 10**9, 'left'))
                j = int(np.searchsorted(t, now + 250 * 10**6, side='right')) - 1
                rev = (a[j] - a[i]) * 100 if j >= 0 and np.isfinite(a[j]) else float('nan')
                out[(ep, s, side)] = (life, c1, c5, szv[i], rev)
        print(f'  {ep} done, rows so far {len(out)}', flush=True)
    return out


if __name__ == '__main__':
    ms = build()
    z = np.load(ROWS, allow_pickle=True); f = np.load(FITS, allow_pickle=True)
    keep = f['keep']
    y = z['y'][keep].astype(float); ep = z['ep'][keep]; sec = z['sec'][keep]; isup = z['is_up'][keep]
    pw = f['pw']
    sc = np.isfinite(pw)
    idx, M = [], []
    for i in np.nonzero(sc)[0]:
        k = (int(ep[i]), int(sec[i]), 'UP' if isup[i] else 'DOWN')
        v = ms.get(k)
        if v is None or not all(np.isfinite(x) for x in v): continue
        idx.append(i); M.append(v)
    idx = np.array(idx); M = np.array(M, dtype=np.float64)
    print(f'\noverlap: {len(idx):,} scored rows carry ms features, on '
          f'{len(set(ep[idx].tolist()))} candles  *thin by construction - one morning*')
    if len(idx) < 500: print('too few to say anything'); sys.exit(0)
    yy = y[idx]; base = pw[idx]
    print(f'  base (v0 walk-forward, out-of-sample) AUC on these rows: {auc(yy, base):.4f}')
    for j, nm in enumerate(MSF):
        print(f'    {nm:10s} p10 {np.percentile(M[:,j],10):10.2f}  p50 {np.percentile(M[:,j],50):10.2f}  '
              f'p90 {np.percentile(M[:,j],90):10.2f}   AUC alone {auc(yy, M[:,j]):.4f}')
    Z = np.c_[[lg(p) for p in base], M]
    eps_ = ep[idx]; cand_ids = sorted(set(eps_.tolist()))
    fold = {e: i % 5 for i, e in enumerate(cand_ids)}
    fa = np.array([fold[e] for e in eps_.tolist()])
    pin, pout = np.full(len(yy), np.nan), np.full(len(yy), np.nan)
    for k in range(5):
        tr, te = fa != k, fa == k
        if tr.sum() < 200 or te.sum() == 0: continue
        mu, sd = Z[tr].mean(0), Z[tr].std(0); sd = np.where(sd < 1e-9, 1.0, sd)
        w = fit_logistic(((Z[tr] - mu) / sd).astype(np.float32), yy[tr])
        pout[te] = predict(w, (Z[te] - mu) / sd)
        w0 = fit_logistic(((Z[tr][:, :1] - mu[:1]) / sd[:1]).astype(np.float32), yy[tr])
        pin[te] = predict(w0, (Z[te][:, :1] - mu[:1]) / sd[:1])
    m = np.isfinite(pout) & np.isfinite(pin)
    print(f'\n  5-fold BY CANDLE, incremental fit on top of the frozen base:')
    print(f'    base only (recalibrated)      AUC {auc(yy[m], pin[m]):.4f}')
    print(f'    base + ms features            AUC {auc(yy[m], pout[m]):.4f}   '
          f'delta {auc(yy[m], pout[m]) - auc(yy[m], pin[m]):+.4f}')
    np.savez_compressed(OUT, idx=idx, M=M, names=np.array(MSF))
    print(f'  saved {OUT}')
