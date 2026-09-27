"""Settlement-rule audit (owner, 09-27 03:3x). How well does a TWAP60-vs-TWAP60 direction computed from
Binance 1 s closes agree with Polymarket's OWN resolution, and how much worse is the raw sec-299 close?

Truth = venues.outcome (Polymarket's resolution) on the BTC 5m market, which is the only source on this
box with thousands of settled epochs. Computed from the same 1 s klines every test here uses.
"""
import sqlite3, numpy as np, datetime as dt
K='/tmp/ll/klines30.sqlite3'; V='/tmp/venues_ro.sqlite3'
c=sqlite3.connect(f'file:{K}?mode=ro',uri=True)
n,t0,t1=c.execute('SELECT count(*),min(ts),max(ts) FROM k').fetchone()
assert t1-t0+1==n
px=np.full(n,np.nan)
for ts,b in c.execute('SELECT ts,btc FROM k ORDER BY ts'): px[ts-t0]=b
try:
    v=sqlite3.connect(f'file:{V}?mode=ro',uri=True); out=dict(v.execute('SELECT epoch,actual FROM outcome'))
except Exception as e:
    print('venues snapshot unreadable:',repr(e)[:70]); raise SystemExit
eps=[e for e in sorted(out) if e-60>=t0 and e+300<=t1 and out[e] in ('UP','DOWN')]
rows=[]
for e in eps:
    i=e-t0
    line=px[i-60:i].mean(); fin=px[i+240:i+300].mean(); last=px[i+299]
    if not (np.isfinite(line) and np.isfinite(fin) and np.isfinite(last)): continue
    rows.append((out[e]=='UP', fin>=line, last>=line))
a=np.array(rows)
f=lambda t: dt.datetime.fromtimestamp(t,dt.timezone.utc).strftime('%m-%d')
print(f'BTC 5m, truth = venues.outcome, {len(a)} settled epochs {f(eps[0])}..{f(eps[-1])}')
print(f'  SETTLEMENT RULE  closing TWAP60 vs opening TWAP60 : {100*np.mean(a[:,0]==a[:,1]):.2f}% agreement')
print(f'  WRONG (old label) sec-299 close vs opening TWAP60 : {100*np.mean(a[:,0]==a[:,2]):.2f}% agreement')
dis=int(np.sum(a[:,1]!=a[:,2]))
print(f'  the two labels differ on {dis} of {len(a)} epochs ({100*dis/len(a):.1f}%)')
