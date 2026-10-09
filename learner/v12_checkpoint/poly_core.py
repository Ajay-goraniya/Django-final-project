"""Polymarket order policy, book cache, and durable trade journal."""
import asyncio, json, math, sqlite3, threading, time, uuid
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN

D=lambda x:Decimal(str(x))

def fee(price,shares,rate=.07,exponent=1):
    return round(shares*rate*(price*(1-price))**exponent,5)

class BookCache:
    def __init__(self): self.books={}; self.terms={}; self.seq=0
    def clear(self): self.books.clear()
    def apply(self,e):
        stamp=float(e['timestamp'])/1000; now=time.time()
        if not math.isfinite(stamp) or not -2<=now-stamp<=2: return
        k=e.get('event_type')
        if k=='tick_size_change':
            token=str(e['asset_id'])
            self.terms.pop(token,None) # no entry until metadata refresh
            return
        if k=='book':
            token=str(e['asset_id'])
            if token in self.books and stamp<self.books[token]['event']: return
            b={s:{float(x['price']):float(x['size']) for x in e.get(s,[]) if 0<float(x['price'])<1 and math.isfinite(float(x['size'])) and float(x['size'])>0} for s in ('asks','bids')}
            self.books[token]=b; self.seq+=1
            b.update(event=stamp,arrival=time.monotonic(),seq=self.seq)
        elif k=='price_change':
            for c in e.get('price_changes',[]):
                b=self.books.get(str(c.get('asset_id')))
                if not b or stamp<b['event'] or c.get('side') not in ('BUY','SELL'): continue
                p,q=float(c['price']),float(c['size'])
                if not (0<p<1 and q>=0 and math.isfinite(q)): continue
                side=b['asks' if c['side']=='SELL' else 'bids']
                if q: side[p]=q
                else: side.pop(p,None)
                self.seq+=1; b.update(event=stamp,arrival=time.monotonic(),seq=self.seq)
    def quote(self,t,max_age=.75):
        b=self.books.get(t)
        if not b or not b['asks'] or not b['bids']: return None
        age=max(time.time()-b['event'],time.monotonic()-b['arrival'])
        if not 0<=age<=max_age: return None
        ask,bid=min(b['asks']),max(b['bids'])
        if bid>=ask: return None
        return dict(ask=ask,bid=bid,asks=sorted(b['asks'].items()),seq=b['seq'],age_ms=age*1000)

def order_plan(q,terms,stake,d,pad=1):
    tick,minimum,rate,exp=map(float,terms)
    if not all(map(math.isfinite,(tick,minimum,rate,exp,stake,d['p'],d['threshold']))) or not (0<tick<1 and minimum>0 and 0<=rate<1 and exp>=1 and stake>0 and 0<d['p']<1 and pad>=0):
        raise ValueError('invalid order inputs')
    cap=float(((D(q['ask'])/D(tick)).to_integral_value(rounding=ROUND_CEILING)+pad)*D(tick))
    if not 0<cap<1: raise ValueError('price cap outside market')
    f=rate*(cap*(1-cap))**exp
    cost=max(cap+f,cap/(1-f/cap)) # also preserves conservative inherited v10 EV
    if d['p']/cost-1<d['threshold']: raise ValueError('padded price fails model EV')
    # Reserve fees for any observed executable level, not just the worst price.
    ratio=max(rate*(p*(1-p))**exp/p for p,size in q['asks'] if p<=cap)
    amount=float((D(stake)/(1+D(ratio))).quantize(D('.01'),rounding=ROUND_DOWN))
    if amount/cap+1e-8<minimum: raise ValueError('below venue minimum; stake not increased')
    return dict(cap=cap,amount=amount,budget=stake,quote=q['ask'],age_ms=q['age_ms'],rate=rate,exponent=exp,seq=q['seq'])

def walk_book(q,plan):
    left=plan['amount']; sh=spent=fees=0.
    for p,n in q['asks']:
        if p>plan['cap']: break
        size=min(n,left/p); sh+=size; spent+=size*p
        fees+=fee(p,size,plan['rate'],plan['exponent']); left-=size*p
        if left<1e-9: break
    return dict(shares=sh,spent=spent,fees=fees,price=spent/sh if sh else None)

class Journal:
    def __init__(self,path,lane,model_hash):
        self.c=sqlite3.connect(path,check_same_thread=False); self.c.row_factory=sqlite3.Row; self.lock=threading.RLock()
        self.c.executescript('''PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
        CREATE TABLE IF NOT EXISTS signals(epoch INTEGER PRIMARY KEY,ts REAL,side TEXT,token TEXT,condition_id TEXT,decision TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,epoch INTEGER,attempt INTEGER,status TEXT,plan TEXT,ts REAL,latency REAL,reason TEXT);
        CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY,order_id TEXT,epoch INTEGER,shares REAL,spent REAL,fees REAL,price REAL,basis TEXT);
        CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY AUTOINCREMENT,epoch INTEGER UNIQUE,actual TEXT,payout REAL,pnl REAL,ts REAL,claim_status TEXT DEFAULT 'PENDING',claim_id TEXT);
        CREATE TABLE IF NOT EXISTS diagnostics(ts REAL,epoch INTEGER,detail TEXT);
        CREATE TABLE IF NOT EXISTS candles(epoch INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,volume REAL);
        ''')
        if 'id' not in [r[1] for r in self.c.execute('PRAGMA table_info(results)')]:
            self.c.close()
            raise ValueError('Pre-release database schema: preserve it and choose a new DB')
        for k,v in [('lane',lane),('model_hash',model_hash),('build','12.0')]:
            old=self.get(k)
            if old is not None and old!=v: raise ValueError('Database identity mismatch; choose a new DB')
            self.set(k,v)
    def sql(self,q,args=()):
        with self.lock,self.c: return self.c.execute(q,args).fetchall()
    def get(self,k,default=None):
        r=self.sql('SELECT v FROM meta WHERE k=?',(k,)); return json.loads(r[0][0]) if r else default
    def set(self,k,v): self.sql('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,json.dumps(v)))
    def reserve(self,ep,d,token,condition):
        with self.lock,self.c:
            return self.c.execute('INSERT OR IGNORE INTO signals VALUES(?,?,?,?,?,?,?)',(ep,time.time(),d['side'],token,condition,json.dumps(d),'RESERVED')).rowcount==1
    def status(self,ep,status): self.sql('UPDATE signals SET status=? WHERE epoch=?',(status,ep))
    def order(self,oid,ep,n,plan): self.sql('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)',(oid,ep,n,'SUBMITTING',json.dumps(plan),time.time(),None,None))
    def order_status(self,oid,status,reason=None,latency=None): self.sql('UPDATE orders SET status=?,reason=?,latency=coalesce(?,latency) WHERE id=?',(status,reason,latency,oid))
    def fill(self,oid,ep,tid,f,basis): self.sql('INSERT OR IGNORE INTO fills VALUES(?,?,?,?,?,?,?,?)',(tid,oid,ep,f['shares'],f['spent'],f['fees'],f['price'],basis))
    def grade(self,ep,actual):
        if actual not in ('UP','DOWN'): return
        with self.lock,self.c:
            if self.c.execute("SELECT 1 FROM orders WHERE epoch=? AND status IN ('SUBMITTING','UNKNOWN','PENDING')",(ep,)).fetchone(): return
            r=self.c.execute('SELECT s.side,sum(f.shares),sum(f.spent+f.fees) FROM signals s JOIN fills f USING(epoch) WHERE epoch=? GROUP BY s.epoch',(ep,)).fetchone()
            if not r: return
            payout=r[1] if r[0]==actual else 0
            self.c.execute('INSERT OR IGNORE INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',(ep,actual,payout,payout-r[2],time.time()))
    def metrics(self):
        n,w,l,pnl=self.sql('SELECT count(*),coalesce(sum(pnl>0),0),coalesce(sum(pnl<0),0),coalesce(sum(pnl),0) FROM results')[0]
        return dict(n=n,wins=w,losses=l,pnl=pnl,accuracy=w/n if n else None)
    def halt_check(self):
        r=self.sql('SELECT sum(f.spent)/sum(f.shares)-min(json_extract(o.plan,\'$.quote\')) FROM fills f JOIN orders o ON o.id=f.order_id GROUP BY f.epoch ORDER BY f.epoch DESC LIMIT 20')
        if len(r)==20 and sum(x[0] for x in r)/20>.03: self.set('halt','Average slippage > $0.03 over 20 fills')
        r=self.sql('SELECT r.pnl/sum(f.spent+f.fees) FROM results r JOIN fills f USING(epoch) GROUP BY r.epoch ORDER BY r.epoch DESC LIMIT 20')
        if len(r)==20 and sum(x[0] for x in r)<-3: self.set('halt','20 settled unit returns sum below -3')

class PaperBroker:
    basis='PAPER_DEPTH_FEE_ESTIMATE'
    def __init__(self,books,db=None): self.books=books; self.db=db; self.pending={}
    async def prepare(self,token,plan):
        oid='paper-'+uuid.uuid4().hex; return (oid,token,plan),oid
    async def post(self,signed):
        oid,token,plan=signed; q=self.books.quote(token)
        f=walk_book(q,plan) if q else None
        if not f or not f['shares']: return {'rejected':'fak_not_filled'}
        if self.db:
            ep=self.db.sql('SELECT epoch FROM orders WHERE id=?',(oid,))[0][0]
            self.db.fill(oid,ep,oid,f,self.basis)
        else: self.pending[oid]=f
        return {'id':oid}
    async def reconcile(self,r):
        f=self.pending.pop(r['id'],None)
        return dict(terminal=True,fills=[(r['id'],f)] if f else [])

class Executor:
    def __init__(self,db,books,broker,age=.75,pad=1): self.db=db; self.books=books; self.broker=broker; self.age=age; self.pad=pad
    async def fire(self,ep,d,token,condition,stake,reassess):
        if self.db.get('halt') or not self.db.reserve(ep,d,token,condition): return
        deadline=min(time.monotonic()+2,time.monotonic()+ep+240-time.time()); seq=-1
        for n in range(1,4):
            while time.monotonic()<deadline:
                q=self.books.quote(token,self.age)
                if q and q['seq']!=seq: break
                await asyncio.sleep(.01)
            else: self.db.status(ep,'DEADLINE'); return
            seq=q['seq']; new=reassess()
            if not new.get('fire') or new['side']!=d['side']: self.db.status(ep,'SIGNAL_CHANGED'); return
            try: plan=order_plan(q,self.books.terms[token],stake,new,self.pad)
            except (ValueError,KeyError) as e:
                self.db.status(ep,'SKIPPED'); self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,str(e))); return
            try: signed,oid=await asyncio.wait_for(self.broker.prepare(token,plan),max(.001,deadline-time.monotonic()))
            except Exception as e:
                self.db.status(ep,'PREPARE_FAILED'); self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,type(e).__name__)); return
            if time.monotonic()>=deadline: self.db.status(ep,'DEADLINE'); return
            latest=self.books.quote(token,self.age)
            if not latest or latest['seq']!=seq: continue
            final=reassess()
            if not final.get('fire') or final.get('side')!=d['side']: self.db.status(ep,'SIGNAL_CHANGED'); return
            try: order_plan(latest,self.books.terms[token],stake,final,self.pad)
            except (KeyError,ValueError): self.db.status(ep,'EV_CHANGED'); return
            self.db.order(oid,ep,n,plan); start=time.monotonic()
            try: r=await asyncio.wait_for(self.broker.post(signed),min(1.2,max(.001,deadline-start)))
            except (Exception,asyncio.CancelledError) as e:
                self.db.order_status(oid,'UNKNOWN',type(e).__name__,1000*(time.monotonic()-start)); self.db.status(ep,'PENDING')
                if isinstance(e,asyncio.CancelledError): raise
                return
            latency=1000*(time.monotonic()-start)
            if r.get('rejected'):
                self.db.order_status(oid,'REJECTED',r['rejected'],latency)
                if r['rejected'] not in ('fak_not_filled','unmatched','market_not_ready'): self.db.status(ep,'REJECTED'); return
                continue
            if r.get('id')!=oid:
                self.db.set('halt','Order hash mismatch; reconcile before resuming'); self.db.order_status(oid,'UNKNOWN'); return
            self.db.order_status(oid,'PENDING',latency=latency); self.db.status(ep,'PENDING'); return
        self.db.status(ep,'EXHAUSTED')
    async def reconcile(self):
        rows=self.db.sql("SELECT o.*,s.token FROM orders o JOIN signals s USING(epoch) WHERE o.status IN ('SUBMITTING','UNKNOWN','PENDING')")
        for row in rows:
            r=dict(row)
            try: out=await asyncio.wait_for(self.broker.reconcile(r),8)
            except Exception: continue
            if out is None: continue
            for tid,f in out.get('fills',[]): self.db.fill(r['id'],r['epoch'],tid,f,self.broker.basis)
            if out.get('terminal'):
                state='FILLED' if self.db.sql('SELECT 1 FROM fills WHERE order_id=?',(r['id'],)) else 'NO_FILL'
                self.db.order_status(r['id'],state); self.db.status(r['epoch'],state)
        self.db.halt_check()
