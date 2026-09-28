#!/usr/bin/env python3
"""Does the Binance FOOTPRINT add anything to the venue price? (V, 09-28). Walk-forward by day, venue labels, taker-paid prices.
Per S: AUC of (a) venue mid alone, (b) footprint alone, (c) venue logit + footprint + spot features. Then the trading arm on the
owner's objective columns: model (c) fires at the first S >= S0 where p_side / cost >= 1 + m. usage: fp_eval.py"""
import os, json, math
import numpy as np
import early_spot_signal as E
import late_rules as LR

HERE = os.path.dirname(os.path.abspath(__file__))
FP = ['absorb30', 'stack_up', 'stack_dn', 'poc_vs_px', 'poc_vs_line', 'acc_above', 'big_delta', 'cvd_div', 'd30', 'r30']
SP = ['move', 'ret5', 'ret30', 'ret60', 'rv60', 'mv_sec']


def main():
    rows = LR.load(); fp = json.load(open(os.path.join(HERE, 'footprint_rows.json')))
    days = sorted({r['day'] for r in rows})
    secs = [S for S in (120, 150, 180, 200, 220, 240)]
    P = {}
    print(f'candles {len(rows)}, footprint candles {len(fp)}')
    for S in secs:
        K = str(S); rs, Xf, Xs, mid = [], [], [], []
        for r in rows:
            q = r['s'].get(K); f = fp.get(str(r['e']), {}).get(K)
            if not q or not f or q['ask_up'] is None or q['ask_dn'] is None: continue
            m = min(0.98, max(0.02, (q['ask_up'] + 1 - q['ask_dn']) / 2))
            rs.append(r); Xf.append([f[k] for k in FP]); Xs.append([q['f'][k] for k in SP]); mid.append(m)
        if len(rs) < 300: print(f'S={S}: only {len(rs)} rows'); continue
        y = np.array([r['up'] for r in rs]).astype(int); d = np.array([r['day'] for r in rs])
        Xf, Xs, mid = np.array(Xf, float), np.array(Xs, float), np.array(mid)
        lv = np.log(mid / (1 - mid))[:, None]
        Xc = np.c_[lv, Xf, Xs]
        pf, pc = np.full(len(rs), np.nan), np.full(len(rs), np.nan)
        for k in days[1:]:
            tr, te = d < k, d == k
            if tr.sum() < 150 or te.sum() == 0: continue
            for X, out in ((Xf, pf), (Xc, pc)):
                mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
                f = E.fit_logit((X[tr] - mu) / sd, y[tr]); out[te] = f((X[te] - mu) / sd)
        ok = ~np.isnan(pc)
        print(f'S={S:3d} n {ok.sum():4d}  AUC venue mid {E.auc(mid[ok], y[ok]):.3f}  footprint alone {E.auc(pf[ok], y[ok]):.3f}  '
              f'mid+footprint+spot {E.auc(pc[ok], y[ok]):.3f}  | corr(footprint p, mid) {np.corrcoef(pf[ok], mid[ok])[0,1]:+.2f}')
        for r, v in zip(rs, pc):
            if not np.isnan(v): P[(r['e'], S)] = float(v)
    print('\n=== TRADE: mid+footprint+spot model, fire at first S >= S0 with p_side/cost >= 1+m, taker-paid price, $10 stake')
    print(f"  {'arm':34s} {'n':>5s} {'/day':>6s} {'win%':>6s} {'per$1':>7s} {'$ tot':>9s} {'maxDD$':>8s} {'P/DD':>6s} {'days+':>6s} {'run':>4s} {'H1':>7s} {'H2':>7s} {'ask':>5s}")
    nd = len(days) - 1
    for S0 in (120, 180, 200, 220):
        for m in (0.0, 0.02, 0.05, 0.10):
            fires = []
            for r in rows:
                for S in secs:
                    if S < S0 or (r['e'], S) not in P: continue
                    q = r['s'][str(S)]; p = P[(r['e'], S)]; up = p >= 0.5; ps = p if up else 1 - p
                    a = q['ask_up'] if up else q['ask_dn']
                    if a is None or not (0.02 < a < 0.98): continue
                    if ps / (a + LR.fee(a)) >= 1 + m:
                        pay = a if LR.MODE != 'fwd' else (q.get('fwd_up') if up else q.get('fwd_dn'))
                        if pay is not None: fires.append((r['e'], r['day'], pay, r['up'] == up))
                        break
            print(LR.line(f'S0 {S0:3d} m {m:.2f}', LR.stats(fires, nd)))


if __name__ == '__main__':
    main()
