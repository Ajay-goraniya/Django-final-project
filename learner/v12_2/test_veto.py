"""13.2.0 DRAFT: the delay-brain veto (poly_veto). It may only REMOVE an EF fire, only when meta ef_veto is enabled,
and a missing input or an unloadable model never blocks trading. Run against the modules and the shipped model file."""
import json, math, pathlib, tempfile, time, unittest
import numpy as np
import poly_veto as V

HERE = pathlib.Path(__file__).parent
MODEL = V.load(str(HERE / 'ef_veto_brain.json'))


def _feats(model, val=0.0):
    return {k: val for k in model['feature_names'] if k not in V.EXTRA}


def _fire(model, **over):
    d = dict(fire=True, side='UP', p=.62, p_raw=.62, ask=.40, features=_feats(model))
    d.update(over); return d


def _toy(w0, names=('a', 'b')):
    n = len(names) + 3
    fit = dict(mean=[0.0] * n, sd=[1.0] * n, weights=[w0] + [0.0] * n, train_days=['x'], n_train=1)
    return dict(intercept_first=True, feature_names=list(names) + list(V.EXTRA), all_days=fit, folds=[])


class Shape(unittest.TestCase):
    def test_shipped_model_matches_zurich_export(self):
        z = json.loads((HERE.parent.parent / 'analysis' / 'zurich' / 'ef_veto_brain.json').read_text())
        self.assertEqual(MODEL['feature_names'], z['feature_names'], 'engine copy must be the exported model')
        self.assertEqual(MODEL['all_days']['weights'], z['all_days']['weights'])
        self.assertEqual(MODEL['feature_names'][-3:], list(V.EXTRA))
    def test_load_rejects_a_mismatched_model(self):
        bad = _toy(0.0); bad['all_days']['weights'] = [0.0]
        p = tempfile.mktemp(suffix='.json'); pathlib.Path(p).write_text(json.dumps(bad))
        with self.assertRaises(ValueError): V.load(p)


class Arithmetic(unittest.TestCase):
    def test_predict_equals_an_independent_numpy_dot(self):
        rng = np.random.default_rng(3); fit = MODEL['all_days']
        x = [float(v) for v in rng.normal(size=len(MODEL['feature_names']))]
        mu, sd, w = np.array(fit['mean']), np.array(fit['sd']), np.array(fit['weights'])
        sd = np.where(np.abs(sd) > 1e-12, sd, 1.0)
        ref = w[0] + float(np.dot(w[1:], (np.array(x) - mu) / sd))
        self.assertAlmostEqual(V.predict(MODEL, x), ref, places=9)
    def test_inputs_are_built_like_training(self):
        """ef_delay_brain.py: lg() clamps to [1e-3, 1-1e-3]; sec = t - epoch; p_raw falls back to p."""
        ep = 1_790_000_000
        x, miss = V.vector(MODEL, _fire(MODEL, ask=0.0, p_raw=None, p=0.7), ep, ep + 150)
        self.assertIsNone(miss)
        self.assertAlmostEqual(x[-3], math.log(1e-3 / (1 - 1e-3)))
        self.assertAlmostEqual(x[-2], math.log(.7 / .3))
        self.assertAlmostEqual(x[-1], 0.5)


class OnlyRemoves(unittest.TestCase):
    ep = 1_790_000_000
    def test_off_by_default_changes_nothing(self):
        d = _fire(MODEL)
        self.assertIs(V.apply(d, _toy(-5.0), dict(V.DEFAULT), self.ep, self.ep + 60), d)
        self.assertFalse(V.DEFAULT['enabled'])
    def test_negative_prediction_vetoes(self):
        out = V.apply(_fire(_toy(-0.2)), _toy(-0.2), dict(enabled=True, theta=0.0), self.ep, self.ep + 60)
        self.assertFalse(out['fire']); self.assertIn('Veto', out['reason']); self.assertAlmostEqual(out['veto_pred'], -0.2)
    def test_positive_prediction_keeps(self):
        out = V.apply(_fire(_toy(0.3)), _toy(0.3), dict(enabled=True, theta=0.0), self.ep, self.ep + 60)
        self.assertTrue(out['fire']); self.assertEqual(out['veto'], 'keep')
    def test_theta_is_the_bar(self):
        m = _toy(0.03)
        self.assertTrue(V.apply(_fire(m), m, dict(enabled=True, theta=0.0), self.ep, self.ep + 60)['fire'])
        self.assertFalse(V.apply(_fire(m), m, dict(enabled=True, theta=0.05), self.ep, self.ep + 60)['fire'])
    def test_never_creates_a_fire(self):
        d = dict(_fire(_toy(5.0)), fire=False, reason='EV at padded price')
        self.assertIs(V.apply(d, _toy(5.0), dict(enabled=True), self.ep, self.ep + 60), d)
    def test_missing_input_never_vetoes(self):
        m = _toy(-5.0); d = _fire(m); del d['features']['a']
        out = V.apply(d, m, dict(enabled=True), self.ep, self.ep + 60)
        self.assertTrue(out['fire']); self.assertEqual(out['veto'], 'skipped: missing a')
        out = V.apply(dict(_fire(m), ask=float('nan')), m, dict(enabled=True), self.ep, self.ep + 60)
        self.assertTrue(out['fire']); self.assertIn('logit_ask', out['veto'])


class EngineWiring(unittest.TestCase):
    def test_veto_runs_after_every_other_gate_in_decide_now(self):
        import inspect, btc_model_v12_polymarket as E
        body = inspect.getsource(E.PolyRunner.decide_now)
        self.assertLess(body.index('_gate_on_padded_ev'), body.index('self._veto('), 'the veto is the last word, never the first')
    def test_runner_is_off_until_meta_enables_it_and_vetoes_when_on(self):
        from test_v122 import _paper_runner
        r, E = _paper_runner(); ep = int(time.time() // 300) * 300
        try:
            d = _fire(MODEL)
            self.assertIs(r._veto(ep, d, time.time()), d, 'no meta -> untouched')
            r._veto_model = _toy(-1.0)
            r.db.set('ef_veto', dict(enabled=True, theta=0.0))
            out = r._veto(ep, _fire(_toy(-1.0)), time.time())
            self.assertFalse(out['fire']); self.assertIn('Veto', out['reason'])
        finally: r.db.c.close()
    def test_unloadable_model_never_blocks_a_fire(self):
        from test_v122 import _paper_runner
        import btc_model_v12_polymarket as E
        r, _ = _paper_runner(); ep = int(time.time() // 300) * 300
        try:
            r.db.set('ef_veto', dict(enabled=True)); orig = V.load
            V.load = lambda p: (_ for _ in ()).throw(OSError('gone'))
            try: out = r._veto(ep, _fire(MODEL), time.time())
            finally: V.load = orig
            self.assertTrue(out['fire']); self.assertEqual(out['veto'], 'skipped: model not loaded')
        finally: r.db.c.close()


if __name__ == '__main__':
    unittest.main()
