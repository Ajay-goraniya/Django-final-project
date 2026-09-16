"""Live forward shadow of H1's frozen 11.2 direction model (analysis/h1/models, Task 17) on twin C's live
Predict.fun book. Path = 1-s prices from book1s.sqlite3 (index 0 = candle open); trailing12 = mean
(high-low)/open bps of the previous 12 candles from twin C's candles table (kline high/low, slightly wider
than the 1-s close range the model was trained on - noted). At each decision second the rule fires with the
live ask/size at that second; first clearing second wins; graded from twin C candles. Nothing is traded."""
import sqlite3, time, sys, numpy as np, joblib
D="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
M="/home/user/Django-final-project/analysis/h1/models"
sys.path.insert(0,M)
from ef11_2_predict import decide, SECS, EV_MARGIN, FEE
model=joblib.load(f"{M}/ef11_2_gbm_seed0.joblib")
out=sqlite3.connect(f"{D}/dm_shadow.sqlite3")
out.execute("""CREATE TABLE IF NOT EXISTS dm(candle_id INTEGER PRIMARY KEY, side TEXT, sec INTEGER, ask REAL, size REAL,
  ev REAL, trail12 REAL, fired_ts INTEGER, actual TEXT, correct INTEGER, pnl REAL)"""); out.commit()
def b1(): return sqlite3.connect(f"{D}/book1s.sqlite3")
def twin(): return sqlite3.connect(f"{D}/v11/tests/c_thr1.sqlite3")
def trail12(ep):
    t=twin(); r=t.execute("select open,high,low from candles where candle_id<? order by candle_id desc limit 12",(ep*1000,)).fetchall(); t.close()
    if len(r)<12: return None
    return float(np.mean([(h-l)/o*1e4 for o,h,l in r]))
def path_and_book(ep,S):
    c=b1(); rows=c.execute("select sec,price,open,ask_up,size_up,ask_dn,size_dn from b1 where epoch=? and sec<=? order by ts_ms",(ep,S+0.999)).fetchall(); c.close()
    if not rows or rows[0][2] is None: return None,None
    path=np.full(300,np.nan); path[0]=rows[0][2]
    for sec,price,op,*_ in rows:
        if price is not None and 0<=int(sec)<300: path[int(sec)]=price
    for i in range(1,S+1):
        if np.isnan(path[i]): path[i]=path[i-1]
    last=[r for r in rows if int(r[0])==S] or rows[-1:]
    return path,last[-1]
def grade():
    t=twin()
    for cid,side in out.execute("select candle_id,side from dm where actual is null").fetchall():
        a=t.execute("select actual from candles where candle_id=?",(cid,)).fetchone()
        if a and a[0] in("UP","DOWN"):
            ask=out.execute("select ask from dm where candle_id=?",(cid,)).fetchone()[0]
            win=a[0]==side; out.execute("update dm set actual=?,correct=?,pnl=? where candle_id=?",(a[0],int(win),((1/ask)*(1-FEE)-1) if win else -1.0,cid))
    out.commit(); t.close()
def stats():
    r=out.execute("select pnl,sec from dm where pnl is not null order by candle_id").fetchall()
    if not r: return "graded 0"
    p=[x[0] for x in r]; h=len(p)//2
    bys={}
    for pnl,s in r: bys.setdefault(s,[]).append(pnl)
    return f"graded {len(p)} hit {np.mean([x>0 for x in p])*100:.0f}% per-fire {np.mean(p):+.3f} halves {sum(p[:h]):+.2f}/{sum(p[h:]):+.2f} | by S "+" ".join(f"{s}:{len(v)}/{np.mean(v):+.2f}" for s,v in sorted(bys.items()))
done_ep=None; tried=set(); last_ep=None
print("11.2 live shadow started; margin",EV_MARGIN,"fee",FEE,"secs",SECS,flush=True)
while True:
    now=time.time(); ep=int(now//300)*300; sec=now-ep
    if ep!=last_ep: last_ep=ep; tried=set(); grade()
    if ep!=done_ep and not out.execute("select 1 from dm where candle_id=?",(ep*1000,)).fetchone():
        for S in SECS:
            if S in tried or sec<S+1.0: continue
            tried.add(S)
            if sec>S+4: continue   # missed the second (restart/lag) - skip it, never look ahead
            t12=trail12(ep)
            path,row=path_and_book(ep,S)
            if t12 is None or path is None or np.isnan(path[S]): continue
            _,_,_,au,su,ad,sd=row
            r=decide(model,path,S,t12,au,ad,su,sd)
            if r:
                side,ask,ev=r; size=su if side=="UP" else sd
                out.execute("insert or ignore into dm values(?,?,?,?,?,?,?,?,NULL,NULL,NULL)",(ep*1000,side,S,ask,size,ev,t12,int(now*1000))); out.commit(); done_ep=ep
                print(time.strftime("%H:%M:%S",time.gmtime()),f"FIRE cid {ep} {side} S={S} ask {ask:.2f} size {size:.0f} ev {ev:+.3f} t12 {t12:.1f} | {stats()}",flush=True)
                break
    time.sleep(0.5)
