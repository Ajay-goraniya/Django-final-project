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
import bisect, json, math, pathlib, sys
from collections import deque
import numpy as np

US = 1_000_000
FEATURES = ["move_bps", "ret5", "ret15", "ret30", "ret60", "rv60", "range_bps", "pos_in_range",
            "dist_hi_bps", "dist_lo_bps", "spot_imb15", "spot_imb60", "ofi5", "ofi15", "ofi60",
            "perp_n15", "basis_bps", "spread_bps", "imb5", "imb20", "micro_bps", "prev1_bps",
            "prev2_bps", "sec_left", "hod_sin", "hod_cos", "p_venue", "lv", "mv_x_sec", "lv_x_sec"]


class FeatureState:
    """Rolling raw-data buffers. Every feature is computed from data at or
    before `now`; nothing looks forward. Buffers keep ~15 minutes."""

    KEEP_US = 20 * 60 * US   # prev2 needs open-10min, plus up to 5 min of candle

    def __init__(self):
        self.s_ts, self.s_px, self.s_buy, self.s_sell = deque(), deque(), deque(), deque()
        self.p_ts, self.p_px, self.p_sig, self.p_abs = deque(), deque(), deque(), deque()
        self.depth = None            # (ts, spread_bps, imb5, imb20, micro_bps, crossed)
        self.venue = (np.nan, np.nan, np.nan, np.nan)   # ask_up, bid_up, ask_dn, bid_dn

    def _trim(self, now):
        cut = now - self.KEEP_US
        for ts, *rest in ((self.s_ts, self.s_px, self.s_buy, self.s_sell), (self.p_ts, self.p_px, self.p_sig, self.p_abs)):
            while ts and ts[0] < cut:
                ts.popleft()
                for q in rest:
                    q.popleft()

    def on_spot_trade(self, ts_us, price, qty, is_buyer_maker):
        self.s_ts.append(int(ts_us)); self.s_px.append(float(price))
        self.s_buy.append(0.0 if is_buyer_maker else float(qty)); self.s_sell.append(float(qty) if is_buyer_maker else 0.0)
        self._trim(int(ts_us))

    def on_perp_trade(self, ts_us, price, qty, signed_quote_notional, quote_notional):
        self.p_ts.append(int(ts_us)); self.p_px.append(float(price))
        self.p_sig.append(float(signed_quote_notional)); self.p_abs.append(float(quote_notional))

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

    # ---- feature computation (must match learner/build_features.py exactly)
    def _px_at(self, ts):
        i = bisect.bisect_right(self.s_ts, ts) - 1
        return self.s_px[i] if i >= 0 else np.nan

    def features(self, candle_open_us, now_us):
        s_ts = np.fromiter(self.s_ts, dtype=np.int64, count=len(self.s_ts))
        s_px = np.fromiter(self.s_px, dtype=np.float64, count=len(self.s_px))
        i0 = int(np.searchsorted(s_ts, candle_open_us, side="left"))
        i = int(np.searchsorted(s_ts, now_us, side="right")) - 1
        if i0 >= len(s_ts) or i < i0:
            return None
        open_px, p = s_px[i0], s_px[i]
        seg = s_px[i0:i + 1]; hi, lo = seg.max(), seg.min(); rng = hi - lo

        def ret(sec):
            q = self._px_at(now_us - sec * US)
            return (p / q - 1) * 1e4 if np.isfinite(q) and q > 0 else 0.0

        grid = np.arange(now_us - 60 * US, now_us + 1, US)
        gi = np.searchsorted(s_ts, grid, side="right") - 1; gi = gi[gi >= 0]
        gp = s_px[gi]
        lr = np.diff(np.log(gp)) if len(gp) > 2 else np.array([0.0])
        rv60 = float(np.std(lr) * 1e4) if len(lr) > 1 else 0.0

        s_buy = np.cumsum(np.fromiter(self.s_buy, dtype=np.float64, count=len(self.s_buy)))
        s_sell = np.cumsum(np.fromiter(self.s_sell, dtype=np.float64, count=len(self.s_sell)))

        def spot_imb(sec):
            a = int(np.searchsorted(s_ts, now_us - sec * US, side="left")); b = i
            if b < a:
                return 0.0
            buy = s_buy[b] - (s_buy[a - 1] if a > 0 else 0.0); sell = s_sell[b] - (s_sell[a - 1] if a > 0 else 0.0)
            tot = buy + sell
            return (buy - sell) / tot if tot > 0 else 0.0

        p_ts = np.fromiter(self.p_ts, dtype=np.int64, count=len(self.p_ts))
        p_sig = np.cumsum(np.fromiter(self.p_sig, dtype=np.float64, count=len(self.p_sig)))
        p_abs = np.cumsum(np.fromiter(self.p_abs, dtype=np.float64, count=len(self.p_abs)))
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
                 mv_x_sec=move * sec_left / 300.0, lv_x_sec=lv * sec_left / 300.0)
        f["_ask_up"], f["_ask_dn"], f["_price"] = ask_up, ask_dn, p
        return f


class Model:
    def __init__(self, path="model_v10.json"):
        j = json.loads(pathlib.Path(path).read_text())
        assert j["features"] == FEATURES, "feature order mismatch"
        self.mean = np.array(j["scaler_mean"]); self.scale = np.array(j["scaler_scale"])
        self.coef = np.array(j["coef"]); self.b = j["intercept"]
        self.iso_x = np.array(j["iso_x"]); self.iso_y = np.array(j["iso_y"])
        self.fee = j["fee_rate"]; self.thr = j["ev_threshold_default"]
        self.regime = j.get("regime") or {}
        acc = j.get("accuracy_mode") or {}
        self.mode = j.get("mode_default", "pnl")
        self.conf_floor = acc.get("conf_floor", 0.85); self.ev_floor = acc.get("ev_floor", 0.02)
        self.acc_regime_floors = acc.get("regime_floors") or {}
        self.acc_rv_edges = acc.get("rv60_edges") or self.regime.get("rv60_edges") or [0.17, 0.37]

    def p_up(self, f):
        x = np.array([f[k] for k in FEATURES], dtype=np.float64)
        x = np.nan_to_num(x, nan=0.0)
        z = float(((x - self.mean) / self.scale) @ self.coef + self.b)
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
        f = state.features(candle_open_us, now_us)
        if f is None:
            return dict(fire=False, reason="no spot history in candle")
        p = self.p_up(f)
        side, ps, ask = ("UP", p, f["_ask_up"]) if p >= 0.5 else ("DOWN", 1 - p, f["_ask_dn"])
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
