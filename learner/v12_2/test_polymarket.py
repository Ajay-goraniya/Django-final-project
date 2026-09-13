import asyncio, contextlib, hashlib, io, json, pathlib, tempfile, time, unittest
from types import SimpleNamespace
from unittest.mock import patch
from poly_core import BookCache, Journal, Executor, PaperBroker, order_plan,walk_book
from poly_live import LiveBroker
from btc_model_v12_polymarket import PolyRunner,official_result
from poly_dashboard import Dashboard

# The Work filesystem rejects fsync. Test-only connection disables sync;
# production Journal keeps synchronous=FULL. Restart/idempotency tests still
# reopen real SQLite files, but this environment cannot test power-loss durability.
import sqlite3
_real_connect=sqlite3.connect
class TestConnection(sqlite3.Connection):
    def executescript(self,script):
        return super().executescript(script.replace('PRAGMA synchronous=FULL','PRAGMA synchronous=OFF').replace('PRAGMA journal_mode=DELETE','PRAGMA journal_mode=MEMORY'))
def _connect(*a,**kw):
    kw['factory']=TestConnection
    return _real_connect(*a,**kw)
def setUpModule():
    global _db_patch
    _db_patch=patch('poly_core.sqlite3.connect',_connect);_db_patch.start()
def tearDownModule(): _db_patch.stop()

ROOT=pathlib.Path(__file__).parent

def snapshot(token='up',ask=.4,qty=100):
    return dict(event_type='book',asset_id=token,timestamp=str(int(time.time()*1000)),asks=[dict(price=str(ask),size=str(qty))],bids=[dict(price=str(ask-.01),size='100')])

def decision(): return dict(fire=True,side='UP',p=.8,threshold=.2,ask=.4,sec=30,ev=.9)

def epoch(): return int(time.time())-30

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=str(pathlib.Path(self.temp.name)/'test.db')
        self.db=Journal(self.path,'PAPER','abc'); self.books=BookCache();self.books.apply(snapshot());self.books.terms['up']=(.01,1,.07,1)
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def test_other_token_does_not_refresh_current(self):
        self.books.books['up']['event']-=10; self.books.apply(snapshot('next')); self.assertIsNone(self.books.quote('up'))
    def test_old_snapshot_rejected(self):
        self.books.clear();s=snapshot();s['timestamp']=str(int((time.time()-10)*1000)); self.books.apply(s);self.assertIsNone(self.books.quote('up'))
    def test_reconnect_requires_snapshot(self):
        self.books.clear();self.books.apply(dict(event_type='price_change',timestamp=str(int(time.time()*1000)),price_changes=[dict(asset_id='up',side='SELL',price='.4',size='100')]))
        self.assertIsNone(self.books.quote('up'))
    def test_crossed_book(self):
        s=snapshot();s['bids'][0]['price']='.5';self.books.apply(s);self.assertIsNone(self.books.quote('up'))
    def test_remove_ask(self):
        self.books.apply(dict(event_type='price_change',timestamp=str(int(time.time()*1000)),price_changes=[dict(asset_id='up',side='SELL',price='.4',size='0')]))
        self.assertIsNone(self.books.quote('up'))
    def test_tick_change_invalidates_terms(self):
        self.books.apply(dict(event_type='tick_size_change',asset_id='up',timestamp=str(int(time.time()*1000)),new_tick_size='.001'))
        self.assertNotIn('up',self.books.terms)
    def test_padded_ev(self):
        d=decision();d['p']=.5
        with self.assertRaisesRegex(ValueError,'EV'): order_plan(self.books.quote('up'),self.books.terms['up'],10,d,10)
    def test_no_stake_inflation(self):
        with self.assertRaisesRegex(ValueError,'minimum'): order_plan(self.books.quote('up'),(.01,5,.07,1),1,decision())
    def test_budget_and_cap(self):
        q=self.books.quote('up');p=order_plan(q,self.books.terms['up'],10,decision());f=walk_book(q,p)
        self.assertLessEqual(f['spent']+f['fees'],10);self.assertAlmostEqual(p['cap'],.41)
    def test_partial_paper_fill(self):
        self.books.apply(snapshot(qty=2));q=self.books.quote('up');p=order_plan(q,self.books.terms['up'],10,decision());f=walk_book(q,p)
        self.assertEqual(f['shares'],2);self.assertAlmostEqual(f['spent'],.8)
    def test_database_separation(self):
        with self.assertRaises(ValueError): Journal(self.path,'LIVE','abc')
    def test_persisted_reservation(self):
        self.assertTrue(self.db.reserve(100,decision(),'up','condition')); self.db.c.close();self.db=Journal(self.path,'PAPER','abc')
        self.assertFalse(self.db.reserve(100,decision(),'up','condition'))
    def test_resolution_requires_final(self):
        m=dict(closed=True,outcomes='["Up","Down"]',outcomePrices='["1","0"]')
        self.assertIsNone(official_result(m));m['umaResolutionStatus']='resolved';self.assertEqual(official_result(m),'UP')
    def test_no_graded_failed_order(self):
        self.db.reserve(100,decision(),'up','c');self.db.grade(100,'UP');self.assertEqual(self.db.metrics()['n'],0)
    def test_fill_dedup_and_pnl(self):
        p=order_plan(self.books.quote('up'),self.books.terms['up'],10,decision());self.db.reserve(100,decision(),'up','c');self.db.order('o',100,1,p)
        f=dict(shares=2,spent=.8,fees=.0336,price=.4)
        self.db.fill('o',100,'f',f,'paper');self.db.fill('o',100,'f',f,'paper');self.db.grade(100,'UP');self.assertEqual(self.db.metrics()['n'],0)
        self.db.order_status('o','FILLED');self.db.grade(100,'UP');self.db.grade(100,'DOWN')
        self.assertAlmostEqual(self.db.metrics()['pnl'],1.1664);self.assertEqual(self.db.metrics()['n'],1)
    def test_paper_execution_end_to_end(self):
        async def run():
            ex=Executor(self.db,self.books,PaperBroker(self.books));ep=epoch()
            await ex.fire(ep,decision(),'up','c',10,decision);await ex.reconcile();self.db.grade(ep,'UP')
            self.assertEqual(self.db.metrics()['n'],1);self.assertEqual(self.db.metrics()['wins'],1)
        asyncio.run(run())
    def test_paper_fill_survives_broker_restart(self):
        async def run():
            ep=epoch();ex=Executor(self.db,self.books,PaperBroker(self.books,self.db))
            await ex.fire(ep,decision(),'up','c',10,decision)
            self.db.c.close(); self.db=Journal(self.path,'PAPER','abc')
            ex=Executor(self.db,self.books,PaperBroker(self.books,self.db))
            await ex.reconcile();self.db.grade(ep,'UP')
            self.assertEqual(self.db.metrics()['wins'],1)
        asyncio.run(run())
    def test_timeout_never_resubmits_on_restart(self):
        class TimeoutBroker(PaperBroker):
            async def post(self,s): raise TimeoutError()
        async def run():
            ex=Executor(self.db,self.books,TimeoutBroker(self.books));ep=epoch()
            await ex.fire(ep,decision(),'up','c',10,decision)
            await ex.fire(ep,decision(),'up','c',10,decision)
            self.assertEqual(len(self.db.sql('SELECT * FROM orders')),1)
            self.assertEqual(self.db.sql('SELECT status FROM orders')[0][0],'UNKNOWN')
        asyncio.run(run())
    def test_partial_acceptance_stops_retries(self):
        async def run():
            self.books.apply(snapshot(qty=2));ex=Executor(self.db,self.books,PaperBroker(self.books));ep=epoch()
            await ex.fire(ep,decision(),'up','c',10,decision);await ex.reconcile()
            self.assertEqual(len(self.db.sql('SELECT * FROM orders')),1);self.assertAlmostEqual(self.db.sql('SELECT shares FROM fills')[0][0],2)
        asyncio.run(run())
    def test_retry_only_on_fresh_quote(self):
        books=self.books
        class Retry(PaperBroker):
            calls=0
            async def post(self,s):
                self.calls+=1
                if self.calls==1:
                    books.apply(snapshot(ask=.42));return {'rejected':'fak_not_filled'}
                return await super().post(s)
        async def run():
            broker=Retry(books);ex=Executor(self.db,books,broker)
            await ex.fire(epoch(),decision(),'up','c',10,decision)
            rows=self.db.sql('SELECT plan FROM orders ORDER BY attempt');self.assertEqual(len(rows),2)
            self.assertEqual(json.loads(rows[1][0])['quote'],.42)
        asyncio.run(run())
    def test_model_changed_before_post_abandons(self):
        calls=[0]
        def changed():
            calls[0]+=1
            return decision() if calls[0]==1 else {'fire':False}
        asyncio.run(Executor(self.db,self.books,PaperBroker(self.books)).fire(epoch(),decision(),'up','c',10,changed))
        self.assertEqual(len(self.db.sql('SELECT * FROM orders')),0)
    def test_explicit_rejection_keeps_full_message_and_releases_reserve(self):
        class FakeResponse:
            status_code=400
            text='insufficient balance / allowance'
            def json(self): return {'error':'insufficient balance / allowance','signature':'must-not-log'}
        class RequestRejectedError(Exception):
            status=400; code='INSUFFICIENT_BALANCE'; response=FakeResponse()
        class RejectBroker(PaperBroker):
            async def post(self,signed):
                raise RequestRejectedError('insufficient balance / allowance')
        async def run():
            out=io.StringIO(); ep=epoch(); ex=Executor(self.db,self.books,RejectBroker(self.books))
            with contextlib.redirect_stdout(out):
                await ex.fire(ep,decision(),'up','c',10,decision)
            row=self.db.sql('SELECT status,reason,error_json FROM orders')[0]
            self.assertEqual(row['status'],'REJECTED')
            info=json.loads(row['error_json'])
            self.assertEqual(info['class'],'RequestRejectedError')
            self.assertIn('insufficient balance',info['message'])
            self.assertEqual(info['status'],400); self.assertEqual(info['code'],'INSUFFICIENT_BALANCE')
            self.assertEqual(info['response_json']['signature'],'<redacted>')
            self.assertIn('insufficient balance',out.getvalue())
            self.assertEqual(self.db.live_reserve(),0)
        asyncio.run(run())
    def test_http_5xx_submit_is_unknown_not_rejected(self):
        class RequestRejectedError(Exception): status=503; code='UPSTREAM_UNAVAILABLE'
        class ServerErrorBroker(PaperBroker):
            async def post(self,signed): raise RequestRejectedError('upstream unavailable after request')
        async def run():
            ex=Executor(self.db,self.books,ServerErrorBroker(self.books)); ep=epoch()
            await ex.fire(ep,decision(),'up','c',10,decision)
            row=self.db.sql('SELECT status,error_json FROM orders')[0]
            self.assertEqual(row['status'],'UNKNOWN')
            self.assertEqual(json.loads(row['error_json'])['request_reached'],'UNKNOWN')
        asyncio.run(run())
    def test_unknown_survives_restart_then_venue_no_fill_clears_reserve(self):
        class AmbiguousBroker(PaperBroker):
            async def post(self,signed): raise TimeoutError('socket closed after send')
        async def first():
            ep=epoch(); ex=Executor(self.db,self.books,AmbiguousBroker(self.books))
            await ex.fire(ep,decision(),'up','c',10,decision)
            return ep
        ep=asyncio.run(first())
        row=self.db.sql('SELECT status,error_json FROM orders')[0]
        self.assertEqual(row['status'],'UNKNOWN')
        self.assertEqual(json.loads(row['error_json'])['request_reached'],'UNKNOWN')
        self.assertGreater(self.db.live_reserve(),0)
        self.db.c.close(); self.db=Journal(self.path,'PAPER','abc')
        class VenueTruth(PaperBroker):
            calls=0
            async def reconcile(self,r):
                self.calls+=1
                if self.calls==1: return dict(terminal=False,fills=[],live=False,reason='first venue miss')
                return dict(terminal=True,fills=[],live=False,verified_no_fill=True,reason='venue confirms no order/trade')
        async def finish():
            ex=Executor(self.db,self.books,VenueTruth(self.books))
            await ex.reconcile(); self.assertGreater(self.db.live_reserve(),0)
            await ex.reconcile()
        asyncio.run(finish())
        self.assertEqual(self.db.sql('SELECT status FROM orders')[0][0],'NO_FILL')
        self.assertEqual(self.db.live_reserve(),0)
        self.db.grade(ep,'DOWN'); self.assertEqual(self.db.metrics()['n'],0)
    def test_latency_stages_are_persisted(self):
        async def run():
            ex=Executor(self.db,self.books,PaperBroker(self.books)); ep=epoch()
            await ex.fire(ep,decision(),'up','c',10,decision)
            row=self.db.sql('SELECT timing_json FROM orders')[0]
            timing=json.loads(row['timing_json'])
            for key in ('quote_wait_ms','quote_read_ms','decision_ms','sign_ms','final_recheck_ms','fire_to_submit_ms','submit_ms','response_ms','total_attempt_ms','book_age_ms'):
                self.assertIn(key,timing)
            stats=ex.latency_stats(); self.assertEqual(stats['n'],1)
            for key in ('p50_ms','p95_ms','p99_ms','max_ms'): self.assertIn(key,stats)
        asyncio.run(run())
    def test_v120_database_migrates_additively(self):
        self.db.reserve(123,decision(),'up','condition')
        self.db.set('build','12.0'); self.db.c.close(); self.db=Journal(self.path,'PAPER','abc')
        self.assertEqual(self.db.get('build'),'12.3.4')
        self.assertEqual(self.db.sql('SELECT count(*) FROM signals WHERE epoch=123')[0][0],1)
        cols={r[1] for r in self.db.c.execute('PRAGMA table_info(orders)')}
        self.assertTrue({'error_json','timing_json','request_reached','reconcile_count','venue_live'}<=cols)


class LiveBrokerSimulationTests(unittest.TestCase):
    """Venue-side simulations: exact order/trade truth wins over local bookkeeping."""
    def setUp(self): self.books=BookCache(); self.b=LiveBroker(self.books)
    def test_sdk_request_rejection_is_explicit_not_unknown(self):
        class Response:
            status_code=400; text='insufficient balance/allowance'
            def json(self): return {'error':'insufficient balance/allowance'}
        class RequestRejectedError(Exception):
            status=400; code='INSUFFICIENT_BALANCE'; response=Response()
        class Client:
            async def post_order(self,_): raise RequestRejectedError('insufficient balance/allowance')
        self.b.client=Client()
        r=asyncio.run(self.b.post(object()))
        self.assertIn('rejected',r); self.assertEqual(r['rejected']['class'],'RequestRejectedError')
        self.assertEqual(r['rejected']['status'],400); self.assertIn('insufficient balance',r['rejected']['message'])
    def test_http_5xx_rejection_exception_remains_ambiguous(self):
        class RequestRejectedError(Exception): status=503; code='UPSTREAM_UNAVAILABLE'
        class Client:
            async def post_order(self,_): raise RequestRejectedError('upstream unavailable')
        self.b.client=Client()
        with self.assertRaises(RequestRejectedError): asyncio.run(self.b.post(object()))
    def test_non_ok_5xx_response_is_ambiguous(self):
        class Client:
            async def post_order(self,_): return SimpleNamespace(ok=False,status=503,code='UPSTREAM_UNAVAILABLE',message='upstream unavailable')
        self.b.client=Client(); r=asyncio.run(self.b.post(object()))
        self.assertIn('ambiguous',r); self.assertEqual(r['ambiguous']['request_reached'],'UNKNOWN')
    def test_repeated_venue_absence_proves_fak_no_fill(self):
        class RequestRejectedError(Exception): status=404; code='NOT_FOUND'
        class Client:
            def list_account_trades(self,**kwargs):
                async def gen():
                    if False: yield None
                return gen()
            async def get_order(self,**kwargs): raise RequestRejectedError('order not found')
        self.b.client=Client()
        base=dict(id='oid',token='up',plan=json.dumps(dict(rate=.07,exponent=1)),ts=time.time()-3,reconcile_count=0)
        first=asyncio.run(self.b.reconcile(base)); self.assertFalse(first['terminal'])
        base['reconcile_count']=1
        second=asyncio.run(self.b.reconcile(base)); self.assertTrue(second['terminal']); self.assertTrue(second['verified_no_fill']); self.assertEqual(second['fills'],[])
    def test_confirmed_account_trade_proves_fill_when_order_endpoint_is_gone(self):
        class RequestRejectedError(Exception): status=404; code='NOT_FOUND'
        trade=SimpleNamespace(taker_order_id='oid',trader_side='TAKER',size='5.4717',price='0.53',status='CONFIRMED',id='trade1')
        class Client:
            def list_account_trades(self,**kwargs):
                async def gen(): yield SimpleNamespace(items=[trade])
                return gen()
            async def get_order(self,**kwargs): raise RequestRejectedError('order not found')
        self.b.client=Client()
        row=dict(id='oid',token='up',plan=json.dumps(dict(rate=.07,exponent=1)),ts=time.time()-3,reconcile_count=0)
        out=asyncio.run(self.b.reconcile(row)); self.assertTrue(out['terminal']); self.assertEqual(len(out['fills']),1)
        tid,f=out['fills'][0]; self.assertEqual(tid,'trade1'); self.assertAlmostEqual(f['shares'],5.4717); self.assertAlmostEqual(f['price'],.53)

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        a=SimpleNamespace(model=str(ROOT/'model_v10.json'),db=str(pathlib.Path(self.temp.name)/'ui.db'),live=False,host='127.0.0.1',port=0,capital=50,quote_age_ms=750,pad_ticks=1,ev=None)
        self.r=PolyRunner(a);self.r.cash=50;self.r.cash_at=time.monotonic();self.ui=self.r.ui
    def tearDown(self):self.r.db.c.close();self.r.process_lock.close();self.temp.cleanup()
    def test_unvalidated_lanes_seed_off(self):
        """MAIN and REVERSAL must not be armed by switching master on.

        The seeding loop PERSISTS what it writes, so a True there is a stored
        flag that reads as deliberately enabled, not a soft default. Seeding all
        three True is what put a live MAIN order on the book on 09-12 16:51 on a
        lane that has never been validated with money.
        """
        self.assertIs(self.r.db.get('main_enabled'),False)
        self.assertIs(self.r.db.get('reversal_enabled'),False)
        self.assertIs(self.r.db.get('ef_enabled'),True)

    def test_master_on_does_not_arm_main_or_reversal(self):
        self.ui.apply('/api/controls/apply',dict(confirmed=True,system={'manual_enabled':True}))
        self.assertTrue(self.ui.allowed('EF'))
        self.assertFalse(self.ui.allowed('MAIN'))
        self.assertFalse(self.ui.allowed('REVERSAL'))

    def test_original_dashboard_has_old_panels(self):
        page=self.ui.page('dashboard_html.html')
        for name in ['id="lwchart"','id="history"','id="pnlCanvas"','Trade Controls','sideTiles']: self.assertIn(name,page)
        self.assertNotIn('Predict.fun',page);self.assertNotIn('__VERSION__',page)
    def test_ladder_two_checks_up_immediate_down(self):
        self.ui.update_stake();self.assertEqual(self.r.db.get('next_stake'),1)
        self.ui.update_stake();self.assertEqual(self.r.db.get('next_stake'),4)
        with patch.object(self.ui,'equity',return_value=29):self.ui.update_stake()
        self.assertEqual(self.r.db.get('next_stake'),1)
    def test_invalid_stake_does_not_apply_master(self):
        self.r.db.set('master',False)
        with self.assertRaises(ValueError):
            self.ui.apply('/api/controls/apply',dict(confirmed=True,system=dict(manual_enabled=True,stake=dict(percent=-1))))
        self.assertFalse(self.r.db.get('master'))
    def test_invalid_daily_limits_apply_neither(self):
        with self.assertRaises(ValueError):
            self.ui.apply('/api/controls/daily-limits',dict(confirmed=True,take_profit=20,stop_loss=-1))
        self.assertEqual(self.r.db.get('tp'),0)
    def test_out_of_order_settlement_updates_streak(self):
        for ep in (200,100):
            self.r.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',(ep,'UP',0,-1,time.time()))
            self.ui.update_stake()
        self.assertEqual(self.r.db.get('streak'),[0,2])
    def test_failed_attempt_has_no_pnl(self):
        db=self.r.db;db.reserve(100,decision(),'up','c')
        plan=dict(quote=.4,budget=1,age_ms=1)
        db.order('fail',100,1,plan);db.order_status('fail','REJECTED')
        db.order('ok',100,2,plan);db.order_status('ok','FILLED')
        db.fill('ok',100,'f',dict(shares=2,spent=.8,fees=.03,price=.4),'test');db.grade(100,'UP')
        orders={r['order_id']:r for r in self.ui.orders()['rows']}
        self.assertIsNone(orders['fail']['pnl']);self.assertAlmostEqual(orders['ok']['pnl'],1.17)
    def test_master_toggle(self):
        self.ui.apply('/api/controls/apply',dict(confirmed=True,system={'manual_enabled':False}));self.assertFalse(self.ui.allowed())
    def test_main_rev_are_real_lanes_and_switch_from_trade_controls(self):
        # v12.0/12.1 reported these two as having no signal source, so the
        # toggles could never take effect. They are now the ported Build 11
        # pressure lanes and must behave exactly like EF under the controls.
        c=self.ui.controls()
        for k in ('MAIN','REVERSAL','EF'):
            self.assertTrue(c['kinds'][k]['source_available'],f'{k} must have a signal source')
        self.ui.apply('/api/controls/apply',dict(confirmed=True,system={'manual_enabled':True}))
        for k in ('MAIN','REVERSAL'):
            self.ui.apply('/api/controls/signal',dict(confirmed=True,kind=k,manual_enabled=True))
            self.assertTrue(self.ui.allowed(k),f'{k} should be permitted when master and its own switch are on')
            self.ui.apply('/api/controls/signal',dict(confirmed=True,kind=k,manual_enabled=False))
            self.assertFalse(self.ui.allowed(k),f'{k} must stop firing when switched off')
            self.assertFalse(self.ui.controls()['kinds'][k]['manual_enabled'])
        # master off overrides an individually enabled lane
        self.ui.apply('/api/controls/signal',dict(confirmed=True,kind='MAIN',manual_enabled=True))
        self.ui.apply('/api/controls/apply',dict(confirmed=True,system={'manual_enabled':False}))
        self.assertFalse(self.ui.allowed('MAIN'))
    def test_lanes_record_separately_per_candle(self):
        # MAIN and REVERSAL can hold opposite sides of one candle: REVERSAL is a
        # hedge beside an open MAIN, not a replacement, so both need their own row.
        db=self.r.db
        self.assertTrue(db.reserve(700,dict(side='UP'),'tok','cond','MAIN'))
        self.assertTrue(db.reserve(700,dict(side='DOWN'),'tok2','cond','REVERSAL'))
        self.assertFalse(db.reserve(700,dict(side='UP'),'tok','cond','MAIN'),'one row per lane per candle')
        rows=db.sql('SELECT kind,side FROM signals WHERE epoch=? ORDER BY kind',(700,))
        self.assertEqual([(r['kind'],r['side']) for r in rows],[('MAIN','UP'),('REVERSAL','DOWN')])
        db.status(700,'PENDING','MAIN')
        got={r['kind']:r['status'] for r in db.sql('SELECT kind,status FROM signals WHERE epoch=?',(700,))}
        self.assertEqual(got['MAIN'],'PENDING')
        self.assertEqual(got['REVERSAL'],'RESERVED','status must not leak across lanes')
    def test_state_x_off_disables_window(self):
        self.r.db.set('sx_until',time.time()+900);self.ui.apply('/api/controls/state-x',dict(confirmed=True,manual_enabled=False));self.assertEqual(self.r.db.get('sx_until'),0)
    def test_venue_cash_is_dashboard_available_even_with_local_unknown_reserve(self):
        self.r.a.live=True; self.r.cash=13.73; self.r.cash_at=time.monotonic(); self.ui.cache=None
        db=self.r.db; db.reserve(100,decision(),'up','c')
        plan=dict(quote=.40,signal_quote=.40,pre_submit_quote=.40,cap=.41,budget=6.,age_ms=1,amount=5,rate=.07,exponent=1,seq=1)
        db.order('unknown',100,1,plan); db.order_status('unknown','UNKNOWN',error={'class':'TimeoutError','request_reached':'UNKNOWN'})
        snap=self.ui.snapshot(); cap=snap['capital']
        self.assertAlmostEqual(cap['wallet'],13.73); self.assertAlmostEqual(cap['free'],13.73)
        self.assertAlmostEqual(cap['reserved'],6.0); self.assertAlmostEqual(cap['funding_headroom'],7.73)
        self.assertEqual(cap['truth']['source'],'Polymarket API (balance, positions, open orders, account PnL)')
    def test_slippage_uses_raw_signal_ask_presubmit_and_fill(self):
        db=self.r.db; db.reserve(101,decision(),'up','c')
        plan=dict(quote=.40,signal_quote=.39,pre_submit_quote=.40,cap=.42,budget=3.,age_ms=1,amount=2.9,rate=.07,exponent=1,seq=1)
        db.order('filled',101,1,plan); db.fill('filled',101,'trade',dict(shares=5,spent=2.05,fees=.01,price=.41),'confirmed'); db.order_status('filled','FILLED')
        row=self.ui.orders('EF',0,10)['rows'][0]
        self.assertAlmostEqual(row['quoted_price'],.39); self.assertAlmostEqual(row['pre_submit_quote'],.40); self.assertAlmostEqual(row['fill_price'],.41)
        self.assertAlmostEqual(row['quote_to_fill'],.02); self.assertAlmostEqual(row['ask_to_fill'],.01); self.assertAlmostEqual(row['cap_to_fill'],.01)
    def test_snapshot_serializes(self):json.dumps(self.ui.snapshot(),allow_nan=False)
    def test_http_pages_and_api(self):
        import threading,urllib.request
        server=self.ui.make_server();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for path in ['/','/controls','/data','/api/state','/api/history','/api/orders?kind=EF','/api/chart','/api/pnl','/export.csv']:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}'+path) as response:self.assertEqual(response.status,200)
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main(verbosity=2)
