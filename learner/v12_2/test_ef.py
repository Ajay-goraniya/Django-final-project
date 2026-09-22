"""12.22.0: the EF reversal lane (poly_ef) - contrarian to the move against the SETTLEMENT line,
build11's gates at the anchors, a Polymarket price rule, one fire per candle. Run against the modules."""
import unittest
from collections import deque
import poly_ef as E, poly_lanes as L

def synth_metrics(**over):
    m = dict(ef_dir='DOWN', body=25.0, phase=120.0, seconds_left=180.0, distance=0.4, extension_sigma=0.8, opposite_flow=.7, old_flow=.2,
             fast_support=.5, persistence=.6, transition=.6, chop=.2, rejection=.6, recovery=.5, path_quality=.6, new_eff=.5, old_eff=.1,
             old_side_exhaustion=.55, control_transfer=.6, reachability=.8, settlement_feasibility=.7, settlement_probability=.62,
             p_base=.6, quality=.6, fake=.2, real=.65, early_prep=.6, book_support=.5)
    m.update(over); return m

class Gates(unittest.TestCase):
    def test_anchors_are_build11s(self):
        self.assertEqual((E.EF_MIN_REAL_REVERSAL_SCORE, E.EF_MAX_FAKE_REVERSAL_PENALTY, E.EF_MIN_OLD_SIDE_EXHAUSTION, E.EF_MIN_FLOW_PERSISTENCE, E.EF_CONFIRM_WINDOW_MS),
                         (0.56, 0.55, 0.38, 0.42, 250))
    def test_all_gates_pass_on_a_clean_reversal(self):
        self.assertEqual([n for n, ok in E.gates(synth_metrics()) if not ok], [])
    def test_each_gate_can_fail(self):
        for k, v, name in (('real', .5, 'REAL_REVERSAL_SCORE'), ('fake', .6, 'FAKE_REVERSAL'), ('old_side_exhaustion', .3, 'OLD_SIDE_EXHAUSTION'),
                           ('persistence', .3, 'FLOW_PERSISTENCE'), ('chop', .6, 'CHOP'), ('reachability', .3, 'REACH')):
            self.assertIn(name, [n for n, ok in E.gates(synth_metrics(**{k: v})) if not ok])

class PriceRule(unittest.TestCase):
    def test_fires_only_when_cheap_and_the_probability_pays(self):
        ef = E.EFReversal(); m = synth_metrics()
        self.assertIsNone(ef.watch(m, 1000, 0.70, 0.02)); self.assertIn('above', ef.block)              # not cheap
        self.assertIsNone(ef.watch(m, 1000, 0.58, 0.02)); self.assertIn('floor', ef.block)              # 0.62 < 0.58+0.06+fee
        d = ef.watch(m, 1000, 0.40, 0.02); self.assertEqual((d['kind'], d['side'], d['how'], d['max_ask']), ('EF', 'DOWN', 'STRUCTURE_DEVELOPED', E.EF_MAX_ASK))
        self.assertEqual(d['price_rule'], 'lane_cap'); self.assertAlmostEqual(d['p'], .62)
    def test_no_quote_means_no_fire(self):
        ef = E.EFReversal(); self.assertIsNone(ef.watch(synth_metrics(), 1000, None, 0.02)); self.assertIn('quote', ef.block)
    def test_latch_confirms_after_250ms_and_expires(self):
        ef = E.EFReversal(); m = synth_metrics(extension_sigma=0.3)
        self.assertIsNone(ef.watch(m, 1000, 0.40, 0.02)); self.assertEqual(ef.block, 'latched')
        self.assertIsNone(ef.watch(m, 1200, 0.40, 0.02)); self.assertIn('latch 200', ef.block)
        d = ef.watch(m, 1300, 0.40, 0.02); self.assertEqual(d['how'], 'STRUCTURE_CONFIRMED')
        ef2 = E.EFReversal(); ef2.watch(m, 1000, 0.40, 0.02); self.assertIsNone(ef2.watch(m, 2000, 0.40, 0.02)); self.assertEqual(ef2.block, 'latch expired')
    def test_window_and_one_per_candle(self):
        ef = E.EFReversal(); self.assertIsNone(ef.watch(synth_metrics(phase=10.0), 1000, .4, .02)); self.assertEqual(ef.block, 'outside window')
        ef.fired = {'direction': 'DOWN'}; self.assertIsNone(ef.watch(synth_metrics(), 1000, .4, .02)); self.assertEqual(ef.block, 'fired')

class Metrics(unittest.TestCase):
    def _tape(self, up_then_down=True):
        """3 minutes: the old side pushes price up 40 above the line, then for the last 5 s aggressive selling
        appears, price stalls under the high and starts to retrace. Returns (f, ticks, prices, now_ms, line, sigma)."""
        ticks = deque(); prices = deque(); t0 = 1_000_000_000; line = 100_000.0; px = line
        for s in range(0, 175):                                   # 175 s of the old side (buying) with a rising price
            px += 0.25; ticks.append((t0 + s * 1000, +800.0)); prices.append(((t0 + s * 1000) / 1000.0, px))
        hi = px
        for s in range(175, 181):                                 # 6 s: sellers hit, price rejected at the high, retraces
            px -= 1.5; ticks.append((t0 + s * 1000, -1500.0)); ticks.append((t0 + s * 1000 + 300, -900.0)); prices.append(((t0 + s * 1000) / 1000.0, px))
        now_ms = t0 + 180 * 1000 + 900
        f = dict(price=px, phase_second=181.0, delta_1s=-2400.0, delta_5s=-11000.0, delta_30s=20000.0, return_5s_bps=(px / (px + 7.5) - 1) * 1e4,
                 spot_imbalance5=-0.2, reject_up=3.0, reject_down=0.0, candle_high_seen=hi, candle_low_seen=line - 2.0)
        return f, ticks, prices, now_ms, line, 2.0
    def test_side_is_contrarian_to_the_move_against_the_line(self):
        f, ticks, prices, now_ms, line, sig = self._tape(); m = E.ef_metrics(f, ticks, prices, now_ms, line, sig)
        self.assertEqual(m['ef_dir'], 'DOWN'); self.assertGreater(m['body'], 0)
        f2 = dict(f, price=line - 30.0, candle_high_seen=line + 1, candle_low_seen=line - 40); m2 = E.ef_metrics(f2, ticks, prices, now_ms, line, sig)
        self.assertEqual(m2['ef_dir'], 'UP')
    def test_exhaustion_and_control_read_the_flip(self):
        f, ticks, prices, now_ms, line, sig = self._tape(); m = E.ef_metrics(f, ticks, prices, now_ms, line, sig)
        self.assertGreater(m['persistence'], 0.5); self.assertGreater(m['control_transfer'], 0.4); self.assertGreater(m['old_side_exhaustion'], 0.3)
        self.assertLess(m['fake'], 0.55); self.assertGreater(m['real'], 0.4)
        for k in ('settlement_probability', 'reachability', 'chop'): self.assertTrue(0.0 <= m[k] <= 1.0)
    def test_no_move_no_metrics(self):
        f, ticks, prices, now_ms, line, sig = self._tape(); self.assertIsNone(E.ef_metrics(dict(f, price=line), ticks, prices, now_ms, line, sig))
        self.assertIsNone(E.ef_metrics(f, ticks, prices, now_ms, line, 0.0))
    def test_settlement_uses_the_twap_horizon(self):
        f, ticks, prices, now_ms, line, sig = self._tape(); m = E.ef_metrics(f, ticks, prices, now_ms, line, sig)
        import math; left = 300 - 181; expect = abs(m['body']) / (sig * math.sqrt(left - E.TWAP_HORIZON_SHIFT_S))
        self.assertAlmostEqual(m['distance'], expect, places=6)

class Lane(unittest.TestCase):
    def test_engine_off_by_default_and_wired(self):
        eng = L.LaneEngine(); self.assertFalse(eng.ef_enabled); self.assertIn('EF', eng.pending); self.assertIsNotNone(eng.ef)
        eng.set_line(100.0, 101.0); self.assertEqual(eng.line_open, 100.0); eng.set_line(None); self.assertIsNone(eng.line_open)
        self.assertEqual(eng.ef_monitor()['enabled'], False)
    def test_confirm_marks_fired_and_counts_refusals(self):
        eng = L.LaneEngine(); eng.ef_signal = dict(direction='DOWN', ts_ms=1, probability_up=.4)
        eng.confirm('EF', False, 'above cap'); self.assertEqual(eng.ef.attempts, 1); self.assertIsNone(eng.ef.fired)
        eng.confirm('EF', True); self.assertEqual(eng.ef.fired['direction'], 'DOWN')
        eng.on_candle(dict(time=300_000, open=1, high=1, low=1, close=1, volume=0)); eng.on_candle(dict(time=600_000, open=1, high=1, low=1, close=1, volume=0))
        self.assertIsNone(eng.ef.fired, 'a new candle resets the EF lane')
    def test_ticks_are_kept_for_32s(self):
        eng = L.LaneEngine()
        for s in range(0, 60): eng.on_spot_trade(s * 1000, 100.0, 1.0, False)
        self.assertLessEqual(eng.ticks[0][0], 59_000 - 27_000 + 1000); self.assertGreaterEqual(eng.ticks[0][0], 59_000 - 32_000)

if __name__ == '__main__': unittest.main()
