"""13.4.0 DRAFT: ef6_lane - pre-registered arm E3 as a pure decision function (OFF by default, not wired)."""
import json, tempfile, os, unittest
import ef6_lane as L

# one stump on own_ask: pred = base + (0.2 if own_ask <= 0.5 else -0.2)
MODEL = dict(names=['own_ask', 'sec'], base=0.0, trees=[[0, 0.5, 0.2, -0.2]])


def lane(**cfg):
    return L.EF6Lane(dict(dict(enabled=True, min_rows=4, grid_s=60.0, window_s=3600.0, q=0.5), **cfg), model=L.StumpModel(MODEL))


class Model(unittest.TestCase):
    def test_predict_and_missing_input(self):
        m = L.StumpModel(MODEL)
        self.assertAlmostEqual(m.predict({'own_ask': 0.4}), 0.2)
        self.assertAlmostEqual(m.predict({'own_ask': 0.6}), -0.2)
        self.assertIsNone(m.predict({'own_ask': float('nan')}))
        self.assertIsNone(m.predict({}))
    def test_load_roundtrip_and_no_model_day_never_fires(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, 'ef6_2026-09-29.json'), 'w') as f: json.dump(MODEL, f)
        x = L.EF6Lane(dict(enabled=True, model_dir=d))
        self.assertTrue(x.load_day_model('2026-09-29')); self.assertFalse(x.load_day_model('2026-09-30'))
        self.assertIsNone(x.decide(900, 1000.0, 100, {}, 0.4, 0.6, 'UP', 0.9))


class Seed(unittest.TestCase):
    def test_day_boundary_seed_fills_the_window_and_old_rows_are_dropped(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, 'ef6_2026-09-29.json'), 'w') as f: json.dump(MODEL, f)
        with open(os.path.join(d, 'ef6_2026-09-29_seed.json'), 'w') as f: json.dump([[t, float(t)] for t in range(0, 10)], f)
        x = L.EF6Lane(dict(enabled=True, model_dir=d, min_rows=5, q=0.5))
        x.tq.add(-5.0, 999.0)                                   # a row from the old model must not survive the reload
        self.assertTrue(x.load_day_model('2026-09-29'))
        self.assertEqual(len(x.tq.rows), 10)
        self.assertAlmostEqual(x.tq.threshold(60.0), 4.5)


class Quantile(unittest.TestCase):
    def test_causal_grid_uses_only_rows_before_the_step(self):
        tq = L.TrailingQuantile(0.5, 3600.0, 60.0, 3)
        for t, v in ((10.0, 1.0), (20.0, 2.0), (30.0, 3.0)): tq.add(t, v)
        self.assertIsNone(tq.threshold(59.0))            # step 0: nothing strictly before it
        tq.add(61.0, 100.0)                               # arrives inside step 60 - must not count for step 60
        self.assertAlmostEqual(tq.threshold(61.0), 2.0)
    def test_window_drops_old_rows(self):
        tq = L.TrailingQuantile(0.5, 100.0, 60.0, 1)
        tq.add(0.0, 50.0); tq.add(200.0, 1.0)
        self.assertAlmostEqual(tq.threshold(240.0), 1.0)
    def test_too_few_rows_no_threshold(self):
        tq = L.TrailingQuantile(0.5, 3600.0, 60.0, 500); tq.add(1.0, 1.0)
        self.assertIsNone(tq.threshold(120.0))


class Rule(unittest.TestCase):
    def warm(self, x, t0=0.0):
        for i in range(4): x.decide(600, t0 + i, 30, {}, 0.6, 0.4, 'DOWN', 0.9)   # candidates feed the window
    def test_off_by_default_never_fires_but_still_learns_the_window(self):
        x = L.EF6Lane(dict(min_rows=1), model=L.StumpModel(MODEL))
        self.assertIsNone(x.decide(900, 100.0, 50, {}, 0.4, 0.6, 'UP', 0.9))
        self.assertTrue(len(x.tq.rows) > 0)
    def test_fires_on_the_models_side_above_threshold_once_per_candle(self):
        x = lane(); self.warm(x)
        d = x.decide(900, 120.0, 40, {}, 0.4, 0.6, 'UP', 0.9)
        self.assertEqual(d['side'], 'UP'); self.assertGreaterEqual(d['pred'], d['thr'])
        self.assertIsNone(x.decide(900, 121.0, 41, {}, 0.4, 0.6, 'UP', 0.9))
    def test_pinned_the_cheap_side_never_fires_when_it_is_not_the_models_side(self):
        x = lane(); self.warm(x)
        self.assertIsNone(x.decide(900, 120.0, 40, {}, 0.4, 0.6, 'DOWN', 0.9))   # UP is cheap but p_up = 0.1
    def test_bad_inputs_do_not_raise(self):
        x = lane(); self.warm(x)
        self.assertIsNone(x.decide(900, 120.0, 40, {}, None, None, 'UP', 0.9))
        self.assertIsNone(x.decide(900, 121.0, 40, {}, 0.4, 0.6, 'UP', float('nan')))


class Asks(unittest.TestCase):
    def test_deltas_and_dip30(self):
        a = L.AskState()
        for t, v in ((0.0, 0.50), (25.0, 0.45), (30.0, 0.55)): a.push(t, v, 1 - v)
        f = a.feats('UP', 30.0)
        self.assertAlmostEqual(f['d_ask_30s'], 0.05); self.assertAlmostEqual(f['dip30'], 0.10)


if __name__ == '__main__':
    unittest.main()
