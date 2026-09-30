#!/usr/bin/env python3
"""LIVE TEST report - counts ONLY from the baseline in /home/ubuntu/pm_ef3/live_test_baseline.json.
Nothing was deleted to make this clean: the 09-28 incident orders and the forward shadow are intact,
this just starts the clock at the baseline so the owner sees his own run and nothing else. READ-ONLY."""
import sqlite3, json, datetime as dt, time
B=json.load(open('/home/ubuntu/pm_ef3/live_test_baseline.json'))
T=B['baseline_epoch']
c=sqlite3.connect('file:/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3?mode=ro',uri=True)
f=lambda t: dt.datetime.fromtimestamp(t,dt.UTC).strftime('%m-%d %H:%M:%S')
print(f"LIVE TEST since {B['baseline_utc']} UTC   (ef_engine {B['ef_engine']}, stake ${B['next_stake']:.2f}, sl ${B['sl']:.0f})")
m=c.execute("SELECT v FROM meta WHERE k='master'").fetchone()[0]
print(f"  master now = {m}" + ("   <- LIVE, real money" if m=='true' else "   <- still off, every fill is paper"))
rows=c.execute("""SELECT o.id,o.epoch,o.ts,o.status,o.plan FROM orders o
                  WHERE o.lane='LIVE' AND o.ts>? ORDER BY o.ts""",(T,)).fetchall()
if not rows:
    print('  no LIVE orders yet since the baseline')
else:
    tot=0.0; eps=set()
    print('  time         candle  side  ask   status    shares   spent   settled     pnl')
    for oid,ep,ts,st,plan in rows:
        pl=json.loads(plan) if plan else {}
        sig=c.execute("SELECT side FROM signals WHERE epoch=? AND kind='EF'",(ep,)).fetchone()
        sh,sp=c.execute("SELECT sum(shares),sum(spent) FROM fills WHERE order_id=?",(oid,)).fetchone()
        r=c.execute("SELECT actual,pnl FROM results WHERE epoch=?",(ep,)).fetchone()
        n=lambda v,w='.4f': ' n/a' if v is None else format(v,w)
        print(f"  {f(ts)} {f(ep)[6:11]}  {(sig[0] if sig else '?'):4s} {n(pl.get('quote'),'.2f')}  {st:9s} "
              f"{n(sh):>8s} {n(sp):>7s}   {(r[0] if r else 'open'):5s} {n(r[1] if r else None,'+.4f'):>8s}")
        if r and r[1] is not None and ep not in eps: tot+=r[1]; eps.add(ep)
    print(f'  {len(eps)} settled candles, realised ${tot:+.4f}  (one pnl per candle, retries not double counted)')
d=c.execute("SELECT count(*) FROM orders WHERE lane='PAPER' AND ts>?",(T,)).fetchone()[0]
print(f'  paper orders since the baseline: {d}')
