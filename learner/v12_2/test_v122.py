"""Tests for the v12.2 changes: venue-sourced money, honest feed staleness,
clock-skew tolerance and per-attempt latency."""
import json, os, sqlite3, tempfile, time, unittest
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
        self.assertEqual(r.executor.pad, 0, 'the running executor must pick it up without a restart')

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
        q = dict(ask=ask, asks=[(ask, 1000.0)], age_ms=0, seq=1)
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
