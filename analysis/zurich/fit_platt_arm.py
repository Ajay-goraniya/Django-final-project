#!/usr/bin/env python3
"""Fit the Platt calibration for shadow arm 2 and print coefficients to freeze. READ-ONLY.

p = sigmoid(c0 + c1*logit(model p) + c2*logit(venue mid of that side))

Rows: one per (candle, second in the 5 s grid 15..240, SIDE). Two rows per candle-second, UP and DOWN, so
the calibration is fitted side-symmetrically rather than on whichever side a rule happened to pick.
  model p  = the frozen arm (iv) logistic on zt, from Binance 1 s closes
  mid      = (ask_up + 1 - ask_dn)/2, both ask proxies aged <= 30 s, exactly as analyze.py line 75 does;
             the DOWN side's mid is 1 - that
  label    = the VENUE'S OWN RESOLUTION for that side (mkt.outcome). V's brief said closing-TWAP60
             labels; the settlement rule says the market's resolution, and a computed TWAP60 direction
             only agrees with it 96.73% of the time, so the resolution is used and the deviation is stated.

The ask proxy here is the same taker-print series that made ETH_SOL_EF.md's paper number optimistic. That
is acceptable for FITTING - a slightly stale price still teaches the right relationship - and unacceptable
for trading, which is why the live arm reads the live book instead. Both a full-sample fit (the one that
gets frozen) and a walk-forward check are printed, so the fit is not shipped blind.
"""
import sqlite3, numpy as np, math, json, datetime as dt

POLY = '/tmp/poly/poly.sqlite3'
KL = '/tmp/ll/klines30.sqlite3'
FROZEN = {'eth': (-0.007173, 1.487533), 'sol': (-0.027489, 1.863596)}
SECS = list(range(15, 241, 5))
MAX_AGE = 30

lg = lambda p: math.log(min(max(p, 1e-3), 1 - 1e-3) / (1 - min(max(p, 1e-3), 1 - 1e-3)))

def fit(X, y, l2=1.0, it=300):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y); R = np.eye(len(w)) * l2; R[0, 0] = 0
        H = X.T @ (X * (p * (1 - p))[:, None]) + R + np.eye(len(w)) * 1e-9
        st = np.linalg.solve(H, g + R @ w); w -= st
        if np.max(np.abs(st)) < 1e-10: break
    return w
sc = lambda w, X: 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))
def auc(y, s):
    y = np.asarray(y, float); s = np.asarray(s, float)
    if y.min() == y.max(): return float('nan')
    r = np.argsort(np.argsort(s)) + 1.0; n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def klines(sym_col):
    c = sqlite3.connect(f'file:{KL}?mode=ro', uri=True)
    n, t0, t1 = c.execute('SELECT count(*),min(ts),max(ts) FROM k').fetchone()
    assert t1 - t0 + 1 == n
    a = np.full(n, np.nan)
    for ts, v in c.execute(f'SELECT ts,{sym_col} FROM k ORDER BY ts'): a[ts - t0] = v
    lr = np.zeros(n); lr[1:] = np.diff(np.log(a))
    return t0, a, np.concatenate([[0], np.cumsum(lr)]), np.concatenate([[0], np.cumsum(lr * lr)])

def ask_series(rows, ep):
    """V's quotes(): per-second mean taker-print ask per side over ep-60..ep+305, plus its age."""
    base = ep - 60; L = 366
    out = {}
    for side_up in (1, 0):
        pr = [[] for _ in range(L)]
        for ts, iu, sd, p in rows:
            k = ts - base
            if not (0 <= k < L): continue
            if iu == side_up and sd == 'BUY': pr[k].append(p)
            elif iu != side_up and sd == 'SELL': pr[k].append(1 - p)
        sec = np.array([np.mean(x) if x else np.nan for x in pr])
        have = ~np.isnan(sec); ar = np.arange(L)
        last = np.where(have, ar, -10**6); np.maximum.accumulate(last, out=last)
        S = np.arange(300) + 60
        li = last[S - 1]; age = (S - li).astype(float)
        past = np.where(li >= 0, sec[np.clip(li, 0, L - 1)], np.nan); age[li < 0] = np.nan
        out[side_up] = (past, age)
    return out

if __name__ == '__main__':
    pc = sqlite3.connect(f'file:{POLY}?mode=ro', uri=True)
    coeffs = {}
    for coin, col in (('eth', 'eth'), ('sol', 'sol')):
        t0, px, cs, cs2 = klines(col)
        b0, b1 = FROZEN[coin]
        mk = pc.execute('SELECT epoch,outcome FROM mkt WHERE asset=? AND outcome IS NOT NULL ORDER BY epoch',
                        (coin,)).fetchall()
        X, Y, DAY = [], [], []
        for ep, oc in mk:
            io = ep - t0
            if io - 960 < 0 or io + 300 >= len(px): continue
            line = px[io - 60:io].mean()
            if not (np.isfinite(line) and line > 0): continue
            rows = pc.execute('SELECT ts,is_up,side,price FROM tr WHERE asset=? AND epoch=?', (coin, ep)).fetchall()
            if not rows: continue
            q = ask_series(rows, ep)
            au, agu = q[1]; ad, agd = q[0]
            for s in SECS:
                if not (np.isfinite(au[s]) and np.isfinite(ad[s]) and agu[s] <= MAX_AGE and agd[s] <= MAX_AGE):
                    continue
                mid_up = (au[s] + (1 - ad[s])) / 2.0
                if not (0 < mid_up < 1): continue
                ip = io + s - 1
                a_, b_ = ip - 899, ip + 1
                m = (cs[b_] - cs[a_]) / 900; v = (cs2[b_] - cs2[a_]) / 900 - m * m
                sig = math.sqrt(max(v, 1e-12))
                zt = math.log(px[ip] / line) / (sig * math.sqrt(max(240 - s, 0) + 20))
                if not np.isfinite(zt): continue
                p_up = 1 / (1 + math.exp(-max(-30, min(30, b0 + b1 * zt))))
                for side_up, pm, mm in ((1, p_up, mid_up), (0, 1 - p_up, 1 - mid_up)):
                    X.append([lg(pm), lg(mm)])
                    Y.append(1.0 if (oc == 'UP') == (side_up == 1) else 0.0)
                    DAY.append(ep // 86400)
        X = np.array(X); Y = np.array(Y); DAY = np.array(DAY)
        w = fit(X, Y)
        days = np.unique(DAY)
        pw = np.full(len(Y), np.nan)
        for d in days[2:]:
            tr, te = DAY < d, DAY == d
            if tr.sum() < 500 or te.sum() == 0: continue
            pw[te] = sc(fit(X[tr], Y[tr]), X[te])
        ok = ~np.isnan(pw)
        print(f'\n{coin.upper()}: {len(Y)} rows ({len(Y)//2} candle-seconds x 2 sides), {len(days)} days, '
              f'base rate {Y.mean():.3f}')
        print(f'  FROZEN  p = sigmoid({w[0]:+.6f} {w[1]:+.6f}*logit(model p) {w[2]:+.6f}*logit(mid))')
        print(f'  in-sample AUC {auc(Y, sc(w, X)):.4f}   walk-forward AUC {auc(Y[ok], pw[ok]):.4f} (n {ok.sum()})')
        print(f'  walk-forward calibration: mean predicted {pw[ok].mean():.4f} vs actual {Y[ok].mean():.4f} '
              f'({100*(pw[ok].mean()-Y[ok].mean()):+.2f} pp)')
        print(f'  for reference, the venue mid alone: AUC {auc(Y, np.array([1/(1+math.exp(-x[1])) for x in X])):.4f}'
              f'   the model p alone: AUC {auc(Y, np.array([1/(1+math.exp(-x[0])) for x in X])):.4f}')
        coeffs[coin] = [float(w[0]), float(w[1]), float(w[2])]
    open('/tmp/platt_coeffs.json', 'w').write(json.dumps(coeffs, indent=1))
    print('\nwritten /tmp/platt_coeffs.json ->', json.dumps(coeffs))
