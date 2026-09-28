"""13.2.0 DRAFT: pair_bot - the 5m/15m TWAP dominance pair. Pure functions, journal, the live guard and the live leg path
(against a fake broker - no network, no key)."""
import asyncio, json, random, sys, tempfile, time, unittest
from types import SimpleNamespace
import pair_bot as P

CFG = dict(first_sec=0, last_sec=290, margin=0.01, min_gap=1.0, stake=20.0, min_shares=5)


def q(ask, size=100.0):
    return dict(ask=ask, bid=ask - .01, asks=[(ask, size), (ask + .01, 500.0)], age_ms=5.0, seq=1)


class Structure(unittest.TestCase):
    def test_the_pair_never_pays_zero(self):
        """The whole premise: both markets settle on the same X; the dominance legs pay 1 or 2 for every X."""
        rng = random.Random(1)
        for _ in range(20000):
            L15, L5 = rng.uniform(80000, 90000), rng.uniform(80000, 90000)
            legs = P.pair_legs(L15, L5, 0.0)
            if legs is None: continue
            X = rng.uniform(79000, 91000)
            out15 = 'UP' if X >= L15 else 'DOWN'; out5 = 'UP' if X >= L5 else 'DOWN'
            self.assertIn(P.payoff(legs, out15, out5), (1, 2))
    def test_legs_follow_the_lines_and_close_lines_are_skipped(self):
        self.assertEqual(P.pair_legs(100.0, 105.0, 1.0), ('UP', 'DOWN'))
        self.assertEqual(P.pair_legs(105.0, 100.0, 1.0), ('DOWN', 'UP'))
        self.assertIsNone(P.pair_legs(100.0, 100.5, 1.0))
        self.assertIsNone(P.pair_legs(None, 100.0, 1.0))
    def test_twap_is_the_mean_of_the_window_and_needs_coverage(self):
        px = {t: float(t) for t in range(0, 100)}
        self.assertAlmostEqual(P.twap(px, 40, 100), sum(range(40, 100)) / 60)
        self.assertIsNone(P.twap({t: 1.0 for t in range(0, 30)}, 0, 60))
    def test_cost_includes_both_taker_fees(self):
        self.assertAlmostEqual(P.pair_cost(0.90, 0.06), 0.90 + 0.07 * .9 * .1 + 0.06 + 0.07 * .06 * .94)


class Decide(unittest.TestCase):
    T = 1_790_000_100 - (1_790_000_100 % 900)
    def _d(self, sec, a15=.90, a5=.05, L15=100.0, L5=110.0, **kw):
        cfg = dict(CFG, **kw)
        return P.decide(self.T + 600 + sec, self.T, L15, L5, q(a15), q(a5), cfg)
    def test_fires_below_the_margin(self):
        d = self._d(120)
        self.assertEqual(d['legs'], ('UP', 'DOWN')); self.assertLess(d['cost'], .99); self.assertEqual(d['sec'], 120)
        self.assertEqual(d['shares'], int(20.0 / d['cost']))
    def test_not_outside_the_last_5m_window(self):
        self.assertIsNone(P.decide(self.T + 599, self.T, 100., 110., q(.9), q(.05), CFG))
        self.assertIsNone(self._d(290))
    def test_not_when_cost_is_too_high(self):
        self.assertIsNone(self._d(60, a15=.94, a5=.06))
    def test_not_on_a_missing_or_stale_quote(self):
        self.assertIsNone(P.decide(self.T + 700, self.T, 100., 110., None, q(.05), CFG))
    def test_size_is_capped_by_the_thinner_touch_and_the_venue_minimum(self):
        d = P.decide(self.T + 700, self.T, 100., 110., q(.90, size=7.0), q(.05), CFG)
        self.assertEqual(d['shares'], 7)
        self.assertIsNone(P.decide(self.T + 700, self.T, 100., 110., q(.90, size=3.0), q(.05), CFG))


class Feeds(unittest.TestCase):
    def test_rtds_frame_parses_seconds_and_btc_only(self):
        j = [dict(topic='crypto_prices_chainlink', payload=dict(symbol='btc/usd', value=84321.5, timestamp=1790000000123)),
             dict(topic='crypto_prices_chainlink', payload=dict(symbol='eth/usd', value=4000.0, timestamp=1790000000123))]
        self.assertEqual(P.ref_samples(j), [(1790000000, 84321.5)])


class JournalFlow(unittest.TestCase):
    def test_record_legs_settle_and_a_lone_leg_pays_on_its_own_market(self):
        j = P.Journal(tempfile.mktemp(suffix='.sqlite3'))
        d = dict(T=900, ep5=1500, legs=('UP', 'DOWN'), a15=.9, a5=.05, cost=.96, shares=10, L15=1., L5=2., sec=100)
        j.record(d, 'PAPER'); self.assertTrue(j.fired(900))
        j.legs_done(900, 'FILLED', 'NO_FILL', 10, 0, 9.06, 0, {})
        row = j.unsettled()[0]
        self.assertEqual(P.settle_row(row, 'UP', 'UP'), (10, 10 - 9.06))
        self.assertEqual(P.settle_row(row, 'DOWN', 'DOWN'), (0, -9.06))


class LiveGuard(unittest.TestCase):
    def test_live_without_owner_confirmation_refuses(self):
        old = sys.argv; sys.argv = ['pair_bot.py', '--live']
        try:
            with self.assertRaises(SystemExit) as e: P.main()
            self.assertIn('owner', str(e.exception))
        finally: sys.argv = old
    def test_live_legs_are_capped_at_their_ask_and_reconciled(self):
        seen = {}
        class FakeBroker:
            async def prepare(self, tok, plan):
                seen.setdefault('plans', []).append((tok, plan)); return ('signed-' + tok, 'oid-' + tok)
            async def post(self, s): return {'id': 'oid-' + s.split('-', 1)[1]}
            async def reconcile(self, r):
                seen.setdefault('rec', []).append(r)
                json.loads(r['plan'])                               # _trade_fills needs it
                sh = 10.0 if r['token'] == 'u15' else 0.0
                fills = [('t1', dict(shares=sh, spent=sh * .9, fees=.06))] if sh else []
                return dict(terminal=True, fills=fills, reason='test')
        a = SimpleNamespace(db=tempfile.mktemp(suffix='.sqlite3'), first_sec=0, last_sec=290, margin=.01, min_gap=1., stake=20.,
                            min_shares=5, quote_age=.25, max_day=50., live=True, owner_confirmed=True)
        bot = P.Bot(a); bot.broker = FakeBroker()
        d = dict(T=900, ep5=1500, legs=('UP', 'DOWN'), a15=.9, a5=.05, cost=.96, shares=10, L15=1., L5=2., sec=100)
        bot.db.record(d, 'LIVE'); asyncio.run(bot.fire_live(d, 'u15', 'd5'))
        caps = {t: p['cap'] for t, p in seen['plans']}
        self.assertEqual(caps, {'u15': .9, 'd5': .05}, 'each leg is capped at its own ask - no chasing')
        self.assertTrue(all('rate' in p and 'exponent' in p for _, p in seen['plans']))
        r = bot.db.c.execute('SELECT st15,st5,sh15,sh5 FROM pairs WHERE T=900').fetchone()
        self.assertEqual(r, ('FILLED', 'NO_FILL', 10.0, 0.0))


if __name__ == '__main__':
    unittest.main()
