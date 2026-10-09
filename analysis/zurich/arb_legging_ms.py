#!/usr/bin/env python3
"""How long does the 15m/5m riskless pair actually live, in MILLISECONDS, and would both legs have filled?
READ-ONLY. Nothing live.

Source: the dual-market ms probe (/home/ubuntu/pm_probe2/arb_ms.sqlite3), one WS subscription carrying both
BTC markets' tokens, top-two asks with sizes on every book and delta event, stamped with our receive time
(rx_ns) and the venue's own event ms (ev_ms). rx_ns is used throughout, because legging risk is measured on
OUR clock, not the venue's.

Lines come from the engine's tape1s.ref_px (the Chainlink reference the venue settles on), TWAP60 of the
minute before each open, exactly as arb_5m_15m.py does. The legs follow from the sign of L15 - L5:
    L15 < L5 -> 15m UP + 5m DOWN        L15 > L5 -> 15m DOWN + 5m UP
and one share of each pays 1 or 2, never 0, as long as that sign is right (see the 09-28 correction in
ARB_5M_15M.md: at a gap of a few dollars the sign itself is inside the reference's resolution, so |gap| is
reported per window and windows under $5 are flagged).

Riskless means cost = a15 + fee(a15) + a5 + fee(a5) < 1, fee per share = 0.07*p*(1-p). A "window" is one
15m candle; the scan covers the last 5 minutes of it, where both markets are live at once.

The +250 ms test is the same FAK rule as ef_persist.py: you decide at t0 on the two asks you can see, you
arrive 250 ms later, and a leg fills only if its ask is still within one tick of what you priced.
"""
import sys, sqlite3, collections, datetime as dt, numpy as np

PROBE = '/home/ubuntu/pm_probe2/arb_ms.sqlite3'
LIVE = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA_DBS = ['/tmp/poly/btc5.sqlite3', '/tmp/poly/btc5b.sqlite3']
RATE, TICK, ARRIVE_MS = 0.07, 0.01, 250
fee = lambda p: RATE * p * (1 - p)
pc = sqlite3.connect(f'file:{PROBE}?mode=ro', uri=True)
lc = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)

ref = {int(t): float(r) for t, r in lc.execute('SELECT ts,ref_px FROM tape1s WHERE ref_px IS NOT NULL')}
def line(ep):
    v = [ref[ep - k] for k in range(1, 61) if (ep - k) in ref]
    return (sum(v) / len(v)) if len(v) >= 45 else None

res15 = {}
try:
    mc = sqlite3.connect('file:/home/ubuntu/pm_multi/multi_market.sqlite3?mode=ro', uri=True)
    res15 = {int(e): o for e, o in mc.execute("SELECT epoch,outcome FROM resolutions WHERE market='btc15'")}
except Exception: pass
res15.update({int(e): o for e, o in pc.execute("SELECT epoch,outcome FROM resolutions WHERE market='btc15'")})
res5 = {int(e): o for e, o in pc.execute("SELECT epoch,outcome FROM resolutions WHERE market='btc5'")}
for p in GAMMA_DBS:
    try:
        g = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        res5.update({int(e): o for e, o in g.execute(
            "SELECT epoch,outcome FROM mkt WHERE asset='btc' AND outcome IS NOT NULL")})
    except Exception: pass

tk = {(m, int(ep)): (u, d) for m, ep, u, d in pc.execute('SELECT market,epoch,token_up,token_dn FROM markets')}
eps = sorted(ep for (m, ep) in tk if m == 'btc15')

def stream(token, t0_ns, t1_ns):
    return pc.execute('SELECT rx_ns,ask,ask_sz FROM top WHERE token=? AND rx_ns BETWEEN ? AND ? ORDER BY rx_ns',
                      (token, t0_ns, t1_ns)).fetchall()

W, per_window, audit = [], [], []
for ep15 in eps:
    ep5 = ep15 + 600
    if ('btc5', ep5) not in tk:
        audit.append((ep15, None, 'no btc5 market for the last 5m candle')); continue
    L15, L5 = line(ep15), line(ep5)
    if L15 is None or L5 is None or abs(L15 - L5) < 1e-9:
        audit.append((ep15, None, 'no usable line')); continue
    leg15, leg5 = ('UP', 'DOWN') if L15 < L5 else ('DOWN', 'UP')
    t15 = tk[('btc15', ep15)][0 if leg15 == 'UP' else 1]
    t5 = tk[('btc5', ep5)][0 if leg5 == 'UP' else 1]
    a, b = ep5 * 10**9, (ep5 + 300) * 10**9
    s15, s5 = stream(t15, a, b), stream(t5, a, b)
    if not s15 or not s5:
        audit.append((ep15, L15 - L5, 'no events on one leg')); continue
    audit.append((ep15, L15 - L5, f'scanned, {len(s15)} + {len(s5)} events'))
    ev = sorted([(r[0], 0, r[1], r[2]) for r in s15] + [(r[0], 1, r[1], r[2]) for r in s5])
    cur = [None, None]; sz = [None, None]
    ivals = []              # (t_start_ns, t_end_ns, a15, a5, min_sz)
    open_iv = None
    for rx, which, ask, asz in ev:
        cur[which] = ask; sz[which] = asz
        if cur[0] is None or cur[1] is None: continue
        ok = (0.01 < cur[0] < 0.99 and 0.01 < cur[1] < 0.99)
        c = (cur[0] + fee(cur[0]) + cur[1] + fee(cur[1])) if ok else 9.
        if c < 1.0:
            if open_iv is None:
                open_iv = [rx, rx, cur[0], cur[1], min(x for x in sz if x is not None)]
            else:
                open_iv[1] = rx
                open_iv[4] = min(open_iv[4], min(x for x in sz if x is not None))
        elif open_iv is not None:
            open_iv[1] = rx; ivals.append(tuple(open_iv)); open_iv = None
    if open_iv is not None: ivals.append(tuple(open_iv))
    if not ivals: continue

    def ask_at(s, t):
        lo, hi, out = 0, len(s) - 1, None
        while lo <= hi:
            m = (lo + hi) // 2
            if s[m][0] <= t: out = s[m]; lo = m + 1
            else: hi = m - 1
        return out

    o15, o5 = res15.get(ep15), res5.get(ep5)
    pay = ((1 if o15 == leg15 else 0) + (1 if o5 == leg5 else 0)) if (o15 and o5) else None
    for t0, t1, a15, a5, msz in ivals:
        q15 = ask_at(s15, t0 + ARRIVE_MS * 10**6); q5 = ask_at(s5, t0 + ARRIVE_MS * 10**6)
        f15 = q15 is not None and q15[1] <= a15 + TICK + 1e-12
        f5 = q5 is not None and q5[1] <= a5 + TICK + 1e-12
        W.append(dict(ep15=ep15, ms=(t1 - t0) / 1e6, a15=a15, a5=a5,
                      cost=a15 + fee(a15) + a5 + fee(a5), msz=msz, f15=f15, f5=f5,
                      sec=int(t0 / 1e9) - ep5, gap=L15 - L5,
                      w15=(1 if o15 == leg15 else 0) if o15 else None, pay=pay,
                      day=dt.datetime.fromtimestamp(ep15, dt.timezone.utc).strftime('%m-%d')))
    per_window.append(dict(ep15=ep15, n=len(ivals), gap=L15 - L5, legs=f'{leg15}+{leg5}', pay=pay,
                           total_ms=sum((t1 - t0) / 1e6 for t0, t1, *_ in ivals),
                           best=min(a15 + fee(a15) + a5 + fee(a5) for _, _, a15, a5, _ in ivals)))

f = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc).strftime('%m-%d %H:%M')
sc = [a for a in audit if a[2].startswith('scanned')]
print(f'btc15 windows in the probe: {len(eps)} ({f(eps[0])} -> {f(eps[-1])}); scannable {len(sc)}; '
      f'windows with a riskless interval: {len(per_window)}')
print('\n(0) EVERY WINDOW, so the denominator is visible and the riskless ones are not cherry-picked')
riskless = {w['ep15'] for w in per_window}
for ep, gap, note in audit:
    print(f'    {f(ep)}  gap {("%+8.2f" % gap) if gap is not None else "       -"}  {note}'
          + ('   <- RISKLESS' if ep in riskless else ''))
gp = [abs(g) for e, g, n in audit if g is not None and n.startswith("scanned")]
gr = [abs(g) for e, g, n in audit if g is not None and e in riskless]
if gp:
    print(f'    |gap| over the {len(gp)} scanned windows: min {min(gp):.2f} median '
          f'{sorted(gp)[len(gp)//2]:.2f} max {max(gp):.2f}; the riskless ones are at '
          + ', '.join(f'{x:.2f}' for x in sorted(gr))
          + '  - the pair only goes riskless where the two lines are CLOSE, which is also where the sign of '
            'the gap, and therefore the choice of legs, is least reliable')
if not W: print('no riskless interval in the probe window'); sys.exit(0)
ms = np.array([w['ms'] for w in W])
print(f'\n(1) HOW LONG BOTH LEGS STAY AT OR UNDER cost 1, on our receive clock')
print(f'    riskless intervals {len(W)} across {len(per_window)} windows')
print(f'    duration ms: min {ms.min():.0f}  p10 {np.percentile(ms,10):.0f}  p50 {np.percentile(ms,50):.0f}  '
      f'p90 {np.percentile(ms,90):.0f}  max {ms.max():.0f}  mean {ms.mean():.0f}')
print(f'    intervals shorter than the {ARRIVE_MS} ms it takes to arrive: '
      f'{int((ms < ARRIVE_MS).sum())}/{len(ms)} = {100*(ms<ARRIVE_MS).mean():.1f}%')
print(f'    total riskless time per window: p50 {np.median([w["total_ms"] for w in per_window]):.0f} ms '
      f'of 300,000 ms = {100*np.median([w["total_ms"] for w in per_window])/300000:.3f}% of the window')

sz = np.array([w['msz'] for w in W if w['msz'] is not None], float)
print(f'\n(2) MIN TOUCH SIZE ACROSS THE TWO LEGS (the binding leg, worst point in the interval)')
print(f'    shares: p10 {np.percentile(sz,10):.0f}  p50 {np.percentile(sz,50):.0f}  '
      f'p90 {np.percentile(sz,90):.0f}  max {sz.max():.0f}')
print(f'    at the 5-share venue minimum, {int((sz>=5).sum())}/{len(sz)} intervals are even tradeable; '
      f'{int((sz>=20).sum())} carry 20+ shares')

print(f'\n(3) COUNT PER WINDOW')
print(f'    {"window":16s}{"legs":10s}{"n":>4}{"total ms":>10}{"best cost":>11}{"gap $":>9}{"pay":>5}')
for w in per_window:
    print(f'    {f(w["ep15"]):16s}{w["legs"]:10s}{w["n"]:4d}{w["total_ms"]:10.0f}{w["best"]:11.4f}'
          f'{w["gap"]:+9.2f}{(str(w["pay"]) if w["pay"] is not None else "-"):>5}'
          + ('   <- |gap| < $5, leg ORDER is inside the reference resolution' if abs(w['gap']) < 5 else ''))

print(f'\n(4) WOULD A "FIRE BOTH, ARRIVE +{ARRIVE_MS} ms" PAIR HAVE FILLED?  (FAK within one tick, ef_persist rule)')
b = sum(1 for w in W if w['f15'] and w['f5']); o15 = sum(1 for w in W if w['f15'] and not w['f5'])
o5 = sum(1 for w in W if w['f5'] and not w['f15']); nn = sum(1 for w in W if not w['f15'] and not w['f5'])
n = len(W)
print(f'    both legs   {b:4d}/{n} = {100*b/n:5.1f}%   <- the only outcome that is actually riskless')
print(f'    15m only    {o15:4d}/{n} = {100*o15/n:5.1f}%   outright long the 15m leg')
print(f'    5m only     {o5:4d}/{n} = {100*o5/n:5.1f}%   outright long the 5m leg')
print(f'    neither     {nn:4d}/{n} = {100*nn/n:5.1f}%')
print(f'    per leg: 15m fills {100*np.mean([w["f15"] for w in W]):.1f}%, 5m fills {100*np.mean([w["f5"] for w in W]):.1f}%')

print(f'\n(5) THE SINGLE-LEG OUTCOME - what the 15m leg alone is worth when the 5m leg misses')
sl = [w for w in W if w['f15'] and not w['f5'] and w['w15'] is not None]
if sl:
    cost15 = np.array([w['a15'] + fee(w['a15']) for w in sl]); win = np.array([w['w15'] for w in sl], float)
    per1 = (win - cost15) / cost15
    print(f'    n {len(sl)}, 15m leg right {100*win.mean():.1f}%, mean cost {cost15.mean():.3f}, '
          f'capital-weighted per $1 {np.sum(win-cost15)/np.sum(cost15):+.3f}'
          + ('  *n<60, not a reading' if len(sl) < 60 else ''))
else:
    print('    no graded 15m-only case in this sample')
al = [w for w in W if w['w15'] is not None]
if al:
    c15 = np.array([w['a15'] + fee(w['a15']) for w in al]); w15 = np.array([w['w15'] for w in al], float)
    print(f'    for reference, the 15m leg on EVERY riskless interval regardless of fill: n {len(al)}, '
          f'right {100*w15.mean():.1f}%, per $1 {np.sum(w15-c15)/np.sum(c15):+.3f}')
print(f'\n    A pair that legs is not the trade that was measured. {100*(o15+o5)/n:.1f}% of these intervals '
      f'turn into an outright at +{ARRIVE_MS} ms.')
