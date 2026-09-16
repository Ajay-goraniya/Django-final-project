#!/usr/bin/env python3
"""
btc_model_v10_runner.py -- run learner v10 LIVE (paper mode) the way your v9
builds run: a port, a database, --reset.

    python3 btc_model_v10_runner.py --port 8788 --db v10.sqlite3 --reset

What it does
  * connects to the same real feeds the model was trained on
        Binance spot   btcusdt@aggTrade
        Binance perp   btcusdt@trade (aggregated like aggTrade), btcusdt@depth20@100ms
        Polymarket     the current BTC 5m market's UP/DOWN books (CLOB, 1s)
  * runs decide() four times a second on the current candle, one trade per
    candle, in the mode you pick (--mode accuracy|pnl; accuracy is default)
  * PAPER mode: it records the trade at the venue ask, never sends an order.
    Grades every trade against the venue's resolved outcome ~90s after the
    candle closes, and keeps running accuracy / PnL in SQLite.
  * serves live status as JSON on http://127.0.0.1:<port>/  (curl it)
  * --reset deletes the database and starts clean

Needs: numpy, websockets  (pip install numpy websockets), plus
btc_model_v10.py and model_v10.json in the same folder.
"""
import argparse, asyncio, json, math, os, pathlib, sqlite3, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
import numpy as np
from btc_model_v10 import FEATURES, Model, FeatureState

US = 1_000_000
UA = {"User-Agent": "learner-v10/1.0"}
GAMMA = "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}"
CLOB = "https://clob.polymarket.com/book?token_id={}"
POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
FEE = 0.07
cost = lambda q: q / (1 - FEE * (1 - q))


def http_json(url, timeout=8):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


class Store:
    def __init__(self, path, reset):
        p = pathlib.Path(path)
        if reset and p.exists():
            p.unlink()
        self.con = sqlite3.connect(str(p), check_same_thread=False)
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS trades(candle_epoch INTEGER PRIMARY KEY, ts_ms INTEGER, mode TEXT,
            side TEXT, p REAL, ask REAL, ev REAL, sec INTEGER, rv60 REAL, stake REAL,
            actual TEXT, win INTEGER, pnl REAL, graded_ms INTEGER, feat TEXT, book_age_ms INTEGER);
        CREATE TABLE IF NOT EXISTS decisions(ts_ms INTEGER, candle_epoch INTEGER, sec INTEGER, side TEXT,
            p REAL, ask REAL, ev REAL, fire INTEGER, feat TEXT);
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);""")
        if "book_age_ms" not in {r[1] for r in self.con.execute("PRAGMA table_info(trades)")}:
            self.con.execute("ALTER TABLE trades ADD COLUMN book_age_ms INTEGER")
        self.con.execute("INSERT OR REPLACE INTO meta VALUES('build','learner-v10-paper')")
        self.con.commit()
        self.lock = threading.Lock()

    def trade(self, **r):
        with self.lock:
            self.con.execute("INSERT OR IGNORE INTO trades(candle_epoch,ts_ms,mode,side,p,ask,ev,sec,rv60,stake,feat,book_age_ms) "
                             "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                             (r["epoch"], r["ts_ms"], r["mode"], r["side"], r["p"], r["ask"], r["ev"], r["sec"], r["rv60"], r["stake"], r.get("feat"), r.get("book_age_ms")))
            self.con.commit()

    def decision(self, ts_ms, epoch, d):
        with self.lock:
            self.con.execute("INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)",
                             (ts_ms, epoch, d.get("sec"), d.get("side"), d.get("p"), d.get("ask"), d.get("ev"), int(bool(d.get("fire"))), d.get("feat")))
            self.con.commit()

    def ungraded(self, before_epoch):
        with self.lock:
            return self.con.execute("SELECT candle_epoch, side, ask, stake FROM trades WHERE actual IS NULL AND candle_epoch < ?",
                                    (before_epoch,)).fetchall()

    def grade(self, epoch, actual, win, pnl):
        with self.lock:
            self.con.execute("UPDATE trades SET actual=?, win=?, pnl=?, graded_ms=? WHERE candle_epoch=?",
                             (actual, int(win), pnl, int(time.time() * 1000), epoch))
            self.con.commit()

    def stats(self):
        with self.lock:
            n, w, pnl, stk = self.con.execute("SELECT COUNT(*), COALESCE(SUM(win),0), COALESCE(SUM(pnl),0), COALESCE(SUM(stake),0) "
                                              "FROM trades WHERE actual IS NOT NULL").fetchone()
            pend = self.con.execute("SELECT COUNT(*) FROM trades WHERE actual IS NULL").fetchone()[0]
            last = self.con.execute("SELECT candle_epoch, side, ask, p, actual, win, pnl FROM trades ORDER BY candle_epoch DESC LIMIT 5").fetchall()
        return dict(graded=n, wins=w, accuracy=round(100 * w / n, 1) if n else None, pnl=round(pnl, 2),
                    staked=round(stk, 2), roi_pct=round(100 * pnl / stk, 2) if stk else None, pending=pend,
                    last=[dict(epoch=e, side=s, ask=a, p=p, actual=ac, win=wn, pnl=pl) for e, s, a, p, ac, wn, pl in last])


class Runner:
    def __init__(self, a):
        self.a = a
        self.m = Model(a.model)
        self.st = FeatureState()
        self.db = Store(a.db, a.reset)
        self.age = {"spot": 0.0, "perp": 0.0, "depth": 0.0, "venue": 0.0}
        self.msgs = {}
        self._agg = None
        self.market = {}          # epoch -> (token_up, token_dn)
        self.ladders = {}         # token -> {"asks": {price: size}, "bids": {price: size}}
        self.venue_ws_up = 0.0
        self.fired = set()
        self.last_decision = {}
        self.started = time.time()

    # ---------------- feeds
    async def ws(self, url, handler, name):
        import websockets
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, max_size=2**22) as w:
                    async for msg in w:
                        handler(json.loads(msg)); self.age[name] = time.time()
                        self.msgs[name] = self.msgs.get(name, 0) + 1
            except Exception as e:
                print(f"[{name}] reconnect: {type(e).__name__}", flush=True)
                await asyncio.sleep(2)

    def on_spot(self, j):
        self.st.on_spot_trade(int(j["T"]) * 1000, float(j["p"]), float(j["q"]), bool(j["m"]))

    def on_perp(self, j):
        """Raw @trade stream, aggregated exactly like Binance aggTrade (same
        timestamp, side and price -> one print) so perp_n15 matches training."""
        p, q, m, T = float(j["p"]), float(j["q"]), bool(j["m"]), int(j["T"])
        k = (T, m, p)
        if self._agg and self._agg[0] == k:
            self._agg[1] += q
            return
        if self._agg:
            (T0, m0, p0), q0 = self._agg
            self.st.on_perp_trade(T0 * 1000, p0, q0, p0 * q0 * (-1.0 if m0 else 1.0), p0 * q0)
        self._agg = [k, q]

    def on_depth(self, j):
        b = [(float(x[0]), float(x[1])) for x in j.get("b", [])][:20]
        a = [(float(x[0]), float(x[1])) for x in j.get("a", [])][:20]
        if not b or not a:
            return
        self.st.on_depth(int(j.get("E", time.time() * 1000)) * 1000, b[0][0], b[0][1], a[0][0], a[0][1],
                         sum(q for _, q in b[:5]), sum(q for _, q in a[:5]),
                         sum(q for _, q in b), sum(q for _, q in a))

    async def resolve_market(self, ep):
        """Gamma lookup: (UP token, DOWN token) for the 5m market at epoch `ep`, cached."""
        if ep in self.market:
            return self.market[ep]
        j = await asyncio.to_thread(http_json, GAMMA.format(ep))
        toks = []
        if j:
            mk = (j[0].get("markets") or [{}])[0]
            try:
                toks = json.loads(mk.get("clobTokenIds") or "[]")
                outs = json.loads(mk.get("outcomes") or "[]")
                if outs and str(outs[0]).strip().upper() != "UP":
                    toks = toks[::-1]
            except Exception:
                toks = []
        self.market[ep] = tuple(toks) if len(toks) == 2 else None
        for old in [k for k in self.market if k < ep - 1800]:
            self.market.pop(old, None)
        return self.market[ep]

    def _publish_venue(self):
        """Best ask/bid of the current candle's two tokens -> feature state."""
        ep = int(time.time() // 300) * 300
        toks = self.market.get(ep)
        if not toks:
            return
        def best(tok):
            lad = self.ladders.get(tok)
            if not lad:
                return (None, None)
            asks = [p for p, q in lad["asks"].items() if q > 0 and 0 < p < 1]
            bids = [p for p, q in lad["bids"].items() if q > 0 and 0 < p < 1]
            return (min(asks) if asks else None, max(bids) if bids else None)
        au, bu = best(toks[0]); ad, bd = best(toks[1])
        self.st.on_venue_quote(au, bu, ad, bd)
        if au is not None or ad is not None:
            self.age["venue"] = time.time()

    def _apply_ws(self, ev):
        k = ev.get("event_type")
        if k == "book":
            tok = str(ev.get("asset_id"))
            self.ladders[tok] = {
                "asks": {float(x["price"]): float(x["size"]) for x in ev.get("asks", [])},
                "bids": {float(x["price"]): float(x["size"]) for x in ev.get("bids", [])},
            }
        elif k == "price_change":
            for ch in ev.get("price_changes", []):
                tok = str(ch.get("asset_id")); lad = self.ladders.get(tok)
                if lad is None:
                    continue
                side = "asks" if str(ch.get("side", "")).upper() == "SELL" else "bids"
                try:
                    price, size = float(ch["price"]), float(ch["size"])
                except (KeyError, TypeError, ValueError):
                    continue
                if size <= 0:
                    lad[side].pop(price, None)
                else:
                    lad[side][price] = size
        else:
            return
        self.msgs["venue_ws"] = self.msgs.get("venue_ws", 0) + 1
        self._publish_venue()

    async def venue(self):
        """Polymarket CLOB market websocket (free, no key): full book snapshots plus
        every price change for the current and the next 5m market. Reconnects once
        per candle (at ~30 s in) so the next market's tokens are already subscribed
        before the rollover. Needs a text PING every <10 s or the server drops it."""
        import websockets
        while True:
            now = time.time(); ep = int(now // 300) * 300
            cur = await self.resolve_market(ep); nxt = await self.resolve_market(ep + 300)
            toks = [t for pair in (cur, nxt) if pair for t in pair]
            if not toks:
                await asyncio.sleep(5); continue
            try:
                async with websockets.connect(POLY_WS, ping_interval=None, max_size=2**23) as w:
                    await w.send(json.dumps({"assets_ids": toks, "type": "market"}))
                    self.venue_ws_up = time.time()
                    async def pinger():
                        while True:
                            await asyncio.sleep(5); await w.send("PING")
                    pt = asyncio.create_task(pinger())
                    try:
                        while True:
                            # resubscribe once the next candle needs a market we do not hold yet
                            ep_now = int(time.time() // 300) * 300
                            if ep_now > ep and time.time() - ep_now >= 30:
                                break
                            try:
                                m = await asyncio.wait_for(w.recv(), timeout=15)
                            except asyncio.TimeoutError:
                                print("[venue] websocket silent 15 s; reconnecting", flush=True); break
                            if m == "PONG":
                                continue
                            try:
                                d = json.loads(m)
                            except Exception:
                                continue
                            for ev in (d if isinstance(d, list) else [d]):
                                if isinstance(ev, dict):
                                    self._apply_ws(ev)
                    finally:
                        pt.cancel()
            except Exception as e:
                print(f"[venue] reconnect: {type(e).__name__}", flush=True)
                await asyncio.sleep(2)

    # ---------------- decisions + grading
    async def decide_loop(self):
        while True:
            now = time.time(); ep = int(now // 300) * 300
            fresh = all(now - self.age[k] < 10 for k in ("spot", "perp", "venue"))
            # warm-up: the features need >= 10 min of spot history (prev2) and >= 60 s of perp
            warm = (len(self.st.s_ts) > 50 and (self.st.s_ts[-1] - self.st.s_ts[0]) >= 600 * US
                    and len(self.st.p_ts) > 20 and (self.st.p_ts[-1] - self.st.p_ts[0]) >= 60 * US)
            if fresh and not warm and int(now) % 30 == 0 and getattr(self, "_warm_log", 0) != int(now):
                self._warm_log = int(now)
                print(f"[{time.strftime('%H:%M:%S')}] warming up: spot {(self.st.s_ts[-1]-self.st.s_ts[0])/US if self.st.s_ts else 0:.0f}s of history", flush=True)
            fresh = fresh and warm
            if fresh and ep not in self.fired and 5 <= now - ep <= 285:
                d = self.m.decide(self.st, ep * US, int(now * US), mode=self.a.mode,
                                  ev_threshold=(self.a.ev if self.a.mode == "pnl" and self.a.ev is not None else None))
                # diagnostics: the full feature vector behind every decision, plus the
                # standardized contribution of each feature to the logit
                try:
                    f = self.st.features(ep * US, int(now * US)) or {}
                    x = np.nan_to_num(np.array([f.get(k, 0.0) for k in FEATURES], dtype=float))
                    zc = (x - self.m.mean) / self.m.scale * self.m.coef
                    d["feat"] = json.dumps({k: (None if not np.isfinite(v) else round(float(v), 6)) for k, v in f.items()}
                                           | {"_contrib": {k: round(float(c), 4) for k, c in zip(FEATURES, zc)},
                                              "_spot_n": len(self.st.s_ts), "_perp_n": len(self.st.p_ts),
                                              "_spot_span_s": (self.st.s_ts[-1] - self.st.s_ts[0]) / US if self.st.s_ts else 0})
                    top = sorted(zip(FEATURES, zc, x), key=lambda t: -abs(t[1]))[:4]
                    d["top"] = " ".join(f"{k}={v:.3g}({c:+.2f})" for k, c, v in top)
                except Exception as e:
                    d["feat"] = None; d["top"] = f"diag error {e!r}"
                self.last_decision = dict(d, epoch=ep, ts=int(now))
                if d.get("fire"):
                    self.fired.add(ep)
                    self.db.trade(epoch=ep, ts_ms=int(now * 1000), mode=self.a.mode, side=d["side"], p=d["p"],
                                  ask=d["ask"], ev=d["ev"], sec=d["sec"], rv60=d["rv60"], stake=self.a.stake, feat=d["feat"],
                                  book_age_ms=int(max(0.0, now - self.age.get("venue", 0.0)) * 1000))
                    print(f"[{time.strftime('%H:%M:%S')}] FIRE {d['side']} p={d['p']} ask={d['ask']} ev={d['ev']} sec={d['sec']} | {d['top']}", flush=True)
                elif now - getattr(self, "_last_dec_log", 0) >= 15:
                    self._last_dec_log = now
                    self.db.decision(int(now * 1000), ep, d)
            await asyncio.sleep(0.25)

    async def grade_loop(self):
        while True:
            now = time.time()
            for ep, side, ask, stake in self.db.ungraded(int(now) - 390):
                j = await asyncio.to_thread(http_json, GAMMA.format(ep))
                if not j:
                    continue
                mk = (j[0].get("markets") or [{}])[0]
                try:
                    names = json.loads(mk.get("outcomes")); prices = json.loads(mk.get("outcomePrices"))
                    w = [n for n, p in zip(names, prices) if str(p) == "1"]
                except Exception:
                    w = []
                if len(w) != 1:
                    continue
                actual = w[0].strip().upper(); win = (actual == side)
                pnl = stake * ((1 / cost(ask) - 1) if win else -1.0)
                self.db.grade(ep, actual, win, pnl)
                s = self.db.stats()
                print(f"[{time.strftime('%H:%M:%S')}] SETTLED {ep} {side} -> {actual} {'WIN' if win else 'LOSS'} {pnl:+.2f} | "
                      f"acc {s['accuracy']}% ({s['graded']}) pnl {s['pnl']:+.2f}", flush=True)
            await asyncio.sleep(20)

    # ---------------- status server
    def serve(self):
        r = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                now = time.time()
                body = json.dumps(dict(build="learner-v10-paper", mode=r.a.mode, model=str(r.a.model), db=str(r.a.db),
                                       uptime_s=int(now - r.started),
                                       feed_age_s={k: (round(now - v, 1) if v else None) for k, v in r.age.items()},
                                       feed_msgs=r.msgs,
                                       last_decision=r.last_decision, **r.db.stats()), indent=1).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        HTTPServer(("0.0.0.0", self.a.port), H).serve_forever()

    async def main(self):
        threading.Thread(target=self.serve, daemon=True).start()
        print(f"learner v10 PAPER runner  mode={self.a.mode}  db={self.a.db}  status: http://127.0.0.1:{self.a.port}/", flush=True)
        await asyncio.gather(
            self.ws("wss://data-stream.binance.vision/ws/btcusdt@aggTrade", self.on_spot, "spot"),
            self.ws("wss://fstream.binance.com/ws/btcusdt@trade", self.on_perp, "perp"),
            self.ws("wss://fstream.binance.com/ws/btcusdt@depth20@100ms", self.on_depth, "depth"),
            self.venue(), self.decide_loop(), self.grade_loop())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--db", default="v10.sqlite3")
    ap.add_argument("--reset", action="store_true", help="delete the database and start clean")
    ap.add_argument("--mode", default="accuracy", choices=["accuracy", "pnl"])
    ap.add_argument("--ev", type=float, default=None, help="EV threshold for pnl mode (default from model_v10.json)")
    ap.add_argument("--stake", type=float, default=10.0, help="paper stake per trade in $")
    ap.add_argument("--model", default=str(pathlib.Path(__file__).resolve().parent / "model_v10.json"))
    a = ap.parse_args()
    try:
        asyncio.run(Runner(a).main())
    except KeyboardInterrupt:
        print("stopped")
