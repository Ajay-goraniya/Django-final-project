"""12.19.0 fast path: one decision per attempt, control check instead of a second decide,
honest wire timing, tick-bounded retry, cached control reads, warm order transport.
Run against poly_core.Executor / Journal / PaperBroker themselves."""
import asyncio, json, pathlib, tempfile, time, unittest
import poly_core as C
from poly_live import LiveBroker

def snap(ask=.4,qty=100.):
    return {'event_type':'book','asset_id':'up','timestamp':str(int(time.time()*1000)),
            'asks':[{'price':str(ask),'size':str(qty)},{'price':str(round(ask+.01,2)),'size':str(qty)}],
            'bids':[{'price':str(round(ask-.01,2)),'size':str(qty)}]}
def decision(): return {'fire':True,'side':'UP','p':.9,'threshold':0.,'features':{}}

class FastPath(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=str(pathlib.Path(self.temp.name)/'j.db')
        self.db=C.Journal(self.path,'PAPER','abc'); self.books=C.BookCache(); self.books.apply(snap()); self.books.terms['up']=(.01,1,.07,1)
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def fire(self,broker=None,reassess=None,**kw):
        ex=C.Executor(self.db,self.books,broker or C.PaperBroker(self.books,self.db),budget_s=1.0,**kw)
        asyncio.run(ex.fire(int(time.time())-30,decision(),'up','c',10,reassess or decision)); return ex

    def test_one_reassess_per_attempt(self):
        calls=[0]
        def r(): calls[0]+=1; return decision()
        self.fire(reassess=r)
        self.assertEqual(len(self.db.sql('SELECT * FROM orders')),1); self.assertEqual(calls[0],1,'the second full decide is gone')

    def test_control_check_before_the_post_releases(self):
        ex=C.Executor(self.db,self.books,C.PaperBroker(self.books,self.db),budget_s=1.0); ex.allowed=lambda kind: False
        asyncio.run(ex.fire(int(time.time())-30,decision(),'up','c',10,decision))
        self.assertEqual(len(self.db.sql('SELECT * FROM orders')),0)
        rel=[json.loads(r[0])['after'] for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%candle_rearmed%'")]
        self.assertEqual(rel,['SIGNAL_CHANGED'])

    def test_allowed_receives_the_lane(self):
        seen=[]
        ex=C.Executor(self.db,self.books,C.PaperBroker(self.books,self.db),budget_s=1.0); ex.allowed=lambda kind: seen.append(kind) or True
        d=dict(decision(),price_rule='lane_cap',max_ask=.9)
        asyncio.run(ex.fire(int(time.time())-30,d,'up','c',10,lambda:d,kind='MAIN'))
        self.assertEqual(seen,['MAIN'])

    def test_wire_timing_is_recorded(self):
        ex=self.fire()
        t=json.loads(self.db.sql('SELECT timing_json FROM orders')[0][0])
        for k in ('fire_to_wire_ms','db_order_ms','fire_to_submit_ms','final_recheck_ms'): self.assertIn(k,t)
        self.assertGreaterEqual(t['fire_to_wire_ms'],t['fire_to_submit_ms'])
        st=ex.latency_stats(); self.assertIn('fire_to_wire_ms',st); self.assertIn('sign_mode',st); self.assertIn('keepalive_ms',st)

    def test_ev_recheck_on_the_moved_book_still_releases(self):
        books=self.books
        class Jump(C.PaperBroker):
            async def prepare(self,t,plan): books.apply(snap(ask=.95)); return await super().prepare(t,plan)
        self.fire(broker=Jump(books,self.db))
        self.assertEqual(len(self.db.sql('SELECT * FROM orders')),0)
        rel=[json.loads(r[0])['after'] for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%candle_rearmed%'")]
        self.assertEqual(rel,['EV_CHANGED'])

    def test_journal_is_wal_normal(self):
        self.assertEqual(self.db.c.execute('PRAGMA journal_mode').fetchone()[0].lower(),'wal')
        self.assertEqual(self.db.c.execute('PRAGMA synchronous').fetchone()[0],1)   # NORMAL

    def test_meta_cache_is_write_through_and_expires(self):
        self.db.set('ef_enabled',True); self.assertIs(self.db.get('ef_enabled'),True)
        self.db.set('ef_enabled',False); self.assertIs(self.db.get('ef_enabled'),False,'a write through set() is visible at once')
        self.db.set_many({'master':True}); self.assertIs(self.db.get('master'),True)
        # a write that bypasses set() is seen after META_TTL_S
        self.db.c.execute("INSERT OR REPLACE INTO meta VALUES('ef_enabled','true')"); self.db.c.commit()
        self.assertIs(self.db.get('ef_enabled'),False)
        self.db._meta_cache['ef_enabled']=(time.monotonic()-C.Journal.META_TTL_S-1,False)
        self.assertIs(self.db.get('ef_enabled'),True)
        self.assertEqual(self.db.get('never_set','dflt'),'dflt'); self.assertEqual(self.db.get('never_set','dflt2'),'dflt2')

    def test_transport_facts_are_reported_before_any_order(self):
        ex=C.Executor(self.db,self.books,C.PaperBroker(self.books,self.db)); st=ex.latency_stats()
        for k in ('sign_mode','keepalive_ms','keepalive_age_s'): self.assertIn(k,st)
        class B(C.PaperBroker): sign_mode='inline'; keepalive_ms=12.5; keepalive_at=time.monotonic()
        st=C.Executor(self.db,self.books,B(self.books,self.db)).latency_stats(); self.assertEqual((st['sign_mode'],st['keepalive_ms']),('inline',12.5))
    def test_paper_keepalive_is_a_noop(self):
        self.assertIsNone(asyncio.run(C.PaperBroker(self.books).keepalive()))

    def test_sign_mode_follows_the_eth_keys_backend(self):
        mode=LiveBroker.pick_sign_mode(); self.assertIn(mode,('inline','thread'))
        try:
            from eth_keys.backends import get_backend_class
            self.assertEqual(mode,'inline' if 'CoinCurve' in get_backend_class().__name__ else 'thread')
        except ImportError: self.assertEqual(mode,'thread')

    def _live(self,book_fails=False):
        from types import SimpleNamespace
        hits=[]
        class T:
            def __init__(s,name): s.name=name
            async def get_json(s,path):
                hits.append((s.name,path))
                if book_fails and s.name=='clob': raise ConnectionError('cold')
                return {}
        b=LiveBroker(self.books); b.client=SimpleNamespace(_ctx=SimpleNamespace(secure_clob=T('secure_clob'),clob=T('clob'))); return b,hits
    def test_keepalive_warms_the_order_and_the_book_transport(self):
        # 13.0.2: get_order_book (the retry's REST refresh) runs on `clob`, a separate pool from the POST's `secure_clob`
        b,hits=self._live(); ms=asyncio.run(b.keepalive())
        self.assertEqual(sorted(h[0] for h in hits),['clob','secure_clob']); self.assertIsNotNone(ms); self.assertIsNotNone(b.keepalive_book_ms)
        st=C.Executor(self.db,self.books,b).latency_stats(); self.assertIn('keepalive_book_ms',st); self.assertIn('loop',st)
    def test_hanging_book_transport_does_not_hide_the_order_keepalive(self):
        from types import SimpleNamespace
        class T:
            def __init__(s,d): s.d=d
            async def get_json(s,path): await asyncio.sleep(s.d); return {}
        b=LiveBroker(self.books); b.KEEPALIVE_BOOK_S=0.05
        b.client=SimpleNamespace(_ctx=SimpleNamespace(secure_clob=T(0.01),clob=T(10)))
        self.assertIsNotNone(asyncio.run(asyncio.wait_for(b.keepalive(),1))); self.assertIsNotNone(b.keepalive_at); self.assertIsNone(b.keepalive_book_ms)
    def test_loop_kind_off_the_loop_reads_the_recorded_kind(self):
        old=C.LOOP_KIND; C.LOOP_KIND='uvloop'
        try: self.assertEqual(C.loop_kind(),'uvloop')
        finally: C.LOOP_KIND=old
    def test_book_transport_failure_does_not_fail_the_order_keepalive(self):
        b,_=self._live(book_fails=True); self.assertIsNotNone(asyncio.run(b.keepalive())); self.assertIsNone(b.keepalive_book_ms)
    def test_attempt1_fire_to_wire_is_reported_apart_from_retries(self):
        ex=C.Executor(self.db,self.books,C.PaperBroker(self.books,self.db))
        ex.latency_samples=[dict(attempt=1,fire_to_wire_ms=float(i),total_attempt_ms=5.) for i in range(1,11)]+[dict(attempt=2,fire_to_wire_ms=500.,total_attempt_ms=600.)]
        a1=ex.latency_stats()['fire_to_wire_attempt1']; self.assertEqual((a1['n'],a1['max_ms'],a1['p90_ms']),(10,10.,9.))
    def test_loop_kind(self):
        self.assertIsNone(C.loop_kind()); self.assertEqual(asyncio.run(self._k()),'asyncio')
        try: import uvloop
        except ImportError: return
        self.assertEqual(uvloop.run(self._k()),'uvloop')
    async def _k(self): return C.loop_kind()
    def test_fast_report_names_every_fast_package(self):
        import btc_model_v12_polymarket as E; r=E.fast_report()
        for k in ('uvloop=','sign=','coincurve=','http2='): self.assertIn(k,r)

    def test_retry_tick_wait_is_bounded(self):
        self.assertEqual(C.Executor.RETRY_TICK_WAIT_S,0.1); self.assertFalse(hasattr(C.Executor,'RETRY_DELAY_S'))

if __name__=='__main__': unittest.main()

class DecideLog(unittest.TestCase):
    """13.0.4: decide_log is opt-in, batched, and records every pass - fire or not - with both asks."""
    def setUp(self):
        import btc_model_v12_polymarket as E
        self.temp=tempfile.TemporaryDirectory(); self.db=C.Journal(str(pathlib.Path(self.temp.name)/'j.db'),'PAPER','abc')
        r=E.PolyRunner.__new__(E.PolyRunner); r.db=self.db; r.books=C.BookCache(); r.books.apply(snap(.41)); self.ep=int(time.time()//300)*300
        r.market={self.ep:('up','dn')}; r.quote_age_s=lambda: 60.; r.DECIDE_LOG_BATCH=3; self.r=r
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def d(self,fire): return {'fire':fire,'side':'UP','p':.62,'ask':.41,'ev':.2,'reason':'x','features':{'b':2.,'a':1.,'ts_ms':5}}
    def test_off_by_default(self):
        for i in range(5): self.r._decide_log(1000+i,self.ep,self.d(False))
        self.assertEqual(self.db.sql('SELECT COUNT(*) FROM decide_log')[0][0],0)
    def test_on_logs_every_pass_batched(self):
        self.db.set('decide_log',True)
        for i in range(2): self.r._decide_log(1000+250*i,self.ep,self.d(i==1))
        self.assertEqual(self.db.sql('SELECT COUNT(*) FROM decide_log')[0][0],0,'held until the batch fills')
        self.r._decide_log(1500,self.ep,{'fire':False,'reason':'Warming up'})
        rows=self.db.sql('SELECT ts_ms,fire,up_ask,dn_ask,feats FROM decide_log ORDER BY ts_ms')
        self.assertEqual([r[1] for r in rows],[0,1,0]); self.assertEqual(rows[0][2],.41); self.assertIsNone(rows[0][3])
        self.assertEqual(json.loads(rows[0][4]),[1.,2.]); self.assertIsNone(rows[2][4])
        self.assertEqual(self.db.get('decide_log_features'),['a','b'])
    def test_fast_passes_keep_four_rows_a_second_but_every_fire(self):
        self.db.set('decide_log',True); self.r.DECIDE_LOG_BATCH=1
        for i in range(50): self.r._decide_log(1000+20*i,self.ep,self.d(i==7))      # 50 passes in 1 s, one fire
        rows=[tuple(r) for r in self.db.sql('SELECT ts_ms,fire FROM decide_log ORDER BY ts_ms')]
        self.assertIn((1140,1),rows); self.assertLessEqual(len(rows),6)

class EventDecide(unittest.TestCase):
    """13.1.0: decide_mode 'event' wakes a fast EF pass on fresh data; full passes (lanes, tape, diagnostics) stay 0.25 s.
    'poll' (default) is the old loop: a full pass every 0.25 s."""
    def run_loop(self,mode,pokes_per_s=0,secs=1.0):
        import btc_model_v12_polymarket as E
        temp=tempfile.TemporaryDirectory(); db=C.Journal(str(pathlib.Path(temp.name)/'j.db'),'PAPER','abc')
        if mode: db.set('decide_mode',mode)
        r=E.PolyRunner.__new__(E.PolyRunner); r.db=db; calls=[]
        async def once(full=True): calls.append((time.monotonic(),full))
        r._decide_once=once
        async def main():
            t=asyncio.create_task(r.decide_loop())
            end=time.monotonic()+secs
            while time.monotonic()<end:
                await asyncio.sleep(1/pokes_per_s if pokes_per_s else secs)
                if pokes_per_s: r._poke()
            t.cancel(); await asyncio.gather(t,return_exceptions=True)
        asyncio.run(main()); db.c.close(); temp.cleanup(); return calls
    def test_poll_is_the_old_loop(self):
        c=self.run_loop(None,secs=1.0)
        self.assertTrue(all(f for _,f in c)); self.assertTrue(4<=len(c)<=6,len(c))
    def test_event_mode_reacts_but_keeps_full_cadence(self):
        c=self.run_loop('event',pokes_per_s=200,secs=1.0)
        full=[t for t,f in c if f]; fast=[t for t,f in c if not f]
        self.assertTrue(4<=len(full)<=6,len(full))                                   # lanes/tape still ~4/s
        self.assertGreater(len(fast),10)                                              # EF sees fresh data often (~16/s at the 50 ms floor)
        gaps=np.diff(sorted(t for t,_ in c)); self.assertGreaterEqual(gaps.min(),C_MIN_GAP-0.005)   # never faster than the floor
    def test_event_mode_without_data_falls_back_to_polling(self):
        c=self.run_loop('event',pokes_per_s=0,secs=1.0)
        self.assertTrue(all(f for _,f in c)); self.assertTrue(4<=len(c)<=6,len(c))
    def test_min_gap_dial(self):
        import btc_model_v12_polymarket as E
        temp=tempfile.TemporaryDirectory(); db=C.Journal(str(pathlib.Path(temp.name)/'j.db'),'PAPER','abc')
        r=E.PolyRunner.__new__(E.PolyRunner); r.db=db
        self.assertEqual(r.decide_min_gap_s(),.05)
        for v,want in ((20,.02),(1,.01),(5000,.25),('x',.05)): db.set('decide_min_gap_ms',v); self.assertAlmostEqual(r.decide_min_gap_s(),want)
        db.set('decide_min_gap_ms',100); c=[]
        async def once(full=True): c.append(time.monotonic())
        r._decide_once=once; db.set('decide_mode','event')
        async def main():
            t=asyncio.create_task(r.decide_loop()); end=time.monotonic()+.6
            while time.monotonic()<end: await asyncio.sleep(.002); r._poke()
            t.cancel(); await asyncio.gather(t,return_exceptions=True)
        asyncio.run(main()); db.c.close(); temp.cleanup()
        self.assertGreaterEqual(np.diff(c).min(),.095); self.assertLessEqual(len(c),8)
    def test_poke_before_loop_is_harmless(self):
        import btc_model_v12_polymarket as E
        r=E.PolyRunner.__new__(E.PolyRunner); r._poke()
import numpy as np
import btc_model_v12_polymarket as _E; C_MIN_GAP=_E.PolyRunner.DECIDE_MIN_GAP_S
