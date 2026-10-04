#!/usr/bin/env python3
"""Does the RUNNING BTC model's probability help ETH/SOL? READ-ONLY. Owner's hypothesis, item 2.

Phase 1(b) already answered the weaker version - BTC's raw *move* adds 0.000 AUC to a coin's own move on
30 days. This tests the version the owner actually specified: `p_btc`, the live BTC EF model's
probability, as a shared input to each coin's own model.

`p_btc` is taken from the real artifact, not reconstructed: `decide_log` rows written by the running
engine (via the archive at /home/ubuntu/pm_archive). Each row's `p` is P(the model's chosen side), so the
directional feature is `p_up_btc = p if side=='UP' else 1-p`. Joined PAST-ONLY - the latest row at or
before epoch+s - and the join age is reported, not assumed.

Cost of using the real thing: `decide_log` only starts 09-24 12:30, so this test gets ~2.5 days and
3 day buckets against Phase 1(b)'s 30 days and 8,351 scored candles per cell. That is the trade and it
is stated per cell rather than buried.

Label and line are the venue's: `<asset>-usd-twap-60s`, line = TWAP of the 60 one-second closes before
the candle opens, UP iff the sec-299 close >= line.
"""
import sqlite3, numpy as np, datetime as dt, bisect

KL = '/tmp/ll/klines30.sqlite3'
ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
SECS = list(range(15, 241, 15))

def load_klines():
    c = sqlite3.connect(f'file:{KL}?mode=ro', uri=True)
    n, lo, hi = c.execute('SELECT count(*),min(ts),max(ts) FROM k').fetchone()
    assert hi - lo + 1 == n
    px = {k: np.full(n, np.nan) for k in ('btc', 'eth', 'sol')}
    for ts, b, e, s in c.execute('SELECT ts,btc,eth,sol FROM k ORDER BY ts'):
        i = ts - lo
        px['btc'][i], px['eth'][i], px['sol'][i] = b, e, s
    return px, lo, n

def load_pbtc():
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    rows = [(int(t // 1000), (p if sd == 'UP' else 1.0 - p))
            for t, sd, p in c.execute('SELECT ts_ms,side,p FROM decide_log '
                                      'WHERE p IS NOT NULL AND side IS NOT NULL ORDER BY ts_ms')]
    last = {}
    for s, v in rows: last[s] = v          # last row within a second
    ts = sorted(last)
    return ts, np.array([last[t] for t in ts]), rows[0][0], rows[-1][0]

def fit(X, y, l2=1.0, it=80):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y); R = np.eye(len(w)) * l2; R[0, 0] = 0
        H = X.T @ (X * (p * (1 - p))[:, None]) + R + np.eye(len(w)) * 1e-9
        st = np.linalg.solve(H, g + R @ w); w -= st
        if np.max(np.abs(st)) < 1e-9: break
    return w
sc = lambda w, X: 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))

def auc(y, s):
    y = np.asarray(y, float); s = np.asarray(s, float)
    if y.min() == y.max(): return np.nan
    r = np.argsort(np.argsort(s)) + 1.0; n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))

def walk(days, y, Xs):
    u = np.unique(days); out = [np.full(len(y), np.nan) for _ in Xs]
    for d in u[1:]:
        tr, te = days < d, days == d
        if tr.sum() < 100 or te.sum() == 0: continue
        for k, X in enumerate(Xs): out[k][te] = sc(fit(X[tr], y[tr]), X[te])
    return out, ~np.isnan(out[0])

if __name__ == '__main__':
    px, lo, n = load_klines()
    pts, pvals, p_lo, p_hi = load_pbtc()
    f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
    print(f'p_btc from the running engine: {len(pts)} distinct seconds, {f(p_lo)} -> {f(p_hi)}')
    print(f'1 s klines: {f(lo)} -> {f(lo+n-1)}')
    ep0 = max(p_lo, lo + 60) // 300 * 300 + 300
    eps = np.array([e for e in range(ep0, min(p_hi, lo + n - 300), 300) if e - 60 >= lo and e + 299 < lo + n])
    print(f'OVERLAP: {len(eps)} candles, {f(eps[0])} -> {f(eps[-1])}, '
          f'{len(np.unique(eps//86400))} day buckets -> {len(np.unique(eps//86400))-1} test days')
    idx = eps - lo
    D = {}
    for k in ('btc', 'eth', 'sol'):
        a = px[k]; line = np.array([a[i-60:i].mean() for i in idx])
        # SETTLEMENT RULE: closing TWAP60 vs opening TWAP60, not the sec-299 close.
        fin = np.array([a[i+240:i+300].mean() for i in idx])
        D[k] = dict(win=(fin >= line).astype(float), fin=fin,
                    mv={s: 1e4*(a[idx+s]/line - 1) for s in SECS})
    ages = []
    pb = {}
    for s in SECS:
        v = np.full(len(eps), np.nan); ag = []
        for j, e in enumerate(eps):
            t = e + s; i = bisect.bisect_right(pts, t) - 1
            if i < 0: continue
            if t - pts[i] > 5: continue
            v[j] = pvals[i]; ag.append(t - pts[i])
        pb[s] = v; ages += ag
    print(f'p_btc past-only join age: p50 {int(np.median(ages))}s p95 {int(np.percentile(ages,95))}s '
          f'max {max(ages)}s (rows dropped if older than 5 s)')
    days = eps // 86400
    print(f'\n{"="*112}\nAUC, walk-forward by day. A = own move. B = own + p_btc. C = own + p_btc + BTC move.')
    print(f'{"="*112}')
    for coin in ('eth', 'sol'):
        y = D[coin]['win']
        print(f'\n{coin.upper()}  {"sec":>5}{"n":>7}{"UP%":>7}{"AUC A":>8}{"AUC B":>8}{"B-A":>8}'
              f'{"AUC C":>8}{"C-A":>8}{"p_btc coef":>12}{"|t|":>6}  verdict')
        for s in SECS:
            XA = D[coin]['mv'][s][:, None]
            XB = np.c_[D[coin]['mv'][s], pb[s]]
            XC = np.c_[D[coin]['mv'][s], pb[s], D['btc']['mv'][s]]
            ok = np.isfinite(XC).all(1) & np.isfinite(y)
            (pA, pB, pC), m = walk(days[ok], y[ok], [XA[ok], XB[ok], XC[ok]])
            aA, aB, aC = (auc(y[ok][m], z[m]) for z in (pA, pB, pC))
            w = fit(XB[ok], y[ok]); p = sc(w, XB[ok])
            Xd = np.c_[np.ones(ok.sum()), XB[ok]]
            cov = np.linalg.inv(Xd.T @ (Xd * (p*(1-p))[:, None]) + np.eye(3)*1e-9)
            t = abs(w[2]) / max(np.sqrt(cov[2, 2]), 1e-12)
            mark = ('helps' if aB-aA > 0.01 else 'hurts' if aB-aA < -0.01 else 'no change')
            flag = '' if m.sum() >= 60 else '  INSUFFICIENT'
            print(f'     {s:>5}{m.sum():>7}{100*y[ok][m].mean():>7.1f}{aA:>8.3f}{aB:>8.3f}{aB-aA:>+8.3f}'
                  f'{aC:>8.3f}{aC-aA:>+8.3f}{w[2]:>+12.3f}{t:>6.1f}  {mark}{flag}')
