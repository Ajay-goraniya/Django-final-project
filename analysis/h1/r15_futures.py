"""R-15 (b) -- futures taker ratio and open-interest change, from data.binance.vision metrics.

R-7 found the taker buy/sell ratio ordered accuracy 58.5 / 56.6 / 50.7 by tercile on 7 of 7 days
(permutation p=0.0065) on ONE WEEK. V's R-15 brief asks for the same signal at scale: the metrics
archive goes back years, so the question becomes whether that ordering survives nine - in practice
six - years of walk-forward instead of a week.

BAR ALIGNMENT, and this is the whole correctness question for this source. Metrics bars are 5-minute
and share the candle grid: the bar stamped T covers [T, T+5m). For a decision taken at second S
inside the candle that opens at c0, the bar stamped c0 is STILL RUNNING and contains the answer.
Only the bar stamped c0-300 is complete. Every feature here reads c0-300 or earlier. V's brief says
the same thing ("at the prev-completed bar") and it is what makes the source usable live at all.

COVERAGE, stated because it changes what can be claimed: the archive 404s before ~2020-07, so arm
(b) tests on 2021-2026, not 2019-2026. Any comparison that includes (b) is on the shorter span and
is reported as such rather than pooled with the (a) arms.
"""
import io, os, sys, time, urllib.request, zipfile, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r12_extract import SP

OUT = os.path.join(SP, 'r15b.npz')
URL = ('https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/'
       'BTCUSDT-metrics-%s.zip')
FUT = ['taker_ratio', 'taker_ratio_z', 'oi_chg_5m', 'oi_chg_1h']


def one(day):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(URL % day, timeout=120) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            out = []
            with z.open(z.namelist()[0]) as fh:
                for ln in io.TextIOWrapper(fh, 'utf-8'):
                    p = ln.rstrip('\n').split(',')
                    if p[0] == 'create_time' or len(p) < 8:
                        continue
                    try:
                        t = int(dt.datetime.strptime(p[0], '%Y-%m-%d %H:%M:%S')
                                .replace(tzinfo=dt.timezone.utc).timestamp())
                        out.append((t, float(p[2]), float(p[7])))
                    except Exception:
                        continue
            return out
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 2:
                return []
            time.sleep(2 ** attempt)
    return []


def main():
    days = []
    d = dt.date(2020, 7, 1)
    end = dt.date(2026, 9, 16)
    while d < end:
        days.append(d.isoformat())
        d += dt.timedelta(days=1)
    print('fetching %d daily metric files...' % len(days), flush=True)
    rows = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        for i, r in enumerate(ex.map(one, days)):
            rows.extend(r)
            if (i + 1) % 200 == 0:
                print('  %d/%d  %d bars  %.0fs' % (i + 1, len(days), len(rows), time.time() - t0),
                      flush=True)
    rows.sort()
    a = np.array(rows, np.float64)
    # de-duplicate on timestamp (daily files overlap at boundaries in places)
    _, keep = np.unique(a[:, 0], return_index=True)
    a = a[np.sort(keep)]
    t, oi, tr = a[:, 0], a[:, 1], a[:, 2]
    print('%d unique bars, %s .. %s' % (len(a),
          dt.datetime.utcfromtimestamp(t[0]), dt.datetime.utcfromtimestamp(t[-1])), flush=True)

    # gaps must not be bridged: a 5-min pct change across a 3-day hole is not a 5-min change
    step = np.diff(t, prepend=t[0] - 300)
    ok5 = step == 300
    prev_oi = np.concatenate([[np.nan], oi[:-1]])
    # A zero or missing prior open-interest makes the pct change meaningless, and dividing by a
    # floor instead of refusing produced a max of 1.2e14 on the first pass - one row that would have
    # dominated any split the learner made on this column. Refuse rather than floor.
    oi_chg5 = np.where(ok5 & (prev_oi > 0), (oi - prev_oi) / np.where(prev_oi > 0, prev_oi, 1),
                       np.nan)
    oi_chg1h = np.full(len(a), np.nan)
    for i in range(12, len(a)):
        if t[i] - t[i - 12] == 3600 and oi[i - 12] > 0:
            oi_chg1h[i] = oi[i] / oi[i - 12] - 1.0
    z = np.full(len(a), np.nan)
    for i in range(12, len(a)):
        if t[i] - t[i - 12] == 3600:
            w = tr[i - 12:i]
            s = w.std()
            z[i] = (tr[i] - w.mean()) / s if s > 1e-9 else 0.0
    F = np.column_stack([tr, z, oi_chg5, oi_chg1h]).astype(np.float32)
    np.savez_compressed(OUT, T=t.astype(np.int64), F=F, OI=oi, TR=tr)
    good = np.isfinite(F).all(1)
    print('saved %s  usable bars %d of %d' % (OUT, int(good.sum()), len(F)))
    for i, n in enumerate(FUT):
        c = F[good, i]
        print('  %-14s min %10.4f  p1 %9.4f  med %9.4f  p99 %9.4f  max %10.4f'
              % (n, c.min(), np.percentile(c, 1), np.median(c), np.percentile(c, 99), c.max()))


if __name__ == '__main__':
    main()
