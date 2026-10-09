#!/usr/bin/env python3
"""Backtest the EXACT M53-NC rule on all available history, two ways, so the look-ahead is visible.
READ-ONLY. The forward arm, its prereg and its decision rule are untouched by this file.

A) as the original retrospective: data-api print timestamps, entry = own-side ask at print_ts + 3 s,
   no size check, no slippage.
B) bias-corrected toward live: data-api timestamps shifted -3 s to match time (the measured median
   offset), the FIRST print re-chosen on corrected time, entry = ask at corrected_ts + 250 ms PLUS
   the live-measured +0.016 slippage, and the trade SKIPPED when level-1 cannot hold $5.
   Where websocket prints exist (epoch >= 1791257400) B uses those instead - they are already match
   time, so no shift is applied to them.
Both: not-calm per the frozen FAV definition (ef3_shadow._vol_bn >= FAV_CUT_LOW, >=240 s), first
taker BUY in sec 60-180 at print price 0.60-0.80, follow that side, $5, fee 0.07p(1-p) per share,
settle on the venue's own resolution.
"""
import sys, io, contextlib, sqlite3, math, collections, statistics as st, datetime as dt
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
with contextlib.redirect_stdout(io.StringIO()):
    import ef3_shadow as S
    S.ALL52, S.STRICT = None, None
    BN = S._bn_1s()
CUT = S.FAV_CUT_LOW
STAKE, FEE, SLIP, RTT, OFFSET = 5.0, 0.07, 0.016, 0.25, 3.0
SEC0, SEC1, LO, HI = 60, 180, 0.60, 0.80
WS_FROM = 1791257400
NC_START = int(open('/home/ubuntu/m53/nc_start_epoch').read().strip())
be = lambda a: a * (1 + FEE * (1 - a))

tp = sqlite3.connect('file:/home/ubuntu/pm_ef3/tape_btc5.sqlite3?mode=ro', uri=True)
mm = sqlite3.connect('file:/home/ubuntu/pm_multi/multi_market.sqlite3?mode=ro', uri=True)
m53 = sqlite3.connect('file:/home/ubuntu/m53/m53.sqlite3?mode=ro', uri=True)
UP = {}
for ep, a in sqlite3.connect('file:/home/ubuntu/m29/venues.sqlite3?mode=ro', uri=True)\
        .execute('select epoch,actual from outcome where actual is not null'): UP[int(ep)] = (a == 'UP')
for ep, o in sqlite3.connect('file:/home/ubuntu/pm_ef3/gamma_zurich.sqlite3?mode=ro', uri=True)\
        .execute("select epoch,outcome from mkt where outcome is not null and asset='btc'"): UP[int(ep)] = (o == 'UP')
BK = collections.defaultdict(dict)
for ts, ep, ua, us, da, ds in mm.execute("select ts,epoch,up_ask,up_ask_sz,dn_ask,dn_ask_sz from books "
                                         "where market='btc5'"):
    BK[int(ep)][int(ts) - int(ep)] = (ua, us, da, ds)
TOK = {int(e): (u, d) for e, u, d in mm.execute("select epoch,token_up,token_dn from markets where market='btc5'")}
WS = {int(e): (p, px, sd) for e, p, px, sd in m53.execute(
    "select epoch,print_ts,print_px,side from dec where src='clob_ws'")}

def ask_at(ep, sec, side):
    v = BK[ep].get(int(round(sec)))
    if v is None:
        for d in (1, -1, 2, -2):
            v = BK[ep].get(int(round(sec)) + d)
            if v is not None: break
    if v is None: return None, None
    return (v[0], v[1]) if side == 'UP' else (v[2], v[3])

def first_print(ep, shift):
    """First taker BUY in the window on the given timebase. shift is subtracted from data-api ts."""
    tu, td = TOK.get(ep, (None, None))
    if tu is None: return None
    best = None
    for ts, asset, price in tp.execute("select ts,asset,price from tape where epoch=? and is_taker=1 "
                                      "and side='BUY' order by ts", (ep,)):
        t = ts - shift
        s = t - ep
        if not (SEC0 <= s <= SEC1): continue
        p = float(price)
        if not (LO <= p <= HI): continue
        sd = 'UP' if asset == tu else ('DOWN' if asset == td else None)
        if sd is None: continue
        if best is None or t < best[0]: best = (t, p, sd)
    return best

rows = {'A': [], 'B': []}
for ep in sorted({int(e) for (e,) in tp.execute('select distinct epoch from tape')} | set(WS)):
    if ep not in UP or ep not in TOK: continue
    vol = S._vol_bn(BN, ep)
    if vol is None: continue
    calm = vol < CUT
    # ---- A: raw data-api ts, entry at +3 s, no size test, no slippage
    a = first_print(ep, 0.0)
    if a:
        t, p, sd = a
        ask, _sz = ask_at(ep, (t - ep) + 3.0, sd)
        if ask is not None and float(ask) < 0.99:
            ask = float(ask); sh = STAKE / be(ask)
            win = 1 if ((sd == 'UP') == UP[ep]) else 0
            rows['A'].append((ep, calm, win, (sh if win else 0.0) - STAKE, STAKE))
    # ---- B: ws print where we have one, else data-api shifted to match time; +250 ms; +slippage; size test
    b = None
    if ep in WS:
        pt, px, sd = WS[ep]; b = (float(pt), float(px), sd)
    else:
        b = first_print(ep, OFFSET)
    if b:
        t, p, sd = b
        ask, sz = ask_at(ep, (t - ep) + RTT, sd)
        if ask is not None:
            ask = min(float(ask) + SLIP, 0.99)
            if ask < 0.99:
                sh = STAKE / be(ask)
                if sz is not None and float(sz) >= sh:          # level-1 must hold $5
                    win = 1 if ((sd == 'UP') == UP[ep]) else 0
                    rows['B'].append((ep, calm, win, (sh if win else 0.0) - STAKE, STAKE))

def blk(tag, rs, calm_flag):
    v = [r for r in rs if r[1] == calm_flag]
    if not v: print(f'    {tag:9s} n 0'); return
    pn = [r[3] for r in v]; w = sum(1 for r in v if r[2] == 1)
    per = sum(pn) / (STAKE * len(v))
    t = st.mean(pn) / st.stdev(pn) * math.sqrt(len(pn)) if len(pn) > 1 and st.stdev(pn) > 0 else 0.0
    print(f'    {tag:9s} n {len(v):4d}  {w}W-{len(v)-w}L  ${sum(pn):+9.2f}  per $1 {per:+.4f}  t {t:+5.2f}'
          + ('  INSUFFICIENT (n<60)' if len(v) < 60 else ''))

def bank(rs):
    cash = 50.0; skipped = 0
    for ep, calm, win, pnl, stake in sorted(rs):
        if calm: continue
        if cash < STAKE: skipped += 1; continue
        cash += pnl
    return cash, skipped

span = sorted({r[0] for r in rows['A']} | {r[0] for r in rows['B']})
print(f'HISTORY COVERED: {dt.datetime.fromtimestamp(span[0],dt.UTC):%m-%d %H:%M} .. '
      f'{dt.datetime.fromtimestamp(span[-1],dt.UTC):%m-%d %H:%M} UTC')
print(f'  NOTE: the data-api tape starts 09-30 09:25, so 09-29 and most of 09-30 have NO print data '
      f'and cannot be tested. V asked for 09-29 onward; this is what exists.')
print(f'  websocket prints available from epoch {WS_FROM} ({dt.datetime.fromtimestamp(WS_FROM,dt.UTC):%m-%d %H:%M}), '
      f'{len(WS)} candles - version B uses those in place of the tape.')
print()
for k, lab in (('A', 'A) ORIGINAL RETROSPECTIVE (data-api ts, entry at print+3 s, no size test, no slippage)'),
               ('B', 'B) BIAS-CORRECTED (ts -3 s to match time, entry at +250 ms, +0.016 slippage, $5 must fit L1)')):
    print(lab)
    blk('NOT-CALM', rows[k], False)
    blk('CALM', rows[k], True)
    c, sk = bank(rows[k])
    print(f'    bankroll path on the NOT-CALM trades only, $50 start / $5 stake: END ${c:.2f}'
          + (f'  ({sk} trades skipped for cash)' if sk else ''))
    print()
for k in ('A', 'B'):
    print(f'PER-DAY, NOT-CALM ONLY, version {k}')
    d = collections.defaultdict(list)
    for ep, calm, win, pnl, _s in rows[k]:
        if not calm: d[dt.datetime.fromtimestamp(ep, dt.UTC).strftime('%m-%d')].append((win, pnl))
    for day in sorted(d):
        v = d[day]; w = sum(1 for x in v if x[0] == 1); pn = sum(x[1] for x in v)
        print(f'  {day}: n {len(v):3d}  {w}W-{len(v)-w}L  ${pn:+8.2f}  per $1 {pn/(STAKE*len(v)):+.4f}')
    print()
ov = [r for r in rows['B'] if not r[1] and r[0] >= NC_START]
hrs = collections.Counter(dt.datetime.fromtimestamp(r[0], dt.UTC).hour for r in rows['B'] if not r[1])
print(f'OVERLAP WITH THE FORWARD ARM: {len(ov)} of {sum(1 for r in rows["B"] if not r[1])} version-B '
      f'not-calm trades sit at epoch >= {NC_START}, i.e. in the window the live arm is already counting.')
print(f'  Those are NOT independent of the forward arm and must not be added to its n.')
print(f'  hour-of-day of version-B not-calm trades (UTC): '
      + ' '.join(f'{h:02d}:{hrs[h]}' for h in sorted(hrs)))
