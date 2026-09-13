"""FAIR STATES: all runs compared over the SAME window - starting when the NEWEST run started.

The window opens at max(each run's first record), so every run is judged on the same candles.
Pass a UTC epoch-ms or 'tokyo' to override the start.
"""
import sqlite3, json, base64, urllib.request, time, sys
S="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
V12="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/v12/results/v12_poly_weekend.sqlite3"
TOKYO_START=1788990900000

def first_ms():
    st={}
    try:
        c=sqlite3.connect(f"file:{S}/b10.sqlite3?mode=ro",uri=True)
        st["Predict.fun paper (v10)"]=c.execute("select min(candle_id) from ef_predictions").fetchone()[0]
    except Exception: pass
    try:
        c=sqlite3.connect("file:/tmp/v10_long4.sqlite3?mode=ro",uri=True)
        st["Polymarket paper (v10)"]=(c.execute("select min(candle_epoch) from trades").fetchone()[0] or 0)*1000
    except Exception: pass
    try:
        c=sqlite3.connect(f"file:{V12}?mode=ro",uri=True)
        v=c.execute("select min(candle_epoch) from trades").fetchone()[0]
        if v: st["Polymarket v12 lane"]=v*1000
    except Exception: pass
    st["Tokyo live (v11)"]=TOKYO_START
    return st

starts=first_ms()
arg=sys.argv[1] if len(sys.argv)>1 else None
t0=TOKYO_START if arg=="tokyo" else (int(arg) if arg else max(starts.values()))
newest=max(starts,key=lambda k:starts[k])

def cost(a,f): return a/(1-f*(1-a))
rows=[]

w=l=0; pn=0.0; op=0
try:
    c=sqlite3.connect(f"file:{S}/b10.sqlite3?mode=ro",uri=True)
    for cor,act,ft in c.execute("select correct,actual,features from ef_predictions where candle_id>=?",(t0,)):
        a=json.loads(ft or "{}").get("ef_v10_ask") or 0.5
        if act in (None,""): op+=1; continue
        if cor: w+=1; pn+=10*(1/cost(a,0.02)-1)
        else: l+=1; pn-=10
except Exception: pass
rows.append(("Predict.fun paper (v10)",w,l,op,pn,None))

try:
    c=sqlite3.connect("file:/tmp/v10_long4.sqlite3?mode=ro",uri=True)
    t=c.execute("select sum(win),sum(win is not null),sum(pnl),sum(win is null) from trades where candle_epoch>=? and ask>0.02",(t0//1000,)).fetchone()
    rows.append(("Polymarket paper (v10)",t[0] or 0,(t[1] or 0)-(t[0] or 0),t[3] or 0,t[2] or 0.0,None))
except Exception: rows.append(("Polymarket paper (v10)",0,0,0,0.0,None))

try:
    c=sqlite3.connect(f"file:{V12}?mode=ro",uri=True)
    t=c.execute("select sum(win),sum(win is not null),sum(pnl),sum(case when win is null then 1 else 0 end) from trades where candle_epoch>=?",(t0//1000,)).fetchone()
    rows.append(("Polymarket v12 lane (paper exec)",t[0] or 0,(t[1] or 0)-(t[0] or 0),t[3] or 0,t[2] or 0.0,None))
except Exception: rows.append(("Polymarket v12 lane (paper exec)",0,0,0,0.0,None))

try:
    url,user,pw=[x.strip() for x in open(f"{S}/v11/launch/tokyo.auth")][:3]
    hdr={"Authorization":"Basic "+base64.b64encode(f"{user}:{pw}".encode()).decode()}
    st=json.load(urllib.request.urlopen(urllib.request.Request(url+"/api/state",headers=hdr),timeout=25))
    got=[]
    for kind in ("EF","REVERSAL"):
        for off in range(0,400,50):
            d=json.load(urllib.request.urlopen(urllib.request.Request(f"{url}/api/orders?kind={kind}&limit=50&offset={off}",headers=hdr),timeout=25))
            rs=d.get("rows") or []
            got+=rs
            if not rs or (d.get("total") or 0)<=off+50: break
    seen=[r for r in got if (r.get("ts_ms") or 0)>=t0 and r.get("filled")]
    gw=sum(1 for r in seen if r.get("correct")); gl=sum(1 for r in seen if r.get("correct") is False)
    pnl=sum(r.get("pnl") or 0.0 for r in seen); openn=sum(1 for r in seen if r.get("correct") is None)
    cap=st["capital"]
    rows.append(("Tokyo live (v11)",gw,gl,openn,pnl*10,dict(wallet=cap["wallet"],equity=cap["equity"])))
except Exception as e:
    rows.append(("Tokyo live (v11)",0,0,0,0.0,dict(wallet=float('nan'),equity=float('nan'))))

hrs=(time.time()*1000-t0)/3600000
print(f"FAIR STATES {time.strftime('%H:%M UTC',time.gmtime())} | window opens with the NEWEST run: {newest}, {time.strftime('%m-%d %H:%M UTC',time.gmtime(t0/1000))} ({hrs:.1f} h)")
print("| run | W/L | acc | open | PnL @$10 |")
for name,w_,l_,op_,pn_,x in rows:
    n=w_+l_; acc=f"{w_/n*100:.0f}%" if n else "-"
    extra=f" (real {pn_/10:+.2f} at $1; wallet {x['wallet']:.2f} equity {x['equity']:.2f})" if x else ""
    print(f"| {name} | {w_}/{l_} | {acc} | {op_} | {pn_:+.1f}{extra} |")
