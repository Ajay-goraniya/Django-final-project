"""R-15 -- the HTF block on the LOGGED Polymarket window, so the candidate can be paired against
frozen v10 on the same candles the engine actually traded.

Same builder as r15_extract.py, fed daily 1 s klines instead of monthly ones. Each day is primed with
the PREVIOUS day so the 4 h lookback is real history rather than a zero-fill; without priming the
first four hours of every day would be dropped, which is 17%% of the window and not a random 17%%
(it is always the same hours of the day).
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r12_parity as P
import r15_extract as E
from r12_extract import SP, to_sec

CACHE = os.path.join(SP, 'r15_live.npz')


def build_days(days, secs=None):
    """{(epoch, sec): htf vector} over the given UTC days."""
    if secs is not None:
        E.SECS = list(secs)
    if os.path.exists(CACHE):
        d = np.load(CACHE)
        return {(int(k[0]), int(k[1])): v for v, k in zip(d['H'], d['K'])}
    import datetime as dt
    Hs, Ks = [], []
    for day in days:
        prev = (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
        try:
            a = P.daily(day)
        except Exception as e:
            print('  no daily file for %s (%s)' % (day, e), flush=True)
            continue
        first = int(to_sec(a[:, 0])[0])
        try:
            pr = P.daily(prev)
            a = np.vstack([pr, a])
        except Exception:
            print('  no prime for %s - its first 4h will be dropped' % day, flush=True)
        g = E.grid(a[:, :3])
        del a
        if g is None:
            continue
        r = E.build(g[0], g[1], g[2], first)
        del g
        if r is None:
            continue
        Hs.append(r[0]); Ks.append(r[1])
        print('  %s  %d rows' % (day, len(r[0])), flush=True)
    H, K = np.vstack(Hs), np.vstack(Ks)
    np.savez_compressed(CACHE, H=H, K=K)
    return {(int(k[0]), int(k[1])): v for v, k in zip(H, K)}


if __name__ == '__main__':
    import task_r8_taker_feature as R8
    import r12_train as T
    L = T.lane_ticks(R8.oracle())
    days = sorted({r['day'] for r in L})
    print('logged days:', days)
    m = build_days(days, secs=range(15, 241))
    print('HTF rows on the logged window:', len(m))
