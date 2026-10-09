#!/usr/bin/env python3
"""Owner question via V, READ-ONLY, mirror of MAKER_DRAWDOWN: how high did our token trade AFTER each
fill, and would taking profit at 0.80 / 0.85 / 0.90 / 0.95 have beaten holding to settlement?

Same method as the drawdown study: the 43 GRADED fills, our token's prints strictly after the fill and
strictly before the candle end, so neither our own fill nor the next market can contaminate it.

TWO PRICE SERIES, because V asked for the bid side if it exists and it partly does:
  ALL PRINTS      every trade on our token. An UPPER BOUND on what we could have sold at - a trade
                  happening at 0.90 does not prove anyone was BIDDING 0.90 for our shares.
  MAKER-BUY ONLY  prints where the resting side was a BUY, i.e. a bid at that price was actually hit.
                  That is near-direct evidence we could have sold there, and it is the honest number.
Both are reported for every level. Where they disagree, the maker-BUY column is the one to believe.

SHARES: V wrote "sell 5 shares", but our fills are not all 5 - there are partials of 0.01, 1.53, 2.08,
2.92 and 4.996 shares. Selling 5 where we hold 0.01 would invent a position, so each fill is sold at
ITS OWN size and that is stated rather than rounded away.
NO SELL FEE IS CHARGED in the take-profit figure. A real exit would cross the spread and pay the taker
fee, so every take-profit number here is optimistic - another reason to read it as a ceiling.
"""
import sqlite3, datetime as dt

PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
TAPE = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
LEVELS = (0.80, 0.85, 0.90, 0.95)
BIG_CANDLE = 1790787600          # 09-30 17:00, which holds 15 of the 43 fills

d = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); d.row_factory = sqlite3.Row
t = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
fills = [dict(r) for r in d.execute(
    'select f.epoch, f.fill_ts_ms, f.side, f.price, f.shares, f.outcome, f.pnl, o.token '
    'from fills f join orders o on o.id=f.order_row where f.pnl is not null order by f.fill_ts_ms')]

def hi(tok, t0, t1, bid_only):
    sql = ('select price, ts from tape where asset=? and ts>=? and ts<? '
           + ("and is_taker=0 and side='BUY' " if bid_only else '')
           + 'order by price desc, ts asc limit 1')
    r = t.execute(sql, (str(tok), t0, t1)).fetchone()
    return (float(r[0]), r[1]) if r else (None, None)

def first_at(tok, t0, t1, lvl, bid_only):
    sql = ('select ts from tape where asset=? and ts>=? and ts<? and price>=? '
           + ("and is_taker=0 and side='BUY' " if bid_only else '')
           + 'order by ts asc limit 1')
    r = t.execute(sql, (str(tok), t0, t1, lvl - 1e-9)).fetchone()
    return r[0] if r else None

for x in fills:
    t0, t1 = x['fill_ts_ms'] / 1000.0, x['epoch'] + 300
    x['hi'], x['hi_ts'] = hi(x['token'], t0, t1, False)
    x['hib'], x['hib_ts'] = hi(x['token'], t0, t1, True)
    x['won'] = int(x['outcome'] == x['side'])

L = [__doc__.strip(), '']
L.append(f'GRADED FILLS {len(fills)} over {len({x["epoch"] for x in fills})} distinct candles.')
L += ['', 'PER FILL - highest price reached after the fill, and the second it printed',
      f'  {"time":14s} {"side":4s} {"price":>6s} {"shares":>7s} {"max all":>8s} {"sec":>5s} '
      f'{"max bid":>8s} {"sec":>5s} {"outcome":>8s}  result']
for x in fills:
    f = lambda v, s: (f'{v:8.2f} {int(s-x["epoch"]):5d}' if v is not None else f'{"-":>8s} {"-":>5s}')
    L.append(f'  {dt.datetime.fromtimestamp(x["fill_ts_ms"]/1000, dt.UTC):%m-%d %H:%M:%S} '
             f'{x["side"]:4s} {x["price"]:6.2f} {x["shares"]:7.3f} {f(x["hi"], x["hi_ts"])} '
             f'{f(x["hib"], x["hib_ts"])} {str(x["outcome"]):>8s}  {"WON" if x["won"] else "LOST"}')

def grid(sel, title):
    out = ['', title, f'  n={len(sel)} fills over {len({x["epoch"] for x in sel})} candles',
           f'  {"level":>6s} {"src":>9s} {"already>=":>10s} {"reached":>8s} {"W":>4s} {"L":>4s} '
           f'{"TP pnl":>9s} {"HOLD pnl":>9s} {"diff":>9s}']
    for lvl in LEVELS:
        already = [x for x in sel if x['price'] >= lvl - 1e-9]
        cand = [x for x in sel if x['price'] < lvl - 1e-9]
        for src, key in (('all', 'hi'), ('maker-bid', 'hib')):
            hit = [x for x in cand if x[key] is not None and x[key] >= lvl - 1e-9]
            w = sum(x['won'] for x in hit)
            tp = sum(x['shares'] * (lvl - x['price']) for x in hit)
            hold = sum(x['pnl'] for x in hit)
            out.append(f'  {lvl:6.2f} {src:>9s} {len(already):10d} {len(hit):8d} {w:4d} {len(hit)-w:4d} '
                       f'{tp:+9.2f} {hold:+9.2f} {tp-hold:+9.2f}')
    if any(x['price'] >= LEVELS[0] - 1e-9 for x in sel):
        out.append('  fills ALREADY at or above a level are excluded from "reached" for that level, as asked;')
        out.append('  they are counted in the already>= column and cannot be a take-profit at it.')
    return out

L += grid(fills, f'A. ALL {len(fills)} GRADED FILLS')   # computed: the count moves as fills settle
sub = [x for x in fills if x['epoch'] != BIG_CANDLE]
nbig = sum(1 for x in fills if x['epoch'] == BIG_CANDLE)
L += grid(sub, f'B. EXCLUDING THE 09-30 17:00 CANDLE (it holds {nbig} of the {len(fills)} fills)')
open('/tmp/tp_block.txt', 'w').write('\n'.join(L) + '\n')
print('\n'.join(L[-34:]))
