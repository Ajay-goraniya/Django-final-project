#!/usr/bin/env python3
"""Polymarket v12: exact v10 pnl signal with original dashboard. Paper by default."""
import argparse, asyncio, datetime, hashlib, json, math, pathlib, threading, time
from btc_model_v10 import Model, FeatureState, FEATURES
from btc_model_v10_runner import Runner, http_json, GAMMA, CLOB, POLY_WS, US
import poly_feeds, poly_lanes
from poly_core import BookCache, Journal, Executor, PaperBroker, order_plan
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
        self.executor=Executor(self.db,self.books,self.broker,a.quote_age_ms/1000,a.pad_ticks,
                               budget_s=getattr(a,'execution_budget_ms',2000)/1000,
                               post_timeout_s=getattr(a,'post_timeout_ms',1200)/1000,
                               attempts=getattr(a,'max_attempts',4))
        self.age={k:0. for k in ('spot','perp','depth','venue')}; self.msgs={}; self._agg=None
        # Arrival age AND event lag per stream; see poly_feeds for why both.
        self.health=poly_feeds.FeedHealth(('spot','perp','depth','venue'))
        # Last authenticated venue snapshot: cash, positions, PnL as Polymarket
        # reports them. Refreshed by venue_truth_loop; never computed here.
        # Named venue_state, not venue: Runner.venue() is the Polymarket book
        # websocket coroutine and an attribute of the same name shadows it.
        self.venue_state={}
        # MAIN/REVERSAL run on the Binance pressure engine, independent of the
        # v10 model that drives EF. See poly_lanes for the port and its caveats.
        self.lanes=poly_lanes.LaneEngine()
        self.lane_decision={}
        self.market={}; self.info={}; self.terms_age={}; self.last_decision={}; self.started=time.time()
        self._wait_census={}; self._wait_flushed=time.monotonic()
        self.cash=None; self.cash_at=0.; self.account_snapshot={}; self.account_positions=[]; self.current_candle={}; self.revision=0; self.error=''
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
        # 12.9.0: ONE quote-age dial. This read the CLI flag while the EV gate
        # and the executor read ev_settings.quote_age_ms, so the model could
        # decide on a quote the executor then waited on as stale (or the
        # reverse). Meta value, CLI as the seed/fallback - see quote_age_s().
        quotes=[self.books.quote(t,self.quote_age_s()) for t in toks]
        if len(quotes)!=2 or not all(quotes):
            self._count_wait(toks,quotes)
            self.st.on_venue_quote(None,None,None,None); self.age['venue']=0.; return False
        self._wait_census['ok']=self._wait_census.get('ok',0)+1
        u,d=quotes; self.st.on_venue_quote(u['ask'],u['bid'],d['ask'],d['bid'])
        self.age['venue']=time.time()-max(u['age_ms'],d['age_ms'])/1000
        self.health.arrival['venue']=time.time(); self.health.lag['venue']=max(u['age_ms'],d['age_ms'])/1000.
        self.health.msgs['venue']=self.health.msgs.get('venue',0)+1
        return True
    async def venue(self):
        import websockets
        while True:
            ep=int(time.time()//300)*300
            cur,nxt=await asyncio.gather(self.resolve_market(ep),self.resolve_market(ep+300))
            toks=[t for pair in (cur,nxt) if pair for t in pair]
            if not toks: await asyncio.sleep(2); continue
            # Drop only tokens we are no longer subscribed to. Clearing the whole
            # cache here (and again in the finally below) meant every token was
            # re-snapshotted at subscribe and never again, so a fire early in a
            # candle priced off a book snapshotted ~5 minutes earlier and patched
            # only by deltas we cannot verify we received in full. That is the
            # phantom-level mechanism with a cause, not a symptom.
            self.books.prune(toks)
            try:
                async with websockets.connect(POLY_WS,ping_interval=None,max_size=2**23) as w:
                    await w.send(json.dumps({'assets_ids':toks,'type':'market'}))
                    async def ping():
                        while True: await asyncio.sleep(5); await w.send('PING')
                    task=asyncio.create_task(ping())
                    try:
                        # ep+345 keeps the rollover clear of the 15-240 s
                        # decision window of the next candle: the teardown and
                        # resubscribe now land at sec 45, after the window opens
                        # at 15 but while the next candle's token is already
                        # subscribed from this cycle.
                        while time.time()<ep+345:
                            msg=await asyncio.wait_for(w.recv(),15)
                            if msg=='PONG': continue
                            data=json.loads(msg)
                            for ev in data if isinstance(data,list) else [data]:
                                if isinstance(ev,dict): self.books.apply(ev)
                            self.publish(); self.msgs['venue']=self.msgs.get('venue',0)+1
                    finally: task.cancel(); await asyncio.gather(task,return_exceptions=True)
            except Exception as e: self.error='Venue reconnect: '+type(e).__name__; await asyncio.sleep(1)
            finally:
                self.books.prune(toks); self.publish()
                for old in list(self.market):
                    if old<ep-600:
                        for t in self.market.pop(old): self.books.terms.pop(t,None); self.terms_age.pop(t,None)
                        self.info.pop(old,None)
    def on_spot(self,j):
        super().on_spot(j)
        try: self.lanes.on_spot_trade(int(j['T']),float(j['p']),float(j['q']),bool(j['m']))
        except Exception: pass
    @staticmethod
    def ref_samples(j):
        """(ts_us, price) pairs for BTC/USD out of one RTDS frame, whatever its envelope.

        The public feed wraps each update as {topic, type, payload:{symbol,value,timestamp}}
        (single dict or a list of them); field names are matched loosely and anything that
        is not a positive BTC/USD price is skipped, so a format change degrades to "no
        reference samples" (ref_src=0 in the features) instead of an exception."""
        out=[]; stack=[j]
        while stack:
            x=stack.pop()
            if isinstance(x,list): stack.extend(x); continue
            if not isinstance(x,dict): continue
            sym=str(x.get('symbol') or x.get('asset') or x.get('pair') or '').lower().replace('-','/').replace('_','/')
            val=x.get('value',x.get('price',x.get('full_accuracy_value')))
            ts=x.get('timestamp',x.get('ts',x.get('time')))
            if sym in ('btc/usd','btcusd','btc') and isinstance(val,(int,float,str)) and ts is not None:
                try:
                    v=float(val); t=float(ts)
                    if v>1e9: v=v/1e18          # chainlink full_accuracy_value: integer string, 1e18 fixed point (Task 100)
                    t_us=int(t*1e6) if t<1e11 else (int(t*1e3) if t<1e14 else int(t))   # s / ms / us
                    if v>0: out.append((t_us,v))
                except (TypeError,ValueError): pass
            for k in ('payload','data','message','updates'):
                if k in x: stack.append(x[k])
        return out
    def on_ref(self,j):
        try:
            for t_us,v in self.ref_samples(j): self.st.on_ref_price(t_us,v)
        except Exception: pass
    def on_depth(self,j):
        super().on_depth(j)
        try:
            b=[(float(x[0]),float(x[1])) for x in j.get('b',[])][:20]
            a=[(float(x[0]),float(x[1])) for x in j.get('a',[])][:20]
            if b and a: self.lanes.on_depth(b,a)
        except Exception: pass
    def on_kline(self,j):
        k=j.get('k',{}); ep=int(k['t'])//1000
        c=dict(time=ep*1000,open=float(k['o']),high=float(k['h']),low=float(k['l']),close=float(k['c']),volume=float(k['v']),seconds_left=max(0,ep+300-time.time()))
        self.current_candle=c
        self.lanes.on_candle(c)
        if k.get('x'):
            self.lanes.on_closed_candle(c)
            self.db.sql('INSERT OR REPLACE INTO candles VALUES(?,?,?,?,?,?)',(ep,c['open'],c['high'],c['low'],c['close'],c['volume'])); self.revision+=1
    def decide_now(self):
        now=time.time(); ep=int(now//300)*300
        if not self.publish(): return {'fire':False,'reason':'Waiting for fresh UP and DOWN books'}
        bad=self.health.stale(('spot','perp','depth'))
        if bad: return {'fire':False,'reason':'Binance feed not usable: '+'; '.join(f'{k} {v}' for k,v in bad.items())}
        s,p=self.st.s_ts,self.st.p_ts
        if len(s)<51 or len(p)<21 or s[-1]-s[0]<600*US or p[-1]-p[0]<60*US: return {'fire':False,'reason':'Warming up: 10 minutes of spot / 60 seconds of perpetual trades'}
        # EV mode is a live control, not a launch flag. 'regime' uses the model's
        # own per-volatility thresholds (0.15 low, 0.25 mid/high); 'fixed' applies
        # one number to every candle; 'accuracy' hands over to the model's
        # confidence/EV floors instead. The CLI --ev still seeds it on first run.
        mode,ev_thr=self.ev_setting()
        d=self.m.decide(self.st,ep*US,int(now*US),
                        mode=('accuracy' if mode=='accuracy' else 'pnl'),
                        ev_threshold=ev_thr)
        f=self.st.features(ep*US,int(now*US)) or {}
        d['features']={k:float(v) for k,v in f.items() if isinstance(v,(int,float)) and math.isfinite(v)}
        d['features']['ts_ms']=int(now*1000)
        # EV is a GATE ON THE DECISION, not a post-mortem on a signal already
        # shown as fired. Until 12.4.0 the model decided against the raw ask and
        # the padded-price EV check ran later inside order_plan, so the dashboard
        # and the chart showed a fire that was never going to trade. That is the
        # single most misleading thing this build did. The same arithmetic now
        # runs here, at the price we would actually pay, and a signal that cannot
        # clear it never claims to have fired.
        # Honesty about p comes BEFORE the EV gate, or the gate judges a claim
        # the model cannot back. Off unless the operator turns it on.
        d=self._calibrate(d)
        if d.get('fire'): d=self._gate_on_padded_ev(ep,d)
        return d
    CALIBRATION_DEFAULT=dict(enabled=False,cut=0.80,to=0.784)
    def calibration(self):
        cfg=dict(self.CALIBRATION_DEFAULT); cfg.update(self.db.get('calibration') or {})
        try:
            cfg['cut']=float(cfg['cut']); cfg['to']=float(cfg['to'])
            cfg['enabled']=bool(cfg['enabled'])
        except (TypeError,ValueError): return dict(self.CALIBRATION_DEFAULT)
        # `to` must be at or below `cut`: this may only ever LOWER a claim.
        # A setting that raises one is a way to make the model more confident by
        # configuration, which is the opposite of the point.
        if not (0.5<cfg['cut']<1.0 and 0.5<cfg['to']<=cfg['cut']):
            return dict(self.CALIBRATION_DEFAULT)
        return cfg
    def _calibrate(self,d):
        """Correct what the model claims about itself, where it overclaims.

        Measured 09-13 over 537 decided candles graded on `candles.actual`:
        below p=0.80 the model is honest, every bucket inside 1.5 points. At
        p>=0.80 it claims 0.912 and delivers 0.756. EV is p/cost-1, so the
        trades that clear the bar are exactly the overstated ones - which is why
        a lane with real skill (0.651 accuracy against a 0.530 base) ran 7-of-20
        and hit its own kill rule.

        Fitted on the chronological FIRST half and validated on the second it
        never saw: the out-of-sample gap falls from -0.171 to -0.038. A global
        shrink was tried first and failed (k=0.98, no improvement) - the
        miscalibration is confined to one region and cannot be fixed globally.

        This is not a gate and moves no threshold. One number the model states
        about itself is replaced by what that statement has historically been
        worth. EF only: the fit is on EF's p, and MAIN's probability comes from a
        different estimator, so applying it there would be unfounded.

        OFF by default. Shipping it inert lets it be deployed without changing
        what trades, and turned on deliberately.
        """
        cfg=self.calibration()
        if not cfg['enabled'] or d.get('p') is None: return d
        try: p=float(d['p'])
        except (TypeError,ValueError): return d
        if p<cfg['cut']: return d
        return dict(d,p=cfg['to'],p_raw=p,calibrated=True)
    def _gate_on_padded_ev(self,ep,d):
        """Re-decide against the price we would really pay. Never widens a fire."""
        toks=self.market.get(ep)
        if not toks: return dict(d,fire=False,reason='Market not resolved yet')
        token=toks[0 if d['side']=='UP' else 1]
        terms=self.books.terms.get(token)
        if terms is None:
            return dict(d,fire=False,reason='No venue terms for this token yet')
        q=self.books.quote(token,self.quote_age_s())
        if not q: return dict(d,fire=False,reason='No fresh quote to price against')
        pad=self.pad_ticks(); stake=self.db.get('next_stake',1.)
        # 12.9.0: the same depth rule as the executor (poly_core Executor.fire
        # passes require_depth=self.require_depth, False for both brokers). This
        # call left it at order_plan's default True, so "book too thin at cap"
        # could refuse here a fire the executor would have sent.
        try:
            plan=order_plan(q,terms,stake,d,pad,band=self.slippage_mode()=='band',require_depth=self.executor.require_depth)
        except ValueError as e:
            out=dict(d,fire=False,reason=f'EV at padded price: {e}',ev_gate=str(e),
                     ev_gate_pad=pad,ev_gate_ask=q['ask'])
            return out
        return dict(d,ev_gate='pass',ev_gate_pad=pad,ev_gate_ask=q['ask'],ev_gate_cap=plan['cap'])
    async def decide_loop(self):
        self._decide_last=0
        while True:
            try:
                await self._decide_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Unguarded until 12.4.2, and gather() has no return_exceptions,
                # so one raise here exited the whole process holding open
                # positions and stopped reconciling and claiming. ep is
                # recomputed after decide_now() returns, so a candle rollover in
                # that window is a plain KeyError on self.market[ep].
                self.error=f'decide loop: {type(e).__name__}'
                try: self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),0,json.dumps(dict(
                    reason='decide_loop_error',error=type(e).__name__,detail=str(e)[:400]))))
                except Exception: pass
            await asyncio.sleep(.25)
    async def _decide_once(self):
        if True:
            d=self.decide_now(); ep=int(time.time()//300)*300; self.last_decision=d
            self._sync_executor_dials()
            if d.get('fire') and self.ui.allowed() and self.cash is not None and time.monotonic()-self.cash_at<15:
                token=self.market[ep][0 if d['side']=='UP' else 1]; stake=self.db.get('next_stake',1.)
                reserved=self.db.live_reserve()
                # A skip for missing terms used to be silent and therefore
                # indistinguishable from no signal. terms are dropped on every
                # tick_size_change and refetched by housekeeping's 5 s loop, so
                # the gap is real and repeating; record it or it cannot be
                # measured.
                if token not in self.books.terms:
                    self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(
                        reason='no_terms',kind='EF',side=d.get('side'),
                        since_tick_change_s=self._since_tick_change(token)))))
                if token in self.books.terms and stake<=max(0,self.cash-reserved):
                    f=self.st.features(ep*US,int(time.time()*US)) or {}
                    d['features']={k:float(v) for k,v in f.items() if isinstance(v,(int,float)) and math.isfinite(v)}
                    d['signal_price']=float(self.st.s_px[-1]) if self.st.s_px else None
                    await self.executor.fire(ep,d,token,self.info[ep]['conditionId'],stake,lambda: self.decide_now() if self.ui.allowed() else {'fire':False})
                    self.revision+=1
            await self.lane_loop(ep)
            if time.time()-self._decide_last>15:
                self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(d))); self._decide_last=time.time()
    @staticmethod
    def skip_reason(status,detail):
        """Say WHY in numbers, not just that it happened.

        User, 09-13: "i just don't see better with my eyes that's why i was a bit
        concerned". The screen said SKIPPED and nothing else, so "MAIN called
        DOWN and was skipped" read as a fault when it was the engine declining
        to pay 0.87 for something worth 0.51. The numbers that settle it were
        already in the diagnostics row; they just were not shown.

        A separate method because it was inline and therefore untestable, which
        is how it stayed uninformative for so long.
        """
        if not detail: return status
        try: d=json.loads(detail) or {}
        except (ValueError,TypeError): d={}
        if not isinstance(d,dict): return f'{status}: {str(detail)[:200]}'
        why=d.get('error') or d.get('reason') or str(detail)
        ask,p,thr=d.get('ask'),d.get('p'),d.get('threshold')
        if None not in (ask,p,thr):
            try:
                why=(f'{why} - ask {float(ask):.2f}, worth {float(p):.2f}, '
                     f'max payable {float(p)/(1.0+float(thr)):.2f} at EV {float(thr):.2f}')
            except (TypeError,ValueError,ZeroDivisionError): pass
        return f'{status}: {str(why)[:200]}'
    async def lane_loop(self,ep):
        """Evaluate MAIN and REVERSAL and fire whichever is ready.

        Each lane is gated by its own Trade Controls toggle through the same
        allowed() check EF uses, so the master switch and the per-kind switch
        behave identically for all three.

        A lane that is switched off still EVALUATES, and its decision is written
        to `diagnostics` below - but the allowed() check returns before anything
        reaches `signals`. So a row in `signals` for a kind is proof that kind's
        permission gate passed at that moment, which is what makes the table
        usable as an audit trail. (This docstring previously claimed an off lane
        was still recorded in signals; it is not, and the session on the AWS box
        caught that on 09-13 while using signals rows as exactly that proof.)"""
        now=time.time()
        bad=self.health.stale(('spot','depth'))
        if bad or not self.current_candle: return
        try: decision=self.lanes.evaluate(int(now*1000))
        except Exception as e:
            self.error=f'lane engine: {type(e).__name__}'; return
        self.lane_decision=self.lanes.monitor()
        if not decision: return
        kind=decision['kind']
        # RECORD THE PRICE THE LANE SAW, on every decision and not only on the
        # ones that reach order_plan.
        #
        # Without this the most important question about MAIN is unanswerable.
        # It has fired 0 orders in three hours; the candidate fix is that it
        # waits 60 aligned reads (~15 s) and the side it wants reprices in that
        # time - one candle shows EV +0.2306 at ask 0.68 earlier in the streak
        # against +0.0307 at the refusal. Testing that needs the ask THROUGHOUT
        # the streak, and on 09-13 the journal had 145 non-refusal MAIN rows
        # carrying `p` and ZERO carrying an ask. The refusal rows exist but span
        # under a second each - four retries, not a time series.
        #
        # The book is venue data, not a lane's opinion, so recording it here
        # costs nothing and commits to nothing. One field, and the question
        # becomes answerable from a few hours of live data instead of inferred
        # from 8-second-stale pairings.
        _px={}
        try:
            _t=self.market.get(ep)
            if _t:
                for _k,_tok in (('ask_up',_t[0]),('ask_dn',_t[1])):
                    _q=self.books.quote(_tok,self.quote_age_s())
                    _px[_k]=(_q or {}).get('ask')
        except Exception: pass
        self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',
                    (now,ep,json.dumps(dict(decision,lane=kind,**_px))))
        if not self.ui.allowed(kind): return
        if self.cash is None or time.monotonic()-self.cash_at>=15: return
        if ep not in self.market or ep not in self.info: return
        self._sync_executor_dials()             # live execution dials
        token=self.market[ep][0 if decision['side']=='UP' else 1]
        if token not in self.books.terms:
            self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(
                reason='no_terms',kind=kind,side=decision.get('side'),
                since_tick_change_s=self._since_tick_change(token)))))
            return
        stake=self.db.get('next_stake',1.); reserved=self.db.live_reserve()
        if stake>max(0,(self.cash or 0)-reserved): return
        d=dict(decision); d['fire']=True
        # The lane supplies the side and its probability; the EV bar the order
        # must clear is the same regime threshold the venue book is priced
        # against, so a lane signal cannot buy at a price EF would refuse.
        d.setdefault('threshold',(self.m.threshold(self.st.features(ep*US,int(now*US)) or {})
                                  if hasattr(self.m,'threshold') else 0.25))
        d['features']={'ts_ms':int(now*1000)}
        d['signal_price']=float(self.st.s_px[-1]) if self.st.s_px else None
        await self.executor.fire(ep,d,token,self.info[ep]['conditionId'],stake,
                                 (lambda k=kind,dd=d: dd if self.ui.allowed(k) else {'fire':False}),kind=kind)
        # Read back what the venue leg actually did. A signal that never reached
        # the book must not be reported, or treated, as a position.
        row=self.db.sql('SELECT status FROM signals WHERE epoch=? AND kind=?',(ep,kind))
        status=row[0]['status'] if row else 'UNKNOWN'
        placed=status in ('PENDING','FILLED','RESERVED')
        reason=''
        if not placed:
            diag=self.db.sql('SELECT detail FROM diagnostics WHERE epoch=? ORDER BY ts DESC LIMIT 1',(ep,))
            # Say WHY in numbers, not just that it happened.
            #
            # User, 09-13: "i just don't see better with my eyes that's why i was
            # a bit concerned". The screen said SKIPPED and nothing else, so
            # "MAIN called DOWN and was skipped" looked like a fault when it was
            # the engine declining to pay 0.87 for something worth 0.51. The
            # numbers that settle it are already in the diagnostics row - they
            # just were not being shown.
            reason=self.skip_reason(status,diag[0]['detail'] if diag else None)
        self.lanes.confirm(kind,placed,reason)
        self.lane_decision=self.lanes.monitor()
        if not placed:
            print(f'[{kind}] signal not executed - {reason}',flush=True)
        self.revision+=1
    def _since_tick_change(self,token):
        """Seconds since this token's last tick_size_change, or None."""
        tc=getattr(self.books,'tick_changes',{}).get(str(token))
        return round(time.monotonic()-tc['at'],2) if tc else None
    # 12.9.0 cadences. Monitors (halt_check, _wipeout_check, _main_oneshot_check)
    # ran every 1-5 s for rows that change a few times an hour; the retention
    # DELETEs ran every 5 s over an unindexed table. All on the loop thread.
    MONITOR_EVERY_S=60.0
    RETENTION_EVERY_S=3600.0
    _clock=staticmethod(time.monotonic)
    def _due(self,name,every_s):
        """True at most once per every_s seconds for `name` (monotonic, first call True)."""
        c=self.__dict__.setdefault('_cadence',{}); now=self._clock(); last=c.get(name)
        if last is not None and now-last<every_s: return False
        c[name]=now; return True
    async def housekeeping(self):
        while True:
            try:
                ep=int(time.time()//300)*300
                # Persist the feed counters. They lived only in memory, so a
                # post-mortem could not tell how many events the clock guard
                # dropped, or how stale the books had been running. Written once
                # a cycle and diffable across restarts.
                try:
                    h=self.books.health()
                    h['snapshot_age_s']={t:round(time.monotonic()-b.get('snapshot',b.get('arrival',0)),1)
                                         for t,b in list(self.books.books.items())}
                    self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',
                                (time.time(),ep,json.dumps(dict(h,reason='feed_counters'))))
                except Exception: pass
                for token in [t for e in (ep,ep+300) for t in self.market.get(e,())]:
                    if token not in self.books.terms or time.monotonic()-self.terms_age.get(token,-1000)>30:
                        if self.a.live: terms=await asyncio.wait_for(self.broker.metadata(token),8)
                        else:
                            b=await asyncio.to_thread(http_json,CLOB.format(token))
                            if not b: continue
                            terms=(float(b['tick_size']),float(b['min_order_size']),self.m.fee,1.)
                        self.books.terms[token]=terms; self.terms_age[token]=time.monotonic()
                if self.a.live:
                    snap=await asyncio.wait_for(self.broker.account_snapshot(),8)
                    self.account_snapshot=snap; self.account_positions=list(snap.get('positions') or [])
                    self.cash=float(snap['cash'])
                else:
                    held=self.db.sql('SELECT coalesce(sum(spent+fees),0) FROM fills WHERE epoch NOT IN (SELECT epoch FROM results)')[0][0]
                    self.cash=max(0.,self.a.capital+self.db.metrics()['pnl']-held)
                self.cash_at=time.monotonic(); self.ui.update_stake()
                if self._due('wipeout',self.MONITOR_EVERY_S): self._wipeout_check()
                if self._due('floor',self.MONITOR_EVERY_S): self._floor_check()
                if self._due('master_watch',self.MONITOR_EVERY_S): self._master_watch()
                self._sample_ambient_age(int(time.time()//300)*300)
                self._flush_wait_census(int(time.time()//300)*300)
                if self._due('retention',self.RETENTION_EVERY_S):
                    self.db.sql('DELETE FROM diagnostics WHERE ts<?',(time.time()-7*86400,))
                    self.db.sql('DELETE FROM candles WHERE epoch<?',(time.time()-30*86400,))
            except Exception as e: self.error='Metadata/balance: '+type(e).__name__
            await asyncio.sleep(5)
    MASTER_OFF_WARN_S=300.0
    MASTER_OFF_REPEAT_S=1800.0
    def _master_watch(self):
        """Say it out loud when a LIVE engine is sitting disarmed.

        09-16: a deploy at 03:40 parked master OFF by safe-start, as it is meant to, and the
        re-arm step waited on a permission prompt until 07:42. Four hours, 962 decide rows,
        four fires the model wanted and could not send, and nothing anywhere said so - the
        engine looked healthy because it was healthy. Silence is the defect, not the state.

        Observation only: it never arms anything (master is the operator's alone). It writes
        a MASTER_OFF diagnostics row and prints, once past MASTER_OFF_WARN_S and then every
        MASTER_OFF_REPEAT_S, and `_master_off_since` is what the dashboard reports."""
        if not self.a.live: return
        if self.db.get('master',False):
            self._master_off_since=None; self._master_off_said=0.0; return
        now=time.time()
        if getattr(self,'_master_off_since',None) is None:
            self._master_off_since=now; self._master_off_said=0.0; return
        off=now-self._master_off_since
        if off<self.MASTER_OFF_WARN_S: return
        said=getattr(self,'_master_off_said',0.0)
        if said and now-said<self.MASTER_OFF_REPEAT_S: return
        self._master_off_said=now
        wanted=self.db.sql('SELECT count(*) FROM diagnostics WHERE ts>=? AND detail LIKE ?',
                           (self._master_off_since,'%"fire": true%'))[0][0]
        self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(now,0,json.dumps(dict(
            kind='MASTER_OFF',off_s=round(off,1),fires_gated=wanted,acted=False))))
        print('[master off] %.0f min, engine live and healthy, %d fires gated - nothing is trading'
              %(off/60.0,wanted),flush=True)
    FLOOR_CONFIRMATIONS=6
    FLOOR_MIN_SPAN_S=360.0
    def _floor_check(self):
        """USER ORDER, 09-16 03:2x: "ef off if bankroll goes below 30$ in central 2".

        The only automatic stop in this engine, and it exists because the owner
        asked for it by name. It is deliberately narrow:

        * EQUITY, not cash. The 09-13 mistake this file already documents halted a
          solvent account because `cash` reads ZERO for a position that has graded
          and not yet paid. Equity here is spendable cash plus `venue_state.open_value`,
          the settled-but-unpaid money. If open_value is unknown the check does
          NOTHING - an unreadable number is not evidence of a low balance.
        * PERSISTENCE. A payout can take five minutes, so the floor must hold for
          FLOOR_CONFIRMATIONS reads AND at least FLOOR_MIN_SPAN_S seconds - longer
          than one full settlement cycle - before it acts. Any read above the floor
          resets both counters.
        * IT TURNS OFF EF, NOTHING ELSE. `master` stays as the operator set it, the
          other lanes are untouched, no halt is written, and it never re-enables
          itself: coming back is the owner's decision, through the dashboard.
        * It is OFF unless `ef_cash_floor` is set in meta. No floor, no behaviour.
        """
        if not self.a.live or self.cash is None: return
        floor=self.db.get('ef_cash_floor')
        if floor is None: return
        try: floor=float(floor)
        except (TypeError,ValueError): return
        if not (floor>0): return
        if not self.db.get('ef_enabled',True):
            self._floor_reads=0; self._floor_since=None; return
        r=self.db.sql('SELECT open_value FROM venue_state ORDER BY ts DESC LIMIT 1')
        opened=float(r[0][0]) if r and r[0][0] is not None else None
        if opened is None: return                      # unknown != low; act on nothing
        equity=self.cash-self.db.live_reserve()+opened
        now=time.time()
        if equity>=floor:
            self._floor_reads=0; self._floor_since=None; return
        self._floor_reads=getattr(self,'_floor_reads',0)+1
        if getattr(self,'_floor_since',None) is None: self._floor_since=now
        if self._floor_reads<self.FLOOR_CONFIRMATIONS or now-self._floor_since<self.FLOOR_MIN_SPAN_S: return
        self.db.set('ef_enabled',False)                # audited write; master untouched
        self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(now,0,json.dumps(dict(
            kind='EF_FLOOR',floor=floor,equity=round(equity,4),cash=round(self.cash,4),
            open_value=round(opened,4),reads=self._floor_reads,
            held_s=round(now-self._floor_since,1),acted=True))))
        print('[ef floor] equity %.2f below %.2f on %d reads over %.0f s - EF DISABLED'
              ' (master untouched; re-enable from the dashboard)'
              %(equity,floor,self._floor_reads,now-self._floor_since),flush=True)
        self._floor_reads=0; self._floor_since=None
    WIPEOUT_CONFIRMATIONS=3
    def _wipeout_check(self):
        """MONITOR ONLY. Records a low-balance reading and stops nothing.

        User, 09-13 19:1x: "what i said was it should be trading when no money
        available and that was for you, to monitor not to add the code in file".
        Their earlier "master off when account run out of money for stack" was a
        job for whoever is watching, and compiling it into the engine was my
        over-implementation. It halted a solvent account at 18:41:10. This is the
        correction: observe, write it down, act never.

        Why it was wrong is kept here rather than deleted, because the quantity
        it watched is the wrong quantity. `self.cash` is CASH, and a position
        that has graded but not yet paid reads as ZERO in it. At 18:41:10 cash
        was 2.065 with 4.38 of position still settling; five and a half minutes
        later cash was 11.90, the rise being exactly one payout to the cent.
        Three confirmations cover an ORDER in flight, which is seconds - a
        POSITION takes up to five minutes, so it could never have waited enough.

        And it was never protecting the balance. The engine cannot spend money it
        does not have: the venue rejects an order it cannot fund. What it
        prevented was a run of failed submissions - noise, not loss.

        It sets no halt, clears no flag and turns nothing off. `master` and the
        lane flags are the operator's alone.
        """
        if not self.a.live or self.cash is None: return
        stake=float(self.db.get('next_stake',1.) or 1.)
        spendable=self.cash-self.db.live_reserve()
        if spendable+1e-9>=stake:
            self._wipeout_seen=0; return
        self._wipeout_seen=getattr(self,'_wipeout_seen',0)+1
        # Once per episode, at the confirmation threshold - not every 5 s for as
        # long as the balance stays low. The counter resets on recovery, so a
        # genuinely new episode records again.
        if self._wipeout_seen!=self.WIPEOUT_CONFIRMATIONS: return
        # open_value is the settled-but-unpaid money the old rule could not see.
        # Recording spendable without it would repeat the mistake being corrected.
        r=self.db.sql('SELECT open_value FROM venue_state ORDER BY ts DESC LIMIT 1')
        opened=float(r[0][0]) if r and r[0][0] is not None else None
        self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),0,json.dumps(dict(
            kind='LOW_BALANCE',spendable=round(spendable,4),stake=stake,open_value=opened,
            equity=(round(spendable+opened,4) if opened is not None else None),
            reads=self._wipeout_seen,acted=False))))
        print('[low balance] spendable %.2f below stake %.2f on %d reads; open %s'
              ' - MONITOR ONLY, nothing stopped'
              %(spendable,stake,self._wipeout_seen,
                'n/a' if opened is None else '%.2f'%opened),flush=True)
    # 12.8.10. AWS Task 86: 34.7% of decide rows were "Waiting for fresh UP and
    # DOWN books" and the journal could not say which token blocked or how old
    # it was; the process-wide quote_block counters are not keyed by token, and
    # ws_gap_probe's number turned out to measure the NEXT candle's illiquid
    # book, not the traded one (Zurich Z-1). This counts, per publish() refusal,
    # side x reason x age bucket, and housekeeping writes one WAIT_CENSUS row a
    # minute. Observation only; the rule itself is unchanged.
    WAIT_BUCKETS=((0.75,'<0.75'),(1.0,'0.75-1'),(2.0,'1-2'),(5.0,'2-5'),(float('inf'),'5+'))
    def _count_wait(self,toks,quotes):
        try:
            c=self._wait_census
            if len(toks)!=2: c['no_market']=c.get('no_market',0)+1; return
            for side,tok,q in zip(('UP','DOWN'),toks,quotes):
                if q is not None: continue
                reason,age=self.books.block_detail.get(tok,('unknown',None))
                b='n/a' if age is None else next(lab for lim,lab in self.WAIT_BUCKETS if age<lim)
                k=f'{side}:{reason}:{b}'; c[k]=c.get(k,0)+1
        except Exception: pass
    def _flush_wait_census(self,ep):
        try:
            if time.monotonic()-self._wait_flushed<60 or not self._wait_census: return
            row=dict(kind='WAIT_CENSUS',window_s=round(time.monotonic()-self._wait_flushed,1),**self._wait_census)
            self._wait_census={}; self._wait_flushed=time.monotonic()
            self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(row)))
        except Exception: pass
    def _sample_ambient_age(self,ep):
        """Log the book's age for both tokens, unfiltered, once per housekeeping tick.

        Task 73 measured that rejected orders sit on a book twice as old as
        filled ones at submit (174.8 vs 86.6 ms, p~0.0003). Task 75 asked
        whether that is the feed being slow or the submit gate at
        poly_core.py:928 selecting quiet books - and it could not be answered,
        because `age_ms` was only ever persisted on the submit path, which the
        gate has already filtered. Nothing on the box recorded the AMBIENT age.

        This does. It reads the raw arrival stamp, not `quote()`, so the 2 s
        staleness filter cannot hide the tail. Submits older than ambient means
        the gate selects; matching ambient means the feed. Instrumentation only,
        same shape as 12.8.1; it commits to nothing and cannot raise.
        """
        try:
            toks=self.market.get(ep)
            if not toks: return
            now=time.monotonic(); row={}
            for side,token in (('up',toks[0]),('dn',toks[1])):
                b=self.books.books.get(token)
                row['age_%s_ms'%side]=(round((now-b['arrival'])*1000,1) if b and b.get('arrival') else None)
            self.db.sql('INSERT INTO diagnostics VALUES(?,?,?)',(time.time(),ep,json.dumps(dict(kind='AMBIENT_AGE',**row))))
        except Exception: pass
    def _main_oneshot_check(self):
        """MAIN disarms itself after ONE filled order.

        User, 09-13: "main off after 1 filled order, whatever happens, win or
        lose i don't care". So the trigger is the FILL, not the outcome - it
        fires without waiting for the candle to grade.

        "One" counts from the moment MAIN was armed, taken from the control-write
        audit trail, not from all time. MAIN already has one historical fill from
        the 09-12 seeding bug; counting that would disarm the lane before the
        operator's test ever ran.

        In code rather than in an operator poll, because a poll can miss the
        window and let a second order through, and the instruction is
        unconditional.
        """
        # 12.13.1: LIVE ONLY. The instruction it implements was about live money
        # ("main off after 1 filled order, whatever happens"), and on a paper
        # engine it ends the experiment at the first fill - which also kills
        # REVERSAL, since REVERSAL is a hedge on an open MAIN and cannot fire
        # without one. Paper lanes therefore keep MAIN armed; live is unchanged.
        if not self.a.live: return
        if not self.db.get('main_enabled'): return
        armed=None
        for r in self.db.sql("SELECT ts,detail FROM diagnostics WHERE detail LIKE "
                             "'%control_write%' AND detail LIKE '%main_enabled%' ORDER BY ts DESC"):
            try: d=json.loads(r['detail'])
            except (ValueError,TypeError): continue
            if d.get('key')=='main_enabled' and d.get('new') is True: armed=r['ts']; break
        if armed is None: return          # armed before auditing existed; do not guess
        n=self.db.sql("SELECT count(*) FROM orders WHERE kind='MAIN' AND status='FILLED' AND ts>?",
                      (armed,))[0][0]
        if not n: return
        self.db.set('main_enabled',False)
        print(f'[MAIN ONE-SHOT] {n} filled MAIN order(s) since arming - main_enabled OFF',flush=True)
    async def reconcile_loop(self):
        while True:
            await self.executor.reconcile()
            if self._due('main_oneshot',self.MONITOR_EVERY_S):
                try: self._main_oneshot_check()
                except Exception as e: self.error='main one-shot: '+type(e).__name__
            await asyncio.sleep(1)
    async def grade_loop(self):
        while True:
            rows=self.db.sql('SELECT DISTINCT epoch FROM fills WHERE epoch<? AND epoch NOT IN (SELECT epoch FROM results)',(time.time()-390,))
            for row in rows:
                ep=row[0]; data=await asyncio.to_thread(http_json,GAMMA.format(ep))
                if not data: continue
                ms=[m for e in data for m in e.get('markets',[]) if m.get('slug')==f'btc-updown-5m-{ep}']
                result=official_result(ms[0]) if len(ms)==1 else None
                if result: self.db.grade(ep,result); self.revision+=1
            self.db.halt_check(every_s=self.db.HALT_CHECK_EVERY_S); await asyncio.sleep(20)
    async def claim_loop(self):
        while True:
            if self.a.live:
                for old in self.db.sql("SELECT epoch,claim_id FROM results WHERE claim_status IN ('REVIEW','SUBMITTING') AND claim_id IS NOT NULL"):
                    try:
                        state=await asyncio.wait_for(self.broker.claim_state(old['claim_id']),8)
                        if state=='STATE_CONFIRMED': self.db.sql("UPDATE results SET claim_status='CONFIRMED' WHERE epoch=?",(old['epoch'],))
                        elif state in ('STATE_FAILED','STATE_INVALID'): self.db.sql("UPDATE results SET claim_status='PENDING',claim_id=NULL WHERE epoch=?",(old['epoch'],))
                    except Exception: pass
            # NO REVIEW -> PENDING SWEEP. 12.4.2 added one and 12.4.3 moved it
            # into the handler; both are removed. The user's account has
            # AUTO-REDEEM enabled, so the venue claims each winning position
            # itself and our redeem() call then raises "already redeemed".
            # Retrying that is an unbounded loop of doomed redemption calls
            # against a live account, every cycle, forever. The row is not a
            # failure to retry - it is a success we mislabelled.
            # GROUP BY epoch: results JOIN signals yields one row per LANE, so a
            # multi-lane candle redeemed the same condition_id twice. The second
            # call fails (already redeemed) and its handler wrote REVIEW over the
            # CONFIRMED the first one earned.
            for row in self.db.sql("SELECT r.*,min(s.condition_id) AS condition_id FROM results r "
                                   "JOIN signals s USING(epoch) WHERE claim_status='PENDING' GROUP BY r.epoch"):
                # status can change under us across an await; re-read before acting
                cur=self.db.sql('SELECT claim_status FROM results WHERE epoch=?',(row['epoch'],))
                if not cur or cur[0][0]!='PENDING': continue
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
                except Exception:
                    # Ask the venue what actually happened rather than assuming
                    # our call was the only one. With auto-redeem on, the venue
                    # has usually already claimed the position and redeem()
                    # raises "already redeemed" - which is a SUCCESS, and was
                    # being recorded as a failure. Six of ten winners landed in
                    # REVIEW that way and showed as a permanent pending payout
                    # that could never clear.
                    v=self.db.sql('SELECT venue_value,venue_ts FROM results WHERE epoch=?',(row['epoch'],))
                    collected=bool(v) and v[0][1] is not None and (v[0][0] or 0)<=1e-9
                    self.db.sql("UPDATE results SET claim_status=? WHERE epoch=?",
                                ('AUTO_REDEEMED' if collected else 'REVIEW',row['epoch']))
            await asyncio.sleep(20)
    EV_MODES=('regime','fixed','accuracy')
    def ev_setting(self):
        """Current EV mode and the threshold it implies.

        Returns (mode, ev_threshold) where ev_threshold is None for 'regime',
        so the model falls back to its own per-volatility table, and None for
        'accuracy', where the confidence and EV floors govern instead.
        """
        cfg=self.db.get('ev_settings') or {}
        mode=cfg.get('mode')
        if mode not in self.EV_MODES:
            # First run: honour the launch flag if one was given.
            mode='fixed' if getattr(self.a,'ev',None) is not None else 'regime'
        if mode=='fixed':
            v=cfg.get('value',getattr(self.a,'ev',None))
            try: v=float(v)
            except (TypeError,ValueError): v=None
            if v is None or not math.isfinite(v): return 'regime',None
            return 'fixed',v
        return mode,None
    def _sync_executor_dials(self):
        """Push meta's execution dials onto the executor. meta is the only source.

        `pad` was refreshed here every pass. `band` and `age` were NOT: they were
        set once in Executor.__init__ and thereafter only by the
        /api/controls/ev HTTP handler. So band mode set through the panel held
        until the next restart and then silently reverted to tick caps with meta
        still reading "band" - and worse, decide_now()'s EV gate reads
        slippage_mode() fresh every pass, so the gate ran in band mode while the
        plan that actually got signed did not. Three live orders were signed at
        exactly one tick under meta slippage_mode=band before this was caught.
        Same failure class as master defaulting off, except master is loud and
        re-armed on every deploy and this was silent.
        """
        self.executor.pad=self.pad_ticks()
        self.executor.band=(self.slippage_mode()=='band')
        self.executor.age=self.quote_age_s()
    def quote_age_s(self):
        """Max book age we will price against. Live control, CLI flag seeds it."""
        v=(self.db.get('ev_settings') or {}).get('quote_age_ms')
        try: v=float(v)
        except (TypeError,ValueError): v=float(self.a.quote_age_ms)
        return max(0.001,min(2.0,v/1000))
    def slippage_mode(self):
        """'ticks' (flat 0-5 dial) or 'band' (build 36's proportional policy)."""
        m=(self.db.get('ev_settings') or {}).get('slippage_mode','ticks')
        return m if m in ('ticks','band') else 'ticks'
    def pad_ticks(self):
        cfg=self.db.get('ev_settings') or {}
        v=cfg.get('pad_ticks',getattr(self.a,'pad_ticks',1))
        try: v=int(v)
        except (TypeError,ValueError): v=int(getattr(self.a,'pad_ticks',1))
        return max(0,min(5,v))
    async def venue_truth_loop(self):
        """Pull the venue's own money numbers and attach them to settled rows.

        This is what makes the reported PnL, win/loss and available funds
        Polymarket's figures rather than ours. Paper mode has no venue account,
        so it keeps the local basis and says so."""
        while True:
            if self.a.live and self.broker is not None and getattr(self.broker,'client',None) is not None:
                try:
                    # Ask for the markets that still need pricing as well as the
                    # open ones, so a settled candle is not left on the local figure.
                    need=self.db.conditions_awaiting_venue()
                    truth=await asyncio.wait_for(self.broker.venue_truth(condition_ids=need or None),25)
                    self.venue_state=truth
                    self.cash=truth.get('cash'); self.cash_at=time.monotonic()
                    self.db.venue_snapshot(truth)
                    self.db.apply_venue_pnl(truth.get('positions'))
                    # Cross-check the local reserve against the venue's open
                    # orders so a dead local row cannot keep holding funds back.
                    self.db.mark_venue_open(truth.get('open_order_ids'))
                    self.revision+=1
                except Exception as e:
                    self.error=f'venue truth: {type(e).__name__}'
            await asyncio.sleep(20)
    async def _stream(self,name,handler):
        def wrapped(j):
            handler(j)
            key=name if name in self.age else None
            if key: self.age[key]=time.time()
            self.msgs[name]=self.msgs.get(name,0)+1
        await poly_feeds.run_stream(name,wrapped,self.health)
    async def _ref_stream(self):
        # 12.11.0: the settlement reference as a first-class stream. Its own url list and a
        # subscribe frame; health/arrival accounting exactly like the Binance streams. If the
        # endpoint is down the features fall back to the Binance proxy (ref_src=0) - decisions
        # never depend on this stream unless the model json says open_reference="twap60".
        def wrapped(j):
            self.on_ref(j); self.msgs['ref']=self.msgs.get('ref',0)+1
        await poly_feeds.run_stream('ref',wrapped,self.health,event_key=(),urls=poly_feeds.REF_WS,subscribe=poly_feeds.REF_SUBSCRIBE)
    async def chart_seed(self):
        # api.binance.com answers HTTP 451 from several hosting regions, which left
        # the chart empty with no error. poly_feeds tries each REST mirror in turn.
        data,host=await asyncio.to_thread(poly_feeds.rest_json,'/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=288')
        if not isinstance(data,list): print(f'[chart] seed failed: {host}',flush=True)
        if isinstance(data,list):
            for k in data:
                if k[0]/1000+300<time.time(): self.db.sql('INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?)',(int(k[0])//1000,*map(float,k[1:6])))
            self.revision+=1
    async def main(self):
        if self.a.live:
            check=await asyncio.to_thread(http_json,'https://polymarket.com/api/geoblock')
            if not isinstance(check,dict) or check.get('blocked') is not False: raise SystemExit('Venue geographic eligibility check did not pass')
            await self.broker.open()
            # Venue-first startup reconciliation: do not trust stale SQLite reservations.
            # Two passes let a prior UNKNOWN prove itself absent before the dashboard opens.
            for _ in range(2):
                await self.executor.reconcile()
                await asyncio.sleep(.35)
            try:
                snap=await asyncio.wait_for(self.broker.account_snapshot(),8)
                self.account_snapshot=snap; self.account_positions=list(snap.get('positions') or [])
                self.cash=float(snap['cash']); self.cash_at=time.monotonic()
            except Exception as e:
                self.error='Startup account verification: '+type(e).__name__+': '+str(e)
        server=self.ui.make_server(); threading.Thread(target=server.serve_forever,daemon=True).start()
        print('Polymarket v12.1', 'LIVE (master OFF)' if self.a.live else 'PAPER',f'http://{self.a.host}:{self.a.port}',flush=True)
        try:
            await asyncio.gather(self.chart_seed(),self._stream('spot',self.on_spot),self._stream('perp',self.on_perp),self._stream('depth',self.on_depth),self._stream('chart',self.on_kline),self._ref_stream(),self.venue(),self.decide_loop(),self.housekeeping(),self.reconcile_loop(),self.grade_loop(),self.claim_loop(),self.venue_truth_loop())
        finally:
            server.shutdown(); server.server_close()
            if self.a.live: await self.broker.close()
            self.db.c.close(); self.process_lock.close()

def args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true'); p.add_argument('--port',type=int,default=8787); p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--model',default=str(pathlib.Path(__file__).with_name('model_v10.json')))
    p.add_argument('--db',default='polymarket_v12_paper.sqlite3'); p.add_argument('--capital',type=float,default=50)
    # --mode is vestigial (audit_deadcode 3c): PolyRunner never reads a.mode; EV
    # mode is the ev_settings meta control. Still accepted, hidden, so the
    # existing launch lines (start_paper.sh, DEPLOY_MUMBAI.md) keep working.
    p.add_argument('--mode',choices=['pnl'],default='pnl',help=argparse.SUPPRESS); p.add_argument('--ev',type=float,default=None)
    p.add_argument('--quote-age-ms',type=float,default=750); p.add_argument('--pad-ticks',type=int,default=1)
    # Execution budget. Raise these for a host far from the venue; the dashboard
    # latency block reports the measured split so the value can be set from data.
    p.add_argument('--execution-budget-ms',type=float,default=2000)
    p.add_argument('--post-timeout-ms',type=float,default=1200)
    p.add_argument('--max-attempts',type=int,default=4)   # build 36 parity:
    # PREDICT_ORDER_MAX_RETRIES=3 is used as `range(1, ...+2)`, i.e. one
    # submit plus three retries = FOUR attempts. v12 shipped 3 and so was a
    # whole attempt short of the rule it was ported from.
    a=p.parse_args()
    if not math.isfinite(a.capital) or a.capital<=0 or not 0<a.quote_age_ms<=2000 or a.pad_ticks<0: p.error('invalid capital/quote age/pad')
    if a.ev is not None and not math.isfinite(a.ev): p.error('invalid EV')
    if not 300<=a.execution_budget_ms<=240000: p.error('execution budget must be 300ms..240s')
    if not 100<=a.post_timeout_ms<=a.execution_budget_ms: p.error('post timeout must be 100ms..budget')
    if not 1<=a.max_attempts<=10: p.error('max attempts must be 1..10')
    if not pathlib.Path(a.model).is_file(): p.error('model_v10.json required')
    return a
if __name__=='__main__':
    try: asyncio.run(PolyRunner(args()).main())
    except KeyboardInterrupt: print('Stopped; saved database retained')
