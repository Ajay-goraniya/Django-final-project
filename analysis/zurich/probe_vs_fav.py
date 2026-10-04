#!/usr/bin/env python3
"""Is calm-FAV's improvement EXECUTION rather than the rule? READ-ONLY.

The probe is passive FAV with real money (post-only BUY at the best bid, maker fee 0). The FAV arm
is the same rule taken as a TAKER in simulation (arrival ask + exact fee). Same candles, same days,
so the difference between them is execution, not the signal.

Costs are made comparable with the shadow's OWN fee functions - be(px) is the fee-exact breakeven,
which is what a taker really pays per share - rather than a fee I invent here.
"""
import math, sqlite3, sys
import datetime as dt

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import be                      # fee-exact breakeven per share, the shadow's own

PROBE = '/home/ubuntu/maker_probe/maker_probe.sqlite3'
SHADOW = '/home/ubuntu/pm_ef3/ef3_shadow.sqlite3'
A = int(dt.datetime(2026, 9, 30, 17, 0, tzinfo=dt.UTC).timestamp())
NOW = int(dt.datetime.now(dt.UTC).timestamp())
TODAY = int(dt.datetime(2026, 10, 2, tzinfo=dt.UTC).timestamp())
BAR = 60

p = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True); p.row_factory = sqlite3.Row
s = sqlite3.connect(f'file:{SHADOW}?mode=ro', uri=True); s.row_factory = sqlite3.Row

# ---- the two populations, keyed by candle --------------------------------------------------------
PR = {}
for r in p.execute('select * from fills where pnl is not null and epoch>=? and epoch<? order by fill_ts_ms',
                   (A, NOW)):
    d = PR.setdefault(r['epoch'], dict(pnl=0.0, spent=0.0, sh=0.0, side=r['side'], price=r['price'],
                                       out=r['outcome'], sec=r['fill_ts_ms'] // 1000 - r['epoch']))
    d['pnl'] += r['pnl']; d['spent'] += r['spent']; d['sh'] += r['shares']

FV = {}
for r in s.execute("select * from fires where arm='FAV' and epoch>=? and epoch<? order by epoch",
                   (A, NOW)):
    sh = r['sh'] or 0.0
    if sh <= 0: continue                               # no fill under the partial arrival model
    vw = r['vwap'] if r['vwap'] == r['vwap'] else r['ask']
    FV[r['epoch']] = dict(pnl=float(r['pnl_part'] or 0.0), sh=float(sh), ask=float(r['ask']),
                          vwap=float(vw), cost=float(sh) * be(float(vw)),
                          side='UP' if r['up'] else 'DOWN', win=r['win'], sec=r['sec'])

BOTH = sorted(set(PR) & set(FV))
MISSED = sorted(set(FV) - set(PR))                     # FAV traded, the probe did not fill
ONLY_P = sorted(set(PR) - set(FV))                     # the probe filled, FAV did not trade

def per(x, key_pnl='pnl', key_dep='spent'):
    return x[key_pnl] / x[key_dep] if x[key_dep] else 0.0

def signtest(diffs):
    """Exact two-sided sign test on the paired per-candle differences. Ties dropped."""
    d = [x for x in diffs if abs(x) > 1e-12]
    if not d: return None, 0, 0
    pos = sum(1 for x in d if x > 0); n = len(d)
    c = lambda n, k: math.comb(n, k)
    tail = sum(c(n, k) for k in range(0, min(pos, n - pos) + 1)) / 2 ** n
    return min(1.0, 2 * tail), pos, n

L = [f'PROBE (passive, real money) vs FAV ARM (taker, simulated) - is the gain EXECUTION?',
     f'READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC. Window 09-30 17:00 .. now.',
     'Probe: post-only BUY at the best bid, maker fee 0, graded on the venue resolution, real fills.',
     'FAV arm: same rule as a TAKER - arrival ask + exact fee, partial arrival fill, $10 nominal.',
     'Per $1 uses the money ACTUALLY deployed on both sides: the probe its spend, FAV sh*be(vwap).',
     f'candles: probe filled {len(PR)}, FAV filled {len(FV)}, BOTH {len(BOTH)}, '
     f'FAV-only {len(MISSED)}, probe-only {len(ONLY_P)}', '']

def section(eps, title, today=False):
    out = []
    tag = ' (10-02 only)' if today else ''
    agree = sum(1 for e in eps if PR[e]['side'] == FV[e]['side'])
    pp = sum(PR[e]['pnl'] for e in eps); pd_ = sum(PR[e]['spent'] for e in eps)
    fp = sum(FV[e]['pnl'] for e in eps); fd = sum(FV[e]['cost'] for e in eps)
    out += [f'== 1. BOTH FILLED{tag}: {len(eps)} candles'
            f'{"   INSUFFICIENT (<60)" if len(eps) < BAR else ""}',
            f'   side agreement: {agree} of {len(eps)}'
            + (f' ({100*agree/len(eps):.1f}%)' if eps else ''),
            f'   mean price paid: probe bid {sum(PR[e]["price"] for e in eps)/max(len(eps),1):.4f} '
            f'vs FAV fee-exact cost per share {sum(FV[e]["cost"]/max(FV[e]["sh"],1e-9) for e in eps)/max(len(eps),1):.4f}'
            f'  (FAV raw ask {sum(FV[e]["ask"] for e in eps)/max(len(eps),1):.4f})',
            f'   mean entry second: probe {sum(PR[e]["sec"] for e in eps)/max(len(eps),1):.0f} '
            f'vs FAV {sum(FV[e]["sec"] for e in eps)/max(len(eps),1):.0f}',
            f'   PROBE total {pp:+.4f} on ${pd_:.2f} = {pp/max(pd_,1e-9):+.4f} per $1',
            f'   FAV   total {fp:+.4f} on ${fd:.2f} = {fp/max(fd,1e-9):+.4f} per $1',
            f'   difference (probe - FAV): {pp-fp:+.4f} $, {pp/max(pd_,1e-9)-fp/max(fd,1e-9):+.4f} per $1']
    diffs = [per(PR[e]) - (FV[e]['pnl'] / FV[e]['cost'] if FV[e]['cost'] else 0.0) for e in eps]
    pv, pos, n = signtest(diffs)
    mean = sum(diffs) / len(diffs) if diffs else 0.0
    out += [f'   PAIRED per candle: n {n} non-tied, probe better on {pos}, mean difference '
            f'{mean:+.4f} per $1, sign-flip p '
            + ('n/a' if pv is None else f'{pv:.4f}')
            + ('   INSUFFICIENT (<60)' if n < BAR else ''),
            f'   outcome agreement is automatic (same candle, same venue resolution), so the only',
            f'   thing moving here is WHAT WAS PAID and WHEN.', '']
    return out

L += section(BOTH, '')

# ---- 2. the missed set -------------------------------------------------------------------------
mp = sum(FV[e]['pnl'] for e in MISSED); md = sum(FV[e]['cost'] for e in MISSED)
mw = sum(1 for e in MISSED if FV[e]['pnl'] > 0); ml = sum(1 for e in MISSED if FV[e]['pnl'] < 0)
L += [f'== 2. FAV TRADED, THE PROBE DID NOT FILL - the "missed" set: {len(MISSED)} candles'
      f'{"   INSUFFICIENT (<60)" if len(MISSED) < BAR else ""}',
      f'   FAV on them: {mw}W/{ml}L, {mp:+.4f} on ${md:.2f} = {mp/max(md,1e-9):+.4f} per $1',
      f'   FAV on the BOTH set, for comparison: {sum(FV[e]["pnl"] for e in BOTH)/max(sum(FV[e]["cost"] for e in BOTH),1e-9):+.4f} per $1',
      '   ADVERSE SELECTION READ: if the probe is being filled only on the bad candles, the missed',
      '   set should be where FAV made its money. Compare the two per-$1 figures directly.', '']

# ---- 3. probe-only ------------------------------------------------------------------------------
op = sum(PR[e]['pnl'] for e in ONLY_P); od = sum(PR[e]['spent'] for e in ONLY_P)
ow = sum(1 for e in ONLY_P if PR[e]['pnl'] > 0); ol = sum(1 for e in ONLY_P if PR[e]['pnl'] < 0)
L += [f'== 3. THE PROBE FILLED, FAV DID NOT TRADE: {len(ONLY_P)} candles'
      f'{"   INSUFFICIENT (<60)" if len(ONLY_P) < BAR else ""}',
      f'   probe on them: {ow}W/{ol}L, {op:+.4f} on ${od:.2f} = {op/max(od,1e-9):+.4f} per $1',
      '   These are candles the taker rule skipped (ask outside 0.65-0.85, or vol/sec gates) but',
      '   where a resting bid still got filled - so they are the probe trading something FAV cannot.', '']

# ---- 4. today ----------------------------------------------------------------------------------
L += ['== 4. TODAY 10-02 ONLY']
tb = [e for e in BOTH if e >= TODAY]
L += section(tb, '', today=True) if tb else ['   no candles where both filled today', '']
tm = [e for e in MISSED if e >= TODAY]; to = [e for e in ONLY_P if e >= TODAY]
tmp = sum(FV[e]['pnl'] for e in tm); tmd = sum(FV[e]['cost'] for e in tm)
top = sum(PR[e]['pnl'] for e in to); tod = sum(PR[e]['spent'] for e in to)
L += [f'   missed set today: {len(tm)} candles, FAV {tmp:+.4f} on ${tmd:.2f} = '
      f'{tmp/max(tmd,1e-9):+.4f} per $1'
      f'{"   INSUFFICIENT (<60)" if len(tm) < BAR else ""}',
      f'   probe-only today: {len(to)} candles, probe {top:+.4f} on ${tod:.2f} = '
      f'{top/max(tod,1e-9):+.4f} per $1'
      f'{"   INSUFFICIENT (<60)" if len(to) < BAR else ""}']
print('\n'.join(L))
