"""Original dashboard HTML, served with the Polymarket lane's data and controls."""
import base64, csv, datetime as dt, hmac, io, json, math, os, pathlib, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
from zoneinfo import ZoneInfo
from btc_model_v10 import FEATURES
ROOT=pathlib.Path(__file__).parent
LONDON=ZoneInfo('Europe/London')
DEFAULT_STAKE=dict(mode='ladder',fixed_stake=1.,percent=10.,current_stake=1.,win_trigger=3,loss_trigger=2,min_stake=1.,max_stake=50.)

def _json_safe(obj):
    """Replace non-finite floats with null so one bad number cannot fail the
    whole response. json.dumps(allow_nan=False) raises on NaN and Infinity, and
    NaN is not valid JSON for the browser either, so neither emitting nor
    raising is acceptable - the value is dropped and the rest survives."""
    if isinstance(obj,float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj,dict):
        return {k:_json_safe(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj,set):
        return sorted(str(v) for v in obj)
    if isinstance(obj,(dt.datetime,dt.date,dt.time)):
        return obj.isoformat()
    if isinstance(obj,(bytes,bytearray)):
        return obj.decode('utf-8','replace')
    if isinstance(obj,(str,int,bool)) or obj is None:
        return obj
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        # A value the encoder cannot take must not cost the whole response.
        # The live box lost its dashboard to exactly one of these: the SDK's
        # account-PnL point carries a datetime.
        return str(obj)


class Dashboard:
    def __init__(self,r):
        self.r=r; self.db=r.db; self.cache=None; self.cache_at=0
        self.password=os.environ.get('DASHBOARD_PASSWORD','')
        if r.a.host not in ('127.0.0.1','localhost','::1') and len(self.password)<12:
            raise ValueError('Set DASHBOARD_PASSWORD (12+ characters) before exposing the dashboard')
        # MAIN and REVERSAL seed OFF. This loop PERSISTS what it writes, so a
        # True here is not a soft default that a later check can override - it
        # becomes a stored flag that reads as deliberately enabled. Seeding all
        # three True meant that switching master on armed every lane at once,
        # which put a live MAIN order on the book on 09-12 16:51 on a lane that
        # has never been validated with money. EF is the lane that is run, so it
        # keeps its True; the other two are opt-in from Trade Controls.
        for k,v in [('master',not r.a.live),('main_enabled',False),('reversal_enabled',False),('ef_enabled',True),('stake_settings',DEFAULT_STAKE),('rules',[]),('sx_enabled',False),('tp',0),('sl',0)]:
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
    def banned(self,kind='EF'):
        now=dt.datetime.now(LONDON); day=now.weekday(); minute=now.hour*60+now.minute
        for rule in self.db.get('rules',[]):
            if kind not in rule['kinds']: continue
            a,b=rule['start_minute'],rule['end_minute']; days=rule['days']
            if a==b and day in days: return True
            if a<b and day in days and a<=minute<b: return True
            if a>b and ((day in days and minute>=a) or ((day-1)%7 in days and minute<b)): return True
        return False
    def allowed(self,kind='EF'):
        key={'MAIN':'main_enabled','REVERSAL':'reversal_enabled','EF':'ef_enabled'}.get(kind,'ef_enabled')
        return self.db.get('master',False) and self.db.get(key,True) and not self.db.get('halt') and not self.daily()['halted'] and not self.banned(kind) and not (self.db.get('sx_enabled') and time.time()<self.db.get('sx_until',0))
    def feed_state(self):
        """Both feed numbers, plus which streams are unusable and why.

        arrival_age_s says the socket is alive; event_lag_s says the data is
        current. A feed can pass one and fail the other, so the dashboard shows
        both rather than a single LIVE badge."""
        r=self.r; h=getattr(r,'health',None)
        if h is None:
            age=time.time()-r.age['spot'] if r.age.get('spot') else None
            return dict(status='LIVE' if age is not None and age<2 else 'CONNECTING',
                        last_event_age_ms=int(1000*age) if age is not None else None)
        snap=h.snapshot(('spot','perp','depth','venue'))
        bad=h.stale(('spot','perp','depth'))
        spot_age=h.arrival_age('spot')
        snap.update(status=('LIVE' if not bad else 'STALE'),unusable=bad,
                    last_event_age_ms=int(1000*spot_age) if spot_age is not None else None,
                    book=self.r.books.health() if hasattr(self.r.books,'health') else {})
        return snap
    def equity(self):
        # Live sizing is driven by what Polymarket says the account is worth:
        # collateral balance plus the venue's own valuation of open positions.
        # The local journal is never the bankroll source in live mode.
        if not self.r.a.live: return self.r.a.capital+self.db.metrics()['pnl']
        vt=getattr(self.r,'venue_state',None) or {}
        if vt.get('cash') is not None:
            return float(vt['cash'])+float(vt.get('open_value') or 0.)
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
    def ev_controls(self):
        """EV mode and slippage allowance, as live settings.

        slippage_ticks is the number of ticks added to the ask before the order
        is capped. It is the fill-versus-frequency dial: measured on 206 real
        fires, 0 ticks lets every signal through the EV re-check, 1 tick lets 57%
        through and 2 ticks 37%, because one tick is a median 2.1% of the ask
        while the EV bar is 0.15 to 0.25. Padding buys fill probability and costs
        signals, and the number here decides the trade.
        """
        cfg=self.db.get('ev_settings') or {}
        mode,value=self.r.ev_setting() if hasattr(self.r,'ev_setting') else ('regime',None)
        pad=self.r.pad_ticks() if hasattr(self.r,'pad_ticks') else cfg.get('pad_ticks',1)
        regime=(self.r.m.regime or {}) if hasattr(self.r,'m') else {}
        return dict(
            mode=mode,modes=list(getattr(self.r,'EV_MODES',('regime','fixed','accuracy'))),
            value=value,slippage_ticks=pad,tick_size=0.01,
            regime_thresholds=(regime.get('thresholds') or {}),
            regime_edges=(regime.get('rv60_edges') or []),
            measured=dict(survive_pct={0:100,1:57,2:37},sample=206,
                          note='share of signals that clear the EV re-check at each pad'),
            describe={'regime':'model thresholds per volatility regime',
                      'fixed':'one EV threshold on every candle',
                      'accuracy':'confidence and EV floors instead of an EV threshold'}.get(mode,''))
    def lane_card(self,kind):
        """Build 36's MAIN/REVERSAL card: the call, plus what became of the order.

        The direction line shows the signal, as it did in build 36 where a
        prediction existed whether or not it executed. The reason line carries the
        execution outcome, so nothing on the panel implies a position that was
        never taken."""
        L=self.r.lane_decision or {}
        if kind=='MAIN':
            sig=L.get('main_signal') or L.get('main'); placed=L.get('main_placed')
            attempts=L.get('main_attempts') or 0; why=L.get('main_last_reason') or ''
        else:
            sig=L.get('reversal_signal'); placed=L.get('reversal_placed')
            attempts=L.get('reversal_attempts') or 0; why=''
        if not sig or not sig.get('direction'): return None
        if placed:
            reason='order placed'
        elif attempts:
            reason=f'called, not executed ({attempts} attempt{"s" if attempts>1 else ""})'+(f' · {why}' if why else '')
        else:
            reason='called, submitting'
        return dict(direction=sig.get('direction'),ts_ms=sig.get('ts_ms'),
                    probability_up=sig.get('probability_up',0.5),reason=reason,placed=bool(placed))
    def pnl_by_kind(self):
        """Settled PnL split by lane. MAIN and REVERSAL can hold opposite sides
        of one candle, so a single blended number would hide the hedge."""
        rows=self.db.sql('''SELECT coalesce(o.kind,'EF') kind,
                            coalesce(sum(CASE WHEN s.side=r.actual THEN f.shares ELSE 0 END),0)
                            - coalesce(sum(f.spent+f.fees),0) pnl
                            FROM results r JOIN signals s USING(epoch)
                            JOIN orders o ON o.epoch=s.epoch AND coalesce(o.kind,'EF')=s.kind
                            JOIN fills f ON f.order_id=o.id GROUP BY coalesce(o.kind,'EF')''')
        out={r['kind']:r['pnl'] for r in rows}
        for k in ('EF','MAIN','REVERSAL'): out.setdefault(k,0.0)
        return out
    def note_error(self,endpoint,exc):
        """Record and print a dashboard failure so it is diagnosable.

        A blank dashboard with no reason costs more time than the fault itself.
        The last few are kept in memory and surfaced in /api/state."""
        import traceback
        entry=dict(ts=time.time(),endpoint=endpoint,error=f'{type(exc).__name__}: {exc}')
        self.errors=(getattr(self,'errors',[])+[entry])[-10:]
        print(f'[dashboard] {endpoint} failed: {entry["error"]}',flush=True)
        traceback.print_exc()
    def controls(self):
        now=dt.datetime.now(LONDON); ready=self.r.cash is not None and time.monotonic()-self.r.cash_at<15
        w,l=self.db.get('streak',[0,0])
        kinds={}
        for k,key in [('MAIN','main_enabled'),('REVERSAL','reversal_enabled'),('EF','ef_enabled')]:
            # All three lanes now have a signal source. EF is the v10 model on the
            # Polymarket book; MAIN and REVERSAL are the Build 11 pressure engine
            # ported in poly_lanes. Neither MAIN nor REVERSAL has a meaningful
            # live record yet, which the status text says rather than hiding.
            status={'EF':'v10 PnL live lane',
                    'MAIN':'Build 11 pressure lane (ported; no live record yet)',
                    'REVERSAL':'Build 11 hedge lane (ported; 53 live fills on Predict.fun)'}[k]
            kinds[k]=dict(manual_enabled=self.db.get(key,True),effective_enabled=self.allowed(k),
                          source_available=True,status=status)
        return dict(master_enabled=self.db.get('master'),clock=now.strftime('%H:%M:%S'),timezone='Europe/London',
          execution=dict(ready=ready,missing=[] if ready else ['waiting for feed / balance readiness']),
          kinds=kinds,
          state_x=dict(enabled=self.db.get('sx_enabled'),active=self.db.get('sx_enabled') and time.time()<self.db.get('sx_until',0),loss_streak=self.db.get('sx_losses',0),resume_time=dt.datetime.fromtimestamp(self.db.get('sx_until',0),LONDON).strftime('%H:%M'),trigger_reason='2 consecutive settled losses'),
          ev=self.ev_controls(),
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
                kind=p.get('kind')
                if kind not in ('MAIN','REVERSAL','EF'): raise ValueError('Invalid signal kind')
                if not isinstance(p.get('manual_enabled'),bool): raise ValueError('Invalid signal toggle')
                self.db.set({'MAIN':'main_enabled','REVERSAL':'reversal_enabled','EF':'ef_enabled'}[kind],p['manual_enabled'])
            elif path=='/api/controls/ev':
                # Changes what the engine will pay and how often it fires, so it
                # is confirmed like every other trading control and bounded here.
                modes=list(getattr(self.r,'EV_MODES',('regime','fixed','accuracy')))
                cfg=dict(self.db.get('ev_settings') or {})
                if 'mode' in p:
                    if p['mode'] not in modes: raise ValueError('mode must be one of '+', '.join(modes))
                    cfg['mode']=p['mode']
                if 'value' in p and p['value'] is not None:
                    v=float(p['value'])
                    if not (0<=v<=5) or not math.isfinite(v): raise ValueError('EV threshold must be 0..5')
                    cfg['value']=v
                if 'slippage_ticks' in p:
                    t=int(p['slippage_ticks'])
                    if not 0<=t<=5: raise ValueError('slippage must be 0..5 ticks')
                    cfg['pad_ticks']=t
                if cfg.get('mode')=='fixed' and cfg.get('value') is None:
                    raise ValueError('fixed mode needs a value')
                self.db.set('ev_settings',cfg)
                if hasattr(self.r,'executor') and 'pad_ticks' in cfg: self.r.executor.pad=int(cfg['pad_ticks'])
                return dict(ok=True,ev=self.ev_controls())
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
            timing=json.loads(r['timing_json'] or '{}') if 'timing_json' in r.keys() else {}
            err=json.loads(r['error_json'] or 'null') if 'error_json' in r.keys() else None
            out.append(dict(utc=dt.datetime.fromtimestamp(r['ts'],LONDON).isoformat(),candle_id=r['epoch']*1000,seconds_into_candle=d.get('sec'),direction=r['side'],kind='EF',ef_attempt_seq=r['attempt'],signal_price=d.get('signal_price'),quoted_price=p.get('signal_quote',p['quote']),pre_submit_quote=p.get('pre_submit_quote',p['quote']),price_cap=p.get('cap'),fill_price=price,shares=r['shares'],delay_ms=timing.get('total_attempt_ms',r['latency']),last_attempt_ms=r['latency'],book_age_ms=p['age_ms'],fee_collateral=r['fees'],market_id=r['condition_id'],order_id=r['id'],status=r['status'],filled=bool(r['shares']),failure_reason=r['reason'],error=err,timing=timing,request_reached=(err.get('request_reached') if isinstance(err,dict) and 'request_reached' in err else (bool(r['request_reached']) if 'request_reached' in r.keys() else None)),stake=(r['spent'] or 0)+(r['fees'] or 0) if r['shares'] else p['budget'],pnl=r['pnl'],correct=r['pnl']>0 if r['pnl'] is not None else None,financial_is_shadow=not self.r.a.live,quote_to_fill=(price-p.get('signal_quote',p['quote'])) if price is not None else None,ask_to_fill=(price-p.get('pre_submit_quote',p['quote'])) if price is not None else None,cap_to_fill=((p.get('cap')-price) if (price is not None and p.get('cap') is not None) else None)))
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
        submissions=self.db.sql('SELECT count(*) FROM orders WHERE ts>=?',(cutoff,))[0][0]
        rejected=self.db.sql("SELECT count(*) FROM orders WHERE ts>=? AND status='REJECTED'",(cutoff,))[0][0]
        unknown=self.db.sql("SELECT count(*) FROM orders WHERE ts>=? AND status='UNKNOWN'",(cutoff,))[0][0]
        confirmed=self.db.sql('SELECT count(distinct f.epoch) FROM fills f JOIN orders o ON f.order_id=o.id WHERE o.ts>=?',(cutoff,))[0][0]
        terminal_eligible=self.db.sql("SELECT count(distinct epoch) FROM orders WHERE ts>=? AND status IN ('FILLED','NO_FILL','REJECTED')",(cutoff,))[0][0]
        return dict(count=len(rows),pnl=pnl,curve=curve,attempted=attempted,signals_attempted=attempted,order_submissions=submissions,explicit_rejections=rejected,unknowns=unknown,confirmed_fills=confirmed,failed=max(0,terminal_eligible-confirmed),fill_rate=confirmed/terminal_eligible if terminal_eligible else None,return_on_stake=pnl/amount if amount else None,per_100=pnl*100/len(rows) if rows else None,avg_price=spent/shares if shares else None,avg_shares=shares/len(rows) if rows else None,by_kind=self.pnl_by_kind())
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
        vt=getattr(r,'venue_state',None) or {}
        vmetrics=self.db.venue_metrics(); divergence=self.db.pnl_divergence()
        live_venue=bool(r.a.live and vmetrics['n'])
        shown=vmetrics if live_venue else metrics
        metric=dict(accuracy=shown['accuracy'],wins=shown['wins'],losses=shown['losses'],
                    real=shown['n'] if r.a.live else 0,shadow=0 if r.a.live else shown['n'],
                    basis=('VENUE_POSITION_PNL' if live_venue else 'LOCAL_FROM_FILLS'),
                    local_pnl=metrics['pnl'],venue_pnl=vmetrics['pnl'],
                    venue_priced=vmetrics['n'],awaiting_venue=max(0,metrics['n']-vmetrics['n']),
                    divergence=divergence)
        # Available funds: the authenticated Polymarket collateral balance, never a
        # locally reconstructed figure. The unresolved local reserve is reported
        # beside it as concurrency headroom and is not subtracted from it.
        cash=(vt.get('cash') if vt.get('cash') is not None else r.cash) or 0.
        # The reserve is the one number on this panel the venue does not publish,
        # so it is reported by how far it has been verified rather than as a
        # single figure. A phantom row - repeatedly absent from the venue's open
        # orders with no fill - is excluded from what it holds back.
        rd=self.db.reserve_detail(); reserve=rd['effective']
        fills=self.orders('EF',0,1)['rows']; last=fills[0] if fills else None
        if last: last.update(slippage=last.get('quote_to_fill'),attempts=last['ef_attempt_seq'],order_status=last['status'])
        current=dict(r.current_candle)
        if current: current['seconds_left']=max(0,current['time']/1000+300-time.time())
        positions=[dict(kind='v10',direction=x['side'],shares=x['shares'],buy_price=x['spent']/x['shares'],used_usd=x['spent']+x['fees'],pnl_usd=None) for x in self.positions() if x['shares'] and x['actual'] is None]
        venue_positions=list(getattr(r,'account_positions',[]) or [])
        position_value=sum(float(x.get('current_value') or 0) for x in venue_positions if isinstance(x,dict))
        sizing_bankroll=self.equity()
        self.cache=dict(feature_names=FEATURES,open_positions=positions,economics=self.pnl(),model=dict(version=10),learning=dict(status='Fixed v10 weights'),candle=current,feature=d.get('features',{}),feed=self.feed_state(),metrics=dict(main={},reversal={},ef=metric,combined=metric),main=self.lane_card('MAIN'),reversal=self.lane_card('REVERSAL'),lanes=(self.r.lane_decision or {}),main_block=(self.r.lane_decision or {}).get('main_block',''),ef=ef,ef_monitor=dict(status=d.get('reason') or f"v10 pnl · p {d.get('p','--')} · EV {d.get('ev','--')}"),book=book,last_fill=last,controls=ctr,capital=dict(balance=sizing_bankroll,sizing_bankroll=sizing_bankroll,wallet=cash,pending_payout=pending,open_position_value=position_value,free=cash,wallet_free=cash,funding_headroom=max(0,cash-reserve),reserve_detail=rd,fresh=age<15,balance_age_sec=age,realised=metrics['pnl'],reserved=reserve,next_stake=self.db.get('next_stake',1),truth=dict(source='Polymarket API (balance, positions, open orders, account PnL)',venue_positions=venue_positions,
                        reserve_confirmed=rd['confirmed'],reserve_unverified=rd['unverified'],
                        reserve_phantom=rd['phantom'],reserve_total_local=rd['total'],
                        reserve_phantom_ids=rd['phantom_ids'],
                        portfolio_value=vt.get('portfolio_value'),open_value=vt.get('open_value'),
                        venue_realized_pnl=vt.get('realized_pnl'),venue_unrealized_pnl=vt.get('unrealized_pnl'),
                        venue_fees_paid=vt.get('fees_paid'),account_pnl=vt.get('account_pnl'),
                        venue_age_sec=(time.time()-vt['ts']) if vt.get('ts') else None,
                        pnl_basis=('VENUE_POSITION_PNL' if live_venue else 'LOCAL_FROM_FILLS'),
                        local_vs_venue=divergence)),trades=self.pnl(),latency=r.executor.latency_stats(),chart_revision=r.revision,error=r.error,dashboard_errors=list(getattr(self,'errors',[])),lane='LIVE' if r.a.live else 'PAPER',model_hash=r.hash,fee_basis=r.broker.basis,halt=self.db.get('halt'))
        self.cache_at=time.monotonic(); return self.cache
    def page(self,name):
        text=(ROOT/name).read_text().replace('__VERSION__','12 Polymarket').replace('__BUILD__','12.3.4 · v10 PnL · '+('LIVE' if self.r.a.live else 'PAPER')).replace('__UPTIME_SEC__',str(time.time()-self.r.started))
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
                if not isinstance(body,bytes):
                    body=json.dumps(_json_safe(body),allow_nan=False).encode() if ctype=='application/json' else body.encode()
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
                except (ValueError,TypeError) as e:
                    ui.note_error(p.path,e); self.send({'ok':False,'error':str(e),'endpoint':p.path},status=400)
                except Exception as e:
                    # Anything not caught above used to escape to the base handler,
                    # which replies with an HTML traceback. The page cannot parse
                    # that, so a single unexpected exception blanked the whole
                    # dashboard with "dashboard API error" and no way to see why.
                    # Always answer with JSON, and put the reason in the log.
                    ui.note_error(p.path,e)
                    self.send({'ok':False,'error':f'{type(e).__name__}: {e}','endpoint':p.path},status=500)
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
