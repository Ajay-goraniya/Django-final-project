"""FAIR STATES: all three runs over the same window since Tokyo went live (21:55 UTC 09-09)."""
import sqlite3, json, base64, urllib.request, time
S="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
t0=1788990900000
def cost7(q): return q/(1-0.07*(1-q))
rows=[]
p=sqlite3.connect(f"{S}/b10.sqlite3"); w=l=0; pn=0.0; op=0
for cor,act,f in p.execute("select correct,actual,features from ef_predictions where candle_id>=?",(t0,)):
    a=json.loads(f or "{}").get("ef_v10_ask") or 0.5
    if act in (None,""): op+=1; continue
    if cor: w+=1; pn+=10*(1/cost7(a)-1)
    else: l+=1; pn-=10
rows.append(("Predict.fun pnl (v10 paper)",w,l,op,pn,None))
r=sqlite3.connect("/tmp/v10_long4.sqlite3"); t=r.execute("select sum(win), sum(win is not null), sum(pnl), sum(win is null) from trades where candle_epoch>=? and ask>0.02",(t0//1000,)).fetchone()
rows.append(("Polymarket pnl (v10 paper)",t[0] or 0,(t[1] or 0)-(t[0] or 0),t[3] or 0,t[2] or 0,None))
V12="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/v12/results/v12_poly_weekend.sqlite3"
try:
    v=sqlite3.connect(f"file:{V12}?mode=ro",uri=True)
    t=v.execute("select sum(win),count(win),sum(pnl),sum(case when win is null then 1 else 0 end) from trades").fetchone()
    rows.append(("Polymarket v12 lane (paper exec)",t[0] or 0,(t[1] or 0)-(t[0] or 0),t[3] or 0,t[2] or 0.0,None))
except Exception as e:
    rows.append(("Polymarket v12 lane (paper exec)",0,0,0,0.0,None))

url,user,pw=[x.strip() for x in open(f"{S}/v11/launch/tokyo.auth")][:3]
hdr={"Authorization":"Basic "+base64.b64encode(f"{user}:{pw}".encode()).decode()}
st=json.load(urllib.request.urlopen(urllib.request.Request(url+"/api/state",headers=hdr),timeout=25)); pnl=json.load(urllib.request.urlopen(urllib.request.Request(url+"/api/pnl",headers=hdr),timeout=25))
ef=st["leg_pnl"]["EF"]; cap=st["capital"]
rows.append(("v11 LIVE (Tokyo, $1)",ef["wins"],ef["settled"]-ef["wins"],len(st.get("open_positions",[])),ef["pnl"],dict(filled=pnl["filled"],attempted=pnl["attempted"],failed=pnl["failed"],wallet=cap["wallet"],delay=pnl.get("avg_delay_ms"))))
print(f"FAIR STATES {time.strftime('%H:%M UTC',time.gmtime())} | window since 21:55 UTC 09-09 ({(time.time()*1000-t0)/3600000:.1f} h)")
print("| run | W/L | acc | open | PnL @$10 |")
for name,w,l,op,pn,x in rows:
    n=w+l; acc=f"{w/n*100:.0f}%" if n else "-"
    if x: print(f"| {name} | {w}/{l} | {acc} | {op} | {pn*10:+.1f} (real {pn:+.2f} at $1; {x['filled']}/{x['attempted']} filled, {x['failed']} failed, wallet {x['wallet']:.2f}) |")
    else: print(f"| {name} | {w}/{l} | {acc} | {op} | {pn:+.1f} |")
