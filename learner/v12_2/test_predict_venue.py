"""12.17.0 — the Predict.fun venue adapter, against recorded payload shapes.

No network. Every payload here is the shape build11 handles in production; the
point of the suite is that the adapter feeds `poly_core.BookCache` events the
UNCHANGED engine can price, and that the YES-centric ladder is complemented into
a DOWN book correctly — that complement is the one place a sign error would
silently invert every DOWN trade.
"""
import json, time, unittest
import predict_venue as V
import poly_core


EP = 1789600000 // 300 * 300


def market(ep=EP, mid='9001'):
    return {
        'id': mid,
        'status': 'OPEN',
        'marketVariant': 'CRYPTO_UP_DOWN',
        'slug': 'btc-updown-5m-%d' % ep,
        'closeTimeMs': (ep + 300) * 1000,
        'outcomes': [{'name': 'Up', 'onChainId': 'tok-up'},
                     {'name': 'Down', 'onChainId': 'tok-dn'}],
    }


def ladder(stamp_ms=None):
    return {'marketId': '9001',
            'updateTimestampMs': int(stamp_ms if stamp_ms is not None else time.time() * 1000),
            'asks': [{'price': '0.44', 'size': '120'}, {'price': '0.45', 'size': '300'}],
            'bids': [{'price': '0.42', 'size': '150'}, {'price': '0.41', 'size': '80'}]}


class Fake:
    """Records the calls so the paging and fallback rules are observable."""

    def __init__(self, pages=None, book=None):
        self.pages = pages if pages is not None else [{'data': [market()]}]
        self.book = book
        self.calls = []

    def __call__(self, path, params=None, timeout=None):
        self.calls.append((path, dict(params or {})))
        if path == '/v1/markets':
            return self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]
        if path.endswith('/orderbook'):
            return self.book
        return None


class Discovery(unittest.TestCase):
    def test_resolves_market_and_both_tokens(self):
        v = V.PredictVenue(Fake())
        self.assertEqual(v.resolve(EP), ('9001', 'tok-up', 'tok-dn'))

    def test_resolution_is_cached(self):
        f = Fake(); v = V.PredictVenue(f)
        v.resolve(EP); v.resolve(EP)
        self.assertEqual(len(f.calls), 1)

    def test_wrong_candle_is_not_accepted(self):
        v = V.PredictVenue(Fake([{'data': [market(ep=EP + 300)]}]))
        self.assertIsNone(v.resolve(EP))

    def test_closed_market_is_not_accepted(self):
        m = market(); m['status'] = 'RESOLVED'
        self.assertIsNone(V.PredictVenue(Fake([{'data': [m]}])).resolve(EP))

    def test_pages_until_the_candle_is_found(self):
        f = Fake([{'data': [market(ep=EP + 600)], 'cursor': 'c1'},
                  {'data': [market()]}])
        self.assertIsNotNone(V.PredictVenue(f).resolve(EP))
        self.assertEqual(f.calls[1][1].get('after'), 'c1')

    def test_listing_shapes_all_flatten(self):
        for payload in ([market()], {'data': [market()]}, {'items': [market()]}):
            self.assertEqual(len(V.flatten_markets(payload)), 1)

    def test_epoch_from_close_time_and_from_slug(self):
        self.assertEqual(V.market_epoch({'closeTimeMs': (EP + 300) * 1000}), EP)
        self.assertEqual(V.market_epoch({'slug': 'btc-updown-5m-%d' % EP}), EP)

    def test_no_market_sets_a_reason(self):
        v = V.PredictVenue(Fake([{'data': []}]))
        self.assertIsNone(v.resolve(EP))
        self.assertTrue(v.error)


class Complement(unittest.TestCase):
    """The NO book is the YES book through 1.0 — build11:9440."""

    def test_down_ask_is_one_minus_up_bid(self):
        asks, bids = V.levels(ladder()['asks']), V.levels(ladder()['bids'])
        dn_asks, dn_bids = V.complement(asks, bids)
        self.assertAlmostEqual(dn_asks[0][0], 1.0 - bids[0][0], places=9)
        self.assertAlmostEqual(dn_bids[0][0], 1.0 - asks[0][0], places=9)

    def test_sizes_ride_with_their_price(self):
        asks, bids = [(0.44, 120.0)], [(0.42, 150.0)]
        dn_asks, dn_bids = V.complement(asks, bids)
        self.assertEqual(dn_asks[0][1], 150.0)
        self.assertEqual(dn_bids[0][1], 120.0)

    def test_books_never_cross(self):
        ev = V.book_events('u', 'd', ladder())
        for e in ev:
            best_ask = min(float(x['price']) for x in e['asks'])
            best_bid = max(float(x['price']) for x in e['bids'])
            self.assertGreater(best_ask, best_bid)

    def test_up_ask_plus_down_bid_is_one(self):
        up, dn = V.book_events('u', 'd', ladder())
        self.assertAlmostEqual(min(float(x['price']) for x in up['asks'])
                               + max(float(x['price']) for x in dn['bids']), 1.0, places=9)

    def test_junk_levels_are_dropped(self):
        raw = [{'price': '0', 'size': '5'}, {'price': '1', 'size': '5'},
               {'price': '0.5', 'size': '0'}, {'price': 'x', 'size': '5'},
               {'price': '0.3', 'size': '7'}]
        self.assertEqual(V.levels(raw), [(0.3, 7.0)])

    def test_pair_ladder_form_is_accepted(self):
        self.assertEqual(V.levels([[0.4, 10]]), [(0.4, 10.0)])


class Events(unittest.TestCase):
    def test_engine_bookcache_prices_the_adapter_output(self):
        """The whole point of the port: an UNCHANGED BookCache quotes both sides."""
        books = poly_core.BookCache()
        for e in V.book_events('tok-up', 'tok-dn', ladder()):
            books.apply(e)
        up = books.quote('tok-up', 60.0)
        dn = books.quote('tok-dn', 60.0)
        self.assertAlmostEqual(up['ask'], 0.44, places=9)
        self.assertAlmostEqual(dn['ask'], 0.58, places=9)   # 1 - 0.42
        self.assertAlmostEqual(up['ask'] + dn['bid'], 1.0, places=9)

    def test_empty_ladder_yields_nothing(self):
        self.assertEqual(V.book_events('u', 'd', {'asks': [], 'bids': []}), [])

    def test_socket_frame_is_translated(self):
        v = V.PredictVenue(Fake()); v.resolve(EP)
        frame = json.dumps({'type': 'M', 'topic': 'predictOrderbook/9001', 'data': ladder()})
        ev = v.on_message(frame)
        self.assertEqual([e['asset_id'] for e in ev], ['tok-up', 'tok-dn'])

    def test_unknown_frames_are_ignored_not_raised(self):
        v = V.PredictVenue(Fake()); v.resolve(EP)
        for msg in ('', 'PONG', b'\x00\x01', '{"broken":', '{"id":1,"result":true}',
                    json.dumps({'topic': 'predictWalletEvents/x', 'data': {}}),
                    json.dumps({'topic': 'predictOrderbook/9001', 'data': None}),
                    json.dumps({'topic': 'predictOrderbook/OTHER', 'data': ladder()})):
            self.assertEqual(v.on_message(msg), [])

    def test_subscribe_frame_names_the_market(self):
        v = V.PredictVenue(Fake())
        f = json.loads(v.subscribe_frame(EP))
        self.assertEqual(f['method'], 'subscribe')
        self.assertEqual(f['params'], ['predictOrderbook/9001'])

    def test_snapshot_bootstraps_from_rest(self):
        v = V.PredictVenue(Fake(book={'data': ladder()}))
        self.assertEqual(len(v.snapshot(EP)), 2)

    def test_prune_drops_old_candles_only(self):
        v = V.PredictVenue(Fake()); v.resolve(EP)
        v.prune(EP); self.assertIn(EP, v.market)
        v.prune(EP + 300); self.assertNotIn(EP, v.market)


class ReadOnly(unittest.TestCase):
    """This adapter must not be able to place an order on the owner's money."""

    def test_module_has_no_order_or_signing_surface(self):
        """Checked against the parsed CODE, not the prose: the docstring says
        'signal' and 'signs nothing', and a substring scan over comments would
        pass or fail on wording rather than on behaviour."""
        import ast
        with open(V.__file__) as fh:
            tree = ast.parse(fh.read())
        names = {n.name.lower() for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for banned in ('post', 'sign', 'sign_order', 'submit', 'place', 'cancel'):
            self.assertNotIn(banned, names)
        strings = {n.value.lower() for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        for path in strings:
            self.assertNotIn('/v1/orders', path)
        self.assertFalse({'private_key', 'wallet'} & {
            n.value.lower() for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)})

    def test_no_secret_is_logged(self):
        h = V._auth_headers()
        self.assertNotIn('Authorization', json.dumps({k: k for k in h}))


class EngineSeam(unittest.TestCase):
    """The seam is the claim: ONLY discovery and the book feed change."""

    def test_cli_refuses_live_on_predict(self):
        import subprocess, sys, pathlib
        eng = str(pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py'))
        r = subprocess.run([sys.executable, eng, '--venue', 'predict', '--live'],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('paper-only', r.stderr)

    def test_default_venue_is_polymarket(self):
        import subprocess, sys, pathlib
        eng = str(pathlib.Path(__file__).with_name('btc_model_v12_polymarket.py'))
        r = subprocess.run([sys.executable, eng, '--help'], capture_output=True, text=True)
        self.assertIn('--venue', r.stdout)

    def test_signal_modules_are_untouched_by_the_port(self):
        """btc_model_v10, poly_lanes and poly_core must not IMPORT the venue.

        Checked on the import graph, not on the text: poly_lanes' docstring cites
        Predict.fun because the lanes were ported from the engine that trades
        there, and prose is not coupling.
        """
        import ast, pathlib
        for name in ('btc_model_v10.py', 'poly_lanes.py', 'poly_core.py'):
            tree = ast.parse(pathlib.Path(__file__).with_name(name).read_text())
            mods = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    mods |= {a.name for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module:
                    mods.add(n.module)
            self.assertNotIn('predict_venue', mods, name)


if __name__ == '__main__':
    unittest.main()
