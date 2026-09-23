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
