"""13.2.0 DRAFT: fresh-book send (ev_settings.fire_book_age_ms). Unset = today's behaviour. Set = an attempt is priced only
on a book of OUR token no older than the limit; it waits for one inside the budget and records DEADLINE if none comes.
It never vetoes a signal on its own - reassess() still decides on the fresh book. Run against poly_core's Executor."""
import asyncio, pathlib, tempfile, time, unittest
from poly_core import BookCache, Journal, Executor, PaperBroker
from test_polymarket import snapshot, decision, epoch, setUpModule, tearDownModule   # noqa: F401  (fsync-free sqlite)


def _age(books, token, s):
    b = books.books[token]; b['arrival'] -= s; b['event'] -= s


class FreshSend(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = str(pathlib.Path(self.temp.name) / 't.db')
        self.db = Journal(self.path, 'PAPER', 'abc'); self.books = BookCache(); self.books.apply(snapshot()); self.books.terms['up'] = (.01, 1, .07, 1)
    def tearDown(self): self.db.c.close(); self.temp.cleanup()
    def _orders(self): return self.db.sql('SELECT * FROM orders')

    def test_unset_is_todays_behaviour(self):
        _age(self.books, 'up', 0.3)
        ex = Executor(self.db, self.books, PaperBroker(self.books), budget_s=0.5)
        self.assertIsNone(ex.fire_age)
        asyncio.run(ex.fire(epoch(), decision(), 'up', 'c', 10, decision))
        self.assertEqual(len(self._orders()), 1, 'a 300 ms-old book is inside the 750 ms dial, so it sends as before')

    def test_stale_book_waits_and_never_sends_on_it(self):
        _age(self.books, 'up', 0.3)
        ex = Executor(self.db, self.books, PaperBroker(self.books), budget_s=0.3); ex.fire_age = 0.05
        asyncio.run(ex.fire(epoch(), decision(), 'up', 'c', 10, decision))
        self.assertEqual(len(self._orders()), 0, 'no order may be priced on a 300 ms-old book when the limit is 50 ms')

    def test_a_fresh_message_releases_the_wait(self):
        _age(self.books, 'up', 0.3); books = self.books
        async def run():
            ex = Executor(self.db, books, PaperBroker(books), budget_s=1.0); ex.fire_age = 0.05
            async def tick(): await asyncio.sleep(0.08); books.apply(snapshot())
            t = asyncio.ensure_future(tick()); t0 = time.monotonic()
            await ex.fire(epoch(), decision(), 'up', 'c', 10, decision); await t
            return time.monotonic() - t0
        waited = asyncio.run(run())
        self.assertEqual(len(self._orders()), 1, 'the next book message makes the attempt fresh and it sends')
        self.assertGreaterEqual(waited, 0.07)

    def test_the_limit_never_loosens_the_main_dial(self):
        ex = Executor(self.db, self.books, PaperBroker(self.books), age=0.75); ex.fire_age = 1.5
        _age(self.books, 'up', 1.0); ex.budget_s = 0.2
        asyncio.run(ex.fire(epoch(), decision(), 'up', 'c', 10, decision))
        self.assertEqual(len(self._orders()), 0, 'min(age, fire_age): a larger fire_age cannot admit a book the main dial rejects')


class EngineDial(unittest.TestCase):
    def test_meta_drives_the_executor_and_unset_is_off(self):
        from test_v122 import _paper_runner
        r, _ = _paper_runner()
        try:
            r._sync_executor_dials(); self.assertIsNone(r.executor.fire_age)
            r.db.set('ev_settings', dict(quote_age_ms=750, fire_book_age_ms=50)); r._sync_executor_dials()
            self.assertAlmostEqual(r.executor.fire_age, 0.05)
            r.db.set('ev_settings', dict(quote_age_ms=750, fire_book_age_ms=0)); r._sync_executor_dials()
            self.assertIsNone(r.executor.fire_age, '0 means off')
        finally: r.db.c.close()


if __name__ == '__main__':
    unittest.main()
