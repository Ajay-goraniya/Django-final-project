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

    def test_platt_mode_flattens_every_claim_and_never_raises_one(self):
        """12.24.0: H1 measured v10 EF's p ~7 points overconfident in every ask bucket (EF_BRAIN.md), so a
        single cut cannot fix it. Platt: p' = sigmoid(a*logit(p)+b), a in (0,1], clamped at p."""
        import math
        self.db.set('calibration',dict(enabled=True,cut=0.80,to=0.784,mode='platt',a=0.8,b=-0.25))
        self.assertEqual(self.r.calibration()['mode'],'platt')
        for p in (0.35,0.5,0.6,0.7,0.9):
            out=self.r._calibrate(dict(p=p)); z=math.log(p/(1-p)); q=1/(1+math.exp(-(0.8*z-0.25)))
            self.assertLessEqual(out['p'],p)
            self.assertAlmostEqual(out['p'],min(p,q),places=9); self.assertEqual(out['p_raw'],p); self.assertTrue(out['calibrated'])
        # a pair that would RAISE a claim is clamped: p stays, no 'calibrated' mark
        self.db.set('calibration',dict(enabled=True,cut=0.80,to=0.784,mode='platt',a=1.0,b=0.5))
        out=self.r._calibrate(dict(p=0.6)); self.assertEqual(out['p'],0.6); self.assertNotIn('calibrated',out)
        # H1's pooled pair (EF_BRAIN.md D): a=1.0677, b=-0.3208 lowers every claim in the tradable range
        self.db.set('calibration',dict(enabled=True,cut=0.80,to=0.784,mode='platt',a=1.0677,b=-0.3208))
        self.assertTrue(self.r.calibration()['enabled'])
        for p in (0.45,0.55,0.60,0.65,0.75):
            out=self.r._calibrate(dict(p=p)); self.assertLess(out['p'],p); self.assertGreater(out['p'],p-0.10)

    def test_platt_mode_bounds_fall_back_to_off(self):
        for bad in (dict(enabled=True,mode='platt',a=1.5,b=0.0),      # slope out of bounds
                    dict(enabled=True,mode='platt',a=0.0,b=0.0),      # degenerate
                    dict(enabled=True,mode='platt',a=0.8,b=float('nan')),
                    dict(enabled=True,mode='sigmoid',a=0.8,b=0.0)):   # unknown mode
            self.db.set('calibration',bad)
            self.assertFalse(self.r.calibration()['enabled'],f'{bad} must not apply')


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


class TheHaltCanBeClearedFromTheControlsPage(unittest.TestCase):
    """User, 09-13 19:2x: "I'm not even able to turn onn master it's not turning onn".

    Three things met to make the engine unrecoverable from its own UI:

    1. `/api/controls/apply` refuses `manual_enabled=True` while `halt` is set.
    2. `controls()` never returned `halt`, so the page could not even show WHY.
    3. `controls_html.html` had no control that called `/api/controls/clear-halt`,
       which had existed since 12.4.1 and was only ever reachable by hand.

    So the master toggle bounced with no visible cause and the only recovery was
    an HTTP call the operator had no way to make. A kill switch whose reset is
    not on the page is an outage, which is the same lesson 12.4.1 wrote down and
    this is the half of it that was missed.
    """
    HALT = 'Account wiped out: spendable 2.06 below stake 5.00 on 3 consecutive balance reads'

    def setUp(self):
        import poly_dashboard as D
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'h.db'), 'LIVE', 'h')
        self.db.set('master', False); self.db.set('next_stake', 5.0)
        class Bare(D.Dashboard):
            def __init__(self): pass
        self.ui = Bare(); self.ui.db = self.db; self.ui.cache_at = 0
        self.ui.r = types.SimpleNamespace(a=types.SimpleNamespace(live=True), cash=11.90,
                                          cash_at=time.monotonic(), revision=1)

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def arm(self):
        return self.ui.apply('/api/controls/apply', dict(confirmed=True, system=dict(manual_enabled=True)))

    def test_the_page_is_told_the_halt_exists(self):
        self.db.set('halt', self.HALT)
        self.assertEqual(self.ui.controls()['halt'], self.HALT)

    def test_no_halt_reads_as_none_not_missing(self):
        self.assertIn('halt', self.ui.controls())
        self.assertIsNone(self.ui.controls()['halt'])

    def test_arming_master_under_a_halt_fails_with_the_reason(self):
        self.db.set('halt', self.HALT)
        with self.assertRaises(ValueError) as cm: self.arm()
        self.assertIn('wiped out', str(cm.exception))
        self.assertFalse(self.db.get('master'))

    def test_clear_then_arm_is_the_recovery_path_and_it_works(self):
        self.db.set('halt', self.HALT)
        out = self.ui.apply('/api/controls/clear-halt', dict(confirmed=True, acknowledge=self.HALT))
        self.assertTrue(out['ok']); self.assertIsNone(self.db.get('halt'))
        self.arm()
        self.assertTrue(self.db.get('master'), 'master must arm once the kill is cleared')

    def test_clearing_does_not_arm_master_by_itself(self):
        self.db.set('halt', self.HALT)
        self.ui.apply('/api/controls/clear-halt', dict(confirmed=True, acknowledge=self.HALT))
        self.assertFalse(self.db.get('master'), 'two deliberate acts, not one')

    def test_a_wrong_acknowledgement_clears_nothing(self):
        self.db.set('halt', self.HALT)
        with self.assertRaises(ValueError):
            self.ui.apply('/api/controls/clear-halt', dict(confirmed=True, acknowledge='yes'))
        self.assertEqual(self.db.get('halt'), self.HALT)

    def test_clearing_restarts_the_kill_window(self):
        self.db.set('halt', self.HALT)
        out = self.ui.apply('/api/controls/clear-halt', dict(confirmed=True, acknowledge=self.HALT))
        self.assertAlmostEqual(self.db.get('halt_cleared_at'), out['window_restarts_at'], places=6)

    def test_the_page_actually_carries_the_control(self):
        page = pathlib.Path(__file__).with_name('controls_html.html').read_text()
        self.assertIn('/api/controls/clear-halt', page, 'the reset must be reachable from the UI')
        self.assertIn('clearHalt', page)
        self.assertIn('acknowledge:state.halt', page, 'the exact reason must be echoed, never retyped')
        self.assertIn('haltBox', page)


class ArmingMasterIsAudited(unittest.TestCase):
    """AWS, 09-13 19:35: master reads true and there is NO control_write row.

    `/api/controls/apply` wrote its updates with a bare INSERT OR REPLACE to keep
    master and the stake bundle atomic. Only `Journal.set()` carries the audit, so
    that path bypassed it: every `master` row in the journal was `True -> False`
    (twelve safe-startup writes plus the wipeout), and there had never been a
    single `False -> True` - not the operator's arming, not any re-arm.

    The audit exists because the lane flags reverted twice on Tokyo with no known
    cause. One that can only record things being turned OFF is backwards for the
    question it was built to answer.
    """
    def setUp(self):
        import poly_dashboard as D
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'a.db'), 'LIVE', 'h')
        self.db.set('master', False)
        class Bare(D.Dashboard):
            def __init__(self): pass
        self.ui = Bare(); self.ui.db = self.db; self.ui.cache_at = 0
        self.ui.r = types.SimpleNamespace(a=types.SimpleNamespace(live=True), cash=11.90,
                                          cash_at=time.monotonic(), revision=1)
        # setUp's own seeding writes an audit row; the tests measure what the
        # ENDPOINT records, so start them from a clean diagnostics table.
        self.db.sql('DELETE FROM diagnostics')

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def writes(self, key):
        return [json.loads(x[0]) for x in
                self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%control_write%'")
                if json.loads(x[0]).get('key') == key]

    def test_arming_master_leaves_an_audit_row(self):
        self.ui.apply('/api/controls/apply', dict(confirmed=True, system=dict(manual_enabled=True)))
        rows = self.writes('master')
        self.assertEqual(len(rows), 1, 'the one direction that matters must be recorded')
        self.assertIs(rows[0]['old'], False); self.assertIs(rows[0]['new'], True)

    def test_the_row_names_the_caller_not_the_journal(self):
        self.ui.apply('/api/controls/apply', dict(confirmed=True, system=dict(manual_enabled=True)))
        stack = self.writes('master')[0]['stack']
        self.assertTrue(any('poly_dashboard.py' in f for f in stack), stack)
        self.assertFalse(any(f.endswith('set_many') or f.endswith('_audit') for f in stack),
                         'the audit must name who asked, not the journal plumbing')

    def test_disarming_is_still_audited(self):
        self.db.set('master', True)
        self.ui.apply('/api/controls/apply', dict(confirmed=True, system=dict(manual_enabled=False)))
        rows = self.writes('master')
        self.assertIs(rows[-1]['new'], False)

    def test_a_no_op_write_records_nothing(self):
        self.ui.apply('/api/controls/apply', dict(confirmed=True, system=dict(manual_enabled=False)))
        self.assertEqual(self.writes('master'), [], 'False -> False is not a control change')

    def test_the_single_key_path_still_names_its_caller(self):
        """set() was refactored through _audit; its stack must not regress."""
        self.db.set('ef_enabled', False)
        stack = self.writes('ef_enabled')[0]['stack']
        self.assertFalse(any(f.endswith(' set') or f.endswith('_audit') for f in stack), stack)

    def test_the_bundle_is_still_written_atomically(self):
        before = self.db.get('next_stake')
        with self.assertRaises(Exception):
            self.db.set_many({'next_stake': 7.0, 'bad': object()})
        self.assertEqual(self.db.get('next_stake'), before, 'a failed bundle must write nothing')

    def test_no_raw_meta_writes_are_left_in_the_dashboard(self):
        src = pathlib.Path(C.__file__).parent.joinpath('poly_dashboard.py').read_text()
        self.assertNotIn('INSERT OR REPLACE INTO meta', src,
                         'control writes go through the journal so they are audited')


class AmbientBookAgeIsSampled(unittest.TestCase):
    """Task 75 could not be answered: age_ms was only ever persisted on the
    submit path, which the seq gate at poly_core.py:928 has already filtered.
    Nothing recorded the ambient age. This samples it from the raw arrival
    stamp - not quote(), so the 2 s filter cannot hide the tail - once per
    housekeeping tick. Instrumentation only; it must never raise.
    """
    def setUp(self):
        import btc_model_v12_polymarket as E
        self.temp=tempfile.TemporaryDirectory()
        self.db=C.Journal(str(pathlib.Path(self.temp.name)/'a.db'),'LIVE','h')
        r=E.PolyRunner.__new__(E.PolyRunner)
        r.db=self.db; r.market={600:('tokUP','tokDN')}
        r.books=types.SimpleNamespace(books={'tokUP':{'arrival':time.monotonic()-0.150},
                                             'tokDN':{'arrival':time.monotonic()-0.420}})
        self.r=r

    def tearDown(self): self.db.c.close(); self.temp.cleanup()

    def rows(self):
        return [json.loads(x[0]) for x in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%AMBIENT_AGE%'")]

    def test_one_row_with_both_tokens_ages(self):
        self.r._sample_ambient_age(600)
        rows=self.rows(); self.assertEqual(len(rows),1)
        self.assertAlmostEqual(rows[0]['age_up_ms'],150,delta=40)
        self.assertAlmostEqual(rows[0]['age_dn_ms'],420,delta=40)

    def test_a_token_with_no_book_yet_is_null_not_an_error(self):
        del self.r.books.books['tokDN']
        self.r._sample_ambient_age(600)
        self.assertIsNone(self.rows()[0]['age_dn_ms'])

    def test_no_market_for_the_epoch_writes_nothing(self):
        self.r._sample_ambient_age(999)
        self.assertEqual(self.rows(),[])

    def test_it_cannot_raise_into_housekeeping(self):
        self.r.books=None                          # worst case: nothing wired
        self.r._sample_ambient_age(600)            # must not raise
        self.assertEqual(self.rows(),[])

    def test_housekeeping_calls_it(self):
        import btc_model_v12_polymarket as E
        src=pathlib.Path(E.__file__).read_text()
        self.assertIn('self._sample_ambient_age(',src)


from unittest import mock

class WaitCensusSaysWhichBookBlockedAndHowOld(unittest.TestCase):
    """12.8.10. Task 86: 34.7% of decide rows were "Waiting for fresh UP and DOWN
    books" and nothing recorded which token or what age. quote() now leaves a
    (reason, age) per refused token; publish() counts side x reason x bucket;
    housekeeping writes one WAIT_CENSUS row a minute. Observation only.
    """
    def setUp(self):
        import btc_model_v12_polymarket as E
        self.temp=tempfile.TemporaryDirectory()
        self.db=C.Journal(str(pathlib.Path(self.temp.name)/'w.db'),'PAPER','h')
        self.books=C.BookCache(); now=time.time()
        # UP: fresh two-sided book. DOWN: one-sided (no asks), 1.5 s old.
        self.books.apply(dict(event_type='book',asset_id='tokUP',timestamp=str(int(now*1000)),bids=[dict(price='0.40',size='10')],asks=[dict(price='0.42',size='10')]))
        self.books.apply(dict(event_type='book',asset_id='tokDN',timestamp=str(int(now*1000)),bids=[dict(price='0.55',size='10')],asks=[]))
        self.books.books['tokDN']['arrival']-=1.5
        r=E.PolyRunner.__new__(E.PolyRunner)
        r.db=self.db; r.books=self.books; r.market={600:('tokUP','tokDN')}
        r.a=types.SimpleNamespace(quote_age_ms=2000); r.age={}; r.health=types.SimpleNamespace(arrival={},lag={},msgs={})
        r.st=types.SimpleNamespace(on_venue_quote=lambda *a: None)
        r._wait_census={}; r._wait_flushed=time.monotonic()-61
        self.r=r; self.E=E
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def rows(self):
        return [json.loads(x[0]) for x in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%WAIT_CENSUS%'")]

    def test_quote_leaves_the_reason_and_age_per_token(self):
        self.assertIsNone(self.books.quote('tokDN',2.0))
        reason,age=self.books.block_detail['tokDN']
        self.assertEqual(reason,'no_asks'); self.assertAlmostEqual(age,1.5,delta=0.2)
        self.assertIsNotNone(self.books.quote('tokUP',2.0)); self.assertNotIn('tokUP',self.books.block_detail)

    def test_publish_counts_side_reason_bucket(self):
        with mock.patch('time.time',return_value=600.0+30):
            self.assertFalse(self.r.publish())
        self.assertEqual(self.r._wait_census,{'DOWN:no_asks:1-2':1})

    def test_stale_is_bucketed_by_the_age_quote_judged(self):
        self.books.books['tokDN']['asks']={0.57:10.}; self.books.books['tokDN']['arrival']-=2.0   # 3.5 s old
        with mock.patch('time.time',return_value=600.0+30):
            self.r.publish()
        self.assertEqual(list(self.r._wait_census),['DOWN:stale:2-5'])

    def test_housekeeping_writes_one_row_a_minute_and_resets(self):
        with mock.patch('time.time',return_value=600.0+30):
            self.r.publish(); self.r.publish()
        self.r._flush_wait_census(600)
        rows=self.rows(); self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['DOWN:no_asks:1-2'],2); self.assertGreaterEqual(rows[0]['window_s'],60)
        self.assertEqual(self.r._wait_census,{})
        self.r._flush_wait_census(600); self.assertEqual(len(self.rows()),1,'nothing to flush, no row')

    def test_ok_publishes_are_counted_too(self):
        self.books.books['tokDN']['asks']={0.57:10.}; self.books.books['tokDN']['arrival']=time.monotonic()
        with mock.patch('time.time',return_value=600.0+30):
            self.assertTrue(self.r.publish())
        self.assertEqual(self.r._wait_census,{'ok':1})

    def test_it_cannot_raise_into_the_decide_path(self):
        self.r.books=types.SimpleNamespace(quote=lambda *a: None)   # no block_detail attribute at all
        with mock.patch('time.time',return_value=600.0+30):
            self.assertFalse(self.r.publish())


# ---------------------------------------------------------------- 12.9.0
# Engine cleanup from analysis/v/audit_hotpath.md and audit_deadcode_overlap.md
# (plan_12_9.md items 1-7). No decision logic, threshold, EV maths, pad or
# execution shape changes; every test below FAILED on 12.8.11 unless noted.
import asyncio, hashlib, math, threading

def _snap(token='up', ask=.4, qty=100., ts=None):
    return dict(event_type='book', asset_id=token, timestamp=str(int((ts or time.time())*1000)),
                asks=[dict(price=str(ask), size=str(qty))], bids=[dict(price=str(ask-.01), size='100')])

def _decision(): return dict(fire=True, side='UP', p=.8, threshold=.2, ask=.4, sec=30, ev=.9)

def _paper_runner():
    import sys, btc_model_v12_polymarket as E
    sys.argv = ['x']
    a = types.SimpleNamespace(live=False, port=0, host='127.0.0.1',
        model=str(pathlib.Path(E.__file__).with_name('model_v10.json')),
        db=tempfile.mktemp(suffix='.sqlite3'), capital=50, mode='pnl', ev=None,
        quote_age_ms=750, pad_ticks=1, execution_budget_ms=2000,
        post_timeout_ms=1200, max_attempts=3)
    return E.PolyRunner(a), E


class PostTimeoutFloor(unittest.TestCase):
    """Item 1. audit_hotpath defect (i): wait_for(post, max(.001, deadline-start))
    could send a real order with a few-ms timeout, cancel it mid-flight and leave
    UNKNOWN. Under POST_FLOOR_S of budget left the attempt releases BUDGET instead."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'f.db'), 'PAPER', 'abc')
        self.books = C.BookCache(); self.books.apply(_snap()); self.books.terms['up'] = (.01, 1, .07, 1)
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def _fire(self, prepare_delay):
        posted = []
        class Slow(C.PaperBroker):
            async def prepare(self, t, plan):
                await asyncio.sleep(prepare_delay)
                books.apply(_snap())                      # same ask re-applied: PaperBroker.post reads a fresh book
                return await super().prepare(t, plan)
            async def post(self, s): posted.append(1); return await super().post(s)
        books = self.books
        ex = C.Executor(self.db, self.books, Slow(self.books), age=5.0, budget_s=2.0)
        ep = int(time.time())-30
        asyncio.run(ex.fire(ep, _decision(), 'up', 'c', 10, _decision))
        rearmed = [json.loads(r[0])['after'] for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%candle_rearmed%'")]
        return len(posted), len(self.db.sql('SELECT * FROM orders')), rearmed, ex
    def test_floor_is_400ms(self):
        self.assertEqual(C.Executor.POST_FLOOR_S, 0.4)
        self.assertIn('BUDGET', C.Journal.NO_ORDER_SENT, 'nothing was sent, so the candle re-arms like DEADLINE')
    def test_above_the_floor_still_posts(self):
        posted, orders, rearmed, ex = self._fire(1.4)          # ~0.6 s left
        self.assertEqual((posted, orders, rearmed), (1, 1, []))
    def test_below_the_floor_releases_budget_and_never_posts(self):
        posted, orders, rearmed, ex = self._fire(1.75)         # ~0.25 s left
        self.assertEqual((posted, orders), (0, 0), 'no order may leave with a sub-floor timeout')
        self.assertEqual(rearmed, ['BUDGET'])
        self.assertEqual(ex.latency_samples[-1]['outcome'], 'BUDGET', 'timing is recorded')
        self.assertLess(ex.latency_samples[-1]['post_budget_left_ms'], 400)


class FeatureCacheParity(unittest.TestCase):
    """Item 2. features() rebuilt np.fromiter over the full 20-min deques on every
    call (~15 ms x ~7 per fire). The array conversions are now cached on a
    mutation counter; the numbers must be bit-identical with and without it."""
    US = 1_000_000
    def _feed(self, st, seed=7):
        import random; rng = random.Random(seed)
        open_us = 1_700_000_000*self.US; px = 60000.0; out = []
        for s in range(700, 0, -1):                       # 700 s of pre-history, 1 trade/s
            px *= 1+rng.uniform(-2e-4, 2e-4); st.on_spot_trade(open_us-s*self.US, px, rng.uniform(.01, 2), rng.random() < .5)
            if s % 2 == 0: st.on_perp_trade(open_us-s*self.US, px*(1+rng.uniform(-1e-4, 1e-4)), 1., rng.uniform(-500, 500), 500.)
        now = open_us + 15*self.US
        for i in range(1000):                              # 1,000 ticks, 250 ms apart
            now += 250_000
            if i % 3: px *= 1+rng.uniform(-3e-4, 3e-4); st.on_spot_trade(now-rng.randint(0, 200_000), px, rng.uniform(.01, 3), rng.random() < .5)
            if i % 2: st.on_perp_trade(now-rng.randint(0, 200_000), px*(1+rng.uniform(-1e-4, 1e-4)), 1., rng.uniform(-900, 900), 900.)
            if i % 4 == 0: st.on_depth(now, px-1, 3., px+1, 2., 30., 28., 100., 90.)
            if i % 5 == 0: st.on_venue_quote(.4+rng.uniform(-.1, .1), .38, .58, .56)
            out.append((open_us, now))
        return out
    def _same(self, a, b):
        self.assertEqual(a is None, b is None)
        if a is None: return
        self.assertEqual(set(a), set(b))
        for k in a:
            x, y = a[k], b[k]
            if isinstance(x, float) and math.isnan(x): self.assertTrue(isinstance(y, float) and math.isnan(y), k); continue
            self.assertEqual(x, y, k); self.assertEqual(type(x), type(y), k)
    def test_cached_and_uncached_are_bit_identical_over_1000_ticks(self):
        from btc_model_v10 import FeatureState
        a, b = FeatureState(), FeatureState(cache=False)
        import random
        ta, tb = self._feed(a), self._feed(b)
        self.assertEqual(ta, tb)
        n = 0
        for ep, now in ta:
            fa = a.features(ep, now); fb = b.features(ep, now)
            self._same(fa, fb); self._same(a.features(ep, now), fa)   # second call in the same tick = a hit
            n += fa is not None
        self.assertGreater(n, 900)
        self.assertGreaterEqual(a.cache_hits, 1000, 'the second call per tick reuses the arrays')
        self.assertEqual(b.cache_hits, 0)
    def test_new_data_invalidates(self):
        from btc_model_v10 import FeatureState
        st = FeatureState(); self._feed(st); ep, now = 1_700_000_000*self.US, 1_700_000_000*self.US+100*self.US
        st.features(ep, now); h = st.cache_hits; st.features(ep, now); self.assertEqual(st.cache_hits, h+1)
        st.on_perp_trade(now, 60000., 1., 1., 1.); st.features(ep, now); self.assertEqual(st.cache_hits, h+1, 'a new print rebuilds')
        st.on_spot_trade(now, 60000., 1., False); st.features(ep, now); self.assertEqual(st.cache_hits, h+1)


class SigningOffTheLoop(unittest.TestCase):
    """Item 3. The EIP-712 sign (5.3 ms) and the journal re-hash ran on the event
    loop inside the fire path. They run in a worker thread now; same bytes."""
    def test_thread_path_matches_the_synchronous_bytes(self):
        from poly_live import sign_off_loop
        from eth_account import Account
        from eth_account.messages import encode_defunct
        acct = Account.from_key('0x'+'11'*32); msg = encode_defunct(text='fixed draft 12.9.0'); threads = []
        async def sign(): threads.append(threading.get_ident()); return acct.sign_message(msg)
        hash_fn = lambda s: '0x'+hashlib.sha256(bytes(s.signature)).hexdigest()
        ref = asyncio.run(sign())
        signed, jh = asyncio.run(sign_off_loop(sign, hash_fn))
        self.assertEqual(bytes(signed.signature), bytes(ref.signature))
        self.assertEqual(jh, hash_fn(ref))
        self.assertNotEqual(threads[1], threading.main_thread().ident, 'the sign ran off the loop thread')
    def test_a_coroutine_that_really_suspends_falls_back_to_the_loop(self):
        from poly_live import sign_off_loop
        async def sign(): await asyncio.sleep(0); return 'sig'
        self.assertEqual(asyncio.run(sign_off_loop(sign, lambda s: s+'-h')), ('sig', 'sig-h'))
    def test_sdk_sign_order_awaits_nothing(self):
        """The off-loop driver relies on polymarket-client 0.10.0's _sign_order never suspending."""
        import inspect
        from polymarket.clients.async_secure import AsyncSecureClient
        self.assertNotIn('await', inspect.getsource(AsyncSecureClient._sign_order))


class HousekeepingCadence(unittest.TestCase):
    """Item 4. diagnostics(ts) indexed; retention DELETEs hourly, not every 5 s;
    halt_check / _wipeout_check at most once a minute (the MAIN one-shot guard was removed in 12.24.2)."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = C.Journal(str(pathlib.Path(self.temp.name)/'h.db'), 'LIVE', 'h')
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def _twenty_losses(self):
        f = dict(shares=10., spent=5., fees=0., price=.5, fee_bps=0)
        for i in range(20):
            ep = 5000+i
            self.db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind) VALUES(?,?,1,'FILLED','{}',0,0,'','EF')", (f'o{ep}', ep))
            self.db.fill(f'o{ep}', ep, f't{ep}', f, 'paper')
            self.db.sql('INSERT INTO results(epoch,actual,payout,pnl,ts) VALUES(?,?,?,?,0)', (ep, 'UP', 0., -1.0))
        self.db.sql('DELETE FROM diagnostics')
    def test_diagnostics_ts_is_indexed(self):
        names = [r[1] for r in self.db.c.execute('PRAGMA index_list(diagnostics)')]
        self.assertIn('diagnostics_ts', names)
    def test_halt_check_is_throttled_when_asked_and_not_otherwise(self):
        self.assertEqual(C.Journal.HALT_CHECK_EVERY_S, 60.0)
        self.assertTrue(self.db.halt_check(every_s=60))
        calls = []; real = self.db.sql; self.db.sql = lambda *a, **k: (calls.append(a[0]), real(*a, **k))[1]
        self.assertFalse(self.db.halt_check(every_s=60)); self.assertEqual(calls, [], 'no query inside the window')
        self.assertTrue(self.db.halt_check()); self.assertTrue(calls, 'a bare call still runs (tests, operator)')
    def test_kill_condition_rows_still_written_through_the_throttled_path(self):
        self._twenty_losses(); self.assertTrue(self.db.halt_check(every_s=60))
        rows = [json.loads(r[0]) for r in self.db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%KILL_CONDITION%'")]
        self.assertEqual(sorted(r['rule'] for r in rows), ['ALL', 'EF']); self.assertTrue(all(r['acted'] is False for r in rows))
        self.assertIsNone(self.db.get('halt'))
    def test_due_helper(self):
        import btc_model_v12_polymarket as E
        r = E.PolyRunner.__new__(E.PolyRunner); clock = [0.]; r._clock = lambda: clock[0]
        self.assertEqual((E.PolyRunner.MONITOR_EVERY_S, E.PolyRunner.RETENTION_EVERY_S), (60.0, 3600.0))
        self.assertTrue(r._due('x', 60)); self.assertFalse(r._due('x', 60))
        clock[0] = 59.9; self.assertFalse(r._due('x', 60)); clock[0] = 60.0; self.assertTrue(r._due('x', 60))
        self.assertTrue(r._due('y', 60), 'names are independent')
    def _run_loop(self, E, coro, step_s, iterations, clock):
        class Stop(Exception): pass
        n = [0]
        async def fake_sleep(s):
            clock[0] += step_s; n[0] += 1
            if n[0] >= iterations: raise Stop()
        with mock.patch.object(E.asyncio, 'sleep', fake_sleep), self.assertRaises(Stop): asyncio.run(coro)
    def test_housekeeping_deletes_hourly_and_wipeout_checks_once_a_minute(self):
        r, E = _paper_runner(); clock = [0.]; r._clock = lambda: clock[0]
        wip = []; r._wipeout_check = lambda: wip.append(clock[0])
        deletes = []; real = r.db.sql
        r.db.sql = lambda *a, **k: (deletes.append(a[0]) if a[0].startswith('DELETE') else None, real(*a, **k))[1]
        self._run_loop(E, r.housekeeping(), 5.0, 13, clock)          # 13 passes = 60 s of housekeeping
        self.assertEqual(r.error, '', 'the body ran to the end on every pass')
        self.assertEqual(len(deletes), 3, 'one retention pass (diagnostics + candles + tape1s since 12.23.0), not one per 5 s')
        self.assertEqual(wip, [0., 60.])
        r.db.c.close()


class OneQuoteAgeDial(unittest.TestCase):
    """Item 5. audit_deadcode 2.1/2.2: publish() read the CLI quote age while the
    gate and executor read meta; the gate ran the depth check the executor skips."""
    def setUp(self):
        self.r, self.E = _paper_runner(); self.ep = int(time.time()//300)*300
        self.r.market = {self.ep: ('tokUP', 'tokDN')}
        for t in ('tokUP', 'tokDN'): self.r.books.apply(_snap(t, .4 if t == 'tokUP' else .58))
    def tearDown(self): self.r.db.c.close()
    def _age_books(self, s):
        for t in ('tokUP', 'tokDN'): self.r.books.books[t]['arrival'] -= s
    def test_publish_follows_the_meta_dial(self):
        self._age_books(1.0)                                    # CLI default is 750 ms
        self.r.db.set('ev_settings', {'quote_age_ms': 1500}); self.assertTrue(self.r.publish())
        self.r.db.set('ev_settings', {'quote_age_ms': 500}); self.assertFalse(self.r.publish())
    def test_gate_cannot_refuse_on_depth_when_the_executor_would_send(self):
        self.r.books.apply(_snap('tokUP', .4, qty=1.)); self.r.books.terms['tokUP'] = (.01, 1, .07, 1)
        self.r.db.set('next_stake', 10.)
        q = self.r.books.quote('tokUP', 2.0)
        with self.assertRaises(ValueError) as e: C.order_plan(q, self.r.books.terms['tokUP'], 10., _decision(), 1)
        self.assertIn('book too thin', str(e.exception), 'the book IS thin for a FOK broker')
        self.assertFalse(self.r.executor.require_depth)
        out = self.r._gate_on_padded_ev(self.ep, _decision())
        self.assertEqual(out.get('ev_gate'), 'pass', out.get('reason'))
    def test_dashboard_comment_is_now_true(self):
        import poly_dashboard as D
        src = pathlib.Path(D.__file__).read_text()
        self.assertIn('12.9.0', src.split("if 'quote_age_ms' in p:")[1].split('qa=float')[0])


class DashboardLatencyFields(unittest.TestCase):
    """Item 6. exchange_latency_ms was read by the page and set nowhere; the
    "N ms old" number is spot ARRIVAL age (trade silence), now labelled so."""
    def test_exchange_latency_is_the_feeds_event_lag(self):
        import btc_model_v12_polymarket as E, poly_dashboard as D
        r = E.PolyRunner.__new__(E.PolyRunner); h = F.FeedHealth(); now = time.time()
        for n, lag in (('spot', .123), ('perp', .050), ('depth', .080)): h.note(n, event_ms=(now-lag)*1000, now=now)
        r.health = h; r.books = types.SimpleNamespace(health=lambda: {})
        ui = D.Dashboard.__new__(D.Dashboard); ui.r = r
        fs = ui.feed_state()
        self.assertEqual(fs['exchange_latency_ms'], 123)
        self.assertIn('last_event_age_ms', fs); self.assertIn('event_lag_s', fs)
    def test_page_labels_and_poll_interval(self):
        import poly_dashboard as D
        html = pathlib.Path(D.__file__).with_name('dashboard_html.html').read_text()
        self.assertIn("'quiet '", html)          # 12.11.3: silence in seconds, labelled as silence
        self.assertIn("'lag '", html)             # and the real feed lag leads the line
        self.assertIn('setTimeout(pollState,1000)', html); self.assertNotIn('setTimeout(pollState,250)', html)


class DeadCodeRemoved(unittest.TestCase):
    """Item 7. audit_deadcode 1a / 1b / 3c."""
    def test_paper_broker_account_snapshot_is_gone(self):
        self.assertFalse(hasattr(C.PaperBroker, 'account_snapshot'))
    def test_bookcache_clear_is_gone(self):
        self.assertFalse(hasattr(C.BookCache, 'clear'))
    def test_mode_flag_is_accepted_but_marked_vestigial(self):
        import btc_model_v12_polymarket as E, sys
        src = pathlib.Path(E.__file__).read_text(); line = [l for l in src.splitlines() if "'--mode'" in l][0]
        self.assertIn('argparse.SUPPRESS', line)
        sys.argv = ['x', '--mode', 'pnl']; self.assertEqual(E.args().mode, 'pnl', 'existing launch lines keep working')
    def test_runner_header_marks_standalone_only_code(self):
        import btc_model_v10_runner as U
        head = pathlib.Path(U.__file__).read_text()[:4000]
        for name in ('STANDALONE-ONLY', 'Store', 'Runner.decide_loop', 'Runner.venue', 'Runner.grade_loop'): self.assertIn(name, head)


class Build1290(unittest.TestCase):
    def test_a_12_8_11_database_opens_additively(self):
        path = tempfile.mktemp(suffix='.sqlite3'); db = C.Journal(path, 'PAPER', 'abc')
        db.set('build', '12.8.11'); db.c.close(); db = C.Journal(path, 'PAPER', 'abc')
        self.assertEqual(db.get('build'), '12.24.2'); db.c.close(); os.unlink(path)


# ---------------------------------------------------------------- 12.10.0
class RefProxy12100(unittest.TestCase):
    """R-16: settlement-reference proxy features are logged beside the model's own, never inside FEATURES."""
    def test_twap_reference_features(self):
        import btc_model_v10 as M
        US = M.US; st = M.FeatureState(); op = 1_000_000 * US
        st.on_spot_trade(op - 90 * US, 100.0, 1.0, False)   # in force through the pre-open minute
        st.on_spot_trade(op, 102.0, 1.0, False)               # candle open trade
        st.on_spot_trade(op + 30 * US, 104.0, 1.0, True)      # now
        f = st.features(op, op + 30 * US)
        self.assertNotIn('ref_open_bps', M.FEATURES)
        self.assertAlmostEqual(f['ref_open_bps'], 200.0, places=6)    # open 102 vs pre-open TWAP 100
        self.assertAlmostEqual(f['ref_move_bps'], 100.0, places=6)    # last-60s TWAP 101 vs 100
        self.assertAlmostEqual(f['ref_gap_bps'], 400.0, places=6)     # spot 104 vs 100
        self.assertAlmostEqual(f['move_bps'], (104 / 102 - 1) * 1e4, places=6)   # untouched
    def test_no_pre_open_trade_falls_back_to_open(self):
        import btc_model_v10 as M
        US = M.US; st = M.FeatureState(); op = 1_000_000 * US
        st.on_spot_trade(op, 102.0, 1.0, False); st.on_spot_trade(op + 5 * US, 103.0, 1.0, False)
        f = st.features(op, op + 5 * US)
        self.assertAlmostEqual(f['ref_open_bps'], 0.0, places=9)
        self.assertTrue(math.isfinite(f['ref_move_bps']) and math.isfinite(f['ref_gap_bps']))


# ---------------------------------------------------------------- 12.11.0
class RefFeed12110(unittest.TestCase):
    """The venue's settlement-reference stream: used when it covers the window, proxy otherwise,
    and the model json's open_reference flag decides whether the candle 'open' is the settlement line."""
    def _state(self):
        import btc_model_v10 as M
        US = M.US; st = M.FeatureState(); op = 1_000_000 * US
        st.on_spot_trade(op - 90 * US, 100.0, 1.0, False); st.on_spot_trade(op, 102.0, 1.0, False)
        st.on_spot_trade(op + 30 * US, 104.0, 1.0, True)
        return M, US, st, op
    def test_proxy_when_no_reference_samples(self):
        M, US, st, op = self._state(); f = st.features(op, op + 30 * US)
        self.assertEqual(f['ref_src'], 0.0); self.assertAlmostEqual(f['ref_open_bps'], 200.0, places=6)
    def test_reference_stream_used_when_it_covers_the_window(self):
        M, US, st, op = self._state()
        for k in range(-70, 31): st.on_ref_price(op + k * US, 101.0 if k < 0 else 103.0)   # 1/s, covers both windows
        f = st.features(op, op + 30 * US)
        self.assertEqual(f['ref_src'], 1.0)
        # 12.20.0: the feed is instant; the line is its 60 s TWAP. At the open: 101 over the whole
        # pre-open minute. Now: 30 s of 101 and 30 s of 103 = 102.
        self.assertAlmostEqual(f['ref_open_bps'], (102 / 101 - 1) * 1e4, places=6)        # first trade vs TWAP60 at open (101)
        self.assertAlmostEqual(f['ref_move_bps'], (102 / 101 - 1) * 1e4, places=6)        # TWAP60 now (102) vs at open (101)
        self.assertAlmostEqual(f['ref_open'], 101.0, places=6); self.assertAlmostEqual(f['ref_now'], 102.0, places=6)
        self.assertAlmostEqual(f['ref_inst'], 103.0, places=6); self.assertEqual(f['ref_inst_ok'], 1.0)
        self.assertAlmostEqual(f['move_bps'], (104 / 102 - 1) * 1e4, places=6)            # v10 as trained: untouched
    def test_stale_reference_falls_back(self):
        M, US, st, op = self._state()
        for k in range(-70, 10): st.on_ref_price(op + k * US, 101.0)                        # stops 20 s before now
        f = st.features(op, op + 30 * US); self.assertEqual(f['ref_src'], 0.0)
    def test_open_reference_twap60_moves_the_open(self):
        M, US, st, op = self._state()
        for k in range(-70, 31): st.on_ref_price(op + k * US, 101.0 if k < 0 else 103.0)
        st.open_ref = 'twap60'; f = st.features(op, op + 30 * US)
        self.assertAlmostEqual(f['move_bps'], (104 / 101 - 1) * 1e4, places=6)            # measured from the settlement line (TWAP60 at open)
        self.assertAlmostEqual(f['ref_open_bps'], (102 / 101 - 1) * 1e4, places=6)        # still reports first trade vs line
    def test_feed_is_averaged_over_the_window(self):
        # 12.20.0 (T0): the feed is the instant price, so the line is its TWAP over the window.
        M, US, st, op = self._state()
        for k in range(-70, 31): st.on_ref_price(op + k * US, 100.0 + k)                   # ramp
        f = st.features(op, op + 30 * US)
        line_open = 100.0 + sum(range(-60, 0)) / 60.0                                      # samples -60..-1 in force over [op-60, op)
        line_now = 100.0 + sum(range(-30, 30)) / 60.0                                      # samples -30..29 over [op-30, op+30)
        self.assertAlmostEqual(f['ref_gap_bps'], (104 / line_open - 1) * 1e4, places=6)
        self.assertAlmostEqual(f['ref_move_bps'], (line_now / line_open - 1) * 1e4, places=6)
        self.assertAlmostEqual(f['ref_inst'], 130.0, places=6)                              # the instant feed value is kept beside the line
        self.assertFalse(M.FeatureState.REF_IS_TWAP)
    def test_model_json_may_list_extra_features(self):
        import btc_model_v10 as M, json, pathlib, tempfile
        j = json.loads((pathlib.Path(__file__).resolve().parent / 'model_v10.json').read_text())
        j['features'] = j['features'] + ['ref_gap_bps']; j['coef'] = list(j['coef']) + [0.0]
        j['scaler_mean'] = list(j['scaler_mean']) + [0.0]; j['scaler_scale'] = list(j['scaler_scale']) + [1.0]
        path = tempfile.mktemp(suffix='.json'); pathlib.Path(path).write_text(json.dumps(j))
        m = M.Model(path); self.assertEqual(m.features[-1], 'ref_gap_bps')
        M2, US, st, op = self._state(); d = m.decide(st, op, op + 30 * US); self.assertIn('p', d)
        j['features'] = j['features'] + ['not_a_feature']; j['coef'].append(0.0); j['scaler_mean'].append(0.0); j['scaler_scale'].append(1.0)
        pathlib.Path(path).write_text(json.dumps(j))
        with self.assertRaises(AssertionError): M.Model(path)
    def test_model_flag_default_and_copy(self):
        import btc_model_v10 as M, pathlib
        m = M.Model(pathlib.Path(__file__).resolve().parent / 'model_v10.json')
        self.assertEqual(m.open_ref, 'first_trade')
        M2, US, st, op = self._state(); st.open_ref = 'twap60'; st.set_venue(0.5, 0.49, 0.51, 0.5) if hasattr(st, 'set_venue') else None
        m.decide(st, op, op + 30 * US); self.assertEqual(st.open_ref, 'first_trade')          # decide() enforces train == serve
    def test_ref_samples_parser(self):
        import btc_model_v12_polymarket as E
        f = E.PolyRunner.ref_samples if hasattr(E, 'PolyRunner') else None
        cls = next(c for c in vars(E).values() if isinstance(c, type) and hasattr(c, 'ref_samples'))
        j = {'topic': 'crypto_prices_chainlink', 'type': 'update', 'payload': {'symbol': 'btc/usd', 'value': 75581.97, 'timestamp': 1789516920123}}
        self.assertEqual(cls.ref_samples(j), [(1789516920123000, 75581.97)])
        self.assertEqual(cls.ref_samples({'payload': [{'symbol': 'eth/usd', 'value': 1, 'timestamp': 1}]}), [])
        self.assertEqual(cls.ref_samples({'payload': {'symbol': 'BTC-USD', 'value': '7', 'timestamp': 1789516920}}), [(1789516920000000, 7.0)])
        self.assertEqual(cls.ref_samples('garbage'), [])
    def test_ref_samples_fixed_point(self):
        import btc_model_v12_polymarket as E
        cls = next(c for c in vars(E).values() if isinstance(c, type) and hasattr(c, 'ref_samples'))
        j = {'topic': 'crypto_prices_chainlink', 'type': 'update', 'payload': {'symbol': 'btc/usd', 'full_accuracy_value': '75409056369963195000000', 'timestamp': 1789516920000}}
        (t, v), = cls.ref_samples(j); self.assertEqual(t, 1789516920000000); self.assertAlmostEqual(v, 75409.056369963195, places=6)


class BlankFrame12112(unittest.TestCase):
    """12.11.2: a blank or non-JSON frame is skipped, not treated as a dead socket.

    The venue's RTDS sends an empty frame as its subscribe ack; json.loads('') raised and
    run_stream reconnected on every one of them (591 reconnects live, zero data delivered)."""
    def _run(self, frames):
        import asyncio, poly_feeds as F
        got = []; sent = []
        class W:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): return False
            async def send(s, m): sent.append(m)
            async def recv(s):
                if frames: return frames.pop(0)
                raise asyncio.CancelledError
        class WS:
            def connect(s, *a, **k): return W()
        real = F.websockets if hasattr(F, 'websockets') else None
        import sys, types
        mod = types.ModuleType('websockets'); mod.connect = lambda *a, **k: W()
        old = sys.modules.get('websockets'); sys.modules['websockets'] = mod
        h = F.FeedHealth(['ref'])
        try:
            asyncio.run(F.run_stream('ref', got.append, h, event_key=(), urls=['wss://x/'], subscribe={'a': 1}))
        except asyncio.CancelledError:
            pass
        finally:
            if old is not None: sys.modules['websockets'] = old
            else: sys.modules.pop('websockets', None)
        return got, h, sent
    def test_blank_and_garbage_frames_do_not_reconnect(self):
        got, h, sent = self._run(['', '   ', 'not json', b'', '{"payload":{"symbol":"btc/usd","value":1,"timestamp":1}}'])
        self.assertEqual(len(got), 1)                      # only the real frame reached the handler
        self.assertEqual(h.reconnects.get('ref', 0), 0)    # and no reconnect was counted
        self.assertEqual(h.skipped.get('ref', 0), 1)       # 'not json' counted as skipped
        self.assertEqual(json.loads(sent[0]), {'a': 1})    # subscribe frame was sent


class StatusLine12113(unittest.TestCase):
    """The top line leads with feed lag; trade silence is seconds, and labelled as silence."""
    def test_status_line_wording(self):
        src = (pathlib.Path(__file__).resolve().parent / 'dashboard_html.html').read_text()
        i = [n for n, l in enumerate(src.splitlines()) if "text('topStatus'" in l][0]
        line = ' '.join(src.splitlines()[i:i + 2])      # the call spans two lines
        self.assertIn('exchange_latency_ms', line)
        self.assertIn("'lag '", line)
        self.assertIn("'quiet '", line)
        self.assertNotIn('since last trade', src)


class EFFloor12120(unittest.TestCase):
    """The owner's bankroll floor: EF off below it, on EQUITY, only after it persists."""
    def _runner(self, cash, open_value, floor=30.0, live=True):
        import btc_model_v12_polymarket as E, poly_core as C, tempfile, types
        path = tempfile.mktemp(suffix='.sqlite3'); db = C.Journal(path, 'LIVE' if live else 'PAPER', 'abc')
        db.set('ef_enabled', True)
        if floor is not None: db.set('ef_cash_floor', floor)
        if open_value is not None:
            db.sql('INSERT INTO venue_state(ts,cash,open_value) VALUES(?,?,?)', (time.time(), cash, open_value))
        r = types.SimpleNamespace(db=db, cash=cash, a=types.SimpleNamespace(live=live),
                                  _floor_reads=0, _floor_since=None,
                                  FLOOR_CONFIRMATIONS=E.PolyRunner.FLOOR_CONFIRMATIONS,
                                  FLOOR_MIN_SPAN_S=E.PolyRunner.FLOOR_MIN_SPAN_S,
                                  FLOOR_OPEN_VALUE_MAX_AGE_S=E.PolyRunner.FLOOR_OPEN_VALUE_MAX_AGE_S)
        r._floor_check = types.MethodType(E.PolyRunner._floor_check, r)
        return r, db, path
    def _hammer(self, r, reads, age_s):
        for _ in range(reads):
            r._floor_check()
            if r._floor_since is not None: r._floor_since -= age_s / max(reads, 1)
    def test_disables_ef_only_after_confirmations_and_time(self):
        r, db, path = self._runner(cash=10.0, open_value=5.0)          # equity 15 < 30
        r._floor_check(); self.assertIs(db.get('ef_enabled'), True)     # one read is not enough
        self._hammer(r, 8, 600)
        self.assertIs(db.get('ef_enabled'), False)
        row = [json.loads(x[2]) for x in db.sql('SELECT * FROM diagnostics') if 'EF_FLOOR' in (x[2] or '')]
        self.assertEqual(row[0]['floor'], 30.0); self.assertAlmostEqual(row[0]['equity'], 15.0)
        self.assertIs(db.get('master', None), None)                     # master untouched
        db.c.close(); os.unlink(path)
    def test_pending_payout_does_not_trip_it(self):
        r, db, path = self._runner(cash=2.0, open_value=40.0)           # cash low, equity 42
        self._hammer(r, 10, 900); self.assertIs(db.get('ef_enabled'), True)
        db.c.close(); os.unlink(path)
    def test_unknown_open_value_acts_on_nothing(self):
        r, db, path = self._runner(cash=1.0, open_value=None)
        self._hammer(r, 10, 900); self.assertIs(db.get('ef_enabled'), True)
        db.c.close(); os.unlink(path)
    def test_no_floor_configured_is_a_no_op(self):
        r, db, path = self._runner(cash=1.0, open_value=1.0, floor=None)
        self._hammer(r, 10, 900); self.assertIs(db.get('ef_enabled'), True)
        db.c.close(); os.unlink(path)
    def test_recovery_resets_and_paper_is_untouched(self):
        r, db, path = self._runner(cash=10.0, open_value=5.0)
        self._hammer(r, 4, 400); self.assertIs(db.get('ef_enabled'), True)
        r.cash = 50.0; db.sql('INSERT INTO venue_state(ts,cash,open_value) VALUES(?,?,?)', (time.time(), 50.0, 5.0))
        r._floor_check(); self.assertEqual(r._floor_reads, 0); self.assertIsNone(r._floor_since)
        db.c.close(); os.unlink(path)
        r2, db2, p2 = self._runner(cash=1.0, open_value=1.0, live=False)
        self._hammer(r2, 10, 900); self.assertIs(db2.get('ef_enabled'), True)
        db2.c.close(); os.unlink(p2)


class SubmitBook12121(unittest.TestCase):
    """12.12.1: the order row carries an independent book read stamped at submit."""
    def test_submit_book_recorded_with_size(self):
        import poly_core as C, tempfile, asyncio
        path = tempfile.mktemp(suffix='.sqlite3'); db = C.Journal(path, 'PAPER', 'abc')
        books = C.BookCache()
        snap = dict(event_type='book', asset_id='up', timestamp=str(int(time.time() * 1000)),
                    asks=[dict(price='0.40', size='120')], bids=[dict(price='0.39', size='80')])
        books.apply(snap); books.terms['up'] = (.01, 1, .07, 1)
        d = dict(fire=True, side='UP', p=.8, threshold=.2, ask=.4, sec=30, ev=.9)
        ex = C.Executor(db, books, C.PaperBroker(books, db)); ep = int(time.time()) - 30
        asyncio.run(ex.fire(ep, d, 'up', 'c', 10, lambda: d))
        t = json.loads(db.sql('SELECT timing_json FROM orders')[0][0])
        self.assertIn('submit_book', t)
        sb = t['submit_book']
        self.assertAlmostEqual(sb['ask'], 0.40); self.assertAlmostEqual(sb['bid'], 0.39)
        self.assertAlmostEqual(float(sb['size']), 120.0)     # displayed size, the thing a fill needs
        self.assertIsNotNone(sb['ts_ms']); self.assertIsNotNone(sb['age_ms'])
        db.c.close(); os.unlink(path)


class MasterWatch12122(unittest.TestCase):
    """12.12.2: a live engine sitting disarmed says so; it never arms anything."""
    def _runner(self, master, live=True):
        import btc_model_v12_polymarket as E, poly_core as C, tempfile, types
        path = tempfile.mktemp(suffix='.sqlite3'); db = C.Journal(path, 'LIVE' if live else 'PAPER', 'abc')
        db.set('master', master)
        r = types.SimpleNamespace(db=db, a=types.SimpleNamespace(live=live),
                                  _master_off_since=None, _master_off_said=0.0,
                                  MASTER_OFF_WARN_S=E.PolyRunner.MASTER_OFF_WARN_S,
                                  MASTER_OFF_REPEAT_S=E.PolyRunner.MASTER_OFF_REPEAT_S)
        r._master_watch = types.MethodType(E.PolyRunner._master_watch, r)
        return r, db, path
    def _rows(self, db):
        return [json.loads(x[2]) for x in db.sql('SELECT * FROM diagnostics') if 'MASTER_OFF' in (x[2] or '')]
    def test_warns_once_past_the_window_and_counts_gated_fires(self):
        r, db, path = self._runner(False)
        r._master_watch(); self.assertEqual(self._rows(db), [])          # first read only starts the clock
        db.sql('INSERT INTO diagnostics VALUES(?,?,?)', (time.time(), 0, json.dumps({'fire': True})))
        r._master_off_since -= 400                                       # past MASTER_OFF_WARN_S
        r._master_watch(); rows = self._rows(db)
        self.assertEqual(len(rows), 1); self.assertGreaterEqual(rows[0]['off_s'], 400)
        self.assertEqual(rows[0]['fires_gated'], 1); self.assertIs(rows[0]['acted'], False)
        r._master_watch(); self.assertEqual(len(self._rows(db)), 1)      # quiet until the repeat window
        self.assertIs(db.get('master'), False)                           # never arms anything
        db.c.close(); os.unlink(path)
    def test_master_on_and_paper_are_silent(self):
        r, db, path = self._runner(True)
        r._master_watch(); r._master_watch(); self.assertEqual(self._rows(db), [])
        db.c.close(); os.unlink(path)
        r2, db2, p2 = self._runner(False, live=False)
        r2._master_watch(); r2._master_off_since = time.time() - 4000; r2._master_watch()
        self.assertEqual(self._rows(db2), []); db2.c.close(); os.unlink(p2)
    def test_recovery_clears_the_clock(self):
        r, db, path = self._runner(False)
        r._master_watch(); self.assertIsNotNone(r._master_off_since)
        db.set('master', True); r._master_watch(); self.assertIsNone(r._master_off_since)
        db.c.close(); os.unlink(path)


class VenueP12130(unittest.TestCase):
    """12.13.0 (R-23): a json may say the decision reads the venue price instead of the model."""
    def _state(self, ask_up=0.40, ask_dn=0.62):
        import btc_model_v10 as M
        US = M.US; st = M.FeatureState(); op = 1_000_000 * US
        for k in range(-120, 31):
            st.on_spot_trade(op + k * US, 100.0 + 0.01 * k, 1.0, k % 2 == 0)
        st.on_venue_quote(ask_up, ask_up - 0.01, ask_dn, ask_dn - 0.01)
        return M, US, st, op
    def test_venue_json_uses_the_book_and_v10_does_not(self):
        import btc_model_v10 as M, pathlib
        here = pathlib.Path(__file__).resolve().parent
        M2, US, st, op = self._state()
        f = st.features(op, op + 30 * US)
        venue = M.Model(here / 'model_venue.json'); model = M.Model(here / 'model_v10.json')
        self.assertEqual(venue.p_source, 'venue'); self.assertEqual(model.p_source, 'model')
        pv = f['p_venue']
        self.assertAlmostEqual(venue.p_up(f), min(0.98, max(0.02, pv)), places=9)
        self.assertNotAlmostEqual(model.p_up(f), venue.p_up(f), places=6)
        self.assertEqual(venue.features, model.features)          # one field differs, nothing else
        self.assertEqual(list(venue.coef), list(model.coef))
    def test_no_two_sided_book_refuses_instead_of_guessing(self):
        import btc_model_v10 as M, pathlib, numpy as np
        here = pathlib.Path(__file__).resolve().parent
        M2, US, st, op = self._state()
        st.on_venue_quote(float('nan'), float('nan'), float('nan'), float('nan'))
        venue = M.Model(here / 'model_venue.json')
        d = venue.decide(st, op, op + 30 * US)
        self.assertFalse(d['fire']); self.assertIn('venue probability', d['reason'])
    def test_unknown_p_source_is_rejected_at_load(self):
        import btc_model_v10 as M, json, pathlib, tempfile
        j = json.loads((pathlib.Path(__file__).resolve().parent / 'model_v10.json').read_text())
        j['p_source'] = 'oracle'; p = tempfile.mktemp(suffix='.json'); pathlib.Path(p).write_text(json.dumps(j))
        with self.assertRaises(AssertionError): M.Model(p)


class LaneSeed12141(unittest.TestCase):
    """A restarted lane must not spend two hours with a meaningless volume_ratio.

    Pinned because the failure is silent: the cold lane reports a volume_ratio
    like any other, it is just computed over 4 candles instead of 24, and the
    only visible symptom is MAIN never calling (or calling far too often).
    """
    def _runner(self, n_candles):
        import btc_model_v12_polymarket as E, poly_lanes
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = C.Journal(str(pathlib.Path(temp.name) / 'seed.db'), 'PAPER', 'h')
        self.addCleanup(db.c.close)
        for i in range(n_candles):
            ep = 1789500000 + i * 300
            db.sql('INSERT OR REPLACE INTO candles VALUES(?,?,?,?,?,?)',
                   (ep, 100000.0, 100050.0, 99950.0, 100010.0, 25.0 + i))
        r = E.PolyRunner.__new__(E.PolyRunner)
        r.db = db; r.lanes = poly_lanes.LaneEngine()
        return r, db

    def test_seeds_the_lane_from_the_journal(self):
        r, _ = self._runner(30)
        r._seed_lane_history()
        self.assertEqual(len(r.lanes.closed), 30)

    def test_keeps_journal_order_oldest_first(self):
        r, _ = self._runner(30)
        r._seed_lane_history()
        eps = [c['time'] for c in r.lanes.closed]
        self.assertEqual(eps, sorted(eps), 'the deque must run oldest -> newest')

    def test_a_cold_lane_is_recorded_not_hidden(self):
        r, db = self._runner(4)
        r._seed_lane_history()
        rows = [json.loads(x[0]) for x in
                db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%LANE_SEED_COLD%'")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['seeded'], 4); self.assertEqual(rows[0]['need'], 20)

    def test_a_warm_lane_files_no_cold_row(self):
        r, db = self._runner(24)
        r._seed_lane_history()
        self.assertEqual(db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%LANE_SEED_COLD%'"), [])

    def test_seeding_changes_the_volume_median_the_gate_reads(self):
        """The defect itself: 4 candles give a median off the true one."""
        cold, _ = self._runner(30)                      # not seeded
        warm, _ = self._runner(30); warm._seed_lane_history()
        for i in (26, 27, 28, 29):                      # the handful a cold lane sees live
            cold.lanes.on_closed_candle(dict(time=(1789500000 + i * 300) * 1000, open=100000.0,
                                             high=100050.0, low=99950.0, close=100010.0,
                                             volume=25.0 + i))
        live = dict(time=1789509000000, open=100000.0, high=100050.0, low=99950.0,
                    close=100010.0, volume=30.0)
        cold.lanes.on_candle(dict(live)); warm.lanes.on_candle(dict(live))
        self.assertNotEqual(round(cold.lanes.volume_ratio(150.0), 4),
                            round(warm.lanes.volume_ratio(150.0), 4),
                            'if these matched, the seed would be doing nothing')

    def test_missing_candles_table_does_not_stop_the_engine(self):
        import btc_model_v12_polymarket as E, poly_lanes
        r = E.PolyRunner.__new__(E.PolyRunner)
        r.lanes = poly_lanes.LaneEngine()
        r.db = types.SimpleNamespace(sql=lambda *a: (_ for _ in ()).throw(RuntimeError('no such table')))
        r._seed_lane_history()                           # must not raise
        self.assertEqual(len(r.lanes.closed), 0)


class ShadowStale12150(unittest.TestCase):
    """The freshness bar blocks ~1,228 decide rows and we cannot grade any of them.

    Task 116 could only measure book age on trades we TOOK, and found it carries
    no information there. Whether the BLOCKED rows would have paid is a separate
    question with no data behind it, because decide_now returns before the model
    is consulted. _shadow_stale closes that by logging the decision that would
    have been made. These tests pin the two things that make it safe: it writes,
    and it cannot trade.
    """
    def _runner(self, ask_up=0.40, ask_dn=0.62, age_ms=9000.0, both=True):
        import btc_model_v12_polymarket as E
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = C.Journal(str(pathlib.Path(temp.name) / 's.db'), 'PAPER', 'h')
        self.addCleanup(db.c.close)
        r = E.PolyRunner.__new__(E.PolyRunner)
        r.db = db; r._shadow_at = 0.0; r.market = {300: ('UP_TOK', 'DN_TOK')}
        r.quote_age_s = lambda: 0.75
        r.ev_setting = lambda: ('regime', None)
        q = {'UP_TOK': {'ask': ask_up, 'bid': ask_up - 0.02, 'age_ms': age_ms},
             'DN_TOK': {'ask': ask_dn, 'bid': ask_dn - 0.02, 'age_ms': age_ms}}
        if not both: q.pop('DN_TOK')
        r.books = types.SimpleNamespace(quote=lambda t, age: q.get(t))
        self.seen = []
        r.st = types.SimpleNamespace(on_venue_quote=lambda *a: self.seen.append(a))
        r.m = types.SimpleNamespace(decide=lambda *a, **k: dict(
            fire=True, side='UP', p=0.61, ask=ask_up, ev=0.18, threshold=0.25))
        return r, db

    def rows(self, db, kind='SHADOW_STALE'):
        return [json.loads(x[0]) for x in
                db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%" + kind + "%'")]

    def test_writes_the_decision_it_would_have_made(self):
        r, db = self._runner()
        r._shadow_stale(300, 1000.0)
        got = self.rows(db)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0]['fire']); self.assertEqual(got[0]['side'], 'UP')
        self.assertAlmostEqual(got[0]['ev'], 0.18)
        self.assertAlmostEqual(got[0]['age_ms'], 9000.0)
        self.assertAlmostEqual(got[0]['bar_ms'], 750.0)

    def test_restores_the_venue_quote_so_the_live_path_is_unchanged(self):
        r, _ = self._runner()
        r._shadow_stale(300, 1000.0)
        self.assertEqual(self.seen[-1], (None, None, None, None),
                         'publish() zeroed the quote; the shadow must leave it zeroed')

    def test_a_genuinely_one_sided_book_is_not_shadowed(self):
        r, db = self._runner(both=False)
        r._shadow_stale(300, 1000.0)
        self.assertEqual(self.rows(db), [], 'nothing to shadow without both sides')

    def test_rate_limited(self):
        r, db = self._runner()
        for t in (1000.0, 1001.0, 1002.0, 1004.9):
            r._shadow_stale(300, t)
        self.assertEqual(len(self.rows(db)), 1, 'one row per SHADOW_EVERY_S')
        r._shadow_stale(300, 1006.0)
        self.assertEqual(len(self.rows(db)), 2)

    def test_a_raising_model_is_recorded_and_does_not_escape(self):
        r, db = self._runner()
        def boom(*a, **k): raise ValueError('bad features')
        r.m = types.SimpleNamespace(decide=boom)
        r._shadow_stale(300, 1000.0)                       # must not raise
        self.assertEqual(len(self.rows(db, 'SHADOW_STALE_ERROR')), 1)
        self.assertEqual(self.seen[-1], (None, None, None, None))

    def test_it_cannot_reach_the_executor(self):
        """The safety property: instrumentation, not a trade."""
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner._shadow_stale)
        for forbidden in ('fire(', 'order_plan', 'reserve(', 'self.ex', 'broker'):
            self.assertNotIn(forbidden, body,
                             'the shadow path must never touch the order path: ' + forbidden)


class DecisionFeaturesAreTheDecisions12151(unittest.TestCase):
    """The journal must record the vector the model DECIDED on, not a later read.

    Until 12.15.1 the fire path replaced d['features'] with a fresh features()
    call taken after publish(), decide(), _calibrate() and the padded-EV gate.
    On the live journal the decision's own rv60 disagreed with features['rv60']
    on 43 of 90 fired diagnostics rows and 37 of 88 signals rows, while all
    4,775 non-fired rows agreed exactly - so half the fired audit trail could
    not be replayed, and every study that replayed it graded the wrong inputs.
    """
    def test_the_fire_path_does_not_overwrite_the_decision_features(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner._decide_once)
        after = body.split('no_terms', 1)[-1]
        self.assertNotIn("d['features']=", after,
                         'the pre-submit read must not replace the decision it is submitting')
        self.assertIn("d['submit_features']=", after,
                      'it is still recorded, under its own name')

    def test_the_decision_features_carry_ts_ms(self):
        """The overwrite dropped ts_ms, which is why EF orders logged signal_ts_ms null."""
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.decide_now)
        self.assertIn("d['features']['ts_ms']", body)


class AuditFixes12152(unittest.TestCase):
    """Regressions for the 12.15.2 batch out of the nine-way audit."""

    def test_accuracy_mode_threshold_is_a_number(self):
        """It was a dict, and order_plan calls math.isfinite on it -> TypeError,
        which neither _gate_on_padded_ev (ValueError) nor fire (ValueError,KeyError)
        catches. One dropdown click stopped EF, MAIN and REVERSAL together."""
        import btc_model_v10 as M, poly_core as PC
        m = M.Model(str(pathlib.Path(__file__).parent / 'model_v10.json'))
        feat = {k: 0.0 for k in m.features}
        feat.update(rv60=0.25, sec_left=120.0, _ask_up=0.40, _ask_dn=0.62, _venue_ok=True)
        class St:
            def features(self, *a, **k): return feat
        for mode in ('pnl', 'accuracy'):
            d = m.decide(St(), 0, 0, mode=mode)
            self.assertIsInstance(d['threshold'], float, mode)
            self.assertTrue(math.isfinite(d['threshold']), mode)
        acc = m.decide(St(), 0, 0, mode='accuracy')
        self.assertEqual(set(acc['floors']), {'conf_floor', 'ev_floor'})
        self.assertAlmostEqual(acc['threshold'], acc['floors']['ev_floor'])

    def test_the_floor_treats_a_stale_open_value_as_unknown(self):
        import btc_model_v12_polymarket as E
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = C.Journal(str(pathlib.Path(temp.name) / 'f.db'), 'LIVE', 'h')
        self.addCleanup(db.c.close)
        db.set('ef_enabled', True); db.set('ef_cash_floor', 30.0)
        old = time.time() - 10 * E.PolyRunner.FLOOR_OPEN_VALUE_MAX_AGE_S
        db.sql('INSERT INTO venue_state(ts,cash,open_value) VALUES(?,?,?)', (old, 5.0, 0.0))
        r = types.SimpleNamespace(db=db, cash=5.0, a=types.SimpleNamespace(live=True),
                                  _floor_reads=0, _floor_since=None,
                                  FLOOR_CONFIRMATIONS=E.PolyRunner.FLOOR_CONFIRMATIONS,
                                  FLOOR_MIN_SPAN_S=E.PolyRunner.FLOOR_MIN_SPAN_S,
                                  FLOOR_OPEN_VALUE_MAX_AGE_S=E.PolyRunner.FLOOR_OPEN_VALUE_MAX_AGE_S)
        r._floor_check = types.MethodType(E.PolyRunner._floor_check, r)
        for _ in range(20): r._floor_check()
        self.assertIs(db.get('ef_enabled'), True,
                      'equity is unknown when open_value is stale; unknown must not act')
        self.assertEqual(r._floor_reads, 0)

    def test_the_monitors_are_not_inside_the_venue_try(self):
        """A metadata timeout used to skip the owner's only automatic stop."""
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.housekeeping)
        head, _, tail = body.partition("except Exception as e: self.error='Metadata/balance: '")
        self.assertIn('_floor_check', tail, 'the floor must run after the venue handler, not inside it')
        self.assertNotIn('_floor_check', head)

    def test_gathered_tasks_are_supervised(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.main)
        for task in ('reconcile_loop', 'grade_loop', 'venue_truth_loop', 'decide_loop'):
            self.assertIn(f"_supervise('{task}'", body, task)

    def test_a_crashing_task_is_recorded_and_restarted(self):
        import btc_model_v12_polymarket as E
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = C.Journal(str(pathlib.Path(temp.name) / 's.db'), 'PAPER', 'h')
        self.addCleanup(db.c.close)
        r = E.PolyRunner.__new__(E.PolyRunner); r.db = db; r.error = ''
        r.SUPERVISE_BACKOFF_S = 0.0
        self.calls = 0
        async def flaky():
            self.calls += 1
            if self.calls < 3: raise RuntimeError('boom')
            raise asyncio.CancelledError()
        async def go():
            try: await r._supervise('flaky', flaky)
            except asyncio.CancelledError: pass
        asyncio.run(go())
        self.assertEqual(self.calls, 3, 'it must come back rather than take the engine down')
        rows = [json.loads(x[0]) for x in
                db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%TASK_CRASH%'")]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['task'], 'flaky')

    def test_shadow_rows_do_not_count_as_gated_fires(self):
        import inspect, btc_model_v12_polymarket as E
        self.assertIn('SHADOW_STALE', inspect.getsource(E.PolyRunner._master_watch))

    def test_every_stake_mode_obeys_the_operator_bounds(self):
        import inspect, poly_dashboard as D
        body = inspect.getsource(D.Dashboard.update_stake)
        self.assertNotIn("if s['mode']!='ladder': current=max", body,
                         'ladder was exempt from min/max stake')

class AuditFixes12153(unittest.TestCase):
    """Regressions for the 12.15.3 batch."""

    def test_no_fill_is_not_declared_faster_than_a_fill_appears(self):
        import inspect
        from poly_live import LiveBroker
        body = inspect.getsource(LiveBroker.reconcile)
        code = [l for l in body.split(chr(10)) if not l.lstrip().startswith('#')]
        cond = [l for l in code if 'order_missing and not trade_unsettled' in l or 'age>=' in l]
        self.assertTrue(any('ABSENT_PROOF_AGE_S' in l for l in cond))
        self.assertFalse(any('age>=2.0' in l for l in cond),
                         'a real fill needs 6.7s minimum to become visible')

    def test_the_venue_socket_survives_a_blank_frame(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.venue)
        self.assertIn('except ValueError', body, 'a bad frame must not tear the socket down')
        self.assertIn('_venue_skipped', body)

    def test_rearm_refuses_while_an_order_may_be_live(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = C.Journal(str(pathlib.Path(temp.name) / 'r.db'), 'PAPER', 'h')
        self.addCleanup(db.c.close)
        ep = 1789500000
        db.reserve(ep, dict(fire=True, side='UP', p=.8, threshold=.2, ask=.4, sec=30, ev=.9), 'tok', 'cond')
        db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
               " VALUES('o1',?,1,'PENDING','{}',?,0,'','EF')", (ep, time.time()))
        self.assertFalse(db.release(ep, 'SIGNAL_CHANGED', 'EF'),
                         'a PENDING order must not have its signals row deleted')
        self.assertTrue(db.sql('SELECT count(*) FROM signals WHERE epoch=?', (ep,))[0][0])
        rows = [json.loads(x[0]) for x in
                db.sql("SELECT detail FROM diagnostics WHERE detail LIKE '%rearm_refused_order_alive%'")]
        self.assertEqual(len(rows), 1)

    def test_rearm_still_works_when_nothing_is_live(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        db = C.Journal(str(pathlib.Path(temp.name) / 'r2.db'), 'PAPER', 'h')
        self.addCleanup(db.c.close)
        ep = 1789500300
        db.reserve(ep, dict(fire=True, side='UP', p=.8, threshold=.2, ask=.4, sec=30, ev=.9), 'tok', 'cond')
        db.sql("INSERT INTO orders(id,epoch,attempt,status,plan,ts,latency,reason,kind)"
               " VALUES('o2',?,1,'REJECTED','{}',?,0,'','EF')", (ep, time.time()))
        self.assertTrue(db.release(ep, 'SIGNAL_CHANGED', 'EF'))
        self.assertEqual(db.sql('SELECT count(*) FROM signals WHERE epoch=?', (ep,))[0][0], 0)

    def test_event_lag_survives_a_clock_behind_the_exchange(self):
        """Clamping the lag to zero turned the event-lag check off entirely."""
        import poly_feeds as F
        h = F.FeedHealth(('spot',))
        now = time.time()
        for i in range(5):                       # clock 3s behind, feed 2s late
            h.note('spot', (now - 3.0 + 3.0 - 2.0 + i * 0.001) * 1000, now=now + i * 0.001)
        self.assertIsNotNone(h.event_lag('spot'))
        h2 = F.FeedHealth(('spot',))
        h2.note('spot', (now + 3.0) * 1000, now=now)          # pure skew, no real lag
        self.assertAlmostEqual(h2.event_lag('spot'), 0.0, places=3)
        self.assertLess(h2.clock_skew_s, 0)

    def test_arrival_age_uses_the_monotonic_clock_for_real_messages(self):
        import poly_feeds as F
        h = F.FeedHealth(('spot',))
        h.note('spot')
        self.assertIn('spot', h.mono)
        self.assertLess(h.arrival_age('spot'), 1.0)

    def test_model_rejects_a_weights_length_mismatch(self):
        import btc_model_v10 as M
        j = json.loads((pathlib.Path(__file__).parent / 'model_v10.json').read_text())
        j['coef'] = j['coef'][:-1]
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        p = pathlib.Path(temp.name) / 'bad.json'; p.write_text(json.dumps(j))
        with self.assertRaises(AssertionError): M.Model(str(p))

    def test_lane_drops_clear_pending_and_say_why(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.lane_loop)
        self.assertNotIn('if not self.ui.allowed(kind): return\n', body)
        self.assertIn('_lane_drop', body)
        self.assertIn('confirm', inspect.getsource(E.PolyRunner._lane_drop))

    def test_the_lane_median_window_matches_build11(self):
        import poly_lanes as L
        self.assertEqual(L.MEDIAN_WINDOW, 23,
                         'build11 filters a 24-deque that holds the LIVE candle -> 23 closed')

    def test_the_two_attempt_caps_agree(self):
        import poly_lanes as L, poly_core as PC
        self.assertEqual(L.LaneEngine.MAIN_MAX_ATTEMPTS, PC.Journal.MAX_ATTEMPTS_PER_CANDLE)

    def test_a_placed_main_without_a_signal_is_not_a_position(self):
        import poly_lanes as L
        e = L.LaneEngine(); e.main_signal = None
        e.confirm('MAIN', True)
        self.assertIsNone(e.current_main, 'an empty dict here reads as placed at three call sites')

    def test_the_status_line_names_every_stop(self):
        page = (pathlib.Path(__file__).parent / 'dashboard_html.html').read_text()
        for token in ("k+' OFF'", "k+' BLOCKED'", 'HALT: ', 'DAILY STOP', 'floor $'):
            self.assertIn(token, page, token)

    def test_the_poll_callback_fires_once(self):
        page = (pathlib.Path(__file__).parent / 'dashboard_html.html').read_text()
        self.assertIn('function finish(err,data){ if(done)return;', page,
                      'a timeout fired the callback twice and doubled the poll rate')

    def test_the_control_write_path_has_a_generic_handler(self):
        src = (pathlib.Path(__file__).parent / 'poly_dashboard.py').read_text()
        head, _, tail = src.partition('def make_server')
        self.assertIn('status=500', tail, 'a failed control write must not return an HTML traceback')


class AuditFixes12154(unittest.TestCase):
    """Regressions for the 12.15.4 batch: the owner's second audit, run against
    12.9.0. Four of its fifteen were already closed in 12.15.x; these pin the
    eleven that were real and open on the current tree."""

    def test_the_four_main_features_are_computed_not_zeroed(self):
        """2.05 of 8.75 anchor weight was permanently silent."""
        import test_lanes as T, poly_lanes as L
        e = T.engine_with()
        for i in range(40):                                   # let the cluster window fill
            e.on_depth([(100000 - 1, 100.0 + i)] * 5, [(100001, 2.0)] * 5, ts_ms=i * 100)
        e.on_depth([(100000 - 1, 900.0)] * 5, [(100001, 2.0)] * 5, ts_ms=4100)   # a bid spike
        e.on_spot_trade(4100, 100000.0, 1.0, False)            # aggressive buy
        e.on_candle(dict(time=0, open=100000.0, high=100001.0, low=99999.0, close=100000.0, volume=1.0))
        f = e.compute(4150)
        self.assertNotEqual(f['ofi_1s'], 0.0)
        self.assertGreater(f['aggressive_cluster_bias'], 0.0, 'a bid-side spike must read as bid cluster')
        self.assertAlmostEqual(f['volume_profile_delta'], 1.0, 'one aggressive buy, no sells')
        self.assertEqual(L.MODEL_FEATURE_NAMES.index('ofi_1s'), 3)

    def test_ofi_matches_build11_accounting(self):
        import poly_lanes as L
        prev = (100.0, 10.0, 101.0, 10.0)
        self.assertAlmostEqual(L.quote_ofi(prev, (100.0, 12.0, 101.0, 10.0)), 2 * 100.0 / 1000.0)  # bid size up
        self.assertAlmostEqual(L.quote_ofi(prev, (100.0, 10.0, 101.0, 12.0)), -2 * 101.0 / 1000.0) # ask size up
        self.assertAlmostEqual(L.quote_ofi(prev, (100.5, 5.0, 101.0, 10.0)), 5.0 * 100.5 / 1000.0)  # bid price up

    def test_lane_reassess_is_no_longer_frozen(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.lane_loop)
        self.assertIn('still_valid', body)
        self.assertNotIn("lambda k=kind,dd=d: dd if self.ui.allowed(k)", body)

    def test_still_valid_reads_the_tape_without_touching_pending(self):
        import test_lanes as T
        e = T.engine_with()
        fired = T.drive(e, 0, 100060.0, seconds=20, step_ms=100)
        self.assertTrue(fired and fired[0][1]['kind'] == 'MAIN')
        before = dict(e.pending)
        self.assertTrue(e.still_valid('MAIN', 'UP', 20500))
        self.assertFalse(e.still_valid('MAIN', 'DOWN', 20500))
        self.assertEqual(e.pending, before)

    def test_venue_state_is_the_whole_account(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.venue_truth_loop)
        self.assertIn('venue_truth(condition_ids=None)', body)
        self.assertIn('self.venue_state=truth', body)

    def test_a_positions_failure_is_not_an_empty_account(self):
        src = pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertNotIn("list(snap.get('positions') or [])", src)
        self.assertIn("if snap.get('positions') is not None else None", src)

    def test_dashboard_positions_group_by_lane(self):
        import inspect, poly_dashboard as D
        self.assertIn("GROUP BY s.epoch,coalesce(s.kind,'EF')", inspect.getsource(D.Dashboard.positions))

    def test_dashboard_ef_signal_is_ef(self):
        src = pathlib.Path(__file__).with_name('poly_dashboard.py').read_text()
        self.assertIn("WHERE epoch=? AND coalesce(kind,'EF')='EF'", src)

    def test_csv_export_does_not_cross_lanes(self):
        src = pathlib.Path(__file__).with_name('poly_dashboard.py').read_text()
        i = src.index('/export.csv')
        self.assertIn("coalesce(o.kind,'EF')=coalesce(s.kind,'EF')", src[i:i + 1500])
        self.assertIn("JOIN orders o2 ON o2.id=f.order_id", src[i:i + 1500])

    def test_direct_tx_claims_can_leave_review(self):
        import inspect
        from poly_live import LiveBroker
        import btc_model_v12_polymarket as E
        self.assertIn("startswith('tx:'): return 'TX_DIRECT'", inspect.getsource(LiveBroker.claim_state))
        self.assertIn("state=='TX_DIRECT'", inspect.getsource(E.PolyRunner.claim_loop))

    def test_banner_prints_the_real_build(self):
        src = pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertNotIn("print('Polymarket v12.1'", src)
        self.assertIn("self.db.get('build')", src)

    def test_persisted_lane_weights_are_loaded(self):
        src = pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertIn("self.db.get('model_weights')", src)
        self.assertIn("poly_lanes.LaneEngine(_mw", src)

    def test_book_clock_ahead_is_corrected_from_a_window(self):
        """A clock 3 s AHEAD used to fail the freshness bar on fresh data forever."""
        b = C.BookCache()
        now = time.time()
        def ev(t): return dict(event_type='book', asset_id='tok', timestamp=str(int(t * 1000)),
                               asks=[dict(price='0.4', size='100')], bids=[dict(price='0.39', size='100')])
        b.apply(ev(now - 3.0))                       # venue stamp reads 3 s "old": local clock is ahead
        self.assertIsNone(b.quote('tok', max_age=0.75), 'one packet must not be trusted as skew')
        for i in range(200):                         # a full window of the same 3 s floor
            b.apply(ev(time.time() - 3.0 + 0.001 * (i % 5)))
        for _ in range(60): b.apply(ev(time.time() - 3.0))   # let the offset converge on the floor
        self.assertGreater(b.clock_offset, 2.5)
        self.assertIsNotNone(b.quote('tok', max_age=0.75), 'after a window of evidence the skew is removed')

    def test_book_first_old_event_is_still_dropped(self):
        b = C.BookCache()
        b.apply(dict(event_type='book', asset_id='tok', timestamp=str(int((time.time() - 600) * 1000)),
                     asks=[dict(price='0.4', size='1')], bids=[dict(price='0.39', size='1')]))
        self.assertEqual(b.dropped_stale, 1)

    def test_feed_clock_ahead_is_corrected_from_a_window(self):
        import poly_feeds as F
        h = F.FeedHealth(('spot',))
        now = time.time()
        h.note('spot', (now - 3.0) * 1000, now=now)
        self.assertGreater(h.event_lag('spot'), 2.5, 'one lagging packet is lag, not skew')
        for i in range(210): h.note('spot', (now - 3.0 + i * 0.01) * 1000, now=now + i * 0.01)
        for i in range(80): h.note('spot', (now + 5 - 3.0 + i * 0.01) * 1000, now=now + 5 + i * 0.01)
        self.assertLess(h.event_lag('spot'), 0.5, 'a persistent 3 s floor is skew and is removed')


class LaneParameters12155(unittest.TestCase):
    """The lanes are build11's strategy, with build11's parameters - not EF's EV dial.

    build11 applies no EV gate to MAIN or REVERSAL; its only price control is the
    REVERSAL max-entry cap. This port was handing every lane decision EF's v10
    regime threshold (0.15/0.25) and refusing on it - a rule the lane was never
    designed to face. Owner: "reversal is different thing and it has different
    parameters."
    """
    def test_lane_decisions_carry_their_own_threshold(self):
        import test_lanes as T, poly_lanes as L
        e = T.engine_with()
        fired = T.drive(e, 0, 100060.0, seconds=20, step_ms=100)
        main = [d for _, d in fired if d['kind'] == 'MAIN'][0]
        self.assertEqual(main['threshold'], L.LANE_EV_FLOOR)
        e.confirm('MAIN', placed=False)
        flipped = T.drive(e, 40000, 99930.0, seconds=30, step_ms=100, imbalance=-0.9, buy=False, candle_id=0)
        rev = [d for _, d in flipped if d['kind'] == 'REVERSAL'][0]
        self.assertEqual(rev['threshold'], L.LANE_EV_FLOOR)

    def test_the_engine_no_longer_overrides_it_with_efs_dial(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.lane_loop)
        self.assertNotIn("self.m.threshold(", body, "EF's regime table must not reach a lane order")
        self.assertIn("poly_lanes.LANE_EV_FLOOR", body)

    def test_breakeven_floor_still_refuses_a_losing_price(self):
        """The one thing kept: a lane may not buy a price it cannot beat even when right."""
        import poly_core as PC, poly_lanes as L
        q = dict(ask=0.70, bid=0.68, asks=[(0.70, 500.0)], seq=1, age_ms=10)
        d = dict(fire=True, side='DOWN', p=0.65, threshold=L.LANE_EV_FLOOR, ask=0.70, sec=60, ev=0.0)
        # stake 10, not 3: at $3 an ask of 0.70 buys 4.2 shares, under the venue's
        # 5-share minimum, and order_plan refuses on THAT before it reaches EV.
        with self.assertRaisesRegex(ValueError, 'EV'):
            PC.order_plan(q, (0.01, 5.0, 0.07, 1.0), 10.0, d, 1, False, False)
        d2 = dict(d, p=0.80)                                   # beats cost at 0.71 -> allowed
        PC.order_plan(q, (0.01, 5.0, 0.07, 1.0), 10.0, d2, 1, False, False)

    def test_rev_entry_cap_is_build11s_and_off_by_default(self):
        import poly_lanes as L
        self.assertEqual(L.REV_MAX_ENTRY_DEFAULT, 0.0)
        src = pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py').read_text()
        self.assertIn("self.db.get('rev_max_entry')", src)
        self.assertIn("REVERSAL entry cap: quote", src)


if __name__ == '__main__':
    unittest.main(verbosity=1)
