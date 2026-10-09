#!/usr/bin/env python3
"""Section 6: LEAD-LAG between the Chainlink settlement reference and Binance spot. READ-ONLY, master OFF.

Both series come from the engine's own 1 Hz tape (tape1s): ref_px is the venue's RTDS
crypto_prices_chainlink topic (poly_feeds.py:90-94), spot_px is Binance. 437k shared seconds.

Two things to keep in mind while reading every number below.
  OVERLAP. Using every second t makes the k-second windows overlap almost completely, so the correlations
  are unbiased but their effective sample size is nearer n/k than n. No p-values are quoted for that reason,
  and every correlation is reported a second time on a NON-OVERLAPPING subsample (every k-th second) so the
  reader can see how much of the precision is real.
  CADENCE. The two feeds do not tick alike: the reference is unchanged second-to-second on ~23% of seconds
  and Binance on ~44%. A 1 s return series made of that many zeros attenuates correlation toward zero on
  both sides, so small numbers here are a floor on the true relationship, not a ceiling.
"""
import sys, sqlite3, math, collections, datetime as dt, numpy as np

ARCH = '/home/ubuntu/pm_archive/zurich_research_archive.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
KS = (1, 2, 3, 5, 10, 20)
SECS = (20, 30, 45, 60)
f = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%m-%d %H:%M')


def series():
    rows = {}
    for src in (ARCH, LIVE):
        try:
            c = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
            for ts, s, r in c.execute('SELECT ts,spot_px,ref_px FROM tape1s '
                                      'WHERE spot_px IS NOT NULL AND ref_px IS NOT NULL'):
                rows[int(ts)] = (float(s), float(r))
        except Exception as e: print(f'  (source {src}: {e})')
    t0, t1 = min(rows), max(rows)
    n = t1 - t0 + 1
    B = np.full(n, np.nan); C = np.full(n, np.nan)
    for t, (s, r) in rows.items():
        B[t - t0] = s; C[t - t0] = r
    return t0, B, C


def corr(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30: return float('nan'), int(m.sum())
    x, y = a[m], b[m]
    if x.std() < 1e-15 or y.std() < 1e-15: return float('nan'), int(m.sum())
    return float(np.corrcoef(x, y)[0, 1]), int(m.sum())


def pcorr(x, y, z):
    """partial corr(x, y | z)"""
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if m.sum() < 30: return float('nan'), int(m.sum())
    x, y, z = x[m], y[m], z[m]
    rxy = np.corrcoef(x, y)[0, 1]; rxz = np.corrcoef(x, z)[0, 1]; ryz = np.corrcoef(y, z)[0, 1]
    d = math.sqrt(max((1 - rxz ** 2) * (1 - ryz ** 2), 1e-18))
    return float((rxy - rxz * ryz) / d), int(m.sum())


def ret(P, i, j):
    """log return from index-shift i to j, aligned on the ARRAY index (bps). ret(P,-k,0) is the past k s."""
    a = np.roll(P, -j); b = np.roll(P, -i)
    out = np.log(a / b) * 1e4
    n = len(P); bad = np.zeros(n, bool)
    for s in (i, j):
        if s < 0: bad[:abs(s)] = True
        elif s > 0: bad[n - s:] = True
    out[bad] = np.nan
    return out


if __name__ == '__main__':
    t0, B, C = series()
    ok = np.isfinite(B) & np.isfinite(C)
    print(f'tape {f(t0)} -> {f(t0+len(B)-1)}  slots {len(B)}  with both feeds {int(ok.sum())} '
          f'({100*ok.mean():.1f}%)')
    zb = np.mean(np.diff(B[ok]) == 0); zc = np.mean(np.diff(C[ok]) == 0)
    print(f'  unchanged second-to-second: binance {100*zb:.1f}%  chainlink {100*zc:.1f}%')

    print(f'\n{"="*104}\n1. WHO LEADS WHOM - corr(future k s of one, past k s of the other)\n{"="*104}')
    print(f'  {"k":>4}{"BIN leads CL":>15}{"(non-ovl)":>11}{"CL leads BIN":>15}{"(non-ovl)":>11}'
          f'{"n":>10}{"diff":>9}')
    for k in KS:
        fut_c = ret(C, 0, k); past_b = ret(B, -k, 0)
        fut_b = ret(B, 0, k); past_c = ret(C, -k, 0)
        a1, n1 = corr(fut_c, past_b)
        a2, _ = corr(fut_b, past_c)
        idx = np.zeros(len(B), bool); idx[::max(k, 1)] = True     # non-overlapping sample
        b1, _ = corr(np.where(idx, fut_c, np.nan), np.where(idx, past_b, np.nan))
        b2, _ = corr(np.where(idx, fut_b, np.nan), np.where(idx, past_c, np.nan))
        print(f'  {k:>4}{a1:>15.4f}{b1:>11.4f}{a2:>15.4f}{b2:>11.4f}{n1:>10}{a1-a2:>+9.4f}')
    print('  "BIN leads CL" = corr(chainlink return over [t,t+k], binance return over [t-k,t]).')
    print('  A positive diff means Binance moves first and the reference follows.')

    print(f'\n{"="*104}\n2. PARTIAL - does one feed add anything BEYOND the other feed\'s own recent move?\n{"="*104}')
    pb5 = ret(B, -5, 0); pc5 = ret(C, -5, 0)
    print(f'  {"horizon":>9}{"corr(BIN5, CL fwd)":>21}{"PARTIAL | CL5":>16}{"corr(CL5, BIN fwd)":>21}'
          f'{"PARTIAL | BIN5":>16}{"n":>9}')
    for h in (10, 30):
        fc = ret(C, 0, h); fb = ret(B, 0, h)
        r1, _ = corr(pb5, fc); p1, n1 = pcorr(pb5, fc, pc5)
        r2, _ = corr(pc5, fb); p2, _ = pcorr(pc5, fb, pb5)
        print(f'  {h:>7}s{r1:>21.4f}{p1:>16.4f}{r2:>21.4f}{p2:>16.4f}{n1:>9}')
    print('  PARTIAL | CL5 = the Binance term after removing what the reference\'s own last 5 s already says.')

    print(f'\n{"="*104}\n3. THE CANDLE VERSION - the two lines, and how often they point at different sides\n{"="*104}')
    print(f'  Binance move  = spot(ep+S) vs TWAP60 of spot over [ep-60, ep-1]')
    print(f'  Chainlink move = ref(ep+S)  vs TWAP60 of ref  over [ep-60, ep-1]   <- what the venue settles on')
    print(f'\n  {"S":>4}{"n":>7}{"corr(moves)":>14}{"sign disagree":>15}{"|BIN| bps p50":>15}'
          f'{"|CL| bps p50":>14}{"disagree |BIN| p50":>20}')
    eps = sorted({(t0 + i) // 300 * 300 for i in range(len(B)) if ok[i]})
    for S in SECS:
        mb, mc = [], []
        for ep in eps:
            i = ep - t0
            if i - 60 < 0 or i + S >= len(B): continue
            wb, wc = B[i - 60:i], C[i - 60:i]
            fb_, fc_ = np.isfinite(wb), np.isfinite(wc)
            # >=45 of the 60 line seconds present on both feeds - the same rule arb_5m_15m.py and
            # ef_chainlink_div.py already use for a TWAP60 line, so the convention is consistent across
            # the repo. Requiring all 60 drops the sample to 208 candles because the Binance column has
            # scattered single-second nulls (spot_px present on 91% of tape rows).
            if fb_.sum() < 45 or fc_.sum() < 45: continue
            if not (np.isfinite(B[i + S]) and np.isfinite(C[i + S])): continue
            lb, lc = wb[fb_].mean(), wc[fc_].mean()
            mb.append(math.log(B[i + S] / lb) * 1e4)
            mc.append(math.log(C[i + S] / lc) * 1e4)
        if len(mb) < 30: print(f'  {S:>4}{len(mb):>7}   too few'); continue
        mb = np.array(mb); mc = np.array(mc)
        dis = np.sign(mb) != np.sign(mc)
        print(f'  {S:>4}{len(mb):>7}{np.corrcoef(mb,mc)[0,1]:>14.4f}{100*dis.mean():>14.1f}%'
              f'{np.median(np.abs(mb)):>15.2f}{np.median(np.abs(mc)):>14.2f}'
              f'{(np.median(np.abs(mb[dis])) if dis.any() else float("nan")):>20.2f}')
    print('\n  The sign-disagreement rate is the ceiling on any settlement-reference edge: it is how often a')
    print('  Binance-derived view of the line points at the OTHER side from the line the venue actually pays on.')
