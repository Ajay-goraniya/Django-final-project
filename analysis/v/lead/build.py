#!/usr/bin/env python3
"""Stage-1 Binance lead test, step 1: per-day feature/label build from data.binance.vision aggTrades.

For each UTC day writes <out>/<day>.npz:
  X      (864000 x F) float32 features on a 100 ms grid t_i = d0 + i*100ms, built ONLY from trades with
         timestamp <= t_i (perp ms stamps are shifted to the END of their ms: +999 us, so nothing can leak).
  fwd    forward spot moves from t_i (bps, last-trade price): end-point r_H, max-up u_H, max-down d_H
         for H = 300/500/1000 ms.
  ev     spot move episodes on a 10 ms grid: (dir, X_bps, start_us, done_us), start = last time at the
         low (high) inside the 1 s window that completed a >= X bps move.
  xc10   perp->spot cross-correlation of 10 ms log returns, lags -50..+50 bins (+k = perp LEADS by k bins)
  xc1    same at 1 ms, lags -100..+100
Spot archive stamps are microseconds, perp milliseconds. Price = last trade (BTCUSDT spot tick = 0.01 USD,
~0.001 bps, so last ~= mid to well under a bp)."""
import argparse, io, os, subprocess, zipfile, datetime as dt, numpy as np, pandas as pd

ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--days', nargs='+', required=True)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
B = 'https://data.binance.vision/data/'
US = 1_000_000; MS = 1000; STEP = 100 * MS; N = 864000
WIN = [100, 250, 500, 1000, 3000]
HOR = [300, 500, 1000]
EVX = [2, 5, 10]


def get(path):
    r = subprocess.run(['curl', '-sSf', '--retry', '3', B + path], capture_output=True, check=True)
    z = zipfile.ZipFile(io.BytesIO(r.stdout)); return z.open(z.namelist()[0]).read()


def load(day):
    s = pd.read_csv(io.BytesIO(get(f'spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{day}.zip')), header=None,
                    usecols=[1, 2, 5, 6])
    ts = s[5].values.astype(np.int64)
    ts = np.where(ts > 1e14, ts, ts * 1000)                                   # -> us
    sp = dict(ts=ts, p=s[1].values.astype(np.float64), q=s[2].values.astype(np.float64),
              side=np.where(s[6].astype(str).str.lower().values == 'true', -1, 1).astype(np.int8))
    f = pd.read_csv(io.BytesIO(get(f'futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{day}.zip')))
    ms = f['transact_time'].values.astype(np.int64)
    pp = dict(ts=ms * 1000 + 999, ts_raw=ms * 1000, p=f['price'].values.astype(np.float64),
              q=f['quantity'].values.astype(np.float64),
              side=np.where(f['is_buyer_maker'].astype(str).str.lower().values == 'true', -1, 1).astype(np.int8))
    for d in (sp, pp):                                                        # stable time order
        o = np.argsort(d['ts'], kind='stable')
        for k in d: d[k] = d[k][o]
    return sp, pp


def flow(d, t, pre):
    """Features of one tape at grid times t (us). Window (t-W, t]."""
    ts, p, q, sd = d['ts'], d['p'], d['q'], d['side']
    out = {}
    hi = np.searchsorted(ts, t, 'right')
    csv = np.r_[0, np.cumsum(q * sd)]; csq = np.r_[0, np.cumsum(q)]
    lp = np.log(p)
    last = np.where(hi > 0, lp[np.maximum(hi - 1, 0)], np.nan)
    cnt = {}
    for W in WIN:
        lo = np.searchsorted(ts, t - W * MS, 'right')
        out[f'{pre}v{W}'] = csv[hi] - csv[lo]
        cnt[W] = (hi - lo).astype(np.float64); out[f'{pre}n{W}'] = cnt[W]
        tot = csq[hi] - csq[lo]
        if W in (250, 1000): out[f'{pre}imb{W}'] = out[f'{pre}v{W}'] / np.maximum(tot, 1e-9)
        hW = np.searchsorted(ts, t - W * MS, 'right')
        prev = np.where(hW > 0, lp[np.maximum(hW - 1, 0)], np.nan)
        out[f'{pre}r{W}'] = (last - prev) * 1e4
    out[f'{pre}acc250'] = np.log((cnt[250] + 1) / (cnt[3000] / 12 + 1))
    out[f'{pre}acc100'] = np.log((cnt[100] + 1) / (cnt[1000] / 10 + 1))
    out[f'{pre}dt'] = np.minimum((t - np.where(hi > 0, ts[np.maximum(hi - 1, 0)], t - 5 * US)) / MS, 5000)
    # signed run length of same-side trades ending at the last trade <= t
    ch = np.r_[True, sd[1:] != sd[:-1]]; st = np.flatnonzero(ch); rid = np.cumsum(ch) - 1
    rl = (np.arange(len(sd)) - st[rid] + 1) * sd
    rq = (np.cumsum(q) - np.r_[0, np.cumsum(q)][st[rid]]) * sd
    j = np.maximum(hi - 1, 0)
    out[f'{pre}run'] = np.where(hi > 0, rl[j], 0).astype(np.float64)
    out[f'{pre}runq'] = np.where(hi > 0, rq[j], 0)
    # largest trade in (t-1000, t]: 100 ms buckets, bucket i = (t_i - 100ms, t_i]
    b = np.ceil((ts - t[0]) / STEP).astype(np.int64); ok = (b >= 0) & (b < len(t))
    bb, qq, ss = b[ok], q[ok], (q * sd)[ok]
    o = np.lexsort((qq, bb)); bb, qq, ss = bb[o], qq[o], ss[o]
    lastof = np.r_[bb[1:] != bb[:-1], True]
    bm = np.zeros(len(t)); bs = np.zeros(len(t)); bm[bb[lastof]] = qq[lastof]; bs[bb[lastof]] = ss[lastof]
    pm = np.r_[np.zeros(9), bm]; ps = np.r_[np.zeros(9), bs]
    V = np.lib.stride_tricks.sliding_window_view(pm, 10); am = V.argmax(1)
    out[f'{pre}maxq'] = V[np.arange(len(t)), am]
    out[f'{pre}bigs'] = np.lib.stride_tricks.sliding_window_view(ps, 10)[np.arange(len(t)), am]
    return out, last


def grid_last(d, g):
    hi = np.searchsorted(d['ts'], g, 'right')
    return np.log(d['p'][np.maximum(hi - 1, 0)])


def xcorr(ts_s, p_s, ts_p, p_p, d0, res_us, n_bins, L):
    """corr of spot return r_s[j] with perp return r_p[j-k]; +k => perp leads. floor binning both."""
    def rets(ts, p):
        bi = ((ts - d0) // res_us).astype(np.int64); ok = (bi >= 0) & (bi < n_bins)
        bi, lp = bi[ok], np.log(p[ok])
        lastof = np.r_[bi[1:] != bi[:-1], True]
        ub, ul = bi[lastof], lp[lastof]                    # last price per occupied bin
        r = np.diff(ul)                                     # return lands in the bin where the new price prints
        return ub[1:], r
    bs, rs = rets(ts_s, p_s); bp, rp = rets(ts_p, p_p)
    rp_full = np.zeros(n_bins, np.float64); rp_full[bp] = rp
    ss = np.sqrt((rs ** 2).sum() * (rp ** 2).sum())
    out = np.zeros(2 * L + 1)
    for i, k in enumerate(range(-L, L + 1)):
        j = bs - k; ok = (j >= 0) & (j < n_bins)
        out[i] = (rs[ok] * rp_full[j[ok]]).sum() / ss
    return out


def episodes(Ls, g_us):
    """Moves >= X bps within 1 s on the 10 ms last-price grid. Returns rows (dir, X, start_us, done_us)."""
    rows = []
    s = pd.Series(Ls)
    mn = s.rolling(100, min_periods=1).min().values; mx = s.rolling(100, min_periods=1).max().values
    for dr, U in ((1, (Ls - mn) * 1e4), (-1, (mx - Ls) * 1e4)):
        for X in EVX:
            on = U >= X
            edge = np.flatnonzero(on & ~np.r_[False, on[:-1]])
            for k in edge:
                w = Ls[max(0, k - 99):k + 1]
                ext = np.flatnonzero(w == (w.min() if dr == 1 else w.max()))[-1] + max(0, k - 99)
                rows.append((dr, X, g_us[ext], g_us[k]))
    return np.array(rows, dtype=np.int64)


for day in a.days:
    fn = os.path.join(a.out, day + '.npz')
    if os.path.exists(fn): print(day, 'exists'); continue
    d0 = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp()) * US
    sp, pp = load(day)
    t = d0 + np.arange(N, dtype=np.int64) * STEP
    fs, ls = flow(sp, t, 's_'); fp, lpp = flow(pp, t, 'p_')
    basis = (lpp - ls) * 1e4
    fx = {**fs, **fp}
    for W in (100, 250, 500, 1000):
        fx[f'db{W}'] = basis - (grid_last(pp, t - W * MS) - grid_last(sp, t - W * MS)) * 1e4
    fx['db60s'] = basis - pd.Series(basis).rolling(600, min_periods=1).mean().values
    names = sorted(fx); X = np.column_stack([fx[k] for k in names]).astype(np.float32)
    # forward labels from a 10 ms spot last-price grid (price <= each 10 ms stamp)
    g = d0 + np.arange(N * 10 + 101, dtype=np.int64) * 10 * MS
    Ls = grid_last(sp, g)
    fwd = {}
    for H in HOR:
        w = H // 10
        cur = Ls[0:N * 10:10]
        fwd[f'r{H}'] = (Ls[w:N * 10 + w:10] - cur) * 1e4
        rmax = pd.Series(Ls).rolling(w).max().values; rmin = pd.Series(Ls).rolling(w).min().values
        fwd[f'u{H}'] = (rmax[w:N * 10 + w:10] - cur) * 1e4          # max over bins j+1..j+w
        fwd[f'd{H}'] = (cur - rmin[w:N * 10 + w:10]) * 1e4
    ev = episodes(Ls[:N * 10], g[:N * 10])
    xc10 = xcorr(sp['ts'], sp['p'], pp['ts_raw'], pp['p'], d0, 10 * MS, N * 10, 50)
    xc1 = xcorr(sp['ts'], sp['p'], pp['ts_raw'], pp['p'], d0, MS, N * 100, 100)
    np.savez_compressed(fn, X=X, names=np.array(names), ev=ev, xc10=xc10, xc1=xc1,
                        **{k: v.astype(np.float32) for k, v in fwd.items()},
                        nsp=len(sp['ts']), npp=len(pp['ts']))
    print(day, 'spot', len(sp['ts']), 'perp', len(pp['ts']), 'F', len(names),
          'ev5', int(((ev[:, 1] == 5)).sum()), 'xc10 peak lag', int(np.argmax(xc10)) - 50, flush=True)
