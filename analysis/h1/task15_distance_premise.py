"""Task 15 part 2 - does distance-from-open at the fire second predict which side the candle closes?

Tokyo's 250 fills say <1 bps at fire is a coin flip (51%) and 1-2.5 bps is 61%. That is 33 fills.
This asks the same question on 72,576 candles of real Binance 1s closes (252 days, 2026-01-01..09-09),
so we find out whether it is the market or one regime.

Buckets fixed in advance (V's, same as Task 14): |price(S) - open| in bps
  <1, 1-2.5, 2.5-5, 5-10, 10-25, 25+
Reported as the FULL grid over decision second, both halves, and per Task 13 regime. No chosen cell.
"""
import numpy as np

SP = '/tmp/claude-0/-home-user-Django-final-project/317e5c49-52d1-5b78-b008-462fcf4858cd/scratchpad'
EARLY = [15, 20, 30, 45, 60, 90, 120]
LATE = [237, 270, 290]
EDGES = [0, 1, 2.5, 5, 10, 25, np.inf]
LBL = ['<1', '1-2.5', '2.5-5', '5-10', '10-25', '25+']
MIN_N = 60


def load():
    d = np.load(f'{SP}/build/paths.npz')
    return d['cid'], d['paths'].astype(np.float64)


def grid(P, secs, sel=None, title=''):
    """P(close on the same side as price(S)) by |price(S)-open| bucket."""
    if sel is not None:
        P = P[sel]
    op, cl = P[:, 0], P[:, -1]
    close_up = cl >= op
    print()
    print(title + '   (n candles = %d)' % len(P))
    print('%-5s | ' % 'sec' + ' | '.join('%-13s' % l for l in LBL))
    print('%-5s | ' % '' + ' | '.join('%6s %6s' % ('n', 'P(same)') for _ in LBL))
    print('-' * (8 + 16 * len(LBL)))
    for S in secs:
        px = P[:, min(S, P.shape[1] - 1)]
        bps = np.abs(px - op) / op * 1e4
        lead_up = px >= op
        same = lead_up == close_up
        cells = []
        for i in range(len(LBL)):
            m = (bps >= EDGES[i]) & (bps < EDGES[i + 1])
            n = int(m.sum())
            cells.append('%6d %6s' % (n, ('%.3f' % same[m].mean()) if n >= MIN_N else '  --  '))
        print('%-5d | ' % S + ' | '.join(cells))


if __name__ == '__main__':
    cid, P = load()
    print('candles=%d  span=%s .. %s' % (len(cid), cid[0], cid[-1]))
    print('NOTE: P(same side) = P(candle closes on the side price(S) is already on).')
    print('      0.50 means the lead at second S tells you nothing about the close.')

    grid(P, EARLY, title='=== EARLY SECONDS, ALL 252 DAYS ===')
    grid(P, LATE, title='=== LATE SECONDS, ALL 252 DAYS ===')

    h = len(P) // 2
    grid(P, EARLY, sel=slice(0, h), title='=== EARLY, FIRST HALF ===')
    grid(P, EARLY, sel=slice(h, None), title='=== EARLY, SECOND HALF ===')
    grid(P, LATE, sel=slice(0, h), title='=== LATE, FIRST HALF ===')
    grid(P, LATE, sel=slice(h, None), title='=== LATE, SECOND HALF ===')

    # ---- Task 13 regime: trailing 12-candle realised range, quartiles from this set ----
    op, cl = P[:, 0], P[:, -1]
    hi = P.max(1); lo = P.min(1)
    rng_bps = (hi - lo) / op * 1e4
    trail = np.full(len(P), np.nan)
    csum = np.concatenate([[0.0], np.cumsum(rng_bps)])
    for i in range(12, len(P)):
        trail[i] = (csum[i] - csum[i - 12]) / 12.0
    ok = ~np.isnan(trail)
    qs = np.percentile(trail[ok], [25, 50, 75])
    print('\ntrailing 12-candle mean range quartiles (bps): %.1f / %.1f / %.1f' % tuple(qs))
    names = ['Q1 calmest', 'Q2', 'Q3', 'Q4 busiest']
    bounds = [-np.inf] + list(qs) + [np.inf]
    for qi in range(4):
        sel = ok & (trail >= bounds[qi]) & (trail < bounds[qi + 1])
        grid(P, [30, 60, 120, 237, 290], sel=sel,
             title='=== REGIME %s (trailing range %.1f-%.1f bps) ===' % (names[qi], bounds[qi] if qi else 0, bounds[qi + 1] if qi < 3 else 9999))
