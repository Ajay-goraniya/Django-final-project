"""Zurich decide-mode comparison: the five metrics V asked for, over one build window. Read-only.

Usage: decide_mode_metrics.py <since_ts> [<until_ts>] [label]
book_age_ms and decision_ms come from orders.timing_json; the signal-ask-vs-fill gap is
(fill price - timing.signal_quote) in ticks of 0.01; refusals/partials are read off order status and
the fill vs plan.max_shares. CPU is measured separately (out/cpu5.py) because it is not in the journal.
"""
import sqlite3, json, sys, statistics as st
DB='/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3'
since=float(sys.argv[1]); until=float(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2]!='-' else 1e18
label=sys.argv[3] if len(sys.argv)>3 else ''
c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True); c.row_factory=sqlite3.Row
def pct(v,q):
    if not v: return None
    v=sorted(v); i=min(len(v)-1,int(round(q*(len(v)-1)))); return v[i]
book=[]; dec=[]; ticks=[]; statuses={}; partial=0; filled=0
for r in c.execute("SELECT id,status,plan,timing_json FROM orders WHERE kind='EF' AND ts>=? AND ts<?",(since,until)):
    statuses[r['status']]=statuses.get(r['status'],0)+1
    t=json.loads(r['timing_json']) if r['timing_json'] else {}
    if isinstance(t.get('book_age_ms'),(int,float)): book.append(t['book_age_ms'])
    if isinstance(t.get('decision_ms'),(int,float)): dec.append(t['decision_ms'])
    if r['status']!='FILLED': continue
    filled+=1
    f=c.execute('SELECT sum(shares) sh,sum(spent) sp FROM fills WHERE order_id=?',(r['id'],)).fetchone()
    pl=json.loads(r['plan']) or {}
    if f and f['sh']:
        px=f['sp']/f['sh']; sq=t.get('signal_quote')
        if isinstance(sq,(int,float)) and sq: ticks.append((px-sq)/0.01)
        if pl.get('max_shares') and f['sh'] < pl['max_shares']*0.999: partial+=1
n=sum(statuses.values())
print(f"--- {label} --- EF orders {n}")
print(f"book_age_ms at fire  p50 {pct(book,.5):.1f}  p90 {pct(book,.9):.1f}  n {len(book)}" if book else "book_age_ms: none")
print(f"decision_ms          p50 {pct(dec,.5):.2f}  p90 {pct(dec,.9):.2f}  n {len(dec)}" if dec else "decision_ms: none")
if ticks:
    print(f"signal-ask -> fill   p50 {pct(ticks,.5):+.2f} ticks  p90 {pct(ticks,.9):+.2f}  mean {st.mean(ticks):+.2f}  n {len(ticks)}")
else: print("signal-ask -> fill: none")
print(f"statuses {statuses} | filled {filled} | partial fills {partial} | refusals {n-filled}")
