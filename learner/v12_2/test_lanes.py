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


if __name__ == '__main__':
    unittest.main(verbosity=1)
