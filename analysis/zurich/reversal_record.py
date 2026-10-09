#!/usr/bin/env python3
"""The REVERSAL lane's full record on Zurich. READ-ONLY on the engine journal and the gamma mirror.

Source of record: the engine's own `calls` table (epoch, kind, side, quote, sec, actual), joined to
`orders`/`fills` to say which decisions became REAL venue fills and which were paper. Graded on
POLYMARKET's resolution - the gamma mirror - with the journal's own `actual` column cross-checked
against it rather than trusted, because grading a Polymarket trade on a Binance close inflates it.
"""
import json, math, sqlite3, sys
import datetime as dt

sys.path.insert(0, '/home/ubuntu/claude-work/repo/analysis/zurich')
from ef2_model import per1                    # fee-exact $ per $1 staked, the house function

ENG = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
GAMMA = '/home/ubuntu/pm_ef3/gamma_zurich.sqlite3'
STAKE, BAR = 5.0, 60
NOW = int(dt.datetime.now(dt.UTC).timestamp())

e = sqlite3.connect(f'file:{ENG}?mode=ro', uri=True); e.row_factory = sqlite3.Row
g = sqlite3.connect(f'file:{GAMMA}?mode=ro', uri=True)

GM = {r[0]: r[1] for r in g.execute('select epoch, outcome from mkt where outcome is not null')}

# which REVERSAL decisions became orders, and were they live or paper
ORD = {}
for r in e.execute("select epoch, lane, status, plan, kind from orders where kind='REVERSAL'"):
    d = ORD.setdefault(r['epoch'], dict(lanes=set(), status=set(), amount=0.0, n=0))
    d['lanes'].add(r['lane']); d['status'].add(r['status']); d['n'] += 1
    try: d['amount'] += float(json.loads(r['plan']).get('amount') or 0)
    except Exception: pass
FILLED = {ep for ep, d in ORD.items() if 'FILLED' in d['status']}

ROWS = []
for r in e.execute("select * from calls where kind='REVERSAL' order by ts"):
    ep = r['epoch']
    gm = GM.get(ep)
    out = gm or r['actual']                     # prefer Polymarket's own resolution
    if not out or r['quote'] is None: continue
    q = float(r['quote'])
    win = 1 if r['side'] == out else 0
    o = ORD.get(ep)
    ROWS.append(dict(ep=ep, ts=float(r['ts']), side=r['side'], q=q, sec=float(r['sec'] or 0),
                     out=out, win=win, src=('gamma' if gm else 'journal'),
                     live=bool(o and 'LIVE' in o['lanes']),
                     filled=ep in FILLED, status=r['status'],
                     per=float(per1(win, q)), day=dt.datetime.fromtimestamp(ep, dt.UTC).strftime('%m-%d')))

agree = sum(1 for x in ROWS if x['src'] == 'gamma' and
            GM.get(x['ep']) == (e.execute('select actual from calls where epoch=? and kind=?',
                                          (x['ep'], 'REVERSAL')).fetchone() or [None])[0])
n_g = sum(1 for x in ROWS if x['src'] == 'gamma')

L = [f'REVERSAL LANE - THE FULL ZURICH RECORD. READ-ONLY. {dt.datetime.now(dt.UTC):%F %T} UTC',
     'Source: the engine journal\'s own `calls` table (kind=REVERSAL), joined to orders/fills for',
     'the real-vs-paper split. Graded on POLYMARKET\'s resolution from the gamma mirror.',
     f'GRADING CROSS-CHECK: {n_g} of {len(ROWS)} decisions have a gamma outcome, and on those the',
     f'journal\'s own `actual` column agrees with Polymarket on {agree} of {n_g}. Where gamma has no',
     f'row the journal value is used and the row is marked - it is never assumed.', '']

def cell(rows):
    n = len(rows); w = sum(x['win'] for x in rows); l = n - w
    per = sum(x['per'] for x in rows) / n if n else 0.0
    return n, w, l, STAKE * sum(x['per'] for x in rows), per

def line(lbl, rows):
    n, w, l, d, per = cell(rows)
    return (f'   {lbl:22s} {n:5d} {f"{w}/{l}":>8s} {d:+9.2f} {per:+9.4f}  '
            f'{"INSUFFICIENT (<60)" if n < BAR else ""}')

LIVE = [x for x in ROWS if x['live']]
PAP = [x for x in ROWS if not x['live']]
L += ['== ALL TIME', f'   {"set":22s} {"n":>5s} {"W/L":>8s} {"$@5":>9s} {"per $1":>9s}  flag',
      line('all decisions', ROWS),
      line('REAL venue fills', LIVE),
      line('paper only', PAP),
      line('order FILLED', [x for x in ROWS if x['filled']]),
      line('no order/unfilled', [x for x in ROWS if not x['filled']]), '']
if ROWS:
    L += [f'   window: {dt.datetime.fromtimestamp(min(x["ep"] for x in ROWS), dt.UTC):%m-%d %H:%M} .. '
          f'{dt.datetime.fromtimestamp(max(x["ep"] for x in ROWS), dt.UTC):%m-%d %H:%M} UTC',
          f'   $ at $5 is the fee-exact per-$1 scaled to a $5 stake, so it is comparable across rows;',
          f'   the lane\'s own plans staked {min(ORD[x["ep"]]["amount"] for x in ROWS if x["ep"] in ORD):.2f}'
          f'-{max(ORD[x["ep"]]["amount"] for x in ORD and [y for y in ROWS if y["ep"] in ORD]):.2f} '
          f'per order, which is why the normalisation matters.' if ORD else '', '']

ts = sorted(ROWS, key=lambda x: x['ts'])
k = (len(ts) + 1) // 2
L += ['== BOTH HALVES (by time)',
      f'   {"half":22s} {"n":>5s} {"W/L":>8s} {"$@5":>9s} {"per $1":>9s}  flag',
      line('H1', ts[:k]), line('H2', ts[k:]), '']

cut = NOW - 7 * 86400
L += ['== LAST 7 DAYS vs EVERYTHING BEFORE',
      f'   {"set":22s} {"n":>5s} {"W/L":>8s} {"$@5":>9s} {"per $1":>9s}  flag',
      line('last 7 days', [x for x in ROWS if x['ep'] >= cut]),
      line('before that', [x for x in ROWS if x['ep'] < cut]), '']

L += ['== PER DAY', f'   {"day":8s} {"n":>4s} {"W/L":>8s} {"$@5":>9s} {"per $1":>9s} {"real":>5s}  flag']
for d in sorted({x['day'] for x in ROWS}):
    rs = [x for x in ROWS if x['day'] == d]
    n, w, l, dd, per = cell(rs)
    L.append(f'   {d:8s} {n:4d} {f"{w}/{l}":>8s} {dd:+9.2f} {per:+9.4f} '
             f'{sum(1 for x in rs if x["live"]):5d}  {"INSUFFICIENT (<60)" if n < BAR else ""}')

L += ['', '== THE PRICE BAND IT BUYS AT (quote at the call)',
      f'   {"band":12s} {"n":>4s} {"W/L":>8s} {"$@5":>9s} {"per $1":>9s}  flag']
BANDS = [(0.0, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 1.01)]
for lo, hi in BANDS:
    rs = [x for x in ROWS if lo <= x['q'] < hi]
    if not rs:
        L.append(f'   {f"{lo:.2f}-{hi:.2f}":12s} {0:4d}  no decisions'); continue
    n, w, l, dd, per = cell(rs)
    L.append(f'   {f"{lo:.2f}-{hi:.2f}":12s} {n:4d} {f"{w}/{l}":>8s} {dd:+9.2f} {per:+9.4f}  '
             f'{"INSUFFICIENT (<60)" if n < BAR else ""}')
qs = sorted(x['q'] for x in ROWS)
if qs:
    L.append(f'   quote distribution: min {qs[0]:.2f} p25 {qs[len(qs)//4]:.2f} MED {qs[len(qs)//2]:.2f} '
             f'p75 {qs[3*len(qs)//4]:.2f} max {qs[-1]:.2f}; mean entry sec '
             f'{sum(x["sec"] for x in ROWS)/len(ROWS):.0f}')

L += ['', '== IS REVERSAL A SHADOW ARM TODAY?',
      '   NO. The ef3/FAV shadow carries 23 arms (A_v0_m02_S150, B_raw25_S60, C_fixed15, D/D2, E1-E5,',
      '   F/F25/F75, FAV, FAV_all, FAV_mid, FAV_ref, PFAV, PFAV50, PFAV_THRU, PFAV_taker, S_fixed_top20,',
      '   S_raw_top20) and REVERSAL is not among them. So Zurich has the SAME GAP London has: when the',
      '   lane is off there is no shadow recording what it would have done. Everything above comes from',
      '   the engine journal while the lane was actually deciding, not from a shadow.']
rec = [x for x in ROWS if x['ep'] >= int(dt.datetime(2026, 9, 29, tzinfo=dt.UTC).timestamp())]
n, w, l, dd, per = cell(rec)
L.append(f'   09-29..now from the journal: n {n}'
         + (f', {w}/{l}, {dd:+.2f} at $5, {per:+.4f} per $1  INSUFFICIENT (<60)' if n else
            ' - NO REVERSAL decisions at all in that window (the lane has been off).'))
print('\n'.join(L))
