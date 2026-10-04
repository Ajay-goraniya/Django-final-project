"""13.3.0 DRAFT: ef2_late - pre-registered arm A as a pure decision function (OFF by default, not wired)."""
import unittest
import ef2_late as L


class FakeScorer:
    """p_win = a fixed table by (side ask); lets the rule be tested without the fitted model's numbers."""
    def __init__(self, p_by_ask): self.t = p_by_ask
    def score(self, row): return self.t.get(round(row['own_ask'], 2), 0.0), dict(n_imputed=0, coef_mass_imputed=0.0)


def lane(p_by_ask, **cfg):
    return L.EF2Late(dict(dict(enabled=True), **cfg), scorer=FakeScorer(p_by_ask))


class Rule(unittest.TestCase):
    def test_off_by_default_never_fires(self):
        x = L.EF2Late(scorer=FakeScorer({0.60: 0.95}))
        self.assertIsNone(x.decide(900, 1000.0, 200, {}, 0.60, 0.41, 'UP', 0.9))
    def test_not_before_s0(self):
        self.assertIsNone(lane({0.60: 0.95}).decide(900, 1000.0, 149, {}, 0.60, 0.41, 'UP', 0.9))
    def test_fires_on_the_side_that_clears_the_margin(self):
        d = lane({0.60: 0.70, 0.41: 0.30}).decide(900, 1000.0, 180, {}, 0.60, 0.41, 'UP', 0.9)
        self.assertEqual(d['side'], 'UP'); self.assertGreaterEqual(d['ev'], 0.02)
    def test_below_margin_does_not_fire(self):
        self.assertIsNone(lane({0.60: 0.61, 0.41: 0.30}).decide(900, 1000.0, 180, {}, 0.60, 0.41, 'UP', 0.9))
    def test_pinned_long_shot_never_fires_even_with_huge_ev(self):
        """A 5c long shot with p_win 0.2 has EV 3x - it must not fire: p_win < 0.5 is not the model's side."""
        self.assertIsNone(lane({0.05: 0.20, 0.96: 0.80}).decide(900, 1000.0, 200, {}, 0.05, 0.96, 'UP', 0.2))
    def test_one_fire_per_candle_and_resets_next_candle(self):
        x = lane({0.60: 0.70})
        self.assertTrue(x.decide(900, 1000.0, 180, {}, 0.60, 0.41, 'UP', 0.9))
        self.assertIsNone(x.decide(900, 1001.0, 181, {}, 0.60, 0.41, 'UP', 0.9))
        self.assertTrue(x.decide(1200, 1300.0, 180, {}, 0.60, 0.41, 'UP', 0.9))
    def test_bad_inputs_do_not_raise(self):
        x = lane({0.60: 0.70})
        self.assertIsNone(x.decide(900, 1000.0, 180, {}, None, None, 'UP', 0.9))
        self.assertIsNone(x.decide(900, 1000.0, 180, {}, 0.60, 0.41, 'UP', float('nan')))


class History(unittest.TestCase):
    def test_ask_deltas_use_the_sample_at_or_before_k(self):
        h = L.AskHistory()
        for t, a in ((0.0, 0.50), (1.0, 0.52), (5.0, 0.55), (30.0, 0.60)):
            h.push(t, a, 1 - a)
        self.assertAlmostEqual(h.delta('UP', 30.0, 1.0), 0.05)
        self.assertAlmostEqual(h.delta('UP', 30.0, 30.0), 0.10)
        self.assertIsNone(L.AskHistory().delta('UP', 5.0, 1.0))


class RealModel(unittest.TestCase):
    def test_the_exported_london44_model_loads_and_scores_a_full_row(self):
        x = L.EF2Late(dict(enabled=True))
        feats = {k: mu for k, mu in zip(x.scorer.names, x.scorer.mean)}
        p, info = x.scorer.score(feats)
        self.assertTrue(0.0 < p < 1.0); self.assertEqual(info['n_imputed'], 0)


if __name__ == '__main__':
    unittest.main()
