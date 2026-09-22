"""12.21.0: master OFF = shadow paper fills, master ON = the venue, in ONE process.
Owner, 09-22: "when master off it's paper and when master on it's live, we don't have to set paper
or live from terminal ... if master off it's paper and if master on it's live it's that simple".
Run against poly_core.Executor / Journal / PaperBroker and poly_dashboard.Dashboard themselves."""
import asyncio, json, pathlib, tempfile, time, unittest
from types import SimpleNamespace
import poly_core as C
from poly_dashboard import Dashboard

def snap(ask=.4,qty=100.):
    return {'event_type':'book','asset_id':'up','timestamp':str(int(time.time()*1000)),
            'asks':[{'price':str(ask),'size':str(qty)},{'price':str(round(ask+.01,2)),'size':str(qty)}],
            'bids':[{'price':str(round(ask-.01,2)),'size':str(qty)}]}
def decision(): return {'fire':True,'side':'UP','p':.9,'threshold':0.,'features':{}}

class Venue(C.PaperBroker):
    """Stands in for LiveBroker: records every post; fills like paper so the journal gets a fill."""
    basis='VENUE_CONFIRMED_TRADE_AND_VENUE_FEE'
    def __init__(self,books,db): super().__init__(books,db); self.posts=0
    async def post(self,signed): self.posts+=1; return await super().post(signed)

class MasterRoutes(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=str(pathlib.Path(self.temp.name)/'j.db')
        self.db=C.Journal(self.path,'LIVE','abc'); self.books=C.BookCache(); self.books.apply(snap()); self.books.terms['up']=(.01,1,.07,1)
        self.venue=Venue(self.books,self.db); self.shadow=C.PaperBroker(self.books,self.db)
        self.ex=C.Executor(self.db,self.books,self.venue,budget_s=1.0,shadow=self.shadow)
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def fire(self,ep=None):
        asyncio.run(self.ex.fire(ep or int(time.time())-30,decision(),'up','c',10,decision))

    def test_master_off_goes_to_the_shadow_broker(self):
        self.db.set('master',False); self.fire()
        rows=self.db.sql('SELECT lane,status FROM orders'); self.assertEqual([tuple(r) for r in rows],[('PAPER','PENDING')])
        self.assertEqual(self.venue.posts,0,'nothing reached the venue')
        self.assertEqual(len(self.db.sql('SELECT * FROM fills')),1,'the shadow fill is journaled')
        asyncio.run(self.ex.reconcile()); self.assertEqual(self.db.sql('SELECT status FROM orders')[0][0],'FILLED')

    def test_master_on_goes_to_the_venue(self):
        self.db.set('master',True); self.fire()
        self.assertEqual(self.db.sql('SELECT lane FROM orders')[0][0],'LIVE'); self.assertEqual(self.venue.posts,1)

    def test_route_flips_at_the_next_fire(self):
        ep=int(time.time())-60; self.db.set('master',False); self.fire(ep=ep); self.db.set('master',True); self.fire(ep=ep+30)
        self.assertEqual([r[0] for r in self.db.sql('SELECT lane FROM orders ORDER BY epoch')],['PAPER','LIVE'])

    def test_shadow_may_top_up_live_never(self):
        seen=[]
        class Peek(C.PaperBroker):
            async def prepare(self,t,plan): seen.append(plan['max_shares']); return await super().prepare(t,plan)
        ex=C.Executor(self.db,self.books,Peek(self.books,self.db),budget_s=1.0,shadow=Peek(self.books,self.db))
        self.books.apply(snap(ask=.85)); self.books.terms['up']=(.01,5.0,0.,1.)
        d=dict(decision(),price_rule='lane_cap',max_ask=.9); ep=int(time.time())-60
        self.db.set('master',False); asyncio.run(ex.fire(ep,d,'up','c',3.0,lambda:d,kind='MAIN'))
        self.assertGreaterEqual(seen[-1]+1e-9,5.0,'shadow topped up to the 5-share minimum')
        self.db.set('master',True); asyncio.run(ex.fire(ep+30,d,'up','c',3.0,lambda:d,kind='MAIN'))
        self.assertEqual(len(seen),1,'live refused below the venue minimum instead of raising the stake')
        rel=[json.loads(r[0]) for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%order_plan_refused%'")]
        self.assertIn('below venue minimum',rel[-1]['error'])

    def test_grade_keeps_venue_and_shadow_pnl_apart(self):
        ep=int(time.time())-60; self.db.set('master',False); self.fire(ep)             # PAPER (shadow) EF fill
        self.db.set('master',True); self.db.reserve(ep,{'side':'UP'},'up','c','MAIN'); self.db.order('live1',ep,1,{'cap':.5},{},'MAIN','LIVE')
        self.db.fill('live1',ep,'f-live1',dict(shares=5.,spent=2.,fees=.05,price=.4),'VENUE'); self.db.order_status('live1','FILLED'); self.db.status(ep,'FILLED','MAIN')
        asyncio.run(self.ex.reconcile()); self.db.grade(ep,'UP')
        r=self.db.sql('SELECT payout,pnl,shadow_payout,shadow_pnl FROM results')[0]
        self.assertAlmostEqual(r['payout'],5.); self.assertAlmostEqual(r['pnl'],5.-2.05)
        paper=self.db.sql("SELECT sum(f.shares),sum(f.spent+f.fees) FROM fills f JOIN orders o ON o.id=f.order_id WHERE o.lane='PAPER'")[0]
        self.assertAlmostEqual(r['shadow_payout'],paper[0]); self.assertAlmostEqual(r['shadow_pnl'],paper[0]-paper[1])
        m=self.db.lane_metrics(); self.assertEqual((m['MAIN']['real']['n'],m['MAIN']['shadow']['n'],m['EF']['real']['n'],m['EF']['shadow']['n']),(1,0,0,1))
        self.assertAlmostEqual(self.db.metrics()['pnl'],5.-2.05,'realised pnl is the venue lane only')

    def test_combined_metrics_split_by_lane_not_flag(self):
        # 12.21.4: on a live journal with only shadow fills, real=0 / shadow=n and the shadow pnl is shown.
        ep=int(time.time())-60; self.db.set('master',False); self.fire(ep); asyncio.run(self.ex.reconcile()); self.db.grade(ep,'DOWN')
        real,shadow=self.db.metrics_for('LIVE'),self.db.metrics_for('PAPER')
        self.assertEqual((real['n'],shadow['n'],shadow['losses']),(0,1,1)); self.assertLess(shadow['pnl'],0); self.assertEqual(self.db.metrics()['pnl'],0.)
        ui=Dashboard.__new__(Dashboard); ui.db=self.db; ui.r=SimpleNamespace(a=SimpleNamespace(live=True))
        self.assertTrue(ui._shadow({}),'no lane on the row: the ROUTE decides, and master is off')
        self.assertIn("real=real_m['n'],shadow=shadow_m['n']",__import__('pathlib').Path(__file__).with_name('poly_dashboard.py').read_text())
    def test_reserve_counts_only_the_journal_lane(self):
        self.db.order('p1',1_000_000,1,{'budget':3.0},{},'EF','PAPER'); self.db.order('l1',1_000_000,1,{'budget':4.0},{},'EF','LIVE')
        self.assertAlmostEqual(self.db.reserve_detail()['total'],4.0)

    def test_paper_process_is_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            db=C.Journal(str(pathlib.Path(t)/'p.db'),'PAPER','abc'); ex=C.Executor(db,self.books,C.PaperBroker(self.books,db),budget_s=1.0)
            ep=int(time.time())-60; db.set('master',False); asyncio.run(ex.fire(ep,decision(),'up','c',10,decision))
            self.assertEqual(db.sql('SELECT lane FROM orders')[0][0],'PAPER'); asyncio.run(ex.reconcile()); db.grade(ep,'UP')
            r=db.sql('SELECT pnl,shadow_pnl FROM results')[0]; self.assertAlmostEqual(r['pnl'],r['shadow_pnl'])
            db.c.close()

class Controls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.db=C.Journal(str(pathlib.Path(self.temp.name)/'j.db'),'PAPER','abc')
        self.ui=Dashboard.__new__(Dashboard); self.ui.db=self.db
        self.ui.r=SimpleNamespace(a=SimpleNamespace(live=False),live_ready=False,cash=100.,cash_at=time.monotonic(),account_snapshot={},venue_state=None,error='')
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def test_allowed_no_longer_needs_master(self):
        self.db.set('master',False); self.db.set('ef_enabled',True); self.assertTrue(self.ui.allowed('EF'))
        self.db.set('ef_enabled',False); self.assertFalse(self.ui.allowed('EF'))
        self.db.set('ef_enabled',True); self.db.set('halt','x'); self.assertFalse(self.ui.allowed('EF'))
    def test_lane_label_follows_credentials_and_master(self):
        self.db.set('master',True); self.assertEqual(self.ui.lane_label(),'PAPER','no credentials: master has no effect')
        self.ui.r.a.live=True; self.assertEqual(self.ui.lane_label(),'LIVE')
        self.db.set('master',False); self.assertEqual(self.ui.lane_label(),'SHADOW')
    def test_venue_cash_gates_only_venue_orders(self):
        # 12.21.1: the runner's four cash checks are guarded by _routing_live(); a shadow order on a
        # live process with $1.65 in the wallet must still fire.
        import pathlib, re
        src=pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertEqual(len(re.findall(r'self\._routing_live\(\)',src)),5)   # 4 cash checks + the 12.21.2 decide-gate min_topup
        self.assertIn("if self._routing_live() and stake>max(0,(self.cash or 0)-reserved):",src)
        self.assertIn("if self._routing_live() and (self.cash is None or time.monotonic()-self.cash_at>=15):",src)
        import btc_model_v12_polymarket as E, poly_core as C
        r=E.PolyRunner.__new__(E.PolyRunner); r.a=SimpleNamespace(live=True); r.executor=C.Executor(self.db,C.BookCache(),C.PaperBroker(C.BookCache()),shadow=C.PaperBroker(C.BookCache()))
        self.db.set('master',False); self.assertFalse(r._routing_live()); self.db.set('master',True); self.assertFalse(r._routing_live(),'a PAPER journal never routes live')
    def test_decide_gate_prices_like_the_order_will_be_placed(self):
        # 12.21.2: the EF decide-stage EV gate passes min_topup = not routing live, so a $1 stake on a
        # shadow route is topped up to the 5-share minimum instead of dying as 'below venue minimum'.
        import pathlib
        src=pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertIn("plan=order_plan(q,terms,stake,dict(d,min_topup=not self._routing_live()),pad,",src)
        import poly_core as C
        q=dict(ask=.76,asks=[(.76,200.),(.77,200.)],age_ms=20.,seq=1); terms=(.01,5.0,0.,1.); d=dict(p=.95,threshold=0.)
        with self.assertRaises(ValueError): C.order_plan(q,terms,1.0,d,pad=1)                     # live: refused
        plan=C.order_plan(q,terms,1.0,dict(d,min_topup=True),pad=1); self.assertGreaterEqual(plan['max_shares']+1e-9,5.0)   # shadow: topped up
    def test_page_header_follows_the_route_not_the_flag(self):
        # 12.21.3: the owner's 15:56 screenshot read "PnL · LIVE" with master OFF - the page header was
        # rendered from the --live flag at page load. It now renders lane_label() and the JS keeps it live.
        import pathlib
        py=pathlib.Path(__file__).with_name('poly_dashboard.py').read_text(); html=pathlib.Path(__file__).with_name('dashboard_html.html').read_text()
        self.assertNotIn("('LIVE' if self.r.a.live else 'PAPER')",py); self.assertIn("' · v10 PnL · '+self.lane_label()",py)
        self.assertIn("text('buildStamp',live.build+",html)
        self.ui.r.a.live=True; self.db.set('master',False); self.assertEqual(self.ui.lane_label(),'SHADOW')
    def test_shadow_bankroll_is_the_shadow_ledger(self):
        # 12.22.0 (Zurich audit :154): with credentials and master OFF, sizing reads capital + shadow pnl.
        ui=Dashboard.__new__(Dashboard); ui.db=self.db; ui.r=SimpleNamespace(a=SimpleNamespace(live=True,capital=50.0),venue_state=dict(cash=1.65,open_value=0.0),cash=1.65)
        self.db.set('master',False); self.assertAlmostEqual(ui.equity(),50.0+self.db.metrics_for('PAPER')['pnl'])
        self.db.set('master',True); self.assertAlmostEqual(ui.equity(),1.65)
    def test_claim_status_and_live_venue_follow_the_lane(self):
        import pathlib
        src=pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text(); dsh=pathlib.Path(__file__).with_name('poly_dashboard.py').read_text()
        self.assertNotIn("'PAPER' if not self.a.live else 'NO_PAYOUT'",src); self.assertIn("'NO_PAYOUT' if _live_fill else 'PAPER'",src)
        self.assertIn("live_venue=bool(self.lane_label()=='LIVE' and vmetrics['n'])",dsh); self.assertNotIn("live_venue=bool(r.a.live",dsh)
    def test_shadow_flag_follows_the_order_lane(self):
        self.assertTrue(self.ui._shadow({'lane':'PAPER'})); self.assertFalse(self.ui._shadow({'lane':'LIVE'})); self.assertTrue(self.ui._shadow({}))

if __name__=='__main__': unittest.main()
