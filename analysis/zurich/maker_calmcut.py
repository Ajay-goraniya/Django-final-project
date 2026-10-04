#!/usr/bin/env python3
"""READ-ONLY: the owner's three questions on the maker probe. Nothing is written to any probe db.

(1) integrity of the 8 fills in 22:33-23:34, (2) their market context, (3) a calm-cut grid over
EVERY graded fill using the vol LOGGED AT POST TIME - never a vol recomputed now, which would be a
different number from the one the gate actually saw.
"""
import sqlite3, datetime as dt

DB    = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
GAMMA = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
A = int(dt.datetime(2026, 10, 1, 22, 33, tzinfo=dt.UTC).timestamp() * 1000)
B = int(dt.datetime(2026, 10, 1, 23, 34, tzinfo=dt.UTC).timestamp() * 1000)
CUTS  = [0.304, 0.28, 0.25, 0.22, 0.20, 0.15]
CHURN = 1790787600            # 09-30 17:00 UTC
BAND  = (0.60, 0.80)
SEC   = (60, 180)
U = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.UTC)

d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); d.row_factory = sqlite3.Row
g = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)

def post_row(f):
    """The decisions row that ACTUALLY posted this fill's order: same epoch and price, action post,
    nearest the order's post_ts_ms. Matching on epoch alone would pick a different post in a candle
    that posted more than once, and that is exactly where sec and vol differ."""
    o = d.execute('select post_ts_ms, side, price from orders where id=?', (f['order_row'],)).fetchone()
    if not o: return None, None
    cand = d.execute("select * from decisions where epoch=? and action='post' and abs(price-?)<1e-9 "
                     "order by abs(ts_ms-?) limit 1", (f['epoch'], o['price'], o['post_ts_ms'])).fetchone()
    return o, cand

fills = [dict(r) for r in d.execute('select * from fills order by fill_ts_ms')]
for f in fills:
    o, p = post_row(f)
    f['o_side'] = o['side'] if o else None
    f['o_price'] = o['price'] if o else None
    f['sec'] = p['sec'] if p else None
    f['vol'] = p['vol'] if p else None
    f['adv_at_post'] = p['adverse'] if p else None
    r = g.execute('select outcome from mkt where epoch=?', (f['epoch'],)).fetchone()
    f['gamma'] = r[0] if r else None

win = [f for f in fills if f['fill_ts_ms'] >= A and f['fill_ts_ms'] < B]
L = [f'MAKER PROBE - owner questions, READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC',
     f'fills in db {len(fills)}, graded {sum(1 for f in fills if f["pnl"] is not None)}', '']

# ---- (1) BROKEN? --------------------------------------------------------------------------------
L += ['(1) INTEGRITY OF THE 8 FILLS 22:33-23:34 UTC', f'  fills in the window: {len(win)}']
checks = []
checks.append(('fill side == intended side',
               [f for f in win if f['side'] != f['o_side']]))
checks.append((f'price inside {BAND[0]}-{BAND[1]}',
               [f for f in win if not (BAND[0] - 1e-9 <= f['price'] <= BAND[1] + 1e-9)]))
checks.append(('fill price == posted price',
               [f for f in win if f['o_price'] is None or abs(f['price'] - f['o_price']) > 1e-9]))
checks.append((f'sec inside {SEC[0]}-{SEC[1]} at post',
               [f for f in win if f['sec'] is None or not (SEC[0] <= f['sec'] <= SEC[1])]))
checks.append(('calm vol < 0.304 at post',
               [f for f in win if f['vol'] is None or f['vol'] >= 0.304]))
checks.append(('graded on venue truth (gamma outcome == fills.outcome)',
               [f for f in win if f['outcome'] != f['gamma']]))
checks.append(('pnl arithmetic = shares*(1-price) win / -shares*price loss',
               [f for f in win if f['pnl'] is None or abs(f['pnl'] - (f['shares'] * (1 - f['price'])
                if f['outcome'] == f['side'] else -f['shares'] * f['price'])) > 1e-6]))
for name, bad in checks:
    L.append(f'  {"OK  " if not bad else "BAD "} {name}'
             + ('' if not bad else f'  -> {[f["id"] for f in bad]}'))
# the 2 bps cancel, which is an ORDERS question, not a fills one
adv_c = d.execute("select count(*) from orders where dry=0 and cancel_reason like '%adverse%'").fetchone()[0]
adv_w = d.execute("select count(*) from orders where dry=0 and cancel_reason like '%adverse%' "
                  "and post_ts_ms>=? and post_ts_ms<?", (A, B)).fetchone()[0]
sec_c = d.execute("select count(*) from orders where dry=0 and cancel_reason like '%sec %'").fetchone()[0]
held = [f for f in win if f['bn_before_bps'] is not None and f['bn_before_bps'] >= 2.0]
L += [f'  2bps cancel: {adv_c} adverse-cancels lifetime, {adv_w} in the window; '
      f'{sec_c} window-exit cancels lifetime',
      f'  fills whose own bn_before >= 2bps (filled before the cancel could land): {len(held)}'
      f'{" -> " + str([f["id"] for f in held]) if held else ""}',
      f'  bn_before present on {sum(1 for f in win if f["bn_before_bps"] is not None)}/{len(win)}, '
      f'bn_after on {sum(1 for f in win if f["bn_after_bps"] is not None)}/{len(win)}', '']

# ---- (2) MARKET? -------------------------------------------------------------------------------
L += ['(2) PER-FILL MARKET CONTEXT, same 8 fills',
      f'  {"id":>4s} {"time UTC":19s} {"side":4s} {"px":>5s} {"sec":>4s} {"vol@post":>9s} '
      f'{"bn_before":>10s} {"bn_after":>9s} {"out":4s} {"pnl":>8s}']
for f in win:
    L.append(f'  {f["id"]:4d} {U(f["fill_ts_ms"]):%F %T} {f["side"]:4s} {f["price"]:5.2f} '
             f'{f["sec"] if f["sec"] is not None else -1:4d} '
             f'{f["vol"] if f["vol"] is not None else float("nan"):9.3f} '
             f'{f["bn_before_bps"] if f["bn_before_bps"] is not None else float("nan"):10.2f} '
             f'{f["bn_after_bps"] if f["bn_after_bps"] is not None else float("nan"):9.2f} '
             f'{f["outcome"] or "-":4s} {f["pnl"]:+8.4f}')
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float('nan')
W = [f for f in win if f['pnl'] > 0]; Lo = [f for f in win if f['pnl'] < 0]
L += ['', f'  winners n {len(W)}: mean vol {mean([f["vol"] for f in W]):.3f}  mean sec '
          f'{mean([f["sec"] for f in W]):.0f}  mean px {mean([f["price"] for f in W]):.3f}  '
          f'mean bn_before {mean([f["bn_before_bps"] for f in W]):+.2f}  '
          f'mean bn_after {mean([f["bn_after_bps"] for f in W]):+.2f}',
      f'  losers  n {len(Lo)}: mean vol {mean([f["vol"] for f in Lo]):.3f}  mean sec '
          f'{mean([f["sec"] for f in Lo]):.0f}  mean px {mean([f["price"] for f in Lo]):.3f}  '
          f'mean bn_before {mean([f["bn_before_bps"] for f in Lo]):+.2f}  '
          f'mean bn_after {mean([f["bn_after_bps"] for f in Lo]):+.2f}',
      f'  ranges: winners vol {min([f["vol"] for f in W], default=0):.3f}-'
          f'{max([f["vol"] for f in W], default=0):.3f} px {min([f["price"] for f in W], default=0):.2f}-'
          f'{max([f["price"] for f in W], default=0):.2f} | losers vol '
          f'{min([f["vol"] for f in Lo], default=0):.3f}-{max([f["vol"] for f in Lo], default=0):.3f} '
          f'px {min([f["price"] for f in Lo], default=0):.2f}-{max([f["price"] for f in Lo], default=0):.2f}',
      '  n is 8. Nothing here is a finding; it is a description of eight candles.', '']

# ---- (3) CALM CUT GRID -------------------------------------------------------------------------
gr = [f for f in fills if f['pnl'] is not None]
no_vol = [f for f in gr if f['vol'] is None]
usable = [f for f in gr if f['vol'] is not None]
gr_t = sorted(usable, key=lambda f: f['fill_ts_ms'])
k = (len(gr_t) + 1) // 2
SETS = [('ALL graded', gr_t),
        ('H1 (first half by time)', gr_t[:k]),
        ('H2 (second half by time)', gr_t[k:]),
        ('ALL excluding 09-30 17:00', [f for f in gr_t if f['epoch'] != CHURN])]
L += ['(3) STRICTER CALM GATE - vol as LOGGED AT POST, every graded fill',
      f'  graded fills {len(gr)}; vol@post recoverable on {len(usable)}; '
      f'{len(no_vol)} have no matching post row and are EXCLUDED from this grid rather than '
      f'assumed calm' + (f' (ids {[f["id"] for f in no_vol][:12]}...)' if no_vol else '')]
for name, rows in SETS:
    L += ['', f'  {name}  (n {len(rows)})',
          f'    {"cut":>6s} {"fills":>6s} {"candles":>8s} {"W/L":>8s} {"deployed":>9s} {"pnl":>9s} '
          f'{"pnl/$1":>8s} {"kept%":>6s}']
    for c in CUTS:
        s = [f for f in rows if f['vol'] < c]
        w = sum(1 for f in s if f['pnl'] > 0); l = sum(1 for f in s if f['pnl'] < 0)
        dep = sum(f['spent'] for f in s); pnl = sum(f['pnl'] for f in s)
        L.append(f'    {c:6.3f} {len(s):6d} {len({f["epoch"] for f in s}):8d} {f"{w}/{l}":>8s} '
                 f'{dep:9.2f} {pnl:+9.4f} {pnl/max(dep,1e-9):+8.4f} '
                 f'{100*len(s)/max(len(rows),1):5.0f}%')
L += ['', '  WHAT EACH CUT REMOVES FROM THE 8-FILL WINDOW (5 losers, 3 winners)',
      f'    {"cut":>6s} {"losers removed":>15s} {"winners removed":>16s} {"left":>6s} {"left pnl":>9s}']
for c in CUTS:
    rl = [f for f in Lo if f['vol'] is None or f['vol'] >= c]
    rw = [f for f in W if f['vol'] is None or f['vol'] >= c]
    kept = [f for f in win if f['vol'] is not None and f['vol'] < c]
    L.append(f'    {c:6.3f} {f"{len(rl)} of {len(Lo)}":>15s} {f"{len(rw)} of {len(W)}":>16s} '
             f'{len(kept):6d} {sum(f["pnl"] for f in kept):+9.4f}')
L += ['', '  Read it as a sweep, not a pick: a cut that helps one of these four sets and not the',
      '  others, or that is non-monotone across the six values, is noise. Every cell below 60 fills',
      '  is INSUFFICIENT by the standing rule, and nothing here changes the probe.']
print('\n'.join(L))
