#!/usr/bin/env python3
"""Per-UTC-day frequency / directional accuracy for each replayed model."""
import sqlite3, datetime, sys, collections
import pathlib
RUNS = pathlib.Path(__file__).resolve().parents[1] / 'runs'
def day(ms): return datetime.datetime.utcfromtimestamp(ms/1000).strftime('%Y-%m-%d')
print(f"{'model':6}{'day':12}{'candles':>8}{'fires':>7}{'freq/100':>10}{'acc':>8}{'n':>6}{'fire@s':>8}")
for tag in ('v9_4','v9_5','b36'):
    try: con=sqlite3.connect(f"file:{RUNS}/week_{tag}.sqlite3?mode=ro",uri=True,timeout=20)
    except Exception as e: print(tag,'ERR',e); continue
    cd=collections.Counter(); fi=collections.Counter(); ok=collections.Counter()
    gr=collections.Counter(); sec=collections.Counter()
    for cid,a in con.execute("select candle_id,actual from candles where actual is not null and actual!=''"):
        cd[day(cid)]+=1
    for cid,d,a,s in con.execute("select candle_id,direction,actual,seconds_into_candle from trades where kind='EF'"):
        k=day(cid); fi[k]+=1; sec[k]+=(s or 0)
        if a: gr[k]+=1; ok[k]+=int(d==a)
    for k in sorted(cd):
        f=fi[k]; c=cd[k]; g=gr[k]
        print(f"{tag:6}{k:12}{c:8}{f:7}{(100*f/c if c else 0):10.1f}"
              f"{(100*ok[k]/g if g else float('nan')):7.1f}%{g:6}{(sec[k]/f if f else 0):8.1f}")
    tf=sum(fi.values()); tc=sum(cd.values()); tg=sum(gr.values()); to=sum(ok.values())
    print(f"{tag:6}{'POOLED':12}{tc:8}{tf:7}{(100*tf/tc if tc else 0):10.1f}"
          f"{(100*to/tg if tg else float('nan')):7.1f}%{tg:6}")
    print()
