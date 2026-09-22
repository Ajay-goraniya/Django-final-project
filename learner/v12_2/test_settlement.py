"""12.20.0: the settlement line (Chainlink TWAP60) is computed as the venue settles it, exposed on the
dashboard, and recorded beside every lane decision."""
import json, math, unittest
from types import SimpleNamespace
import btc_model_v10 as M
from poly_dashboard import Dashboard

US = M.US
def state():
    st = M.FeatureState(); op = 1_000_000 * US
    st.on_spot_trade(op - 90 * US, 100.0, 1.0, False); st.on_spot_trade(op, 102.0, 1.0, False); st.on_spot_trade(op + 30 * US, 104.0, 1.0, True)
    for k in range(-70, 31): st.on_ref_price(op + k * US, 101.0 if k < 0 else 103.0)
    return st, op

class Settlement(unittest.TestCase):
    def test_default_is_twap_of_the_feed(self):
        self.assertFalse(M.FeatureState.REF_IS_TWAP)
    def test_features_carry_the_line_in_absolute_terms(self):
        st, op = state(); f = st.features(op, op + 30 * US)
        self.assertEqual((round(f['ref_open'], 6), round(f['ref_now'], 6), f['ref_inst'], f['ref_src']), (101.0, 102.0, 103.0, 1.0))
        self.assertAlmostEqual(f['bn_line_open'], 100.0, places=6)          # Binance TWAP60 before the open
        self.assertAlmostEqual(f['bn_line_now'], (30 * 100 + 30 * 102) / 60, places=6)   # [op-30, op+30): 100 then 102
    def test_without_the_feed_the_proxy_stands_in(self):
        st = M.FeatureState(); op = 1_000_000 * US
        st.on_spot_trade(op - 90 * US, 100.0, 1.0, False); st.on_spot_trade(op, 102.0, 1.0, False)
        f = st.features(op, op + 5 * US)
        self.assertEqual(f['ref_src'], 0.0); self.assertEqual(f['ref_inst_ok'], 0.0); self.assertAlmostEqual(f['ref_open'], 100.0, places=6)
    def test_dashboard_settlement_card(self):
        st, op = state()
        for k in range(31, 251): st.on_ref_price(op + k * US, 103.0)                       # feed covers up to now = op+250
        st.on_spot_trade(op + 250 * US, 104.0, 1.0, True); f = st.features(op, op + 250 * US)
        d = Dashboard.__new__(Dashboard); d.r = SimpleNamespace(st=st)
        s = d.settlement(f); json.dumps(s, allow_nan=False)
        self.assertEqual((round(s['line_open'], 6), s['source'], s['chainlink_now'], s['binance_last']), (101.0, 'chainlink', 103.0, 104.0))
        self.assertAlmostEqual(s['basis_bps'], (103 / 104 - 1) * 1e4, places=6)
        self.assertEqual(s['locked_s'], 10, 'at 250 s, 10 s of the closing 60 s window is already known')
        self.assertAlmostEqual(s['move_bps'], (s['line_now'] / s['line_open'] - 1) * 1e4, places=6)
    def test_dashboard_settlement_is_serialisable_when_empty(self):
        d = Dashboard.__new__(Dashboard); d.r = SimpleNamespace(st=None)
        s = d.settlement({}); json.dumps(s, allow_nan=False); self.assertIsNone(s['line_open']); self.assertIsNone(s['source'])

class LaneMetrics(unittest.TestCase):
    def test_each_lane_is_graded_on_its_own_fills(self):
        import pathlib, tempfile, poly_core as C
        with tempfile.TemporaryDirectory() as t:
            db = C.Journal(str(pathlib.Path(t) / 'j.db'), 'PAPER', 'abc'); ep = 1_000_000
            for kind, side, oid in (('MAIN', 'UP', 'o1'), ('REVERSAL', 'DOWN', 'o2'), ('EF', 'DOWN', 'o3')):
                db.reserve(ep, {'side': side}, 'tok', 'c', kind); db.order(oid, ep, 1, {'cap': .5}, {}, kind)
                db.fill(oid, ep, 'f' + oid, dict(shares=10., spent=4., fees=.1, price=.4), 'PAPER'); db.order_status(oid, 'FILLED'); db.status(ep, 'FILLED', kind)
            db.grade(ep, 'DOWN'); m = db.lane_metrics()
            self.assertEqual((m['MAIN']['wins'], m['MAIN']['losses']), (0, 1)); self.assertAlmostEqual(m['MAIN']['pnl'], -4.1)
            self.assertEqual((m['REVERSAL']['wins'], m['EF']['wins']), (1, 1)); self.assertAlmostEqual(m['EF']['pnl'], 10 - 4.1)
            self.assertAlmostEqual(db.metrics()['pnl'], -4.1 + 5.9 + 5.9, places=6)    # the per-epoch net, once
            db.c.close()

if __name__ == '__main__': unittest.main()
