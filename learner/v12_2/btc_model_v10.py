#!/usr/bin/env python3
"""
btc_model_v10.py -- standalone BTC 5-minute UP/DOWN learner for Polymarket.

WHAT IT IS
  A calibrated probability model plus an expected-value trading rule. It was
  trained OFFLINE on every candle of 8 days (2,272 candles x 10 decision
  seconds = 22,720 rows), not only on the candles some signal happened to fire
  on. That is the structural fix over the in-engine learners: they only ever
  saw their own fires, a few hundred biased rows, and learned confidence
  instead of accuracy.

  Design: L2 logistic regression on 26 causal BTC microstructure features +
  the venue's implied probability (raw and as a logit) + two interactions with
  time-left, then isotonic calibration. Convex, no hidden state, and its
  reported probability is what actually happens (out-of-sample calibration
  within 1 point in every bin).

WHAT IT IS NOT
  It is not EF and does not replace your engine's data plumbing. It consumes
  the same raw inputs your engine already has (spot aggTrades, perp aggTrades,
  perp top-of-book, the venue's UP/DOWN best bid/ask) and returns a
  probability and a decision. Wire it as a lane or run it beside EF.

FREQUENCY DIAL
  `ev_threshold` is the one knob. Lower = more trades, higher = fewer and
  better. Out-of-sample on the 8 days ($10 flat, one trade per candle):
      thr 0.15 ->  95 trades/day  56.8%  +$103/day   t=3.0
      thr 0.20 ->  62 trades/day  59.4%  +$130/day   t=4.5
      thr 0.30 ->  30 trades/day  59.5%   +$95/day   t=4.3
  `regime_thresholds` (optional) picks the threshold from the realized-vol
  tercile at decision time, which is how "frequency adjusts to the market".

NUMBERS YOU SHOULD NOT TRUST
  Fills on 6 of the 8 days are trade-inferred, not from an order book. The
  real-book-only subset is still positive (+$437 at thr 0.20, t>4), but treat
  the full-week dollar figures as an estimate. Live slippage is on top.

USAGE
  from btc_model_v10 import Model, FeatureState
  m = Model("model_v10.json")
  st = FeatureState()                  # feed it your raw streams as they arrive
  st.on_spot_trade(ts_us, price, qty, is_buyer_maker)
  st.on_perp_trade(ts_us, price, qty, signed_quote_notional, quote_notional)
  st.on_depth(ts_us, bid_px0, bid_qty0, ask_px0, ask_qty0, bid_qty_top5, ask_qty_top5, bid_qty_top20, ask_qty_top20, is_crossed)
  st.on_venue_quote(ask_up, bid_up, ask_dn, bid_dn)
  d = m.decide(st, candle_open_ts_us, now_ts_us)   # -> dict(side, p, ask, ev, fire, ...)

  python3 btc_model_v10.py --selftest   # parity vs the training features + in-sample check
"""
import bisect, json, math, os, pathlib, sys
from collections import deque
import numpy as np

US = 1_000_000
FEATURES = ["move_bps", "ret5", "ret15", "ret30", "ret60", "rv60", "range_bps", "pos_in_range",
            "dist_hi_bps", "dist_lo_bps", "spot_imb15", "spot_imb60", "ofi5", "ofi15", "ofi60",
            "perp_n15", "basis_bps", "spread_bps", "imb5", "imb20", "micro_bps", "prev1_bps",
            "prev2_bps", "sec_left", "hod_sin", "hod_cos", "p_venue", "lv", "mv_x_sec", "lv_x_sec"]
# 12.11.x settlement-line features, always computed and logged; a model json may list them.
EXTRA_FEATURES = ["ref_open_bps", "ref_move_bps", "ref_gap_bps", "ref_src"]


class FeatureState:
    """Rolling raw-data buffers. Every feature is computed from data at or
    before `now`; nothing looks forward. Buffers keep ~15 minutes."""

    KEEP_US = 20 * 60 * US   # prev2 needs open-10min, plus up to 5 min of candle

    def __init__(self, cache=True):
        self.s_ts, self.s_px, self.s_buy, self.s_sell = deque(), deque(), deque(), deque()
        self.p_ts, self.p_px, self.p_sig, self.p_abs = deque(), deque(), deque(), deque()
        self.depth = None            # (ts, spread_bps, imb5, imb20, micro_bps, crossed)
        self.venue = (np.nan, np.nan, np.nan, np.nan)   # ask_up, bid_up, ask_dn, bid_dn
        # 12.11.0 settlement-reference stream (Polymarket's public Chainlink BTC/USD feed,
        # ~1 value/s). The venue settles btc-5m-twap-60 markets on this feed's 60 s TWAP
        # at close vs the same TWAP at the candle start. When the buffer covers a window
        # its TWAP is used; otherwise the Binance spot TWAP stands in (ref_src=0).
        self.r_ts, self.r_px = deque(), deque()
        # Which price the candle "open" means for every open-relative feature:
        # "first_trade" (v10 as trained) or "twap60" (a model retrained on the settlement
        # line sets open_reference="twap60" in its json; Model.decide copies it here).
        self.open_ref = "first_trade"
        # 12.9.0 array cache. features() converted every deque with np.fromiter
        # (+ cumsum) on EVERY call: ~15 ms at 120k rows, and the live engine
        # calls it twice per 250 ms tick and five more times per fire attempt.
        # The conversions depend only on the deque contents, so they are kept
        # until a trade mutates a deque (_rev bumps in on_spot_trade, which also
        # trims both sides, and on_perp_trade). Everything that depends on
        # now_us, depth or the venue quote is still computed per call. The
        # arrays are read-only inside features(), so reuse is bit-identical
        # (FeatureCacheParity pins that on 1,000 ticks). cache=False is the
        # reference path for that test.
        self.cache = bool(cache); self.cache_hits = 0
        self._rev = 0; self._arr_key = None; self._arr = None

    def _trim(self, now):
        cut = now - self.KEEP_US
        for ts, *rest in ((self.s_ts, self.s_px, self.s_buy, self.s_sell), (self.p_ts, self.p_px, self.p_sig, self.p_abs)):
            while ts and ts[0] < cut:
                ts.popleft()
                for q in rest:
                    q.popleft()

    def on_spot_trade(self, ts_us, price, qty, is_buyer_maker):
        if not (price > 0):
            return
        self.s_ts.append(int(ts_us)); self.s_px.append(float(price))
        self.s_buy.append(0.0 if is_buyer_maker else float(qty)); self.s_sell.append(float(qty) if is_buyer_maker else 0.0)
        self._trim(int(ts_us)); self._rev += 1

    def on_perp_trade(self, ts_us, price, qty, signed_quote_notional, quote_notional):
        # Binance futures @trade emits "X":"NA" prints with p=0,q=0 (about 15/min live);
        # one of those as the latest perp print makes basis_bps = -10000 and pins p.
        if not (price > 0):
            return
        self.p_ts.append(int(ts_us)); self.p_px.append(float(price))
        self.p_sig.append(float(signed_quote_notional)); self.p_abs.append(float(quote_notional))
        self._rev += 1

    def on_depth(self, ts_us, b0, bq0, a0, aq0, bq5, aq5, bq20, aq20, is_crossed=0):
        if not (a0 > 0 and b0 > 0):
            return
        mid = (a0 + b0) / 2
        micro = (a0 * bq0 + b0 * aq0) / (bq0 + aq0) if (bq0 + aq0) > 0 else mid
        self.depth = (int(ts_us), (a0 - b0) / mid * 1e4,
                      (bq5 - aq5) / (bq5 + aq5) if (bq5 + aq5) > 0 else 0.0,
                      (bq20 - aq20) / (bq20 + aq20) if (bq20 + aq20) > 0 else 0.0,
                      (micro - mid) / mid * 1e4, float(is_crossed))

    def on_venue_quote(self, ask_up, bid_up, ask_dn, bid_dn):
        # keep any finite quote (mirrors training); decide() guards 0<ask<1 itself
        f = lambda x: float(x) if x is not None and math.isfinite(float(x)) else np.nan
        self.venue = (f(ask_up), f(bid_up), f(ask_dn), f(bid_dn))

    def on_ref_price(self, ts_us, price):
        """One settlement-reference sample (Chainlink BTC/USD via the venue's feed)."""
        if not (price > 0):
            return
        ts_us = int(ts_us)
        if self.r_ts and ts_us < self.r_ts[-1]:
            return                       # out of order: keep the step function monotone
        self.r_ts.append(ts_us); self.r_px.append(float(price))
        cut = ts_us - self.KEEP_US
        while self.r_ts and self.r_ts[0] < cut:
            self.r_ts.popleft(); self.r_px.popleft()

    # The venue's feed already publishes the settlement quantity (Chainlink's 60 s TWAP,
    # resolutionSource btc-usd-twap-60s; the market's price-to-beat is that value at
    # eventStartTime). So the line at the open is the feed's value AT the open and the
    # line now is its latest value - never a TWAP of a TWAP. REF_IS_TWAP=0 (env) switches
    # to averaging the feed, for the case where a raw-price topic is configured instead.
    REF_IS_TWAP = os.environ.get("REF_IS_TWAP", "1") != "0"
    REF_STALE_US = 5 * US

    def _ref_at(self, t):
        """Reference value in force at t (latest sample <= t), nan if none or stale."""
        i = bisect.bisect_right(self.r_ts, int(t)) - 1
        if i < 0 or t - self.r_ts[i] > self.REF_STALE_US:
            return np.nan
        return self.r_px[i]

    def _ref_twap(self, t0, t1):
        """TWAP of the reference stream over [t0, t1) if the buffer covers it, else nan."""
        if len(self.r_ts) < 2 or self.r_ts[0] > t0 or self.r_ts[-1] < t1 - self.REF_STALE_US:
            return np.nan                # no sample in force at t0, or feed stale near t1
        ts = np.fromiter(self.r_ts, dtype=np.int64, count=len(self.r_ts))
        px = np.fromiter(self.r_px, dtype=np.float64, count=len(self.r_px))
        return self._twap(ts, px, t0, t1)

    def _ref_line(self, t0, t1):
        """Settlement line over the window ending at t1: the feed's value at t1 when the feed
        is the TWAP itself, else the TWAP of the feed over [t0, t1)."""
        return self._ref_at(t1) if self.REF_IS_TWAP else self._ref_twap(t0, t1)

    # ---- feature computation (must match learner/build_features.py exactly)
    @staticmethod
    def _twap(ts, px, t0, t1):
        """Time-weighted mean of the step-function spot price over [t0, t1); nan if no trade in force."""
        if t1 <= t0 or len(ts) == 0:
            return np.nan
        j0 = int(np.searchsorted(ts, t0, side="right")) - 1   # trade in force at t0
        j1 = int(np.searchsorted(ts, t1, side="left"))         # first trade at/after t1
        if j1 <= 0:
            return np.nan
        j0 = max(j0, 0)
        t = np.concatenate(([t0], ts[j0 + 1:j1], [t1])).astype(np.float64)
        w = np.diff(t)
        if w.sum() <= 0:
            return np.nan
        return float(np.dot(px[j0:j1], w) / w.sum())

    def _px_at(self, ts):
        i = bisect.bisect_right(self.s_ts, ts) - 1
        return self.s_px[i] if i >= 0 else np.nan

    def _arrays(self):
        """The deque -> ndarray conversions features() needs, cached per mutation."""
        key = (self._rev, len(self.s_ts), len(self.p_ts))
        if self.cache and self._arr_key == key:
            self.cache_hits += 1
            return self._arr
        s_ts = np.fromiter(self.s_ts, dtype=np.int64, count=len(self.s_ts))
        s_px = np.fromiter(self.s_px, dtype=np.float64, count=len(self.s_px))
        s_buy = np.cumsum(np.fromiter(self.s_buy, dtype=np.float64, count=len(self.s_buy)))
        s_sell = np.cumsum(np.fromiter(self.s_sell, dtype=np.float64, count=len(self.s_sell)))
        p_ts = np.fromiter(self.p_ts, dtype=np.int64, count=len(self.p_ts))
        p_sig = np.cumsum(np.fromiter(self.p_sig, dtype=np.float64, count=len(self.p_sig)))
        p_abs = np.cumsum(np.fromiter(self.p_abs, dtype=np.float64, count=len(self.p_abs)))
        arr = (s_ts, s_px, s_buy, s_sell, p_ts, p_sig, p_abs)
        if self.cache:
            self._arr_key, self._arr = key, arr
        return arr

    def features(self, candle_open_us, now_us):
        s_ts, s_px, s_buy, s_sell, p_ts, p_sig, p_abs = self._arrays()
        i0 = int(np.searchsorted(s_ts, candle_open_us, side="left"))
        i = int(np.searchsorted(s_ts, now_us, side="right")) - 1
        if i0 >= len(s_ts) or i < i0:
            return None
        open_px, p = s_px[i0], s_px[i]
        # Settlement-reference line (R-16). ref_open = 60 s TWAP ending at the candle open,
        # ref_now = 60 s TWAP ending now; from the venue's Chainlink feed when the buffer
        # covers the window (ref_src=1), else the Binance spot TWAP proxy (ref_src=0).
        ref_open = self._ref_line(candle_open_us - 60 * US, candle_open_us)
        ref_now = self._ref_line(now_us - 60 * US, now_us)
        ref_src = 1.0 if (np.isfinite(ref_open) and np.isfinite(ref_now)) else 0.0
        if not (np.isfinite(ref_open) and ref_open > 0):
            ref_open = self._twap(s_ts, s_px, candle_open_us - 60 * US, candle_open_us)
        if not (np.isfinite(ref_now) and ref_now > 0):
            ref_now = self._twap(s_ts, s_px, now_us - 60 * US, now_us)
        if not (np.isfinite(ref_open) and ref_open > 0):
            ref_open = open_px
        if not (np.isfinite(ref_now) and ref_now > 0):
            ref_now = p
        first_trade_px = open_px
        if self.open_ref == "twap60":
            open_px = ref_open           # every open-relative feature below now measures from the settlement line
        seg = s_px[i0:i + 1]; hi, lo = seg.max(), seg.min(); rng = hi - lo

        def ret(sec):
            q = self._px_at(now_us - sec * US)
            return (p / q - 1) * 1e4 if np.isfinite(q) and q > 0 else 0.0

        grid = np.arange(now_us - 60 * US, now_us + 1, US)
        gi = np.searchsorted(s_ts, grid, side="right") - 1; gi = gi[gi >= 0]
        gp = s_px[gi]
        lr = np.diff(np.log(gp)) if len(gp) > 2 else np.array([0.0])
        rv60 = float(np.std(lr) * 1e4) if len(lr) > 1 else 0.0

        def spot_imb(sec):
            a = int(np.searchsorted(s_ts, now_us - sec * US, side="left")); b = i
            if b < a:
                return 0.0
            buy = s_buy[b] - (s_buy[a - 1] if a > 0 else 0.0); sell = s_sell[b] - (s_sell[a - 1] if a > 0 else 0.0)
            tot = buy + sell
            return (buy - sell) / tot if tot > 0 else 0.0

        pi = int(np.searchsorted(p_ts, now_us, side="right")) - 1

        def perp_ofi(sec):
            a = int(np.searchsorted(p_ts, now_us - sec * US, side="left")); b = pi
            if b < a or b < 0:
                return 0.0, 0.0
            sg = p_sig[b] - (p_sig[a - 1] if a > 0 else 0.0); ab = p_abs[b] - (p_abs[a - 1] if a > 0 else 0.0)
            return (sg / ab if ab > 0 else 0.0), float(b - a + 1)

        ofi5, _ = perp_ofi(5); ofi15, n15 = perp_ofi(15); ofi60, _ = perp_ofi(60)
        perp_px = self.p_px[pi] if pi >= 0 else np.nan
        basis = (perp_px / p - 1) * 1e4 if np.isfinite(perp_px) else 0.0
        d = self.depth
        spread, imb5, imb20, micro = (d[1], d[2], d[3], d[4]) if d else (0.0, 0.0, 0.0, 0.0)
        p1, p2, p3 = self._px_at(candle_open_us), self._px_at(candle_open_us - 300 * US), self._px_at(candle_open_us - 600 * US)
        prev1 = (p1 / p2 - 1) * 1e4 if np.isfinite(p2) and p2 > 0 else 0.0
        prev2 = (p2 / p3 - 1) * 1e4 if np.isfinite(p3) and p3 > 0 else 0.0
        off = (now_us - candle_open_us) / US
        ep = candle_open_us // US
        hod = ((ep % 86400) / 86400.0) * 2 * math.pi
        ask_up, bid_up, ask_dn, bid_dn = self.venue
        if np.isfinite(ask_up) and np.isfinite(bid_up):
            p_venue = (ask_up + bid_up) / 2
        elif np.isfinite(ask_up) and np.isfinite(ask_dn):
            p_venue = (ask_up + (1 - ask_dn)) / 2
        else:
            p_venue = np.nan
        pvc = min(0.98, max(0.02, p_venue)) if np.isfinite(p_venue) else np.nan
        lv = math.log(pvc / (1 - pvc)) if np.isfinite(pvc) else 0.0
        sec_left = 300 - off
        move = (p / open_px - 1) * 1e4
        f = dict(move_bps=move, ret5=ret(5), ret15=ret(15), ret30=ret(30), ret60=ret(60), rv60=rv60,
                 range_bps=rng / open_px * 1e4, pos_in_range=((p - lo) / rng) if rng > 0 else 0.5,
                 dist_hi_bps=(hi - p) / open_px * 1e4, dist_lo_bps=(p - lo) / open_px * 1e4,
                 spot_imb15=spot_imb(15), spot_imb60=spot_imb(60), ofi5=ofi5, ofi15=ofi15, ofi60=ofi60,
                 perp_n15=n15, basis_bps=basis, spread_bps=spread, imb5=imb5, imb20=imb20, micro_bps=micro,
                 prev1_bps=prev1, prev2_bps=prev2, sec_left=sec_left, hod_sin=math.sin(hod), hod_cos=math.cos(hod),
                 p_venue=(p_venue if np.isfinite(p_venue) else 0.0), lv=lv,
                 mv_x_sec=move * sec_left / 300.0, lv_x_sec=lv * sec_left / 300.0,
                 ref_open_bps=(first_trade_px / ref_open - 1) * 1e4, ref_move_bps=(ref_now / ref_open - 1) * 1e4,
                 ref_gap_bps=(p / ref_open - 1) * 1e4, ref_src=ref_src)
        f["_ask_up"], f["_ask_dn"], f["_price"] = ask_up, ask_dn, p
        f["_venue_ok"] = bool(np.isfinite(p_venue))   # both sides quoted -> venue features are real, not zero-filled
        return f


class Model:
    def __init__(self, path="model_v10.json"):
        j = json.loads(pathlib.Path(path).read_text())
        # 12.11.1: the json owns its feature list. v10's json equals FEATURES; a model retrained
        # on the settlement line may add ref_move_bps / ref_gap_bps / ref_src (every name must be
        # a key FeatureState.features() computes - checked at load, not at fire time).
        self.features = list(j["features"])
        assert all(isinstance(k, str) and k for k in self.features), "bad feature list"
        unknown = [k for k in self.features if k not in FEATURES and k not in EXTRA_FEATURES]
        assert not unknown, f"features not computed by FeatureState: {unknown}"
        self.mean = np.array(j["scaler_mean"]); self.scale = np.array(j["scaler_scale"])
        self.coef = np.array(j["coef"]); self.b = j["intercept"]
        self.iso_x = np.array(j["iso_x"]); self.iso_y = np.array(j["iso_y"])
        self.fee = j["fee_rate"]; self.thr = j["ev_threshold_default"]
        self.open_ref = j.get("open_reference", "first_trade")
        assert self.open_ref in ("first_trade", "twap60"), "unknown open_reference"
        self.p_source = j.get("p_source", "model")
        assert self.p_source in ("model", "venue"), "unknown p_source"
        self.regime = j.get("regime") or {}
        acc = j.get("accuracy_mode") or {}
        self.mode = j.get("mode_default", "pnl")
        self.conf_floor = acc.get("conf_floor", 0.85); self.ev_floor = acc.get("ev_floor", 0.02)
        self.acc_regime_floors = acc.get("regime_floors") or {}
        self.acc_rv_edges = acc.get("rv60_edges") or self.regime.get("rv60_edges") or [0.17, 0.37]

    def p_up(self, f):
        # 12.13.0, R-23: `p_source: "venue"` in the json makes the decision read the venue's own
        # price instead of the fitted model. It is not a shortcut - it is the measured result:
        # replaying the EV rule with p = p_venue gave +0.296/$1 on 547 fires against the model's
        # +0.141 on 1,033, at a lower drawdown, because what we are paid for is a lagging book
        # rather than a forecast (R-13, R-18, R-19). Kept behind a json field so the two run side
        # by side on the same candles and the comparison is an observation, not an argument.
        # Off unless a json asks for it; model_v10.json does not.
        if self.p_source == "venue":
            pv = f.get("p_venue")
            if not (pv is not None and np.isfinite(pv) and f.get("_venue_ok")):
                return float("nan")             # no two-sided book -> decide() refuses, as it does today
            return float(min(0.98, max(0.02, pv)))
        x = np.array([f[k] for k in self.features], dtype=np.float64)
        x = np.nan_to_num(x, nan=0.0)
        z = float(((x - self.mean) / self.scale) @ self.coef + self.b)
        z = max(-60.0, min(60.0, z))            # numerically safe sigmoid
        raw = 1.0 / (1.0 + math.exp(-z))
        return float(np.interp(raw, self.iso_x, self.iso_y))

    def cost(self, q):
        return q / (1 - self.fee * (1 - q))

    def threshold(self, f):
        """Frequency dial. Fixed, or per realized-vol regime if configured."""
        r = self.regime
        if r and r.get("thresholds") and f is not None:
            lo, hi = r["rv60_edges"]
            key = "low" if f["rv60"] <= lo else ("mid" if f["rv60"] <= hi else "high")
            return float(r["thresholds"].get(key, self.thr))
        return self.thr

    def decide(self, state, candle_open_us, now_us, ev_threshold=None, mode=None,
               conf_floor=None, ev_floor=None):
        """Two modes, both out-of-sample tested on 8 days / 2,272 candles:

        mode="pnl"      fire when EV >= ev_threshold (default 0.20; or per-vol
                        regime). ~62 trades/day, 59% accuracy, +$2.09 per $10.
        mode="accuracy" fire when confidence p_side >= conf_floor AND EV >= ev_floor.
                        With regime_floors configured (default in model_v10.json) the
                        floors follow the realized-vol regime, so frequency adapts to
                        the market: ~53 trades/day, 81.8% accuracy, and under the
                        $50 hybrid staking rule $50 -> $1,538 over the 8-day week
                        (out-of-sample). Fixed 0.85/0.02: ~82/day, 87.6%, 8/8 days.
        Frequency is adjusted by moving these floors; nothing else changes.
        """
        state.open_ref = self.open_ref   # train == serve: the json says which "open" its weights were fitted on
        f = state.features(candle_open_us, now_us)
        if f is None:
            return dict(fire=False, reason="no spot history in candle")
        p = self.p_up(f)
        if not np.isfinite(p):
            return dict(fire=False, reason="no venue probability for this candle")
        side, ps, ask = ("UP", p, f["_ask_up"]) if p >= 0.5 else ("DOWN", 1 - p, f["_ask_dn"])
        off = 300 - f["sec_left"]
        # Only decide inside the window the model was trained and validated on
        # (offsets 15..240 s). Earlier there is no information yet; later the book
        # is one-sided and near-resolved, which is where the 0.01 "dust" asks live.
        if off < 15 or off > 240:
            return dict(fire=False, side=side, p=ps, reason=f"outside decision window (15-240 s), at {off:.0f} s")
        # A venue quote with one side missing zero-fills p_venue/lv, so p collapses to
        # ~0.51 while the remaining ask can be a 0.01 leftover: EV explodes on nothing.
        # Every bogus fire seen live (2026-09-08) had exactly this signature.
        if not f.get("_venue_ok", True):
            return dict(fire=False, side=side, p=ps, reason="venue quote incomplete (one side missing)")
        if not (isinstance(ask, float) and np.isfinite(ask) and 0 < ask < 1):
            return dict(fire=False, side=side, p=ps, reason="no venue ask for that side")
        ev = ps * (1 / self.cost(ask) - 1) - (1 - ps)
        mode = mode or self.mode
        if mode == "accuracy":
            cf = self.conf_floor if conf_floor is None else conf_floor
            ef = self.ev_floor if ev_floor is None else ev_floor
            # frequency adapts to the market: per realized-vol regime floors, if configured
            rf = self.acc_regime_floors
            if conf_floor is None and ev_floor is None and rf:
                lo, hi = self.acc_rv_edges
                key = "low" if f["rv60"] <= lo else ("mid" if f["rv60"] <= hi else "high")
                if key in rf:
                    cf, ef = float(rf[key]["conf_floor"]), float(rf[key]["ev_floor"])
            fire = bool(ps >= cf and ev >= ef)
            thr = dict(conf_floor=cf, ev_floor=ef)
        else:
            thr = self.thr if ev_threshold is None else ev_threshold
            if ev_threshold is None and self.regime:
                thr = self.threshold(f)
            fire = bool(ev >= thr)
        return dict(fire=fire, mode=mode, side=side, p=round(ps, 4), ask=ask, ev=round(ev, 4),
                    threshold=thr, breakeven=round(self.cost(ask), 4), rv60=round(f["rv60"], 3),
                    sec=int(300 - f["sec_left"]))


# ----------------------------------------------------------------- self-test
def _selftest():
    import pandas as pd, glob, datetime as dt, pyarrow.parquet as pq, pyarrow as pa
    here = pathlib.Path(__file__).resolve().parent
    m = Model(here / "model_v10.json")
    F = pd.read_parquet(here / "features.parquet")
    pv = F.p_venue.clip(0.02, 0.98)
    F["lv"] = np.log(pv / (1 - pv)).fillna(0.0)
    F["mv_x_sec"] = F.move_bps * F.sec_left / 300.0; F["lv_x_sec"] = F.lv * F.sec_left / 300.0
    # 1. parity: live feature path vs the training feature table, on real tape
    d = "2026-09-03"; root = here.parent
    W0 = int(dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
    nd = root / "week_replay" / d / "normalized"
    sp = pa.concat_tables([pq.read_table(f, columns=["timestamp", "price", "quantity", "is_buyer_maker"]) for f in sorted(glob.glob(str(nd / "spot_aggtrades_1[0-1].parquet")))]).to_pandas().sort_values("timestamp")
    pp = pa.concat_tables([pq.read_table(f, columns=["timestamp", "price", "quantity", "signed_quote_notional", "quote_notional"]) for f in sorted(glob.glob(str(nd / "perp_trades_1[0-1].parquet")))]).to_pandas().sort_values("timestamp")
    st = FeatureState(); st.KEEP_US = 10**12   # whole tape is fed first, so do not trim
    for r in sp.itertuples(): st.on_spot_trade(r.timestamp, r.price, r.quantity, r.is_buyer_maker)
    for r in pp.itertuples(): st.on_perp_trade(r.timestamp, r.price, r.quantity, r.signed_quote_notional, r.quote_notional)
    worst = 0.0; n = 0
    for k in range(11 * 12 + 2, 11 * 12 + 12):          # candles inside hour 11 (hours 10-11 loaded)
        ep = W0 + k * 300
        for off in (30, 120, 240):
            row = F[(F.epoch == ep) & (F.offset == off)]
            if row.empty: continue
            f = st.features(ep * US, (ep + off) * US)
            if f is None: continue
            for c in ("move_bps", "ret30", "ret60", "rv60", "range_bps", "spot_imb60", "ofi60", "basis_bps", "prev1_bps"):
                worst = max(worst, abs(float(f[c]) - float(row[c].iloc[0]))); n += 1
    print(f"parity live-path vs training table: {n} feature values checked, max abs diff {worst:.2e}  ->  {'OK' if worst < 1e-6 else 'MISMATCH'}")
    # 2. model output vs the training-time pipeline (in-sample, params fitted on all days)
    from sklearn.metrics import log_loss
    X = F[FEATURES].fillna(0.0)
    p = np.array([m.p_up(dict(zip(FEATURES, x))) for x in X.values])
    print(f"in-sample logloss of exported model: {log_loss(F.y, p):.4f}   (out-of-sample LODO was 0.4988; venue 0.4953 all-rows)")
    print(f"P(UP) range {p.min():.3f}..{p.max():.3f}   mean {p.mean():.3f}   label mean {F.y.mean():.3f}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
