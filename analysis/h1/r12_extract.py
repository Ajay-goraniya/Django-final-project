"""R-12 stage 1: build the historical feature store from spot 1s klines.

Streams one month at a time: download -> parse -> derive features -> write npz -> DELETE the raw.
Peak disk stays under ~1 GB regardless of how many months are processed.

FEATURE MASK (V's addendum 22:49 - "serve the 9 unbuildable features zeroed too so train == serve"):
  BUILT (18), exactly as btc_model_v10.FeatureState computes them:
    move_bps ret5 ret15 ret30 ret60 rv60 range_bps pos_in_range dist_hi_bps dist_lo_bps
    prev1_bps prev2_bps sec_left hod_sin hod_cos mv_x_sec spot_imb15 spot_imb60
  MASKED TO ZERO (12): ofi5 ofi15 ofi60 perp_n15 basis_bps spread_bps imb5 imb20 micro_bps
                       p_venue lv lv_x_sec

DEVIATION FROM MY OWN REPLY 1, stated so it is not silent: reply 1 said basis_bps, ofi60 and
perp_n15 would be APPROXIMATED from futures 1m klines. They are masked instead. A 1m kline is
minute-aligned, not trailing, and perp_n15 is a 15 s count that a 1m bar cannot express at all.
Feeding a misaligned approximation at train time while serve computes the precise value is exactly
the train/serve skew the addendum exists to remove. Masking is the addendum's own logic applied
one step further; 18 honest features beat 21 with 3 lies in them.

`spot_imb15/60` ARE built: 1s klines carry taker-buy base volume, so taker sell = volume - taker
buy, which is the same quantity FeatureState accumulates from the trade stream.
"""
import io, os, sys, time, urllib.request, zipfile

import numpy as np

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
OUT = os.path.join(SP, 'r12')
BASE = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1s/BTCUSDT-1s-%s.zip'
SECS = [30, 75, 120, 165, 210]          # sampled decision seconds inside the 15-240 s window
BUILT = ['move_bps', 'ret5', 'ret15', 'ret30', 'ret60', 'rv60', 'range_bps', 'pos_in_range',
         'dist_hi_bps', 'dist_lo_bps', 'prev1_bps', 'prev2_bps', 'sec_left', 'hod_sin', 'hod_cos',
         'mv_x_sec', 'spot_imb15', 'spot_imb60']


def months(a='2017-08', b='2026-09'):
    y, m = map(int, a.split('-'))
    Y, M = map(int, b.split('-'))
    out = []
    while (y, m) <= (Y, M):
        out.append('%04d-%02d' % (y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def fetch(mon):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(BASE % mon, timeout=180) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            name = z.namelist()[0]
            return np.loadtxt(z.open(name), delimiter=',', usecols=(0, 4, 5, 9), dtype=np.float64)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return None


def build(a):
    """a: (ts_ms, close, volume, taker_buy_base) at 1 s. Returns rows, one per (candle, S)."""
    sec = (a[:, 0] // 1000).astype(np.int64)
    close, vol, tbb = a[:, 1], a[:, 2], a[:, 3]
    lo_s, hi_s = sec[0], sec[-1]
    n = hi_s - lo_s + 1
    px = np.full(n, np.nan)
    bv = np.zeros(n)
    sv = np.zeros(n)
    idx = sec - lo_s
    px[idx] = close
    bv[idx] = tbb
    sv[idx] = np.maximum(vol - tbb, 0.0)
    # forward-fill price across gaps (a second with no trade keeps the last price)
    m = np.isnan(px)
    if m.any():
        good = np.where(~m)[0]
        if len(good) == 0:
            return None
        px[:good[0]] = px[good[0]]
        fill = np.maximum.accumulate(np.where(m, 0, np.arange(n)))
        px = px[fill]
    cb, cs = np.concatenate([[0], np.cumsum(bv)]), np.concatenate([[0], np.cumsum(sv)])
    start = lo_s + (-lo_s % 300)
    rows, keys = [], []
    for c0 in range(start, hi_s - 300 + 1, 300):
        i0 = c0 - lo_s
        if i0 < 600:                                  # prev2 needs open-600 s
            continue
        openp = px[i0]
        if not np.isfinite(openp) or openp <= 0:
            continue
        p1, p2, p3 = px[i0], px[i0 - 300], px[i0 - 600]
        prev1 = (p1 / p2 - 1) * 1e4 if p2 > 0 else 0.0
        prev2 = (p2 / p3 - 1) * 1e4 if p3 > 0 else 0.0
        hod = ((c0 % 86400) / 86400.0) * 2 * np.pi
        hs, hc = np.sin(hod), np.cos(hod)
        for S in SECS:
            j = i0 + S
            p = px[j]
            seg = px[i0:j + 1]
            hi, lo = seg.max(), seg.min()
            rng = hi - lo
            ret = lambda k: (p / px[j - k] - 1) * 1e4 if px[j - k] > 0 else 0.0
            g = px[j - 60:j + 1]
            lr = np.diff(np.log(g))
            rv60 = float(np.std(lr) * 1e4) if len(lr) > 1 else 0.0
            imb = lambda k: ((cb[j + 1] - cb[j + 1 - k]) - (cs[j + 1] - cs[j + 1 - k])) / t \
                if (t := (cb[j + 1] - cb[j + 1 - k]) + (cs[j + 1] - cs[j + 1 - k])) > 0 else 0.0
            move = (p / openp - 1) * 1e4
            sl = 300 - S
            rows.append([move, ret(5), ret(15), ret(30), ret(60), rv60,
                         rng / openp * 1e4, ((p - lo) / rng) if rng > 0 else 0.5,
                         (hi - p) / openp * 1e4, (p - lo) / openp * 1e4,
                         prev1, prev2, sl, hs, hc, move * sl / 300.0, imb(15), imb(60)])
            keys.append([c0, S, 1 if px[i0 + 299] >= openp else 0])
    if not rows:
        return None
    return np.array(rows, np.float32), np.array(keys, np.int64)


def main():
    os.makedirs(OUT, exist_ok=True)
    todo = months()
    t0 = time.time()
    for i, mon in enumerate(todo):
        f = os.path.join(OUT, mon + '.npz')
        if os.path.exists(f):
            continue
        a = fetch(mon)
        if a is None or len(a) < 1000:
            print('%s  no data' % mon, flush=True)
            continue
        r = build(a)
        del a
        if r is None:
            print('%s  no candles' % mon, flush=True)
            continue
        X, K = r
        np.savez_compressed(f, X=X, K=K)
        print('%s  %7d rows  %6.1fs elapsed  (%d/%d)'
              % (mon, len(X), time.time() - t0, i + 1, len(todo)), flush=True)
    print('DONE %d months in %.1f min' % (len(todo), (time.time() - t0) / 60), flush=True)


if __name__ == '__main__':
    main()
