"""Original dashboard HTML, served with the Polymarket lane's data and controls."""
import base64, csv, datetime as dt, hmac, io, json, math, os, pathlib, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from zoneinfo import ZoneInfo
from btc_model_v10 import FEATURES
ROOT=pathlib.Path(__file__).parent
LONDON=ZoneInfo('Europe/London')
DEFAULT_STAKE=dict(mode='ladder',fixed_stake=1.,percent=10.,current_stake=1.,win_trigger=3,loss_trigger=2,min_stake=1.,max_stake=50.)

class Dashboard:
    def __init__(self,r):
        self.r=r; self.db=r.db; self.cache=None; self.cache_at=0
        self.password=os.environ.get('DASHBOARD_PASSWORD','')
        if r.a.host not in ('127.0.0.1','localhost','::1') and len(self.password)<12:
            raise ValueError('Set DASHBOARD_PASSWORD (12+ characters) before exposing the dashboard')
        for k,v in [('master',not r.a.live),('ef_enabled',True),('stake_settings',DEFAULT_STAKE),('rules',[]),('sx_enabled',False),('tp',0),('sl',0)]:
            if self.db.get(k) is None: self.db.set(k,v)
    def day(self):
        now=dt.datetime.now(LONDON); start=now.replace(hour=12,minute=0,second=0,microsecond=0)
        if now<start: start-=dt.timedelta(days=1)
        return start,start+dt.timedelta(days=1)
    def daily(self):
        start,end=self.day()
        n,p=self.db.sql('SELECT count(*),coalesce(sum(pnl),0) FROM results WHERE ts>=?',(start.timestamp(),))[0]
        tp,sl=self.db.get('tp',0),self.db.get('sl',0)
        halted=(tp>0 and p>=tp) or (sl>0 and p<=-sl)
        return dict(trades=n,pnl=p,take_profit=tp,stop_loss=sl,halted=halted,reason='Daily limit reached' if halted else '',resets_at=end.strftime('%d %b %H:%M'),resets_label='Europe/London')
    def banned(self):
        now=dt.datetime.now(LONDON); day=now.weekday(); minute=now.hour*60+now.minute
        for rule in self.db.get('rules',[]):
            if 'EF' not in rule['kinds']: continue
            a,b=rule['start_minute'],rule['end_minute']; days=rule['days']
            if a==b and day in days: return True
            if a<b and day in days and a<=minute<b: return True
            if a>b and ((day in days and minute>=a) or ((day-1)%7 in days and minute<b)): return True
        return False
    def allowed(self):
        return self.db.get('master',False) and self.db.get('ef_enabled',True) and not self.db.get('halt') and not self.daily()['halted'] and not self.banned() and not (self.db.get('sx_enabled') and time.time()<self.db.get('sx_until',0))
    def equity(self):
        if not self.r.a.live: return self.r.a.capital+self.db.metrics()['pnl']
        unclaimed=self.db.sql("SELECT coalesce(sum(payout),0) FROM results WHERE claim_status NOT IN ('CONFIRMED','NO_PAYOUT')")[0][0]
        return (self.r.cash or 0)+unclaimed
    def update_stake(self):
        with self.db.lock:
            s=self.db.get('stake_settings',DEFAULT_STAKE); equity=self.equity(); current=self.db.get('next_stake',1.)
            last=self.db.get('streak_cursor',0); w,l=self.db.get('streak',[0,0]); sx=self.db.get('sx_losses',0)
            settled=self.db.sql('SELECT rowid AS settlement_id,pnl,ts FROM results WHERE rowid>? ORDER BY rowid',(last,))
            running_equity=equity-sum(x['pnl'] for x in settled)
            for row in settled:
                running_equity+=row['pnl']
                if row['pnl']>0: w+=1; l=0; sx=0
                elif row['pnl']<0: l+=1; w=0; sx+=1
                else: w=l=sx=0
                if s['mode']=='streak' and (w>=s['win_trigger'] or l>=s['loss_trigger']):
                    current=max(s['min_stake'],min(s['max_stake'],running_equity*s['percent']/100)); w=l=0
                if self.db.get('sx_enabled') and sx>=2:
                    self.db.set('sx_until',row['ts']+900); sx=0
                self.db.set('streak_cursor',row['settlement_id'])
            self.db.set('streak',[w,l]); self.db.set('sx_losses',sx if self.db.get('sx_enabled') else 0)
            if s['mode']=='ladder':
                target=max(1,min(20,int(equity//10)-1)); pending=self.db.get('rung',[0,0])
                if target<=current: current=target; pending=[0,0]
                else:
                    pending=[target,pending[1]+1 if pending[0]==target else 1]
                    if pending[1]>=2: current=target; pending=[0,0]
                self.db.set('rung',pending)
            elif s['mode']=='fixed': current=s['fixed_stake']
            elif s['mode']=='percent': current=equity*s['percent']/100
            if s['mode']!='ladder': current=max(s['min_stake'],min(s['max_stake'],current))
            self.db.set('next_stake',round(current,2))
    def controls(self):
        now=dt.datetime.now(LONDON); ready=self.r.cash is not None and time.monotonic()-self.r.cash_at<15
        enabled=self.allowed(); w,l=self.db.get('streak',[0,0])
        return dict(master_enabled=self.db.get('master'),clock=now.strftime('%H:%M:%S'),timezone='Europe/London',
          execution=dict(ready=ready,missing=[] if ready else ['waiting for feed / balance readiness']),
          kinds={k:dict(manual_enabled=self.db.get('ef_enabled') if k=='EF' else False,effective_enabled=enabled if k=='EF' else False,status='v10 Polymarket lane' if k=='EF' else 'Not part of the v10 paper strategy') for k in ('MAIN','REVERSAL','EF')},
          state_x=dict(enabled=self.db.get('sx_enabled'),active=self.db.get('sx_enabled') and time.time()<self.db.get('sx_until',0),loss_streak=self.db.get('sx_losses',0),resume_time=dt.datetime.fromtimestamp(self.db.get('sx_until',0),LONDON).strftime('%H:%M'),trigger_reason='2 consecutive settled losses'),
          daily_limits=self.daily(),shared_stake=self.db.get('stake_settings'),shared_next_stake=self.db.get('next_stake',1),win_streak=w,loss_streak=l,rules=self.db.get('rules'),lane='LIVE' if self.r.a.live else 'PAPER')
    def apply(self,path,p):
        if p.get('confirmed') is not True: raise ValueError('Confirmation required')
        with self.db.lock:
            if path=='/api/controls/apply':
                system=p.get('system',{})
                updates={}
                if 'manual_enabled' in system:
                    if not isinstance(system['manual_enabled'],bool): raise ValueError('Invalid master toggle')
                    if system['manual_enabled'] and self.db.get('halt'): raise ValueError('Execution kill active: '+self.db.get('halt'))
                    updates['master']=system['manual_enabled']
                if 'stake' in system:
                    s={**DEFAULT_STAKE,**system['stake']}
                    if s['mode'] not in ('fixed','percent','streak','ladder'): raise ValueError('Unsupported stake mode')
                    for k in DEFAULT_STAKE:
                        if k!='mode':
                            s[k]=float(s[k])
                            if not math.isfinite(s[k]) or s[k]<=0: raise ValueError('Invalid stake value')
                    if s['min_stake']<1 or s['max_stake']>50 or s['min_stake']>s['max_stake'] or s['fixed_stake']>s['max_stake'] or s['percent']>100: raise ValueError('Stake bounds: $1 to $50; ladder caps at $20')
                    for k in ('win_trigger','loss_trigger'):
                        if int(s[k])!=s[k]: raise ValueError('Streak triggers must be integers')
                    if not s['min_stake']<=s['current_stake']<=s['max_stake']: raise ValueError('Current stake outside bounds')
                    updates.update(stake_settings=s,next_stake=s['current_stake'],streak=[0,0],rung=[0,0])
                with self.db.c:
                    for key,value in updates.items(): self.db.c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value)))
                if 'stake' in system: self.update_stake()
            elif path=='/api/controls/signal':
                if p.get('kind')!='EF': raise ValueError('MAIN and REVERSAL are not traded by the original v10 Polymarket strategy')
                if not isinstance(p.get('manual_enabled'),bool): raise ValueError('Invalid signal toggle')
                self.db.set('ef_enabled',p['manual_enabled'])
            elif path=='/api/controls/state-x':
                if not isinstance(p.get('manual_enabled'),bool): raise ValueError('Invalid SX toggle')
                self.db.set('sx_enabled',p['manual_enabled']); self.db.set('sx_losses',0); self.db.set('sx_until',0)
            elif path=='/api/controls/daily-limits':
                updates={}
                for param,key in [('take_profit','tp'),('stop_loss','sl')]:
                    v=float(p.get(param,0))
                    if not math.isfinite(v) or v<0: raise ValueError('Invalid daily limit')
                    updates[key]=v
                with self.db.c:
                    for key,value in updates.items(): self.db.c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value)))
            elif path=='/api/controls/rule':
                r=p.get('rule',{}); days=r.get('days',[]); kinds=r.get('kinds',[])
                a,b=int(r.get('start_minute',-1)),int(r.get('end_minute',-1))
                if not days or any(not isinstance(x,int) or not 0<=x<=6 for x in days) or not kinds or set(kinds)-{'MAIN','REVERSAL','EF'} or not(0<=a<1440 and 0<=b<1440): raise ValueError('Invalid ban rule')
                r=dict(id=uuid.uuid4().hex,kinds=kinds,days=days,start_minute=a,end_minute=b,describe=f"London days {','.join(str(x) for x in days)} · {a//60:02}:{a%60:02}–{b//60:02}:{b%60:02}")
                self.db.set('rules',self.db.get('rules',[])+[r])
            elif path=='/api/controls/rule/delete': self.db.set('rules',[r for r in self.db.get('rules',[]) if r['id']!=p.get('id')])
            else: raise ValueError('Unknown control')
        self.cache_at=0
        return dict(ok=True,state=self.controls())
    def positions(self):
        return self.db.sql('''SELECT s.*,sum(f.shares) shares,sum(f.spent) spent,sum(f.fees) fees,
        r.actual,r.pnl,r.payout,r.claim_status FROM signals s LEFT JOIN fills f USING(epoch) LEFT JOIN results r USING(epoch)
        GROUP BY s.epoch ORDER BY s.epoch DESC''')
    def orders(self,kind='EF',offset=0,limit=10):
        if kind!='EF': return dict(rows=[],offset=offset,total=0)
        rows=self.db.sql('''SELECT o.*,s.side,s.token,s.condition_id,s.decision,sum(f.shares) shares,sum(f.spent) spent,sum(f.fees) fees,CASE WHEN sum(f.shares)>0 THEN r.pnl ELSE NULL END pnl
        FROM orders o JOIN signals s USING(epoch) LEFT JOIN fills f ON f.order_id=o.id LEFT JOIN results r ON r.epoch=o.epoch
        GROUP BY o.id ORDER BY o.ts DESC LIMIT ? OFFSET ?''',(limit,offset))
        out=[]
        for r in rows:
            p=json.loads(r['plan']); d=json.loads(r['decision']); price=r['spent']/r['shares'] if r['shares'] else None
            out.append(dict(utc=dt.datetime.fromtimestamp(r['ts'],LONDON).isoformat(),candle_id=r['epoch']*1000,seconds_into_candle=d.get('sec'),direction=r['side'],kind='EF',ef_attempt_seq=r['attempt'],signal_price=d.get('signal_price'),quoted_price=p['quote'],fill_price=price,shares=r['shares'],delay_ms=r['latency'],last_attempt_ms=r['latency'],book_age_ms=p['age_ms'],fee_collateral=r['fees'],market_id=r['condition_id'],order_id=r['id'],status=r['status'],filled=bool(r['shares']),failure_reason=r['reason'],stake=(r['spent'] or 0)+(r['fees'] or 0) if r['shares'] else p['budget'],pnl=r['pnl'],correct=r['pnl']>0 if r['pnl'] is not None else None,financial_is_shadow=not self.r.a.live))
        return dict(rows=out,total=self.db.sql('SELECT count(*) FROM orders')[0][0],offset=offset)
    def history(self,offset,limit):
        rows=[]
        ps=self.db.sql('''SELECT s.*,sum(f.shares) shares,sum(f.spent) spent,sum(f.fees) fees,r.actual,r.pnl
        FROM results r JOIN signals s USING(epoch) JOIN fills f USING(epoch) GROUP BY s.epoch ORDER BY s.epoch DESC LIMIT ? OFFSET ?''',(limit,offset))
        for r in ps:
            d=json.loads(r['decision']); result='WIN' if r['pnl']>0 else 'LOSS' if r['pnl']<0 else 'FLAT'
            ef=dict(direction=r['side'],at=d.get('sec'),filled=True,fill_price=r['spent']/r['shares'],stake=r['spent']+r['fees'],pnl=r['pnl'],correct=r['pnl']>0,financial_result=result,financial_is_shadow=not self.r.a.live)
            rows.append(dict(candle_id=r['epoch']*1000,actual=r['actual'],main={},reversal={},ef=ef,combined_financial_result=result,combined_financial_pnl=r['pnl']))
        return dict(rows=rows,offset=offset,total=self.db.metrics()['n'])
    def pnl(self,range_key='1D'):
        cutoff=time.time()-({'1D':86400,'1W':7*86400}.get(range_key,1e12))
        rows=self.db.sql('SELECT pnl,epoch FROM results WHERE ts>=? ORDER BY ts',(cutoff,))
        pnl=0.; curve=[]
        for r in rows: pnl+=r['pnl']; curve.append(pnl)
        amount,shares,spent=self.db.sql('SELECT coalesce(sum(f.spent+f.fees),0),coalesce(sum(f.shares),0),coalesce(sum(f.spent),0) FROM fills f JOIN results r USING(epoch) WHERE r.ts>=?',(cutoff,))[0]
        attempted=self.db.sql('SELECT count(distinct epoch) FROM orders WHERE ts>=?',(cutoff,))[0][0]
        filled=self.db.sql('SELECT count(distinct f.epoch) FROM fills f JOIN orders o ON f.order_id=o.id WHERE o.ts>=?',(cutoff,))[0][0]
        return dict(count=len(rows),pnl=pnl,curve=curve,attempted=attempted,failed=max(0,attempted-filled),fill_rate=filled/attempted if attempted else None,return_on_stake=pnl/amount if amount else None,per_100=pnl*100/len(rows) if rows else None,avg_price=spent/shares if shares else None,avg_shares=shares/len(rows) if rows else None,by_kind={'EF':pnl})
    def chart(self):
        candles=[dict(time=r['epoch']*1000,open=r['open'],high=r['high'],low=r['low'],close=r['close'],volume=r['volume']) for r in reversed(self.db.sql('SELECT * FROM candles ORDER BY epoch DESC LIMIT 500'))]
        markers=[]
        for r in self.db.sql('SELECT * FROM signals ORDER BY epoch DESC LIMIT 500'):
            d=json.loads(r['decision']); markers.append(dict(candle_id=r['epoch']*1000,ts_ms=int(r['ts']*1000),time=r['epoch']*1000,kind='EF',direction=r['side'],price=d.get('signal_price'),financial_is_shadow=not self.r.a.live))
        return dict(candles=candles,markers=markers,history=[],revision=self.r.revision)
    def snapshot(self):
        if self.cache is not None and time.monotonic()-self.cache_at<.5: return self.cache
        r=self.r; metrics=self.db.metrics(); ctr=self.controls(); pending=self.db.sql("SELECT coalesce(sum(payout),0) FROM results WHERE claim_status NOT IN ('CONFIRMED','NO_PAYOUT','PAPER')")[0][0]
        age=time.monotonic()-r.cash_at; d=r.last_decision; ep=int(time.time()//300)*300
        pairs=r.market.get(ep,()); q=[r.books.quote(t,r.a.quote_age_ms/1000) for t in pairs]; book={}
        if len(q)==2 and all(q):
            book=dict(status='live',age_ms=max(x['age_ms'] for x in q),market=f'btc-updown-5m-{ep}',environment='live' if r.a.live else 'paper',api_key_configured=r.a.live)
            for key,x in zip(('up','down'),q): book[key]=dict(price=x['ask'],size=x['asks'][0][1],spread=x['ask']-x['bid'],break_even=r.m.cost(x['ask']))
        else: book=dict(status='waiting for fresh UP/DOWN books',environment='live' if r.a.live else 'paper')
        ef=None
        s=self.db.sql('SELECT * FROM signals WHERE epoch=?',(ep,))
        if s: ef=dict(direction=s[0]['side'],ts_ms=int(s[0]['ts']*1000),reason='v10 pnl · '+s[0]['status'])
        metric=dict(accuracy=metrics['accuracy'],wins=metrics['wins'],losses=metrics['losses'],real=metrics['n'] if r.a.live else 0,shadow=0 if r.a.live else metrics['n'])
        cash=r.cash or 0.; reserve=self.db.sql("SELECT coalesce(sum(json_extract(plan,'$.budget')),0) FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')")[0][0]
        fills=self.orders('EF',0,1)['rows']; last=fills[0] if fills else None
        if last: last.update(slippage=(last['fill_price']-last['quoted_price']) if last['fill_price'] else 0,attempts=last['ef_attempt_seq'],order_status=last['status'])
        current=dict(r.current_candle)
        if current: current['seconds_left']=max(0,current['time']/1000+300-time.time())
        positions=[dict(kind='v10',direction=x['side'],shares=x['shares'],buy_price=x['spent']/x['shares'],used_usd=x['spent']+x['fees'],pnl_usd=None) for x in self.positions() if x['shares'] and x['actual'] is None]
        self.cache=dict(feature_names=FEATURES,open_positions=positions,economics=self.pnl(),model=dict(version=10),learning=dict(status='Fixed v10 weights'),candle=current,feature=d.get('features',{}),feed=dict(status='LIVE' if r.age['spot'] and time.time()-r.age['spot']<2 else 'CONNECTING',last_event_age_ms=int(1000*(time.time()-r.age['spot'])) if r.age['spot'] else None),metrics=dict(main={},reversal={},ef=metric,combined=metric),main=None,reversal=None,main_block='Not part of the v10 Polymarket strategy',ef=ef,ef_monitor=dict(status=d.get('reason') or f"v10 pnl · p {d.get('p','--')} · EV {d.get('ev','--')}"),book=book,last_fill=last,controls=ctr,capital=dict(balance=self.equity(),wallet=cash,pending_payout=pending,free=max(0,cash-reserve),wallet_free=max(0,cash-reserve),fresh=age<15,balance_age_sec=age,realised=metrics['pnl'],reserved=reserve,next_stake=self.db.get('next_stake',1),truth={}),trades=self.pnl(),chart_revision=r.revision,error=r.error,lane='LIVE' if r.a.live else 'PAPER',model_hash=r.hash,fee_basis=r.broker.basis,halt=self.db.get('halt'))
        self.cache_at=time.monotonic(); return self.cache
    def page(self,name):
        text=(ROOT/name).read_text().replace('__VERSION__','12 Polymarket').replace('__BUILD__','12.0 · v10 PnL · '+('LIVE' if self.r.a.live else 'PAPER')).replace('__UPTIME_SEC__',str(time.time()-self.r.started))
        return text
    def make_server(self):
        ui=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def auth(self):
                if not ui.password: return True
                expected='Basic '+base64.b64encode(('ajay:'+ui.password).encode()).decode()
                if hmac.compare_digest(self.headers.get('Authorization',''),expected): return True
                self.send_response(401); self.send_header('WWW-Authenticate','Basic realm="BTC"'); self.end_headers(); return False
            def send(self,body,ctype='application/json',status=200):
                if not isinstance(body,bytes): body=json.dumps(body,allow_nan=False).encode() if ctype=='application/json' else body.encode()
                self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                if not self.auth(): return
                p=urlsplit(self.path); q=parse_qs(p.query)
                try:
                    offset=max(0,int(q.get('offset',['0'])[0])); limit=max(1,min(50,int(q.get('limit',['10'])[0])))
                    if p.path in ('/','/data','/controls'): self.send(ui.page({'/':'dashboard_html.html','/data':'data_html.html','/controls':'controls_html.html'}[p.path]),'text/html; charset=utf-8')
                    elif p.path=='/api/state': self.send(ui.snapshot())
                    elif p.path=='/api/controls': self.send(ui.controls())
                    elif p.path=='/api/history': self.send(ui.history(offset,limit))
                    elif p.path=='/api/orders': self.send(ui.orders(q.get('kind',['EF'])[0],offset,limit))
                    elif p.path=='/api/pnl': self.send(ui.pnl(q.get('range',['1D'])[0]))
                    elif p.path=='/api/chart': self.send(ui.chart())
                    elif p.path=='/api/weights': self.send(dict(model_hash=ui.r.hash,weights=[dict(name=n,weight=float(v),anchor=float(v),drift=0,max_drift=0) for n,v in zip(FEATURES,ui.r.m.coef)],version=10,status='Original v10 weights; no online retraining',learning=dict(status='Fixed weights; offline calibration')))
                    elif p.path=='/events': self.send({'error':'polling endpoint used'},status=404)
                    elif p.path=='/export.csv':
                        rows=[dict(r) for r in ui.db.sql('''SELECT s.*,r.actual,r.pnl,r.payout,r.claim_status,(SELECT json_group_array(json_object('id',o.id,'attempt',o.attempt,'status',o.status,'plan',json(o.plan),'latency_ms',o.latency,'reason',o.reason)) FROM orders o WHERE o.epoch=s.epoch) order_attempts,(SELECT json_group_array(json_object('id',f.id,'order_id',f.order_id,'shares',f.shares,'spent',f.spent,'fees',f.fees,'price',f.price,'basis',f.basis)) FROM fills f WHERE f.epoch=s.epoch) fills FROM signals s LEFT JOIN results r USING(epoch) ORDER BY epoch''')]
                        b=io.StringIO(); fields=['model','lane']+list(rows[0]) if rows else ['model','lane','epoch','pnl']
                        w=csv.DictWriter(b,fieldnames=fields); w.writeheader()
                        for row in rows: w.writerow(dict(model='v12_polymarket_v10',lane='LIVE' if ui.r.a.live else 'PAPER',**row))
                        self.send(b.getvalue(),'text/csv; charset=utf-8')
                    else: self.send({'error':'Not found'},status=404)
                except (ValueError,TypeError) as e: self.send({'ok':False,'error':str(e)},status=400)
            def do_POST(self):
                if not self.auth(): return
                # Reject cross-origin browser writes, even on localhost.
                origin=self.headers.get('Origin')
                if origin and urlsplit(origin).netloc!=self.headers.get('Host'): self.send({'ok':False,'error':'Cross-origin request rejected'},status=403); return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=16384: raise ValueError('Invalid request size')
                    if 'application/json' not in self.headers.get('Content-Type',''): raise ValueError('JSON required')
                    self.send(ui.apply(urlsplit(self.path).path,json.loads(self.rfile.read(length))))
                except (ValueError,TypeError,KeyError) as e: self.send({'ok':False,'error':str(e)},status=400)
        return ThreadingHTTPServer((self.r.a.host,self.r.a.port),Handler)
