"""1 Hz logger of twin C's live view: spot price, candle open, Predict.fun best asks/sizes/age, per second.
Gives any offline replay (11.2 direction model, J, REVERSAL variants) the exact-second ask and price path
on the live book. Grading comes from the twin's candles table. Table b1(ts_ms, epoch, sec, price, open,
ask_up, size_up, age_up, ask_dn, size_dn, age_dn, book_candle)."""
import json, sqlite3, time, urllib.request
D="/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/b10live"
API="http://127.0.0.1:8796/api/state"
con=sqlite3.connect(f"{D}/book1s.sqlite3")
con.execute("""CREATE TABLE IF NOT EXISTS b1(ts_ms INTEGER PRIMARY KEY, epoch INTEGER, sec REAL, price REAL, open REAL,
  ask_up REAL, size_up REAL, age_up INTEGER, ask_dn REAL, size_dn REAL, age_dn INTEGER, book_candle INTEGER)""")
con.execute("CREATE INDEX IF NOT EXISTS b1_ep ON b1(epoch, sec)"); con.commit()
n=0
while True:
    t0=time.time()
    try:
        s=json.load(urllib.request.urlopen(API,timeout=3))
        f=s.get("feature") or {}; c=s.get("candle") or {}; b=s.get("book") or {}
        up=b.get("up") or {}; dn=b.get("down") or {}
        ep=int(c.get("time") or 0)//1000
        con.execute("INSERT OR IGNORE INTO b1 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(t0*1000), ep, f.get("phase_second"), f.get("price"), c.get("open"),
             up.get("price"), up.get("size"), up.get("age_ms"), dn.get("price"), dn.get("size"), dn.get("age_ms"),
             int(b.get("candle_id") or 0)//1000 or None))
        n+=1
        if n%600==0: con.commit(); print(time.strftime("%H:%M:%S",time.gmtime()),"rows",con.execute("select count(*) from b1").fetchone()[0],flush=True)
        else: con.commit()
    except Exception as e:
        if n%60==0: print("err",repr(e)[:80],flush=True)
    time.sleep(max(0.05,1.0-(time.time()-t0)))
