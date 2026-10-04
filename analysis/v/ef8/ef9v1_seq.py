#!/usr/bin/env python3
"""EF-9 v1 (V side, + Binance spot/perp 1 s price and SIGNED taker flow from aggTrades) - EF-9 (V side, independent days 09-11..16): a SEQUENCE model (GRU) on the raw 1 s stream, no hand features.
Input per decision second s: the last 30 s of [ask_up, ask_dn, bid_up, bid_dn, log size_up, log size_dn, log quote age,
line distance bps (Binance vs TWAP60 open), its 1 s change, sec/300]. Output: after-fill $ per $1 for UP and for DOWN (the EF-8
fill model: same-side ask 1 s later <= ask+1c, fee-exact, venue labels). Walk-forward by day (train < D, test D), test 09-13..16.
Rules fixed before the run (same as EF-8): E4 = strict q.90 of the trailing 1 h of predictions (60 s grid), E5 = strict q.90 of
yesterday's predictions; pin none|phys (TWAP z >= 0); first second, once per candle, $10. Nulls: favourite at the same second."""
import sys, math, bisect, datetime as dt, numpy as np, torch, torch.nn as nn
torch.manual_seed(0); np.random.seed(0); torch.set_num_threads(4)
S = sys.argv[1]; Z = np.load(f'{S}/ef8_rows.npz'); X = Z['X']; c = {k: i for i, k in enumerate(Z['cols'])}
L = 30
import glob
AG = {}
for mk in ('spot', 'perp'):
    t_, p_, f_, n_ = [], [], [], []
    for fn in sorted(glob.glob(f'{S}/agg1s_{mk}_*.npz')):
        z = np.load(fn); t_.append(z['t']); p_.append(z['px']); f_.append(z['flow']); n_.append(z['n'])
    t_ = np.concatenate(t_); AG[mk] = dict(zip(t_.tolist(), zip(np.concatenate(p_), np.concatenate(f_), np.concatenate(n_))))
NCH = 16
U = X[X[:, c['side']] == 1]; Dn = X[X[:, c['side']] == -1]
dkey = {(r[c['ep']], r[c['sec']]): r for r in Dn}
eps = sorted(set(U[:, c['ep']]))
seqs, meta = [], []           # meta: ep, sec, pnl_up, pnl_dn, ask_up, ask_dn, z_up
for ep in eps:
    rows = U[U[:, c['ep']] == ep]; by = {int(r[c['sec']]): r for r in rows}
    F = np.full((296, NCH), np.nan); prev = None; lastp = {'spot': None, 'perp': None}
    for s in range(296):
        r = by.get(s)
        ex = []
        for mk in ('spot', 'perp'):
            a = AG[mk].get(int(ep) + s)
            if a is None: ex += [0.0, 0.0, 0.0]
            else:
                ret = 0.0 if lastp[mk] is None else (a[0] / lastp[mk] - 1) * 1e4
                lastp[mk] = a[0]; ex += [ret, float(np.sign(a[1]) * math.log1p(abs(a[1]) * 10)), math.log1p(a[2])]
        if r is None:
            if prev is not None: F[s] = prev; F[s, 8] = 0.0; F[s, 9] = s / 300; F[s, 10:] = ex
            continue
        f = [r[c['own_ask']], r[c['opp_ask']], r[c['own_bid']], r[c['opp_bid']], math.log1p(r[c['own_size']] or 0),
             math.log1p(r[c['opp_size']] or 0), math.log1p(min(max(r[c['age']], 0), 60)), r[c['dist_bps']], 0.0, s / 300]
        f[8] = (f[7] - prev[7]) if prev is not None else 0.0
        f += ex
        F[s] = f; prev = F[s].copy()
    F = np.nan_to_num(F, nan=0.0)
    for s in range(max(15, L), 241):
        r = by.get(s); d = dkey.get((ep, s))
        if r is None or d is None: continue
        seqs.append(F[s - L + 1:s + 1]); meta.append((ep, s, r[c['pnl']], d[c['pnl']], r[c['own_ask']], d[c['own_ask']], r[c['z']]))
Xs = np.array(seqs, dtype=np.float32); M = np.array(meta)
day = np.array([dt.datetime.utcfromtimestamp(e).strftime('%m-%d') for e in M[:, 0]]); days = sorted(set(day)); TEST = days[2:]
mu, sd = Xs.reshape(-1, NCH).mean(0), Xs.reshape(-1, NCH).std(0) + 1e-6
print(f'samples {len(Xs)}, candles {len(eps)}, test days {TEST}')


class Net(nn.Module):
    def __init__(s):
        super().__init__(); s.g = nn.GRU(NCH, 32, batch_first=True); s.h = nn.Sequential(nn.Linear(32, 32), nn.ReLU(), nn.Linear(32, 2))
    def forward(s, x): o, _ = s.g(x); return s.h(o[:, -1])


def fit(idx):
    net = Net(); opt = torch.optim.Adam(net.parameters(), 1e-3)
    x = torch.tensor((Xs[idx] - mu) / sd); y = torch.tensor(M[idx][:, 2:4].astype(np.float32))
    for ep in range(6):
        perm = torch.randperm(len(idx))
        for i in range(0, len(idx), 512):
            b = perm[i:i + 512]; opt.zero_grad(); l = ((net(x[b]) - y[b]) ** 2).mean(); l.backward(); opt.step()
    return net


def predict(net, idx):
    with torch.no_grad(): return net(torch.tensor((Xs[idx] - mu) / sd)).numpy()


P = np.full((len(Xs), 2), np.nan); Y = {}
for d in TEST:
    tr = np.where(np.isin(day, [x for x in days if x < d]))[0]; te = np.where(day == d)[0]; yv = np.where(day == days[days.index(d) - 1])[0]
    net = fit(tr); P[te] = predict(net, te); Y[d] = (M[yv, 0] + M[yv, 1], predict(net, yv))
    print(f'# {d}: train {len(tr)} test {len(te)} pred p50 {np.median(P[te]):+.4f} p90 {np.quantile(P[te], .9):+.4f}')


def strict(v, q):
    v = np.sort(v); k = q * (len(v) - 1); lo = int(k); hi = min(lo + 1, len(v) - 1); qv = v[lo] + (v[hi] - v[lo]) * (k - lo)
    i = np.searchsorted(v, qv, side='right'); return v[i] if i < len(v) else np.inf


te_idx = np.where(np.isin(day, TEST))[0]; te_idx = te_idx[np.argsort(M[te_idx, 0] + M[te_idx, 1], kind='stable')]
for rule in ('E5', 'E4'):
    for pin in ('none', 'phys'):
        fired = []; done = set(); cur = None; wt, wv = [], []; nxt = None; thr = np.inf
        for i in te_idx:
            d = day[i]; t = M[i, 0] + M[i, 1]
            if rule == 'E4':
                if d != cur:
                    cur = d; yt, yp = Y[d]; sel = yt >= yt.max() - 3600; o = np.argsort(yt[sel])
                    wt = list(np.repeat(yt[sel][o], 2)); wv = list(yp[sel][o].reshape(-1)); nxt = None
                step = math.floor(t / 60) * 60
                if nxt is None or step >= nxt:
                    lo = bisect.bisect_left(wt, step - 3600); wt, wv = wt[lo:], wv[lo:]; k = bisect.bisect_left(wt, step)
                    thr = strict(np.array(wv[:k]), 0.90) if k >= 500 else np.inf; nxt = step + 60
                wt += [t, t]; wv += list(P[i])
            else:
                thr = strict(Y[d][1].reshape(-1), 0.90)
            if M[i, 0] in done: continue
            for side in (0, 1):
                zs = M[i, 6] if side == 0 else -M[i, 6]
                if pin == 'phys' and not zs >= 0: continue
                if P[i, side] >= thr:
                    done.add(M[i, 0]); fired.append((i, side)); break
        if not fired: print(f'{rule} pin={pin}: n0'); continue
        pn = np.array([10 * M[i, 2 + s] for i, s in fired]); ask = np.array([M[i, 4 + s] for i, s in fired])
        fav = np.array([10 * M[i, 2 + (0 if M[i, 4] >= M[i, 5] else 1)] for i, s in fired])
        cost = lambda a: a * (1 + 0.07 * (1 - a))
        def bump(k):
            out = []
            for (i, s), a in zip(fired, ask):
                p = M[i, 2 + s]
                if p == 0: out.append(0); continue
                win = (p + 1) * cost(a) > 0.5
                out.append(10 * ((1 if win else 0) / cost(min(a + k, 0.99)) - 1))
            return np.sum(out)
        cum = np.cumsum(pn); dd = np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum])
        per = {d: pn[[day[i] == d for i, _ in fired]].sum() for d in TEST}
        print(f'{rule} pin={pin:4s} n{len(fired)} /day {len(fired)/len(TEST):.0f} paid {ask.mean():.2f} $ {pn.sum():+.1f} DD {dd:.1f} '
              f'days+ {sum(v > 0 for v in per.values())}/{len(TEST)} | ' + ' '.join(f'{v:+.0f}' for v in per.values()) +
              f' | +1c {bump(.01):+.1f} +2c {bump(.02):+.1f} | FAV null {fav.sum():+.1f}')
