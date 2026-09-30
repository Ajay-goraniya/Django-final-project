#!/usr/bin/env python3
"""Tests for the five safety properties the owner's YES is conditional on, plus the shared-wallet rule.

These are the properties, not the strategy. A probe that loses money is a result; a probe that
crosses the spread, outlives its cancel, doubles up, or reaches into 8787's orders is a fault.
"""
import re, sqlite3, sys, time, unittest
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

    def test_a_risen_bid_is_a_cancel_then_a_repost_never_a_second_order(self):
        rest = dict(side='UP', price=0.69)
        act, _, _, why = self.q.decide(**{**OK, 'resting': rest})
        self.assertEqual(act, 'cancel'); self.assertEqual(why, 'bid_moved')

    def test_a_flipped_favourite_cancels_rather_than_adding_a_side(self):
        rest = dict(side='DOWN', price=0.70)
        act, _, _, why = self.q.decide(**{**OK, 'resting': rest})
        self.assertEqual(act, 'cancel'); self.assertIn('flipped', why)

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

    def test_becoming_not_calm_pulls_a_resting_order(self):
        rest = dict(side='UP', price=0.70)
        self.assertEqual(self.q.decide(**{**OK, 'vol': 0.5, 'resting': rest})[0], 'cancel')


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
