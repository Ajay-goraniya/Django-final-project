import sqlite3,urllib.request,json,time,sys,ssl
DB=sys.argv[1]; T0=int(sys.argv[2]); T1=int(sys.argv[3])  # ms
c=sqlite3.connect(DB); c.execute("create table if not exists k1s(ts integer primary key, o real, h real, l real, cl real, v real, n integer, tb real)")
last=c.execute("select max(ts) from k1s").fetchone()[0]
t=max(T0, (last+1000) if last else T0)
while t<T1:
    url=f"https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1s&startTime={t}&limit=1000"
    try:
        rows=json.loads(urllib.request.urlopen(url,timeout=20).read())
    except Exception as e:
        print('retry',t,e,flush=True); time.sleep(3); continue
    if not rows: t+=1000*1000; continue
    c.executemany("insert or ignore into k1s values(?,?,?,?,?,?,?,?)",[(r[0],float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5]),r[8],float(r[9])) for r in rows])
    c.commit(); t=rows[-1][0]+1000
    time.sleep(0.15)
print('done',c.execute("select count(*),min(ts),max(ts) from k1s").fetchone(),flush=True)
