"""Do MAIN and REVERSAL help in EF drawdown? Read-only, Zurich shadow journal live4.

Common period = the span where all three lanes are live: first REVERSAL fill to the last fill.
Stake normalised to $5 per trade for EVERY lane, so the lanes are comparable regardless of what the
stake dial actually was at the time: pnl = 5 * (payout/cost - 1).
Paired throughout - the per-candle correlation uses only candles where BOTH lanes fired, because the
candles where one is absent carry no information about how they move together.
"""
import sqlite3, json, statistics as st, datetime as dt, math

DB = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
STAKE = 5.0
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
res = {r['epoch']: r['actual'] for r in c.execute('SELECT epoch,actual FROM results')}
trades = []
for r in c.execute("""SELECT o.epoch,o.ts,o.kind,o.plan,sum(f.shares) sh,sum(f.spent) sp,sum(f.fees) fe
                      FROM orders o JOIN fills f ON f.order_id=o.id
                      WHERE o.status='FILLED' AND o.kind IN ('EF','MAIN','REVERSAL') GROUP BY o.id ORDER BY o.ts"""):
    a = res.get(r['epoch'])
    if a is None: continue
    side = (json.loads(r['plan']) or {}).get('side') or (c.execute(
        "SELECT side FROM signals WHERE epoch=? AND kind=? LIMIT 1", (r['epoch'], r['kind'])).fetchone() or [None])[0]
    if side is None: continue
    cost = (r['sp'] or 0.) + (r['fe'] or 0.)
    if not cost: continue
    payout = (r['sh'] or 0.) if side == a else 0.
    trades.append(dict(epoch=r['epoch'], ts=r['ts'], kind=r['kind'], pnl=STAKE * (payout / cost - 1.0)))
lo = max(min(t['ts'] for t in trades if t['kind'] == k) for k in ('EF','MAIN','REVERSAL'))
hi = min(max(t['ts'] for t in trades if t['kind'] == k) for k in ('EF','MAIN','REVERSAL'))
trades = [t for t in trades if lo <= t['ts'] <= hi]
f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%m-%d %H:%M')
print(f'COMMON PERIOD (all three lanes live): {f(lo)} -> {f(hi)} UTC, {(hi-lo)/3600:.1f} h')
for k in ('EF','MAIN','REVERSAL'):
    s = [t for t in trades if t['kind'] == k]
    print(f'  {k:<9} n {len(s):4d}  total {sum(x["pnl"] for x in s):+9.2f}  at ${STAKE:.0f}/trade')

def corr(a, b):
    if len(a) < 3: return None
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x-ma)**2 for x in a)); db = math.sqrt(sum((y-mb)**2 for y in b))
    return num/(da*db) if da and db else None

print('\n(1) CORRELATION')
hours = sorted({int(t['ts']//3600) for t in trades})
series = {k: [sum(x['pnl'] for x in trades if x['kind']==k and int(x['ts']//3600)==h) for h in hours] for k in ('EF','MAIN','REVERSAL')}
for k in ('MAIN','REVERSAL'):
    r = corr(series['EF'], series[k])
    print(f'  per hour   EF vs {k:<9} r {r:+.3f}  over {len(hours)} hours' if r is not None else f'  per hour EF vs {k}: too few')
for k in ('MAIN','REVERSAL'):
    eps = sorted({t['epoch'] for t in trades if t['kind']=='EF'} & {t['epoch'] for t in trades if t['kind']==k})
    ef = [sum(x['pnl'] for x in trades if x['kind']=='EF' and x['epoch']==e) for e in eps]
    ot = [sum(x['pnl'] for x in trades if x['kind']==k and x['epoch']==e) for e in eps]
    r = corr(ef, ot)
    print(f'  per candle EF vs {k:<9} r {r:+.3f}  on {len(eps)} candles where BOTH fired' if r is not None
          else f'  per candle EF vs {k:<9} only {len(eps)} shared candles - too few')

print('\n(2) EF DRAWDOWN EPISODES (peak-to-trough >= 10 stakes = $%.0f) and what the others made inside each' % (10*STAKE))
ef = [t for t in trades if t['kind']=='EF']
cum = 0.; peak = 0.; peak_ts = ef[0]['ts'] if ef else lo; epis = []; cur = None
for t in ef:
    cum += t['pnl']
    if cum > peak: 
        if cur: epis.append(cur); cur = None
        peak, peak_ts = cum, t['ts']
    dd = peak - cum
    if dd >= 10*STAKE:
        if cur is None: cur = dict(start=peak_ts, end=t['ts'], dd=dd)
        else: cur.update(end=t['ts'], dd=max(cur['dd'], dd))
if cur: epis.append(cur)
if not epis: print('  none')
for i, e in enumerate(epis, 1):
    w = [t for t in trades if e['start'] <= t['ts'] <= e['end']]
    ef_n = [x for x in w if x['kind']=='EF']
    print(f"  #{i} {f(e['start'])} -> {f(e['end'])}  ({(e['end']-e['start'])/3600:.1f} h)  EF drawdown -{e['dd']:.2f}")
    for k in ('EF','MAIN','REVERSAL'):
        s = [x for x in w if x['kind']==k]
        print(f"      {k:<9} n {len(s):3d}  pnl {sum(x['pnl'] for x in s):+8.2f}")
    off = sum(x['pnl'] for x in w if x['kind'] in ('MAIN','REVERSAL'))
    print(f"      MAIN+REV offsets {off:+.2f} of the -{e['dd']:.2f}  =  {100*off/e['dd']:+.0f}%")

print('\n(3) COMBINED CURVES, chronological, same $%.0f stake per trade' % STAKE)
def curve(kinds):
    s = sorted([t for t in trades if t['kind'] in kinds], key=lambda x: x['ts'])
    cum = 0.; peak = 0.; mdd = 0.
    for t in s:
        cum += t['pnl']; peak = max(peak, cum); mdd = max(mdd, peak-cum)
    return len(s), cum, mdd
print(f"  {'portfolio':<22}{'n':>6}{'total pnl':>12}{'maxDD':>10}")
for label, kinds in (('EF alone', ('EF',)), ('EF + MAIN', ('EF','MAIN')),
                     ('EF + REVERSAL', ('EF','REVERSAL')), ('EF + MAIN + REVERSAL', ('EF','MAIN','REVERSAL'))):
    n, tot, mdd = curve(kinds)
    print(f'  {label:<22}{n:>6}{tot:>+12.2f}{mdd:>10.2f}')
