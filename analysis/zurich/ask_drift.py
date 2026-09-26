"""Did we fire EARLIER? Measure the ask AFTER the fire, not the book age before it. Read-only.

V, 09-24: book_age is the wrong metric for "sooner" - firing right after a Binance tick means firing
BEFORE Polymarket re-quotes, so the book is older by construction. The test that does discriminate:
if we are earlier, the ask we paid should RISE afterwards, because the market has not moved yet.

Per EF order: (ask at fire+1s) - signal_ask and (ask at fire+2s) - signal_ask, in ticks of 0.01,
taken from tape1s on the SAME side (up_ask for UP, dn_ask for DOWN). Reports the share of orders that
rose by >=1 tick and the mean rise.

Usage: ask_drift.py <since_ts> <until_ts|-> <label>
"""
import sqlite3, json, sys, statistics as st
DB = '/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
since = float(sys.argv[1]); until = float(sys.argv[2]) if sys.argv[2] != '-' else 1e18
label = sys.argv[3] if len(sys.argv) > 3 else ''
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
tape = {r['ts']: r for r in c.execute('SELECT ts,up_ask,dn_ask FROM tape1s')}

def ask_at(ts, side):
    """Nearest tape1s row at or after ts, within 3 s. None if the tape has a hole there."""
    for t in range(int(ts), int(ts) + 4):
        r = tape.get(t)
        if r is None: continue
        v = r['up_ask'] if side == 'UP' else r['dn_ask']
        if v is not None: return float(v)
    return None

# Two baselines, because they are NOT interchangeable:
#   vs signal_quote - what V asked for, but signal_quote is the EXECUTOR's read and the tape is a 1 Hz
#     snapshot taken on the full pass. At the fire second itself the median gap between them is already
#     0.050 (5 ticks), so a "+6 tick rise" is partly that offset, not market movement.
#   vs the tape's OWN ask at the fire second - same source at both ends, so the offset cancels and what
#     is left is the actual move after we fired. This is the one that answers "were we earlier".
d1, d2, t1, t2, n, miss = [], [], [], [], 0, 0
for r in c.execute("SELECT epoch,ts,timing_json FROM orders WHERE kind='EF' AND ts>=? AND ts<? ORDER BY ts", (since, until)):
    t = json.loads(r['timing_json']) if r['timing_json'] else {}
    sq = t.get('signal_quote')
    side = (c.execute("SELECT side FROM signals WHERE epoch=? AND kind='EF' LIMIT 1", (r['epoch'],)).fetchone() or [None])[0]
    if not isinstance(sq, (int, float)) or side is None: continue
    n += 1
    a0, a1, a2 = ask_at(r['ts'], side), ask_at(r['ts'] + 1, side), ask_at(r['ts'] + 2, side)
    if a1 is None or a2 is None: miss += 1; continue
    d1.append((a1 - sq) / 0.01); d2.append((a2 - sq) / 0.01)
    if a0 is not None: t1.append((a1 - a0) / 0.01); t2.append((a2 - a0) / 0.01)
def line(tag, v):
    if not v: return f'  {tag}: no data'
    rose = sum(1 for x in v if x >= 1.0)
    return (f'  {tag}: mean {st.mean(v):+.3f} ticks | median {st.median(v):+.2f} | '
            f'rose >=1 tick {rose}/{len(v)} = {rose/len(v)*100:.1f}% | n {len(v)}')
print(f'--- {label} --- EF orders {n}, usable {len(d1)}, tape gaps {miss}')
print(line('vs signal_ask  +1s', d1))
print(line('vs signal_ask  +2s', d2))
print(line('vs tape@fire   +1s', t1))
print(line('vs tape@fire   +2s', t2))
