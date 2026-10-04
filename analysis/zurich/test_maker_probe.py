#!/usr/bin/env python3
"""Tests for the five safety properties the owner's YES is conditional on, plus the shared-wallet rule.

These are the properties, not the strategy. A probe that loses money is a result; a probe that
crosses the spread, outlives its cancel, doubles up, or reaches into 8787's orders is a fault.
"""
import datetime as dt, re, sqlite3, sys, tempfile, time, unittest
sys.path.insert(0, '/home/ubuntu/pm_paper_zurich')
import maker_probe as M


def mem():
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.executescript("""
    create table orders(id integer primary key, epoch integer, side text, token text, price real,
      shares real, post_ts_ms integer, venue_order_id text, cancel_ts_ms integer, cancel_reason text,
      status text, dry integer, note text);
    create table fills(id integer primary key, order_row integer, epoch integer, utc_day text,
      side text, fill_ts_ms integer, price real, shares real, spent real, bn_before_bps real,
      bn_after_bps real, outcome text, pnl real);
    create table decisions(id integer primary key, ts_ms integer, epoch integer, sec integer,
      action text, side text, price real, reason text, vol real, up_bid real, dn_bid real,
      up_ask real, dn_ask real, adverse real);""")
    return db


OK = dict(sec=100, up_bid=0.70, dn_bid=0.28, up_ask=0.72, dn_ask=0.30, vol=0.20,
          resting=None, adverse=0.0, filled_this_candle=False)


class NeverCrosses(unittest.TestCase):
    """Property 1. The venue's post_only is the real guarantee; this is ours."""
    def setUp(self): self.q = M.Quoter()

    def test_posts_strictly_below_the_ask(self):
        act, side, px, _ = self.q.decide(**OK)
        self.assertEqual((act, side), ('post', 'UP'))
        self.assertLess(px, OK['up_ask'])

    def test_refuses_when_bid_equals_ask(self):
        act, *_ , why = self.q.decide(**{**OK, 'up_ask': 0.70})
        self.assertEqual(act, 'none'); self.assertIn('cross', why)

    def test_refuses_when_the_book_is_crossed(self):
        act, *_, why = self.q.decide(**{**OK, 'up_ask': 0.69})
        self.assertEqual(act, 'none'); self.assertIn('cross', why)

    def test_refuses_when_there_is_no_ask_at_all(self):
        act, *_, why = self.q.decide(**{**OK, 'up_ask': None})
        self.assertEqual(act, 'none'); self.assertIn('cross', why)

    def test_the_live_order_is_signed_post_only(self):
        self.assertTrue(M.POST_ONLY)
        src = open('/home/ubuntu/pm_paper_zurich/maker_probe.py').read()
        self.assertIn('post_only=POST_ONLY', src)
        self.assertNotIn("order_type='FAK'", src)
        self.assertNotIn('create_market_order', src)


class CancelsOnAdverseMove(unittest.TestCase):
    """Property 2. 2 bps against us over the last second, measured on Binance spot."""
    def setUp(self): self.q = M.Quoter()

    def test_sign_convention_up(self):
        m = M.Mover(); m.add(1000, 100000.0); m.add(1900, 99970.0)      # -3 bps
        self.assertAlmostEqual(m.adverse_bps('UP'), 3.0, places=1)      # bad for UP
        self.assertAlmostEqual(m.adverse_bps('DOWN'), -3.0, places=1)   # good for DOWN

    def test_sign_convention_down(self):
        m = M.Mover(); m.add(1000, 100000.0); m.add(1900, 100030.0)     # +3 bps
        self.assertAlmostEqual(m.adverse_bps('DOWN'), 3.0, places=1)
        self.assertAlmostEqual(m.adverse_bps('UP'), -3.0, places=1)

    def test_only_the_last_second_counts(self):
        m = M.Mover(); m.add(0, 100000.0); m.add(3000, 99000.0); m.add(3500, 99000.0)
        self.assertAlmostEqual(m.adverse_bps('UP', now_ms=3500), 0.0, places=6)

    def test_resting_order_is_cancelled_at_the_threshold(self):
        rest = dict(side='UP', price=0.70)
        act, _, _, why = self.q.decide(**{**OK, 'resting': rest, 'adverse': M.ADVERSE_BPS})
        self.assertEqual(act, 'cancel'); self.assertIn('adverse', why)

    def test_just_under_the_threshold_holds(self):
        rest = dict(side='UP', price=0.70)
        act, *_ = self.q.decide(**{**OK, 'resting': rest, 'adverse': M.ADVERSE_BPS - 0.01})
        self.assertEqual(act, 'hold')

    def test_adverse_beats_every_other_reason_to_stay(self):
        """A 2 bps move pulls the order even mid-window with a perfect book."""
        rest = dict(side='UP', price=0.70)
        act, *_ = self.q.decide(**{**OK, 'sec': 61, 'resting': rest, 'adverse': 50.0})
        self.assertEqual(act, 'cancel')


class Window(unittest.TestCase):
    """Property 3. 60-120 s, and nothing rests past 120 (owner 10-02: was 180)."""
    def setUp(self): self.q = M.Quoter()

    def test_no_post_before_60(self):
        self.assertEqual(self.q.decide(**{**OK, 'sec': 59})[0], 'none')

    def test_posts_at_60_and_at_120(self):
        self.assertEqual(self.q.decide(**{**OK, 'sec': 60})[0], 'post')
        self.assertEqual(self.q.decide(**{**OK, 'sec': 120})[0], 'post')

    def test_no_post_after_120(self):
        self.assertEqual(self.q.decide(**{**OK, 'sec': 121})[0], 'none')

    def test_the_old_180_window_is_gone(self):
        """The edge that moved. 121-180 used to post and must not any more; this is the test that
        would have caught the change being applied to the constant but not to the gate."""
        for sec in (121, 150, 179, 180, 181):
            self.assertEqual(self.q.decide(**{**OK, 'sec': sec})[0], 'none', f'sec {sec} must not post')

    def test_resting_order_is_cancelled_at_121(self):
        rest = dict(side='UP', price=0.70)
        act, _, _, why = self.q.decide(**{**OK, 'sec': 121, 'resting': rest})
        self.assertEqual(act, 'cancel'); self.assertIn('121', why)

    def test_resting_order_is_cancelled_if_the_window_has_not_opened(self):
        rest = dict(side='UP', price=0.70)
        self.assertEqual(self.q.decide(**{**OK, 'sec': 5, 'resting': rest})[0], 'cancel')


class OneOrderOneFill(unittest.TestCase):
    """Property 4. One resting order, at most one fill per candle."""
    def setUp(self): self.q = M.Quoter()

    def test_a_resting_order_at_the_right_price_is_never_duplicated(self):
        rest = dict(side='UP', price=0.70)
        self.assertEqual(self.q.decide(**{**OK, 'resting': rest})[0], 'hold')

    def test_a_one_tick_rise_now_HOLDS_instead_of_chasing(self):
        """THE 17:00 REGRESSION. This used to cancel and re-post, which produced 34 orders and zero
        fills in one candle. One tick is within tolerance: we stay in the book."""
        rest = dict(side='UP', price=0.69)
        self.assertEqual(self.q.decide(**{**OK, 'resting': rest})[0], 'hold')

    def test_a_flipped_favourite_does_NOT_pull_a_resting_order(self):
        """OWNER option A: only 2 bps or the window end pull it. A favourite that flips against us shows up
        as a Binance move, which is the faster signal anyway - that is the control, not the book."""
        rest = dict(side='DOWN', price=0.70)
        self.assertEqual(self.q.decide(**{**OK, 'resting': rest})[0], 'hold')

    def test_nothing_is_posted_after_a_fill_in_the_same_candle(self):
        self.assertEqual(self.q.decide(**{**OK, 'filled_this_candle': True})[0], 'none')

    def test_a_fill_pulls_any_other_resting_order(self):
        rest = dict(side='UP', price=0.70)
        act, *_ = self.q.decide(**{**OK, 'resting': rest, 'filled_this_candle': True})
        self.assertEqual(act, 'cancel')

    def test_the_loop_clears_resting_before_posting(self):
        src = open('/home/ubuntu/pm_paper_zurich/maker_probe.py').read()
        self.assertIn('self.resting = None', src.split('async def cancel')[1][:400])


class HardStops(unittest.TestCase):
    """Property 5. Both stops, checked before EVERY post."""
    def setUp(self):
        self.db = mem(); self.g = M.Guard(self.db, dry_run=False)
        self.g.flag_on = lambda: True

    def add(self, pnl, day='2026-09-30'):
        self.db.execute('insert into fills(epoch,utc_day,side,price,shares,pnl) '
                        'values(1,?,?,0.7,5,?)', (day, 'UP', pnl)); self.db.commit()

    def test_clean_book_may_trade(self):
        self.assertTrue(self.g.may_trade()[0])

    def test_day_stop_binds_exactly_at_minus_ten(self):
        self.add(-10.0, time.strftime('%Y-%m-%d', time.gmtime()))
        ok, why = self.g.may_trade(); self.assertFalse(ok); self.assertIn('DAY STOP', why)

    def test_day_stop_does_not_bind_at_minus_nine_ninety_nine(self):
        self.add(-9.99, time.strftime('%Y-%m-%d', time.gmtime()))
        self.assertTrue(self.g.may_trade()[0])

    def test_yesterdays_loss_does_not_stop_today(self):
        self.add(-10.0, '2026-01-01')
        self.assertTrue(self.g.may_trade()[0])

    def test_lifetime_stop_binds_across_days(self):
        for d in ('2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'):
            self.add(-5.0, d)
        ok, why = self.g.may_trade(); self.assertFalse(ok); self.assertIn('LIFETIME', why)

    def test_lifetime_stop_outranks_a_clean_day(self):
        for d in ('2026-01-01', '2026-01-02'): self.add(-10.0, d)
        self.assertFalse(self.g.may_trade()[0])

    def test_unsettled_fills_do_not_count_as_zero(self):
        self.db.execute("insert into fills(epoch,utc_day,side,price,shares) values(1,?,?,0.7,5)",
                        (time.strftime('%Y-%m-%d', time.gmtime()), 'UP')); self.db.commit()
        self.assertEqual(self.g.realised(), 0.0)

    def test_flag_off_blocks_even_with_a_clean_book(self):
        g = M.Guard(self.db, flag_path='/nonexistent/ENABLED', dry_run=False)
        ok, why = g.may_trade(); self.assertFalse(ok); self.assertEqual(why, 'flag off')

    def test_dry_run_can_never_trade(self):
        g = M.Guard(self.db, dry_run=True); g.flag_on = lambda: True
        self.assertFalse(g.may_trade()[0])

    def test_default_is_off(self):
        self.assertFalse(M.Guard(mem()).may_trade()[0])


class SharedWallet(unittest.TestCase):
    """Property 6, the one that protects the OTHER engine. Zurich and London share one wallet."""
    def test_module_never_calls_a_wallet_wide_cancel(self):
        src = open('/home/ubuntu/pm_paper_zurich/maker_probe.py').read()
        code = '\n'.join(l for l in src.splitlines()
                         if not l.strip().startswith('#') and 'NEVER' not in l)
        for bad in ('cancel_all', 'cancel_market_orders'):
            self.assertNotIn(bad + '(', code, f'{bad} would reach into 8787 orders')

    def test_cancel_is_always_by_our_own_order_id(self):
        src = open('/home/ubuntu/pm_paper_zurich/maker_probe.py').read()
        for m in re.finditer(r'cancel_order\(([^)]*)\)', src):
            self.assertIn('order_id=', m.group(1))


class Calm(unittest.TestCase):
    """The calm gate is the frozen one, not a new number."""
    def setUp(self): self.q = M.Quoter()

    def test_uses_the_frozen_cut(self):
        self.assertEqual(M.VOL_CUT, 0.304)

    def test_not_calm_does_not_post(self):
        self.assertEqual(self.q.decide(**{**OK, 'vol': 0.304})[0], 'none')

    def test_calm_just_under_posts(self):
        self.assertEqual(self.q.decide(**{**OK, 'vol': 0.3039})[0], 'post')

    def test_unknown_vol_does_not_post(self):
        self.assertEqual(self.q.decide(**{**OK, 'vol': None})[0], 'none')

    def test_vol_leaving_calm_does_NOT_pull_a_resting_order(self):
        """Changed 09-30 by V's fix. Calm gates ENTRY, not exit: once we are in the book the only
        reasons to leave are the four in the no-chase rule. Vol rising is not one of them - the
        2 bps Binance test is the live risk control, and it is strictly faster than a vol estimate
        computed over the 300 s BEFORE the open (which cannot change intra-candle anyway)."""
        rest = dict(side='UP', price=0.70)
        self.assertEqual(self.q.decide(**{**OK, 'vol': 0.5, 'resting': rest})[0], 'hold')


class Band(unittest.TestCase):
    """Favourite = the side whose best BID is in [0.60, 0.80]."""
    def setUp(self): self.q = M.Quoter()

    def test_favourite_is_the_higher_bid(self):
        self.assertEqual(M.Quoter.favourite(0.70, 0.28)[0], 'UP')
        self.assertEqual(M.Quoter.favourite(0.28, 0.70)[0], 'DOWN')

    def test_equal_bids_have_no_favourite(self):
        self.assertIsNone(M.Quoter.favourite(0.5, 0.5)[0])

    def test_edges_are_inclusive(self):
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.60, 'up_ask': 0.62})[0], 'post')
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.80, 'up_ask': 0.82})[0], 'post')

    def test_outside_the_band_does_not_post(self):
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.59, 'up_ask': 0.61})[0], 'none')
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.81, 'up_ask': 0.83})[0], 'none')

    def test_the_down_side_is_priced_against_the_down_ask(self):
        """A DOWN favourite must be checked against dn_ask, not up_ask - the crossing bug that
        would let us buy through the book on one side only."""
        act, side, px, _ = self.q.decide(**{**OK, 'up_bid': 0.28, 'dn_bid': 0.70,
                                            'up_ask': 0.30, 'dn_ask': 0.72})
        self.assertEqual((act, side), ('post', 'DOWN')); self.assertLess(px, 0.72)
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.28, 'dn_bid': 0.70,
                                          'up_ask': 0.30, 'dn_ask': 0.70})[0], 'none')


class Settlement(unittest.TestCase):
    """Maker BUY: pays price, no taker fee, a winner redeems at 1.00. Venue resolution only."""
    def setUp(self):
        self.db = mem()
        self.g = sqlite3.connect(':memory:')
        self.g.execute('create table mkt(asset,epoch integer,cond,tok_up,tok_dn,outcome)')
        self.g.execute("insert into mkt values('x',100,'c','u','d','UP')")
        self.g.execute("insert into mkt values('x',200,'c','u','d','DOWN')")
        self.g.execute("insert into mkt values('x',300,'c','u','d',NULL)")
        self.g.commit()
        import tempfile, os
        self.path = tempfile.mktemp(suffix='.sqlite3')
        d = sqlite3.connect(self.path)
        d.execute('create table mkt(asset,epoch integer,cond,tok_up,tok_dn,outcome)')
        for r in self.g.execute('select * from mkt'): d.execute('insert into mkt values(?,?,?,?,?,?)', r)
        d.commit(); d.close()

    def add(self, epoch, side, price=0.70, shares=5.0):
        self.db.execute('insert into fills(epoch,utc_day,side,price,shares) values(?,?,?,?,?)',
                        (epoch, '2026-09-30', side, price, shares)); self.db.commit()

    def test_a_winner_pays_one_minus_price(self):
        self.add(100, 'UP'); M.settle(self.db, self.path)
        self.assertAlmostEqual(self.db.execute('select pnl from fills').fetchone()[0], 5 * 0.30, 6)

    def test_a_loser_costs_the_whole_stake(self):
        self.add(200, 'UP'); M.settle(self.db, self.path)
        self.assertAlmostEqual(self.db.execute('select pnl from fills').fetchone()[0], -5 * 0.70, 6)

    def test_an_unresolved_candle_stays_unsettled(self):
        self.add(300, 'UP'); M.settle(self.db, self.path)
        self.assertIsNone(self.db.execute('select pnl from fills').fetchone()[0])

    def test_settle_is_idempotent(self):
        self.add(100, 'UP'); M.settle(self.db, self.path)
        self.assertEqual(M.settle(self.db, self.path), 0)


class PostPathIntegration(unittest.TestCase):
    """The 30-min dry run of 09-30 13:24-13:54 posted NOTHING because all 7 candles were
    non-calm (vol 0.545-2.456 vs the 0.304 cut). So the dry run proves the gates, not the
    posting path. These drive Probe.one_pass with injected book/vol state and assert that a
    post is actually written - the part the market did not let us observe."""

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=True, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.ep = int(time.time() // 300) * 300
        self.now = self.ep + 100            # a chosen second inside the 60-120 window
        self.p.gamma_db = ':none:'
        M_tokens = lambda epoch, gamma_db=None: ('TOKUP', 'TOKDN') if epoch == self.ep else (None, None)
        self._orig = M.tokens_for; M.tokens_for = M_tokens
        self.p.books = {'TOKUP': dict(bids=[(0.70, 500.0)], asks=[(0.72, 500.0)], ts=time.time()),
                        'TOKDN': dict(bids=[(0.28, 500.0)], asks=[(0.30, 500.0)], ts=time.time())}
        self.p.fav.vol_before_open = lambda epoch, px=None: 0.20     # calm
        self.p.mover.add(int(self.now * 1000) - 900, 100000.0)
        self.p.mover.add(int(self.now * 1000), 100000.0)          # flat -> not adverse

    def tearDown(self):
        M.tokens_for = self._orig; self.loop.close()

    def run_pass(self):
        self.loop.run_until_complete(self.p.one_pass(now=self.now))

    def test_a_calm_in_band_candle_produces_a_post_row(self):
        self.run_pass()
        r = self.p.db.execute('select side, price, shares, status, dry from orders').fetchall()
        self.assertEqual(len(r), 1, 'exactly one order should have been written')
        self.assertEqual(r[0]['side'], 'UP')
        self.assertAlmostEqual(r[0]['price'], 0.70)
        self.assertEqual(r[0]['shares'], M.SHARES)
        self.assertEqual(r[0]['status'], 'DRY')
        self.assertEqual(r[0]['dry'], 1)

    def test_the_posted_price_is_below_the_ask_on_the_real_book(self):
        self.run_pass()
        px = self.p.db.execute('select price from orders').fetchone()[0]
        self.assertLess(px, self.p.books['TOKUP']['asks'][0][0])

    def test_a_non_calm_candle_writes_no_order(self):
        self.p.fav.vol_before_open = lambda epoch, px=None: 1.50
        self.run_pass()
        self.assertEqual(self.p.db.execute('select count(*) from orders').fetchone()[0], 0)

    def test_an_adverse_move_blocks_the_post(self):
        now = int(self.now * 1000)
        self.p.mover.ticks.clear()
        self.p.mover.add(now - 900, 100000.0); self.p.mover.add(now, 99950.0)   # -5 bps, bad for UP
        self.p.resting = dict(epoch=self.ep, side='UP', price=0.70, token='TOKUP',
                              order_id=None, post_ts_ms=now, row=1)
        self.p.db.execute("insert into orders(id,epoch,side,token,price,shares,status) "
                          "values(1,?,'UP','TOKUP',0.70,5,'OPEN')", (self.ep,))
        self.run_pass()
        self.assertIsNone(self.p.resting, 'the resting order must be pulled')
        self.assertEqual(self.p.db.execute('select status from orders where id=1').fetchone()[0],
                         'CANCELLED')

    def test_a_dry_resting_order_can_never_reach_the_venue(self):
        """Changed 09-30: a dry run now DOES keep a virtual resting order, so that it exercises the
        no-chase rule rather than only the per-candle cap. The invariant that matters is not that
        nothing rests - it is that a dry order carries NO venue order id, which is what makes
        cancel() and check_fill() return before touching the broker."""
        self.run_pass()
        self.assertIsNotNone(self.p.resting)
        self.assertIsNone(self.p.resting['order_id'])
        self.assertEqual(self.p.db.execute(
            "select count(*) from orders where dry=0").fetchone()[0], 0)

    def test_a_dry_run_never_constructs_a_broker(self):
        self.assertIsNone(self.p.broker)
        self.run_pass()
        self.assertEqual(self.p.db.execute(
            "select count(*) from orders where dry=1 and status='DRY'").fetchone()[0], 1)

    def test_place_returns_before_signing_in_a_dry_run(self):
        """self.broker is None in a dry run, so any attempt to sign would raise AttributeError.
        Asserting the DRY row exists AND no exception escaped is the proof it returned early."""
        oid, row = self.loop.run_until_complete(
            self.p.place(self.ep, 'UP', 'TOKUP', 0.70))
        self.assertIsNone(oid)
        self.assertEqual(self.p.db.execute('select status from orders where id=?', (row,)).fetchone()[0], 'DRY')


class NoChasing(unittest.TestCase):
    """V's fix, 09-30, after the 17:00 candle produced 34 orders and 0 fills.
    ONCE POSTED THE ORDER RESTS. Exactly four reasons to pull it - nothing else."""
    def setUp(self): self.q = M.Quoter()

    def rest(self, price=0.70, side='UP'): return dict(side=side, price=price)

    def test_reason_1_adverse_two_bps(self):
        act, _, _, why = self.q.decide(**{**OK, 'resting': self.rest(), 'adverse': 2.0})
        self.assertEqual(act, 'cancel'); self.assertIn('adverse', why)

    def test_reason_2_past_120(self):
        act, _, _, why = self.q.decide(**{**OK, 'sec': 121, 'resting': self.rest()})
        self.assertEqual(act, 'cancel'); self.assertIn('outside', why)

    def test_the_bid_dropping_below_us_no_longer_pulls_the_order(self):
        """OWNER option A, 09-30: rule 3 removed. It could only fire once our order had left the
        book, and the case that matters there - it left because it FILLED - is caught by the fill
        check that now runs every pass. Cancelling a resting order was the wrong way to detect it."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.69,
                                          'resting': self.rest(0.70)})[0], 'hold')

    def test_the_bid_running_away_no_longer_pulls_the_order(self):
        """OWNER option A: 'bid ran >= 2 ticks' removed. On the live books it fired constantly -
        10 of 12 exits on 21:00-21:20, every one at exactly our price + 0.02 - so we were still
        chasing, just rate-limited, with ~10% book time and 0 fills."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.72,
                                          'resting': self.rest(0.70)})[0], 'hold')

    def test_a_far_bid_still_does_not_pull_it(self):
        """Not a cliff at 2 ticks any more: nothing about the book pulls a resting order."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.90, 'up_ask': 0.92,
                                          'resting': self.rest(0.70)})[0], 'hold')

    def test_an_offer_reaching_our_resting_price_is_a_FILL_not_a_cancel(self):
        """THE 18:30 REGRESSION. A resting BUY at 0.70 meeting an offer at 0.70 is us being filled
        as the maker - the event the probe exists to measure. Cancelling there would guarantee the
        probe never fills, which is the 17:00 symptom from the opposite cause."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.70, 'up_ask': 0.70,
                                          'resting': self.rest(0.70)})[0], 'hold')

    def test_the_crossing_test_still_applies_to_a_NEW_post(self):
        """Removing it from the resting branch must not weaken entry."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.70, 'up_ask': 0.70})[0], 'none')

    def test_being_alone_at_the_top_of_the_book_is_NOT_a_cancel(self):
        """Our own order is in the book we read, so best bid == our price while we rest. A maker
        WANTS to be at the front of the queue; the 2 bps Binance test is what protects us there."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.70, 'up_ask': 0.72,
                                          'resting': self.rest(0.70)})[0], 'hold')

    def test_one_tick_away_is_within_tolerance(self):
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.71,
                                          'resting': self.rest(0.70)})[0], 'hold')

    def test_nothing_else_pulls_it_band_exit(self):
        """A bid leaving the 0.60-0.80 band is NOT one of the four reasons."""
        self.assertEqual(self.q.decide(**{**OK, 'up_bid': 0.70, 'up_ask': 0.72,
                                          'resting': self.rest(0.70), 'vol': 0.29})[0], 'hold')

    def test_the_exact_17_00_sequence_no_longer_churns(self):
        """Replay of the real bid path from candle 17:00 (0.61 0.60 0.65 0.63 0.61 0.62 0.64 ...).
        Old rule: a cancel on every change. New rule: at most a handful of pulls."""
        path = [0.61, 0.60, 0.65, 0.63, 0.61, 0.62, 0.64, 0.62, 0.60, 0.62, 0.61]
        resting, cancels, posts = None, 0, 0
        for b in path:
            act, side, px, _ = self.q.decide(**{**OK, 'up_bid': b, 'up_ask': b + 0.02,
                                                'resting': resting, 'posts_this_candle': posts})
            if act == 'cancel': resting = None; cancels += 1
            elif act == 'post': resting = dict(side=side, price=px); posts += 1
        self.assertLessEqual(posts, M.MAX_POSTS_PER_CANDLE)
        self.assertLess(cancels, len(path))


class PostCeiling(unittest.TestCase):
    def setUp(self): self.q = M.Quoter()

    def test_three_posts_is_the_cap(self):
        self.assertEqual(self.q.decide(**{**OK, 'posts_this_candle': 2})[0], 'post')
        act, _, _, why = self.q.decide(**{**OK, 'posts_this_candle': 3})
        self.assertEqual(act, 'none'); self.assertIn('max', why)

    def test_the_cap_is_three(self):
        self.assertEqual(M.MAX_POSTS_PER_CANDLE, 3)

    def test_place_increments_the_per_candle_count(self):
        import asyncio
        p = M.Probe(dry_run=True, db=mem()); loop = asyncio.new_event_loop()
        for _ in range(2): loop.run_until_complete(p.place(999, 'UP', 'T', 0.70))
        self.assertEqual(p.posts_per_epoch[999], 2); loop.close()


class RejectBookkeeping(unittest.TestCase):
    """Fix (2) and (3): a venue rejection is REJECTED, not PENDING, and a post-only reject
    stops us firing again off the same book read."""
    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')   # never the committed report
        self.p.books = {'T': dict(bids=[(0.70, 9.0)], asks=[(0.72, 9.0)], ts=1000.0)}

        class Boom:
            def __init__(s, msg): s.msg = msg
            async def create_limit_order(s, **k):
                # maker_amount / taker_amount IS the price; both are venue 1e6 units
                # (poly_live.prepare relies on exactly this). 0.70 * 5 sh = 3.5 USDC.
                return type('S', (), dict(maker_amount=3_500_000.0, taker_amount=5_000_000.0))()
            async def post_order(s, signed): raise RuntimeError(s.msg)
        self.boom = Boom
        self.p.broker = type('B', (), {'client': Boom('invalid post-only order: order crosses book')})()

    def tearDown(self): self.loop.close()

    def test_a_venue_rejection_is_recorded_as_REJECTED_not_PENDING(self):
        oid, row = self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertIsNone(oid)
        r = self.p.db.execute('select status, note from orders where id=?', (row,)).fetchone()
        self.assertEqual(r['status'], 'REJECTED')
        self.assertIn('post-only', r['note'])

    def test_no_row_is_ever_left_PENDING_after_a_reject(self):
        self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertEqual(self.p.db.execute(
            "select count(*) from orders where status='PENDING'").fetchone()[0], 0)

    def test_a_post_only_reject_blocks_the_next_post_until_the_book_moves(self):
        self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertFalse(self.p.book_fresh('T'), 'same book read must be treated as stale')
        self.p.books['T']['ts'] = 1001.0                      # a newer book event arrives
        self.assertTrue(self.p.book_fresh('T'))

    def test_a_stale_book_makes_the_quoter_refuse_to_post(self):
        act, _, _, why = M.Quoter().decide(**{**OK, 'book_fresh': False})
        self.assertEqual(act, 'none'); self.assertIn('fresh book', why)

    def test_a_non_postonly_error_does_not_set_the_stale_flag(self):
        self.p.broker = type('B', (), {'client': self.boom('some other venue error')})()
        self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertIsNone(self.p.stale_book_token)
        self.assertEqual(self.p.db.execute(
            "select status from orders order by id desc limit 1").fetchone()[0], 'REJECTED')


class DryRunRests(unittest.TestCase):
    """A dry run must simulate resting, or it measures the cap instead of the rule."""
    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=True, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.ep = int(time.time() // 300) * 300
        self._orig = M.tokens_for
        M.tokens_for = lambda e, gamma_db=None: ('TOKUP', 'TOKDN') if e == self.ep else (None, None)
        self.p.books = {'TOKUP': dict(bids=[(0.70, 500.0)], asks=[(0.72, 500.0)], ts=time.time()),
                        'TOKDN': dict(bids=[(0.28, 500.0)], asks=[(0.30, 500.0)], ts=time.time())}
        self.p.fav.vol_before_open = lambda epoch, px=None: 0.20
        n = int((self.ep + 80) * 1000)
        self.p.mover.add(n - 900, 100000.0); self.p.mover.add(n, 100000.0)

    def tearDown(self): M.tokens_for = self._orig; self.loop.close()

    def test_a_dry_post_leaves_a_virtual_order_resting(self):
        self.loop.run_until_complete(self.p.one_pass(now=self.ep + 80))
        self.assertIsNotNone(self.p.resting)
        self.assertIsNone(self.p.resting['order_id'], 'a dry order must carry no venue id')

    def test_a_stable_book_produces_ONE_post_not_three(self):
        """The regression the cap was masking: with the book unchanged the probe must post once
        and then sit, not re-post until it hits the ceiling."""
        for t in range(80, 110):            # inside 60-120 since the owner's 10-02 change
            self.loop.run_until_complete(self.p.one_pass(now=self.ep + t))
        self.assertEqual(self.p.posts_per_epoch[self.ep], 1,
                         f'posted {self.p.posts_per_epoch[self.ep]}x on a book that never moved')

    def test_dry_mode_puts_our_virtual_order_into_the_book_it_reads(self):
        """Live, our resting BUY is the best bid on its side. The dry sim must reproduce that or it
        over-cancels on V's rule 3 and its resting life is meaningless."""
        self.loop.run_until_complete(self.p.one_pass(now=self.ep + 80))
        self.assertIsNotNone(self.p.resting)
        px = self.p.resting['price']
        self.p.books['TOKUP']['bids'] = [(px - 0.01, 500.0)]      # real bid ticks BELOW us
        for t in range(81, 95):             # inside the window: this test is about the BOOK, not
                                            # the clock, so it must not step over the window edge
            self.loop.run_until_complete(self.p.one_pass(now=self.ep + t))
        self.assertIsNotNone(self.p.resting, 'must still be resting: live we would be the best bid')
        self.assertEqual(self.p.posts_per_epoch[self.ep], 1)


class FillsFeedTheStops(unittest.TestCase):
    """SPEC FIX (a), V 09-30. Both hard stops are computed FROM the fills table, so a fill that is
    never recorded does not just lose a row - it disables the stops. That is the one failure here
    that loses money quietly, so it gets tested from every angle a fill can arrive."""

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.ep = int(time.time() // 300) * 300
        self.now = self.ep + 80
        self._orig = M.tokens_for
        M.tokens_for = lambda e, gamma_db=None: ('TOKUP', 'TOKDN') if e == self.ep else (None, None)
        self.p.fav.vol_before_open = lambda epoch, px=None: 0.20
        self.p.guard.flag_on = lambda: True
        self.p.mover.add(int(self.now * 1000) - 900, 100000.0)
        self.p.mover.add(int(self.now * 1000), 100000.0)
        self.p.db.execute("insert into orders(id,epoch,side,token,price,shares,status,dry) "
                          "values(1,?,'UP','TOKUP',0.70,5,'OPEN',0)", (self.ep,))
        self.p.db.commit()
        self.p.resting = dict(epoch=self.ep, side='UP', price=0.70, token='TOKUP',
                              order_id='OID1', post_ts_ms=int(self.now * 1000), row=1)
        self.calls = []
        self.will_fill = True
        async def fake_check(epoch):
            self.calls.append(epoch)
            if not self.will_fill: return False
            self.p.db.execute("insert into fills(order_row,epoch,utc_day,side,fill_ts_ms,price,"
                              "shares,spent) values(1,?,?,'UP',0,0.70,5,3.5)",
                              (epoch, time.strftime('%Y-%m-%d', time.gmtime())))
            self.p.db.commit(); self.p.filled_epochs.add(epoch); self.p.resting = None
            return True
        self.p.check_fill = fake_check

    def tearDown(self): M.tokens_for = self._orig; self.loop.close()

    def book(self, up_bid, up_ask=0.72):
        self.p.books = {'TOKUP': dict(bids=[(up_bid, 9.0)], asks=[(up_ask, 9.0)], ts=time.time()),
                        'TOKDN': dict(bids=[(0.28, 9.0)], asks=[(0.30, 9.0)], ts=time.time())}

    def want_cancel(self):
        """Make the rule want to cancel. Since the owner's option A there is exactly one way to do
        that mid-window: a Binance move >= 2 bps against our side."""
        self.p.mover.ticks.clear()
        n = int(self.now * 1000)
        self.p.mover.add(n - 900, 100000.0); self.p.mover.add(n, 99950.0)   # -5 bps, bad for UP

    def fills(self): return self.p.db.execute('select count(*) from fills').fetchone()[0]

    def test_a_fill_survives_a_pass_that_wanted_to_cancel(self):
        """The exact hole: rule 3 wants a cancel, the order has in fact filled."""
        self.book(0.70); self.want_cancel()    # 2 bps against us -> cancel wanted
        self.p._last_fill_check = self.now     # defeat the routine check, so only the pre-cancel one can save it
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.assertEqual(self.fills(), 1, 'the fill must be recorded, not thrown away by the cancel')
        self.assertEqual(self.p.db.execute("select status from orders where id=1").fetchone()[0],
                         'OPEN', 'a filled order must not be stamped CANCELLED')

    def test_a_fill_is_seen_on_a_routine_pass_with_no_cancel(self):
        self.book(0.70)                        # nothing wrong -> hold
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.assertEqual(self.fills(), 1)

    def test_a_fill_is_seen_at_the_candle_roll(self):
        """A resting order that filled as the candle ended must not be cancelled into oblivion."""
        self.book(0.70)
        self.loop.run_until_complete(self.p.one_pass(now=self.ep + 305))
        self.assertEqual(self.fills(), 1)

    def test_no_fill_means_the_cancel_still_happens(self):
        self.will_fill = False
        self.book(0.70); self.want_cancel()
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.assertEqual(self.fills(), 0)
        self.assertEqual(self.p.db.execute("select status from orders where id=1").fetchone()[0],
                         'CANCELLED')
        self.assertIsNone(self.p.resting)

    def test_the_pre_cancel_check_ignores_the_throttle(self):
        """Throttling the routine check must never be able to delay the pre-cancel one."""
        self.will_fill = False
        self.book(0.70); self.want_cancel()
        self.p._last_fill_check = self.now          # routine check throttled out
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.assertEqual(len(self.calls), 1, 'the pre-cancel check must still have run')

    def test_the_routine_check_IS_throttled(self):
        """5 passes a second must not mean 5 venue calls a second."""
        self.will_fill = False
        self.book(0.70)
        for i in range(10):
            self.loop.run_until_complete(self.p.one_pass(now=self.now + i * 0.2))
        self.assertLessEqual(len(self.calls), 3, f'{len(self.calls)} venue calls in 2 s is too many')
        self.assertGreaterEqual(len(self.calls), 2, 'but it must still be checking')

    def test_a_fill_recorded_this_way_actually_trips_the_day_stop(self):
        """End to end: the fill lands, the loss is realised, may_trade() refuses. This is the whole
        point of fix (a) - a stop that cannot see a fill is not a stop."""
        self.book(0.70); self.want_cancel()
        self.p._last_fill_check = self.now
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.p.db.execute("update fills set pnl=-10.0"); self.p.db.commit()
        ok, why = self.p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('DAY STOP', why)

    def test_a_fill_recorded_this_way_trips_the_lifetime_stop(self):
        self.book(0.70); self.want_cancel()
        self.p._last_fill_check = self.now
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.p.db.execute("update fills set pnl=-20.0, utc_day='2020-01-01'"); self.p.db.commit()
        ok, why = self.p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('LIFETIME', why)

    def test_a_dry_run_never_calls_the_venue_fill_check(self):
        p = M.Probe(dry_run=True, db=mem()); p.logfile = tempfile.mktemp(suffix='.log')
        calls = []
        async def spy(e): calls.append(e); return False
        p.check_fill = spy
        p.fav.vol_before_open = lambda epoch, px=None: 0.20
        p.books = {'TOKUP': dict(bids=[(0.70, 9.0)], asks=[(0.72, 9.0)], ts=time.time()),
                   'TOKDN': dict(bids=[(0.28, 9.0)], asks=[(0.30, 9.0)], ts=time.time())}
        p.resting = dict(epoch=self.ep, side='UP', price=0.70, token='TOKUP',
                         order_id=None, post_ts_ms=0, row=1)
        self.loop.run_until_complete(p.one_pass(now=self.now))
        self.assertEqual(calls, [], 'a dry run must not reach the venue')


class SameSecondLockout(unittest.TestCase):
    """SPEC FIX (b), V 09-30: "do not re-post in the same second" after a post-only reject.
    The book-freshness test alone was not enough - these books publish many events a second, so it
    cleared instantly. Live proof: two rejects at 21:06:05, same second, same price 0.70."""

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.ep = int(time.time() // 300) * 300
        self.now = self.ep + 80
        self._orig = M.tokens_for
        M.tokens_for = lambda e, gamma_db=None: ('TOKUP', 'TOKDN') if e == self.ep else (None, None)
        self.p.fav.vol_before_open = lambda epoch, px=None: 0.20
        self.p.guard.flag_on = lambda: True
        self.p.mover.add(int(self.now * 1000) - 900, 100000.0)
        self.p.mover.add(int(self.now * 1000), 100000.0)
        self.p.books = {'TOKUP': dict(bids=[(0.70, 9.0)], asks=[(0.72, 9.0)], ts=1000.0),
                        'TOKDN': dict(bids=[(0.28, 9.0)], asks=[(0.30, 9.0)], ts=1000.0)}
        class Rejecter:
            async def create_limit_order(s, **k):
                return type('S', (), dict(maker_amount=3_500_000.0, taker_amount=5_000_000.0))()
            async def post_order(s, signed):
                raise RuntimeError('invalid post-only order: order crosses book')
        self.p.broker = type('B', (), {'client': Rejecter()})()

    def tearDown(self): M.tokens_for = self._orig; self.loop.close()

    def posts(self): return self.p.db.execute('select count(*) from orders').fetchone()[0]

    def test_a_reject_sets_the_second_level_lock(self):
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.assertEqual(self.p.reject_lock_s, int(time.time()))

    def test_no_second_post_in_the_same_second_even_if_the_book_moves(self):
        """The regression: a fresh book event used to clear the block instantly."""
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        first = self.posts()
        self.p.reject_lock_s = int(self.now)             # pin the lock to our injected clock
        for frac in (0.2, 0.4, 0.6, 0.8):
            self.p.books['TOKUP']['ts'] = 2000.0 + frac  # a brand new book each time
            self.loop.run_until_complete(self.p.one_pass(now=self.now + frac))
        self.assertEqual(self.posts(), first, 'no re-post is allowed inside the rejecting second')

    def test_the_next_second_is_allowed_again(self):
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        first = self.posts()
        self.p.reject_lock_s = int(self.now)
        self.p.books['TOKUP']['ts'] = 3000.0
        self.loop.run_until_complete(self.p.one_pass(now=self.now + 1.0))
        self.assertGreater(self.posts(), first, 'the lock must expire with the second')
        # That new post is rejected too (the stub always rejects), so a NEW lock is set for the
        # current second. The old one being gone is what matters, not the field being None.
        self.assertNotEqual(self.p.reject_lock_s, int(self.now),
                            'the expired lock must not still be the one we pinned')

    def test_the_lock_clears_when_a_later_post_is_accepted(self):
        class Accepter:
            async def create_limit_order(s, **k):
                return type('S', (), dict(maker_amount=3_500_000.0, taker_amount=5_000_000.0))()
            async def post_order(s, signed):
                return type('R', (), dict(ok=True, order_id='OID9'))()
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.p.reject_lock_s = int(self.now)
        self.p.broker = type('B', (), {'client': Accepter()})()
        self.p.books['TOKUP']['ts'] = 4000.0
        self.loop.run_until_complete(self.p.one_pass(now=self.now + 1.0))
        self.assertIsNone(self.p.reject_lock_s)
        self.assertIsNotNone(self.p.resting)

    def test_the_reject_is_still_recorded_as_REJECTED(self):
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        r = self.p.db.execute('select status, note from orders order by id desc limit 1').fetchone()
        self.assertEqual(r['status'], 'REJECTED'); self.assertIn('post-only', r['note'])
        self.assertEqual(self.p.db.execute(
            "select count(*) from orders where status='PENDING'").fetchone()[0], 0)


# =================================================================================================
try:
    from polymarket.models.clob.account import ClobTrade
except Exception:                                   # pragma: no cover - the venv always has it
    ClobTrade = None

HEX32 = '0x' + 'ab' * 32
WALLET = '0x' + '11' * 20


def venue_trade(our_id='0xOURS', *, matched='5', trader_side='MAKER', taker_order_id='0xTAKER',
                status='MATCHED', match_time='1790813160', price='0.60', makers=None, tid='t1'):
    """One trade as the venue really serialises it, parsed by the SDK's own model.

    Built through ClobTrade.model_validate on purpose: the bug was that our code read a field name
    the model does not have, so a test that fakes the trade with a SimpleNamespace would have
    passed while the probe stayed blind. If polymarket-client renames or reshapes this, these
    tests fail here, at the parse, which is the only early warning there is."""
    if makers is None:
        makers = [dict(order_id=our_id, asset_id='TOKUP', maker_address=WALLET, owner='own',
                       side='BUY', price=price, matched_amount=matched, outcome='Up',
                       fee_rate_bps='0')]
    return ClobTrade.model_validate(dict(
        id=tid, market=HEX32, asset_id='TOKUP', owner='own', maker_address=WALLET,
        taker_order_id=taker_order_id, side='BUY', trader_side=trader_side, price=price,
        size='5', outcome='Up', status=status, fee_rate_bps='0', bucket_index=0,
        transaction_hash='0x' + 'cd' * 32, maker_orders=makers,
        match_time=match_time, last_update=match_time))


class TapeClient:
    """The two client calls check_fill can make, and a record of the cancels it asked for."""
    def __init__(self, trades):
        self.trades, self.cancelled = trades, []

    def list_account_trades(self, token_id=None, **kw):
        trades = self.trades
        class Pages:
            def __aiter__(self):
                async def gen():
                    yield type('Page', (), {'items': tuple(trades)})()
                return gen()
        return Pages()

    async def cancel_order(self, order_id=None):
        self.cancelled.append(order_id); return {'canceled': [order_id]}


@unittest.skipIf(ClobTrade is None, 'polymarket-client not importable')
class MakerFillsAreVisible(unittest.TestCase):
    """The 10-01 blindness: our post-only order is the MAKER of every trade it is in, and a maker
    appears on the tape only inside the taker's trade, under maker_orders[]. check_fill compared
    our id against t.maker_order_id - a field ClobTrade does not define - so it matched nothing,
    recorded nothing, raised nothing, and left both hard stops with an empty fills table to read.
    The probe reported 0 fills while the wallet showed 4 real 5-share buys."""

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.ep = 1790813100
        self.p.db.execute("insert into orders(id,epoch,side,token,price,shares,post_ts_ms,"
                          "venue_order_id,status,dry) values(1,?,'UP','TOKUP',0.60,5,?,'0xOURS',"
                          "'OPEN',0)", (self.ep, 1790813100000))
        self.p.db.commit()
        self.p.resting = dict(epoch=self.ep, side='UP', price=0.60, token='TOKUP',
                              order_id='0xOURS', post_ts_ms=1790813100000, row=1)

    def tearDown(self):
        import asyncio
        for t in asyncio.all_tasks(self.loop): t.cancel()
        self.loop.close()

    def check(self, *trades):
        self.p.broker = type('B', (), {'client': TapeClient(list(trades))})()
        return self.loop.run_until_complete(self.p.check_fill(self.ep))

    def test_the_sdk_trade_has_no_maker_order_id_field(self):
        """The root cause, pinned. getattr(t,'maker_order_id','') was '' on every trade forever."""
        t = venue_trade()
        self.assertNotIn('maker_order_id', ClobTrade.model_fields)
        self.assertFalse(hasattr(t, 'maker_order_id'))

    def test_a_maker_fill_nested_in_maker_orders_is_seen(self):
        self.assertTrue(self.check(venue_trade()))
        f = self.p.db.execute('select * from fills').fetchall()
        self.assertEqual(len(f), 1, 'the maker fill must be recorded exactly once')
        self.assertEqual(f[0]['shares'], 5.0)
        self.assertEqual(f[0]['price'], 0.60)
        self.assertEqual(f[0]['side'], 'UP')
        self.assertEqual(self.p.db.execute('select status from orders where id=1').fetchone()[0],
                         'FILLED')
        self.assertIsNone(self.p.resting, 'a filled order is no longer resting')

    def test_the_fill_is_stamped_with_the_venue_match_time(self):
        """match_time is parsed into `matched_at`; reading `match_time` off the model gave 0 and
        stamped the local clock, which is the clock bn_before_bps is measured against."""
        self.check(venue_trade(match_time='1790813160'))
        r = self.p.db.execute('select fill_ts_ms, utc_day from fills').fetchone()
        self.assertEqual(r['fill_ts_ms'], 1790813160000)
        self.assertEqual(r['utc_day'], '2026-10-01')

    def test_a_fill_leaves_a_row_the_hard_stops_can_read(self):
        """Both stops are sums over fills. No row, no stop - that is what made this a safety bug."""
        self.check(venue_trade())
        self.assertEqual(self.p.db.execute('select count(*) from fills').fetchone()[0], 1)
        # -25 so this binds on the LIFETIME stop, which does not depend on what day it is run
        self.p.db.execute("update fills set pnl=-25.0 where id=1"); self.p.db.commit()
        on = tempfile.mktemp(suffix='.flag')
        with open(on, 'w') as f: f.write('1')       # the flag is a different gate; prove the STOP
        ok, why = M.Guard(self.p.db, flag_path=on, dry_run=False).may_trade()
        self.assertFalse(ok); self.assertIn('LIFETIME STOP', why)

    def test_a_taker_side_trade_is_still_seen(self):
        self.assertTrue(self.check(venue_trade(trader_side='TAKER', taker_order_id='0xOURS',
                                               makers=[])))
        self.assertEqual(self.p.db.execute('select shares from fills').fetchone()[0], 5.0)

    def test_another_makers_order_in_the_same_trade_is_not_our_fill(self):
        """The wallet is shared with 8787. Someone else's maker order in the same trade must not
        be read as ours, or the probe books a fill it never had and trips a stop on it."""
        other = [dict(order_id='0x8787', asset_id='TOKUP', maker_address=WALLET, owner='own',
                      side='BUY', price='0.60', matched_amount='5', outcome='Up', fee_rate_bps='0')]
        self.assertFalse(self.check(venue_trade(makers=other, taker_order_id='0xSOMEONE')))
        self.assertEqual(self.p.db.execute('select count(*) from fills').fetchone()[0], 0)
        self.assertIsNotNone(self.p.resting)

    def test_a_failed_trade_is_not_a_fill(self):
        """TradeStatus is an enum: str(status).upper() is 'TRADESTATUS.FAILED', which is in no
        ('FAILED', ...) tuple, so the old skip never fired either."""
        self.assertFalse(self.check(venue_trade(status='FAILED')))
        self.assertEqual(self.p.db.execute('select count(*) from fills').fetchone()[0], 0)

    def test_two_partial_trades_on_one_order_sum_to_one_fill(self):
        a = venue_trade(matched='2', tid='t1', match_time='1790813160')
        b = venue_trade(matched='3', tid='t2', match_time='1790813170')
        self.assertTrue(self.check(a, b))
        r = self.p.db.execute('select shares, fill_ts_ms from fills').fetchone()
        self.assertEqual(r['shares'], 5.0)
        self.assertEqual(r['fill_ts_ms'], 1790813160000, 'the FIRST match is when we were filled')

    def test_a_partial_fill_pulls_its_own_remainder(self):
        """2 of 5 filled leaves 3 resting at the venue. Clearing self.resting without cancelling
        them would orphan them: nothing can reach an order id self.resting no longer holds."""
        self.p.broker = type('B', (), {'client': TapeClient([venue_trade(matched='2')])})()
        self.assertTrue(self.loop.run_until_complete(self.p.check_fill(self.ep)))
        self.assertEqual(self.p.broker.client.cancelled, ['0xOURS'])
        self.assertEqual(self.p.db.execute('select shares from fills').fetchone()[0], 2.0)

    def test_a_full_fill_does_not_cancel_anything(self):
        self.p.broker = type('B', (), {'client': TapeClient([venue_trade()])})()
        self.loop.run_until_complete(self.p.check_fill(self.ep))
        self.assertEqual(self.p.broker.client.cancelled, [],
                         'a fully filled order has nothing left to cancel')

    def test_the_owners_2_then_3_split_is_one_5_share_fill(self):
        """The owner's app on the 8:30-8:35PM ET candle: 'Buy 2 Down @ 64c' then 'Buy 3 Down @ 64c'
        - our order 90, one 5-share post, two venue trades. They must sum to one 5-share fill, not
        be read as 2 and the other 3 dropped."""
        a = venue_trade(matched='2', price='0.64', tid='t1', match_time='1790814660')
        b = venue_trade(matched='3', price='0.64', tid='t2', match_time='1790814665')
        self.assertTrue(self.check(a, b))
        f = self.p.db.execute('select shares, price, spent from fills').fetchall()
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]['shares'], 5.0)
        self.assertAlmostEqual(f[0]['spent'], 3.20)
        self.assertEqual(self.p.broker.client.cancelled, [], 'nothing is left to cancel')

    def test_shares_that_match_while_we_cancel_the_remainder_are_still_booked(self):
        """The race the 2-then-3 split makes real: we see 2, we cancel the other 3, and the venue
        had already matched them. Before the re-read those 3 shares were as invisible to the stops
        as the maker fills themselves - the fill row said 2 and nothing ever corrected it."""
        two = venue_trade(matched='2', price='0.64', tid='t1', match_time='1790814660')
        three = venue_trade(matched='3', price='0.64', tid='t2', match_time='1790814665')

        class RacingTape(TapeClient):
            def __init__(self): super().__init__([two])
            async def cancel_order(self, order_id=None):
                self.cancelled.append(order_id)
                self.trades = [two, three]          # the venue had already matched the rest
                raise RuntimeError('order is already filled')

        self.p.broker = type('B', (), {'client': RacingTape()})()
        self.assertTrue(self.loop.run_until_complete(self.p.check_fill(self.ep)))
        f = self.p.db.execute('select shares, spent, fill_ts_ms from fills').fetchall()
        self.assertEqual(len(f), 1, 'one order is one fill row, amended - never two rows')
        self.assertEqual(f[0]['shares'], 5.0, 'the raced 3 shares must be booked')
        self.assertAlmostEqual(f[0]['spent'], 3.20)
        self.assertEqual(f[0]['fill_ts_ms'], 1790814660000)

    def test_a_tape_error_is_recorded_not_swallowed(self):
        class Boom:
            def list_account_trades(self, **kw): raise RuntimeError('tape down')
        self.p.broker = type('B', (), {'client': Boom()})()
        self.assertFalse(self.loop.run_until_complete(self.p.check_fill(self.ep)))
        self.assertIn('fill check',
                      self.p.db.execute('select note from orders where id=1').fetchone()[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)


class RealBackfilledFillIsHonoured(unittest.TestCase):
    """V, 10-01: prove that a REAL maker fill - one of the 27 recovered from the venue's
    maker_orders[] - trips one-fill-per-candle AND counts toward both hard stops.

    This is the end of the chain that broke. The fill was invisible, so filled_this_candle never
    set (15 fills landed in the 17:00 candle against a rule of one) and the stops read an empty
    table (so -$10/day and -$20 lifetime could never fire). Synthetic fills already cover the
    plumbing; this reads the probe's OWN database so the thing under test is the real recovered
    row, not a fixture that happens to agree with me.
    """
    DB = '/home/ubuntu/maker_probe/maker_probe.sqlite3'

    @classmethod
    def setUpClass(cls):
        import os
        if not os.path.exists(cls.DB): raise unittest.SkipTest('no probe db on this host')
        src = sqlite3.connect(f'file:{cls.DB}?mode=ro', uri=True); src.row_factory = sqlite3.Row
        # SETTLED rows only. This reads the LIVE probe db, which legitimately carries an unsettled
        # fill whenever a candle has not resolved yet - the first version summed pnl across all rows
        # and broke the moment the probe took a new fill mid-candle. A test that reads live data has
        # to tolerate the data being live.
        cls.rows = [dict(r) for r in src.execute(
            'select epoch, side, price, shares, pnl, utc_day FROM fills '
            'WHERE pnl IS NOT NULL ORDER BY fill_ts_ms')]
        cls.pending = src.execute('select count(*) from fills where pnl is null').fetchone()[0]
        src.close()
        if not cls.rows: raise unittest.SkipTest('no settled fills to assert on')

    def fresh(self):
        """A probe whose fills table is loaded with the REAL recovered fills."""
        p = M.Probe(dry_run=False, db=mem())
        p.logfile = tempfile.mktemp(suffix='.log')
        p.guard.flag_on = lambda: True
        for r in self.rows:
            p.db.execute('insert into fills(epoch,utc_day,side,fill_ts_ms,price,shares,spent,pnl) '
                         'values(?,?,?,?,?,?,?,?)',
                         (r['epoch'], r['utc_day'], r['side'], 0, r['price'], r['shares'],
                          r['shares'] * r['price'], r['pnl']))
        p.db.commit()
        return p

    def test_the_recovered_fills_are_really_there(self):
        self.assertGreaterEqual(len(self.rows), 20, 'expected at least the 27 recovered fills')
        self.assertTrue(all(r['pnl'] is not None for r in self.rows),
                        'this class selects settled rows only, so none may be None here')

    def test_a_real_fill_blocks_a_second_post_in_that_candle(self):
        """one fill per candle, driven by the real fill's own epoch."""
        p = self.fresh()
        ep = self.rows[0]['epoch']
        p.filled_epochs.add(ep)                       # what check_fill now does on a real fill
        act, _, _, why = p.quoter.decide(**{**OK, 'filled_this_candle': (ep in p.filled_epochs)})
        self.assertEqual(act, 'none'); self.assertIn('already filled', why)

    def test_the_17_00_candle_would_now_be_capped_at_one_fill(self):
        """15 of the 27 fills were in one candle. Count them, then prove that candle is now shut."""
        from collections import Counter
        worst, n = Counter(r['epoch'] for r in self.rows).most_common(1)[0]
        self.assertGreater(n, 1, 'the incident had repeated fills inside one candle')
        p = self.fresh(); p.filled_epochs.add(worst)
        self.assertEqual(p.quoter.decide(**{**OK, 'filled_this_candle': True})[0], 'none')

    def test_the_real_fills_reach_guard_realised(self):
        p = self.fresh()
        want = round(sum(r['pnl'] for r in self.rows), 4)
        self.assertAlmostEqual(round(p.guard.realised(), 4), want, places=3)
        self.assertNotEqual(p.guard.realised(), 0.0, 'an empty read is the bug we are testing for')

    def test_a_real_losing_day_trips_the_DAY_stop(self):
        """Re-sign the real fills to a loss. Only as many as it takes to clear -$10 WITHOUT clearing
        the -$20 lifetime bar, because may_trade() checks lifetime FIRST - re-signing all 27 sums to
        -42.40 and the lifetime stop answers before the day stop is ever consulted. That ordering is
        correct; the test has to respect it to be testing the day stop at all."""
        p = self.fresh()
        day = time.strftime('%Y-%m-%d', time.gmtime())
        p.db.execute('delete from fills'); p.db.commit()
        run = 0.0
        for r in self.rows:
            loss = -abs(r['pnl'])
            if run + loss < -19.0: break
            p.db.execute('insert into fills(epoch,utc_day,side,fill_ts_ms,price,shares,spent,pnl) '
                         'values(?,?,?,?,?,?,?,?)',
                         (r['epoch'], day, r['side'], 0, r['price'], r['shares'],
                          r['shares'] * r['price'], loss))
            run += loss
        p.db.commit()
        self.assertLessEqual(run, M.DAY_STOP, f'need <= {M.DAY_STOP} to test the day stop, got {run}')
        self.assertGreater(run, M.LIFE_STOP, 'must stay above the lifetime bar')
        ok, why = p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('DAY STOP', why)
        self.assertLessEqual(p.guard.realised(day), M.DAY_STOP)

    def test_a_real_losing_history_trips_the_LIFETIME_stop(self):
        p = self.fresh()
        p.db.execute("update fills set pnl=-abs(pnl), utc_day='2020-01-01'"); p.db.commit()
        ok, why = p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('LIFETIME', why)

    def test_with_the_fills_INVISIBLE_the_stops_do_not_fire(self):
        """The counterfactual that makes the rest of this class mean something: delete the rows and
        the same losing history passes may_trade(). That is exactly what shipped."""
        p = self.fresh()
        p.db.execute('update fills set pnl=-abs(pnl)'); p.db.commit()
        self.assertFalse(p.guard.may_trade()[0])
        p.db.execute('delete from fills'); p.db.commit()
        self.assertTrue(p.guard.may_trade()[0], 'blind stops let trading continue - the bug')


class DustDoesNotLockTheCandle(unittest.TestCase):
    """OWNER APPROVED 10-01 11:5x: a fill under 1.0 share does not set filled-this-candle. Its
    ledger row and pnl stay, and it still counts toward BOTH stops.

    Provoked by the real 11:40 fill: 0.01 shares - seven tenths of a cent - closed a whole candle
    and blocked 11 passes. One-fill-per-candle caps EXPOSURE, and dust is not exposure. Both sides
    of the boundary are asserted, because a threshold tested on one side only is half a test."""

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.ep = int(time.time() // 300) * 300
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.p.guard.flag_on = lambda: True
        self.p.resting = dict(epoch=self.ep, side='UP', price=0.70, token='T',
                              order_id='OID', post_ts_ms=0, row=1)
        self.p.db.execute("insert into orders(id,epoch,side,token,price,shares,status,dry) "
                          "values(1,?,'UP','T',0.70,5,'OPEN',0)", (self.ep,)); self.p.db.commit()

    def tearDown(self): self.loop.close()

    def fill(self, shares):
        """Drive the real check_fill with a venue trade of `shares` on our order."""
        class MO:
            def __init__(s, n): s.order_id='OID'; s.matched_amount=n; s.price=0.70
        class TR:
            def __init__(s, n):
                s.id='t1'; s.size=n; s.price=0.70; s.status='CONFIRMED'
                s.taker_order_id='OTHER'; s.maker_orders=(MO(n),)
                s.matched_at=dt.datetime.fromtimestamp(self.ep + 100, dt.UTC)
        class Page:
            def __init__(s, n): s.items=(TR(n),)
        class Client:
            def __init__(s, n): s.n=n
            def list_account_trades(s, **k):
                async def gen():
                    yield Page(s.n)
                return gen()
            async def cancel_order(s, **k): return None
        self.p.broker = type('B', (), {'client': Client(shares)})()
        return self.loop.run_until_complete(self.p.check_fill(self.ep))

    def test_the_threshold_is_one_share(self):
        self.assertEqual(M.MIN_LOCK_SHARES, 1.0)

    def test_0_99_shares_does_NOT_lock_the_candle(self):
        self.assertTrue(self.fill(0.99))
        self.assertNotIn(self.ep, self.p.filled_epochs, '0.99sh must leave the candle open')

    def test_1_00_shares_DOES_lock_the_candle(self):
        self.assertTrue(self.fill(1.00))
        self.assertIn(self.ep, self.p.filled_epochs, '1.00sh is not dust and must close the candle')

    def test_the_real_0_01_share_case_no_longer_locks(self):
        self.assertTrue(self.fill(0.01))
        self.assertNotIn(self.ep, self.p.filled_epochs)

    def test_a_full_5_share_fill_still_locks(self):
        self.assertTrue(self.fill(5.0))
        self.assertIn(self.ep, self.p.filled_epochs)

    def test_a_dust_fill_STILL_writes_its_ledger_row(self):
        """The row and the money are kept - only the candle lock is waived."""
        self.fill(0.01)
        r = self.p.db.execute('select shares, price, spent from fills').fetchone()
        self.assertIsNotNone(r, 'a dust fill must still be recorded')
        self.assertAlmostEqual(r['shares'], 0.01)
        self.assertAlmostEqual(r['spent'], 0.007, places=4)

    def test_dust_pnl_REACHES_both_stops(self):
        """The stops read the fills table, so a dust loss must still count against them."""
        self.fill(0.01)
        self.p.db.execute('update fills set pnl=-10.0, utc_day=?',
                          (time.strftime('%Y-%m-%d', time.gmtime()),)); self.p.db.commit()
        ok, why = self.p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('DAY STOP', why)
        self.p.db.execute("update fills set pnl=-20.0, utc_day='2020-01-01'"); self.p.db.commit()
        ok, why = self.p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('LIFETIME', why)

    def test_the_candle_stays_postable_after_dust(self):
        """End to end: dust fill, then decide() must still be willing to post in that candle."""
        self.fill(0.01)
        act, _, _, _ = self.p.quoter.decide(
            **{**OK, 'filled_this_candle': (self.ep in self.p.filled_epochs),
               'posts_this_candle': 1})
        self.assertEqual(act, 'post', 'the candle must remain open after a dust fill')

    def test_the_post_ceiling_still_bounds_the_worst_case(self):
        """Owner's stated bound: 2 x 0.99 + 5 shares. It holds only because the 3-post cap holds."""
        self.assertEqual(M.MAX_POSTS_PER_CANDLE, 3)
        act, _, _, why = self.p.quoter.decide(**{**OK, 'posts_this_candle': 3})
        self.assertEqual(act, 'none'); self.assertIn('max', why)


class ComplementTokenFillIsFound(unittest.TestCase):
    """OWNER APPROVED 10-01 ~20:1x ("Yes to whatever issue Zurich has"): the fill scan must query the
    account tape WITHOUT a token filter and let matched_by() decide ownership.

    THE BUG THIS LOCKS OUT: the venue books a maker fill against the COMPLEMENT token at the
    complement price. Order 109 was UP @ 0.60 on token 4432226411 and its trade sits on token
    7780369265 at 0.40. scan_tape asked for OUR token, i.e. the one token the trade is not filed
    under, and 12 real fills were invisible for a whole day while the stops read an empty table.

    The fake client below returns the trade ONLY when no token_id is passed, and returns nothing when
    one is. So these tests fail if the filter ever comes back - which is the point. A test that merely
    checked matched_by() would have passed throughout the outage, because matched_by was never wrong.
    """
    COMP_TOK = '7780369265'          # the complement; our order sits on OUR_TOK
    OUR_TOK  = '4432226411'

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.ep = int(time.time() // 300) * 300
        self.now = self.ep + 80
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.p.guard.flag_on = lambda: True
        self.p.db.execute("insert into orders(id,epoch,side,token,price,shares,status,dry,post_ts_ms) "
                          "values(1,?,'UP',?,0.60,5,'OPEN',0,?)",
                          (self.ep, self.OUR_TOK, int(self.now*1000))); self.p.db.commit()
        self.p.resting = dict(epoch=self.ep, side='UP', price=0.60, token=self.OUR_TOK,
                              order_id='OID109', post_ts_ms=int(self.now*1000), row=1)
        self.filtered_calls = []
        outer = self
        class MO:
            order_id='OID109'; matched_amount=5.0; price=0.60; outcome='Up'
        class TR:
            # the OUTER trade is the TAKER's view: complement token, complement price, taker's size
            id='t-comp'; size=10.0; price=0.40; status='CONFIRMED'
            asset_id=outer.COMP_TOK; taker_order_id='OTHER'; maker_orders=(MO(),)
            matched_at=dt.datetime.fromtimestamp(outer.now+1, dt.UTC)
        class Page: items=(TR(),)
        class Client:
            def list_account_trades(s, **kw):
                outer.filtered_calls.append(kw)
                async def gen():
                    if 'token_id' in kw and kw['token_id'] is not None:
                        return            # a token-filtered query finds NOTHING, as the venue behaves
                    yield Page()
                return gen()
            async def cancel_order(s, **kw): return None
        self.p.broker = type('B', (), {'client': Client()})()

    def tearDown(self): self.loop.close()

    def test_the_scan_passes_NO_token_filter(self):
        self.loop.run_until_complete(self.p.scan_tape(self.OUR_TOK, 'OID109', int(self.now*1000)))
        self.assertTrue(self.filtered_calls, 'the tape was never queried')
        for kw in self.filtered_calls:
            self.assertNotIn('token_id', kw, f'token filter is back: {kw}')

    def test_a_complement_token_fill_IS_found(self):
        sh, px, ts = self.loop.run_until_complete(
            self.p.scan_tape(self.OUR_TOK, 'OID109', int(self.now*1000)))
        self.assertAlmostEqual(sh, 5.0)
        self.assertAlmostEqual(px, 0.60, msg='price must come from maker_orders, not the outer trade')

    def test_the_outer_trade_fields_are_NOT_used(self):
        """The outer trade says 10 shares @ 0.40. Ours is 5 @ 0.60. Taking the outer values would
        both overstate size and misprice the fill."""
        sh, px, _ = self.loop.run_until_complete(
            self.p.scan_tape(self.OUR_TOK, 'OID109', int(self.now*1000)))
        self.assertNotAlmostEqual(sh, 10.0); self.assertNotAlmostEqual(px, 0.40)

    def test_check_fill_records_it_and_locks_the_candle(self):
        self.assertTrue(self.loop.run_until_complete(self.p.check_fill(self.ep)))
        r = self.p.db.execute('select shares,price,spent from fills').fetchone()
        self.assertAlmostEqual(r['shares'], 5.0); self.assertAlmostEqual(r['price'], 0.60)
        self.assertAlmostEqual(r['spent'], 3.00)
        self.assertIn(self.ep, self.p.filled_epochs, '5 shares is not dust; the candle must close')
        act, _, _, why = self.p.quoter.decide(**{**OK, 'filled_this_candle': True})
        self.assertEqual(act, 'none'); self.assertIn('already filled', why)

    def test_BOTH_stops_see_a_complement_token_fill(self):
        self.loop.run_until_complete(self.p.check_fill(self.ep))
        today = time.strftime('%Y-%m-%d', time.gmtime())
        self.p.db.execute('update fills set pnl=-10.0, utc_day=?', (today,)); self.p.db.commit()
        ok, why = self.p.guard.may_trade(); self.assertFalse(ok); self.assertIn('DAY STOP', why)
        self.p.db.execute("update fills set pnl=-20.0, utc_day='2020-01-01'"); self.p.db.commit()
        ok, why = self.p.guard.may_trade(); self.assertFalse(ok); self.assertIn('LIFETIME', why)


class TheTwelveRecoveredFills(unittest.TestCase):
    """The 12 fills the token filter hid on 10-01, as they now stand in the probe's own ledger.

    Their pnl and outcomes were written from VENUE truth (maker_orders[] on an unfiltered tape), and
    each order carries a note saying the token filter missed it. This asserts the recovery is intact
    and graded; the live re-scan against the venue is run by hand with credentials, which a unit test
    must not need."""
    DB = '/home/ubuntu/maker_probe/maker_probe.sqlite3'

    @classmethod
    def setUpClass(cls):
        import os
        if not os.path.exists(cls.DB): raise unittest.SkipTest('no probe db on this host')
        c = sqlite3.connect(f'file:{cls.DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
        cls.rec = [dict(r) for r in c.execute(
            "select o.id, o.side, o.price, o.note, f.shares, f.spent, f.pnl, f.outcome "
            "from orders o join fills f on f.order_row=o.id "
            "where o.note like '%token filter%' order by o.id")]
        c.close()

    def test_all_twelve_are_present(self):
        self.assertEqual(len(self.rec), 12, f'expected the 12 recovered fills, found {len(self.rec)}')

    def test_every_one_is_graded(self):
        for r in self.rec:
            self.assertIsNotNone(r['pnl'], f"order {r['id']} ungraded - the stops cannot see it")
            self.assertIn(r['outcome'], ('UP', 'DOWN'))

    def test_the_money_is_consistent_with_the_prices(self):
        for r in self.rec:
            self.assertAlmostEqual(r['spent'], r['shares'] * r['price'], places=4)
            won = r['outcome'] == r['side']
            want = r['shares'] * (1 - r['price']) if won else -r['shares'] * r['price']
            self.assertAlmostEqual(r['pnl'], want, places=4,
                                   msg=f"order {r['id']} pnl does not match its own price and outcome")

    def test_they_reach_the_stops(self):
        tot = sum(r['pnl'] for r in self.rec)
        self.assertNotEqual(tot, 0.0)
        p = M.Probe(dry_run=False, db=mem()); p.logfile = tempfile.mktemp(suffix='.log')
        for r in self.rec:
            p.db.execute("insert into fills(epoch,utc_day,side,fill_ts_ms,price,shares,spent,pnl) "
                         "values(1,'2020-01-01',?,0,?,?,?,?)",
                         (r['side'], r['price'], r['shares'], r['spent'], -abs(r['pnl'])))
        p.db.commit()
        self.assertLess(p.guard.realised(), 0.0)


class InsufficientBalanceReject(unittest.TestCase):
    """10-01 21:4x, V: the shared wallet is down to ~$25 and London's master is OFF. A
    not-enough-cash rejection must not be retried in a loop and must never be read as a fill.
    The venue's wording is not ours to choose, so the properties are tested on the message the
    venue actually sends ('not enough balance / allowance') AND on the generic case: neither
    contains 'post-only', so neither takes the post-only branch."""
    MSG = 'RequestRejectedError: not enough balance / allowance'

    def setUp(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        self.p = M.Probe(dry_run=False, db=mem())
        self.p.logfile = tempfile.mktemp(suffix='.log')
        self.p.books = {'T': dict(bids=[(0.70, 9.0)], asks=[(0.72, 9.0)], ts=1000.0)}
        msg = self.MSG

        class Broke:
            calls = 0
            async def create_limit_order(s, **k):
                return type('S', (), dict(maker_amount=3_500_000.0, taker_amount=5_000_000.0))()
            async def post_order(s, signed):
                type(s).calls += 1
                raise RuntimeError(msg)
        self.client = Broke
        self.p.broker = type('B', (), {'client': Broke()})()

    def tearDown(self): self.loop.close()

    def test_a_balance_reject_is_REJECTED_and_writes_no_fill(self):
        oid, row = self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertIsNone(oid)
        r = self.p.db.execute('select status, note, venue_order_id from orders where id=?',
                              (row,)).fetchone()
        self.assertEqual(r['status'], 'REJECTED')
        self.assertIn('balance', r['note'])
        self.assertIsNone(r['venue_order_id'], 'no venue id, so nothing can be attributed to it')
        self.assertEqual(self.p.db.execute('select count(*) from fills').fetchone()[0], 0)

    def test_a_reject_leaves_nothing_resting_so_check_fill_cannot_fire(self):
        self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertIsNone(self.p.resting, 'place() returned no order id; nothing may rest')
        self.assertFalse(self.loop.run_until_complete(self.p.check_fill(1)))
        self.assertEqual(self.p.db.execute('select count(*) from fills').fetchone()[0], 0)

    def test_the_rejected_attempt_still_counts_against_the_per_candle_cap(self):
        """The loop bound. posts_per_epoch is incremented at the INSERT, before post_order, so a
        reject consumes an attempt exactly like a successful post does."""
        for _ in range(M.MAX_POSTS_PER_CANDLE):
            self.loop.run_until_complete(self.p.place(7, 'UP', 'T', 0.70))
        self.assertEqual(self.p.posts_per_epoch[7], M.MAX_POSTS_PER_CANDLE)
        act, _, _, why = M.Quoter().decide(**{**OK, 'posts_this_candle': self.p.posts_per_epoch[7]})
        self.assertEqual(act, 'none')
        self.assertIn('max', why)

    def test_a_balance_reject_cannot_exceed_the_cap_however_often_the_loop_runs(self):
        """Drive the quoter the way one_pass does: once the cap is reached the answer is 'none',
        so no fourth post_order call can happen in that candle no matter how many passes run."""
        posts = 0
        for _ in range(50):
            act, side, px, _ = M.Quoter().decide(**{**OK, 'posts_this_candle': posts})
            if act != 'post': break
            self.loop.run_until_complete(self.p.place(7, side, 'T', px)); posts += 1
        self.assertEqual(posts, M.MAX_POSTS_PER_CANDLE)
        self.assertEqual(self.client.calls, M.MAX_POSTS_PER_CANDLE)
        self.assertEqual(self.p.db.execute(
            "select count(*) from orders where status='REJECTED'").fetchone()[0],
            M.MAX_POSTS_PER_CANDLE)

    def test_a_balance_reject_does_NOT_take_the_post_only_branch(self):
        """Documents the one real gap: 'not enough balance' contains neither 'post-only' nor
        'crosses book', so the same-second lockout and the stale-book flag are NOT set. The cap
        is therefore the only thing spacing the retries - 3 in a candle, possibly in one second."""
        self.loop.run_until_complete(self.p.place(1, 'UP', 'T', 0.70))
        self.assertIsNone(self.p.reject_lock_s)
        self.assertIsNone(self.p.stale_book_token)
        self.assertTrue(self.p.book_fresh('T'))
        self.assertEqual(self.p.counts['reject'], 1)
        self.assertEqual(self.p.counts.get('postonly_reject', 0), 0)
