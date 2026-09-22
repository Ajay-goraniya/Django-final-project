"""MAIN / REVERSAL port parity tests against the Build 11.2 specification."""
import unittest, poly_lanes as L


def engine_with(volume_ratio_median=100.0):
    e = L.LaneEngine()
    base = 100000.0
    # 24 closed candles: small bodies so fair odds move readily, known volume median
    for i in range(24):
        e.on_closed_candle(dict(time=(i * 300) * 1000, open=base, high=base + 10,
                                low=base - 10, close=base + 2, volume=volume_ratio_median))
    return e


def drive(e, t0, price, seconds, imbalance=0.9, buy=True, step_ms=200, volume=100.0,
          open_price=100000.0, high=None, low=None, candle_id=0):
    """Push aligned flow for `seconds`, returning any lane decision that fires.

    candle_id stays fixed across a call so that advancing t0 moves the clock
    WITHIN one 5-minute candle. Changing it is what starts a new candle, which
    resets MAIN/REVERSAL - the first draft of this harness moved both together
    and so never reached the reversal path at all.
    """
    bids = [(price - 1, 50.0)] * 5
    asks = [(price + 1, 50.0)] * 5
    if imbalance > 0:
        bids = [(price - 1, 100.0)] * 5; asks = [(price + 1, 2.0)] * 5
    else:
        bids = [(price - 1, 2.0)] * 5; asks = [(price + 1, 100.0)] * 5
    out = []
    ts = t0
    end = t0 + int(seconds * 1000)
    while ts <= end:
        e.on_candle(dict(time=candle_id, open=open_price, high=high if high is not None else max(price, open_price),
                         low=low if low is not None else min(price, open_price), close=price, volume=volume))
        e.on_depth(bids, asks)
        e.on_spot_trade(ts, price, 1.0, not buy)   # is_buyer_maker False => aggressive buy
        d = e.evaluate(ts)
        if d: out.append((ts, d))
        ts += step_ms
    return out


class MainLane(unittest.TestCase):
    def test_does_not_fire_before_hold_time(self):
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=5, step_ms=50)   # 5s, 100 reads
        self.assertEqual(fired, [], 'MAIN must not fire before MAIN_HOLD_MS even with enough reads')

    def test_does_not_fire_before_hold_reads(self):
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=1000)  # 20s but only 21 reads
        self.assertEqual(fired, [], 'MAIN must not fire before MAIN_HOLD_READS even after 12s')

    def test_fires_once_both_satisfied(self):
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100)   # 20s, 200 reads
        self.assertTrue(fired, 'MAIN should fire once hold time and reads are both met')
        ts, d = fired[0]
        self.assertEqual(d['kind'], 'MAIN'); self.assertEqual(d['side'], 'UP')
        self.assertGreaterEqual(ts, L.MAIN_HOLD_MS)
        self.assertEqual(len(fired), 1, 'MAIN is once per candle')

    def test_blocked_by_thin_volume(self):
        e = engine_with(volume_ratio_median=100000.0)   # this candle's pace far below median
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100, volume=1.0)
        self.assertEqual(fired, [], 'volume_ratio below GATED_VOL_MIN must block MAIN')

    def test_blocked_when_odds_disagree(self):
        # Pressure says UP but price is below the open, so fair_p_up < 0.60.
        e = engine_with()
        fired = drive(e, 0, 99940.0, seconds=20, step_ms=100, open_price=100000.0)
        for _, d in fired:
            self.assertNotEqual(d['side'], 'UP', 'UP requires fair_p_up >= GATED_ODDS_UP')

    def test_blocked_after_last_second(self):
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100)
        e2 = engine_with()
        out = []
        ts = int(L.MAIN_LAST_SECOND * 1000) + 1000
        for _ in range(200):
            e2.on_candle(dict(time=0, open=100000.0, high=100060.0, low=100000.0, close=100060.0, volume=100.0))
            e2.on_depth([(100059, 100.0)] * 5, [(100061, 2.0)] * 5)
            e2.on_spot_trade(ts, 100060.0, 1.0, False)
            d = e2.evaluate(ts)
            if d: out.append(d)
            ts += 100
        self.assertEqual(out, [], 'no MAIN after MAIN_LAST_SECOND')
        self.assertIn('outside', e2.main_block)


class ReversalLane(unittest.TestCase):
    def _main_up(self):
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100)
        self.assertTrue(fired and fired[0][1]['kind'] == 'MAIN')
        # REVERSAL hedges a real position, so the order has to have been placed.
        e.confirm('MAIN', placed=True)
        return e

    def test_requires_a_main_first(self):
        e = engine_with()
        # Drive DOWN flow only; with no MAIN there can be no REVERSAL.
        fired = drive(e, 0, 99940.0, seconds=40, step_ms=100, imbalance=-0.9, buy=False)
        self.assertTrue(all(d['kind'] != 'REVERSAL' for _, d in fired))

    def test_does_not_fire_while_signal_agrees(self):
        e = self._main_up()
        more = drive(e, 20000, 100080.0, seconds=30, step_ms=100, candle_id=0)
        self.assertTrue(all(d['kind'] != 'REVERSAL' for _, d in more))
        self.assertIn('agrees', e.reversal_state['detail'])

    def test_fires_when_signal_flips_against_main(self):
        e = self._main_up()
        flipped = drive(e, 40000, 99930.0, seconds=30, step_ms=100,
                        imbalance=-0.9, buy=False, open_price=100000.0, candle_id=0)
        revs = [d for _, d in flipped if d['kind'] == 'REVERSAL']
        self.assertTrue(revs, 'REVERSAL should fire when the alignment names the opposite side')
        self.assertEqual(revs[0]['side'], 'DOWN')
        self.assertEqual(len(revs), 1, 'REVERSAL is once per candle')

    def test_main_stays_open_after_reversal(self):
        e = self._main_up()
        drive(e, 40000, 99930.0, seconds=30, step_ms=100, imbalance=-0.9, buy=False, candle_id=0)
        self.assertIsNotNone(e.current_main, 'REVERSAL is a hedge leg, MAIN is not closed')
        self.assertEqual(e.current_main['direction'], 'UP')

    def test_window_is_enforced(self):
        e = self._main_up()
        early = drive(e, 1000, 99930.0, seconds=10, step_ms=100, imbalance=-0.9, buy=False, candle_id=0)
        self.assertTrue(all(d['kind'] != 'REVERSAL' for _, d in early),
                        'no REVERSAL before REVERSAL_MIN_SECOND')


class Primitives(unittest.TestCase):
    def test_pressure_gauge_matches_spec(self):
        self.assertAlmostEqual(L.pressure_score(0.3, 0.25, 1.0), 0.45 + 0.35 + 0.20)
        self.assertEqual(L.pressure_text(0.10, 20), 'BALANCED')
        self.assertTrue(L.pressure_text(0.50, 20).startswith('UP strong'))
        self.assertTrue(L.pressure_text(-0.20, 20).startswith('DOWN weak'))

    def test_confidence_factors_bounds(self):
        self.assertAlmostEqual(L.volume_factor(0.0), L.VOL_FLOOR_FACTOR)
        self.assertAlmostEqual(L.volume_factor(1.5), 1.0)
        self.assertAlmostEqual(L.runway_factor(0.0), 0.5)
        self.assertAlmostEqual(L.rejection_factor(1.0, 0.0, 0.0), 1.0)
        self.assertLess(L.rejection_factor(1.0, 10.0, 0.0), 1.0)
        self.assertAlmostEqual(L.feasibility_factor(0.0, 1.0, 100.0), 1.0)

    def test_model_weights_clamped_to_anchor_band(self):
        m = L.Model({'delta_1s': 99.0})
        self.assertAlmostEqual(m.weights['delta_1s'], 1.10 + L.MODEL_WEIGHT_CLAMP)

class SignalIsNotAPosition(unittest.TestCase):
    """v12.2.3 latched the candle the moment MAIN called it, before any order was
    attempted. A MAIN the EV guard refused therefore showed on the dashboard as
    though it had traded, and could never retry when the price improved."""

    def _fired(self):
        e = engine_with()
        out = drive(e, 0, 100060.0, seconds=20, step_ms=100)
        self.assertTrue(out and out[0][1]['kind'] == 'MAIN')
        return e

    def test_calling_it_does_not_create_a_position(self):
        e = self._fired()
        self.assertIsNotNone(e.main_signal, 'the call is recorded')
        self.assertIsNone(e.current_main, 'but nothing is held until an order is placed')
        self.assertFalse(e.monitor()['main_placed'])

    def test_a_refused_order_lets_the_lane_try_again(self):
        e = self._fired()
        e.confirm('MAIN', placed=False, reason='padded price fails model EV')
        self.assertIsNone(e.current_main)
        self.assertEqual(e.main_attempts, 1)
        again = drive(e, 21000, 100070.0, seconds=6, step_ms=100, candle_id=0)
        self.assertTrue([d for _, d in again if d['kind'] == 'MAIN'],
                        'the signal still stands, so it may fire again at a better price')

    def test_a_placed_order_ends_the_candle_for_main(self):
        e = self._fired()
        e.confirm('MAIN', placed=True)
        self.assertIsNotNone(e.current_main)
        again = drive(e, 21000, 100070.0, seconds=6, step_ms=100, candle_id=0)
        self.assertEqual([d for _, d in again if d['kind'] == 'MAIN'], [],
                         'one position per candle')

    def test_retries_are_capped(self):
        e = self._fired()
        for _ in range(L.LaneEngine.MAIN_MAX_ATTEMPTS):
            e.confirm('MAIN', placed=False, reason='not payable')
        again = drive(e, 21000, 100070.0, seconds=6, step_ms=100, candle_id=0)
        self.assertEqual([d for _, d in again if d['kind'] == 'MAIN'], [])
        self.assertIn('not payable after', e.main_block)

    def test_reversal_fires_on_the_main_call_even_if_no_order_was_placed(self):
        """12.14.0 inverts the test that stood here. Deliberately.

        The old test asserted 'no REVERSAL while MAIN holds nothing', on the
        reasoning that hedging an untaken position is an outright bet. True, and
        not what build11 does: btc_model_build11.py:17151 sets current_main when
        the PREDICTION is stored, and may_execute(kind) is consulted afterwards
        at 16804 to decide whether an order goes out. The owner's Tokyo box runs
        MAIN OFF / EF OFF / REVERSAL ON and REVERSAL trades there.

        So this must fail if anyone restores the 'real position' requirement.
        """
        e = self._fired()
        e.confirm('MAIN', placed=False, reason='padded price fails model EV')
        self.assertIsNone(e.current_main, 'nothing was bought')
        flipped = drive(e, 40000, 99930.0, seconds=30, step_ms=100,
                        imbalance=-0.9, buy=False, candle_id=0)
        revs = [d for _, d in flipped if d['kind'] == 'REVERSAL']
        self.assertTrue(revs, 'the MAIN call stands, so REVERSAL watches it')
        self.assertEqual(revs[0]['side'], 'DOWN')
        self.assertIn('call only', e.reversal_state['detail'],
                      'and it says so: an unplaced MAIN is named, not hidden')

    def test_reversal_names_a_placed_main_without_the_call_only_note(self):
        e = self._fired()
        e.confirm('MAIN', placed=True)
        drive(e, 40000, 99930.0, seconds=30, step_ms=100,
              imbalance=-0.9, buy=False, candle_id=0)
        self.assertNotIn('call only', e.reversal_state['detail'])

    def test_reversal_fires_when_the_engine_never_confirms_at_all(self):
        """The exact path Task 114 runs, and the one confirm()-based tests miss.

        With main_enabled False the engine drops the MAIN decision at
        `ui.allowed(kind)` (btc_model_v12_polymarket.py) and returns BEFORE
        `lanes.confirm(...)`, so the lane is never told anything: pending['MAIN']
        stays True and current_main stays None for the whole candle. REVERSAL
        must still fire off main_signal. Tested here because the other reversal
        tests all call confirm() and would pass even if this path did not work.
        """
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100)
        self.assertTrue([d for _, d in fired if d['kind'] == 'MAIN'])
        self.assertTrue(e.pending['MAIN'], 'no confirm arrived, so the call is still outstanding')
        self.assertIsNone(e.current_main)
        flipped = drive(e, 40000, 99930.0, seconds=30, step_ms=100,
                        imbalance=-0.9, buy=False, candle_id=0)
        revs = [d for _, d in flipped if d['kind'] == 'REVERSAL']
        self.assertTrue(revs, 'REVERSAL must not depend on the engine confirming MAIN')
        self.assertEqual(revs[0]['side'], 'DOWN')

    def test_no_main_call_no_reversal(self):
        """The floor that survives: REVERSAL still needs a MAIN *call*."""
        e = engine_with()
        self.assertIsNone(e.main_signal)
        flipped = drive(e, 40000, 99930.0, seconds=8, step_ms=100,
                        imbalance=-0.9, buy=False, candle_id=0)
        self.assertEqual([d for _, d in flipped if d['kind'] == 'REVERSAL'], [],
                         'with no MAIN call there is nothing to flip against')

    def test_reversal_fires_once_main_actually_holds(self):
        e = self._fired()
        e.confirm('MAIN', placed=True)
        flipped = drive(e, 40000, 99930.0, seconds=30, step_ms=100,
                        imbalance=-0.9, buy=False, candle_id=0)
        revs = [d for _, d in flipped if d['kind'] == 'REVERSAL']
        self.assertTrue(revs); self.assertEqual(revs[0]['side'], 'DOWN')

    def test_monitor_reports_both_states_distinctly(self):
        e = self._fired()
        e.confirm('MAIN', placed=False, reason='padded price fails model EV')
        m = e.monitor()
        self.assertEqual(m['main_signal']['direction'], 'UP')
        self.assertIsNone(m['main'])
        self.assertFalse(m['main_placed'])
        self.assertIn('EV', m['main_last_reason'])


class ReversalProbability12150(unittest.TestCase):
    """REVERSAL handed order_plan the probability of the side it was NOT buying.

    The old code flipped twice: `p_up = fair if UP else 1-fair` (already the
    side's probability) and then `p_side = p_up if UP else 1-p_up`. A DOWN
    reversal with fair_p_up 0.0100 reached the EV gate as p=0.0100 when P(DOWN)
    was 0.9900. Because _aligned_direction only names DOWN when fair_p_up <=
    GATED_ODDS_DOWN, the p was always <= 0.40 against a ~0.60 ask, so DOWN
    REVERSAL could never clear EV and failed as "price fails model EV".
    These tests fail if anyone reintroduces the second flip.
    """
    def _reversal(self, down):
        e = engine_with()
        if down:
            drive(e, 0, 100060.0, seconds=20, step_ms=100)          # MAIN calls UP
            e.confirm('MAIN', placed=False)
            fl = drive(e, 40000, 99930.0, seconds=30, step_ms=100,
                       imbalance=-0.9, buy=False, candle_id=0)
        else:
            drive(e, 0, 99940.0, seconds=20, step_ms=100, imbalance=-0.9, buy=False)
            e.confirm('MAIN', placed=False)
            fl = drive(e, 40000, 100070.0, seconds=30, step_ms=100, candle_id=0)
        revs = [d for _, d in fl if d['kind'] == 'REVERSAL']
        self.assertTrue(revs, 'harness must produce a REVERSAL to test')
        return e, revs[0]

    def test_down_reversal_gets_the_probability_of_down(self):
        e, d = self._reversal(down=True)
        fair = e.feature['fair_p_up']
        self.assertEqual(d['side'], 'DOWN')
        self.assertAlmostEqual(d['p'], 1.0 - fair, places=9,
                               msg='p must be P(the side being bought)')
        self.assertGreater(d['p'], 0.5,
                           'a DOWN reversal fires because DOWN is likely; p must reflect that')

    def test_up_reversal_gets_the_probability_of_up(self):
        e, d = self._reversal(down=False)
        fair = e.feature['fair_p_up']
        self.assertEqual(d['side'], 'UP')
        self.assertAlmostEqual(d['p'], fair, places=9)

    def test_probability_up_means_probability_of_up_on_both_sides(self):
        for down in (True, False):
            e, d = self._reversal(down=down)
            self.assertAlmostEqual(d['probability_up'], e.feature['fair_p_up'], places=9,
                                   msg='the field is named probability_up on both sides')

    def test_main_and_reversal_agree_on_the_convention(self):
        """MAIN was always right; the two must not drift apart again."""
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100)
        main = [d for _, d in fired if d['kind'] == 'MAIN'][0]
        self.assertAlmostEqual(main['p'], main['probability_up'], places=9,
                               msg='for an UP call both are P(UP)')
        _, rev = self._reversal(down=False)
        self.assertAlmostEqual(rev['p'], rev['probability_up'], places=9,
                               msg='same for an UP reversal')


if __name__ == '__main__':
    unittest.main(verbosity=1)


class AdaptRatio12160(unittest.TestCase):
    """build 11's adapt_ratio port: identity in calm tape, engages on a fast/slow
    vol break, resets on a stale feed, and scales fair_odds' typical move."""
    def _feed(self, ar, secs, step, start=0, price=100000.0):
        import random
        rnd = random.Random(7); p = price
        for i in range(secs):
            p *= 1.0 + rnd.gauss(0.0, step)
            ar.add((start + i) * 1000, p)
        return p
    def test_cold_is_identity(self):
        ar = L.AdaptRatio()
        self._feed(ar, 30, 1e-5)
        self.assertEqual(ar.value(), 1.0)
    def test_calm_tape_stays_identity(self):
        ar = L.AdaptRatio()
        self._feed(ar, 1200, 1e-5)
        self.assertEqual(ar.value(), 1.0)
        self.assertTrue(L.ADAPT_IDENTITY_LO <= ar.raw <= L.ADAPT_IDENTITY_HI)
    def test_vol_break_engages_and_is_bounded(self):
        ar = L.AdaptRatio()
        p = self._feed(ar, 1200, 1e-5)
        self._feed(ar, 180, 5e-5, start=1200, price=p)
        self.assertGreater(ar.value(), 1.15)
        self.assertLessEqual(ar.value(), L.ADAPT_RATIO_HI)
    def test_stale_feed_resets(self):
        ar = L.AdaptRatio()
        p = self._feed(ar, 1200, 1e-5)
        self._feed(ar, 180, 5e-5, start=1200, price=p)
        self.assertGreater(ar.value(), 1.0)
        # gap > ADAPT_STALE_BUCKETS: build11:15830-15855 breaks the chain, and
        # the first post-gap return leaves the fast window under ADAPT_MIN_FAST.
        g = 1200 + 180 + 200   # gap longer than the fast window: only fresh returns can rebuild it
        ar.add(g * 1000, p); ar.add((g + 1) * 1000, p); ar.add((g + 2) * 1000, p)
        self.assertEqual(ar.value(), 1.0)
    def test_engaged_ramp(self):
        e = L.engaged_adapt_ratio
        self.assertEqual(e(1.0), 1.0); self.assertEqual(e(1.15), 1.0); self.assertEqual(e(0.85), 1.0)
        self.assertAlmostEqual(e(1.5), 1.5, places=9); self.assertAlmostEqual(e(0.67), 0.67, places=9)
        self.assertAlmostEqual(e(3.0), 3.0, places=9); self.assertEqual(e(10.0), L.ADAPT_RATIO_HI)
        self.assertTrue(1.0 < e(1.3) < 1.3)
    def test_fair_odds_uses_ratio(self):
        eng = L.LaneEngine()
        for i in range(30):
            eng.on_closed_candle(dict(time=i * 300000, open=100000.0, high=100050.0, low=99950.0,
                                      close=100000.0 + (20.0 if i % 2 else -20.0), volume=10.0))
        eng.candle = dict(time=30 * 300000, open=100000.0)
        base, _ = eng.fair_odds(30 * 300000 + 60000, 100030.0, 100000.0)
        eng.adapt.cache = 2.0
        wide, _ = eng.fair_odds(30 * 300000 + 60000, 100030.0, 100000.0)
        self.assertGreater(base, wide); self.assertGreater(wide, 0.5)
        eng.adapt.cache = 1.0
        same, _ = eng.fair_odds(30 * 300000 + 60000, 100030.0, 100000.0)
        self.assertEqual(base, same)


class AdaptRatioJournaled12161(unittest.TestCase):
    """12.16.0 set adapt_ratio only in the feature dict; the journal and /api/state never saw it."""
    def test_monitor_carries_adapt_ratio(self):
        eng = L.LaneEngine(); eng.adapt.cache = 1.7
        self.assertEqual(eng.monitor()["adapt_ratio"], 1.7)
    def test_decision_dicts_carry_adapt_ratio(self):
        import inspect
        src = inspect.getsource(L.LaneEngine)
        self.assertGreaterEqual(src.count("adapt_ratio=self.adapt.value()"), 3)


class SettlementOpen12244(unittest.TestCase):
    """12.24.4: Polymarket settles TWAP60 close vs TWAP60 open. Once the runner hands the lane engine the
    settlement line (set_line), every lane measures from it; without one the Binance first trade stands."""
    def test_line_open_replaces_the_candle_open_in_the_features(self):
        e = engine_with()
        e.on_candle(dict(time=0, open=100000.0, high=100060.0, low=99990.0, close=100050.0, volume=100.0))
        f = e.compute(30000)
        self.assertEqual(f['open_price'], 100000.0)
        e.set_line(100040.0)
        f = e.compute(31000)
        self.assertEqual(f['open_price'], 100040.0, 'the settlement line is the open')
        self.assertAlmostEqual(f['price'], 100050.0)
        e.set_line(None)
        self.assertEqual(e.compute(32000)['open_price'], 100000.0, 'no line -> first trade, as 12.23.x')


class BlockedLaneKeepsPredicting12245(unittest.TestCase):
    """12.24.5, owner: MAIN switched off must still make its prediction and show it as BLOCKED, as the
    Predict.fun builds do. The switch is not an order attempt, and REVERSAL keeps watching MAIN's call."""
    def test_blocked_main_keeps_its_call_spends_no_attempt_and_reversal_still_fires(self):
        e = engine_with()
        fired = drive(e, 0, 100060.0, seconds=20, step_ms=100)
        self.assertTrue(fired and fired[0][1]['kind'] == 'MAIN')
        e.block('MAIN', 'switched off')
        self.assertEqual(e.main_attempts, 0, 'the switch is not an order attempt')
        self.assertIsNotNone(e.main_signal, 'the prediction is kept')
        self.assertIn('BLOCKED', e.main_block)
        self.assertIn('MAIN', e.monitor()['blocked'])
        more = drive(e, 20000, 100080.0, seconds=10, step_ms=100, candle_id=0)
        self.assertFalse([d for _, d in more if d['kind'] == 'MAIN'], 'MAIN calls once per candle, then stays blocked')
        flipped = drive(e, 40000, 99930.0, seconds=30, step_ms=100, imbalance=-0.9, buy=False, candle_id=0)
        self.assertTrue([d for _, d in flipped if d['kind'] == 'REVERSAL'], 'REVERSAL watches the blocked MAIN call')

    def test_block_resets_at_the_next_candle(self):
        e = engine_with()
        drive(e, 0, 100060.0, seconds=20, step_ms=100)
        e.block('MAIN')
        e.on_candle(dict(time=300000, open=100060.0, high=100060.0, low=100060.0, close=100060.0, volume=100.0))
        self.assertEqual(e.monitor()['blocked'], [])
