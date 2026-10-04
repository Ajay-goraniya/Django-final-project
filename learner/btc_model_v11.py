"""
Learner v11 decision layer: POLYMARKET SIGNAL, PREDICT.FUN EXECUTION.

Findings behind it (19 h live, 2026-09-08/09, four parallel runs):
  * Polymarket's book forecasts better than Predict.fun's (leader right 2:1 on every
    disagreement) and Predict.fun sells the same side cheaper on the leader side.
  * Predict.fun's fee is 2% of notional (cost = ask * 1.02), not 7% of payout.
  * Cheap prices with 2 shares behind them are not trades: require size at the ask.
  * The two live bugs were both book-mismatch: never price from another candle's market.

Two-book rule: Predict.fun is the platform (market, candle id, book state, size, fee,
fills, settlement). Polymarket is an INPUT only: it feeds the model's venue features
when fresh and on the same candle; otherwise the model falls back to Predict.fun's own
quote. Every price in EV, size and order is Predict.fun's ask.

Retro-test on the recorded 19 h (Polymarket decisions x Predict.fun book x outcomes):
  v10 baseline (Polymarket exec, 7% fee)   110 trades  56%  +$186
  v11 pnl, no calibration                   118 trades  63%  +$241
  v11 pnl + live calibration (default)       97 trades  69%  +$332  (calibration in-sample)
  v11 accuracy (margin 0.05, conf 0.75)      97 trades  85%  +$140
"""
from __future__ import annotations
import json, math, threading, time, socket, urllib.request, collections
from typing import Any, Dict, Optional
import numpy as np

US = 1_000_000
GAMMA = "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}"
POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url: str, timeout: float = 6.0):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


# ---------------------------------------------------------------- Polymarket book (signal only)
class PolyBook(threading.Thread):
    """Free public CLOB market websocket. Keeps best ask/bid per token for the current
    and next 5-minute market. quote(epoch) answers only for that exact epoch."""

    def __init__(self, stop_event: Optional[threading.Event] = None):
        super().__init__(name="poly-signal", daemon=True)
        self.stop_event = stop_event or threading.Event()
        self.lock = threading.Lock()
        self.tokens: Dict[int, Optional[tuple]] = {}      # epoch -> (up_token, dn_token)
        self.ladders: Dict[str, Dict[str, Dict[float, float]]] = {}
        self.last_msg_ms = 0
        self.status = "starting"
        self.msgs = 0
        self.reconnects = 0

    # -- market discovery, keyed to the 5-min epoch (same clock as Predict.fun candle id / 1000)
    def resolve(self, epoch: int):
        with self.lock:
            if epoch in self.tokens:
                return self.tokens[epoch]
        toks = None
        j = _get(GAMMA.format(epoch))
        if j:
            try:
                mk = (j[0].get("markets") or [{}])[0]
                ids = json.loads(mk.get("clobTokenIds") or "[]")
                outs = json.loads(mk.get("outcomes") or "[]")
                if outs and str(outs[0]).strip().upper() != "UP":
                    ids = ids[::-1]
                toks = tuple(ids) if len(ids) == 2 else None
            except Exception:
                toks = None
        with self.lock:
            self.tokens[epoch] = toks
            for old in [k for k in self.tokens if k < epoch - 1800]:
                self.tokens.pop(old, None)
        return toks

    def _apply(self, ev: Dict[str, Any]) -> None:
        k = ev.get("event_type")
        if k == "book":
            tok = str(ev.get("asset_id"))
            lad = {"asks": {}, "bids": {}}
            for x in ev.get("asks", []):
                try: lad["asks"][float(x["price"])] = float(x["size"])
                except Exception: pass
            for x in ev.get("bids", []):
                try: lad["bids"][float(x["price"])] = float(x["size"])
                except Exception: pass
            with self.lock:
                self.ladders[tok] = lad
        elif k == "price_change":
            with self.lock:
                for ch in ev.get("price_changes", []):
                    lad = self.ladders.get(str(ch.get("asset_id")))
                    if lad is None:
                        continue
                    side = "asks" if str(ch.get("side", "")).upper() == "SELL" else "bids"
                    try:
                        price, size = float(ch["price"]), float(ch["size"])
                    except Exception:
                        continue
                    if size <= 0:
                        lad[side].pop(price, None)
                    else:
                        lad[side][price] = size
        else:
            return
        self.msgs += 1
        self.last_msg_ms = int(time.time() * 1000)

    def quote(self, epoch: int) -> Optional[Dict[str, Any]]:
        """Best ask/bid + size for UP and DOWN of exactly this epoch's market, or None."""
        with self.lock:
            toks = self.tokens.get(epoch)
            if not toks:
                return None
            out = {}
            for name, tok in (("up", toks[0]), ("dn", toks[1])):
                lad = self.ladders.get(tok)
                if not lad:
                    return None
                asks = [(p, q) for p, q in lad["asks"].items() if 0 < p < 1 and q > 0]
                bids = [(p, q) for p, q in lad["bids"].items() if 0 < p < 1 and q > 0]
                ba = min(asks, default=(None, 0.0)); bb = max(bids, default=(None, 0.0))
                out[f"ask_{name}"], out[f"size_{name}"] = ba[0], ba[1]
                out[f"bid_{name}"] = bb[0]
            out["age_s"] = (time.time() * 1000 - self.last_msg_ms) / 1000.0 if self.last_msg_ms else None
            return out

    def run(self) -> None:
        try:
            import websocket  # websocket-client, already required by the engine
        except ImportError:
            self.status = "dependency missing (websocket-client)"; return
        backoff = 1.0
        while not self.stop_event.is_set():
            ep = int(time.time() // 300) * 300
            cur = self.resolve(ep); nxt = self.resolve(ep + 300)
            toks = [t for pair in (cur, nxt) if pair for t in pair]
            if not toks:
                self.status = "no market"; self.stop_event.wait(5); continue
            closed = threading.Event()
            def on_open(ws):
                ws.send(json.dumps({"assets_ids": toks, "type": "market"}))
                self.status = "live websocket"; backoff_reset[0] = True
            def on_message(ws, raw):
                if raw == "PONG":
                    return
                try: d = json.loads(raw)
                except Exception: return
                for ev in (d if isinstance(d, list) else [d]):
                    if isinstance(ev, dict):
                        self._apply(ev)
            def on_error(ws, err): self.status = f"error: {err}"
            def on_close(ws, *a):
                closed.set()
                if not self.stop_event.is_set(): self.status = "reconnecting"
            backoff_reset = [False]
            app = websocket.WebSocketApp(POLY_WS, on_open=on_open, on_message=on_message,
                                         on_error=on_error, on_close=on_close)
            def keeper():
                # PING every 5 s (server drops silent clients after ~10 s); rotate once the next
                # candle needs a market we do not hold yet; drop a silent socket after 15 s.
                while not self.stop_event.wait(5) and not closed.is_set():
                    try: app.send("PING")
                    except Exception: pass
                    now = time.time(); ep_now = int(now // 300) * 300
                    silent = self.last_msg_ms and now * 1000 - self.last_msg_ms > 15000
                    if (ep_now > ep and now - ep_now >= 30) or silent:
                        try: app.close()
                        except Exception: pass
                        return
            threading.Thread(target=keeper, name="poly-signal-keeper", daemon=True).start()
            try:
                app.run_forever(ping_interval=0, skip_utf8_validation=True,
                                sockopt=((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),),
                                http_no_proxy=["*"], suppress_origin=True)
            except Exception as exc:
                self.status = f"error: {exc}"
            closed.set(); self.reconnects += 1
            if backoff_reset[0]:
                backoff = 1.0
            if self.stop_event.wait(backoff): break
            backoff = min(8.0, backoff * 1.7)

    def snapshot(self) -> Dict[str, Any]:
        return {"status": self.status, "msgs": self.msgs, "reconnects": self.reconnects,
                "age_ms": (int(time.time() * 1000) - self.last_msg_ms) if self.last_msg_ms else None}


# ---------------------------------------------------------------- live calibration
class Calibration:
    """Per-bin shrinkage of the model's claimed p toward what it realized live.
    adj = (wins + n0*claimed) / (n + n0); applied as an additive shift inside the bin."""

    def __init__(self, path: Optional[str] = None):
        self.edges = [0.5, 0.56, 0.62, 0.70, 1.0]
        self.shift = [0.0] * 4
        self.meta: Dict[str, Any] = {}
        if path:
            try:
                j = json.load(open(path))
                self.edges = j["edges"]; self.shift = j["shift"]; self.meta = j.get("meta", {})
            except Exception:
                pass

    def apply(self, p_side: float) -> float:
        for i in range(len(self.edges) - 1):
            if self.edges[i] <= p_side < self.edges[i + 1] or (i == len(self.edges) - 2 and p_side >= self.edges[i + 1]):
                return float(min(0.99, max(0.30, p_side + self.shift[i])))
        return p_side


# ---------------------------------------------------------------- leader-conversion window
class ConversionWindow:
    """Per CANDLE (fired or not): the signal book's leader at ~60 s and its Predict.fun ask;
    graded at settlement. Window = last N settled candles. ok() is False while the leader
    converts under its Predict.fun break-even (ask*1.02). Reacts within ~N candles whatever the
    lane's own fire rate. Retro (19 h, 2026-09-08/09): accuracy lane 85% -> 89-90% with N=12
    (PnL +150 -> +137); pnl lane (contrarian fires) LOSES with it (removed 24 wins / 10 losses),
    so it gates the accuracy lane only by default."""

    def __init__(self, n: int = 12, at_sec: int = 60):
        self.n = int(n); self.at_sec = int(at_sec)
        self.pending: Dict[int, Dict[str, Any]] = {}     # epoch -> {side, be}
        self.settled: "collections.deque[tuple]" = collections.deque(maxlen=self.n)
        self.lock = threading.Lock()

    def observe(self, epoch: int, sec: float, poly: Optional[Dict[str, Any]], pred: Dict[str, Any]) -> None:
        if sec < self.at_sec or not poly:
            return
        with self.lock:
            if epoch in self.pending:
                return
            au, ad = poly.get("ask_up"), poly.get("ask_dn")
            if not (au and ad):
                return
            side = "UP" if au >= ad else "DOWN"
            pask = pred.get("ask_up" if side == "UP" else "ask_dn")
            if not (isinstance(pask, (int, float)) and 0 < pask < 1):
                return
            self.pending[epoch] = {"side": side, "be": float(pask) * (1.0 + float(pred.get("fee_rate") or 0.02))}

    def settle(self, epoch: int, actual: str) -> None:
        with self.lock:
            rec = self.pending.pop(epoch, None)
            if rec and actual in ("UP", "DOWN"):
                self.settled.append((1.0 if rec["side"] == actual else 0.0, rec["be"]))
            for old in [k for k in self.pending if k < epoch - 3600]:
                self.pending.pop(old, None)

    def stats(self) -> Dict[str, Any]:
        with self.lock:
            n = len(self.settled)
            if n == 0:
                return {"n": 0, "conversion": None, "break_even": None, "ok": True}
            conv = sum(w for w, _ in self.settled) / n; be = sum(b for _, b in self.settled) / n
            return {"n": n, "conversion": round(conv, 3), "break_even": round(be, 3), "ok": bool(n < self.n or conv >= be)}

    def ok(self) -> bool:
        return bool(self.stats()["ok"])


# ---------------------------------------------------------------- decision
def decide_v11(model, f: Dict[str, Any], pred_quote: Dict[str, Any], *, mode: str = "pnl",
               thr_scale: float = 1.0, min_notional: float = 10.0, calib: Optional[Calibration] = None,
               acc_conf: float = 0.75, acc_margin: float = 0.05, conv_ok: bool = True,
               conv_gate: str = "accuracy", trend_bps: Optional[float] = None,
               trend_guard_bps: float = 0.0, ef_min_ask: float = 0.0) -> Dict[str, Any]:
    """f: v10 feature dict (venue features already injected from the signal book).
    pred_quote: {'ask_up','size_up','ask_dn','size_dn','fee_rate'} from PREDICT.FUN.
    Every price used here is Predict.fun's; Polymarket only shaped f."""
    p = model.p_up(f)
    side, ps = ("UP", p) if p >= 0.5 else ("DOWN", 1 - p)
    off = 300 - f["sec_left"]
    base = dict(side=side, p_raw=ps, sec=int(off), rv60=f.get("rv60"))
    if off < 15 or off > 240:
        return dict(base, fire=False, reason=f"outside decision window (15-240 s), at {off:.0f} s")
    if not f.get("_venue_ok", True):
        return dict(base, fire=False, reason="signal quote incomplete (one side missing)")
    # Slow-trend guard (v11.1, OFF by default): never fire against the lean of the last N closed
    # candles when the net move exceeds trend_guard_bps. Mixed evidence on 09-08/09-09: on the
    # v10 runs' realised fires 45 min / 20 bps kept +459 vs +296; replayed through THIS function
    # on the runner's decision log it kept +421 vs +532 (the removed against-lean fires won 70%).
    base["trend_bps"] = None if trend_bps is None else round(float(trend_bps), 1)
    if trend_bps is not None and trend_guard_bps > 0:
        if (side == "UP" and trend_bps <= -trend_guard_bps) or (side == "DOWN" and trend_bps >= trend_guard_bps):
            return dict(base, fire=False, reason=f"against the lean ({trend_bps:+.0f} bps over the window)")
    ps_c = calib.apply(ps) if calib else ps
    if ps_c < 0.5:
        return dict(base, p=ps_c, fire=False, reason="live calibration puts the model's side under 50%")
    ask = pred_quote.get("ask_up" if side == "UP" else "ask_dn")
    size = pred_quote.get("size_up" if side == "UP" else "size_dn") or 0.0
    fee = pred_quote.get("fee_rate")
    fee = 0.02 if fee is None else float(fee)
    if not (isinstance(ask, (int, float)) and math.isfinite(ask) and 0.0 < ask < 1.0):
        return dict(base, p=ps_c, fire=False, reason="no Predict.fun ask for that side")
    # EF ask floor (v11.3, OFF by default): EF earns on the fires the book already prices up and
    # loses on the cheap ones (09-10: fills below 0.48 were 37% right, -0.19 per $1 on Tokyo, and
    # negative in both halves on twins A, B, C and the v10 runner). Opposite of REVERSAL's cap.
    if ef_min_ask > 0 and float(ask) < float(ef_min_ask):
        return dict(base, p=ps_c, fire=False, reason=f"ask {float(ask):.2f} below EF floor {float(ef_min_ask):.2f}")
    if size * ask < min_notional:
        return dict(base, p=ps_c, ask=ask, size=size, fire=False,
                    reason=f"Predict.fun size within 2c of ask ${size * ask:.0f} < ${min_notional:.0f}")
    cost = ask * (1.0 + fee)                       # Predict.fun: fee on notional
    if cost >= 1.0:
        return dict(base, p=ps_c, ask=ask, fire=False, reason="ask too high to pay after fee")
    ev = ps_c * (1.0 / cost - 1.0) - (1.0 - ps_c)
    regime = model.threshold(f)                    # v10 per-vol EV threshold (0.15/0.25/0.25)
    rv = f.get("rv60") or 0.0
    lo = (model.regime or {}).get("rv60_edges", [0.17, 0.37])[0]
    lane = mode
    if mode == "auto":
        lane = "accuracy" if rv <= lo else "pnl"
    if lane == "accuracy":
        fire = bool(ps_c >= acc_conf and ps_c - ask >= acc_margin)
        thr = dict(conf=acc_conf, margin=acc_margin)
    else:
        fire = bool(ev >= regime * thr_scale)
        thr = dict(ev=round(regime * thr_scale, 3))
    if fire and not conv_ok and (conv_gate == "all" or conv_gate == lane):
        return dict(base, p=ps_c, ask=float(ask), size=float(size), fee=fee, cost=round(cost, 4), ev=round(ev, 4),
                    lane=lane, threshold=thr, fire=False, reason="leader converting under its price (12-candle window)")
    return dict(base, p=ps_c, ask=float(ask), size=float(size), fee=fee, cost=round(cost, 4), ev=round(ev, 4),
                lane=lane, threshold=thr, fire=fire, reason=None if fire else "waiting")
