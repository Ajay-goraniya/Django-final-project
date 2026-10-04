import asyncio, hashlib, json, pathlib, tempfile, time, unittest
from types import SimpleNamespace
from unittest.mock import patch
from poly_core import BookCache, Journal, Executor, PaperBroker, order_plan,walk_book
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

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        a=SimpleNamespace(model=str(ROOT/'model_v10.json'),db=str(pathlib.Path(self.temp.name)/'ui.db'),live=False,host='127.0.0.1',port=0,capital=50,quote_age_ms=750,pad_ticks=1,ev=None)
        self.r=PolyRunner(a);self.r.cash=50;self.r.cash_at=time.monotonic();self.ui=self.r.ui
    def tearDown(self):self.r.db.c.close();self.r.process_lock.close();self.temp.cleanup()
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
    def test_main_cannot_accidentally_enable(self):
        with self.assertRaises(ValueError):self.ui.apply('/api/controls/signal',dict(confirmed=True,kind='MAIN',manual_enabled=True))
    def test_state_x_off_disables_window(self):
        self.r.db.set('sx_until',time.time()+900);self.ui.apply('/api/controls/state-x',dict(confirmed=True,manual_enabled=False));self.assertEqual(self.r.db.get('sx_until'),0)
    def test_snapshot_serializes(self):json.dumps(self.ui.snapshot(),allow_nan=False)
    def test_http_pages_and_api(self):
        import threading,urllib.request
        server=self.ui.make_server();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for path in ['/','/controls','/data','/api/state','/api/history','/api/orders?kind=EF','/api/chart','/api/pnl','/export.csv']:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}'+path) as response:self.assertEqual(response.status,200)
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main(verbosity=2)
