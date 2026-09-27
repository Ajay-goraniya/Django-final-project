#!/usr/bin/env python3
"""Per-candle x per-second panel for ONE Polymarket up/down market of any candle length (V/multi/btc15, 09-27).
Adapted from ../build_panel.py (same past-only rules); the candle length CL is a parameter and there is no leader coin.

usage: build_panel15.py POLY_DB K1S_DB ASSET SYMBOL CL OUT.npz      e.g. btc BTCUSDT 900 (15m) or btc BTCUSDT 300 (5m)

Resolution (gamma event description, btc-updown-15m-1790477100, identical wording to the 5m): "Up if the TWAP of BTC/USD
(Chainlink btc-usd-twap-60s stream) of the time range ... >= the price at the beginning of that range". So both ends are
60 s TWAPs:  line = mean Binance 1 s close over [ep-60, ep-1];  settle proxy = mean over [ep+CL-60, ep+CL-1].
Decision at second s of candle ep = instant ep+s. Allowed: klines with open <= ep+s-1, prints with ts <= ep+s-1.
- z   = ln(P/line) / (sig1s*sqrt(CL));  zt = ln(P/line) / (sig1s*sqrt(max(CL-60-s,0)+20))  (time left to the TWAP window)
- sig1s = std of 1 s log returns over the prior 900 s
- ask proxy per side (UP shown): taker BUY of UP at p -> UP ask p; taker SELL of DOWN at q -> UP ask 1-q. Per-second mean.
  past ask at s = last print second <= ep+s-1; exec at s = first print second in [ep+s, ep+s+4] (at-or-after).
- secu/secd = the per-second ask-proxy series on [ep-60, ep+CL+120) (for priced-later / lead-lifetime tests).
- outcome = gamma outcomePrices (venue settlement); post = side whose post-close prints are >= 0.90; bnc = Binance TWAP proxy."""
import sys, sqlite3, numpy as np
PDB, KDB, ASSET, SYM, CL, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6]
pc = sqlite3.connect(PDB); kc = sqlite3.connect(KDB)
PAD = 120; LQ = 60 + CL + PAD

def series(sym):
    r = np.array(kc.execute('select ts, c from k where sym=? order by ts', (sym,)).fetchall())
    t0 = int(r[0, 0]); n = int(r[-1, 0]) - t0 + 1
    c = np.full(n, np.nan); c[(r[:, 0] - t0).astype(int)] = r[:, 1]
    idx = np.where(~np.isnan(c), np.arange(n), 0); np.maximum.accumulate(idx, out=idx); c = c[idx]
    lr = np.zeros(n); lr[1:] = np.diff(np.log(c))
    cs = np.concatenate([[0], np.cumsum(lr)]); cs2 = np.concatenate([[0], np.cumsum(lr * lr)])
    return t0, c, cs, cs2

def feats(ser, ep):
    t0, c, cs, cs2 = ser; S = np.arange(CL)
    i_open = ep - t0
    line = c[i_open - 60:i_open].mean(); fin = c[i_open + CL - 60:i_open + CL].mean()
    ip = i_open + S - 1; P = c[ip]
    a, b = ip - 899, ip + 1
    m = (cs[b] - cs[a]) / 900; v = (cs2[b] - cs2[a]) / 900 - m * m
    sig = np.sqrt(np.maximum(v, 1e-12)); mv = np.log(P / line)
    z = mv / (sig * np.sqrt(CL)); zt = mv / (sig * np.sqrt(np.maximum(CL - 60 - S, 0) + 20))
    return z, zt, int(fin >= line)

def quotes(ep, rows):
    base = ep - 60; out = {}
    for side_up in (1, 0):
        pr = [[] for _ in range(LQ)]
        for ts, iu, sd, p, sz in rows:
            k = ts - base
            if not (0 <= k < LQ): continue
            if iu == side_up and sd == 'BUY': pr[k].append(p)
            elif iu != side_up and sd == 'SELL': pr[k].append(1 - p)
        sec = np.array([np.mean(x) if x else np.nan for x in pr])
        have = ~np.isnan(sec); ar = np.arange(LQ)
        last = np.where(have, ar, -10**6); np.maximum.accumulate(last, out=last)
        nxt = np.where(have, ar, 10**6); nxt = np.minimum.accumulate(nxt[::-1])[::-1]
        S = np.arange(CL) + 60
        li = last[S - 1]; age = (S - li).astype(float)
        past = np.where(li >= 0, sec[np.clip(li, 0, LQ - 1)], np.nan); age[li < 0] = np.nan
        ni = nxt[S]; ok = (ni < LQ) & (ni - S <= 4)
        ex = np.where(ok, sec[np.clip(ni, 0, LQ - 1)], np.nan)
        out[side_up] = (past, age, ex, sec)
    return out

def post_label(ep, rows):
    up = [p for ts, iu, sd, p, sz in rows if ts >= ep + CL and iu == 1 and sd == 'BUY']
    dn = [p for ts, iu, sd, p, sz in rows if ts >= ep + CL and iu == 0 and sd == 'BUY']
    mu = np.median(up) if up else np.nan; md = np.median(dn) if dn else np.nan
    if mu >= 0.9: return 1
    if md >= 0.9: return 0
    return -1

own = series(SYM)
mk = pc.execute('select m.epoch, m.outcome, d.n from mkt m join done d on d.asset=m.asset and d.epoch=m.epoch '
                'where m.asset=? and m.outcome is not null order by m.epoch', (ASSET,)).fetchall()
lo = own[0] + 1000; hi = own[0] + len(own[1]) - CL - 10
mk = [r for r in mk if lo <= r[0] <= hi]
N = len(mk); print(ASSET, CL, 'candles', N, flush=True)
A = {k: np.full((N, CL), np.nan) for k in ('z', 'zt', 'au', 'agu', 'eu', 'ad', 'agd', 'ed')}
SU = np.full((N, LQ), np.nan); SD = np.full((N, LQ), np.nan)
ep_a = np.zeros(N, int); y = np.zeros(N, int); post = np.zeros(N, int); bnc = np.zeros(N, int); ntr = np.zeros(N, int)
capped = np.zeros(N, int); usd_med = np.zeros(N); usd_p90 = np.zeros(N); usd_sec = np.zeros(N)
for i, (ep, oc, nd) in enumerate(mk):
    ep_a[i] = ep; y[i] = 1 if oc == 'UP' else 0; capped[i] = int(nd >= 10000)
    A['z'][i], A['zt'][i], bnc[i] = feats(own, ep)
    rows = pc.execute('select ts, is_up, side, price, size from tr where asset=? and epoch=?', (ASSET, ep)).fetchall(); ntr[i] = len(rows)
    q = quotes(ep, rows)
    A['au'][i], A['agu'][i], A['eu'][i], SU[i] = q[1]; A['ad'][i], A['agd'][i], A['ed'][i], SD[i] = q[0]
    post[i] = post_label(ep, rows)
    # print size at the ask (taker BUY prints inside the candle, $ notional): a lower bound on depth at best
    buys = [(ts, p * sz) for ts, iu, sd, p, sz in rows if sd == 'BUY' and ep <= ts < ep + CL]
    if buys:
        u = np.array([b for _, b in buys]); usd_med[i] = np.median(u); usd_p90[i] = np.percentile(u, 90)
        per = {}
        for ts, b in buys: per[ts] = per.get(ts, 0) + b
        usd_sec[i] = np.median(list(per.values()))
    if i % 200 == 0: print(i, flush=True)
np.savez_compressed(OUT, ep=ep_a, y=y, post=post, bnc=bnc, ntr=ntr, capped=capped, CL=CL, secu=SU, secd=SD,
                    usd_med=usd_med, usd_p90=usd_p90, usd_sec=usd_sec, **A)
print('saved', OUT, flush=True)
