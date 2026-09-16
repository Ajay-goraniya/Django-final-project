"""R-15 (a) -- higher-timeframe state, added to the 9-year store.

USER ORDER (via V, 09-16 00:4x/00:5x): "the issue is the signal that fails to predict correctly, not
the execution", and "keep working on finding the solution for how the drawdowns can be stopped."
The concrete failure the user sees is a run of 7-9 same-side losses inside one trend. The refuted
"trend guard" tried to fix that with an on/off rule; this is different in method - the trend state is
given to the learner as FEATURES and it decides. That is the standing rule's own remedy: "give it a
trained brain that knows that move is wrong and it will reverse", not a gate.

Built from the same spot 1s klines the 18-feature store came from, keyed by (candle_epoch, S) so it
joins straight onto r12/*.npz.

WINDOW DEFINITION, stated because train/serve parity depends on it: every higher-timeframe window
ends at the LAST FULLY COMPLETED MINUTE at or before the decision second, never at the decision
second itself. A live engine has the same minute grid available, so this is computable at serve time
exactly as it is here. It costs at most 59 s of freshness on a 1-4 h window, which is nothing, and it
buys an aggregation that cannot silently include the future.

MONTH BOUNDARIES: a 4 h window needs 14,400 s of history, so the first hours of each monthly file
have none. Rather than zero-fill them (which teaches the model that "no history" is a real state),
the previous month's LAST DAY is downloaded and prepended as priming data, and any row still short of
its full lookback is DROPPED. Dropping is safe here: the 18-feature store is the join key, so a
dropped row just means that (epoch, S) has no (a) block and the arm that needs it skips it.
"""
import io, os, sys, time, urllib.request, zipfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r12_extract import SP, SECS, to_sec, months

OUT = os.path.join(SP, 'r15a')
MON = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1s/BTCUSDT-1s-%s.zip'
DAY = 'https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1s/BTCUSDT-1s-%s.zip'

HTF = ['ret_5m', 'ret_15m', 'ret_1h', 'ret_4h',
       'rv_15m', 'rv_1h', 'rv_ratio_60_15m', 'rv_ratio_15m_1h',
       'vwap_dist_1h', 'vwap_dist_4h',
       'pos_in_range_1h', 'pos_in_range_4h', 'dist_hi_4h', 'dist_lo_4h',
       'streak', 'secs_since_reversal']
LOOKBACK = 14400 + 300      # 4 h plus one candle of slack


def get(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=240) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            return np.loadtxt(z.open(z.namelist()[0]), delimiter=',',
                              usecols=(0, 4, 5), dtype=np.float64)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return None


def prev_day(mon):
    y, m = map(int, mon.split('-'))
    import datetime as dt
    d = dt.date(y, m, 1) - dt.timedelta(days=1)
    return d.isoformat()


def grid(a):
    """1 s close/volume on a dense second grid, forward-filled across gaps."""
    sec = to_sec(a[:, 0])
    lo, hi = sec[0], sec[-1]
    n = hi - lo + 1
    px = np.full(n, np.nan)
    vol = np.zeros(n)
    i = sec - lo
    px[i] = a[:, 1]
    vol[i] = a[:, 2]
    m = np.isnan(px)
    if m.any():
        good = np.where(~m)[0]
        if not len(good):
            return None
        px[:good[0]] = px[good[0]]
        px = px[np.maximum.accumulate(np.where(m, 0, np.arange(n)))]
    return lo, px, vol


def build(lo, px, vol, first_candle):
    """One row per (candle, S). Windows end at the last completed minute before the decision second."""
    n = len(px)
    # minute grid: index k covers seconds [lo + 60k, lo + 60k + 59]
    nm = n // 60
    if nm < 260:
        return None
    P = px[:nm * 60].reshape(nm, 60)
    V = vol[:nm * 60].reshape(nm, 60)
    m_close = P[:, -1]
    m_high, m_low = P.max(1), P.min(1)
    m_vol = V.sum(1)
    m_pv = (P * V).sum(1)
    c_vol = np.concatenate([[0.0], np.cumsum(m_vol)])
    c_pv = np.concatenate([[0.0], np.cumsum(m_pv)])
    lr = np.concatenate([[0.0], np.diff(np.log(np.maximum(m_close, 1e-12)))])

    def roll(arr, w, fn):
        from numpy.lib.stride_tricks import sliding_window_view
        out = np.full(len(arr), np.nan)
        if len(arr) >= w:
            out[w - 1:] = fn(sliding_window_view(arr, w), axis=-1)
        return out

    hi_1h, lo_1h = roll(m_high, 60, np.max), roll(m_low, 60, np.min)
    hi_4h, lo_4h = roll(m_high, 240, np.max), roll(m_low, 240, np.min)
    rv15 = roll(lr, 15, np.std) * 1e4
    rv1h = roll(lr, 60, np.std) * 1e4

    start = lo + (-lo % 300)
    rows, keys = [], []
    # completed-candle direction history for the streak, built as we go (strictly earlier candles)
    dirs = {}
    for c0 in range(start, lo + n - 300, 300):
        i0 = c0 - lo
        if i0 + 299 < n:
            o, c = px[i0], px[i0 + 299]
            dirs[c0] = 1 if c >= o else -1

    ordered = sorted(dirs)
    streak_of, since_of = {}, {}
    run, last_rev_epoch = 0, None
    prev = None
    for e in ordered:
        # state BEFORE this candle opens = built only from strictly earlier candles
        streak_of[e] = run if prev is None else run * prev
        since_of[e] = (e - last_rev_epoch) if last_rev_epoch is not None else -1
        d = dirs[e]
        if prev is None or d == prev:
            run += 1
        else:
            run = 1
            last_rev_epoch = e
        prev = d

    for c0 in ordered:
        if c0 < first_candle:
            continue
        i0 = c0 - lo
        if i0 < LOOKBACK or i0 + 299 >= n:
            continue
        openp = px[i0]
        if not (openp > 0):
            continue
        for S in SECS:
            j = i0 + S
            p = px[j]
            k = (j // 60) - 1                     # last FULLY COMPLETED minute strictly before j
            if k < 240 or k >= nm:
                continue
            if not np.isfinite(hi_4h[k]) or not np.isfinite(rv1h[k]):
                continue
            r = lambda back: (p / px[j - back] - 1) * 1e4 if px[j - back] > 0 else 0.0
            vw = lambda w: ((c_pv[k + 1] - c_pv[k + 1 - w]) / t
                            if (t := (c_vol[k + 1] - c_vol[k + 1 - w])) > 0 else p)
            v1, v4 = vw(60), vw(240)
            g = px[j - 60:j + 1]
            d60 = np.diff(np.log(np.maximum(g, 1e-12)))
            rv60 = float(np.std(d60) * 1e4) if len(d60) > 1 else 0.0
            r1, r4 = hi_1h[k] - lo_1h[k], hi_4h[k] - lo_4h[k]
            rows.append([
                r(300), r(900), r(3600), r(14400),
                rv15[k], rv1h[k],
                rv60 / rv15[k] if rv15[k] > 1e-9 else 0.0,
                rv15[k] / rv1h[k] if rv1h[k] > 1e-9 else 0.0,
                (p - v1) / p * 1e4, (p - v4) / p * 1e4,
                (p - lo_1h[k]) / r1 if r1 > 0 else 0.5,
                (p - lo_4h[k]) / r4 if r4 > 0 else 0.5,
                (hi_4h[k] - p) / p * 1e4, (p - lo_4h[k]) / p * 1e4,
                float(streak_of[c0]),
                float(since_of[c0] + S) if since_of[c0] >= 0 else -1.0,
            ])
            keys.append([c0, S])
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
        a = get(MON % mon)
        if a is None or len(a) < 1000:
            print('%s  no data' % mon, flush=True)
            continue
        prime = get(DAY % prev_day(mon))
        first_candle = int(to_sec(a[:, 0])[0])
        if prime is not None and len(prime) > 1000:
            a = np.vstack([prime, a])
        g = grid(a)
        del a, prime
        if g is None:
            print('%s  no grid' % mon, flush=True); continue
        r = build(g[0], g[1], g[2], first_candle)
        del g
        if r is None:
            print('%s  no rows' % mon, flush=True); continue
        np.savez_compressed(f, H=r[0], K=r[1])
        print('%s  %7d rows  %6.1fs  (%d/%d)' % (mon, len(r[0]), time.time() - t0, i + 1, len(todo)),
              flush=True)
    print('DONE %d months in %.1f min' % (len(todo), (time.time() - t0) / 60), flush=True)


if __name__ == '__main__':
    main()
