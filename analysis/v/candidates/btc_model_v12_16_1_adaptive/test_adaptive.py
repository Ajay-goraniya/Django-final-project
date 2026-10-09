"""12.16.1 adaptive probability + shared volatility-state regressions."""
import json
import math
import pathlib
import sys
import unittest

import btc_model_v10 as M

HERE = pathlib.Path(__file__).resolve().parent

def logit(p):
    p = min(.999999, max(.000001, float(p)))
    return math.log(p/(1-p))

def sigmoid(z):
    return 1/(1+math.exp(-z))

class AdaptiveEF12161(unittest.TestCase):
    def setUp(self):
        self.frozen = M.Model(HERE / "model_v10.json")
        self.adapt = M.Model(HERE / "model_v10_adaptive.json")

    def feat(self, ratio=1.0, venue=.57):
        f = {k: 0.0 for k in self.adapt.features}
        f.update(p_venue=float(venue), lv=logit(venue), sec_left=180.0, rv60=.5,
                 _ask_up=.58, _ask_dn=.44, _venue_ok=True,
                 adapt_ratio=float(ratio), adapt_raw=float(ratio),
                 adapt_fast_bps=.5, adapt_slow_bps=.25, adapt_ready=1.0)
        return f

    def test_frozen_json_stays_nonadaptive_benchmark(self):
        self.assertFalse(self.frozen.adaptive_enabled)
        f = self.feat(ratio=4.0)
        p = self.frozen.p_up(f)
        self.assertAlmostEqual(p, self.frozen._base_model_p(f), places=12)

    def test_identity_ratio_is_bit_identical_to_frozen_v10_probability(self):
        f = self.feat(ratio=1.0)
        self.assertAlmostEqual(self.adapt.p_up(f), self.frozen.p_up(f), places=12)

    def test_volatility_acceleration_shrinks_only_model_delta_to_venue(self):
        f = self.feat(ratio=2.0, venue=.57)
        final, base, trust, anchor = self.adapt.p_up_detail(f)
        self.assertAlmostEqual(trust, .5, places=12)
        expected = sigmoid(logit(anchor) + .5 * (logit(base) - logit(anchor)))
        self.assertAlmostEqual(final, expected, places=12)
        self.assertLessEqual(abs(logit(final)-logit(anchor)),
                             abs(logit(base)-logit(anchor)) + 1e-12)

    def test_quiet_ratio_never_amplifies_confidence(self):
        f = self.feat(ratio=.55)
        final, base, trust, anchor = self.adapt.p_up_detail(f)
        self.assertAlmostEqual(final, base, places=12)
        self.assertEqual(trust, 1.0)
        self.assertTrue(math.isnan(anchor))

    def test_incomplete_venue_does_not_create_a_fake_anchor(self):
        f = self.feat(ratio=3.0)
        f["_venue_ok"] = False
        final, base, trust, anchor = self.adapt.p_up_detail(f)
        self.assertAlmostEqual(final, base, places=12)
        self.assertEqual(trust, 1.0)
        self.assertTrue(math.isnan(anchor))

    def test_decision_exposes_base_and_adaptive_probability(self):
        f = self.feat(ratio=2.0)
        class State:
            open_ref = "first_trade"
            def features(self, *args): return dict(f)
        d = self.adapt.decide(State(), 0, 120*M.US, ev_threshold=.25)
        for k in ("p_base","adaptive","adaptive_ratio","adaptive_trust","adaptive_anchor"):
            self.assertIn(k, d)
        self.assertTrue(d["adaptive"])
        self.assertAlmostEqual(d["adaptive_ratio"], 2.0)

class FeatureStateAdaptive12161(unittest.TestCase):
    def test_feature_state_emits_continuous_adaptive_metrics(self):
        st = M.FeatureState()
        p = 100000.0
        # 10 min calm (enough for both EF warmup and slow observed baseline)
        for i in range(602):
            p *= math.exp(1e-5 if i % 2 else -1e-5)
            st.on_spot_trade(i*M.US, p, 1.0, False)
        # current candle must contain spot history
        op = 600*M.US
        st.on_venue_quote(.55,.53,.47,.45)
        f = st.features(op, 601*M.US)
        self.assertIn("adapt_ratio", f)
        self.assertIn("adapt_fast_bps", f)
        self.assertGreater(f["adapt_slow_bps"], 0.0)
        self.assertTrue(math.isfinite(f["adapt_ratio"]))

    def test_fast_shock_is_continuous_not_low_mid_high_bucket(self):
        st = M.FeatureState()
        p = 100000.0
        for i in range(1200):
            p *= math.exp(1e-5 if i % 2 else -1e-5)
            st.on_spot_trade(i*M.US, p, 1.0, False)
        calm = st.adapt.value()
        for i in range(1200, 1381):
            p *= math.exp(5e-5 if i % 2 else -5e-5)
            st.on_spot_trade(i*M.US, p, 1.0, False)
        self.assertEqual(calm, 1.0)
        self.assertGreater(st.adapt.value(), 1.15)

class RuntimeDefault12161(unittest.TestCase):
    def test_default_model_is_adaptive_but_frozen_file_is_retained(self):
        import btc_model_v12_polymarket as E
        old = sys.argv[:]
        try:
            sys.argv = ["x"]
            a = E.args()
        finally:
            sys.argv = old
        self.assertEqual(pathlib.Path(a.model).name, "model_v10_adaptive.json")
        self.assertEqual(a.db, "polymarket_v12_16_1_adaptive_paper.sqlite3")
        self.assertTrue((HERE/"model_v10.json").is_file())

if __name__ == "__main__":
    unittest.main(verbosity=1)
