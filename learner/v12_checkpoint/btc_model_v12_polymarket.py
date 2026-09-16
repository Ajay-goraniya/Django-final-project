#!/usr/bin/env python3
"""Polymarket v12: exact v10 pnl signal with original dashboard. Paper by default."""
import argparse, asyncio, datetime, hashlib, json, math, pathlib, threading, time
from btc_model_v10 import Model, FeatureState, FEATURES
from btc_model_v10_runner import Runner, http_json, GAMMA, CLOB, POLY_WS, US
from poly_core import BookCache, Journal, Executor, PaperBroker
from poly_live import LiveBroker


def official_result(m):
    if m.get('closed') is not True or str(m.get('umaResolutionStatus','')).lower()!='resolved': return None
    try:
        names=m['outcomes']; prices=m['outcomePrices']
        if isinstance(names,str): names=json.loads(names)
        if isinstance(prices,str): prices=json.loads(prices)
        if len(names)!=2 or sorted(map(float,prices))!=[0.,1.]: return None
        winner=str(names[list(map(float,prices)).index(1.)]).upper()
        return winner if winner in ('UP','DOWN') else None
    except (KeyError,TypeError,ValueError): return None

class PolyRunner(Runner):
    def __init__(self,a):
        self.a=a; self.m=Model(a.model); self.st=FeatureState()
        # Keep the exact model/weights. No retraining or threshold changes.
        self.hash=hashlib.sha256(pathlib.Path(a.model).read_bytes()).hexdigest()
        import fcntl
        pathlib.Path(a.db).resolve().parent.mkdir(parents=True,exist_ok=True)
        self.process_lock=open(str(pathlib.Path(a.db).resolve())+'.lock','a')
        try: fcntl.flock(self.process_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('Database already used by another process')
        self.db=Journal(a.db,'LIVE' if a.live else 'PAPER',self.hash)
        self.books=BookCache(); self.broker=LiveBroker(self.books) if a.live else PaperBroker(self.books,self.db)
        self.executor=Executor(self.db,self.books,self.broker,a.quote_age_ms/1000,a.pad_ticks)
        self.age={k:0. for k in ('spot','perp','depth','venue')}; self.msgs={}; self._agg=None
        self.market={}; self.info={}; self.terms_age={}; self.last_decision={}; self.started=time.time()
        self.cash=None; self.cash_at=0.; self.current_candle={}; self.revision=0; self.error=''
        self.db.set('master',False) if a.live else None # explicit arming through old controls
        from poly_dashboard import Dashboard
        self.ui=Dashboard(self)
    async def resolve_market(self,ep):
        if self.market.get(ep): return self.market[ep]
        data=await asyncio.to_thread(http_json,GAMMA.format(ep))
        try:
            ms=[m for e in data for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
            if len(ms)!=1: return None
            m=ms[0]
            if not m.get('acceptingOrders') or m.get('closed'): return None
            names=m['outcomes']; toks=m['clobTokenIds']
            if isinstance(names,str): names=json.loads(names)
            if isinstance(toks,str): toks=json.loads(toks)
            if len(names)!=2 or len(toks)!=2: return None
            pairs={str(n).upper():str(t) for n,t in zip(names,toks)}
            if set(pairs)!={'UP','DOWN'}: return None
            self.market[ep]=(pairs['UP'],pairs['DOWN']); self.info[ep]=m
            return self.market[ep]
        except (KeyError,TypeError,ValueError): return None
    def publish(self):
        ep=int(time.time()//300)*300; toks=self.market.get(ep,())
        quotes=[self.books.quote(t,self.a.quote_age_ms/1000) for t in toks]
        if len(quotes)!=2 or not all(quotes):
            self.st.on_venue_quote(None,None,None,None); self.age['venue']=0.; return False
        u,d=quotes; self.st.on_venue_quote(u['ask'],u['bid'],d['ask'],d['bid'])
        self.age['venue']=time.time()-max(u['age_ms'],d['age_ms'])/1000; return True
    async def venue(self):
        import websockets
        while True:
            ep=int(time.time()//300)*300
            cur,nxt=await asyncio.gather(self.resolve_market(ep),self.resolve_market(ep+300))
            toks=[t for pair in (cur,nxt) if pair for t in pair]
            if not toks: await asyncio.sleep(2); continue
            self.books.clear()
            try:
                async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
                    await w.send(json.dumps({'assets_ids':toks,'type':'market'}))
                    async def ping():
                        while True: await asyncio.sleep(5); await w.send('PING')
                    task=asyncio.create_task(ping())
                    try:
                        while time.time()<ep+330:
                            msg=await asyncio.wait_for(w.recv(),15)
                            if msg=='PONG': continue
                            data=json.loads(msg)
                            for ev in data if isinstance(data,list) else [data]:
                                if isinstance(ev,dict): self.books.apply(ev)
                            self.publish(); self.msgs['venue']=self.msgs.get('venue',0)+1
                    finally: task.cancel(); await asyncio.gather(task,return_exceptions=True)
            except Exception as e: self.error='Venue reconnect: '+type(e).__name__; await asyncio.sleep(1)
            finally:
                self.books.clear(); self.publish()
                for old in list(self.market):
                    if old<ep-600:
                        for t in self.market.pop(old): self.books.terms.pop(t,None); self.terms_age.pop(t,None)
                        self.info.pop(old,None)
    def on_kline(self,j):
        k=j.get('k',{}); ep=int(k['t'])//1000
        c=dict(time=ep*1000,open=float(k['o']),high=float(k['h']),low=float(k['l']),close=float(k['c']),volume=float(k['v']),seconds_left=max(0,ep+300-time.time()))
        self.current_candle=c
        if k.get('x'):
            self.db.sql('INSERT OR REPLACE INTO candles VALUES(?,?,?,?,?,?)',(ep,c['open'],c['high'],c['low'],c['close'],c['volume'])); self.revision+=1
    def decide_now(self):
        now=time.time(); ep=int(now//300)*300
        if not self.publish(): return {'fire':False,'reason':'Waiting for fresh UP and DOWN books'}
        if any(now-self.age[k]>2 for k in ('spot','perp','depth')): return {'fire':False,'reason':'Waiting for fresh Binance feeds'}
        s,p=self.st.s_ts,self.st.p_ts
        if len(s)<51 or len(p)<21 or s[-1]-s[0]<600*US or p[-1]-p[0]<60*US: return {'fire':False,'reason':'Warming up: 10 minutes of spot / 60 seconds of perpetual trades'}
        d=self.m.decide(self.st,ep*US,int(now*US),mode='pnl',ev_threshold=self.a.ev)
        f=self.st.features(ep*US,int(now*US)) or {}
        d['features']={k:float(v) for k,v in f.items() if isinstance(v,(int,float)) and math.isfinite(v)}
        d['features']['ts_ms']=int(now*1000)
        return d
    async def decide_loop(self):
        last=0
        while True:
            d=self.decide_now(); ep=int(time.time()//300)*300; self.last_decision=d
            if d.get('fire') and self.ui.allowed() and self.cash is not None and time.monotonic()-self.cash_at<15:
                token=self.market[ep][0 if d['side']=='UP' else 1]; stake=self.db.get('next_stake',1.)
                reserved=self.db.sql("SELECT coalesce(sum(json_extract(plan,'$.budget')),0) FROM orders WHERE status IN ('SUBMITTING','UNKNOWN','PENDING')")[0][0]
                if token in self.books.terms and stake<=max(0,self.cash-reserved):
                    f=self.st.features(ep*US,int(time.time()*US)) or {}
                    d['features']={k:float(v) for k,v in f.items() if isinstance(v,(int,float)) and math.isfinite(v)}
                    d['signal_price']=float(self.st.s_px[-1]) if self.st.s_px else None
                    await self.executor.fire(ep,d,token,self.info[ep]['conditionId'],stake,lambda: self.decide_now() if self.ui.allowed() else {'fire':False})
                    self.revision+=1
            if time.time()-last>15:
                self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(d))); last=time.time()
            await asyncio.sleep(.25)
    async def housekeeping(self):
        while True:
            try:
                ep=int(time.time()//300)*300
                for token in [t for e in (ep,ep+300) for t in self.market.get(e,())]:
                    if token not in self.books.terms or time.monotonic()-self.terms_age.get(token,-1000)>30:
                        if self.a.live: terms=await asyncio.wait_for(self.broker.metadata(token),8)
                        else:
                            b=await asyncio.to_thread(http_json,CLOB.format(token))
                            if not b: continue
                            terms=(float(b['tick_size']),float(b['min_order_size']),self.m.fee,1.)
                        self.books.terms[token]=terms; self.terms_age[token]=time.monotonic()
                if self.a.live: self.cash=await asyncio.wait_for(self.broker.cash(),8)
                else:
                    held=self.db.sql('SELECT coalesce(sum(spent+fees),0) FROM fills WHERE epoch NOT IN (SELECT epoch FROM results)')[0][0]
                    self.cash=max(0.,self.a.capital+self.db.metrics()['pnl']-held)
                self.cash_at=time.monotonic(); self.ui.update_stake()
                self.db.sql('DELETE FROM diagnostics WHERE ts<?',(time.time()-7*86400,))
                self.db.sql('DELETE FROM candles WHERE epoch<?',(time.time()-30*86400,))
            except Exception as e: self.error='Metadata/balance: '+type(e).__name__
            await asyncio.sleep(5)
    async def reconcile_loop(self):
        while True: await self.executor.reconcile(); await asyncio.sleep(1)
    async def grade_loop(self):
        while True:
            rows=self.db.sql('SELECT DISTINCT epoch FROM fills WHERE epoch<? AND epoch NOT IN (SELECT epoch FROM results)',(time.time()-390,))
            for row in rows:
                ep=row[0]; data=await asyncio.to_thread(http_json,GAMMA.format(ep))
                if not data: continue
                ms=[m for e in data for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
                result=official_result(ms[0]) if len(ms)==1 else None
                if result: self.db.grade(ep,result); self.revision+=1
            self.db.halt_check(); await asyncio.sleep(20)
    async def claim_loop(self):
        while True:
            if self.a.live:
                for old in self.db.sql("SELECT epoch,claim_id FROM results WHERE claim_status IN ('REVIEW','SUBMITTING') AND claim_id IS NOT NULL"):
                    try:
                        state=await asyncio.wait_for(self.broker.claim_state(old['claim_id']),8)
                        if state=='STATE_CONFIRMED': self.db.sql("UPDATE results SET claim_status='CONFIRMED' WHERE epoch=?",(old['epoch'],))
                        elif state in ('STATE_FAILED','STATE_INVALID'): self.db.sql("UPDATE results SET claim_status='PENDING',claim_id=NULL WHERE epoch=?",(old['epoch'],))
                    except Exception: pass
            for row in self.db.sql("SELECT r.*,s.condition_id FROM results r JOIN signals s USING(epoch) WHERE claim_status='PENDING'"):
                if not self.a.live or row['payout']==0:
                    self.db.sql('UPDATE results SET claim_status=? WHERE epoch=?',('PAPER' if not self.a.live else 'NO_PAYOUT',row['epoch'])); continue
                self.db.sql("UPDATE results SET claim_status='SUBMITTING' WHERE epoch=?",(row['epoch'],))
                try:
                    h=await asyncio.wait_for(self.broker.redeem(row['condition_id']),20)
                    self.db.sql('UPDATE results SET claim_id=? WHERE epoch=?',(('relayer:'+h.transaction_id) if h.transaction_id else ('tx:'+h.transaction_hash),row['epoch']))
                    outcome=await asyncio.wait_for(h.wait(),45)
                    # The SDK terminal state must confirm success; no result guessed.
                    state='CONFIRMED' if getattr(outcome,'transaction_hash',None) else 'REVIEW'
                    self.db.sql('UPDATE results SET claim_status=? WHERE epoch=?',('CONFIRMED' if state in ('CONFIRMED','STATE_CONFIRMED','STATE_MINED','MINED') else 'REVIEW',row['epoch']))
                except Exception: self.db.sql("UPDATE results SET claim_status='REVIEW' WHERE epoch=?",(row['epoch'],))
            await asyncio.sleep(20)
    async def chart_seed(self):
        data=await asyncio.to_thread(http_json,'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=288')
        if isinstance(data,list):
            for k in data:
                if k[0]/1000+300<time.time(): self.db.sql('INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?)',(int(k[0])//1000,*map(float,k[1:6])))
            self.revision+=1
    async def main(self):
        if self.a.live:
            check=await asyncio.to_thread(http_json,'https://polymarket.com/api/geoblock')
            if not isinstance(check,dict) or check.get('blocked') is not False: raise SystemExit('Venue geographic eligibility check did not pass')
            await self.broker.open()
        server=self.ui.make_server(); threading.Thread(target=server.serve_forever,daemon=True).start()
        print('Polymarket v12', 'LIVE (master OFF)' if self.a.live else 'PAPER',f'http://{self.a.host}:{self.a.port}',flush=True)
        try:
            await asyncio.gather(self.chart_seed(),self.ws('wss://data-stream.binance.vision/ws/btcusdt@aggTrade',self.on_spot,'spot'),self.ws('wss://fstream.binance.com/ws/btcusdt@trade',self.on_perp,'perp'),self.ws('wss://fstream.binance.com/ws/btcusdt@depth20@100ms',self.on_depth,'depth'),self.ws('wss://data-stream.binance.vision/ws/btcusdt@kline_5m',self.on_kline,'chart'),self.venue(),self.decide_loop(),self.housekeeping(),self.reconcile_loop(),self.grade_loop(),self.claim_loop())
        finally:
            server.shutdown(); server.server_close()
            if self.a.live: await self.broker.close()
            self.db.c.close(); self.process_lock.close()

def args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true'); p.add_argument('--port',type=int,default=8787); p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--model',default=str(pathlib.Path(__file__).with_name('model_v10.json')))
    p.add_argument('--db',default='polymarket_v12_paper.sqlite3'); p.add_argument('--capital',type=float,default=50)
    p.add_argument('--mode',choices=['pnl'],default='pnl'); p.add_argument('--ev',type=float,default=None)
    p.add_argument('--quote-age-ms',type=float,default=750); p.add_argument('--pad-ticks',type=int,default=1)
    a=p.parse_args()
    if not math.isfinite(a.capital) or a.capital<=0 or not 0<a.quote_age_ms<=2000 or a.pad_ticks<0: p.error('invalid capital/quote age/pad')
    if a.ev is not None and not math.isfinite(a.ev): p.error('invalid EV')
    if not pathlib.Path(a.model).is_file(): p.error('model_v10.json required')
    return a
if __name__=='__main__':
    try: asyncio.run(PolyRunner(args()).main())
    except KeyboardInterrupt: print('Stopped; saved database retained')
