#!/usr/bin/env python3
"""How many ms after a Binance move does the Polymarket ask move against us? READ-ONLY.

Source: the 2 h ms probe. Binance `bookTicker` mid vs the Polymarket BTC 5m best ask on the side the move
favours (BTC up -> the UP token).

CLOCK CHOICE, and it is not cosmetic: this comparison uses ONLY our local receive time. Binance's
`bookTicker` on the combined stream carries no event timestamp at all, and even where both venues stamp a
message the two clocks cannot be differenced - a "latency" built from two different clocks is fiction.
Local receive time is one clock, and it is also the clock our own engine actually lives on.

A move is counted when the mid differs from its value 1 s earlier by >= the threshold. A COOLDOWN of 1 s
per direction stops one sustained move being counted hundreds of times.

Reaction = the first moment the favoured side's best ask goes UP or the level is pulled (ask becomes None
or rises). That is the event that makes us late: the price we decided on is no longer there.
"""
import sqlite3, bisect, numpy as np

DB = '/home/ubuntu/pm_probe/ms_probe.sqlite3'
# V asked for 3/5/10 bps. This window turned out to be very quiet - total BTC range 30.2 bps over the
# whole 2 h and a MAXIMUM 1 s move of 5.24 bps - so 10 bps never happened and 5 bps barely did. The lower
# thresholds are added so there is a usable number at all; the specified three are still printed with
# their real n so the shortfall is visible rather than papered over.
THRESH_BPS = (0.5, 1, 2, 3, 5, 10)
LAG_NS = 1_000_000_000
COOLDOWN_NS = 1_000_000_000
HORIZON_NS = 5_000_000_000
BUCKETS = (50, 100, 200, 500)
OUR_PATH_MS = 230

c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
mk = list(c.execute('SELECT epoch,token_up,token_dn FROM markets ORDER BY epoch'))
tok = {}
for ep, up, dn in mk: tok[ep] = (up, dn)
eps = sorted(tok)

bn = np.array([(r[0], (r[1] + r[2]) / 2.0) for r in c.execute(
    'SELECT rx_ns,bid,ask FROM bn WHERE kind="book" AND bid IS NOT NULL AND ask IS NOT NULL ORDER BY rx_ns')],
    dtype=np.float64)
print(f'Binance bookTicker rows {len(bn)}  span {(bn[-1,0]-bn[0,0])/1e9/60:.1f} min')

top = {}
for tk in {t for pair in tok.values() for t in pair}:
    rows = c.execute('SELECT rx_ns,ask FROM pm_top WHERE token=? ORDER BY rx_ns', (tk,)).fetchall()
    if not rows: continue
    top[tk] = (np.array([r[0] for r in rows], dtype=np.float64),
               np.array([(r[1] if r[1] is not None else np.nan) for r in rows], dtype=np.float64))
print(f'tokens with a top-of-book series: {len(top)}')

def token_at(rx_ns, up):
    t = rx_ns / 1e9
    i = bisect.bisect_right(eps, int(t // 300 * 300)) - 1
    if i < 0: return None
    ep = eps[i]
    if not (ep <= t < ep + 300): return None
    return tok[ep][0 if up else 1]

def reaction(tk, rx0):
    """First moment the favoured side's best ask rises or is pulled. Returns ms, or None."""
    s = top.get(tk)
    if s is None: return None
    rxs, asks = s
    i = bisect.bisect_right(rxs, rx0)
    if i >= len(rxs): return None
    base = None
    for j in range(max(0, i - 1), -1, -1):
        if not np.isnan(asks[j]): base = asks[j]; break
    if base is None: return None
    for j in range(i, len(rxs)):
        if rxs[j] - rx0 > HORIZON_NS: return None
        a = asks[j]
        if np.isnan(a) or a > base + 1e-9: return (rxs[j] - rx0) / 1e6
    return None

rx = bn[:, 0]; mid = bn[:, 1]
print(f'\nreaction of the favoured side\'s best ask, local-receive ms, horizon {HORIZON_NS/1e9:.0f}s')
print(f'{"move":>6}{"events":>8}{"measured":>10}{"p10":>7}{"p50":>7}{"p90":>8}' +
      ''.join(f'{"<="+str(b)+"ms":>10}' for b in BUCKETS) + f'{"no react":>10}')
for th in THRESH_BPS:
    last = {1: -10**18, -1: -10**18}
    ev = []
    lo = 0
    for i in range(len(rx)):
        while rx[lo] < rx[i] - LAG_NS: lo += 1
        if lo == 0: continue
        ref = mid[lo - 1]
        if ref <= 0: continue
        d = 1e4 * (mid[i] / ref - 1)
        if abs(d) < th: continue
        dirn = 1 if d > 0 else -1
        if rx[i] - last[dirn] < COOLDOWN_NS: continue
        last[dirn] = rx[i]; ev.append((rx[i], dirn))
    out = []
    for rx0, dirn in ev:
        tk = token_at(rx0, dirn > 0)
        if tk is None: continue
        r = reaction(tk, rx0)
        out.append(r)
    got = np.array([x for x in out if x is not None], dtype=float)
    n_meas = len(got); n_try = len(out)
    if n_meas == 0:
        print(f'{th:>5}b{len(ev):>8}{0:>10}   (no events of this size in the window)'); continue
    mark = '' if n_meas >= 60 else '  INSUFFICIENT'
    print(f'{th:>5}b{len(ev):>8}{n_meas:>10}{np.percentile(got,10):>7.0f}{np.percentile(got,50):>7.0f}'
          f'{np.percentile(got,90):>8.0f}' +
          ''.join(f'{100*np.mean(got<=b):>9.1f}%' for b in BUCKETS) +
          f'{100*(1-n_meas/max(n_try,1)):>9.1f}%{mark}')
print(f'\nour order path is ~{OUR_PATH_MS} ms from seeing the book to being matched.')
