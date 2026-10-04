#!/usr/bin/env python3
"""Owner question via V, READ-ONLY: after each probe fill, how far did OUR token trade DOWN before the
candle ended, and did the fills that fell furthest still recover and win?

Method, stated because every choice matters:
  fills     every GRADED probe fill (venue truth). The ungraded one is excluded, not guessed.
  window    [fill_ts, candle end) - strictly AFTER the fill, so our own fill print cannot be the
            minimum, and never past the candle, so nothing from the next market leaks in.
  prices    every trade print on OUR token on the public tape (tape_btc5). Both maker and taker rows
            are read: a trade has one price whichever side is recorded, and for a MINIMUM the
            duplicate is harmless. Taking the lowest price reached, as asked.
  drops     PERCENT of the fill price (0.78 -> 0.702/0.624/...) and, separately, PERCENTAGE POINTS
            (0.78 -> 0.68/0.58/...). The two differ most at the cheap end, which is where most of our
            fills are, so reporting only one would mislead.
  outcome   the venue's own resolution, already stored per fill.
"""
import sqlite3, datetime as dt

PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
TAPE = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
PCT = (10, 20, 30, 40, 50)
PTS = (0.10, 0.20, 0.30, 0.40, 0.50)

d = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); d.row_factory = sqlite3.Row
t = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
rows = [dict(r) for r in d.execute(
    'select f.epoch, f.fill_ts_ms, f.side, f.price, f.shares, f.outcome, f.pnl, o.token '
    'from fills f join orders o on o.id=f.order_row where f.pnl is not null order by f.fill_ts_ms')]
ungraded = d.execute('select count(*) from fills where pnl is null').fetchone()[0]

L = [__doc__.strip(), '']
recs = []
for r in rows:
    lo_row = t.execute('select price, ts from tape where asset=? and ts>=? and ts<? '
                       'order by price asc, ts asc limit 1',
                       (str(r['token']), r['fill_ts_ms'] / 1000.0, r['epoch'] + 300)).fetchone()
    lo = lo_row[0] if lo_row else None
    lo_sec = int(lo_row[1] - r['epoch']) if lo_row else None
    n = t.execute('select count(*) from tape where asset=? and ts>=? and ts<?',
                  (str(r['token']), r['fill_ts_ms'] / 1000.0, r['epoch'] + 300)).fetchone()[0]
    recs.append(dict(r, lo=(float(lo) if lo is not None else None), lo_sec=lo_sec, prints=n,
                     won=int(r['outcome'] == r['side'])))

L.append(f'GRADED FILLS {len(recs)} over {len({x["epoch"] for x in recs})} DISTINCT CANDLES '
         f'(several fills share a candle). Ungraded and excluded: {ungraded}.')
nop = [x for x in recs if x['lo'] is None]
if nop: L.append(f'  fills with NO tape print after the fill: {len(nop)} - excluded from the grids.')
use = [x for x in recs if x['lo'] is not None]
L.append(f'  usable: {len(use)} fills, {len({x["epoch"] for x in use})} candles.')

L += ['', 'PER FILL  (min after = the lowest price OUR token traded at between the fill and the candle end)',
      f'  {"time":14s} {"side":4s} {"price":>6s} {"min after":>10s} {"at sec":>7s} {"worst drop":>11s} '
      f'{"pts":>6s} {"prints":>7s} {"outcome":>8s}  result']
for x in use:
    drop = 100 * (x['price'] - x['lo']) / x['price']
    L.append(f'  {dt.datetime.fromtimestamp(x["fill_ts_ms"]/1000, dt.UTC):%m-%d %H:%M:%S} '
             f'{x["side"]:4s} {x["price"]:6.2f} {x["lo"]:10.2f} {x["lo_sec"]:7d} {drop:10.1f}% '
             f'{x["price"]-x["lo"]:6.2f} {x["prints"]:7d} {str(x["outcome"]):>8s}  '
             f'{"WON" if x["won"] else "LOST"}')

def grid(title, thresholds, label):
    out = ['', title, f'  {label:>14s} {"reached":>8s} {"recovered/WON":>14s} {"LOST":>6s} {"win% of those":>14s}']
    for th in thresholds:
        bar = (lambda px: px * (1 - th / 100)) if label == 'drop %' else (lambda px: px - th / 100)
        hit = [x for x in use if x['lo'] <= bar(x['price']) + 1e-9]
        w = sum(x['won'] for x in hit)
        wr = f'{100*w/len(hit):.1f}%' if hit else '-'
        shown = f'-{th}%' if label == 'drop %' else f'-{th/100:.2f}'
        out.append(f'  {shown:>14s} {len(hit):8d} {w:14d} {len(hit)-w:6d} {wr:>14s}')
    return out

L += grid('A. BY PERCENT OF THE FILL PRICE  (0.78 -> 0.702 / 0.624 / 0.546 / 0.468 / 0.39)', PCT, 'drop %')
L += grid('B. BY PERCENTAGE POINTS BELOW THE FILL PRICE  (0.78 -> 0.68 / 0.58 / 0.48 / 0.38 / 0.28)',
          [int(p * 100) for p in PTS], 'drop pts')

never = [x for x in use if x['lo'] > x['price'] * 0.9 + 1e-9]
w = sum(x['won'] for x in never)
L += ['', 'C. FILLS THAT NEVER DROPPED 10% OF THEIR PRICE',
      f'  n {len(never)}  WON {w}  LOST {len(never)-w}'
      + (f'  win% {100*w/len(never):.1f}%' if never else '')]
nev_pts = [x for x in use if x['lo'] > x['price'] - 0.10 + 1e-9]
w2 = sum(x['won'] for x in nev_pts)
L.append(f'  and never dropped 10 POINTS: n {len(nev_pts)}  WON {w2}  LOST {len(nev_pts)-w2}'
         + (f'  win% {100*w2/len(nev_pts):.1f}%' if nev_pts else ''))
deep = [x for x in use if x['lo'] <= x['price'] * 0.5 + 1e-9]
late = [x for x in deep if x['lo_sec'] >= 270]
L += ['', 'D. WHEN DID THE DEEP DROPS HAPPEN? (the -50% bucket, by the second the minimum printed)',
      f'  of {len(deep)} fills that halved, {len(late)} printed their minimum at sec >= 270, i.e. in the',
      '  last 30 s of the candle - that is the market RESOLVING, not a dip that recovered. A drop to',
      '  0.00 at second 299 on a losing side is the settlement arriving, and counting it as a',
      '  "drawdown that recovered" would be reading the resolution as volatility.',
      f'  minima at sec < 270 (genuine intra-candle dips): {len(deep)-len(late)}']
L += ['', 'READ THIS WITH THE SAMPLE IN MIND: 43 graded fills over 24 candles, and the deepest buckets',
      'hold only a handful of fills each - a 100% recovery rate on 3 fills is not a 100% recovery rate.',
      'Fills also cluster: 15 of them sit in the single 17:00 candle of 09-30, so the effective number of',
      'independent observations is nearer 24 than 43.']
open('/home/ubuntu/claude-work/repo/analysis/zurich/MAKER_DRAWDOWN.txt', 'w').write('\n'.join(L) + '\n')
print('\n'.join(L[-40:]))
