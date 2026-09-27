#!/usr/bin/env python3
"""Does BTC's move predict the ETH/SOL 5-minute outcome BEYOND the coin's own move? READ-ONLY, offline.

Owner's premise (09-27, via V): "BTC's moves should help the other coins". This tests it on 30 days of
Binance 1 s closes (data.binance.vision daily zips, BTC/ETH/SOL, 08-28 -> 09-26, 2,592,000 seconds with
all three present on 100% of them - no gap filling, nothing interpolated).

Settlement copied from the venue, not invented: these markets are `<asset>-usd-twap-60s`, so the line is
the TWAP of the 60 one-second closes BEFORE the candle opens, and the outcome is UP iff the close at
sec 299 is >= that line. Same rule for every coin, including BTC.

At second s of the candle, both moves are observed at the SAME instant, so nothing here is lookahead:
    own_bps = 1e4 * (px_coin(epoch+s)/line_coin - 1)
    btc_bps = 1e4 * (px_btc(epoch+s)/line_btc  - 1)

Walk-forward by DAY: fit on all strictly-prior days, score the day itself. Model A = own move only;
model B = own + BTC move. The statistic is the AUC gain B-A on the scored days, per second bucket, and
the whole grid is printed - no bucket is selected.
"""
import sqlite3, numpy as np, datetime as dt

DB = '/tmp/ll/klines30.sqlite3'
SECS = list(range(15, 241, 15))
COINS = ('eth', 'sol', 'btc')

def load():
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    n, lo, hi = c.execute('SELECT count(*),min(ts),max(ts) FROM k').fetchone()
    assert hi - lo + 1 == n, f'ts not contiguous: {n} rows over {hi-lo+1} seconds'
    px = {k: np.full(n, np.nan) for k in COINS}
    for ts, b, e, s in c.execute('SELECT ts,btc,eth,sol FROM k ORDER BY ts'):
        i = ts - lo
        px['btc'][i] = b if b is not None else np.nan
        px['eth'][i] = e if e is not None else np.nan
        px['sol'][i] = s if s is not None else np.nan
    return px, lo, n

def build(px, lo, n):
    ep0 = ((lo + 60) + 299) // 300 * 300
    eps = np.array([e for e in range(ep0, lo + n - 300, 300) if e - 60 >= lo and e + 299 < lo + n])
    idx = eps - lo
    out = {}
    for k in COINS:
        a = px[k]
        line = np.array([a[i - 60:i].mean() for i in idx])
        close = a[idx + 299]
        # SETTLEMENT RULE (owner, 09-27 03:3x): the venue settles CLOSING TWAP60 vs OPENING TWAP60, not
        # the live close. This line previously used the single sec-299 close as the label, which is not
        # what the market pays on.
        fin = np.array([a[i + 240:i + 300].mean() for i in idx])
        out[k] = dict(line=line, close=close, fin=fin, win=(fin >= line).astype(float),
                      mv={s: 1e4 * (a[idx + s] / line - 1) for s in SECS})
    return eps, out

def fit(X, y, l2=1.0, it=60):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y); R = np.eye(len(w)) * l2; R[0, 0] = 0
        H = X.T @ (X * (p * (1 - p))[:, None]) + R + np.eye(len(w)) * 1e-9
        st = np.linalg.solve(H, g + R @ w); w -= st
        if np.max(np.abs(st)) < 1e-9: break
    return w
score = lambda w, X: 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))

def auc(y, s):
    y = np.asarray(y, float); s = np.asarray(s, float)
    if y.min() == y.max(): return np.nan
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def walk(days, y, XA, XB):
    """Fit on all strictly-prior days, score the day. Returns (pA, pB, mask of scored rows)."""
    u = np.unique(days); pA = np.full(len(y), np.nan); pB = np.full(len(y), np.nan)
    for d in u[1:]:
        tr = days < d; te = days == d
        if tr.sum() < 200 or te.sum() == 0: continue
        pA[te] = score(fit(XA[tr], y[tr]), XA[te])
        pB[te] = score(fit(XB[tr], y[tr]), XB[te])
    return pA, pB, ~np.isnan(pA)

if __name__ == '__main__':
    px, lo, n = load()
    eps, D = build(px, lo, n)
    days = eps // 86400
    f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
    print(f'30-day 1 s history: {n} seconds, {f(lo)} -> {f(lo+n-1)} UTC, all three coins present on 100%')
    print(f'candles built: {len(eps)}, {len(np.unique(days))} day buckets, '
          f'{f(eps[0])} -> {f(eps[-1])}')
    for k in COINS:
        print(f'  {k.upper()}: UP rate {100*D[k]["win"].mean():.1f}%  |move@240s| p50 '
              f'{np.nanmedian(np.abs(D[k]["mv"][240])):.1f} bps')
    print(f'\ncorrelation of the moves with BTC (Pearson on bps, sec 240): ' +
          '  '.join(f'{k}-btc {np.corrcoef(D[k]["mv"][240], D["btc"]["mv"][240])[0,1]:+.3f}' for k in ('eth', 'sol')))

    print(f'\n{"="*104}\nAUC on the walk-forward days, per second bucket. A = own move only, '
          f'B = own + BTC move. Full grid, nothing selected.\n{"="*104}')
    for coin in ('eth', 'sol'):
        y = D[coin]['win']
        print(f'\n{coin.upper()}   {"sec":>5}{"n scored":>10}{"UP%":>7}{"AUC A":>9}{"AUC B":>9}{"gain":>9}'
              f'{"BTC coef":>10}{"|t|":>7}   verdict')
        for s in SECS:
            XA = D[coin]['mv'][s][:, None]
            XB = np.c_[D[coin]['mv'][s], D['btc']['mv'][s]]
            ok = np.isfinite(XB).all(1) & np.isfinite(y)
            pA, pB, m = walk(days[ok], y[ok], XA[ok], XB[ok])
            aA, aB = auc(y[ok][m], pA[m]), auc(y[ok][m], pB[m])
            # in-sample coefficient and its Wald |t| on the full period, for direction and scale only
            w = fit(XB[ok], y[ok]); p = score(w, XB[ok])
            Xd = np.c_[np.ones(ok.sum()), XB[ok]]
            cov = np.linalg.inv(Xd.T @ (Xd * (p * (1 - p))[:, None]) + np.eye(3) * 1e-9)
            t = abs(w[2]) / max(np.sqrt(cov[2, 2]), 1e-12)
            mark = ('helps' if aB - aA > 0.005 else 'hurts' if aB - aA < -0.005 else 'no change')
            print(f'      {s:>5}{m.sum():>10}{100*y[ok][m].mean():>7.1f}{aA:>9.3f}{aB:>9.3f}'
                  f'{aB-aA:>+9.3f}{w[2]:>+10.4f}{t:>7.1f}   {mark}')
