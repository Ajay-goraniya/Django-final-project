#!/usr/bin/env python3
"""Where signal->venue-ack time goes, from a journal's orders.timing_json. Read-only.
Usage: latency_breakdown.py JOURNAL.sqlite3 [--since EPOCH]"""
import sqlite3,json,sys,statistics as st
jp=sys.argv[1]; since=int(sys.argv[sys.argv.index('--since')+1]) if '--since' in sys.argv else 0
c=sqlite3.connect(f'file:{jp}?mode=ro',uri=True)
rows=[]
for s,ts,tj,att,ep,kind,reason in c.execute("select status,ts,timing_json,attempt,epoch,kind,reason from orders where timing_json is not null and epoch>=?",(since,)):
    try: t=json.loads(tj); t.update(status=s,ts=ts,attempt=att,epoch=ep,kind=kind,reason=reason or ''); rows.append(t)
    except Exception: pass
print(f'{jp}: orders with timing {len(rows)}; status', {s:sum(1 for r in rows if r["status"]==s) for s in sorted({r["status"] for r in rows})})
def q(k,S):
    v=sorted(float(r[k]) for r in S if r.get(k) is not None)
    return f'{k:24s} n={len(v):4d} p50={v[len(v)//2]:7.1f} p90={v[int(.9*len(v))-1]:7.1f} max={v[-1]:7.1f}' if v else f'{k}: none'
KEYS=('decision_ms','quote_wait_ms','sign_ms','final_recheck_ms','fire_to_submit_ms','submit_ms','total_attempt_ms','book_age_ms','pre_submit_book_age_ms')
for k in KEYS: print(q(k,rows))
print('-- attempt 1 only, FILLED vs REJECTED (fire_to_submit_ms / submit_ms)')
for s in ('FILLED','REJECTED'):
    S=[r for r in rows if r['attempt']==1 and r['status']==s]
    if S: print(s, q('fire_to_submit_ms',S)); print(s, q('submit_ms',S))
sig={(e,k):t for e,t,k in c.execute("select epoch,ts,kind from signals")}
d=sorted((r['ts']-sig[(r['epoch'],r['kind'])])*1000 for r in rows if (r['epoch'],r['kind']) in sig and r['attempt']==1)
if d: print(f'signal.ts -> order.ts (attempt 1) n={len(d)} p50={d[len(d)//2]:.0f} p90={d[int(.9*len(d))-1]:.0f} ms')
print('by attempt:',{a:(sum(1 for r in rows if r['attempt']==a),sum(1 for r in rows if r['attempt']==a and r['status']=='FILLED')) for a in sorted({r['attempt'] for r in rows})},'(orders, filled)')
rej={}
for r in rows:
    if r['status']=='REJECTED': k=r['reason'][:60]; rej[k]=rej.get(k,0)+1
for k,n in sorted(rej.items(),key=lambda x:-x[1])[:6]: print(f'  reject x{n}: {k}')
