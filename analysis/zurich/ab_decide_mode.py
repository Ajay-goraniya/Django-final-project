"""A/B report: poll vs event, split by each EF order's OWN feed_timing.decide_mode (13.1.2). Read-only.

Arm membership comes from the order's journalled decision, not from flip bookkeeping, so a missed or
mistimed flip cannot mis-assign an order. Orders whose decision predates 13.1.2 carry no feed_timing
and are excluded rather than guessed at.
"""
import sqlite3, json, sys, statistics as st
DB = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
since = float(sys.argv[1])
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
arms = {}
no_ft = 0
for r in c.execute("SELECT epoch,ts,timing_json FROM orders WHERE kind='EF' AND ts>=? ORDER BY ts", (since,)):
    s = c.execute("SELECT decision FROM signals WHERE epoch=? AND kind='EF' LIMIT 1", (r['epoch'],)).fetchone()
    d = json.loads(s['decision']) if s and s['decision'] else {}
    ft = d.get('feed_timing') or {}
    mode = ft.get('decide_mode')
    if not mode: no_ft += 1; continue
    a = arms.setdefault(mode, dict(eps=set(), newest=[], spot_rx=[], spot_exch=[], book=[]))
    a['eps'].add(r['epoch'])
    for key, dest in (('newest_rx_age_ms', 'newest'), ('spot_rx_age_ms', 'spot_rx'), ('spot_exch_age_ms', 'spot_exch')):
        v = ft.get(key)
        if isinstance(v, (int, float)): a[dest].append(float(v))
    t = json.loads(r['timing_json']) if r['timing_json'] else {}
    if isinstance(t.get('book_age_ms'), (int, float)): a['book'].append(t['book_age_ms'])
def pct(v, q):
    if not v: return None
    v = sorted(v); return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]
def row(tag, v):
    return f'{tag:>18}: p50 {pct(v,.5):8.1f}  p90 {pct(v,.9):8.1f}  n {len(v)}' if v else f'{tag:>18}: none'
print(f'orders with no feed_timing (pre-13.1.2), excluded: {no_ft}')
for mode in ('poll', 'event'):
    a = arms.get(mode)
    if not a: print(f'\n=== {mode.upper()} === no orders yet'); continue
    print(f'\n=== {mode.upper()} === EF orders {len(a["eps"])} distinct epochs')
    print(' ', row('newest_rx_age_ms', a['newest']))
    print(' ', row('spot_rx_age_ms', a['spot_rx']))
    print(' ', row('spot_exch_age_ms', a['spot_exch']))
    print(' ', row('book_age_ms', a['book']))
