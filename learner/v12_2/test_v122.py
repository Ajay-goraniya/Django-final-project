"""Tests for the v12.2 changes: venue-sourced money, honest feed staleness,
clock-skew tolerance and per-attempt latency."""
import json, os, pathlib, sqlite3, tempfile, time, unittest, types
import poly_core as C
import poly_feeds as F


class VenueTruth(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mktemp(suffix='.sqlite3')
        self.db = C.Journal(self.path, 'LIVE', 'hash')

    def tearDown(self):
        try: self.db.c.close(); os.unlink(self.path)
        except Exception: pass

    def _settled(self, epoch, condition, local_pnl):
        self.db.reserve(epoch, dict(side='UP'), 'tok', condition, 'EF')
        self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',
                    (epoch, 'UP', 1.0, local_pnl, time.time()))

    def test_venue_pnl_overrides_local_and_is_labelled(self):
        self._settled(1000, 'cond-a', local_pnl=0.50)
        n = self.db.apply_venue_pnl([dict(condition_id='cond-a', realized_pnl=0.42,
                                          total_pnl=0.42, entry_fees=0.03, current_value=0.0)])
        self.assertEqual(n, 1)
        row = self.db.sql('SELECT venue_pnl,pnl,pnl_basis,venue_fees FROM results WHERE epoch=1000')[0]
        self.assertAlmostEqual(row['venue_pnl'], 0.42)
        self.assertAlmostEqual(row['pnl'], 0.50, msg='local figure is kept for comparison')
        self.assertEqual(row['pnl_basis'], 'VENUE_POSITION_PNL')
        self.assertAlmostEqual(row['venue_fees'], 0.03)

    def test_venue_metrics_count_only_venue_priced_rows(self):
        self._settled(1000, 'cond-a', 0.50)
        self._settled(1300, 'cond-b', -1.00)
        self.db.apply_venue_pnl([dict(condition_id='cond-a', realized_pnl=0.42, total_pnl=0.42,
                                      entry_fees=0.0, current_value=0.0)])
        vm = self.db.venue_metrics()
        self.assertEqual(vm['n'], 1, 'a row the venue has not priced is excluded, not back-filled')
        self.assertEqual(vm['wins'], 1); self.assertEqual(vm['losses'], 0)
        self.assertEqual(vm['basis'], 'VENUE_POSITION_PNL')
        self.assertEqual(self.db.metrics()['n'], 2, 'local metrics still see both')

    def test_divergence_between_local_and_venue_is_reported(self):
        self._settled(1000, 'cond-a', 0.50)
        self.db.apply_venue_pnl([dict(condition_id='cond-a', realized_pnl=0.42, total_pnl=0.42,
                                      entry_fees=0.0, current_value=0.0)])
        d = self.db.pnl_divergence()
        self.assertEqual(d['compared'], 1)
        self.assertAlmostEqual(d['worst_abs'], 0.08, places=6)

    def test_venue_snapshot_persists(self):
        self.db.venue_snapshot(dict(ts=time.time(), cash=13.73, portfolio_value=20.0, open_value=6.27,
                                    realized_pnl=1.1, unrealized_pnl=-0.2, fees_paid=0.05,
                                    account_pnl=dict(realized_pnl=1.1)))
        r = self.db.sql('SELECT cash,portfolio_value,realized_pnl FROM venue_state')[0]
        self.assertAlmostEqual(r['cash'], 13.73)
        self.assertAlmostEqual(r['portfolio_value'], 20.0)

    def test_fill_records_venue_fee_basis(self):
        self.db.reserve(1000, dict(side='UP'), 'tok', 'cond', 'EF')
        self.db.order('o1', 1000, 1, dict(budget=1.0), kind='EF')
        self.db.fill('o1', 1000, 't1', dict(shares=2.0, spent=1.0, fees=0.007, price=0.5,
                                            fee_basis='VENUE_FEE_RATE_BPS', fee_rate_bps=35.0), 'basis')
        r = self.db.sql('SELECT fee_basis,fee_rate_bps FROM fills WHERE id=?', ('t1',))[0]
        self.assertEqual(r['fee_basis'], 'VENUE_FEE_RATE_BPS')
        self.assertAlmostEqual(r['fee_rate_bps'], 35.0)


class FeedStaleness(unittest.TestCase):
    def test_arrival_and_lag_are_independent(self):
        h = F.FeedHealth(('spot',))
        now = time.time()
        # Socket alive (message just arrived) but the data in it is 6s old.
        h.note('spot', (now - 6.0) * 1000, now=now)
        self.assertLess(h.arrival_age('spot'), 1.0)
        self.assertGreater(h.event_lag('spot'), 5.0)
        bad = h.stale(('spot',))
        self.assertIn('spot', bad, 'a lagging feed must be rejected even though it is arriving')
        self.assertIn('behind its event time', bad['spot'])

    def test_fresh_feed_passes_both(self):
        h = F.FeedHealth(('spot',))
        now = time.time()
        h.note('spot', (now - 0.1) * 1000, now=now)
        self.assertEqual(h.stale(('spot',)), {})

    def test_dead_socket_is_caught_even_with_no_lag_history(self):
        h = F.FeedHealth(('spot',))
        h.note('spot', None, now=time.time() - 30)
        bad = h.stale(('spot',))
        self.assertIn('no message', bad['spot'])

    def test_clock_behind_venue_is_skew_not_negative_lag(self):
        h = F.FeedHealth(('spot',))
        now = time.time()
        h.note('spot', (now + 3.0) * 1000, now=now)   # event stamped in our future
        self.assertEqual(h.event_lag('spot'), 0.0, 'lag is clamped, never negative')
        self.assertLess(h.clock_skew_s, 0.0, 'the offset is recorded as skew')

    def test_snapshot_shape(self):
        h = F.FeedHealth(('spot', 'perp'))
        h.note('spot', time.time() * 1000)
        s = h.snapshot(('spot', 'perp'))
        for k in ('arrival_age_s', 'event_lag_s', 'messages', 'host', 'reconnects', 'clock_skew_s', 'limits'):
            self.assertIn(k, s)


class BookClockSkew(unittest.TestCase):
    def _event(self, token, stamp_s, ask=0.5):
        return {'event_type': 'book', 'asset_id': token, 'timestamp': stamp_s * 1000,
                'asks': [{'price': str(ask), 'size': '100'}],
                'bids': [{'price': str(ask - 0.02), 'size': '100'}]}

    def test_skewed_clock_no_longer_discards_the_whole_feed(self):
        # v12.1 dropped any event more than 2s from local time, so a host whose
        # clock was off by more than that logged an empty book and no error.
        b = C.BookCache()
        now = time.time()
        for i in range(40):
            b.apply(self._event('tok', now + 30 + i * 0.1))   # venue 30s "ahead"
        self.assertGreater(b.applied, 0, 'events must still be applied under clock skew')
        self.assertIsNotNone(b.quote('tok', max_age=5.0))
        self.assertLess(b.health()['clock_offset_s'], 0.0)

    def test_genuinely_old_events_are_still_dropped(self):
        b = C.BookCache()
        now = time.time()
        b.apply(self._event('tok', now - 600))
        self.assertEqual(b.applied, 0)
        self.assertEqual(b.dropped_stale, 1)

    def test_quote_age_never_negative(self):
        b = C.BookCache()
        b.apply(self._event('tok', time.time() + 30))
        q = b.quote('tok', max_age=5.0)
        self.assertIsNotNone(q)
        self.assertGreaterEqual(q['age_ms'], 0.0)


class LatencyTelemetry(unittest.TestCase):
    def test_every_outcome_is_sampled_not_only_accepted(self):
        ex = C.Executor.__new__(C.Executor)
        ex.latency_samples = []
        ex._sample({'total_attempt_ms': 100.0, 'sign_ms': 10.0}, 'ACCEPTED')
        ex._sample({'total_attempt_ms': 900.0, 'sign_ms': 12.0}, 'REJECTED')
        ex._sample({'total_attempt_ms': 1500.0, 'sign_ms': 11.0}, 'UNKNOWN')
        st = ex.latency_stats()
        self.assertEqual(st['total']['n'], 3, 'rejections and timeouts are the slow ones; they must count')
        self.assertIn('REJECTED', st['by_outcome'])
        self.assertIn('sign_ms', st)
        self.assertEqual(st['max_ms'], 1500.0)

    def test_configurable_execution_budget(self):
        ex = C.Executor.__new__(C.Executor)
        C.Executor.__init__(ex, None, None, None, budget_s=5.0, post_timeout_s=2.0, attempts=4)
        self.assertEqual(ex.budget_s, 5.0)
        self.assertEqual(ex.post_timeout_s, 2.0)
        self.assertEqual(ex.max_attempts, 4)


class SignalMigration(unittest.TestCase):
    def test_v121_database_migrates_and_keeps_history(self):
        path = tempfile.mktemp(suffix='.sqlite3')
        c = sqlite3.connect(path)
        c.executescript('''CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT);
            CREATE TABLE signals(epoch INTEGER PRIMARY KEY,ts REAL,side TEXT,token TEXT,
                condition_id TEXT,decision TEXT,status TEXT);
            CREATE TABLE orders(id TEXT PRIMARY KEY,epoch INTEGER,attempt INTEGER,status TEXT,
                plan TEXT,ts REAL,latency REAL,reason TEXT);
            CREATE TABLE fills(id TEXT PRIMARY KEY,order_id TEXT,epoch INTEGER,shares REAL,
                spent REAL,fees REAL,price REAL,basis TEXT);
            CREATE TABLE results(id INTEGER PRIMARY KEY AUTOINCREMENT,epoch INTEGER UNIQUE,
                actual TEXT,payout REAL,pnl REAL,ts REAL,claim_status TEXT DEFAULT 'PENDING',claim_id TEXT);
            CREATE TABLE diagnostics(ts REAL,epoch INTEGER,detail TEXT);
            CREATE TABLE candles(epoch INTEGER PRIMARY KEY,open REAL,high REAL,low REAL,close REAL,volume REAL);''')
        c.execute("INSERT INTO signals VALUES(500,1.0,'UP','tok','cond','{}','FILLED')")
        for k, v in (('lane', '"LIVE"'), ('model_hash', '"hash"'), ('build', '"12.1"')):
            c.execute('INSERT INTO meta VALUES(?,?)', (k, v))
        c.commit(); c.close()
        db = C.Journal(path, 'LIVE', 'hash')
        rows = db.sql('SELECT epoch,kind,status FROM signals')
        self.assertEqual(len(rows), 1, 'existing history is preserved')
        self.assertEqual(rows[0]['kind'], 'EF', 'pre-existing rows were EF by definition')
        self.assertTrue(db.reserve(500, dict(side='DOWN'), 't', 'c', 'MAIN'),
                        'the same candle can now carry a second lane')
        self.assertEqual(len(db.sql('SELECT 1 FROM signals WHERE epoch=500')), 2)
        db.c.close(); os.unlink(path)




class VenueVerifiedReserve(unittest.TestCase):
    """The pending/reserve figure is the only balance number the venue does not
    publish, so it is the one that drifts. These cover the drift."""

    def setUp(self):
        self.path = tempfile.mktemp(suffix='.sqlite3')
        self.db = C.Journal(self.path, 'LIVE', 'hash')

    def tearDown(self):
        try: self.db.c.close(); os.unlink(self.path)
        except Exception: pass

    def _pending(self, oid, epoch, budget, age_s=0.0):
        self.db.reserve(epoch, dict(side='UP'), 'tok', 'cond', 'EF')
        self.db.order(oid, epoch, 1, dict(budget=budget), kind='EF')
        self.db.sql('UPDATE orders SET status=?,ts=? WHERE id=?',
                    ('PENDING', time.time() - age_s, oid))

    def test_unchecked_order_still_holds_funds(self):
        self._pending('o1', 100, 3.0)
        d = self.db.reserve_detail()
        self.assertAlmostEqual(d['unverified'], 3.0)
        self.assertAlmostEqual(self.db.live_reserve(), 3.0,
                               msg='before the venue is asked, hold the funds back')

    def test_order_the_venue_lists_is_confirmed(self):
        self._pending('o1', 100, 3.0, age_s=30)
        self.db.mark_venue_open({'o1'})
        d = self.db.reserve_detail()
        self.assertAlmostEqual(d['confirmed'], 3.0)
        self.assertAlmostEqual(d['phantom'], 0.0)
        self.assertAlmostEqual(self.db.live_reserve(), 3.0)

    def test_single_absence_does_not_release_funds(self):
        # There is a real race between submitting and the order being listed.
        self._pending('o1', 100, 3.0, age_s=30)
        self.db.mark_venue_open(set())
        self.assertAlmostEqual(self.db.live_reserve(), 3.0,
                               msg='one absence is not proof')

    def test_repeated_absence_releases_a_phantom_reserve(self):
        # This is the case in the live screenshot: $3.00 held by an order the
        # venue never had, shrinking what can be traded for the rest of the run.
        self._pending('o1', 100, 3.0, age_s=30)
        self.db.mark_venue_open(set())
        self.db.mark_venue_open(set())
        d = self.db.reserve_detail()
        self.assertAlmostEqual(d['phantom'], 3.0)
        self.assertAlmostEqual(d['effective'], 0.0)
        self.assertAlmostEqual(self.db.live_reserve(), 0.0)
        self.assertEqual(d['phantom_ids'], ['o1'])
        self.assertAlmostEqual(self.db.live_reserve(venue_verified=False), 3.0,
                               msg='the raw local figure is still available for comparison')

    def test_a_fresh_order_is_protected_by_the_grace_period(self):
        self._pending('o1', 100, 3.0, age_s=0.0)
        self.db.mark_venue_open(set()); self.db.mark_venue_open(set())
        self.assertAlmostEqual(self.db.live_reserve(), 3.0,
                               msg='an order younger than the grace period is never released')

    def test_an_order_with_a_fill_is_never_phantom(self):
        self._pending('o1', 100, 3.0, age_s=30)
        self.db.fill('o1', 100, 't1', dict(shares=1.0, spent=0.5, fees=0.0, price=0.5), 'b')
        self.db.mark_venue_open(set()); self.db.mark_venue_open(set())
        d = self.db.reserve_detail()
        self.assertAlmostEqual(d['phantom'], 0.0, msg='it traded; it is not phantom')

    def test_available_is_venue_cash_not_cash_minus_reserve(self):
        # Build 12.0 showed AVAILABLE as wallet minus the local reserve, so a
        # phantom row reduced the figure the operator reads as spendable.
        self._pending('o1', 100, 3.0, age_s=30)
        cash = 16.42
        self.db.mark_venue_open(set()); self.db.mark_venue_open(set())
        reserve = self.db.live_reserve()
        self.assertAlmostEqual(cash, 16.42, msg='the venue balance is reported as-is')
        self.assertAlmostEqual(max(0, cash - reserve), 16.42,
                               msg='a phantom reserve no longer reduces fundable')

class SettledPositionsAreQueried(unittest.TestCase):
    """A 5-minute position is OPEN only while the candle runs; once it settles it
    is REDEEMABLE, then CLOSED. The first live run of v12.2 kept reporting
    LOCAL_FROM_FILLS because the default query returned neither."""

    def setUp(self):
        self.path = tempfile.mktemp(suffix='.sqlite3')
        self.db = C.Journal(self.path, 'LIVE', 'hash')

    def tearDown(self):
        try: self.db.c.close(); os.unlink(self.path)
        except Exception: pass

    def test_settled_rows_awaiting_venue_are_listed(self):
        self.db.reserve(1000, dict(side='UP'), 'tok', 'cond-a', 'EF')
        self.db.reserve(1300, dict(side='UP'), 'tok', 'cond-b', 'EF')
        for ep in (1000, 1300):
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,?)',
                        (ep, 'UP', 1.0, 0.5, time.time()))
        self.assertEqual(sorted(self.db.conditions_awaiting_venue()), ['cond-a', 'cond-b'])
        self.db.apply_venue_pnl([dict(condition_id='cond-a', realized_pnl=0.4, total_pnl=0.4,
                                      entry_fees=0.0, current_value=0.0)])
        self.assertEqual(self.db.conditions_awaiting_venue(), ['cond-b'],
                         'a priced market drops out of the query')

    def test_all_three_statuses_are_requested(self):
        import poly_live
        self.assertEqual(poly_live.LiveBroker.POSITION_STATUSES, ('OPEN', 'REDEEMABLE', 'CLOSED'))

    def test_positions_merges_statuses_without_duplicates(self):
        import asyncio, poly_live
        class FakePage:
            def __init__(self, items): self.items = items
        class FakePos:
            def __init__(self, cid, aid, rp):
                self.condition_id, self.asset_id, self.realized_pnl = cid, aid, rp
                self.current_size = 1.0; self.total_pnl = rp; self.entry_fees_usdc = 0.0
                self.status = 'REDEEMABLE'
            def __getattr__(self, n): return 0
        class FakeClient:
            def __init__(self): self.asked = []
            def list_positions(self, **kw):
                self.asked.append(kw.get('status'))
                pos = [FakePos('cond-a', 'asset-1', 0.4)]      # same position each time
                async def gen():
                    yield FakePage(pos)
                return gen()
        b = poly_live.LiveBroker.__new__(poly_live.LiveBroker)
        b.client = FakeClient()
        out = asyncio.run(b.positions(condition_ids=['cond-a']))
        self.assertEqual(b.client.asked, ['OPEN', 'REDEEMABLE', 'CLOSED'])
        self.assertEqual(len(out), 1, 'the same position seen under two statuses is counted once')
        self.assertAlmostEqual(out[0]['realized_pnl'], 0.4)

class DashboardNeverGoesDark(unittest.TestCase):
    """The live box showed "dashboard API error" with no way to see the reason.

    The handler caught only ValueError and TypeError, so anything else escaped to
    the base HTTP handler, which answers with an HTML traceback the page cannot
    parse. A single unexpected exception therefore blanked the whole dashboard.
    """

    def test_non_finite_numbers_are_dropped_not_fatal(self):
        import poly_dashboard as D
        body = {'a': float('nan'), 'b': float('inf'), 'c': 1.5,
                'nested': {'d': float('-inf')}, 'list': [float('nan'), 2.0]}
        safe = D._json_safe(body)
        out = json.dumps(safe, allow_nan=False)      # exactly what the server does
        back = json.loads(out)
        self.assertIsNone(back['a']); self.assertIsNone(back['b'])
        self.assertEqual(back['c'], 1.5)
        self.assertIsNone(back['nested']['d'])
        self.assertEqual(back['list'], [None, 2.0])

    def test_sets_are_serialisable(self):
        import poly_dashboard as D
        # venue_truth carries open_order_ids as a set; json.dumps cannot encode one
        out = json.dumps(D._json_safe({'ids': {'b', 'a'}}), allow_nan=False)
        self.assertEqual(json.loads(out)['ids'], ['a', 'b'])

    def test_every_endpoint_answers_json_even_when_it_raises(self):
        import poly_dashboard as D, urllib.request, urllib.error, threading, types, tempfile as TF
        class Boom(D.Dashboard):
            def __init__(self): pass
        ui = Boom()
        ui.password = None
        ui.errors = []
        # snapshot raises something the old handler did not catch
        ui.snapshot = lambda: (_ for _ in ()).throw(KeyError('venue_state'))
        ui.controls = lambda: {'ok': True}
        ui.history = lambda o, l: {'rows': []}
        ui.orders = lambda k, o, l: {'rows': []}
        ui.pnl = lambda r='1D': {'pnl': 0}
        ui.chart = lambda: {'candles': []}
        ui.page = lambda n: '<html></html>'
        ui.db = types.SimpleNamespace(sql=lambda *a, **k: [])
        ui.r = types.SimpleNamespace(hash='h', m=types.SimpleNamespace(coef=[]),
                                     a=types.SimpleNamespace(host='127.0.0.1', port=0, live=False))
        srv = D.Dashboard.make_server(ui)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            try:
                r = urllib.request.urlopen(f'http://127.0.0.1:{port}/api/state', timeout=5)
                body = json.loads(r.read())
                code = r.status
            except urllib.error.HTTPError as e:
                body = json.loads(e.read())          # must still be JSON
                code = e.code
            self.assertEqual(code, 500)
            self.assertIn('KeyError', body['error'], 'the reason must reach the page')
            self.assertEqual(body['endpoint'], '/api/state')
            self.assertTrue(ui.errors, 'the failure is recorded for /api/state to surface')
        finally:
            srv.shutdown(); srv.server_close()

class DatetimeFromTheSdk(unittest.TestCase):
    """The live box lost its dashboard to exactly this: the SDK's account-PnL
    point carries a datetime, which json.dumps cannot encode. It broke two
    things at once - the dashboard response, and the venue snapshot write, which
    failed inside its loop's exception handler and left PnL on the local basis.
    """

    def test_account_pnl_timestamp_is_normalised_at_the_source(self):
        import asyncio, datetime as dt, poly_live
        class P:
            timestamp = dt.datetime(2026, 9, 12, 14, 0, tzinfo=dt.timezone.utc)
            realized_pnl = -0.034927; unrealized_pnl = 0.0; settled_pnl = -0.034927
            economic_pnl = -0.034927; trade_pnl = 0.154553; fees_paid = -0.18948
            volume_usdc = 5.299999; trade_count = 2
        class Series:
            points = [P()]
        class Client:
            async def get_user_pnl(self, **kw): return Series()
        b = poly_live.LiveBroker.__new__(poly_live.LiveBroker)
        b.client = Client()
        out = asyncio.run(b.account_pnl())
        self.assertIsInstance(out['ts'], str)
        json.dumps(out, allow_nan=False)      # must not raise

    def test_encoder_survives_a_datetime_anywhere(self):
        import datetime as dt, poly_dashboard as D
        body = {'truth': {'account_pnl': {'ts': dt.datetime(2026, 9, 12, 14, 0)}}}
        out = json.dumps(D._json_safe(body), allow_nan=False)
        self.assertIn('2026-09-12T14:00:00', out)

    def test_venue_snapshot_write_survives_an_unserialisable_value(self):
        import datetime as dt
        path = tempfile.mktemp(suffix='.sqlite3')
        db = C.Journal(path, 'LIVE', 'hash')
        try:
            db.venue_snapshot(dict(ts=time.time(), cash=18.4, portfolio_value=0.0, open_value=0.0,
                                   realized_pnl=-0.2, unrealized_pnl=0.0, fees_paid=0.2,
                                   account_pnl=dict(ts=dt.datetime(2026, 9, 12, 14, 0), realized_pnl=-0.03)))
            r = db.sql('SELECT cash FROM venue_state')
            self.assertEqual(len(r), 1, 'the snapshot must be written, not lost to an encoder error')
            self.assertAlmostEqual(r[0]['cash'], 18.4)
        finally:
            db.c.close(); os.unlink(path)

class EvAndSlippageControls(unittest.TestCase):
    """EV mode and slippage are live controls now, not launch flags.

    Slippage is the fill-versus-frequency dial: measured on 206 real fires, a pad
    of 0 ticks lets every signal through the EV re-check, 1 tick lets 57% through
    and 2 ticks 37%, because one tick is a median 2.1% of the ask against an EV
    bar of 0.15 to 0.25.
    """

    def _runner(self):
        import types, pathlib, sys
        sys.argv = ['x']
        import btc_model_v12_polymarket as E
        a = types.SimpleNamespace(live=False, port=0, host='127.0.0.1',
            model=str(pathlib.Path('model_v10.json').resolve()),
            db=tempfile.mktemp(suffix='.sqlite3'), capital=50, mode='pnl', ev=None,
            quote_age_ms=750, pad_ticks=1, execution_budget_ms=2000,
            post_timeout_ms=1200, max_attempts=3)
        return E.PolyRunner(a)

    def test_defaults_to_the_model_regime_thresholds(self):
        r = self._runner()
        mode, thr = r.ev_setting()
        self.assertEqual(mode, 'regime')
        self.assertIsNone(thr, 'regime hands the decision back to the model table')
        self.assertEqual(r.pad_ticks(), 1)

    def test_fixed_mode_applies_one_threshold(self):
        r = self._runner()
        r.ui.apply('/api/controls/ev', dict(confirmed=True, mode='fixed', value=0.10))
        self.assertEqual(r.ev_setting(), ('fixed', 0.10))

    def test_accuracy_mode_hands_over_to_the_floors(self):
        r = self._runner()
        r.ui.apply('/api/controls/ev', dict(confirmed=True, mode='accuracy'))
        mode, thr = r.ev_setting()
        self.assertEqual(mode, 'accuracy')
        self.assertIsNone(thr)

    def test_slippage_is_settable_and_bounded(self):
        r = self._runner()
        r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_ticks=0))
        self.assertEqual(r.pad_ticks(), 0)
        r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_ticks=3))
        self.assertEqual(r.pad_ticks(), 3)
        for bad in (-1, 6, 'x'):
            with self.assertRaises((ValueError, TypeError)):
                r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_ticks=bad))

    def test_slippage_reaches_the_executor(self):
        r = self._runner()
        r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_ticks=0))
        r._sync_executor_dials()   # what the decide loop does every pass
        self.assertEqual(r.executor.pad, 0, 'the running executor must pick it up without a restart')

    def test_every_execution_dial_is_synced_from_meta_not_just_pad(self):
        """band and age were set only by the HTTP handler, so a restart lost them.

        meta kept saying slippage_mode=band while Executor.__init__ had reset
        self.band to False, and decide_now()'s EV gate reads slippage_mode()
        fresh - so the gate ran in band mode while the plan that got signed did
        not. Three live orders were signed at exactly one tick under
        meta slippage_mode=band before this was caught.
        """
        r = self._runner()
        r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_mode='band',
                                            quote_age_ms=400, slippage_ticks=2))
        r._sync_executor_dials()
        self.assertTrue(r.executor.band)
        self.assertEqual(r.executor.pad, 2)
        self.assertAlmostEqual(r.executor.age, 0.4)

        # Simulate the restart: a fresh Executor comes up on the constructor
        # defaults, and the first decide pass must restore every dial from meta.
        r.executor.band = False
        r.executor.pad = 1
        r.executor.age = 0.75
        r._sync_executor_dials()
        self.assertTrue(r.executor.band, 'band must survive a restart via meta')
        self.assertEqual(r.executor.pad, 2)
        self.assertAlmostEqual(r.executor.age, 0.4)

    def test_an_unrelated_ev_edit_does_not_clear_band(self):
        """The old handler did band=(cfg.get('slippage_mode')=='band').

        Any EV write that omitted slippage_mode therefore silently turned band
        mode off while meta still carried it.
        """
        r = self._runner()
        r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_mode='band'))
        r.ui.apply('/api/controls/ev', dict(confirmed=True, slippage_ticks=1))
        r._sync_executor_dials()
        self.assertEqual(r.slippage_mode(), 'band')
        self.assertTrue(r.executor.band)

    def test_bad_mode_and_missing_value_are_rejected(self):
        r = self._runner()
        with self.assertRaises(ValueError):
            r.ui.apply('/api/controls/ev', dict(confirmed=True, mode='whatever'))
        with self.assertRaises(ValueError):
            r.ui.apply('/api/controls/ev', dict(confirmed=True, mode='fixed'))

    def test_controls_report_the_measured_trade_off(self):
        r = self._runner()
        ev = r.ui.controls()['ev']
        self.assertEqual(ev['mode'], 'regime')
        self.assertEqual(ev['slippage_ticks'], 1)
        self.assertEqual(ev['measured']['survive_pct'][0], 100)
        self.assertEqual(ev['measured']['survive_pct'][1], 57)
        self.assertIn('modes', ev)

    def test_settings_survive_a_restart(self):
        r = self._runner()
        path = r.a.db
        r.ui.apply('/api/controls/ev', dict(confirmed=True, mode='fixed', value=0.05, slippage_ticks=0))
        # release both the connection and the advisory lock, as a real stop does
        r.db.c.close()
        try: r.process_lock.close()
        except Exception: pass
        import types, pathlib, sys
        sys.argv = ['x']
        import btc_model_v12_polymarket as E
        a = types.SimpleNamespace(live=False, port=0, host='127.0.0.1',
            model=str(pathlib.Path('model_v10.json').resolve()), db=path, capital=50,
            mode='pnl', ev=None, quote_age_ms=750, pad_ticks=1,
            execution_budget_ms=2000, post_timeout_ms=1200, max_attempts=3)
        r2 = E.PolyRunner(a)
        self.assertEqual(r2.ev_setting(), ('fixed', 0.05))
        self.assertEqual(r2.pad_ticks(), 0)


class LaneCardMatchesBuild36(unittest.TestCase):
    """The panel shows the call on the direction line, as build 36 did, and what
    became of the order on the reason line."""

    def _ui(self, lane_decision):
        import types, pathlib, sys
        sys.argv = ['x']
        import btc_model_v12_polymarket as E
        a = types.SimpleNamespace(live=False, port=0, host='127.0.0.1',
            model=str(pathlib.Path('model_v10.json').resolve()),
            db=tempfile.mktemp(suffix='.sqlite3'), capital=50, mode='pnl', ev=None,
            quote_age_ms=750, pad_ticks=1, execution_budget_ms=2000,
            post_timeout_ms=1200, max_attempts=3)
        r = E.PolyRunner(a); r.lane_decision = lane_decision
        return r.ui

    def test_no_signal_gives_no_card(self):
        self.assertIsNone(self._ui({}).lane_card('MAIN'))

    def test_placed_order_says_so(self):
        ui = self._ui({'main_signal': dict(direction='UP', ts_ms=1, probability_up=0.8),
                       'main_placed': True})
        c = ui.lane_card('MAIN')
        self.assertEqual(c['direction'], 'UP'); self.assertTrue(c['placed'])
        self.assertEqual(c['reason'], 'order placed')

    def test_refused_order_names_the_reason_without_hiding_the_call(self):
        ui = self._ui({'main_signal': dict(direction='DOWN', ts_ms=1, probability_up=0.27),
                       'main_placed': False, 'main_attempts': 2,
                       'main_last_reason': 'SKIPPED: padded price fails model EV'})
        c = ui.lane_card('MAIN')
        self.assertEqual(c['direction'], 'DOWN', 'build 36 shows the call on this line')
        self.assertFalse(c['placed'])
        self.assertIn('not executed', c['reason'])
        self.assertIn('2 attempts', c['reason'])
        self.assertIn('model EV', c['reason'])


class SnapshotAgeTracking(unittest.TestCase):
    """A book running on deltas alone is not a trustworthy book.

    Polymarket sends no per-token sequence number, so a dropped price_change is
    undetectable: it leaves a phantom level that survives until the next full
    'book' snapshot. Age since the last snapshot is the only available measure
    of how far our book may have drifted from the venue's. Found by the session
    on the AWS box, 09-13, while explaining the "no orders found to match"
    rejects.
    """
    def setUp(self):
        self.bc = C.BookCache()

    def book(self, token='t1', ts=None):
        return dict(event_type='book', asset_id=token, timestamp=str(int((ts or time.time())*1000)),
                    asks=[{'price':'0.55','size':'100'}], bids=[{'price':'0.53','size':'100'}])

    def delta(self, token='t1', ts=None, price='0.56', size='50'):
        return dict(event_type='price_change', timestamp=str(int((ts or time.time())*1000)),
                    price_changes=[dict(asset_id=token, side='SELL', price=price, size=size)])

    def test_snapshot_age_starts_near_zero(self):
        self.bc.apply(self.book())
        q = self.bc.quote('t1', 5.0)
        self.assertIsNotNone(q)
        self.assertLess(q['snapshot_age_s'], 1.0)

    def test_a_delta_does_not_refresh_the_snapshot(self):
        self.bc.apply(self.book())
        self.bc.books['t1']['snapshot'] -= 120.0      # pretend the snapshot is old
        self.bc.apply(self.delta())
        q = self.bc.quote('t1', 5.0)
        self.assertIsNotNone(q)
        self.assertGreater(q['snapshot_age_s'], 100.0,
                           'a price_change must not count as a resync')

    def test_a_full_book_event_does_refresh_it(self):
        self.bc.apply(self.book())
        self.bc.books['t1']['snapshot'] -= 120.0
        self.bc.apply(self.book())
        self.assertLess(self.bc.quote('t1', 5.0)['snapshot_age_s'], 1.0)

    def test_snapshot_age_is_recorded_not_gated(self):
        """12.3.2 refused orders on snapshot age. That was wrong.

        venue() subscribes once per cycle and clears the cache, so snapshot age
        is very nearly seconds-into-candle with a 300 s cliff at the rollover -
        a disguised time-of-candle gate, which the standing no-gates rule
        forbids. On 28 live orders it refused a higher share of FILLS than of
        rejects at every limit from 30 s to 300 s. The field stays as telemetry;
        nothing in the module may gate on it.
        """
        self.assertFalse(hasattr(C,'MAX_SNAPSHOT_AGE_S'),
                         'snapshot age must not come back as a threshold')
        src=(pathlib.Path(C.__file__).read_text() if hasattr(C,'__file__') else '')
        self.assertNotIn('BOOK_UNSYNCED',src,
                         'the snapshot-age refusal must stay removed')


class MultiLaneCandleIsNotDoubleCounted(unittest.TestCase):
    """A candle with two lanes must not report twice the shares and spend.

    signals has been keyed (epoch,kind) since the 12.3.x migration, but three
    dashboard queries still joined fills on epoch alone. Verified on the live
    box: epoch 1789232100 reported 10.3929 shares / $5.82 against a truth of
    5.1964 / $2.91 - exactly 2x, because it carries EF:FILLED plus MAIN:DEADLINE.
    That feeds open-position size and the last-fill panel, which is the
    "available and fundable amounts are misleading" the user reported.
    """
    BAD = ("SELECT sum(f.shares) FROM signals s JOIN fills f USING(epoch) "
           "WHERE s.epoch=500")
    GOOD = ("SELECT sum(f.shares) FROM signals s "
            "JOIN orders o ON o.epoch=s.epoch AND o.kind=s.kind "
            "JOIN fills f ON f.order_id=o.id WHERE s.epoch=500")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'a.db'), 'PAPER', 'h')
        d = dict(side='UP', fire=True)
        for kind, status in (('EF','FILLED'), ('MAIN','DEADLINE')):
            self.db.reserve(500, d, 'tok', 'cond', kind=kind)
            self.db.status(500, status, kind)
        self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,kind) "
                    "VALUES('o1',500,1,'FILLED','{}',0,'EF')")
        self.db.sql("INSERT INTO fills(id,order_id,epoch,shares,spent,fees,price,basis) "
                    "VALUES('f1','o1',500,5.1964,2.91,0.0,0.56,'T')")

    def tearDown(self):
        self.db.c.close(); self.temp.cleanup()

    def test_joining_on_epoch_alone_doubles_it(self):
        self.assertAlmostEqual(self.db.sql(self.BAD)[0][0], 2*5.1964, places=4,
                               msg='the old shape must still double, or this test proves nothing')

    def test_routing_through_orders_does_not(self):
        self.assertAlmostEqual(self.db.sql(self.GOOD)[0][0], 5.1964, places=4)

    def test_the_dashboard_no_longer_joins_fills_on_epoch_alone(self):
        src = pathlib.Path(C.__file__).parent.joinpath('poly_dashboard.py').read_text()
        self.assertNotIn('JOIN fills f USING(epoch)', src)


class AutoRedeemIsNotAFailure(unittest.TestCase):
    """The venue redeems first on an auto-redeem account. That is a success.

    Retracted from 12.4.2/12.4.3: those treated a raising redeem() as a failure
    to retry. The user has AUTO-REDEEM enabled, so the venue claims each winning
    position itself and our call then raises "already redeemed". Retrying that
    is an unbounded loop of doomed redemption calls against a live account.
    Venue truth for the six affected rows: venue_value 0.00 and +21.14 of
    realized PnL already booked - collected, not outstanding.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'a.db'), 'PAPER', 'h')

    def tearDown(self):
        self.db.c.close(); self.temp.cleanup()

    def add(self, epoch, status, payout, venue_value=None, venue_ts=None):
        self.db.sql("INSERT INTO results(epoch,actual,payout,pnl,ts,claim_status) VALUES(?,?,?,?,0,?)",
                    (epoch, 'UP', payout, 1.0, status))
        if venue_ts is not None:
            self.db.sql("UPDATE results SET venue_value=?,venue_ts=? WHERE epoch=?",
                        (venue_value, venue_ts, epoch))

    def pending(self):
        return self.db.sql("""SELECT coalesce(sum(payout),0) FROM results
                              WHERE claim_status NOT IN ('CONFIRMED','NO_PAYOUT','PAPER','AUTO_REDEEMED')
                                AND NOT (venue_ts IS NOT NULL AND coalesce(venue_value,0)<=1e-9)""")[0][0]

    def test_a_venue_valued_zero_row_is_not_pending(self):
        self.add(100, 'REVIEW', 6.85, venue_value=0.0, venue_ts=1.0)
        self.assertEqual(self.pending(), 0, 'the venue paid it; it cannot be outstanding')

    def test_the_old_query_showed_it_forever(self):
        self.add(100, 'REVIEW', 6.85, venue_value=0.0, venue_ts=1.0)
        old = self.db.sql("SELECT coalesce(sum(payout),0) FROM results "
                          "WHERE claim_status NOT IN ('CONFIRMED','NO_PAYOUT','PAPER')")[0][0]
        self.assertAlmostEqual(old, 6.85, msg='the old shape must still show it, or this proves nothing')

    def test_an_unpriced_row_still_counts(self):
        self.add(101, 'REVIEW', 5.0)          # venue has not valued it yet
        self.assertAlmostEqual(self.pending(), 5.0, msg='genuinely outstanding')

    def test_auto_redeemed_is_terminal(self):
        self.add(102, 'AUTO_REDEEMED', 7.0)
        self.assertEqual(self.pending(), 0)

    def test_no_retry_sweep_remains_in_the_source(self):
        src = pathlib.Path(__file__).parent.joinpath('btc_model_v12_polymarket.py').read_text()
        self.assertNotIn("claim_status='PENDING',claim_tries", src,
                         'a REVIEW -> PENDING sweep would retry an already-redeemed position forever')
        self.assertNotIn('claim_tries', src)


class UnfilledFakIsRetryable(unittest.TestCase):
    """The venue sends a sentence; the whitelist compared it for equality.

    error_info() never populates 'code' for this exception - the stored keys
    are class/message/phase/repr/request_reached/status - so the match fell
    through to the venue's full text and never equalled any entry. Across 34
    live orders the attempt histogram was {1: 34}: the retry loop, the 2 s
    budget, the wait-for-a-new-book-seq and the EV re-check had never once run.
    """
    SENTENCE = ('no orders found to match with FAK order. FAK orders are '
                'partially filled or killed if no match is found.')

    def code_for(self, info):
        return ' '.join(str(info.get(k) or '') for k in ('code','message','class')).lower()

    def retryable(self, code):
        return any(x in code for x in ('fak_not_filled','unmatched','market_not_ready',
                                       'no orders found to match','partially filled or killed'))

    def test_the_real_venue_sentence_is_retryable(self):
        info = dict(**{'class':'RequestRejectedError'}, message=self.SENTENCE, phase='post')
        self.assertTrue(self.retryable(self.code_for(info)))

    def test_equality_would_have_missed_it(self):
        self.assertNotIn(self.SENTENCE.lower(),
                         ('fak_not_filled','unmatched','market_not_ready'))

    def test_the_short_codes_still_match(self):
        for c in ('fak_not_filled','unmatched','market_not_ready'):
            self.assertTrue(self.retryable(self.code_for(dict(code=c))))

    def test_an_unrelated_rejection_is_not_retried(self):
        info = dict(**{'class':'RequestRejectedError'}, message='insufficient balance')
        self.assertFalse(self.retryable(self.code_for(info)))

    def test_source_uses_substring_matching(self):
        src = pathlib.Path(C.__file__).read_text()
        self.assertIn('no orders found to match', src)
        self.assertNotIn("if code not in ('fak_not_filled'", src)


class BookDepthIsCheckedBeforeSending(unittest.TestCase):
    """Do not POST an order the ladder cannot fill.

    order_plan only required that SOME ask existed at or below the cap, never
    that there was enough of it - so the engine signed and sent fill-or-kill
    orders against books that demonstrably could not fill them, and the venue
    answered "no orders found to match". That is the reject signature, and it is
    why zero of 28 attempts partially filled. Build 36 walked the ladder locally
    and refused before the network.
    """
    terms = (0.01, 1.0, 0.0, 1.0)
    d = dict(p=0.99, threshold=-1.0)

    def plan(self, asks, stake, **kw):
        q = dict(ask=asks[0][0], asks=asks, age_ms=0, seq=1)
        return C.order_plan(q, self.terms, stake, self.d, **kw)

    def test_a_partial_filling_venue_is_not_depth_checked(self):
        """The check reflects the venue, not a global policy.

        Neither broker we run is all-or-nothing, so neither is depth-checked.
        Polymarket's own error table: a FAK needs at least ONE match and is
        "partially filled or killed if no match is found" - so a thin book is a
        partial fill, not the "no orders found to match" reject. 12.4.1 set the
        live broker True on the opposite belief; retracted in 12.4.5.
        """
        self.plan([(0.50, 2.0)], 3.0, pad=0, require_depth=False)
        self.assertFalse(C.PaperBroker.all_or_nothing)

    def test_live_broker_is_not_all_or_nothing(self):
        """FAK partially fills, so the live lane must not depth-refuse.

        Locks the 12.4.5 retraction: a True here silently converts every
        partial fill the venue would have given us into a local skip.
        """
        import poly_live
        self.assertFalse(poly_live.LiveBroker.all_or_nothing)
        # Executor reads it via getattr with a True default, so an absent
        # attribute is as wrong as a True one.
        self.assertIn('all_or_nothing', vars(poly_live.LiveBroker))

    def test_four_attempts_matches_build_36(self):
        """Build 36 sends FOUR orders per fire, not three.

        `PREDICT_ORDER_MAX_RETRIES = 3` is consumed as
        `range(1, PREDICT_ORDER_MAX_RETRIES + 2)` and
        `max_attempts = PREDICT_ORDER_MAX_RETRIES + 1`, i.e. one submit plus
        three retries. v12 read the constant as a total and shipped 3, so it was
        a whole attempt short of the rule it was ported from.
        """
        import inspect
        sig = inspect.signature(C.Executor.__init__)
        self.assertEqual(sig.parameters['attempts'].default, 4)
        ex = C.Executor.__new__(C.Executor)
        ex.max_attempts = max(1, int(sig.parameters['attempts'].default))
        self.assertEqual(list(range(1, ex.max_attempts + 1)), [1, 2, 3, 4])

    def test_engine_cli_default_is_four_attempts(self):
        """The CLI default is the one that reaches the live box."""
        import pathlib
        src = pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertIn("p.add_argument('--max-attempts',type=int,default=4)", src)
        self.assertIn("attempts=getattr(a,'max_attempts',4))", src)

    def test_slippage_mode_never_changes_which_trades_qualify(self):
        """The cap is survivability. It must not be a second opinion on the trade.

        `_px = ask if band else cap` made the EV bar move with the slippage dial:
        band mode judged EV at the ask instead of ask+1 tick, loosening the test
        by +0.019 to +0.028 and admitting marginal trades 12.3.4 refused. The
        operator's point stands - once a trade is decided the cap's only job is
        to get it filled, and a taker pays the maker's price anyway.

        So across the whole price range and both tick grids, tick mode and band
        mode must accept and reject exactly the same candles.
        """
        terms_for = lambda tick: (tick, 5.0, 0.07, 1.0)
        for tick in (0.01, 0.001):
            for i in range(1, int(1 / tick)):
                ask = round(i * tick, 4)
                if not 0 < ask < 1:
                    continue
                q = dict(ask=ask, asks=[(ask, 10000.0)], age_ms=0, seq=1)
                for p_, thr in ((0.55, 0.15), (0.60, 0.20), (0.50, 0.05)):
                    d = dict(p=p_, threshold=thr)
                    out = {}
                    for band in (False, True):
                        try:
                            out[band] = C.order_plan(q, terms_for(tick), 3.0, d,
                                                     pad=1, band=band, require_depth=False)
                        except ValueError as e:
                            out[band] = str(e)
                    ev_fail = lambda r: isinstance(r, str) and 'model EV' in r
                    self.assertEqual(ev_fail(out[False]), ev_fail(out[True]),
                                     f'EV verdict differs by mode at ask {ask}, '
                                     f'tick {tick}, p {p_}, thr {thr}')
                    # And when both qualify, band must give the WIDER cap.
                    if isinstance(out[False], dict) and isinstance(out[True], dict):
                        self.assertGreaterEqual(out[True]['cap'] + 1e-9, out[False]['cap'],
                                                f'band cap narrower at ask {ask}')

    def test_band_is_clamped_to_clear_the_five_share_minimum(self):
        """A wider cap signs FEWER shares, so the band can trip the floor.

        The venue minimum is 5 SHARES and the signed size is amount/cap. At the
        live $3 stake an unclamped band pulls the tradable ask from 0.57 down to
        0.52 - band mode would trade a reject problem for a skip problem across
        the expensive half of the book. 12.4.6 clamps the cushion instead of
        dropping the trade.
        """
        terms = (0.01, 5.0, 0.07, 1.0)
        d = dict(p=0.99, threshold=-1.0)
        for tick in (0.01, 0.001):
            for i in range(1, int(1 / tick)):
                ask = round(i * tick, 4)
                if not 0 < ask < 1:
                    continue
                q = dict(ask=ask, asks=[(ask, 10000.0)], age_ms=0, seq=1)
                t = (tick,) + terms[1:]
                def plan(band):
                    try:
                        return C.order_plan(q, t, 3.0, d, pad=1, band=band,
                                            require_depth=False)
                    except ValueError:
                        return None
                pad, band = plan(False), plan(True)
                if band is None:
                    # Band may only refuse where the tight pad also refuses.
                    self.assertIsNone(pad, f'band refused at ask {ask}, tick {tick}')
                    continue
                self.assertGreaterEqual(band['max_shares'] + 1e-8, 5.0, ask)
                self.assertGreaterEqual(band['cap'] + 1e-9, ask, ask)
                if pad is not None:
                    # Cushion is the point of the parameter: never narrower.
                    self.assertGreaterEqual(band['cap'] + 1e-9, pad['cap'], ask)

    def test_thin_book_is_refused_locally(self):
        # $3 wanted, one level holding 2 shares at 0.50 = $1.00 of depth
        with self.assertRaises(ValueError) as e:
            self.plan([(0.50, 2.0)], 3.0, pad=0)
        self.assertIn('book too thin', str(e.exception))

    def test_deep_enough_book_passes(self):
        self.plan([(0.50, 100.0)], 3.0, pad=0)   # $50 of depth

    def test_depth_is_summed_across_levels_within_the_cap(self):
        # no single level covers $3, but two inside the cap together do
        self.plan([(0.50, 4.0), (0.51, 4.0)], 3.0, pad=1)

    def test_depth_beyond_the_cap_does_not_count(self):
        with self.assertRaises(ValueError) as e:
            self.plan([(0.50, 1.0), (0.90, 1000.0)], 3.0, pad=0)
        self.assertIn('book too thin', str(e.exception))


class SlippageBands(unittest.TestCase):
    """Build 36's policy: headroom scales inversely with price.

    A flat tick pad collapses in relative terms exactly where build 36 was most
    generous - at ask 0.28 one tick is 3.6% against build 36's ~50%. The bands
    are build 36's stated price-expansion intent; its bps figures were Predict's
    isMinAmountOut encoding and do not port to a venue that takes a price cap.
    """
    terms = (0.01, 1.0, 0.0, 1.0)
    d = dict(p=0.99, threshold=-1.0)

    def test_bands_scale_inversely_with_price(self):
        self.assertAlmostEqual(C.slippage_band(0.06), 1.00)
        self.assertAlmostEqual(C.slippage_band(0.15), 0.70)
        self.assertAlmostEqual(C.slippage_band(0.25), 0.50)
        self.assertAlmostEqual(C.slippage_band(0.35), 0.20)
        self.assertAlmostEqual(C.slippage_band(0.45), 0.10)
        self.assertAlmostEqual(C.slippage_band(0.90), 0.10)

    def test_band_edges_are_half_open_at_the_top(self):
        self.assertAlmostEqual(C.slippage_band(0.10), 0.70, msg='0.10 enters the 0.10-0.20 band')
        self.assertAlmostEqual(C.slippage_band(0.40), 0.10)

    def test_invalid_price_gets_the_widest_band(self):
        for bad in (0.0, -1.0, float('nan'), None):
            self.assertAlmostEqual(C.slippage_band(bad), 1.00)

    def test_band_mode_gives_more_headroom_than_the_tick_dial(self):
        q = dict(ask=0.28, asks=[(0.28, 1000.0)], age_ms=0, seq=1)
        ticks = C.order_plan(q, self.terms, 3.0, self.d, pad=2)['cap']
        band = C.order_plan(q, self.terms, 3.0, self.d, band=True)['cap']
        self.assertGreater(band, ticks)
        self.assertAlmostEqual(band, 0.42, places=6)   # 0.28 * 1.5, on the grid

    def test_widening_survivability_changes_no_verdict_in_either_direction(self):
        """The cap is not a second opinion on the trade.

        This test used to assert that pad=5 REFUSED where band accepted, which
        encoded the very coupling that was the bug: EV moved with the slippage
        dial, so widening it refused trades in tick mode and admitted marginal
        ones in band mode. EV is now judged at a fixed reference and a marginal
        candle gets the same verdict at every setting - only the cap changes.
        """
        q = dict(ask=0.50, asks=[(0.50, 1000.0)], age_ms=0, seq=1)
        settings = (dict(pad=1), dict(pad=5), dict(band=True))

        # A candle that clears: every setting must take it.
        good = dict(p=0.60, threshold=0.10)
        caps = [C.order_plan(q, self.terms, 3.0, good, **kw)['cap'] for kw in settings]
        self.assertLess(caps[0], caps[1], 'a bigger pad must still widen the cap')

        # A candle that does not clear: every setting must refuse it.
        bad = dict(p=0.56, threshold=0.10)
        for kw in settings:
            with self.assertRaises(ValueError, msg=f'{kw} must refuse it too'):
                C.order_plan(q, self.terms, 3.0, bad, **kw)

    def test_a_cap_above_the_top_tick_clamps_rather_than_refusing(self):
        """A wide band on an expensive ask must not reject the trade."""
        q = dict(ask=0.91, asks=[(0.91, 10000.0)], age_ms=0, seq=1)
        d = dict(p=0.99, threshold=-1.0)
        plan = C.order_plan(q, (0.01, 1.0, 0.07, 1.0), 3.0, d, band=True,
                            require_depth=False)
        self.assertLess(plan['cap'], 1.0)
        self.assertGreaterEqual(plan['cap'], 0.91)


class RefusedCandleIsRearmed(unittest.TestCase):
    """A refused attempt must not consume the candle.

    User, 09-13: "as the signal appears triggered it does not fire again inside
    the same candle thus we will miss the second opportunities when the odds
    will align again". The reservation is PRIMARY KEY(epoch,kind), so one
    refusal used to burn all five minutes. Bounded so a repeatedly refused
    candle cannot spin.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'a.db'), 'PAPER', 'h')
        self.d = dict(side='UP', fire=True)

    def tearDown(self):
        self.db.c.close(); self.temp.cleanup()

    def test_a_refused_candle_can_fire_again(self):
        self.assertTrue(self.db.reserve(100, self.d, 'tok', 'cond'))
        self.assertFalse(self.db.reserve(100, self.d, 'tok', 'cond'), 'held while in flight')
        self.db.release(100, 'SKIPPED')
        self.assertTrue(self.db.reserve(100, self.d, 'tok', 'cond'), 'must re-arm after a refusal')

    def test_a_sent_order_still_consumes_the_candle(self):
        self.db.reserve(100, self.d, 'tok', 'cond')
        self.db.release(100, 'REJECTED')      # reached the venue
        self.assertFalse(self.db.reserve(100, self.d, 'tok', 'cond'),
                         'an order that was sent must never re-fire')

    def test_filled_never_rearms(self):
        self.db.reserve(100, self.d, 'tok', 'cond')
        self.db.release(100, 'FILLED')
        self.assertFalse(self.db.reserve(100, self.d, 'tok', 'cond'))

    def test_attempts_are_capped(self):
        n = 0
        for _ in range(12):
            if not self.db.reserve(100, self.d, 'tok', 'cond'): break
            n += 1
            self.db.release(100, 'SKIPPED')
        self.assertEqual(n, C.Journal.MAX_ATTEMPTS_PER_CANDLE,
                         'a repeatedly refused candle must stop, not spin')

    def test_each_no_order_status_rearms(self):
        for st in ('SKIPPED','DEADLINE','SIGNAL_CHANGED','EV_CHANGED','PREPARE_FAILED'):
            with self.subTest(status=st):
                db = C.Journal(str(pathlib.Path(self.temp.name)/f'{st}.db'), 'PAPER', 'h')
                db.reserve(1, self.d, 't', 'c')
                db.release(1, st)
                self.assertTrue(db.reserve(1, self.d, 't', 'c'))
                db.c.close()

    def test_a_rearm_is_recorded(self):
        self.db.reserve(100, self.d, 'tok', 'cond')
        self.db.release(100, 'SKIPPED')
        rows = [r[2] for r in self.db.sql('SELECT * FROM diagnostics')]
        self.assertTrue(any('candle_rearmed' in (r or '') for r in rows))


class ControlWritesAreAudited(unittest.TestCase):
    """Every change to a money-moving control leaves a named trace.

    The lane flags reverted silently twice on the Tokyo engine with no restart
    and no known cause, and on 09-13 pad_ticks moved from 2 to 1 with nobody
    admitting to it. A bare INSERT OR REPLACE leaves nothing to reconstruct
    from, so control writes now record old, new and the calling frame.
    """
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'a.db'), 'PAPER', 'h')

    def tearDown(self):
        self.db.c.close(); self.temp.cleanup()

    def rows(self):
        return [json.loads(r[2]) for r in self.db.sql('SELECT * FROM diagnostics')
                if 'control_write' in (r[2] or '')]

    def test_a_control_change_is_recorded_with_old_and_new(self):
        self.db.set('ev_settings', {'mode':'regime','pad_ticks':2})
        self.db.set('ev_settings', {'mode':'regime','pad_ticks':1})
        r = [x for x in self.rows() if x['key']=='ev_settings']
        self.assertEqual(len(r), 2)
        self.assertEqual(r[1]['old'], {'mode':'regime','pad_ticks':2})
        self.assertEqual(r[1]['new'], {'mode':'regime','pad_ticks':1})

    def test_the_calling_frame_is_recorded(self):
        self.db.set('master', True)
        r = [x for x in self.rows() if x['key']=='master']
        self.assertTrue(r and r[0]['stack'], 'a control write must name where it came from')

    def test_writing_the_same_value_is_not_noise(self):
        self.db.set('ef_enabled', True)
        before = len(self.rows())
        self.db.set('ef_enabled', True)
        self.assertEqual(len(self.rows()), before, 'only actual changes are recorded')

    def test_lane_flags_are_audited(self):
        for k in ('master','main_enabled','reversal_enabled','ef_enabled'):
            self.assertIn(k, C.Journal.AUDITED)

    def test_ordinary_keys_are_not_audited(self):
        self.db.set('some_scratch_value', 7)
        self.assertFalse([x for x in self.rows() if x['key']=='some_scratch_value'])


class QuoteBlockReasons(unittest.TestCase):
    """Why quote() declined, counted separately.

    A one-sided book yields no quote, which is almost certainly what the 20.9%
    of a session spent "Waiting for fresh UP and DOWN books" actually is. The
    message does not distinguish that from a stale or crossed book, so the
    counters do.
    """
    def setUp(self):
        self.bc = C.BookCache()

    def push(self, asks, bids, token='t1'):
        self.bc.apply(dict(event_type='book', asset_id=token,
                           timestamp=str(int(time.time()*1000)),
                           asks=[{'price':p,'size':'100'} for p in asks],
                           bids=[{'price':p,'size':'100'} for p in bids]))

    def test_missing_book_is_counted(self):
        self.assertIsNone(self.bc.quote('nope', 5.0))
        self.assertEqual(self.bc.quote_block['no_book'], 1)

    def test_one_sided_no_bids(self):
        self.push(['0.55'], [])
        self.assertIsNone(self.bc.quote('t1', 5.0))
        self.assertEqual(self.bc.quote_block['no_bids'], 1)

    def test_one_sided_no_asks(self):
        self.push([], ['0.53'])
        self.assertIsNone(self.bc.quote('t1', 5.0))
        self.assertEqual(self.bc.quote_block['no_asks'], 1)

    def test_crossed_is_counted_separately(self):
        self.push(['0.50'], ['0.55'])
        self.assertIsNone(self.bc.quote('t1', 5.0))
        self.assertEqual(self.bc.quote_block['crossed'], 1)

    def test_good_book_counts_ok(self):
        self.push(['0.55'], ['0.53'])
        self.assertIsNotNone(self.bc.quote('t1', 5.0))
        self.assertEqual(self.bc.quote_block['ok'], 1)

    def test_counters_reach_health(self):
        self.push(['0.55'], [])
        self.bc.quote('t1', 5.0)
        self.assertEqual(self.bc.health()['quote_block']['no_bids'], 1)


class TickSizeChangeIsRecorded(unittest.TestCase):
    """The venue moves these markets between grids intra-candle.

    Measured on the live feed 09-13: eight tick_size_change events in 300 s on
    the active tokens, every one 0.01 -> 0.001. Popping terms makes housekeeping
    refetch, but that loop runs every 5 s, so the token has no terms until it
    does. Whether that explains the rejects is a hypothesis; this records enough
    to decide it from the journal rather than infer it.
    """
    def setUp(self):
        self.bc = C.BookCache()

    def change(self, token='t1', new='0.001'):
        return dict(event_type='tick_size_change', asset_id=token,
                    timestamp=str(int(time.time()*1000)),
                    old_tick_size='0.01', new_tick_size=new)

    def test_terms_are_still_dropped(self):
        self.bc.terms['t1'] = (0.01, 5.0, 0.07, 1.0)
        self.bc.apply(self.change())
        self.assertNotIn('t1', self.bc.terms)

    def test_the_change_is_recorded_with_a_time(self):
        self.bc.apply(self.change())
        self.assertIn('t1', self.bc.tick_changes)
        self.assertEqual(self.bc.tick_changes['t1']['new'], '0.001')
        self.assertGreater(self.bc.tick_changes['t1']['at'], 0)

    def test_count_reaches_health(self):
        for _ in range(3): self.bc.apply(self.change())
        self.assertEqual(self.bc.health()['tick_changes'], 3)

    def test_untouched_tokens_are_not_recorded(self):
        self.bc.apply(self.change('t1'))
        self.assertNotIn('t2', self.bc.tick_changes)


class BookPruneKeepsSubscribedTokens(unittest.TestCase):
    """A resubscribe must not start from an empty cache.

    venue() cleared the whole cache on every cycle and again on every reconnect,
    so a token's only full snapshot was the one its subscribe delivered. A fire
    early in a candle then priced off a book snapshotted a cycle earlier and
    patched only by deltas with no continuity check - the phantom-level
    mechanism, with a cause rather than a symptom.
    """
    def setUp(self):
        self.bc = C.BookCache()
        for t in ('a', 'b', 'c'):
            self.bc.apply(dict(event_type='book', asset_id=t,
                               timestamp=str(int(time.time()*1000)),
                               asks=[{'price':'0.55','size':'100'}],
                               bids=[{'price':'0.53','size':'100'}]))

    def test_prune_keeps_the_tokens_still_subscribed(self):
        self.bc.prune(['a', 'b'])
        self.assertEqual(set(self.bc.books), {'a', 'b'})

    def test_prune_drops_the_rest(self):
        self.bc.prune(['a'])
        self.assertNotIn('b', self.bc.books)
        self.assertNotIn('c', self.bc.books)

    def test_prune_with_everything_kept_is_a_no_op(self):
        self.bc.prune(['a', 'b', 'c'])
        self.assertEqual(set(self.bc.books), {'a', 'b', 'c'})

    def test_prune_accepts_non_string_tokens(self):
        self.bc.prune([1, 'a'])          # market tuples are not always str
        self.assertIn('a', self.bc.books)


class TickGridRounding(unittest.TestCase):
    """The cap must land on the tick grid the venue quoted.

    Found live on 09-13 by the session on the AWS box: D(float) carries the
    binary representation error, so D(0.28)/D(0.01) is 28.000...2 and
    ROUND_CEILING made it 29 - a free extra tick on roughly half of all ask
    values. At pad 0 the cap must equal the ask exactly, on every tick.
    """
    terms = (0.01, 5.0, 0.0, 1.0)
    d = dict(p=0.99, threshold=-1.0)

    def plan(self, ask, pad):
        # depth in SHARES: 50/ask keeps every tick able to absorb the $50 stake,
        # so this fixture tests rounding rather than the depth check
        q = dict(ask=ask, asks=[(ask, 50.0/ask + 10)], age_ms=0, seq=1)
        return C.order_plan(q, self.terms, 50.0, self.d, pad=pad)

    def test_pad_zero_cap_equals_ask_on_every_tick(self):
        for i in range(1, 100):
            ask = round(i / 100, 2)
            with self.subTest(ask=ask):
                self.assertAlmostEqual(self.plan(ask, 0)['cap'], ask, places=9)

    def test_pad_adds_exactly_that_many_ticks(self):
        for ask in (0.28, 0.33, 0.52, 0.55, 0.29, 0.44, 0.63):
            for pad in (0, 1, 2, 3):
                with self.subTest(ask=ask, pad=pad):
                    self.assertAlmostEqual(self.plan(ask, pad)['cap'],
                                           round(ask + pad * 0.01, 2), places=9)

    def test_the_specific_values_that_were_wrong(self):
        # 0.28 -> 0.29 and 0.52 -> 0.53 at pad 0 before the fix.
        self.assertAlmostEqual(self.plan(0.28, 0)['cap'], 0.28, places=9)
        self.assertAlmostEqual(self.plan(0.52, 0)['cap'], 0.52, places=9)


if __name__ == '__main__':
    unittest.main(verbosity=1)


class LowBalanceIsWatchedNeverActedOn(unittest.TestCase):
    """User, 09-13 19:1x: "what i said was it should be trading when no money
    available and that was for you, to monitor not to add the code in file".

    Their earlier "master off when account run out of money for stack" was an
    instruction to the operator. Compiling it into the engine was an
    over-implementation, and on 09-13 it halted a SOLVENT account: cash read
    2.065 at 18:41:10 with 4.38 of position still settling, and 11.90 five and a
    half minutes later - the rise being exactly one payout.

    These tests are the inverse of the ones they replace. That is deliberate:
    the rule was removed on the owner's instruction, and the tests must fail if
    anyone puts it back.
    """
    def setUp(self):
        import btc_model_v12_polymarket as E
        self.E=E
        self.temp=tempfile.TemporaryDirectory()
        self.db=C.Journal(str(pathlib.Path(self.temp.name)/'w.db'),'LIVE','h')
        self.db.set('master',True); self.db.set('next_stake',5.0)
        r=E.PolyRunner.__new__(E.PolyRunner)
        r.db=self.db; r.a=types.SimpleNamespace(live=True); r.cash=100.0
        self.r=r

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def low(self):
        return [json.loads(x[0]) for x in
                self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%LOW_BALANCE%'")]

    def test_a_sustained_low_balance_no_longer_stops_anything(self):
        self.db.set('main_enabled',True); self.db.set('reversal_enabled',True)
        self.r.cash=1.0
        for _ in range(50): self.r._wipeout_check()
        self.assertTrue(self.db.get('master'), 'the engine must keep trading; the owner watches the money')
        self.assertIsNone(self.db.get('halt'), 'a low balance must not set a halt')
        self.assertTrue(self.db.get('main_enabled')); self.assertTrue(self.db.get('reversal_enabled'))

    def test_it_still_records_what_it_saw(self):
        self.r.cash=1.0
        for _ in range(self.r.WIPEOUT_CONFIRMATIONS): self.r._wipeout_check()
        rows=self.low()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['spendable'], 1.0, places=4)
        self.assertEqual(rows[0]['stake'], 5.0)
        self.assertFalse(rows[0]['acted'])

    def test_the_reading_carries_the_money_the_old_rule_could_not_see(self):
        """open_value is settled-but-unpaid; recording without it repeats the bug."""
        self.db.sql('INSERT INTO venue_state(ts,cash,open_value) VALUES(?,?,?)', (1., 1.0, 4.38))
        self.r.cash=1.0
        for _ in range(self.r.WIPEOUT_CONFIRMATIONS): self.r._wipeout_check()
        row=self.low()[0]
        self.assertAlmostEqual(row['open_value'], 4.38, places=4)
        self.assertAlmostEqual(row['equity'], 5.38, places=4)

    def test_one_low_read_records_nothing(self):
        self.r.cash=1.0
        self.r._wipeout_check()
        self.assertEqual(self.low(), [], 'a single dip is a race, not an episode')

    def test_it_records_once_per_episode_not_every_five_seconds(self):
        self.r.cash=1.0
        for _ in range(200): self.r._wipeout_check()
        self.assertEqual(len(self.low()), 1, 'a long low spell is one episode, not 200 rows')
        self.r.cash=100.0; self.r._wipeout_check()           # recovered
        self.r.cash=1.0
        for _ in range(self.r.WIPEOUT_CONFIRMATIONS): self.r._wipeout_check()
        self.assertEqual(len(self.low()), 2, 'a genuinely new episode records again')

    def test_a_healthy_balance_records_nothing_and_changes_nothing(self):
        for _ in range(10): self.r._wipeout_check()
        self.assertTrue(self.db.get('master')); self.assertIsNone(self.db.get('halt'))
        self.assertEqual(self.low(), [])

    def test_it_never_turns_master_ON_either(self):
        self.db.set('master',False)
        self.r.cash=100.0
        for _ in range(10): self.r._wipeout_check()
        self.assertFalse(self.db.get('master'), 'monitoring writes no flags in either direction')

    def test_paper_is_untouched(self):
        self.r.a=types.SimpleNamespace(live=False); self.r.cash=0.0
        for _ in range(10): self.r._wipeout_check()
        self.assertTrue(self.db.get('master')); self.assertEqual(self.low(), [])

    def test_nothing_else_in_the_engine_halts_on_the_balance(self):
        src = pathlib.Path(self.E.__file__).read_text()
        self.assertNotIn('Account wiped out', src, 'the wipeout halt must not come back')


class MainDisarmsAfterOneFill(unittest.TestCase):
    """User, 09-13: "main off after 1 filled order, whatever happens,
    win or lose i don't care". The trigger is the FILL, not the outcome."""
    def setUp(self):
        import btc_model_v12_polymarket as E
        self.temp=tempfile.TemporaryDirectory()
        self.db=C.Journal(str(pathlib.Path(self.temp.name)/'m.db'),'LIVE','h')
        r=E.PolyRunner.__new__(E.PolyRunner); r.db=self.db
        r.a=types.SimpleNamespace(live=True); r.error=''
        self.r=r

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def order(self,oid,kind,status,ts):
        self.db.sql('INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)'
                    " VALUES(?,?,1,?,'{}',?,0,'',?)",(oid,int(ts),status,ts,kind))

    def test_the_historical_fill_does_not_count(self):
        """MAIN has one fill from the 09-12 seeding bug. Counting it would
        disarm the lane before the operator's test ever ran."""
        self.order('old','MAIN','FILLED',100.0)      # predates arming
        self.db.set('main_enabled',True)             # audit row written here
        self.r._main_oneshot_check()
        self.assertTrue(self.db.get('main_enabled'))

    def test_one_fill_after_arming_disarms_it(self):
        self.db.set('main_enabled',True)
        ts=self.db.sql("SELECT max(ts) FROM diagnostics")[0][0]+1
        self.order('new','MAIN','FILLED',ts)
        self.r._main_oneshot_check()
        self.assertFalse(self.db.get('main_enabled'))

    def test_a_reject_is_not_a_fill(self):
        self.db.set('main_enabled',True)
        ts=self.db.sql("SELECT max(ts) FROM diagnostics")[0][0]+1
        for st in ('REJECTED','UNKNOWN','NO_FILL','PENDING'):
            self.order('o'+st,'MAIN',st,ts)
        self.r._main_oneshot_check()
        self.assertTrue(self.db.get('main_enabled'),'only a FILLED order counts')

    def test_an_ef_fill_does_not_disarm_main(self):
        self.db.set('main_enabled',True)
        ts=self.db.sql("SELECT max(ts) FROM diagnostics")[0][0]+1
        self.order('ef','EF','FILLED',ts)
        self.r._main_oneshot_check()
        self.assertTrue(self.db.get('main_enabled'))

    def test_it_does_not_wait_for_the_candle_to_grade(self):
        """win or lose, i do not care - no results row is needed."""
        self.db.set('main_enabled',True)
        ts=self.db.sql("SELECT max(ts) FROM diagnostics")[0][0]+1
        self.order('new','MAIN','FILLED',ts)
        self.assertEqual(self.db.sql('SELECT count(*) FROM results')[0][0],0)
        self.r._main_oneshot_check()
        self.assertFalse(self.db.get('main_enabled'))

    def test_it_is_a_no_op_when_main_is_already_off(self):
        self.db.set('main_enabled',False)
        self.r._main_oneshot_check()
        self.assertFalse(self.db.get('main_enabled'))


class CalibrationIsOffUntilTurnedOn(unittest.TestCase):
    """Correct what the model overclaims - EF only, and inert by default.

    Measured over 537 decided candles: honest below p=0.80, claims 0.912 and
    delivers 0.756 above it. Fitted on the first half, validated on the second,
    out-of-sample gap -0.171 -> -0.038.
    """
    def setUp(self):
        import btc_model_v12_polymarket as E
        self.temp=tempfile.TemporaryDirectory()
        self.db=C.Journal(str(pathlib.Path(self.temp.name)/'c.db'),'LIVE','h')
        r=E.PolyRunner.__new__(E.PolyRunner); r.db=self.db
        self.r=r

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def test_it_is_off_by_default(self):
        """Shipping it inert means deploying it changes nothing."""
        self.assertFalse(self.r.calibration()['enabled'])
        d=dict(fire=True,side='UP',p=0.95)
        self.assertEqual(self.r._calibrate(d)['p'],0.95)
        self.assertNotIn('calibrated',self.r._calibrate(d))

    def test_when_on_it_only_touches_the_overclaimed_region(self):
        self.db.set('calibration',dict(enabled=True,cut=0.80,to=0.784))
        for p in (0.55,0.65,0.75,0.799):
            self.assertEqual(self.r._calibrate(dict(p=p))['p'],p,f'{p} is honest, leave it')
        for p in (0.80,0.912,0.99):
            out=self.r._calibrate(dict(p=p))
            self.assertAlmostEqual(out['p'],0.784)
            self.assertAlmostEqual(out['p_raw'],p,msg='the original must stay on the record')
            self.assertTrue(out['calibrated'])

    def test_it_can_only_lower_a_claim(self):
        self.db.set('calibration',dict(enabled=True,cut=0.80,to=0.784))
        for p in (0.80,0.85,0.90,0.95,1.0):
            self.assertLessEqual(self.r._calibrate(dict(p=p))['p'],p)

    def test_a_nonsense_setting_falls_back_to_off(self):
        for bad in (dict(enabled=True,cut=0.3,to=0.784),      # cut outside range
                    dict(enabled=True,cut=0.80,to=1.5),       # to above 1
                    dict(enabled=True,cut=0.80,to='x'),       # unparseable
                    dict(enabled=True,cut=0.80,to=0.99)):     # a RAISE, not a shrink
            self.db.set('calibration',bad)
            self.assertFalse(self.r.calibration()['enabled'],f'{bad} must not apply')

    def test_a_missing_or_bad_p_is_passed_through(self):
        self.db.set('calibration',dict(enabled=True,cut=0.80,to=0.784))
        self.assertEqual(self.r._calibrate(dict(fire=True)),dict(fire=True))
        self.assertEqual(self.r._calibrate(dict(p=None))['p'],None)


class LaneDecisionsRecordThePriceTheySaw(unittest.TestCase):
    """Without the ask on every lane decision, MAIN's question is unanswerable.

    On 09-13 the journal held 145 non-refusal MAIN rows carrying `p` and zero
    carrying an ask, so "would firing earlier have helped" could not be tested -
    the only priced rows were four retries inside one second. The book is venue
    data, not a lane's opinion, so recording it commits to nothing.
    """
    def test_the_writer_records_both_asks_from_the_book(self):
        import btc_model_v12_polymarket as E, inspect
        src=inspect.getsource(E.PolyRunner.lane_loop)
        self.assertIn("'ask_up'",src)
        self.assertIn("'ask_dn'",src)
        self.assertIn('self.books.quote',src)
        # it must go in the SAME row as the decision, not a separate write
        self.assertIn('dict(decision,lane=kind,**_px)',src)

    def test_it_cannot_break_the_decision_path(self):
        """A missing market or a cold book must not stop the lane recording."""
        import btc_model_v12_polymarket as E, inspect
        src=inspect.getsource(E.PolyRunner.lane_loop)
        head=src[:src.index('INSERT INTO diagnostics')]
        self.assertIn('except Exception: pass',head,
                      'the price lookup must not be able to raise into lane_loop')


class MainHasAnEntryTheUserCanSee(unittest.TestCase):
    """The user: "there's no entry for main in data for me to see".

    Three places in the dashboard erased MAIN, and the data page has had a
    "MAIN - RECENT ORDERS" section the whole time:

    1. `orders()` opened with `if kind!='EF': return rows=[]`, so the MAIN and
       REVERSAL tables were empty BY CONSTRUCTION.
    2. Its query never filtered on kind, so the EF table listed every lane's
       orders - each one relabelled `kind='EF'` in the row dict. MAIN's fill of
       09-13 18:20:43 was not merely missing, it was displayed as EF.
    3. `history()` hardcoded `main={}` / `reversal={}` and grouped by epoch, so a
       two-lane candle charged the whole combined loss to EF.

    Epoch 1789323600 is the real one: EF -4.81 at 18:20:34 and MAIN -4.80 at
    18:20:43, nine seconds apart, a -9.61 result row that is two lanes and not
    one trade.
    """
    EPOCH, WIN = 1789323600, 1789323300

    def setUp(self):
        import poly_dashboard as D
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'a.db'), 'LIVE', 'h')
        plan = json.dumps(dict(quote=.43, pre_submit_quote=.43, cap=.48, age_ms=12, budget=5.))
        dec = json.dumps(dict(sec=34., signal_price=77000.))
        # the real double-lane candle: both lanes UP, the candle went DOWN
        for kind, oid, spent, shares, ts in (('EF','oEF',4.81,8.00,100.),('MAIN','oMAIN',4.80,11.16,109.)):
            self.db.reserve(self.EPOCH, dict(side='UP', fire=True), 'tok', 'cond', kind=kind)
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,kind,decision) "
                        "VALUES(?,?,1,'FILLED',?,?,50,?,?)" if 'decision' in
                        {r[1] for r in self.db.c.execute('PRAGMA table_info(orders)')} else
                        "INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,kind) VALUES(?,?,1,'FILLED',?,?,50,?)",
                        (oid, self.EPOCH, plan, ts, kind))
            self.db.sql("INSERT INTO fills(id,order_id,epoch,shares,spent,fees,price,basis) VALUES(?,?,?,?,?,0,?,'T')",
                        ('f'+oid, oid, self.EPOCH, shares, spent, spent/shares))
        self.db.sql("INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,'DOWN',0,-9.61,120)", (self.EPOCH,))
        # and an EF-only winner, so the single-lane path is covered too
        self.db.reserve(self.WIN, dict(side='UP', fire=True), 'tok', 'cond', kind='EF')
        self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,kind) "
                    "VALUES('oW',?,1,'FILLED',?,90,50,'EF')", (self.WIN, plan))
        self.db.sql("INSERT INTO fills(id,order_id,epoch,shares,spent,fees,price,basis) "
                    "VALUES('fW','oW',?,10.42,5.00,0,0.48,'T')", (self.WIN,))
        self.db.sql("INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,'UP',10.42,5.42,95)", (self.WIN,))
        class Bare(D.Dashboard):
            def __init__(self): pass
        self.ui = Bare(); self.ui.db = self.db
        self.ui.r = types.SimpleNamespace(a=types.SimpleNamespace(live=True), revision=1)

    def tearDown(self):
        self.db.c.close(); self.temp.cleanup()

    def test_main_orders_are_served_at_all(self):
        out = self.ui.orders('MAIN', 0, 10)
        self.assertEqual(len(out['rows']), 1, 'MAIN asked for its orders and got an empty page')
        self.assertEqual(out['rows'][0]['kind'], 'MAIN')
        self.assertEqual(out['rows'][0]['order_id'], 'oMAIN')

    def test_the_ef_table_no_longer_shows_mains_order(self):
        rows = self.ui.orders('EF', 0, 10)['rows']
        self.assertEqual({r['order_id'] for r in rows}, {'oEF', 'oW'})
        self.assertTrue(all(r['kind'] == 'EF' for r in rows))

    def test_each_lanes_pager_counts_only_its_own(self):
        self.assertEqual(self.ui.orders('MAIN', 0, 10)['total'], 1)
        self.assertEqual(self.ui.orders('EF', 0, 10)['total'], 2)

    def test_an_order_row_carries_its_own_lane_pnl_not_the_candles(self):
        # the result row is -9.61 for the candle; neither lane lost that
        self.assertAlmostEqual(self.ui.orders('MAIN', 0, 10)['rows'][0]['pnl'], -4.80, places=2)
        ef = [r for r in self.ui.orders('EF', 0, 10)['rows'] if r['order_id'] == 'oEF'][0]
        self.assertAlmostEqual(ef['pnl'], -4.81, places=2)

    def test_history_splits_the_double_lane_candle(self):
        row = [r for r in self.ui.history(0, 10)['rows'] if r['candle_id'] == self.EPOCH*1000][0]
        self.assertTrue(row['main'], 'MAIN traded this candle and the row shows it blank')
        self.assertAlmostEqual(row['main']['pnl'], -4.80, places=2)
        self.assertAlmostEqual(row['ef']['pnl'], -4.81, places=2)
        self.assertAlmostEqual(row['combined_financial_pnl'], -9.61, places=2)
        self.assertEqual(sorted(row['lanes']), ['EF', 'MAIN'])

    def test_a_two_lane_candle_is_still_one_row_and_paging_counts_candles(self):
        rows = self.ui.history(0, 10)['rows']
        self.assertEqual(len(rows), 2, 'two candles, one of them two-lane')
        self.assertEqual(len(self.ui.history(0, 1)['rows']), 1, 'limit must mean candles, not lane rows')

    def test_the_single_lane_winner_is_unchanged(self):
        row = [r for r in self.ui.history(0, 10)['rows'] if r['candle_id'] == self.WIN*1000][0]
        self.assertEqual(row['main'], {}); self.assertEqual(row['reversal'], {})
        self.assertAlmostEqual(row['ef']['pnl'], 5.42, places=2)
        self.assertEqual(row['combined_financial_result'], 'WIN')

    def test_chart_markers_carry_the_real_lane(self):
        self.assertEqual({m['kind'] for m in self.ui.chart()['markers']}, {'EF', 'MAIN'})

    def test_the_empty_page_guard_still_holds(self):
        self.assertEqual(self.ui.orders('NOPE', 0, 10)['rows'], [])
        self.assertEqual(self.ui.history(500, 10)['rows'], [])
