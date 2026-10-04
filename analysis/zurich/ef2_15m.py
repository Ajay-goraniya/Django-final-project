#!/usr/bin/env python3
"""Is the PRICE as good on the SLOWER market? BTC 15m vs BTC 5m. READ-ONLY, master OFF.

Owner 09-28: early fires are guessing; v0b dropped. V: the one question left is whether the venue's price is
as hard to beat on a 15-minute candle as it is on a 5-minute one.

THREE CORRECTIONS TO THE BRIEF, up front, because two of them change what can be delivered.
  1. btc15 books do NOT go back to 09-22. The recorder holds 09-27 03:37 -> now, 32.4 h, 131 markets and
     125 gamma-resolved candles. Everything below is on those 125.
  2. There is no eth15 or sol15. recorder.py records eth and sol on the 5m grid and only BTC on the 15m
     grid, so the ETH/SOL 15m comparison V asked for has no data behind it.
  3. (c), "the same 52-feature logistic walk-forward", is not viable here and I am not going to fake it.
     125 independent outcomes cannot support 52 features; and the engine's 44 features are computed against
     the 5m line and the 5m book, so transplanting them to a 15m decision would need several of them zeroed -
     the exact level-shift failure that broke the London 35-key run an hour ago. What is delivered instead is
     (b): the same FAMILY of spot features, rebuilt honestly against the 15m line with sec_left scaled to
     900, and fitted ON the 15m data, so nothing is transplanted and nothing is imputed.

(a) is the real question and it is clean: AUC of the 15m own-side ask alone at each S, beside the identical
measurement on 5m at the matching FRACTION of the candle, so "slower" is compared like with like.
"""
import sys, sqlite3, math, collections, datetime as dt, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import auc, per1, cost, halves, MIN_CELL

MULTI = '/home/ubuntu/pm_multi/multi_market.sqlite3'
ROWS5 = '/home/ubuntu/pm_ef2/ef2_rows.npz'
SS = (30, 60, 120, 180, 300, 450, 600)
STEP = 900
TICK = 0.01


def load15():
    c = sqlite3.connect(f'file:{MULTI}?mode=ro', uri=True)
    res = {int(e): o for e, o in c.execute(
        "SELECT epoch,outcome FROM resolutions WHERE market='btc15' AND outcome IS NOT NULL")}
    bk = collections.defaultdict(dict)
    for ts, ep, ua, uz, da, dz, ag, agd in c.execute(
            "SELECT ts,epoch,up_ask,up_ask_sz,dn_ask,dn_ask_sz,up_snap_age_s,dn_snap_age_s "
            "FROM books WHERE market='btc15'"):
        bk[int(ep)][int(ts)] = (ua, da, ag, agd)
    k = {int(t): (o, h, l, cl, v, tb) for t, o, h, l, cl, v, tb in c.execute(
        "SELECT ts,o,h,l,cl,v,tb FROM k1s WHERE sym='btc'")}
    return res, bk, k


def line15(k, ep):
    v = [k[ep - i][3] for i in range(1, 61) if (ep - i) in k]
    return (sum(v) / len(v)) if len(v) >= 45 else None


if __name__ == '__main__':
    res, bk, k = load15()
    eps = sorted(e for e in bk if e in res)
    f = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%m-%d %H:%M')
    print(f'btc15: {len(bk)} candles with books, {len(eps)} of them gamma-resolved, '
          f'{f(eps[0])} -> {f(eps[-1])} = {(eps[-1]-eps[0])/3600:.1f} h')
    print(f'  Binance 1 s klines for btc: {len(k):,} seconds')
    print('  eth15 / sol15: NOT RECORDED - recorder.py has eth and sol on the 5m grid only.\n')

    # ---------- (a) the ask alone, 15m ----------
    print(f'{"="*118}\n(a) AUC OF THE 15m OWN-SIDE ASK ALONE, and what the 5m ask scores at the same '
          f'FRACTION of its candle\n{"="*118}')
    print(f'  {"S":>5}{"frac":>7}{"n":>6}{"AUC ask 15m":>13}{"| 5m sec":>10}{"AUC ask 5m":>12}'
          f'{"delta":>9}{"ask p50":>9}{"stale%":>8}')
    z5 = np.load(ROWS5, allow_pickle=True)
    n5 = [str(s) for s in z5['names']]
    fin5 = np.all(np.isfinite(z5['X']), axis=1)
    X5, y5, sec5 = z5['X'][fin5], z5['y'][fin5].astype(float), z5['sec'][fin5]
    ia5 = n5.index('own_ask')
    rows15 = {}
    for S in SS:
        yy, aa, stale = [], [], 0
        for ep in eps:
            t = ep + S
            b = bk[ep].get(t)
            if b is None: continue
            ua, da, ag, agd = b
            for side, a, age in (('UP', ua, ag), ('DOWN', da, agd)):
                if a is None or not (0.01 < a < 0.99): continue
                if age is not None and age > 15: stale += 1; continue
                yy.append(1.0 if res[ep] == side else 0.0); aa.append(float(a))
        rows15[S] = (np.array(yy), np.array(aa))
        if len(yy) < 30: print(f'  {S:>5}   too few'); continue
        frac = S / STEP
        s5 = int(round(frac * 300))
        m5 = (sec5 >= s5 - 2) & (sec5 <= s5 + 2)
        a5 = auc(y5[m5], -X5[m5, ia5]) if m5.sum() > 100 else float('nan')
        a15 = auc(np.array(yy), -np.array(aa))
        print(f'  {S:>5}{frac:>7.2f}{len(yy):>6}{1-a15:>13.4f}{s5:>10}{1-a5:>12.4f}'
              f'{(1-a15)-(1-a5):>+9.4f}{np.median(aa):>9.3f}{100*stale/max(len(yy)+stale,1):>7.1f}%')
    print('  AUC is reported for the ASK as a predictor (higher ask -> more likely to win), i.e. 1 - AUC(-ask).')
    print('  "stale%" is the share of side-seconds dropped for a book snapshot older than 15 s.')

    # ---------- (b) a spot model fitted ON the 15m data ----------
    print(f'\n{"="*118}\n(b) CAN A SPOT MODEL BEAT THAT PRICE? same feature family, 15m line, sec_left '
          f'scaled to 900, fitted on 15m\n{"="*118}')
    print('  Nothing transplanted and nothing imputed: the v10 json is fitted to the 5m line and to 5m book')
    print('  depth, and carrying it over would need imb5/imb20/spread/micro zeroed - the level shift that')
    print('  broke the London 35-key run. So the same FAMILY of spot features is rebuilt and refitted here.')
    from ef2_model import fit_logistic, predict
    FE = ['move_bps', 'ret5', 'ret15', 'ret30', 'ret60', 'rv60', 'range_bps', 'pos_in_range',
          'dist_hi_bps', 'dist_lo_bps', 'spot_imb15', 'spot_imb60', 'sec_left', 'hod_sin', 'hod_cos',
          'mv_x_sec']

    def feats(ep, S):
        t = ep + S
        if t not in k: return None
        ln = line15(k, ep)
        if not ln: return None
        cl = k[t][3]
        seg = [k[ep + i][3] for i in range(0, S + 1) if (ep + i) in k]
        if len(seg) < max(10, S // 3): return None
        hi, lo = max(seg), min(seg)
        def ret(s):
            q = k.get(t - s)
            return (cl / q[3] - 1) * 1e4 if q and q[3] > 0 else 0.0
        def imb(s):
            w = [k[t - i] for i in range(0, s) if (t - i) in k]
            tot = sum(x[4] for x in w); tb = sum(x[5] for x in w)
            return (2 * tb - tot) / tot if tot > 0 else 0.0
        lr = [math.log(k[t - i][3] / k[t - i - 1][3]) for i in range(0, 60)
              if (t - i) in k and (t - i - 1) in k and k[t - i - 1][3] > 0]
        mv = (cl / ln - 1) * 1e4
        sl = (STEP - S) / 900.0
        hod = (t % 86400) / 86400 * 2 * math.pi
        return [mv, ret(5), ret(15), ret(30), ret(60),
                (np.std(lr) * 1e4 if len(lr) > 10 else 0.0),
                (hi - lo) / ln * 1e4, ((cl - lo) / (hi - lo) if hi > lo else 0.5),
                (hi - cl) / ln * 1e4, (cl - lo) / ln * 1e4, imb(15), imb(60), sl,
                math.sin(hod), math.cos(hod), mv * sl]

    print(f'  {"S":>5}{"n rows":>8}{"train":>7}{"test":>6}{"AUC model":>11}{"AUC ask":>10}{"delta":>9}'
          f'{"~SE":>8}{"|d|/SE":>8}{"5m delta":>10}')
    for S in SS:
        R, Y, A, D = [], [], [], []
        for ep in eps:
            b = bk[ep].get(ep + S)
            if b is None: continue
            v = feats(ep, S)
            if v is None or not all(np.isfinite(x) for x in v): continue
            ua, da, ag, agd = b
            for side, a, age in (('UP', ua, ag), ('DOWN', da, agd)):
                if a is None or not (0.01 < a < 0.99): continue
                if age is not None and age > 15: continue
                sgn = 1.0 if side == 'UP' else -1.0
                R.append([x * (sgn if i in (0, 1, 2, 3, 4, 10, 11, 15) else 1.0) for i, x in enumerate(v)])
                Y.append(1.0 if res[ep] == side else 0.0); A.append(float(a))
                D.append(dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d'))
        if len(Y) < 60: print(f'  {S:>5}{len(Y):>8}   too few'); continue
        R = np.array(R); Y = np.array(Y); A = np.array(A); D = np.array(D)
        days = sorted(set(D.tolist()))
        pw = np.full(len(Y), np.nan)
        for d in days[1:]:
            tr, te = D < d, D == d
            if tr.sum() < 40 or te.sum() == 0: continue
            mu, sd = R[tr].mean(0), R[tr].std(0); sd = np.where(sd < 1e-9, 1.0, sd)
            w = fit_logistic(((R[tr] - mu) / sd).astype(np.float32), Y[tr])
            pw[te] = predict(w, (R[te] - mu) / sd)
        sc = np.isfinite(pw)
        if sc.sum() < 40: print(f'  {S:>5}{len(Y):>8}   no scored rows'); continue
        am, ak = auc(Y[sc], pw[sc]), 1 - auc(Y[sc], -A[sc])
        # Hanley-McNeil style rough SE, so the deltas can be read against the noise instead of asserted
        # to be inside it: sqrt(A(1-A)/min(n_pos, n_neg)).
        n1 = float(Y[sc].sum()); n0 = float(sc.sum() - n1)
        se = math.sqrt(max(am * (1 - am), 1e-9) / max(min(n1, n0), 1.0))
        print(f'  {S:>5}{len(Y):>8}{int((~sc).sum()):>7}{int(sc.sum()):>6}{am:>11.4f}{ak:>10.4f}'
              f'{am-ak:>+9.4f}{se:>8.3f}{abs(am-ak)/se:>8.2f}{"+0.003":>10}')
    print('\n  "5m delta" is the reference from EF2.md: on the 5m market the full 52-feature model beat the')
    print('  ask by +0.003. A materially larger positive delta here would mean the slower market is softer.')
    print(f'  WALK-FORWARD IS ONE TRAINING DAY: btc15 covers 09-27 and 09-28 only. Everything in (b) is thin')
    print(f'  and none of it is offered as a finding.')
