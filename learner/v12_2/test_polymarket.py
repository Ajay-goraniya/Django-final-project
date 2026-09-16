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
        self.books=BookCache();s=snapshot();s['timestamp']=str(int((time.time()-10)*1000)); self.books.apply(s);self.assertIsNone(self.books.quote('up'))
    def test_reconnect_requires_snapshot(self):
        self.books=BookCache();self.books.apply(dict(event_type='price_change',timestamp=str(int(time.time()*1000)),price_changes=[dict(asset_id='up',side='SELL',price='.4',size='100')]))
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
        q=self.books.quote('up');p=order_plan(q,self.books.terms['up'],10,decision(),require_depth=False);f=walk_book(q,p)  # partial-fill maths is PaperBroker behaviour
        self.assertLessEqual(f['spent']+f['fees'],10);self.assertAlmostEqual(p['cap'],.41)
    def test_partial_paper_fill(self):
        self.books.apply(snapshot(qty=2));q=self.books.quote('up');p=order_plan(q,self.books.terms['up'],10,decision(),require_depth=False);f=walk_book(q,p)  # partial-fill maths is PaperBroker behaviour
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
    def test_skipped_records_kind_and_the_ev_numbers(self):
        """The SKIPPED exit is 97% of what EF loses before the network.

        It used to write a bare sentence. diagnostics has ts and epoch only, and
        one epoch can hold an EF and a MAIN signal at once, so the largest loss
        in the system could not be attributed to a lane at all. Record the lane
        and the three numbers the EV comparison is made of.
        """
        async def run():
            ex=Executor(self.db,self.books,PaperBroker(self.books,self.db));ep=epoch()
            d=dict(decision(),p=.30,threshold=.20)   # 0.30/cost - 1 < 0.20 -> raises
            await ex.fire(ep,d,'up','c',10,lambda:d,kind='MAIN')
            rows=[r[2] for r in self.db.sql('SELECT * FROM diagnostics')]
            hit=[json.loads(r) for r in rows
                 if 'order_plan_refused' in (r or '')]
            self.assertEqual(len(hit),1,rows)
            g=hit[0]
            self.assertEqual(g['kind'],'MAIN')
            self.assertEqual(g['side'],'UP')
            self.assertIn('EV',g['error'])
            self.assertAlmostEqual(g['ask'],.4)
            self.assertAlmostEqual(g['p'],.30)
            self.assertAlmostEqual(g['threshold'],.20)
            self.assertEqual(self.db.sql('SELECT count(*) FROM orders')[0][0],0)
        asyncio.run(run())

    def test_rolling_observes_a_turn_that_cumulative_pnl_hides(self):
        """Cumulative PnL reads "up" while the recent window is bleeding.

        That is exactly the state the operator was looking at: a run that made
        money earlier and is losing now. rolling() is observation only.
        """
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        for i in range(30):                      # 30 winners, then 20 losers
            ep=1000+i
            self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                        " VALUES(?,?,1,'FILLED','{}',0,0,'',?)",(f'o{ep}',ep,'EF'))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',
                        (ep,'UP',10.,+5.))
        for i in range(20):
            ep=2000+i
            self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                        " VALUES(?,?,1,'FILLED','{}',0,0,'',?)",(f'o{ep}',ep,'EF'))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',
                        (ep,'DOWN',0.,-5.))
        self.assertGreater(self.db.metrics()['pnl'],0,'cumulative still reads up')
        r=self.db.rolling()
        self.assertEqual(r['all'][20]['n'],20)
        self.assertLess(r['all'][20]['per_dollar'],0,'the recent window must show the turn')
        self.assertEqual(r['all'][20]['wins'],0,'the whole recent window lost')
        self.assertFalse(r['all'][20]['sufficient'],'20 is under the 60 bar and must say so')
        self.assertAlmostEqual(r['all'][20]['median_price'],.5)
        self.assertTrue(r['kill']['armed'])
        self.assertEqual(r['by_kind'][20]['EF']['n'],20)
        self.assertEqual(r['mixed_epochs'],0)

    def test_rolling_refuses_to_split_lanes_that_share_a_candle(self):
        """results has no kind, so a shared epoch cannot be attributed.

        Reporting it per lane would count the same PnL twice. It reports None.
        """
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        for kind in ('EF','MAIN'):
            self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                        " VALUES(?,?,1,'FILLED','{}',0,0,'',?)",(f'o{kind}',500,kind))
            self.db.fill(f'o{kind}',500,f't{kind}',f,'paper')
        self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',(500,'UP',10.,+5.))
        r=self.db.rolling()
        self.assertEqual(r['mixed_epochs'],1)
        self.assertIsNone(r['by_kind'][20],'a mixed epoch must not be split per lane')
        self.assertEqual(r['all'][20]['n'],1,'the overall window still counts it once')

    def test_kill_rule_is_per_lane_not_blended(self):
        """Another lane's stale win must not buy EF headroom against its halt.

        Reproduces 09-13 exactly: EF's last 20 sum below -3.00 while one MAIN
        winner lifts the blended sum above it. Blended-only, this never fires.
        """
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        def settle(ep,kind,pnl):
            self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                        " VALUES(?,?,1,'FILLED','{}',0,0,'',?)",(f'o{ep}',ep,kind))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',
                        (ep,'UP',0.,pnl))
        for i in range(20): settle(3000+i,'EF',-1.0)      # EF sum = -4.00
        settle(3100,'MAIN',+25.0)                          # one MAIN winner
        self.db.halt_check()
        # 12.8.8: the lane's own window is still what is measured - but it is
        # REPORTED, not acted on. User: "kill ?? bro we don't need that".
        self.assertIsNone(self.db.get('halt'),'a PnL condition never halts the engine')
        rows=[json.loads(r[0]) for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%KILL_CONDITION%'")]
        self.assertEqual([r['rule'] for r in rows],['EF'],"EF's own window tripped; the blend did not")
        self.assertFalse(rows[0]['acted']); self.assertAlmostEqual(rows[0]['unit_sum'],-4.0)

    def test_rolling_reports_the_same_per_lane_rule_halt_check_enforces(self):
        """What the rule enforces is what the screen must show.

        12.5.1 made halt_check per-lane but left rolling()['kill'] blended, so
        the engine acted on one number while the operator read another - the
        same shape as the dashboard build string reading 12.4.4 while 12.4.6 ran.
        """
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        def settle(ep,kind,pnl):
            self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                        " VALUES(?,?,1,'FILLED','{}',0,0,'',?)",(f'o{ep}',ep,kind))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',
                        (ep,'UP',0.,pnl))
        for i in range(20): settle(5000+i,'EF',-1.0)   # EF's own 20: sum -4.00
        settle(5100,'MAIN',+25.0)                       # lifts the blend
        k=self.db.rolling()['kill']
        self.assertGreater(k['unit_return_sum'],-3.0,'the blend alone looks fine')
        self.assertIn('EF',k['by_kind'])
        self.assertLess(k['by_kind']['EF']['unit_return_sum'],-3.0,
                        "EF's own window is what halt_check acts on")
        self.assertTrue(k['by_kind']['EF']['armed'])
        # MAIN has one result, so it is not armed and reports no sum.
        self.assertEqual(k['by_kind']['MAIN']['n'],1)
        self.assertIsNone(k['by_kind']['MAIN']['unit_return_sum'])
        self.assertEqual(k['by_kind']['MAIN']['results_until_armed'],19)

    def test_kill_rule_does_not_fire_on_a_healthy_lane(self):
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        for i in range(20):
            ep=4000+i
            self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                        " VALUES(?,?,1,'FILLED','{}',0,0,'',?)",(f'o{ep}',ep,'EF'))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',
                        (ep,'UP',10.,+5.))
        self.db.halt_check()
        self.assertIsNone(self.db.get('halt'))
        self.assertEqual(self.db.sql("SELECT count(*) FROM diagnostics WHERE detail LIKE '%KILL_CONDITION%'")[0][0],0,
                         'a healthy lane reports no condition')

    def test_a_skip_is_explained_in_numbers_not_just_named(self):
        """User: "i just don't see better with my eyes that's why i was concerned".

        SKIPPED alone reads as a fault. With the numbers it is obviously the
        engine declining to overpay - the difference between a screen you can
        trust and one you cannot.
        """
        import btc_model_v12_polymarket as E
        r=E.PolyRunner.skip_reason
        out=r('SKIPPED',json.dumps(dict(reason='order_plan_refused',kind='MAIN',
              side='DOWN',error='price fails model EV',ask=0.87,p=0.6426,threshold=0.25)))
        self.assertIn('ask 0.87',out)
        self.assertIn('worth 0.64',out)
        self.assertIn('max payable 0.51',out)
        self.assertIn('price fails model EV',out)

    def test_skip_reason_survives_rows_without_the_numbers(self):
        import btc_model_v12_polymarket as E
        r=E.PolyRunner.skip_reason
        self.assertEqual(r('SKIPPED',None),'SKIPPED')
        self.assertIn('below venue minimum',
                      r('SKIPPED','below venue minimum; stake not increased'))
        self.assertIn('boom', r('SKIPPED',json.dumps(dict(error='boom'))))
        self.assertIn('SKIPPED', r('SKIPPED','[1,2,3]'))

    def test_clearing_a_halt_actually_restarts_trading(self):
        """Without a fresh window the reset does not reset.

        The window is the last 20 settled results; clearing `halt` does not
        change them, and no new result can arrive while every lane is blocked.
        So halt_check re-fired about a second later and the engine never
        restarted. Proved on 09-13 after EF's kill.
        """
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        def loss(ep,ts):
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
                        " VALUES(?,?,1,'FILLED','{}',?,0,'','EF')",(f'o{ep}',ep,ts))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',
                        (ep,'UP',0.,-5.,ts))
        # 12.8.8: nothing halts any more, but the fresh-window semantics still
        # govern WHEN the condition is reported: one row per episode, and a
        # clear (halt_cleared_at) starts a new episode.
        # One lane only, so the blended (ALL) and the per-lane (EF) conditions
        # trip together: two rows per episode.
        def cond(): return self.db.sql("SELECT count(*) FROM diagnostics WHERE detail LIKE '%KILL_CONDITION%'")[0][0]
        for i in range(20): loss(1000+i,100.0+i)
        self.db.halt_check(); self.db.halt_check()
        self.assertIsNone(self.db.get('halt'),'a PnL condition never halts')
        self.assertEqual(cond(),2,'each condition reported once, not once per pass')

        self.db.set('halt_cleared_at',500.0)
        self.db.halt_check()
        self.assertEqual(cond(),2,'the window is empty after the clear: nothing new to report')

        for i in range(19): loss(2000+i,600.0+i)
        self.db.halt_check()
        self.assertEqual(cond(),2,'19 fresh results are not a full window')
        loss(2100,700.0); self.db.halt_check()
        self.assertEqual(cond(),4,'20 fresh bad results are a new episode, reported again')
        self.assertIsNone(self.db.get('halt'))

    def test_what_the_rule_enforces_is_what_the_screen_shows(self):
        """Three times on 09-13 the acting code and the displayed code drifted.

        The header said 12.4.4 while meta said 12.4.6. halt_check enforced per
        lane while rolling() showed the blend. halt_check honoured the fresh
        window after a clear while rolling() showed the stale one - so the
        dashboard reported EF armed at -4.46 minutes after enforcement had
        reset, and an operator would have read that as the clear having failed.

        They share one query now. This asserts they cannot drift again.
        """
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        def loss(ep,ts):
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
                        " VALUES(?,?,1,'FILLED','{}',?,0,'','EF')",(f'o{ep}',ep,ts))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',
                        (ep,'UP',0.,-5.,ts))
        for i in range(20): loss(1000+i,100.0+i)
        self.db.halt_check()
        # 12.8.8: "armed" on the screen means the condition is met and REPORTED;
        # the engine no longer acts on it, so halt stays None throughout.
        self.assertIsNone(self.db.get('halt'))
        k=self.db.rolling()['kill']
        self.assertTrue(k['by_kind']['EF']['armed'],'the screen shows the condition the report is about')
        self.assertEqual(sorted(json.loads(r[0])['rule'] for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%KILL_CONDITION%'")),
                         ['ALL','EF'],'one lane: the blend and the lane trip together, one row each')

        # The clear resets the window. The display must reset with it.
        self.db.set('halt_cleared_at',500.0)
        self.db.halt_check()
        self.assertIsNone(self.db.get('halt'))
        k=self.db.rolling()['kill']
        self.assertEqual(k['by_kind'],{},'no lane has results in the fresh window')
        self.assertIsNone(k['unit_return_sum'],'and no stale sum is displayed')
        self.assertEqual(k['results_until_armed'],20)
        self.assertFalse(k['armed'],'the screen must not say armed when it is not')

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
    def test_stuck_reconcile_is_recorded_once_not_every_second(self):
        """12.8.11. The 4,292-attempt loop left NO diagnostics row, because
        broker.reconcile returned instead of raising. One RECONCILE_STUCK row per
        order per distinct reason, so the next stuck order is visible in an hour,
        not found by a human counting reconcile_count."""
        class AmbiguousBroker(PaperBroker):
            async def post(self,signed): raise TimeoutError('socket closed after send')
        async def first():
            ep=epoch(); ex=Executor(self.db,self.books,AmbiguousBroker(self.books))
            await ex.fire(ep,decision(),'up','c',10,decision)
        asyncio.run(first())
        self.db.c.close(); self.db=Journal(self.path,'PAPER','abc')
        class Stuck(PaperBroker):
            async def reconcile(self,r): return dict(terminal=False,fills=[],live=False,reason=json.dumps({'class':'UnexpectedResponseError','message':'OpenOrder response did not match expected shape','phase':'reconcile_get_order'}))
        async def loop():
            ex=Executor(self.db,self.books,Stuck(self.books))
            for _ in range(5): await ex.reconcile()
        asyncio.run(loop())
        rows=[json.loads(r['detail']) for r in self.db.sql('SELECT detail FROM diagnostics')]
        stuck=[d for d in rows if d.get('kind')=='RECONCILE_STUCK']
        self.assertEqual(len(stuck),1); self.assertEqual(stuck[0]['class'],'UnexpectedResponseError'); self.assertIn('order',stuck[0])
        self.assertEqual(self.db.sql('SELECT status FROM orders')[0][0],'UNKNOWN')
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
        self.assertEqual(self.db.get('build'),'12.15.0')
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
    def test_unreadable_get_order_resolves_on_repeated_venue_absence(self):
        """12.8.11. Zurich Z-4: get_order raised UnexpectedResponseError ("OpenOrder
        response did not match expected shape") in 0.04 s for an order the venue
        never received; the non-404 branch returned terminal=False 4,292 times over
        80 minutes, the candle never graded and 2.88 stayed reserved. The account's
        own open-orders listing had shown the id absent 232 times and the trade tape
        had nothing. That is venue truth; use it."""
        class UnexpectedResponseError(Exception): pass
        class Client:
            def list_account_trades(self,**kwargs):
                async def gen():
                    if False: yield None
                return gen()
            async def get_order(self,**kwargs): raise UnexpectedResponseError('OpenOrder response did not match expected shape')
        self.b.client=Client()
        row=dict(id='oid',token='up',plan=json.dumps(dict(rate=.07,exponent=1)),ts=time.time()-70,reconcile_count=5,venue_absent=0)
        out=asyncio.run(self.b.reconcile(row)); self.assertFalse(out['terminal']); self.assertIn('UnexpectedResponseError',out['reason'])
        row['venue_absent']=3; row['ts']=time.time()-10
        out=asyncio.run(self.b.reconcile(row)); self.assertFalse(out['terminal'])
        row['ts']=time.time()-70
        out=asyncio.run(self.b.reconcile(row)); self.assertTrue(out['terminal']); self.assertTrue(out['verified_no_fill']); self.assertEqual(out['fills'],[])
        self.assertIn('UnexpectedResponseError',out['reason']); self.assertIn('3x',out['reason'])
    def test_unreadable_get_order_still_takes_a_confirmed_trade(self):
        class UnexpectedResponseError(Exception): pass
        trade=SimpleNamespace(taker_order_id='oid',trader_side='TAKER',size='5.4717',price='0.53',status='CONFIRMED',id='trade1')
        class Client:
            def list_account_trades(self,**kwargs):
                async def gen(): yield SimpleNamespace(items=[trade])
                return gen()
            async def get_order(self,**kwargs): raise UnexpectedResponseError('OpenOrder response did not match expected shape')
        self.b.client=Client()
        row=dict(id='oid',token='up',plan=json.dumps(dict(rate=.07,exponent=1)),ts=time.time()-70,reconcile_count=5,venue_absent=9)
        out=asyncio.run(self.b.reconcile(row)); self.assertTrue(out['terminal']); self.assertEqual(len(out['fills']),1); self.assertNotIn('verified_no_fill',out)

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

    def test_header_build_is_read_from_the_journal(self):
        """The screen the operator checks must not lie about what is running.

        This literal was hardcoded and went stale: the header read 12.4.4 while
        12.4.6 was live. Two places to bump means one is eventually wrong.
        """
        page=self.ui.page('controls_html.html')
        self.assertIn(self.r.db.get('build'),page)
        self.assertNotIn('__BUILD__',page)
        self.r.db.set('build','99.9.9')
        self.assertIn('99.9.9',self.ui.page('controls_html.html'))

    def test_no_version_literal_is_hardcoded_in_the_dashboard(self):
        """poly_core's meta build is the single source; nothing else states one."""
        import pathlib,re
        src=pathlib.Path(__file__).with_name('poly_dashboard.py').read_text()
        src=re.sub(r'#[^\n]*','',src)          # comments may name past builds
        self.assertEqual(re.findall(r"['\"]12\.\d+\.\d+",src),[])
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


class PnLConditionsNeverHalt(unittest.TestCase):
    """12.8.8. User, 09-13 23:5x: "kill ?? bro we don't need that, what i said was
    you will turn off master when it will run out of money, it doesn't mean you
    write a code block for that in model".

    The -3.00 rule was the operator's by-hand rule, and it had been written into
    halt_check as a coded stop (since 12.4.x) - the same mistake 12.8.3 fixed for
    the low-balance guard. The conditions are still measured and written to
    diagnostics as KILL_CONDITION rows, once per episode, so the operator can see
    them; the engine never sets `halt` on any of them. The one engine-set halt
    that remains is the order-identity mismatch in Executor.fire.
    """
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Journal(str(pathlib.Path(self.temp.name)/'h.db'),'LIVE','h')
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        for i in range(20):                       # EF sum -20: blended AND per-lane both trip
            ep=5000+i
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
                        " VALUES(?,?,1,'FILLED','{}',0,0,'','EF')",(f'o{ep}',ep))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',(ep,'UP',0.,-1.0))
        self.db.sql('DELETE FROM diagnostics')

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def rows(self):
        return [json.loads(r[0]) for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%KILL_CONDITION%'")]

    def halt_writes(self):
        return [json.loads(r[0]) for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%control_write%'")
                if json.loads(r[0]).get('key')=='halt']

    def test_both_conditions_true_and_the_engine_does_not_stop(self):
        for _ in range(50): self.db.halt_check()
        self.assertIsNone(self.db.get('halt'))
        self.assertEqual(self.halt_writes(),[],'halt is not written by a PnL rule, not even once')

    def test_each_condition_is_reported_once_per_episode_with_its_number(self):
        for _ in range(50): self.db.halt_check()
        rows=self.rows()
        self.assertEqual(sorted(r['rule'] for r in rows),['ALL','EF'],'blended and per-lane both tripped, each reported once')
        for r in rows:
            self.assertFalse(r['acted']); self.assertEqual(r['n'],20)
            self.assertAlmostEqual(r['unit_sum'],-4.0); self.assertEqual(r['limit'],-3.0)

    def test_the_report_is_per_process_episode_and_a_recovery_re_arms_it(self):
        self.db.halt_check(); self.assertEqual(len(self.rows()),2)
        # Twenty winners on top push both windows back above the line...
        f=dict(shares=10.,spent=5.,fees=0.,price=.5,fee_bps=0)
        for i in range(20):
            ep=6000+i
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
                        " VALUES(?,?,1,'FILLED','{}',0,0,'','EF')",(f'o{ep}',ep))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',(ep,'UP',10.,+5.0))
        self.db.halt_check(); self.assertEqual(len(self.rows()),2,'a cleared condition adds nothing')
        # ...and twenty fresh losers are a NEW episode.
        for i in range(20):
            ep=7000+i
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
                        " VALUES(?,?,1,'FILLED','{}',0,0,'','EF')",(f'o{ep}',ep))
            self.db.fill(f'o{ep}',ep,f't{ep}',f,'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)',(ep,'UP',0.,-1.0))
        self.db.halt_check(); self.assertEqual(len(self.rows()),4)
        self.assertIsNone(self.db.get('halt'))

    def test_the_screen_still_shows_the_condition(self):
        self.db.halt_check()
        k=self.db.rolling()['kill']
        self.assertTrue(k['armed']); self.assertTrue(k['by_kind']['EF']['armed'])
        self.assertLess(k['unit_return_sum'],-3.0)

    def test_the_only_engine_halt_left_is_the_order_identity_stop(self):
        src=pathlib.Path(__file__).with_name('poly_core.py').read_text()
        sites=[l for l in src.splitlines() if "set('halt'" in l]
        self.assertEqual(len(sites),1,sites)
        self.assertIn('Order hash mismatch',sites[0])


class AttemptLoopIsPaperParity(unittest.TestCase):
    """REMAKE_PLAN §3a, 09-13. Live retried a venue reject but every retry first
    waited for the book's seq to CHANGE (poly_core.py:880) inside a 2 s budget,
    and a signed order was abandoned if the book ticked during the ~10 ms sign
    (:928). Paper takes the current book, sleeps 75 ms and fires again. 82 live
    orders produced 4 second attempts and 10 DEADLINEs; Task 76 priced the gap
    at 31 venue rejects worth +0.25/$1. Three edits; the signal and EV untouched.
    The order_plan(latest) re-check at :932 is now the only guard on a moved
    book, and test 3 pins that it still does its job.
    """
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=str(pathlib.Path(self.temp.name)/'t.db')
        self.db=Journal(self.path,'PAPER','abc'); self.books=BookCache(); self.books.apply(snapshot()); self.books.terms['up']=(.01,1,.07,1)
    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def test_retry_on_a_book_that_did_not_move(self):
        """The book does NOT tick between attempts. Old code: 1 order, then DEADLINE."""
        class RejectOnce(PaperBroker):
            calls=0
            async def post(self,s):
                self.calls+=1
                if self.calls==1: return {'rejected':'fak_not_filled'}
                return await super().post(s)
        async def run():
            ex=Executor(self.db,self.books,RejectOnce(self.books),budget_s=1.0)
            await ex.fire(epoch(),decision(),'up','c',10,decision)
            self.assertEqual(len(self.db.sql('SELECT * FROM orders')),2,'a second attempt must not need the book to tick')
        asyncio.run(run())

    def test_a_tick_during_signing_does_not_abandon_the_order(self):
        """Same ask re-applied during prepare(): seq changes, EV does not. Old code: 0 orders."""
        books=self.books
        class TickWhileSigning(PaperBroker):
            async def prepare(self,token,plan):
                books.apply(snapshot(ask=.4)); return await super().prepare(token,plan)
        async def run():
            ex=Executor(self.db,books,TickWhileSigning(books),budget_s=1.0)
            await ex.fire(epoch(),decision(),'up','c',10,decision)
            self.assertEqual(len(self.db.sql('SELECT * FROM orders')),1,'a tick during the sign must not throw the attempt away')
        asyncio.run(run())

    def test_a_tick_during_signing_that_breaks_ev_still_releases(self):
        """Ask jumps to .9 during prepare(): the :932 re-check must catch it as EV_CHANGED."""
        books=self.books
        class JumpWhileSigning(PaperBroker):
            async def prepare(self,token,plan):
                books.apply(snapshot(ask=.9)); return await super().prepare(token,plan)
        async def run():
            ex=Executor(self.db,books,JumpWhileSigning(books),budget_s=1.0)
            await ex.fire(epoch(),decision(),'up','c',10,decision)
            self.assertEqual(len(self.db.sql('SELECT * FROM orders')),0)
            # release() deletes the signals row so the candle can re-fire, and
            # records why in diagnostics - that is where the reason lives.
            rel=[json.loads(r[0]) for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%candle_rearmed%'")]
            self.assertEqual([r['after'] for r in rel],['EV_CHANGED'],'the moved-book guard is the EV re-check, not the seq gate')
        asyncio.run(run())

    def test_retry_waits_at_least_the_delay(self):
        ts=[]
        class RejectOnce(PaperBroker):
            async def post(self,s):
                ts.append(time.monotonic())
                if len(ts)==1: return {'rejected':'no orders found to match with FAK order'}
                return await super().post(s)
        async def run():
            ex=Executor(self.db,self.books,RejectOnce(self.books),budget_s=1.0)
            await ex.fire(epoch(),decision(),'up','c',10,decision)
            self.assertEqual(len(ts),2)
            self.assertGreaterEqual(ts[1]-ts[0],0.07,'paper waits 75 ms before the second shot')
        asyncio.run(run())

if __name__=='__main__':unittest.main(verbosity=2)
