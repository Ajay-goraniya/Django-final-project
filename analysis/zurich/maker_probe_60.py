#!/usr/bin/env python3
"""The 60-GRADED-FILL report the owner asked for. READ-ONLY.

Fires once, when graded fills first reach 60. Everything here is venue-truth: the fills table is
reconciled from the venue's own maker_orders[] on an unfiltered tape, and this script re-checks the
venue for open orders before reporting, because the ledger has been wrong four separate ways today and
a report that trusts it without looking is not a report.

The band grid follows analysis/v/maker2/PREREG_M16_BAND.md exactly: buckets [0.60,0.65) [0.65,0.70)
[0.70,0.75) [0.75,0.81], and ONLY fills after 12:45 UTC on 10-01, which is when the hypothesis was
written. Fills before that are the data that SUGGESTED it and must not also test it.
"""
import asyncio, os, sqlite3, sys, time, datetime as dt

sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
DB = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
CUT = int(dt.datetime(2026, 10, 1, 12, 45, tzinfo=dt.UTC).timestamp() * 1000)
BUCKETS = [(0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.81)]
DAY_STOP, LIFE_STOP, BAR = -10.0, -20.0, 60
# V, 10-01 23:2x: the bar is 60 DISTINCT GRADED CANDLES, not 60 graded fills, and the report also
# carries the time halves and the result with the 09-30 17:00 candle taken out. That candle is
# epoch 1790787600; it alone holds 15 fills and more than half the lifetime pnl, which is exactly
# why it has to be shown both ways rather than averaged in silently.
CHURN = 1790787600


def halves(rows):
    """pnl in the first and second half of the graded fills, split by TIME at equal count. The
    split point is printed, because 'H1/H2' means nothing without knowing where it fell."""
    r = sorted(rows, key=lambda x: x['fill_ts_ms'])
    if len(r) < 2: return []
    k = (len(r) + 1) // 2
    out = []
    for name, part in (('H1', r[:k]), ('H2', r[k:])):
        d = sum(x['spent'] for x in part); pn = sum(x['pnl'] for x in part)
        w = sum(1 for x in part if x['pnl'] > 0); l = sum(1 for x in part if x['pnl'] < 0)
        out.append(f'    {name}  n {len(part):3d}  {w}W/{l}L  pnl {pn:+8.4f} on ${d:7.2f} = '
                   f'{pn/max(d,1e-9):+.4f} per $1')
    split = dt.datetime.fromtimestamp(r[k]['fill_ts_ms'] / 1000, dt.UTC)
    out.append(f'    split at {split:%F %T} UTC (H2 starts there)')
    return out


def summary(rows, title):
    """The headline block for any subset of graded fills, so the all-fills read and the
    ex-17:00 read are produced by the SAME code rather than two hand-written versions."""
    w = sum(1 for x in rows if x['pnl'] > 0); l = sum(1 for x in rows if x['pnl'] < 0)
    dep = sum(x['spent'] for x in rows); pnl = sum(x['pnl'] for x in rows)
    return [title,
            f'    fills {len(rows)} over {len({x["epoch"] for x in rows})} DISTINCT candles | {w}W / {l}L',
            f'    pnl {pnl:+.4f} on ${dep:.2f} deployed = {pnl/max(dep,1e-9):+.4f} per $1'] + halves(rows)


def q(c, sql, a=()):
    r = c.execute(sql, a).fetchone()
    return r[0] if r else None


async def venue_check():
    """Open orders and probe trades straight from the venue. Returns a line, or None if no creds."""
    if not os.environ.get('POLYMARKET_PRIVATE_KEY'):
        return None
    from poly_live import LiveBroker
    b = LiveBroker(None); await b.open()
    n = 0
    async for page in b.client.list_open_orders():
        n += len(getattr(page, 'items', ()))
    cash = await b.cash()
    return f'venue cross-check: open orders {n}, wallet collateral ${cash:.4f}'


def main():
    c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
    g = [dict(r) for r in c.execute('select * from fills where pnl is not null order by fill_ts_ms')]
    today = time.strftime('%Y-%m-%d', time.gmtime())
    cand = len({x['epoch'] for x in g})
    L = [f'MAKER PROBE HAS REACHED {cand} DISTINCT GRADED CANDLES (bar {BAR}) on {len(g)} graded '
         f'fills. Venue-graded. {dt.datetime.now(dt.UTC):%F %T} UTC']
    w = sum(1 for x in g if x['pnl'] > 0); l = sum(1 for x in g if x['pnl'] < 0)
    dep = sum(x['spent'] for x in g); pnl = sum(x['pnl'] for x in g)
    tp = q(c, 'select coalesce(sum(pnl),0) from fills where utc_day=?', (today,))
    lp = q(c, 'select coalesce(sum(pnl),0) from fills')
    unsettled = q(c, 'select count(*) from fills where pnl is null')
    L += [f'  fills {len(g)} over {cand} DISTINCT candles | {w}W / {l}L'
          f'{f" | {unsettled} still unsettled and excluded" if unsettled else ""}',
          f'  pnl {pnl:+.4f} on ${dep:.2f} deployed = {pnl/max(dep,1e-9):+.4f} per $1',
          f'  today {tp:+.4f} of {DAY_STOP:.0f} stop | lifetime {lp:+.4f} of {LIFE_STOP:.0f} stop']
    adv = [x for x in g if x['bn_after_bps'] is not None]
    an = sum(1 for x in adv if x['bn_after_bps'] >= 2.0)
    L.append(f'  adverse share (>=2bps against us within 1s of the fill): {an} of {len(adv)} fills that '
             f'HAVE a venue-timed window' + (f' ({100*an/len(adv):.1f}%)' if adv else '')
             + f'; the other {len(g)-len(adv)} predate the matched_at fix and are excluded rather than '
               f'counted as zero')
    L += [''] + summary(g, '  TIME HALVES, all graded fills')
    ex = [x for x in g if x['epoch'] != CHURN]
    n_ch = len(g) - len(ex)
    L += [''] + summary(ex, f'  EXCLUDING the 09-30 17:00 candle (epoch {CHURN}, {n_ch} fills removed)')
    L += ['', 'M16 BAND GRID - PREREG_M16_BAND.md, fills AFTER 10-01 12:45 UTC only (out of sample)',
          f'  {"bucket":14s} {"fills":>6s} {"candles":>8s} {"W/L":>7s} {"deployed":>10s} {"pnl":>9s} '
          f'{"pnl/$1":>9s}  flag']
    oos = [x for x in g if x['fill_ts_ms'] >= CUT]
    rest_pnl = rest_dep = 0.0
    for lo, hi in BUCKETS:
        sel = [x for x in oos if lo <= x['price'] < hi or (hi == 0.81 and abs(x['price'] - 0.80) < 1e-9)]
        if not sel:
            L.append(f'  [{lo:.2f},{hi:.2f}{"]" if hi == 0.81 else ")"} {0:5d} {0:8d} '
                     f'{"-":>7s} {"-":>10s} {"-":>9s} {"-":>9s}  no fills'); continue
        bw = sum(1 for x in sel if x['pnl'] > 0); bl = sum(1 for x in sel if x['pnl'] < 0)
        bd = sum(x['spent'] for x in sel); bp = sum(x['pnl'] for x in sel)
        if hi != 0.81: rest_pnl += bp; rest_dep += bd
        edge = ']' if hi == 0.81 else ')'      # the prereg's top bucket is INCLUSIVE
        L.append(f'  [{lo:.2f},{hi:.2f}{edge} {len(sel):5d} {len({x["epoch"] for x in sel}):8d} '
                 f'{f"{bw}/{bl}":>7s} {bd:10.2f} {bp:+9.2f} {bp/max(bd,1e-9):+9.4f}'
                 f'  {"INSUFFICIENT (<60)" if len(sel) < 60 else ""}')
    top = [x for x in oos if x['price'] >= 0.75 - 1e-9]
    tp_pnl = sum(x['pnl'] for x in top); tp_dep = sum(x['spent'] for x in top)
    L += ['', '  THE PRE-REGISTERED PREDICTION was: [0.75,0.81] pnl/$ < 0, the other three combined > 0.',
          f'    [0.75,0.81]      n {len(top):3d}  pnl/$1 {tp_pnl/max(tp_dep,1e-9):+.4f}  '
          f'-> prediction {"HELD" if tp_pnl < 0 else "FAILED"}',
          f'    other three      n {len(oos)-len(top):3d}  pnl/$1 {rest_pnl/max(rest_dep,1e-9):+.4f}  '
          f'-> prediction {"HELD" if rest_pnl > 0 else "FAILED"}',
          f'    out-of-sample fills available: {len(oos)} of {len(g)} graded. EVERY bucket is under 60',
          '    fills, which the prereg itself said to expect, so this read decides nothing on its own',
          '    and NO band change happens without the owner\'s confirmation.']
    try:
        v = asyncio.run(venue_check())
        L.append('')
        L.append('  ' + (v if v else 'venue cross-check SKIPPED: no credentials in this environment'))
    except Exception as e:
        L.append(f'  venue cross-check FAILED: {type(e).__name__}: {e}')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
