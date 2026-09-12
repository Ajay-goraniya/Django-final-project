"""Polymarket order policy, book cache, durable trade journal and reconciliation."""
import asyncio, json, math, os, sqlite3, threading, time, uuid
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN

D=lambda x:Decimal(str(x))


def fee(price,shares,rate=.07,exponent=1):
    return round(shares*rate*(price*(1-price))**exponent,5)


def _safe_error_value(value, depth=0):
    """Best-effort JSON-safe error payload with credential/signature redaction."""
    if depth > 4:
        return '<truncated>'
    if value is None or isinstance(value,(bool,int,float)):
        return value
    if isinstance(value,str):
        text=value[:4096]
        for env in ('POLYMARKET_PRIVATE_KEY','RELAYER_API_KEY','DASHBOARD_PASSWORD'):
            secret=os.environ.get(env)
            if secret and len(secret)>=6:
                text=text.replace(secret,'<redacted>')
        return text
    if isinstance(value,dict):
        out={}
        for k,v in list(value.items())[:80]:
            key=str(k)
            low=key.lower()
            if any(x in low for x in ('private','secret','password','authorization','signature','api_key','apikey')):
                out[key]='<redacted>'
            else:
                out[key]=_safe_error_value(v,depth+1)
        return out
    if isinstance(value,(list,tuple)):
        return [_safe_error_value(v,depth+1) for v in list(value)[:80]]
    return _safe_error_value(str(value),depth+1)


def error_info(exc, *, phase=None, request_reached=None):
    """Serialize an exception while retaining the useful venue rejection text.

    Explicit HTTP rejection => request_reached=True.  Transport ambiguity should
    pass ``'UNKNOWN'`` rather than pretending the venue definitely saw it.
    """
    out={
        'class':type(exc).__name__,
        'message':_safe_error_value(str(exc)),
        'repr':_safe_error_value(repr(exc)),
    }
    for name in ('status','status_code','code','retry_after','restriction','reason'):
        try:
            value=getattr(exc,name,None)
            if value is not None and isinstance(value,(str,int,float,bool)):
                out[name]=_safe_error_value(value)
        except Exception:
            pass
    # Some HTTP clients hang the raw response off the exception.  Capture only
    # sanitized response data; never headers/cookies/auth/signatures.
    try:
        response=getattr(exc,'response',None)
        if response is not None:
            status=getattr(response,'status_code',getattr(response,'status',None))
            if status is not None: out.setdefault('status',status)
            try:
                body=getattr(response,'text',None)
                if callable(body): body=body()
                if body: out['response_body']=_safe_error_value(body)
            except Exception:
                pass
            try:
                fn=getattr(response,'json',None)
                if callable(fn):
                    body_json=fn()
                    if body_json is not None: out['response_json']=_safe_error_value(body_json)
            except Exception:
                pass
    except Exception:
        pass
    if phase: out['phase']=phase
    if request_reached is not None:
        out['request_reached']=request_reached if isinstance(request_reached,str) else bool(request_reached)
    return out


def compact_error(info):
    if isinstance(info,str): return info
    if not isinstance(info,dict): return str(info)
    cls=info.get('class') or 'Error'; msg=info.get('message') or ''
    status=info.get('status'); code=info.get('code')
    bits=[f'{cls}: {msg}' if msg else cls]
    if status is not None: bits.append(f'HTTP {status}')
    if code: bits.append(f'code={code}')
    return ' · '.join(bits)


class BookCache:
    def __init__(self):
        self.books={}; self.terms={}; self.seq=0
        # Venue event time minus our clock, measured continuously.  v12.1 dropped
        # every book event more than 2s from local time, so a host whose clock had
        # drifted (a fresh VPS before NTP settles) discarded the entire feed and
        # reported an empty book rather than a clock problem.  We now measure the
        # offset, correct for it, and surface it instead of dropping data.
        self.clock_offset=0.0; self._offset_seeded=False
        self.dropped_future=0; self.dropped_stale=0; self.applied=0
    def clear(self): self.books.clear()
    def health(self):
        return dict(clock_offset_s=round(self.clock_offset,3),applied=self.applied,
                    dropped_future=self.dropped_future,dropped_stale=self.dropped_stale,
                    tokens=len(self.books))
    def apply(self,e):
        stamp=float(e['timestamp'])/1000; now=time.time()
        if not math.isfinite(stamp): return
        delta=now-stamp
        # Seed the offset from the first event rather than converging toward it.
        # An EMA starting at zero would reject several hundred events before it
        # caught up with a badly set clock, which is the same outage this change
        # exists to prevent - just slower.
        if not self._offset_seeded:
            self.clock_offset=min(delta,0.0); self._offset_seeded=True
        elif delta<self.clock_offset:
            # Our clock is further behind than we thought: follow immediately.
            self.clock_offset=delta
        else:
            # Drift back toward zero slowly, so one late packet cannot move it.
            self.clock_offset=.999*self.clock_offset
        corrected=delta-self.clock_offset
        if corrected>8: self.dropped_stale+=1; return
        if corrected<-8: self.dropped_future+=1; return
        self.applied+=1
        k=e.get('event_type')
        if k=='tick_size_change':
            token=str(e['asset_id']); self.terms.pop(token,None); return
        if k=='book':
            token=str(e['asset_id'])
            if token in self.books and stamp<self.books[token]['event']: return
            b={s:{float(x['price']):float(x['size']) for x in e.get(s,[]) if 0<float(x['price'])<1 and math.isfinite(float(x['size'])) and float(x['size'])>0} for s in ('asks','bids')}
            self.books[token]=b; self.seq+=1; b.update(event=stamp,arrival=time.monotonic(),seq=self.seq)
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
        # Monotonic arrival is authoritative for age: it cannot be moved by clock
        # drift or NTP steps.  The wall-clock figure is corrected by the measured
        # offset and used only when it indicates the book is OLDER.
        mono=time.monotonic()-b['arrival']
        wall=(time.time()-b['event'])-self.clock_offset
        age=max(mono,min(wall,mono+max_age))
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
    cost=max(cap+f,cap/(1-f/cap))
    if d['p']/cost-1<d['threshold']: raise ValueError('padded price fails model EV')
    levels=[rate*(p*(1-p))**exp/p for p,size in q['asks'] if p<=cap]
    if not levels: raise ValueError('no executable ask at cap')
    ratio=max(levels)
    amount=float((D(stake)/(1+D(ratio))).quantize(D('.01'),rounding=ROUND_DOWN))
    if amount/cap+1e-8<minimum: raise ValueError('below venue minimum; stake not increased')
    return dict(cap=cap,amount=amount,max_shares=amount/cap,budget=stake,quote=q['ask'],pre_submit_quote=q['ask'],age_ms=q['age_ms'],rate=rate,exponent=exp,seq=q['seq'])


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
        CREATE TABLE IF NOT EXISTS signals(epoch INTEGER PRIMARY KEY,ts REAL,side TEXT,token TEXT,condition_id TEXT,decision TEXT,status TEXT,kind TEXT DEFAULT 'EF');
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,epoch INTEGER,attempt INTEGER,status TEXT,plan TEXT,ts REAL,latency REAL,reason TEXT);
        CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY,order_id TEXT,epoch INTEGER,shares REAL,spent REAL,fees REAL,price REAL,basis TEXT);
        CREATE TABLE IF NOT EXISTS results(id INTEGER PRIMARY KEY AUTOINCREMENT,epoch INTEGER UNIQUE,actual TEXT,payout REAL,pnl REAL,ts REAL,claim_status TEXT DEFAULT 'PENDING',claim_id TEXT);
        CREATE TABLE IF NOT EXISTS diagnostics(ts REAL,epoch INTEGER,detail TEXT);
        CREATE TABLE IF NOT EXISTS candles(epoch INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,volume REAL);
        ''')
        self._add_columns('orders',{
            'error_json':'TEXT','timing_json':'TEXT','request_reached':'INTEGER DEFAULT 0',
            'reconcile_count':'INTEGER DEFAULT 0','last_reconcile':'REAL','venue_live':'INTEGER DEFAULT 0',
            'venue_absent':'INTEGER DEFAULT 0','venue_checked':'REAL'
        })
        # Money as Polymarket reports it, kept beside the local figure rather than
        # replacing it, so the two can be compared and any divergence surfaced.
        self._add_columns('results',{
            'venue_pnl':'REAL','venue_realized_pnl':'REAL','venue_fees':'REAL',
            'venue_value':'REAL','venue_ts':'REAL','pnl_basis':"TEXT DEFAULT 'LOCAL_FROM_FILLS'"
        })
        self._add_columns('fills',{'fee_basis':'TEXT','fee_rate_bps':'REAL'})
        self._add_columns('signals',{'kind':"TEXT DEFAULT 'EF'"})
        self._add_columns('orders',{'kind':"TEXT DEFAULT 'EF'"})
        self._migrate_signals_multilane()
        self.c.executescript('''
        CREATE TABLE IF NOT EXISTS venue_state(ts REAL PRIMARY KEY,cash REAL,portfolio_value REAL,
            open_value REAL,realized_pnl REAL,unrealized_pnl REAL,fees_paid REAL,detail TEXT);
        ''')
        if 'id' not in [r[1] for r in self.c.execute('PRAGMA table_info(results)')]:
            self.c.close(); raise ValueError('Pre-release database schema: preserve it and choose a new DB')
        for k,v in [('lane',lane),('model_hash',model_hash),('build','12.3.0')]:
            old=self.get(k)
            # v12.0 -> v12.1 is an additive execution/accounting migration.
            if k=='build' and old in ('12.0','12.1','12.2','12.2.1','12.2.2','12.2.3','12.2.4','12.3.0'): pass
            elif old is not None and old!=v: raise ValueError('Database identity mismatch; choose a new DB')
            self.set(k,v)
    def _migrate_signals_multilane(self):
        """Widen signals from one row per candle to one row per (candle, lane).

        Until this build EF was the only lane that could fire, so epoch alone was
        a sufficient key. MAIN and REVERSAL both trade the same candle - REVERSAL
        is a hedge placed beside an open MAIN, not a replacement for it - so the
        key has to carry the lane. SQLite cannot alter a primary key in place, so
        the table is rebuilt; every existing row is stamped EF, which is what it
        was, and no history is dropped."""
        cols=[r[1] for r in self.c.execute('PRAGMA table_info(signals)')]
        if not cols: return
        pk=[r[1] for r in self.c.execute('PRAGMA table_info(signals)') if r[5]]
        if pk==['epoch','kind']: return
        with self.lock,self.c:
            self.c.execute('''CREATE TABLE IF NOT EXISTS signals_ml(
                epoch INTEGER,ts REAL,side TEXT,token TEXT,condition_id TEXT,
                decision TEXT,status TEXT,kind TEXT NOT NULL DEFAULT 'EF',
                PRIMARY KEY(epoch,kind))''')
            self.c.execute('''INSERT OR IGNORE INTO signals_ml(epoch,ts,side,token,condition_id,decision,status,kind)
                              SELECT epoch,ts,side,token,condition_id,decision,status,
                                     coalesce(kind,'EF') FROM signals''')
            self.c.execute('DROP TABLE signals')
            self.c.execute('ALTER TABLE signals_ml RENAME TO signals')
    def _add_columns(self,table,cols):
        existing={r[1] for r in self.c.execute(f'PRAGMA table_info({table})')}
        with self.c:
            for name,decl in cols.items():
                if name not in existing: self.c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')
    def sql(self,q,args=()):
        with self.lock,self.c: return self.c.execute(q,args).fetchall()
    def get(self,k,default=None):
        r=self.sql('SELECT v FROM meta WHERE k=?',(k,)); return json.loads(r[0][0]) if r else default
    def set(self,k,v): self.sql('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,json.dumps(v)))
    def reserve(self,ep,d,token,condition,kind='EF'):
        with self.lock,self.c:
            return self.c.execute('''INSERT OR IGNORE INTO signals(epoch,ts,side,token,condition_id,decision,status,kind)
                                     VALUES(?,?,?,?,?,?,?,?)''',
                (ep,time.time(),d['side'],token,condition,json.dumps(d),'RESERVED',kind)).rowcount==1
    def status(self,ep,status,kind='EF'): self.sql('UPDATE signals SET status=? WHERE epoch=? AND kind=?',(status,ep,kind))
    def order(self,oid,ep,n,plan,timing=None,kind='EF'):
        self.sql('''INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,timing_json,request_reached,reconcile_count,venue_live,kind)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(oid,ep,n,'SUBMITTING',json.dumps(plan),time.time(),None,None,json.dumps(timing or {}),0,0,0,kind))
    def order_status(self,oid,status,reason=None,latency=None,*,error=None,timing=None,request_reached=None,venue_live=None):
        fields=['status=?','reason=?','latency=coalesce(?,latency)']; vals=[status,reason,latency]
        if error is not None: fields.append('error_json=?'); vals.append(json.dumps(error,ensure_ascii=False))
        if timing is not None: fields.append('timing_json=?'); vals.append(json.dumps(timing))
        if request_reached is not None: fields.append('request_reached=?'); vals.append(1 if request_reached else 0)
        if venue_live is not None: fields.append('venue_live=?'); vals.append(1 if venue_live else 0)
        vals.append(oid); self.sql('UPDATE orders SET '+','.join(fields)+' WHERE id=?',tuple(vals))
    def reconcile_touch(self,oid,venue_live=False):
        self.sql('UPDATE orders SET reconcile_count=reconcile_count+1,last_reconcile=?,venue_live=? WHERE id=?',(time.time(),1 if venue_live else 0,oid))
    def fill(self,oid,ep,tid,f,basis):
        self.sql('''INSERT OR IGNORE INTO fills(id,order_id,epoch,shares,spent,fees,price,basis,fee_basis,fee_rate_bps)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',
                 (tid,oid,ep,f['shares'],f['spent'],f['fees'],f['price'],basis,
                  f.get('fee_basis'),f.get('fee_rate_bps')))
    def grade(self,ep,actual):
        if actual not in ('UP','DOWN'): return
        with self.lock,self.c:
            if self.c.execute("SELECT 1 FROM orders WHERE epoch=? AND status IN ('SUBMITTING','UNKNOWN','PENDING')",(ep,)).fetchone(): return
            # Each lane is graded on its own fills: MAIN and REVERSAL can hold
            # opposite sides of the same candle, so summing them together would
            # net a hedge into a single meaningless number.
            rows=self.c.execute('''SELECT s.kind,s.side,sum(f.shares),sum(f.spent+f.fees)
                                   FROM signals s JOIN orders o ON o.epoch=s.epoch AND coalesce(o.kind,'EF')=s.kind
                                   JOIN fills f ON f.order_id=o.id
                                   WHERE s.epoch=? GROUP BY s.kind,s.side''',(ep,)).fetchall()
            if not rows: return
            payout=sum((r[2] if r[1]==actual else 0) for r in rows)
            staked=sum(r[3] for r in rows)
            self.c.execute('INSERT OR IGNORE INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',(ep,actual,payout,payout-staked,time.time()))
    def venue_snapshot(self,truth):
        if not isinstance(truth,dict): return
        self.sql('INSERT OR REPLACE INTO venue_state VALUES(?,?,?,?,?,?,?,?)',(
            float(truth.get('ts') or time.time()),truth.get('cash'),truth.get('portfolio_value'),
            truth.get('open_value'),truth.get('realized_pnl'),truth.get('unrealized_pnl'),
            truth.get('fees_paid'),
            # default=str so an unserialisable SDK value cannot abort the write.
            # When this raised, the whole venue snapshot was lost inside the
            # loop's exception handler and the reported PnL silently stayed on
            # the local basis.
            json.dumps(truth.get('account_pnl') or {},ensure_ascii=False,default=str)))
    def apply_venue_pnl(self,positions):
        """Write Polymarket's own per-position PnL onto the settled rows.

        Matched by condition_id through the signal that opened the epoch, so the
        number attributed to a candle is the venue's, not ours."""
        by_condition={}
        for p in positions or []:
            c=p.get('condition_id')
            if not c: continue
            a=by_condition.setdefault(c,dict(realized=0.,total=0.,fees=0.,value=0.))
            a['realized']+=p.get('realized_pnl') or 0.; a['total']+=p.get('total_pnl') or 0.
            a['fees']+=p.get('entry_fees') or 0.; a['value']+=p.get('current_value') or 0.
        if not by_condition: return 0
        rows=self.sql('''SELECT DISTINCT r.epoch,s.condition_id FROM results r JOIN signals s USING(epoch)
                         WHERE s.condition_id IS NOT NULL''')
        n=0
        for row in rows:
            a=by_condition.get(row['condition_id'])
            if not a: continue
            self.sql('''UPDATE results SET venue_pnl=?,venue_realized_pnl=?,venue_fees=?,venue_value=?,
                        venue_ts=?,pnl_basis='VENUE_POSITION_PNL' WHERE epoch=?''',
                     (a['total'],a['realized'],a['fees'],a['value'],time.time(),row['epoch']))
            n+=1
        return n
    def conditions_awaiting_venue(self,limit=60):
        """Markets with a settled row the venue has not yet priced.

        Passed to the positions query so attaching PnL to a settled candle costs
        one narrow lookup instead of paging the whole position history.
        """
        rows=self.sql('''SELECT DISTINCT s.condition_id FROM results r JOIN signals s USING(epoch)
                         WHERE r.venue_pnl IS NULL AND s.condition_id IS NOT NULL
                         ORDER BY r.epoch DESC LIMIT ?''',(int(limit),))
        return [r['condition_id'] for r in rows if r['condition_id']]
    def venue_metrics(self):
        """Wins, losses and PnL from the venue's numbers only. Rows the venue has
        not priced yet are excluded rather than back-filled from local math."""
        r=self.sql('''SELECT count(*) n,coalesce(sum(venue_pnl>0),0) w,coalesce(sum(venue_pnl<0),0) l,
                      coalesce(sum(venue_pnl),0) pnl FROM results WHERE venue_pnl IS NOT NULL''')[0]
        n=r['n'] or 0
        return dict(n=n,wins=r['w'],losses=r['l'],pnl=r['pnl'],
                    accuracy=(r['w']/n if n else None),basis='VENUE_POSITION_PNL')
    def pnl_divergence(self):
        """Largest gap between the venue figure and our local one, if any."""
        r=self.sql('''SELECT count(*) n,coalesce(max(abs(venue_pnl-pnl)),0) worst,
                      coalesce(sum(venue_pnl-pnl),0) total FROM results WHERE venue_pnl IS NOT NULL''')[0]
        return dict(compared=r['n'] or 0,worst_abs=r['worst'],total_delta=r['total'])
    def metrics(self):
        n,w,l,pnl=self.sql('SELECT count(*),coalesce(sum(pnl>0),0),coalesce(sum(pnl<0),0),coalesce(sum(pnl),0) FROM results')[0]
        return dict(n=n,wins=w,losses=l,pnl=pnl,accuracy=w/n if n else None)
    ABSENT_GRACE_S=5.0
    ABSENT_CONFIRMATIONS=2
    def mark_venue_open(self,open_ids,now=None):
        """Cross-check every unresolved local order against the venue's open orders.

        The local reserve is the only number on the dashboard that the venue does
        not publish, so it is the one that can drift. An order we recorded as
        PENDING that the venue does not list, and that produced no trade, is not
        holding venue funds - it is a local row outliving the thing it described.

        A single absence proves nothing: there is a real race between our submit
        and the order appearing in the listing. Release requires the order to be
        older than the grace period AND absent on consecutive checks, the same
        standard the reconciler applies before declaring a no-fill.
        """
        if open_ids is None: return 0
        now=time.time() if now is None else now
        ids=set(str(x) for x in open_ids)
        rows=self.sql("SELECT id,ts FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')")
        touched=0
        for r in rows:
            if str(r['id']) in ids:
                self.sql('UPDATE orders SET venue_absent=0,venue_live=1,venue_checked=? WHERE id=?',(now,r['id']))
            elif (now-float(r['ts'] or 0))>=self.ABSENT_GRACE_S:
                self.sql('UPDATE orders SET venue_absent=venue_absent+1,venue_live=0,venue_checked=? WHERE id=?',(now,r['id']))
            touched+=1
        return touched
    def reserve_detail(self):
        """The reserve split by what the venue can actually confirm.

        confirmed  the venue lists this order as open
        unverified we have not yet proved it either way (inside the grace period)
        phantom    repeatedly absent from the venue with no fill; not real money
        """
        rows=self.sql('''SELECT id,status,venue_live,coalesce(venue_absent,0) absent,venue_checked,ts,
                         coalesce(json_extract(plan,'$.budget'),0) budget,
                         (SELECT count(*) FROM fills f WHERE f.order_id=orders.id) fills
                         FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')''')
        out=dict(confirmed=0.0,unverified=0.0,phantom=0.0,rows=len(rows),phantom_ids=[])
        for r in rows:
            b=float(r['budget'] or 0)
            if r['venue_checked'] is None: out['unverified']+=b
            elif r['venue_live']: out['confirmed']+=b
            elif r['absent']>=self.ABSENT_CONFIRMATIONS and not r['fills']:
                out['phantom']+=b; out['phantom_ids'].append(r['id'])
            else: out['unverified']+=b
        out['total']=out['confirmed']+out['unverified']+out['phantom']
        out['effective']=out['confirmed']+out['unverified']
        return out
    def live_reserve(self,venue_verified=True):
        """Funds to hold back before sizing the next order.

        With venue_verified, an order the venue has repeatedly denied holding is
        excluded, so a dead local row cannot shrink what you are able to trade.
        """
        if not venue_verified:
            return float(self.sql("SELECT coalesce(sum(json_extract(plan,'$.budget')),0) FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')")[0][0] or 0)
        return self.reserve_detail()['effective']
    def halt_check(self):
        # Measured against the ask that was on the book immediately before submit,
        # which is the price the fill can fairly be judged against. The signal
        # quote can be hundreds of milliseconds older and flatters the number.
        r=self.sql('''SELECT sum(f.spent)/sum(f.shares)-min(coalesce(json_extract(o.plan,'$.pre_submit_quote'),
                      json_extract(o.plan,'$.quote'))) FROM fills f JOIN orders o ON o.id=f.order_id
                      GROUP BY f.epoch ORDER BY f.epoch DESC LIMIT 20''')
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
        if not f or not f['shares']: return {'rejected':{'class':'PaperReject','message':'fak_not_filled','code':'fak_not_filled','request_reached':True}}
        if self.db:
            ep=self.db.sql('SELECT epoch FROM orders WHERE id=?',(oid,))[0][0]; self.db.fill(oid,ep,oid,f,self.basis)
        else: self.pending[oid]=f
        return {'id':oid}
    async def reconcile(self,r):
        f=self.pending.pop(r['id'],None)
        return dict(terminal=True,fills=[(r['id'],f)] if f else [],live=False,verified_no_fill=not bool(f))
    async def account_snapshot(self): return dict(cash=None,open_order_ids=set(),positions=[])


class Executor:
    def __init__(self,db,books,broker,age=.75,pad=1,budget_s=2.0,post_timeout_s=1.2,attempts=3):
        self.db=db; self.books=books; self.broker=broker; self.age=age; self.pad=pad
        # v12.1 hardcoded a 2.0s total budget and a 1.2s post timeout. Both are
        # fine beside the venue and too tight from a distant region: three
        # attempts of sign + round trip do not fit in 2s when one round trip is
        # 300ms. They are settings now, so a deployment can be given a budget
        # that matches its measured latency instead of silently running out of
        # time and recording DEADLINE.
        self.budget_s=float(budget_s); self.post_timeout_s=float(post_timeout_s)
        self.max_attempts=max(1,int(attempts))
        self.latency_samples=[]
    def _sample(self,timing,outcome):
        """Record one attempt's stage timings.

        v12.1 sampled only accepted submissions, so the published p95 excluded
        every rejection and timeout - exactly the attempts that are slow. Latency
        is recorded for all of them and the outcome is kept alongside so the
        percentiles can be read overall or per outcome."""
        t=dict(timing); t['outcome']=outcome
        self.latency_samples.append(t); self.latency_samples=self.latency_samples[-500:]
    @staticmethod
    def _ambiguous(exc):
        # Transport failures and HTTP 408/5xx can occur after the venue saw the
        # request.  4xx RequestRejectedError (except 408) is explicit rejection.
        if type(exc).__name__=='RequestRejectedError':
            status=getattr(exc,'status',getattr(exc,'status_code',None))
            return status in (None,408) or (isinstance(status,int) and status>=500)
        return type(exc).__name__ in {'TransportError','TimeoutError','ConnectionLostError','UnexpectedResponseError'} or isinstance(exc,(asyncio.TimeoutError,TimeoutError,ConnectionError,OSError))
    async def fire(self,ep,d,token,condition,stake,reassess,kind='EF'):
        if self.db.get('halt') or not self.db.reserve(ep,d,token,condition,kind): return
        fire_start=time.monotonic(); deadline=min(fire_start+self.budget_s,fire_start+ep+240-time.time()); seq=-1
        for n in range(1,self.max_attempts+1):
            timing={'attempt':n,'signal_ts_ms':d.get('features',{}).get('ts_ms')}
            t=time.monotonic()
            while time.monotonic()<deadline:
                q=self.books.quote(token,self.age)
                if q and q['seq']!=seq: break
                await asyncio.sleep(.005)
            else: self.db.status(ep,'DEADLINE',kind); return
            timing['quote_wait_ms']=1000*(time.monotonic()-t); timing['quote_read_ms']=timing['quote_wait_ms']; timing['book_age_ms']=q['age_ms']; seq=q['seq']
            t=time.monotonic(); new=reassess(); timing['decision_ms']=1000*(time.monotonic()-t)
            if not new.get('fire') or new['side']!=d['side']: self.db.status(ep,'SIGNAL_CHANGED',kind); return
            try: plan=order_plan(q,self.books.terms[token],stake,new,self.pad)
            except (ValueError,KeyError) as e:
                self.db.status(ep,'SKIPPED',kind); self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,str(e))); return
            timing['signal_quote']=float(d.get('ask',plan['quote'])) if d.get('ask') is not None else plan['quote']
            t=time.monotonic()
            try: signed,oid=await asyncio.wait_for(self.broker.prepare(token,plan),max(.001,deadline-time.monotonic()))
            except Exception as e:
                info=error_info(e,phase='prepare',request_reached=False)
                self.db.status(ep,'PREPARE_FAILED',kind); self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(info)))
                print('[order prepare failed]',compact_error(info),flush=True); return
            timing['sign_ms']=1000*(time.monotonic()-t)
            if time.monotonic()>=deadline: self.db.status(ep,'DEADLINE',kind); return
            latest=self.books.quote(token,self.age)
            if not latest or latest['seq']!=seq: continue
            plan['pre_submit_quote']=latest['ask']; plan['signal_quote']=timing['signal_quote']
            t=time.monotonic(); final=reassess(); timing['final_recheck_ms']=1000*(time.monotonic()-t)
            if not final.get('fire') or final.get('side')!=d['side']: self.db.status(ep,'SIGNAL_CHANGED',kind); return
            try: order_plan(latest,self.books.terms[token],stake,final,self.pad)
            except (KeyError,ValueError): self.db.status(ep,'EV_CHANGED',kind); return
            timing['pre_submit_book_age_ms']=latest['age_ms']; timing['fire_to_submit_ms']=1000*(time.monotonic()-fire_start)
            self.db.order(oid,ep,n,plan,timing,kind); start=time.monotonic()
            try:
                r=await asyncio.wait_for(self.broker.post(signed),min(self.post_timeout_s,max(.001,deadline-start)))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                elapsed=1000*(time.monotonic()-start); timing['submit_ms']=elapsed; timing['response_ms']=elapsed; timing['network_roundtrip_ms']=elapsed; timing['total_attempt_ms']=1000*(time.monotonic()-fire_start)
                ambiguous=self._ambiguous(e); info=error_info(e,phase='post',request_reached=('UNKNOWN' if ambiguous else False))
                status='UNKNOWN' if ambiguous else 'REJECTED'
                self.db.order_status(oid,status,compact_error(info),elapsed,error=info,timing=timing,request_reached=(None if ambiguous else False))
                self.db.status(ep,'PENDING' if ambiguous else 'REJECTED',kind)
                self._sample(timing,status)
                print(f'[order {status.lower()}] id={oid} condition={condition} token={token} side={d.get("side")} quote={plan.get("quote"):.4f} pre={plan.get("pre_submit_quote"):.4f} cap={plan.get("cap"):.4f} stake={stake:.2f} amount={plan.get("amount"):.4f} max_shares={plan.get("max_shares"):.4f} attempt={n} submit={elapsed:.1f}ms total={timing.get("total_attempt_ms",0):.1f}ms {compact_error(info)}',flush=True)
                return
            latency=1000*(time.monotonic()-start); timing['submit_ms']=latency; timing['response_ms']=latency; timing['network_roundtrip_ms']=latency; timing['total_attempt_ms']=1000*(time.monotonic()-fire_start)
            ambiguous_response=r.get('ambiguous')
            if ambiguous_response:
                info=ambiguous_response if isinstance(ambiguous_response,dict) else {'class':'AmbiguousResponse','message':str(ambiguous_response),'request_reached':'UNKNOWN'}
                self.db.order_status(oid,'UNKNOWN',compact_error(info),latency,error=info,timing=timing,request_reached=None)
                self.db.status(ep,'PENDING',kind)
                self._sample(timing,'UNKNOWN')
                print(f'[order unknown] id={oid} condition={condition} token={token} side={d.get("side")} quote={plan.get("quote"):.4f} pre={plan.get("pre_submit_quote"):.4f} cap={plan.get("cap"):.4f} stake={stake:.2f} amount={plan.get("amount"):.4f} max_shares={plan.get("max_shares"):.4f} attempt={n} submit={latency:.1f}ms total={timing.get("total_attempt_ms",0):.1f}ms {compact_error(info)}',flush=True)
                return
            rejected=r.get('rejected')
            if rejected:
                info=rejected if isinstance(rejected,dict) else {'class':'RequestRejected','message':str(rejected),'code':str(rejected),'request_reached':True}
                self.db.order_status(oid,'REJECTED',compact_error(info),latency,error=info,timing=timing,request_reached=True)
                self._sample(timing,'REJECTED')
                print(f'[order rejected] id={oid} condition={condition} token={token} side={d.get("side")} quote={plan.get("quote"):.4f} pre={plan.get("pre_submit_quote"):.4f} cap={plan.get("cap"):.4f} stake={stake:.2f} amount={plan.get("amount"):.4f} max_shares={plan.get("max_shares"):.4f} attempt={n} submit={latency:.1f}ms total={timing.get("total_attempt_ms",0):.1f}ms {compact_error(info)}',flush=True)
                code=str(info.get('code') or info.get('message') or '')
                if code not in ('fak_not_filled','unmatched','market_not_ready'): self.db.status(ep,'REJECTED',kind); return
                continue
            if r.get('id')!=oid:
                info={'class':'OrderIdentityMismatch','message':f'signed={oid} response={r.get("id")}', 'request_reached':True}
                self.db.set('halt','Order hash mismatch; reconcile before resuming'); self.db.order_status(oid,'UNKNOWN',compact_error(info),latency,error=info,timing=timing,request_reached=True); return
            self.db.order_status(oid,'PENDING',latency=latency,timing=timing,request_reached=True,venue_live=True); self.db.status(ep,'PENDING',kind)
            self._sample(timing,'ACCEPTED')
            return
        self.db.status(ep,'EXHAUSTED',kind)
    async def reconcile(self):
        rows=self.db.sql('''SELECT o.*,s.token FROM orders o
                            JOIN signals s ON s.epoch=o.epoch AND s.kind=coalesce(o.kind,'EF')
                            WHERE o.status IN ('SUBMITTING','UNKNOWN','PENDING')''')
        for row in rows:
            r=dict(row)
            try: out=await asyncio.wait_for(self.broker.reconcile(r),8)
            except Exception as e:
                info=error_info(e,phase='reconcile')
                self.db.reconcile_touch(r['id'],venue_live=False)
                # Do not overwrite the original submission error; leave UNKNOWN until venue truth is established.
                self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),r['epoch'],json.dumps(info)))
                continue
            if out is None: continue
            self.db.reconcile_touch(r['id'],venue_live=bool(out.get('live')))
            for tid,f in out.get('fills',[]): self.db.fill(r['id'],r['epoch'],tid,f,self.broker.basis)
            if out.get('terminal'):
                has_fill=bool(self.db.sql('SELECT 1 FROM fills WHERE order_id=?',(r['id'],)))
                state='FILLED' if has_fill else 'NO_FILL'
                reason=out.get('reason') or ('venue-confirmed fill' if has_fill else 'venue-confirmed no fill')
                self.db.order_status(r['id'],state,reason,venue_live=False); self.db.status(r['epoch'],state,r['kind'] if 'kind' in r.keys() and r['kind'] else 'EF')
                print(f'[reconcile] id={r["id"]} -> {state}: {reason}',flush=True)
        self.db.halt_check()
    def latency_stats(self):
        def pcts(vals):
            if not vals: return None
            vals=sorted(vals)
            def pct(p): return round(vals[min(len(vals)-1,max(0,round((len(vals)-1)*p)))],1)
            return {'n':len(vals),'p50_ms':pct(.50),'p95_ms':pct(.95),'p99_ms':pct(.99),'max_ms':round(vals[-1],1)}
        S=self.latency_samples
        if not S: return {}
        out={'total':pcts([float(x['total_attempt_ms']) for x in S if x.get('total_attempt_ms') is not None])}
        for stage in ('quote_wait_ms','decision_ms','sign_ms','final_recheck_ms','fire_to_submit_ms','network_roundtrip_ms','book_age_ms'):
            v=[float(x[stage]) for x in S if x.get(stage) is not None]
            if v: out[stage]=pcts(v)
        by={}
        for x in S:
            o=x.get('outcome') or 'UNKNOWN'
            if x.get('total_attempt_ms') is not None: by.setdefault(o,[]).append(float(x['total_attempt_ms']))
        out['by_outcome']={k:pcts(v) for k,v in by.items()}
        t=out.get('total') or {}
        out.update({k:t.get(k) for k in ('n','p50_ms','p95_ms','p99_ms','max_ms')})
        return out
