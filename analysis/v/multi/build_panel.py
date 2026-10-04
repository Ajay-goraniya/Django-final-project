#!/usr/bin/env python3
"""Per-candle x per-second panel for one coin (V/multi, 09-27). All inputs past-only at the decision second.

usage: build_panel.py POLY_DB K1S_DB COIN OUT.npz        (COIN in eth/sol/btc; BTC is always loaded as the leader)

Decision at second s of candle ep = instant ep+s. Information allowed: Binance 1 s klines with open time <= ep+s-1
(their close is the price at ep+s) and Polymarket trades with timestamp <= ep+s-1 (1 s stamps -> strictly earlier).
- line   = mean Binance close over klines [ep-60, ep-1]   (TWAP60 of the minute before the open, NC-1)
- z      = ln(P/line) / (sig1s*sqrt(300))                  sig1s = std of 1 s log returns over the prior 900 s
- zt     = ln(P/line) / (sig1s*sqrt(max(240-s,0)+20))      time-scaled (TWAP of the last 60 s has var ~ 20 s)
- r10    = ln(P_s/P_{s-10}) / (sig1s*sqrt(10))
- ask proxy per side (UP shown): taker BUY of UP at p -> UP ask p; taker SELL of DOWN at q -> DOWN bid q = UP ask 1-q
  (Polymarket's books are mirrors). Per second the mean of that second's prints.
  past ask at s = last print second <= ep+s-1 (age = seconds before the decision, >=1)
  exec price at s = first print second in [ep+s, ep+s+4] (AT-OR-AFTER the decision; NaN if none) -> what we pay
- outcome = Polymarket's own resolution (gamma outcomePrices); post = side whose post-close (ts>=ep+300) prints are
  >=0.90 (an independent read of the same settlement); bnc = Binance TWAP60 proxy (information only)."""
import sys, sqlite3, numpy as np
PDB, KDB, COIN, OUT = sys.argv[1:5]
SYM = {'btc': 'BTCUSDT', 'eth': 'ETHUSDT', 'sol': 'SOLUSDT'}
pc = sqlite3.connect(PDB); kc = sqlite3.connect(KDB)

def series(sym):
    r = np.array(kc.execute('select ts, c from k where sym=? order by ts', (sym,)).fetchall())
    t0 = int(r[0, 0]); n = int(r[-1, 0]) - t0 + 1
    c = np.full(n, np.nan); c[(r[:, 0] - t0).astype(int)] = r[:, 1]
    idx = np.where(~np.isnan(c), np.arange(n), 0); np.maximum.accumulate(idx, out=idx); c = c[idx]   # ffill
    lr = np.zeros(n); lr[1:] = np.diff(np.log(c))
    cs = np.concatenate([[0], np.cumsum(lr)]); cs2 = np.concatenate([[0], np.cumsum(lr * lr)])
    return t0, c, cs, cs2

def feats(ser, ep):
    t0, c, cs, cs2 = ser; S = np.arange(300)
    i_open = ep - t0
    line = c[i_open - 60:i_open].mean()
    fin = c[i_open + 240:i_open + 300].mean()
    ip = i_open + S - 1                                  # kline open ep+s-1 -> price at ep+s
    P = c[ip]
    a, b = ip - 899, ip + 1                              # 900 returns ending at ip
    m = (cs[b] - cs[a]) / 900; v = (cs2[b] - cs2[a]) / 900 - m * m
    sig = np.sqrt(np.maximum(v, 1e-12))
    mv = np.log(P / line)
    z = mv / (sig * np.sqrt(300)); zt = mv / (sig * np.sqrt(np.maximum(240 - S, 0) + 20))
    r10 = np.log(P / c[np.maximum(ip - 10, 0)]) / (sig * np.sqrt(10))
    return z, zt, r10, int(fin >= line)

def quotes(ep, rows):
    """rows: (ts, is_up, side, price). Returns past ask/age and exec price per side, arrays over s=0..299."""
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
        nxt = np.where(have, ar, 10**6); nxt = np.minimum.accumulate(nxt[::-1])[::-1]
        S = np.arange(300) + 60                           # index of ep+s
        li = last[S - 1]; age = (S - li).astype(float)
        past = np.where(li >= 0, sec[np.clip(li, 0, L - 1)], np.nan); age[li < 0] = np.nan
        ni = nxt[S]; ok = (ni < L) & (ni - S <= 4)
        ex = np.where(ok, sec[np.clip(ni, 0, L - 1)], np.nan)
        out[side_up] = (past, age, ex)
    return out

def post_label(ep, rows):
    up = [p for ts, iu, sd, p in rows if ts >= ep + 300 and iu == 1 and sd == 'BUY']
    dn = [p for ts, iu, sd, p in rows if ts >= ep + 300 and iu == 0 and sd == 'BUY']
    mu = np.median(up) if up else np.nan; md = np.median(dn) if dn else np.nan
    if mu >= 0.9: return 1
    if md >= 0.9: return 0
    return -1

def trade_rows(asset, ep):
    return pc.execute('select ts, is_up, side, price from tr where asset=? and epoch=?', (asset, ep)).fetchall()

own = series(SYM[COIN]); btc = series('BTCUSDT')
mk = pc.execute('select epoch, outcome from mkt where asset=? and outcome is not null and epoch in (select epoch from done where asset=?) order by epoch', (COIN, COIN)).fetchall()
btc_ok = {e for (e,) in pc.execute("select epoch from done where asset='btc'")}
lo = max(own[0], btc[0]) + 1000; hi = min(own[0] + len(own[1]), btc[0] + len(btc[1])) - 310
mk = [(e, o) for e, o in mk if lo <= e <= hi]
N = len(mk); print(COIN, 'candles', N, flush=True)
A = {k: np.full((N, 300), np.nan) for k in ('z', 'zt', 'r10', 'bz', 'bzt', 'br10', 'au', 'agu', 'eu', 'ad', 'agd', 'ed', 'bau', 'bad')}
ep_a = np.zeros(N, int); y = np.zeros(N, int); post = np.zeros(N, int); bnc = np.zeros(N, int); bbnc = np.zeros(N, int); ntr = np.zeros(N, int)
for i, (ep, oc) in enumerate(mk):
    ep_a[i] = ep; y[i] = 1 if oc == 'UP' else 0
    A['z'][i], A['zt'][i], A['r10'][i], bnc[i] = feats(own, ep)
    A['bz'][i], A['bzt'][i], A['br10'][i], bbnc[i] = feats(btc, ep)
    rows = trade_rows(COIN, ep); ntr[i] = len(rows)
    q = quotes(ep, rows)
    A['au'][i], A['agu'][i], A['eu'][i] = q[1]; A['ad'][i], A['agd'][i], A['ed'][i] = q[0]
    post[i] = post_label(ep, rows)
    if COIN != 'btc' and ep in btc_ok:
        qb = quotes(ep, trade_rows('btc', ep))
        bu, bgu, _ = qb[1]; bd, bgd, _ = qb[0]
        A['bau'][i] = np.where(bgu <= 30, bu, np.nan); A['bad'][i] = np.where(bgd <= 30, bd, np.nan)
    if i % 500 == 0: print(i, flush=True)
np.savez_compressed(OUT, ep=ep_a, y=y, post=post, bnc=bnc, bbnc=bbnc, ntr=ntr, **A)
print('saved', OUT, flush=True)
