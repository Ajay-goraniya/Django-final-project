#!/usr/bin/env python3
"""Export one row per BTC 15m window that ever went riskless against its last 5m candle. READ-ONLY.

V asked for: ep15, the first riskless second, a15, a5, the legs, sz15. Same sources and same arithmetic as
arb_5m_15m.py (recorder 1 Hz btc15 book with sizes; engine tape1s BTC-5m asks read at the SAME second; lines
from tape1s.ref_px, the Chainlink reference the venue settles on) - this only changes the output shape.

Two columns are here because of the 09-28 arb_trades_check result: `gap` = L15 - L5 in dollars, and
`gap_lt5` . The single 0-payoff window in 763 (09-22 15:15) had a gap of $2.33, i.e. the LINE ORDERING was
inside the reference's own resolution, so the sign of the gap is what decides which legs you buy and a tiny
gap makes that decision untrustworthy. Any consumer of this file should filter on |gap|.

sz5 is NOT available: tape1s carries up_ask/dn_ask with no sizes. The 15m size is the touch size only.

FRESHNESS GATE (added 09-28 05:3x, and it changes the answer). The recorder stores `up_snap_age_s` /
`dn_snap_age_s` = the age of the last FULL book snapshot, because a price_change delta does not resync the
book. Checked against the dual-market ms probe, which holds an independent WS subscription to the same btc15
tokens, over 20,205 shared seconds:

    snap age <= 3 s   mean |recorder - probe|  0.71c   >=5c on  2.0%
    snap age 3-15 s   mean                     0.79c   >=5c on  3.2%
    snap age 15-60 s  mean                     8.81c   >=5c on 34.2%
    snap age > 60 s   mean                    15.62c   >=5c on 37.5%   p90 53c

and the recorder's own resync loop had a bug that made btc15 exceed 60 s routinely in exactly this window
(mean snap age by candle minute: 4.9 s at min 10, then 15.3 / 41.2 / 76.1 / 125.5 s at minutes 11-14; fixed
in recorder.py the same hour). So every 15m quote used here must be gated on snapshot age, default 15 s. The
engine's 5m leg is NOT affected - tape1s vs the same probe is 0.79c mean, >=5c on 3.0%, flat across candle
minutes 0-3.

usage: arb_windows_csv.py [OUT.csv] [MAX_SNAP_AGE_S]
"""
import sys, csv, sqlite3, datetime as dt, collections, numpy as np
sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from arb_5m_15m import MULTI, LIVE, fee, outcomes5

OUT = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/claude-work/repo/analysis/zurich/arb_windows.csv'
MAXAGE = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
COLS = ['ep15', 'day', 'utc15', 'first_riskless_ts', 'sec', 'leg15', 'leg5', 'a15', 'a5', 'cost', 'sz15',
        'notional15', 'age15', 'gap', 'gap_lt5', 'n_riskless_secs', 'best_cost', 'pay', 'o15', 'o5']

mc = sqlite3.connect(f'file:{MULTI}?mode=ro', uri=True)
lc = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True)
res15 = dict(mc.execute("SELECT epoch,outcome FROM resolutions WHERE market='btc15'").fetchall())
res5 = outcomes5()
b15 = {int(ts): (int(ep), ua, uz, da, dz, ag, agd) for ts, ep, ua, uz, da, dz, ag, agd in mc.execute(
    "SELECT ts,epoch,up_ask,up_ask_sz,dn_ask,dn_ask_sz,up_snap_age_s,dn_snap_age_s FROM books "
    "WHERE market='btc15'")}
tape, ref = {}, {}
for ts, ua, da, rp in lc.execute('SELECT ts,up_ask,dn_ask,ref_px FROM tape1s WHERE ts>=? ORDER BY ts',
                                 (min(b15) - 700,)):
    if ua is not None and da is not None: tape[int(ts)] = (ua, da)
    if rp is not None: ref[int(ts)] = float(rp)

def line(ep):
    v = [ref[ep - k] for k in range(1, 61) if (ep - k) in ref]
    return (sum(v) / len(v)) if len(v) >= 45 else None

rows, skip = [], collections.Counter()
for ep15 in sorted({v[0] for v in b15.values()}):
    ep5 = ep15 + 600
    L15, L5 = line(ep15), line(ep5)
    if L15 is None or L5 is None: skip['no_line'] += 1; continue
    if abs(L15 - L5) < 1e-9: skip['lines_equal'] += 1; continue
    leg15, leg5 = ('UP', 'DOWN') if L15 < L5 else ('DOWN', 'UP')
    o15, o5 = res15.get(ep15), res5.get(ep5)
    hits, hits_raw = [], []
    for s in range(ep5, ep5 + 296):
        if s not in b15 or s not in tape: continue
        ep, ua, uz, da, dz, ag, agd = b15[s]
        if ep != ep15: continue
        a15, z15, age = (ua, uz, ag) if leg15 == 'UP' else (da, dz, agd)
        a5 = tape[s][0] if leg5 == 'UP' else tape[s][1]
        if a15 is None or a5 is None: continue
        if not (0.01 < a15 < 0.99 and 0.01 < a5 < 0.99): continue
        c = a15 + fee(a15) + a5 + fee(a5)
        if c >= 1.0: continue
        hits_raw.append(s)
        if age is None or age > MAXAGE: skip['stale_15m_quote'] += 1; continue
        hits.append((s, a15, a5, c, z15, age))
    if hits_raw: skip['windows_riskless_ungated'] += 1
    if not hits: skip['never_riskless'] += 1; continue
    s, a15, a5, c, z15, age = hits[0]
    pay = ((1 if o15 == leg15 else 0) + (1 if o5 == leg5 else 0)) if (o15 and o5) else ''
    rows.append(dict(ep15=ep15, day=dt.datetime.fromtimestamp(ep15, dt.timezone.utc).strftime('%Y-%m-%d'),
                     utc15=dt.datetime.fromtimestamp(ep15, dt.timezone.utc).strftime('%H:%M'),
                     first_riskless_ts=s, sec=s - ep5, leg15=leg15, leg5=leg5,
                     a15=f'{a15:.3f}', a5=f'{a5:.3f}', cost=f'{c:.4f}',
                     sz15=('' if z15 is None else f'{z15:.0f}'),
                     notional15=('' if z15 is None else f'{z15*a15:.2f}'), age15=f'{age:.1f}',
                     gap=f'{L15-L5:+.2f}', gap_lt5=int(abs(L15 - L5) < 5.0),
                     n_riskless_secs=len(hits), best_cost=f'{min(h[3] for h in hits):.4f}',
                     pay=pay, o15=(o15 or ''), o5=(o5 or '')))

with open(OUT, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader(); w.writerows(rows)
tot = len({v[0] for v in b15.values()})
print(f'wrote {OUT}: {len(rows)} windows of {tot} with a btc15 book, snap age <= {MAXAGE:.0f}s '
      f'({skip["no_line"]} no line, {skip["lines_equal"]} lines equal)')
print(f'  FRESHNESS: {skip["windows_riskless_ungated"]} windows look riskless on the raw book, '
      f'{len(rows)} survive the {MAXAGE:.0f}s gate; {skip["stale_15m_quote"]} individual seconds dropped '
      f'as stale 15m quotes')
if rows:
    g = np.array([abs(float(r['gap'])) for r in rows])
    pays = [r['pay'] for r in rows if r['pay'] != '']
    print(f'  |gap| $: min {g.min():.2f} p50 {np.median(g):.2f} max {g.max():.2f}; '
          f'|gap|<$5 on {sum(int(r["gap_lt5"]) for r in rows)} of {len(rows)}')
    print(f'  first riskless sec p10 {np.percentile([r["sec"] for r in rows],10):.0f} '
          f'p50 {np.median([r["sec"] for r in rows]):.0f} p90 {np.percentile([r["sec"] for r in rows],90):.0f}')
    print(f'  cost p50 {np.median([float(r["cost"]) for r in rows]):.4f}, '
          f'best {min(float(r["best_cost"]) for r in rows):.4f}; '
          f'riskless seconds per window p50 {np.median([r["n_riskless_secs"] for r in rows]):.0f}')
    print(f'  payoff on the graded windows: ' + str(dict(collections.Counter(pays))) + '  (0 would be a break)')
