#!/usr/bin/env python3
"""How long do the shares at the best ask actually live? READ-ONLY.

The owner's question, verbatim: "we saw shares at 0.30 in the book, sent an order, and it was rejected.
How long were those shares actually available, and how fast did they disappear?"

Source: the 2 h ms probe (/home/ubuntu/pm_probe/ms_probe.sqlite3), BTC 5m tokens, every book / price_change
message with the venue's own timestamp and our local receive time.

Two clocks, used for different things on purpose:
  - durations WITHIN the venue's stream (how long a level lived) use the venue's `timestamp`, because
    every one of those messages comes off the same clock;
  - anything comparing Binance to Polymarket uses our local receive time, because the two venues'
    clocks cannot be differenced. That separation is the whole reason both are logged.

Two lifetimes are reported because the owner's sentence contains both:
  LEVEL  the best-ask PRICE, from becoming best ask to no longer being best ask (or its size hitting 0)
  SIZE   the specific (price, size) offering, from when that size appears to the first change in it -
         "how long were THOSE shares there", which is what a rejected order actually cared about.

Ending is classified TAKEN if a last_trade_price for that token at that price lands within
TRADE_WINDOW_MS of the end, else CANCELLED. Split by whether the candle settled the token's way, using
the venue's own resolution (settlement rule, CLAUDE.md f21fbfa).
"""
import sqlite3, collections, numpy as np

DB = '/home/ubuntu/pm_probe/ms_probe.sqlite3'
TRADE_WINDOW_MS = 100
BUCKETS = (50, 100, 200, 250, 500)
OUR_PATH_MS = 230          # London: seeing the book -> our order matched, ~230-250 ms

c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
side_of, epoch_of = {}, {}
for ep, up, dn in c.execute('SELECT epoch,token_up,token_dn FROM markets'):
    side_of[up] = 'UP'; side_of[dn] = 'DOWN'; epoch_of[up] = ep; epoch_of[dn] = ep
res = dict(c.execute('SELECT epoch,outcome FROM resolutions'))

trades = collections.defaultdict(list)
for tk, ev, px in c.execute('SELECT token,ev_ms,price FROM pm_trade WHERE price IS NOT NULL ORDER BY ev_ms'):
    trades[tk].append((ev, round(float(px), 4)))

def taken(tk, ev_end, price):
    for ev, px in reversed(trades.get(tk, [])):
        if ev < ev_end - TRADE_WINDOW_MS: break
        if ev <= ev_end + TRADE_WINDOW_MS and abs(px - price) < 1e-6: return True
    return False

lvl, siz = [], []
cur = {}
n_rows = 0
for rx, ev, tk, kind, ask, asz, bid, bsz in c.execute(
        'SELECT rx_ns,ev_ms,token,kind,ask,ask_sz,bid,bid_sz FROM pm_top ORDER BY token, rx_ns'):
    n_rows += 1
    st = cur.get(tk)
    if ask is None:
        if st: lvl.append((tk, st['p'], st['ev0'], ev, st['rx0'], rx, st['sz0'], 'vanished'))
        cur.pop(tk, None); continue
    if st is None or st['p'] != ask:
        if st: lvl.append((tk, st['p'], st['ev0'], ev, st['rx0'], rx, st['sz0'], 'moved'))
        cur[tk] = dict(p=ask, ev0=ev, rx0=rx, sz0=asz, sev0=ev, srx0=rx, sz=asz)
        continue
    if asz != st['sz']:
        siz.append((tk, st['p'], st['sev0'], ev, st['srx0'], rx, st['sz'], asz))
        st['sev0'] = ev; st['srx0'] = rx; st['sz'] = asz
for tk, st in cur.items():
    pass   # open at the end of the capture: dropped, they have no measured end

def pct(a, q): return float(np.percentile(a, q)) if len(a) else float('nan')

def block(title, rows, dur_idx, rx0i, rx1i, ev0i, ev1i, price_i, tk_i, end_ev_i, tag):
    d_ev = np.array([r[ev1i] - r[ev0i] for r in rows], float)
    d_rx = np.array([(r[rx1i] - r[rx0i]) / 1e6 for r in rows], float)
    ok = (d_ev >= 0) & (d_rx >= 0)
    d_ev, d_rx = d_ev[ok], d_rx[ok]
    keep = [r for r, k in zip(rows, ok) if k]
    print(f'\n{title}: n {len(keep)}')
    print(f'  venue-clock ms   p10 {pct(d_ev,10):7.0f}  p50 {pct(d_ev,50):7.0f}  p90 {pct(d_ev,90):8.0f}  mean {d_ev.mean():8.0f}')
    print(f'  local-rx    ms   p10 {pct(d_rx,10):7.0f}  p50 {pct(d_rx,50):7.0f}  p90 {pct(d_rx,90):8.0f}  mean {d_rx.mean():8.0f}')
    print('  gone within: ' + '  '.join(f'{b}ms {100*np.mean(d_ev<=b):5.1f}%' for b in BUCKETS))
    print(f'  our order path is ~{OUR_PATH_MS} ms: {100*np.mean(d_ev<=OUR_PATH_MS):.1f}% of these are '
          f'already gone before we could be matched')
    return keep, d_ev

print(f'ms probe: {n_rows} top-of-book rows, {len(side_of)} tokens, {len(res)} settled epochs')
print(f'best-ask LEVEL episodes {len(lvl)} | (price,size) SIZE episodes {len(siz)}')

keep, d_ev = block('LEVEL — best-ask price, until it is no longer the best ask', lvl,
                   None, 4, 5, 2, 3, 1, 0, 3, 'level')
print('\n  ENDING (taken by a trade at that price within ±100 ms vs cancelled):')
tk_taken = np.array([taken(r[0], r[3], r[1]) for r in keep])
for lab, m in (('TAKEN by a trade', tk_taken), ('CANCELLED (no trade)', ~tk_taken)):
    if m.sum() == 0: continue
    dd = d_ev[m]
    print(f'    {lab:22s} n {m.sum():7d} ({100*m.mean():4.1f}%)  p50 {pct(dd,50):6.0f} ms  '
          + '  '.join(f'<={b}ms {100*np.mean(dd<=b):4.1f}%' for b in (50, 100, 250)))

print('\n  BY WHETHER THE CANDLE SETTLED THAT WAY (venue resolution):')
went = np.array([1 if res.get(epoch_of.get(r[0])) == side_of.get(r[0]) else
                 (0 if epoch_of.get(r[0]) in res else -1) for r in keep])
for lab, m in (('candle went that way', went == 1), ('candle went the other way', went == 0),
               ('unsettled in the window', went == -1)):
    if m.sum() == 0: continue
    dd = d_ev[m]; tt = tk_taken[m]
    print(f'    {lab:26s} n {m.sum():7d}  p50 {pct(dd,50):6.0f} ms  <=250ms {100*np.mean(dd<=250):4.1f}%  '
          f'taken {100*tt.mean():4.1f}%')

block('SIZE — the specific (price,size) offering, until that size changes IN ANY DIRECTION', siz,
      None, 4, 5, 2, 3, 1, 0, 3, 'size')
grew = np.array([r[7] > r[6] for r in siz])
print(f'  CAVEAT: {100*grew.mean():.1f}% of those endings were the size GROWING, not disappearing, so')
print('  "any change" OVERSTATES how fast the shares go away. The adverse subset is the real answer:')
adverse = [r for r in siz if r[7] < r[6]]
block('SIZE (ADVERSE ONLY) — until the size SHRINKS or goes to zero', adverse,
      None, 4, 5, 2, 3, 1, 0, 3, 'size_adv')
