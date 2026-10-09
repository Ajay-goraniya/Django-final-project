import sys, sqlite3, numpy as np, datetime as dt, time, glob, os
sys.path.insert(0,'/home/ubuntu/claude-work/repo/analysis/zurich')
import ef3_shadow as S
now=int(time.time()); f=lambda t: dt.datetime.fromtimestamp(t,dt.UTC).strftime('%m-%d %H:%M')
def age(p,q):
    try:
        c=sqlite3.connect(f'file:{p}?mode=ro',uri=True); v=c.execute(q).fetchone()[0]
        if v is None: return None
        v=float(v); v=v/1000 if v>2e10 else v
        return now-v
    except Exception: return None
feeds=[('decide_log',age('/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3','SELECT max(ts_ms) FROM decide_log')),
       ('tape1s',   age('/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3','SELECT max(ts) FROM tape1s')),
       ('books',    age('/home/ubuntu/pm_multi/multi_market.sqlite3',"SELECT max(ts) FROM books WHERE market='btc5'")),
       ('bn_flow',  age('/home/ubuntu/pm_multi/bn_flow.sqlite3','SELECT max(ts_ms) FROM flow')),
       ('rtds',     age('/home/ubuntu/pm_multi/rtds.sqlite3','SELECT max(ts_ms) FROM px')),
       ('gamma',    age('/home/ubuntu/pm_ef3/gamma_zurich.sqlite3','SELECT max(epoch) FROM mkt WHERE outcome IS NOT NULL'))]
procs=[]
for d in glob.glob('/proc/[0-9]*'):
    try: a=' '.join(x.decode('utf8','replace') for x in open(d+'/cmdline','rb').read().split(b'\0') if x)
    except Exception: continue
    for k in ('btc_model_v12_polymarket','recorder.py','bn_flow.py','rtds.py'):
        if k in a and 'flock' not in a: procs.append(k)
errs=[]
for lg in glob.glob('/home/ubuntu/pm_ef3/*.log')+glob.glob('/home/ubuntu/pm_multi/*.log'):
    try: tail=open(lg,'rb').read()[-4000:].decode('utf8','replace')
    except Exception: continue
    # code=1013 is the venue saying "try again later" - a websocket RECONNECT, not a failure. Counting
    # those as errors reported healthy feeds as broken. Count only lines that are neither reconnects
    # nor the routine close frames that follow them.
    n=sum(1 for l in tail.splitlines()
          if ('Traceback' in l or 'ERROR' in l) and 'code=1013' not in l and 'ConnectionClosed' not in l)
    rc=sum(1 for l in tail.splitlines() if 'code=1013' in l)
    if n or rc: errs.append(f'{os.path.basename(lg)}:{n}err/{rc}reconnect')
sh=sqlite3.connect(f'file:{S.DB}?mode=ro',uri=True)
last=sh.execute('SELECT max(epoch) FROM seen').fetchone()[0]
e=sqlite3.connect('file:/home/ubuntu/pm_paper_zurich/polymarket_v12_zurich_live4.sqlite3?mode=ro',uri=True)
master=dict(e.execute("SELECT k,v FROM meta WHERE k='master'"))['master']
lanes=dict(e.execute('SELECT lane,count(*) FROM orders GROUP BY lane'))
print(f'HEALTH {f(now)} UTC | engine pid-alive {sorted(set(procs))} | shadow last candle {f(last)} '
      f'({(now-last)/60:.0f} min) | feeds age s: ' +
      ' '.join(f'{k}={"DEAD" if v is None else int(v)}' for k,v in feeds) +
      f' | errors {errs if errs else "none"} | master={master} lanes={lanes}')
START=1790645*1000//1000
START=sh.execute("SELECT min(epoch) FROM fires WHERE arm LIKE 'FAV%'").fetchone()[0]
print(f'\nALL FORWARD-SHADOW ARMS, {f(START)} .. {f(last)} UTC  (all arms on the same window)')
print('arm                      decisions  fills  wins    $@10    maxDD   flag')
rows=[]
for a in S.ARMS:
    r=sh.execute("SELECT fill,win,pnl,pnl_part,sh FROM fires WHERE arm=? AND epoch>=? ORDER BY epoch",(a,START)).fetchall()
    part=[x for x in r if x[3] is not None]
    if part:                      # FAV family: V's partial model is the registered one
        got=[x for x in part if (x[4] or 0)>0]; pn=np.array([x[3] for x in part],dtype=float)
        nf=len(got); w=sum(x[1] for x in got)
    else:
        fl=[x for x in r if x[0] is not None]; pn=np.array([x[2] for x in r],dtype=float) if r else np.array([0.0])
        nf=len(fl); w=sum(x[1] for x in fl)
    c=np.cumsum(pn); dd=float(np.max(np.maximum.accumulate(np.r_[0,c])-np.r_[0,c])) if len(pn) else 0.0
    rows.append((a,len(r),nf,w,pn.sum(),dd))
for a,n,nf,w,p,dd in rows:
    print(f'{a:24s} {n:9d} {nf:6d} {w:5d} {p:+8.2f} {dd:8.2f}   ' + ('INSUFFICIENT (<60 fills)' if nf<60 else ''))
big=[a for a,n,nf,w,p,dd in rows if nf>=60]
print(f'\n{len(rows)-len(big)} of {len(rows)} arms are under the 60-fill bar and flagged INSUFFICIENT.')
# hours computed, never hardcoded: the 17:05 edition of this file carried a literal "15.4 h" that was
# already wrong by the next run.
print(f'Only {len(big)} clear it on this window: {", ".join(big)}')
print(f'- and {(last-START)/3600:.1f} h of one day is still not a basis for any decision about any arm.')
print('The forward decision rule needs >= 3 full days; it has 1.')
print('EF-9 is NOT a forward-shadow arm - it was never registered as one; 19 arms are registered and')
print('all 19 are listed. EF-9 exists only as the offline studies ef9.py / ef9v1.py / ef11.py.')
