"""12.18.0: MAIN/REVERSAL are priced by a maximum entry, not by EF's model-EV test,
and a PAPER lane may top a plan up to the venue's 5-share minimum.

Run against poly_core.order_plan itself (the running artifact's function), with the
quote shape the engine passes it, on the exact refusals Zurich logged in MAIN's first
45 minutes ON: ask 0.85, p 0.75, stake $3."""
import unittest
import poly_core as C, poly_lanes as L

TERMS = (0.01, 5.0, 0.0, 1.0)           # tick, 5-share minimum, no venue fee curve (Polymarket rate=0 in journals)
def quote(ask, depth=200.0):
    return dict(ask=ask, asks=[(ask, depth), (round(ask + 0.01, 2), depth)], age_ms=20.0, seq=1)

class LaneCap(unittest.TestCase):
    def test_ef_decision_still_uses_model_ev(self):
        d = dict(p=0.75, threshold=0.0)                       # EF-shaped: no price_rule
        with self.assertRaises(ValueError) as cm:
            C.order_plan(quote(0.85), TERMS, 3.0, d, pad=1)
        self.assertIn('price fails model EV', str(cm.exception))

    def test_lane_decision_is_not_refused_by_model_ev(self):
        d = dict(p=0.75, threshold=L.LANE_EV_FLOOR, price_rule='lane_cap', max_ask=L.LANE_MAX_ASK, min_topup=True)
        plan = C.order_plan(quote(0.85), TERMS, 3.0, d, pad=1)   # Zurich's refused case
        self.assertGreaterEqual(plan['max_shares'] + 1e-9, 5.0, 'topped up to the 5-share minimum')
        self.assertAlmostEqual(plan['amount'], 4.30, places=2)     # 5 shares x cap 0.86
        self.assertGreaterEqual(plan['budget'], plan['amount'])

    def test_lane_decision_refused_above_the_cap(self):
        d = dict(p=0.95, threshold=L.LANE_EV_FLOOR, price_rule='lane_cap', max_ask=L.LANE_MAX_ASK, min_topup=True)
        with self.assertRaises(ValueError) as cm:
            C.order_plan(quote(0.93), TERMS, 3.0, d, pad=1)
        self.assertIn('above lane cap', str(cm.exception))

    def test_live_lane_is_not_topped_up(self):
        d = dict(p=0.75, threshold=L.LANE_EV_FLOOR, price_rule='lane_cap', max_ask=L.LANE_MAX_ASK, min_topup=False)
        with self.assertRaises(ValueError) as cm:
            C.order_plan(quote(0.85), TERMS, 3.0, d, pad=1)
        self.assertIn('below venue minimum', str(cm.exception))

    def test_lane_below_minimum_ask_needs_no_topup(self):
        d = dict(p=0.60, threshold=L.LANE_EV_FLOOR, price_rule='lane_cap', max_ask=L.LANE_MAX_ASK, min_topup=True)
        plan = C.order_plan(quote(0.55), TERMS, 3.0, d, pad=1)
        self.assertAlmostEqual(plan['budget'], 3.0)                # stake untouched when 5 shares already fit

    def test_lane_decisions_carry_the_rule(self):
        # the dicts the lanes emit must carry price_rule/max_ask, or order_plan falls back to the EV test
        import inspect
        src = inspect.getsource(L.LaneEngine._try_main) + inspect.getsource(L.LaneEngine._watch_reversal)
        self.assertEqual(src.count("price_rule='lane_cap'"), 2)
        self.assertEqual(L.LaneEngine().monitor()['thresholds']['lane_max_ask'], L.LANE_MAX_ASK)

if __name__ == '__main__':
    unittest.main()
