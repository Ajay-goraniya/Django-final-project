"""1 Hz logger of Polymarket's BTC 5-min book (best ask/bid/size, both sides) using the engine's own PolyBook
websocket client (learner/btc_model_v11.py), so what is logged is exactly what the live signal sees.
Polymarket has no historical order-book endpoint (H1 Task 19), so every Polymarket evaluation must come from
this forward record. Table pb(ts_ms, epoch, sec, ask_up, size_up, bid_up, ask_dn, size_dn, bid_dn, age_s, status)."""
import sys, time, sqlite3
sys.path.insert(0, "/home/user/Django-final-project/learner")
from btc_model_v11 import PolyBook
D="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
con=sqlite3.connect(f"{D}/polybook.sqlite3")
con.execute("""CREATE TABLE IF NOT EXISTS pb(ts_ms INTEGER PRIMARY KEY, epoch INTEGER, sec REAL, ask_up REAL, size_up REAL, bid_up REAL,
  ask_dn REAL, size_dn REAL, bid_dn REAL, age_s REAL, status TEXT)""")
con.execute("CREATE INDEX IF NOT EXISTS pb_ep ON pb(epoch, sec)"); con.commit()
pb=PolyBook(); pb.start()
n=0
while True:
    t0=time.time(); ep=int(t0//300)*300; sec=t0-ep
    q=pb.quote(ep) or {}
    con.execute("INSERT OR IGNORE INTO pb VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (int(t0*1000), ep, round(sec,3), q.get("ask_up"), q.get("size_up"), q.get("bid_up"),
         q.get("ask_dn"), q.get("size_dn"), q.get("bid_dn"), q.get("age_s"), pb.status))
    con.commit(); n+=1
    if n%600==0: print(time.strftime("%H:%M:%S",time.gmtime()),"rows",con.execute("select count(*) from pb").fetchone()[0],"status",pb.status,"msgs",pb.msgs,flush=True)
    time.sleep(max(0.05,1.0-(time.time()-t0)))
