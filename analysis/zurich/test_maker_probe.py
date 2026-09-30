#!/usr/bin/env python3
"""Tests for the five safety properties the owner's YES is conditional on, plus the shared-wallet rule.

These are the properties, not the strategy. A probe that loses money is a result; a probe that
crosses the spread, outlives its cancel, doubles up, or reaches into 8787's orders is a fault.
"""
import re, sqlite3, sys, tempfile, time, unittest
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
    """Property 3. 60-180 s, and nothing rests past 180."""
    def setUp(self): self.q = M.Quoter()

    def test_no_post_before_60(self):
        self.assertEqual(self.q.decide(**{**OK, 'sec': 59})[0], 'none')

    def test_posts_at_60_and_at_180(self):
        self.assertEqual(self.q.decide(**{**OK, 'sec': 60})[0], 'post')
        self.assertEqual(self.q.decide(**{**OK, 'sec': 180})[0], 'post')

    def test_no_post_after_180(self):
        self.assertEqual(self.q.decide(**{**OK, 'sec': 181})[0], 'none')

    def test_resting_order_is_cancelled_at_181(self):
        rest = dict(side='UP', price=0.70)
        act, _, _, why = self.q.decide(**{**OK, 'sec': 181, 'resting': rest})
        self.assertEqual(act, 'cancel'); self.assertIn('181', why)

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

    def test_a_flipped_favourite_still_cancels_now_via_the_price_test(self):
        """There is no longer a 'favourite flipped' branch; it is subsumed. If the favourite flips,
        our side's bid collapses, so our resting price is above it and rule 3 (we would be the
        crosser) fires. Same outcome, one fewer special case."""
        rest = dict(side='DOWN', price=0.70)
        act, _, _, why = self.q.decide(**{**OK, 'resting': rest})
        self.assertEqual(act, 'cancel'); self.assertIn('we would cross', why)

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


if __name__ == '__main__':
    unittest.main(verbosity=1)


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
        self.now = self.ep + 120            # a chosen second inside the 60-180 window
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

    def test_reason_2_past_180(self):
        act, _, _, why = self.q.decide(**{**OK, 'sec': 181, 'resting': self.rest()})
        self.assertEqual(act, 'cancel'); self.assertIn('outside', why)

    def test_reason_3_we_would_be_the_crosser(self):
        """Our price must stay at or under the best bid."""
        act, _, _, why = self.q.decide(**{**OK, 'up_bid': 0.69, 'resting': self.rest(0.70)})
        self.assertEqual(act, 'cancel'); self.assertIn('we would cross', why)

    def test_reason_4_bid_ran_two_ticks_away(self):
        act, _, _, why = self.q.decide(**{**OK, 'up_bid': 0.72, 'resting': self.rest(0.70)})
        self.assertEqual(act, 'cancel'); self.assertIn('ran >= 2 ticks', why)

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
        n = int((self.ep + 120) * 1000)
        self.p.mover.add(n - 900, 100000.0); self.p.mover.add(n, 100000.0)

    def tearDown(self): M.tokens_for = self._orig; self.loop.close()

    def test_a_dry_post_leaves_a_virtual_order_resting(self):
        self.loop.run_until_complete(self.p.one_pass(now=self.ep + 120))
        self.assertIsNotNone(self.p.resting)
        self.assertIsNone(self.p.resting['order_id'], 'a dry order must carry no venue id')

    def test_a_stable_book_produces_ONE_post_not_three(self):
        """The regression the cap was masking: with the book unchanged the probe must post once
        and then sit, not re-post until it hits the ceiling."""
        for t in range(120, 150):
            self.loop.run_until_complete(self.p.one_pass(now=self.ep + t))
        self.assertEqual(self.p.posts_per_epoch[self.ep], 1,
                         f'posted {self.p.posts_per_epoch[self.ep]}x on a book that never moved')

    def test_dry_mode_puts_our_virtual_order_into_the_book_it_reads(self):
        """Live, our resting BUY is the best bid on its side. The dry sim must reproduce that or it
        over-cancels on V's rule 3 and its resting life is meaningless."""
        self.loop.run_until_complete(self.p.one_pass(now=self.ep + 120))
        self.assertIsNotNone(self.p.resting)
        px = self.p.resting['price']
        self.p.books['TOKUP']['bids'] = [(px - 0.01, 500.0)]      # real bid ticks BELOW us
        for t in range(121, 135):
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
        self.now = self.ep + 120
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

    def fills(self): return self.p.db.execute('select count(*) from fills').fetchone()[0]

    def test_a_fill_survives_a_pass_that_wanted_to_cancel(self):
        """The exact hole: rule 3 wants a cancel, the order has in fact filled."""
        self.book(0.69)                        # our 0.70 is above the best bid -> cancel wanted
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
        self.book(0.69)
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.assertEqual(self.fills(), 0)
        self.assertEqual(self.p.db.execute("select status from orders where id=1").fetchone()[0],
                         'CANCELLED')
        self.assertIsNone(self.p.resting)

    def test_the_pre_cancel_check_ignores_the_throttle(self):
        """Throttling the routine check must never be able to delay the pre-cancel one."""
        self.will_fill = False
        self.book(0.69)
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
        self.book(0.69)
        self.p._last_fill_check = self.now
        self.loop.run_until_complete(self.p.one_pass(now=self.now))
        self.p.db.execute("update fills set pnl=-10.0"); self.p.db.commit()
        ok, why = self.p.guard.may_trade()
        self.assertFalse(ok); self.assertIn('DAY STOP', why)

    def test_a_fill_recorded_this_way_trips_the_lifetime_stop(self):
        self.book(0.69)
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
        self.now = self.ep + 120
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
