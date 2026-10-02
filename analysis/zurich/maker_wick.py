#!/usr/bin/env python3
"""READ-ONLY: the owner's "we lost in wicks" hypothesis. Nothing is written to any probe db.

Universe: every GRADED fill that has a venue-timed window, i.e. both bn_before_bps and
bn_after_bps present. Fills without it are not counted as zero - they are excluded and said so.
Binance series: the engine's own bn_flow spot 1 s feed, forward-filled exactly as
poly_fav.FavBrain._series() does, so these bps are on the same series the probe's 2 bps rule uses.
"""
import math, sqlite3, datetime as dt

DB    = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
BN    = '/home/ubuntu/pm_multi/bn_flow.sqlite3'
TAPE  = '/home/ubuntu/pm_ef3/tape_btc5.sqlite3'
GAMMA = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
FF_MAX_S = 10
A_BUCKETS = [(None, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.0)]
B_BUCKETS = [(None, 5.0), (5.0, 10.0), (10.0, 20.0), (20.0, None)]
BAR = 60
U = lambda s: dt.datetime.fromtimestamp(s, dt.UTC).strftime('%F %T')

d = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); d.row_factory = sqlite3.Row
bn = sqlite3.connect(f'file:{BN}?mode=ro', uri=True)
tp = sqlite3.connect(f'file:{TAPE}?mode=ro', uri=True)
gm = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)

def series(a, b):
    """1 s spot prices on [a,b], forward-filled up to FF_MAX_S - FavBrain's construction."""
    raw = {}
    for tms, px in bn.execute("SELECT ts_ms,px FROM flow WHERE stream='spot' AND px IS NOT NULL "
                              "AND ts_ms>=? AND ts_ms<=?", ((a - 5) * 1000, (b + 5) * 1000)):
        raw[int(tms) // 1000] = float(px)
    if not raw: return {}
    out, last, held = {}, None, 0
    for t in range(min(raw), max(raw) + 1):
        if t in raw: last, held = raw[t], 0
        else:
            held += 1
            if held > FF_MAX_S: continue
        if last is not None: out[t] = last
    return out

fills = [dict(r) for r in d.execute(
    'select * from fills where pnl is not null and bn_before_bps is not null '
    'and bn_after_bps is not null order by fill_ts_ms')]
all_graded = d.execute('select count(*) from fills where pnl is not null').fetchone()[0]

for f in fills:
    o = d.execute('select token, post_ts_ms from orders where id=?', (f['order_row'],)).fetchone()
    f['token'] = o['token'] if o else None
    ep, fs = f['epoch'], f['fill_ts_ms'] // 1000
    px = series(ep - 70, ep + 310)
    f['px'] = px
    p0 = px.get(fs) or px.get(fs + 1) or px.get(fs - 1)
    sign = +1 if f['side'] == 'UP' else -1          # UP buy is hurt by a FALL
    worst = None
    for t in range(fs, ep + 301):
        if t not in px or p0 is None: continue
        adv = -sign * (px[t] - p0) / p0 * 1e4       # positive = against us
        worst = adv if worst is None else max(worst, adv)
    f['max_adv'] = worst
    f['p0'] = p0
    # TWAP60 proxy on the same series: open = [ep-60,ep), close = [ep+240,ep+300)
    ow = [px[t] for t in range(ep - 60, ep) if t in px]
    cw = [px[t] for t in range(ep + 240, ep + 300) if t in px]
    f['twap_open'] = sum(ow) / len(ow) if len(ow) >= 30 else None
    f['twap_close'] = sum(cw) / len(cw) if len(cw) >= 30 else None
    f['px240'] = px.get(ep + 240)
    g = gm.execute('select outcome from mkt where epoch=?', (ep,)).fetchone()
    f['gamma'] = g[0] if g else None

def cell(rows):
    w = sum(1 for x in rows if x['pnl'] > 0); l = sum(1 for x in rows if x['pnl'] < 0)
    return len(rows), w, l, sum(x['spent'] for x in rows), sum(x['pnl'] for x in rows)

def grid(title, key, buckets, fmt='{:.1f}'):
    out = [title, f'    {"bucket":>12s} {"n":>4s} {"W/L":>7s} {"deployed":>9s} {"pnl":>9s} '
                  f'{"pnl/$1":>8s}  flag']
    seen = []
    for lo, hi in buckets:
        sel = [x for x in rows_for(key) if in_bucket(x[key], lo, hi)]
        seen += sel
        n, w, l, dep, pnl = cell(sel)
        lbl = (f'<{fmt.format(hi)}' if lo is None else
               f'>={fmt.format(lo)}' if hi is None else f'{fmt.format(lo)}-{fmt.format(hi)}')
        out.append(f'    {lbl:>12s} {n:4d} {f"{w}/{l}":>7s} {dep:9.2f} {pnl:+9.4f} '
                   f'{pnl/max(dep,1e-9):+8.4f}  {"INSUFFICIENT (<60)" if n < BAR else ""}')
    left = [x for x in rows_for(key) if x not in seen]
    if left:
        n, w, l, dep, pnl = cell(left)
        out.append(f'    {"ABOVE TOP":>12s} {n:4d} {f"{w}/{l}":>7s} {dep:9.2f} {pnl:+9.4f} '
                   f'{pnl/max(dep,1e-9):+8.4f}  outside the fixed buckets, shown not dropped')
    return out

def in_bucket(v, lo, hi):
    if v is None: return False
    if lo is None: return v < hi
    if hi is None: return v >= lo
    return lo <= v < hi

def rows_for(key): return [x for x in fills if x[key] is not None]

L = [f'MAKER PROBE - "we lost in wicks". READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC',
     f'universe: {len(fills)} graded fills with BOTH bn_before and bn_after present, over '
     f'{len({f["epoch"] for f in fills})} distinct candles, '
     f'{sum(1 for f in fills if f["pnl"]>0)}W/{sum(1 for f in fills if f["pnl"]<0)}L.',
     f'the other {all_graded - len(fills)} graded fills predate the matched_at fix and have no '
     f'venue-timed window; they are EXCLUDED, not counted as zero.',
     'bps are on the engine bn_flow spot 1s series, forward-filled as FavBrain does.', '']
L += grid('(A) BY bn_before - the Binance move against us in the seconds BEFORE the fill',
          'bn_before_bps', A_BUCKETS)
L += ['']
L += grid('(B) BY MAX ADVERSE BINANCE MOVE from the fill to the candle end (bps vs price at fill)',
          'max_adv', B_BUCKETS)

# ---- (C) the losers ----------------------------------------------------------------------------
L += ['', '(C) EVERY LOSER: when our side first traded under 0.50, and what the last 60 s did',
      '    px<0.50 = first trade print of OUR token below 0.50 after the fill, on the public tape.',
      '    ahead@240 = at sec 240 the spot sat on OUR side of the opening TWAP60 (proxy, see below).',
      f'    {"id":>4s} {"candle":5s} {"side":4s} {"px":>5s} {"fill@s":>7s} {"<0.50 @s":>9s} '
      f'{"low":>5s} {"maxadv":>7s} {"ahead@240":>10s} {"flipped":>8s} {"pnl":>8s}']
agree = flips = ahead_lost = 0
for f in fills:
    if f['twap_open'] and f['twap_close']:
        imp = 'UP' if f['twap_close'] >= f['twap_open'] else 'DOWN'
        if imp == f['gamma']: agree += 1
losers = [f for f in fills if f['pnl'] < 0]
for f in losers:
    ep, fs = f['epoch'], f['fill_ts_ms'] // 1000
    rows = tp.execute('select ts, price from tape where epoch=? and asset=? and ts>=? order by ts',
                      (ep, f['token'], fs)).fetchall()
    under = next((int(t) - ep for t, p in rows if p is not None and float(p) < 0.50), None)
    low = min([float(p) for t, p in rows if p is not None], default=None)
    ahead = flip = '-'
    if f['twap_open'] and f['px240']:
        side240 = 'UP' if f['px240'] >= f['twap_open'] else 'DOWN'
        ahead = 'yes' if side240 == f['side'] else 'no'
        if ahead == 'yes':
            ahead_lost += 1
            if f['twap_close'] and (('UP' if f['twap_close'] >= f['twap_open'] else 'DOWN') != side240):
                flip = 'YES'; flips += 1
            else: flip = 'no'
        else: flip = 'n/a'
    L.append(f'    {f["id"]:4d} {U(ep)[11:16]:5s} {f["side"]:4s} {f["price"]:5.2f} {fs-ep:7d} '
             f'{(str(under) if under is not None else "never"):>9s} '
             f'{(f"{low:.2f}" if low is not None else "-"):>5s} '
             f'{(f"{f['max_adv']:.1f}" if f["max_adv"] is not None else "-"):>7s} '
             f'{ahead:>10s} {flip:>8s} {f["pnl"]:+8.4f}')
nu = sum(1 for f in losers if f['token'] and not tp.execute(
    'select 1 from tape where epoch=? and asset=? limit 1', (f['epoch'], f['token'])).fetchone())
L += ['',
      f'  losers whose token has NO tape rows at all (cannot be answered): {nu} of {len(losers)}',
      f'  TWAP60 PROXY CHECK: open=[ep-60,ep) close=[ep+240,ep+300) on bn_flow spot agrees with the '
      f'venue resolution on {agree} of {len(fills)} candles '
      f'({100*agree/max(len(fills),1):.1f}%). The venue settles on its Chainlink reference TWAP60, '
      f'not on Binance spot, so read the 240 s columns as a proxy.',
      f'  losers that were AHEAD at sec 240 and still lost: {ahead_lost} of {len(losers)}; of those, '
      f'the last 60 s flipped the TWAP sign on {flips}.']
print('\n'.join(L))
