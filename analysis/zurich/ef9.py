#!/usr/bin/env python3
"""EF-9 INSUF: a 1D-CNN on the raw 250 ms stream. READ-ONLY. PAPER. Master OFF.

Owner's order was a SEQUENCE model on the raw stream instead of stumps on hand-made summaries. What
Zurich actually holds at 250 ms over multiple days is BOTH ASKS and nothing else, so this is built on
own_ask / opp_ask / line-distance / sec and is marked INSUF. Dropped for want of data, each listed
because the absence is the finding, not a detail: the btc5 BID side (never recorded anywhere, at any
cadence), Binance per-250 ms price (k1s is 1 s and covers 1.67 d), and signed taker flow (unheld; a
recorder for spot was started 09-28 18:1x, and PERP is unreachable from this box - fstream times out).

No hand features. The only non-sequence quantity is p_side, and it is used ONLY to pin the side as the
rule requires, never as an input.

MODEL  numpy 1D-CNN, no torch on this box: conv(4->16,k5,s2) - ReLU - conv(16->16,k5,s2) - ReLU -
       mean+max pool - dense(32->1), Adam, MSE. Walk-forward: day D trains on days < D.
TARGET after-fill $ per $1 of buying THAT side at that pass under the +250 ms FAK sim, 0 if no fill.
RULE   strict q.90 trailing-1h cut (smallest distinct prediction above the quantile), pinned p_side>=0.5,
       first qualifying pass, one fire per candle, anchors 0/15/30/45 s.
"""
import sys, os, json, sqlite3, collections, datetime as dt, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef2_model import per1, cost
from ef3 import platt, pad_cost, STAKE, MIN_CELL
from ef3_shadow import outcomes

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
STEP_MS, WIN, TICK, DELAY_MS = 250, 120, 0.01, 250      # 120 steps x 250 ms = 30 s
ANCHORS, Q = (0, 15, 30, 45), 0.90
CACHE = '/home/ubuntu/pm_ef3/ef9_seq.npz'


# ---------------- numpy 1D-CNN ---------------------------------------------------------------------
def _idx(C, T, k, st):
    """Explicit (row, col) index pair for im2col, so the backward pass is a provable transpose."""
    o = (T - k) // st + 1
    tt = (np.arange(o)[:, None] * st + np.arange(k)[None, :])          # (o,k) time index
    cc = np.arange(C)[:, None, None]                                    # (C,1,1)
    col = (cc * k + np.arange(k)[None, None, :]).repeat(o, 1)           # (C,o,k)
    return o, tt, cc, col


def im2col(x, k, st):
    """(N,C,T) -> (N*o, C*k); rows are ordered sample-major then time."""
    N, C, T = x.shape
    o, tt, cc, _ = _idx(C, T, k, st)
    v = x[:, cc, tt[None, :, :]]                 # (N,C,o,k)
    return v.transpose(0, 2, 1, 3).reshape(N * o, C * k)


def col2im(d, N, C, T, k, st):
    """Exact transpose of im2col: scatter-add (N*o, C*k) back onto (N,C,T)."""
    o, tt, cc, _ = _idx(C, T, k, st)
    g = np.zeros((N, C, T), dtype=d.dtype)
    dd = d.reshape(N, o, C, k).transpose(0, 2, 1, 3)                    # (N,C,o,k)
    np.add.at(g, (slice(None), cc, tt[None, :, :]), dd)
    return g


class CNN:
    """conv(4->16,k5,s2) - ReLU - conv(16->16,k5,s2) - ReLU - mean+max pool - dense. Adam, MSE.

    The first version of this hand-rolled a gradient w.r.t. the first layer's output with a slicing loop
    and produced nan on the very first day. Replaced with col2im, which is the literal transpose of the
    forward gather - a gradient that has to be reasoned about line by line is a gradient that will be
    wrong, and numerically checked below.
    """

    def __init__(self, cin=4, h=16, k=5, seed=0):
        r = np.random.default_rng(seed)
        self.k, self.cin, self.h = k, cin, h
        self.W1 = r.normal(0, (2.0 / (cin * k)) ** .5, (cin * k, h)); self.b1 = np.zeros(h)
        self.W2 = r.normal(0, (2.0 / (h * k)) ** .5, (h * k, h)); self.b2 = np.zeros(h)
        self.W3 = r.normal(0, (2.0 / (2 * h)) ** .5, (2 * h, 1)); self.b3 = np.zeros(1)
        self.p = ['W1', 'b1', 'W2', 'b2', 'W3', 'b3']
        self.m = {n: np.zeros_like(getattr(self, n)) for n in self.p}
        self.v = {n: np.zeros_like(getattr(self, n)) for n in self.p}
        self.t = 0

    def fwd(self, x):
        N, C, T = x.shape
        c1 = im2col(x, self.k, 2); z1 = c1 @ self.W1 + self.b1; a1 = np.maximum(z1, 0)
        T1 = (T - self.k) // 2 + 1
        o1 = a1.reshape(N, T1, self.h).transpose(0, 2, 1)               # (N,h,T1)
        c2 = im2col(o1, self.k, 2); z2 = c2 @ self.W2 + self.b2; a2 = np.maximum(z2, 0)
        T2 = (T1 - self.k) // 2 + 1
        o2 = a2.reshape(N, T2, self.h)                                   # (N,T2,h)
        g = np.concatenate([o2.mean(1), o2.max(1)], 1)
        return (g @ self.W3 + self.b3).ravel(), (x, c1, z1, T1, c2, z2, o2, T2, g, N, T)

    def bwd(self, ca, dy):
        x, c1, z1, T1, c2, z2, o2, T2, g, N, T = ca
        dy = dy.reshape(-1, 1)
        gW3 = g.T @ dy; gb3 = dy.sum(0); dg = dy @ self.W3.T
        dmean, dmax = dg[:, :self.h], dg[:, self.h:]
        do2 = np.repeat((dmean / T2)[:, None, :], T2, 1)
        am = o2.argmax(1)
        np.add.at(do2, (np.arange(N)[:, None], am, np.arange(self.h)[None, :]), dmax)
        dz2 = do2.reshape(-1, self.h) * (z2 > 0)
        gW2 = c2.T @ dz2; gb2 = dz2.sum(0)
        do1 = col2im(dz2 @ self.W2.T, N, self.h, T1, self.k, 2)          # (N,h,T1)
        dz1 = do1.transpose(0, 2, 1).reshape(-1, self.h) * (z1 > 0)
        gW1 = c1.T @ dz1; gb1 = dz1.sum(0)
        return dict(W1=gW1, b1=gb1, W2=gW2, b2=gb2, W3=gW3, b3=gb3)

    def step(self, gr, lr=2e-3):
        self.t += 1
        for n in self.p:
            g = np.clip(gr[n], -1e3, 1e3)
            self.m[n] = .9 * self.m[n] + .1 * g
            self.v[n] = .999 * self.v[n] + .001 * g * g
            mh = self.m[n] / (1 - .9 ** self.t); vh = self.v[n] / (1 - .999 ** self.t)
            setattr(self, n, getattr(self, n) - lr * mh / (np.sqrt(vh) + 1e-8))


def gradcheck():
    """Numeric check on a tiny batch. A hand-written backward pass gets verified or it does not ship."""
    r = np.random.default_rng(1)
    net = CNN(seed=2)
    x = r.normal(size=(6, 4, 120)); t = r.normal(size=6)
    yh, ca = net.fwd(x)
    gr = net.bwd(ca, (2.0 / len(x)) * (yh - t))
    worst = 0.0
    for n in net.p:
        A = getattr(net, n); idx = tuple(r.integers(0, s) for s in A.shape)
        e = 1e-5; o = A[idx]
        A[idx] = o + e; lp = ((net.fwd(x)[0] - t) ** 2).mean()
        A[idx] = o - e; lm = ((net.fwd(x)[0] - t) ** 2).mean()
        A[idx] = o
        num = (lp - lm) / (2 * e); ana = gr[n][idx]
        rel = abs(num - ana) / max(1e-8, abs(num) + abs(ana))
        worst = max(worst, rel)
        print(f'    {n:3s} numeric {num:+.6e}  analytic {ana:+.6e}  rel {rel:.2e}')
    print(f'  gradcheck worst relative error {worst:.2e}  -> {"PASS" if worst < 1e-4 else "FAIL"}')
    return worst < 1e-4


def build():
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        return {k: z[k] for k in z.files}
    L = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
    ref = {}
    for t, p in L.execute('SELECT ts, ref_px FROM tape1s WHERE ref_px IS NOT NULL'):
        ref[int(t)] = float(p)
    vo = outcomes()
    c = sqlite3.connect(f'file:{ARCH}?mode=ro', uri=True)
    by = collections.defaultdict(list)
    for ts, ep, side, p, ua, da in c.execute(
            'SELECT ts_ms,epoch,side,p,up_ask,dn_ask FROM decide_log WHERE p IS NOT NULL AND side IS NOT NULL '
            'AND up_ask IS NOT NULL AND dn_ask IS NOT NULL ORDER BY ts_ms'):
        if ep not in vo: continue
        by[ep].append((int(ts), side, float(p), float(ua), float(da)))
    S, Y, Q_, EP, TS, SD, PS, DAY = [], [], [], [], [], [], [], []
    for ep, rs in by.items():
        line = ref.get(ep)
        if line is None: continue
        n = 1 + 300 * 1000 // STEP_MS
        gu = np.full(n, np.nan); gd = np.full(n, np.nan); gl = np.full(n, 0.0)
        for ts, side, p, ua, da in rs:
            i = (ts - ep * 1000) // STEP_MS
            if 0 <= i < n: gu[i], gd[i] = ua, da
        for s in range(0, 301):
            v = ref.get(ep + s)
            if v is not None:
                i = s * 1000 // STEP_MS
                if i < n: gl[i] = (v - line) / line * 1e4
        for g in (gu, gd):
            # Forward fill, THEN back-fill the head. A pure ffill leaves NaN before the candle's first
            # logged pass, and a 30 s window on a pass at sec 30 reaches back into exactly that prefix -
            # which is why the first two runs produced nan predictions on every day with a gradient that
            # numerically checks to 5e-11. The model was fine; the tensor was not.
            m = np.isnan(g)
            if m.all(): continue
            idx = np.where(~m, np.arange(n), 0); np.maximum.accumulate(idx, out=idx)
            g[:] = g[idx]
            first = int(np.argmax(~np.isnan(g)))
            if first > 0: g[:first] = g[first]
        m = gl == 0
        idx = np.where(~m, np.arange(n), 0); np.maximum.accumulate(idx, out=idx); gl[:] = gl[idx]
        ts_a = np.array([r[0] for r in rs]); ua_a = np.array([r[3] for r in rs]); da_a = np.array([r[4] for r in rs])
        day = dt.datetime.fromtimestamp(ep, dt.timezone.utc).strftime('%m-%d')
        out = vo[ep]
        for i2, (ts, side_l, p_l, ua, da) in enumerate(rs):
            sec = ts // 1000 - ep
            if not (15 <= sec <= 240): continue
            gi = (ts - ep * 1000) // STEP_MS
            if gi < WIN: continue
            j = int(np.searchsorted(ts_a, ts + DELAY_MS, 'left'))
            w = slice(gi - WIN + 1, gi + 1)
            for sd_, own, opp, oa in (('UP', ua, da, ua_a), ('DOWN', da, ua, da_a)):
                if not (0.01 < own < 0.99): continue
                q = np.nan
                if j < len(rs):
                    lat = float(oa[j])
                    if 0.01 < lat < 0.99 and lat <= own + TICK + 1e-12: q = lat
                seq = np.stack([(gu[w] if sd_ == 'UP' else gd[w]), (gd[w] if sd_ == 'UP' else gu[w]),
                                gl[w] / 10.0, np.full(WIN, sec / 240.0)]).astype(np.float32)
                S.append(seq); Y.append(1.0 if sd_ == out else 0.0); Q_.append(q)
                EP.append(ep); TS.append(ts); SD.append(1 if sd_ == 'UP' else 0)
                PS.append(p_l if sd_ == side_l else 1.0 - p_l); DAY.append(day)
    Sarr = np.stack(S)
    good = np.isfinite(Sarr).all((1, 2))
    if not good.all():
        print(f'  dropping {int((~good).sum()):,} of {len(Sarr):,} sequences with a non-finite step')
        Sarr = Sarr[good]
        Y = [v for v, k_ in zip(Y, good) if k_]; Q_ = [v for v, k_ in zip(Q_, good) if k_]
        EP = [v for v, k_ in zip(EP, good) if k_]; TS = [v for v, k_ in zip(TS, good) if k_]
        SD = [v for v, k_ in zip(SD, good) if k_]; PS = [v for v, k_ in zip(PS, good) if k_]
        DAY = [v for v, k_ in zip(DAY, good) if k_]
    assert np.isfinite(Sarr).all(), 'non-finite sequences survived the filter'
    d = dict(S=Sarr, y=np.array(Y, np.float32), q=np.array(Q_, np.float32),
             ep=np.array(EP, np.int64), ts=np.array(TS, np.int64), up=np.array(SD, np.int8),
             ps=np.array(PS, np.float32), day=np.array(DAY))
    np.savez(CACHE, **d)
    return d


if __name__ == '__main__':
    if not gradcheck(): sys.exit('gradcheck FAILED - not training on an unverified gradient')
    D = build()
    S, y, q, ep, ts, up, ps, day = (D[k] for k in ('S', 'y', 'q', 'ep', 'ts', 'up', 'ps', 'day'))
    filled = np.isfinite(q)
    tgt = np.where(filled, per1(y, np.where(filled, q, 0.5)), 0.0).astype(np.float32)
    days = sorted(set(day.tolist()))
    print(f'EF-9 INSUF. sequences {len(S):,}  channels 4 (own_ask, opp_ask, line_bps/10, sec/240)  '
          f'{WIN} x {STEP_MS} ms = 30 s')
    print(f'  days {days}   fill rate {100*filled.mean():.1f}%   target mean {tgt.mean():+.4f}')
    print(f'  DROPPED for want of data: btc5 bids/sizes (never recorded), Binance 250 ms price, '
          f'signed taker flow (spot recorder started today, perp unreachable)')
    mu = S.reshape(len(S), 4, -1).mean((0, 2), keepdims=True)
    sd = S.reshape(len(S), 4, -1).std((0, 2), keepdims=True) + 1e-6
    pred = np.full(len(S), np.nan, np.float32)
    rng = np.random.default_rng(0)
    for k, dcur in enumerate(days):
        if k == 0: continue
        tr = np.where(np.isin(day, days[:k]))[0]; te = np.where(day == dcur)[0]
        if len(tr) < 20000: continue
        sub = rng.choice(tr, size=min(len(tr), 120000), replace=False)
        net = CNN()
        B = 4096
        for epch in range(4):
            rng.shuffle(sub)
            for i in range(0, len(sub) - B + 1, B):
                b = sub[i:i + B]
                x = (S[b] - mu) / sd
                yh, ca = net.fwd(x)
                dl = (2.0 / len(b)) * (yh - tgt[b])
                net.step(net.bwd(ca, dl))
        outp = np.empty(len(te), np.float32)
        for i in range(0, len(te), 8192):
            outp[i:i + 8192] = net.fwd((S[te[i:i + 8192]] - mu) / sd)[0]
        pred[te] = outp
        print(f'  day {dcur}: train {len(sub):,} test {len(te):,}  corr(pred,target) '
              f'{np.corrcoef(pred[te], tgt[te])[0,1]:+.4f}')
    np.save('/home/ubuntu/pm_ef3/ef9_pred.npy', pred)
    print('  predictions saved -> /home/ubuntu/pm_ef3/ef9_pred.npy')
