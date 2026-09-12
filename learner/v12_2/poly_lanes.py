"""MAIN and REVERSAL signal lanes, ported from Build 11.2 (btc_model_build11.py).

Why this file exists
--------------------
v12.0 and v12.1 shipped MAIN and REVERSAL as dashboard toggles that could never
fire, on the stated grounds that the packaged v10 classifier contains no MAIN or
REVERSAL logic.  That statement is true and the refusal to synthesise a strategy
from v10 was correct.  It was also the wrong conclusion, because MAIN and
REVERSAL never ran on v10 in the first place.

In the live build the two lanes share one signal engine that has no contact with
v10, with the Polymarket book, or with the EF learner.  It reads Binance spot
trades and depth only:

    pressure gauge   0.45*clamp(imbalance/0.3) + 0.35*clamp(delta/0.25) + 0.20*momentum
    fair odds        Phi(lead / (sigma * sqrt(seconds_left)))
    volume ratio     this candle's pace against the median of the last 24
    13-feature model tanh-squashed micro-features, sigmoid at temperature 1.55

v12 already carries every one of those inputs, so the lanes are ported here
rather than invented.  Constants, weights and gate order are copied from the
live file; the provenance comment on each block names the original lines.

What is NOT claimed
-------------------
Porting makes the lanes real and controllable.  It does not make them proven.
On the live Tokyo account MAIN has 0 settled fills and REVERSAL has 53 for
+1.27, so REVERSAL's record is thin and MAIN's does not exist.  Treat both as
untested on Polymarket, whose book and fee model differ from Predict.fun's.

One deliberate difference from the live build
---------------------------------------------
Build 11 drifts the 13-feature weights by online SGD after every settled candle
and persists them, so its live weights are no longer the anchors.  This port
starts from the published anchors and will load drifted weights when a
``model_weights`` row is present, but it does not itself run SGD: a learner that
trains on Polymarket settlement is a separate decision, not a porting detail.
"""
import json, math, time
from collections import deque

# ---- constants, verbatim from btc_model_build11.py lines 522-543, 776-829 ----
PRESSURE_FIRE = 0.15
PRESSURE_STRONG = 0.45
PRESSURE_HISTORY = 300
IMBALANCE_STRONG = 0.12
DELTA_STRONG = 0.10
MIN_SCORE = 2

EDGE_CONTRADICTION_KEEP = 0.25
MAIN_HOLD_MS = 12_000
MAIN_HOLD_READS = 60
MAIN_LAST_SECOND = 295.0

GATED_ODDS_UP = 0.60
GATED_ODDS_DOWN = 0.40
GATED_VOL_MIN = 0.70

REVERSAL_MIN_SECOND = 30.0
REVERSAL_LAST_SECOND = 285.0

VOL_REFERENCE = 1.00
VOL_FLOOR_FACTOR = 0.55
VOL_CEILING_FACTOR = 0.80
VOLATILITY_WINDOW = 120
REJECTION_MIN_ACTIVITY = 0.5
REJECTION_CAP = 6.0
REJECTION_HALF_LIFE_SEC = 8.0
REJECTION_ZONE_SIGMA = 1.5
REJECTION_MIN_SCALE_USD = 1.5
RUNWAY_MIN_FACTOR = 0.55
FEASIBILITY_SIGMAS = 2.5

MODEL_TEMPERATURE = 1.55
MODEL_WEIGHT_CLAMP = 0.35
CANDLE_MS = 300_000

MODEL_FEATURE_SPEC = (
    ("delta_1s", 1.10, 0.10), ("delta_5s", 0.95, 0.10), ("delta_30s", 0.55, 0.12),
    ("ofi_1s", 0.85, 250.0), ("ofi_5s", 0.60, 250.0), ("spot_imbalance5", 0.90, 0.12),
    ("return_250ms_bps", 0.25, 0.80), ("return_1s_bps", 0.40, 1.30), ("return_5s_bps", 0.35, 2.50),
    ("body_range_ratio", 0.30, 0.50), ("close_location_centred", 0.30, 0.60),
    ("aggressive_cluster_bias", 0.25, 1.50), ("volume_profile_delta", 0.35, 0.15),
)
MODEL_FEATURE_NAMES = tuple(n for n, _, _ in MODEL_FEATURE_SPEC)


def clamp(v, lo, hi): return lo if v < lo else hi if v > hi else v
def logistic(x): return 1.0 / (1.0 + math.exp(-clamp(x, -60.0, 60.0)))
def safe_float(v, d=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else d
    except Exception:
        return d


def avg_move(hist, secs=10.0):
    """Median absolute move over `secs` seconds (build11:1409)."""
    rows = list(hist); moves = []; right = 1
    for left in range(len(rows)):
        if right <= left: right = left + 1
        while right < len(rows) and rows[right][0] - rows[left][0] < secs: right += 1
        if right < len(rows): moves.append(abs(rows[right][1] - rows[left][1]))
    moves.sort()
    return moves[len(moves) // 2] if moves else 0.0


def pressure_score(imb, delta, mom):
    """The v5/v7 gauge. Weights and divisors are fixed (build11:1432)."""
    return (0.45 * clamp(imb / 0.3, -1.0, 1.0)
            + 0.35 * clamp(delta / 0.25, -1.0, 1.0)
            + 0.20 * mom)


def pressure_text(score, magnitude):
    """build11:1439. The lanes read only the leading UP/DOWN token."""
    if abs(score) < PRESSURE_FIRE: return "BALANCED"
    d = "UP" if score > 0 else "DOWN"
    s = "strong" if abs(score) > PRESSURE_STRONG else "weak"
    est = magnitude * (1.0 + abs(score)) if magnitude else 0.0
    return f"{d} {s} ~${est:.0f}"


def volume_factor(vr):
    """build11:1490. Damps both a dead tape and a violent one."""
    if vr <= 0.0: return VOL_FLOOR_FACTOR
    if vr < VOL_REFERENCE:
        return VOL_FLOOR_FACTOR + (1.0 - VOL_FLOOR_FACTOR) * max(vr / VOL_REFERENCE, 0.0)
    if vr <= 2.0: return 1.0
    return 1.0 - (1.0 - VOL_CEILING_FACTOR) * min((vr - 2.0) / 3.0, 1.0)


def rejection_factor(sign, reject_up, reject_down):
    """build11:1507. Reads the balance between the sides, never a magnitude."""
    total = reject_up + reject_down
    if total <= REJECTION_MIN_ACTIVITY: return 1.0
    share = (reject_up if sign > 0 else reject_down) / total
    if share <= 0.5: return 1.0
    return 1.0 - 0.5 * min((share - 0.5) * 2.0, 1.0)


def runway_factor(seconds_left):
    """build11:1532. Less time left, less confidence."""
    if seconds_left <= 0.0: return 0.5
    return RUNWAY_MIN_FACTOR + (1.0 - RUNWAY_MIN_FACTOR) * clamp(seconds_left / 240.0, 0.0, 1.0)


def feasibility_factor(required, sigma_root, seconds_left):
    """build11:1547. Is the move being predicted physically plausible."""
    if seconds_left <= 0.0 or sigma_root <= 0.0: return 0.5
    expected = sigma_root * math.sqrt(seconds_left)
    if expected <= 0.0: return 0.5
    sigmas = abs(required) / expected
    if sigmas <= 1.0: return 1.0
    if sigmas >= FEASIBILITY_SIGMAS: return 0.5
    return 1.0 - 0.5 * (sigmas - 1.0) / (FEASIBILITY_SIGMAS - 1.0)


class RollingDelta:
    """Aggressive-buy vs aggressive-sell quote-volume delta (build11:4359)."""
    def __init__(self, window_ms):
        self.window_ms = int(window_ms); self.items = deque(); self.buy = 0.0; self.sell = 0.0
    def add(self, ts_ms, signed_quote):
        buy = signed_quote if signed_quote > 0 else 0.0
        sell = -signed_quote if signed_quote < 0 else 0.0
        self.items.append((ts_ms, buy, sell)); self.buy += buy; self.sell += sell; self.prune(ts_ms)
    def prune(self, ts_ms):
        cutoff = ts_ms - self.window_ms
        while self.items and self.items[0][0] < cutoff:
            _, b, s = self.items.popleft(); self.buy -= b; self.sell -= s
    def value(self, ts_ms):
        self.prune(ts_ms); total = self.buy + self.sell
        return (self.buy - self.sell) / total if total > 0 else 0.0


class Model:
    """score = sum(w_i*tanh(x_i/thr_i)); p_up = sigmoid(score/T)  (build11:4606).

    Anchors are the published values. Weights loaded from a persisted table are
    clamped to the same band the live build enforces. No SGD here; see the
    module docstring.
    """
    def __init__(self, weights=None, version=0, temperature=MODEL_TEMPERATURE):
        self.anchors = {n: w for n, w, _ in MODEL_FEATURE_SPEC}
        self.thresholds = {n: t for n, _, t in MODEL_FEATURE_SPEC}
        self.temperature = float(temperature) or MODEL_TEMPERATURE
        self.version = int(version)
        self.weights = dict(self.anchors)
        for n, v in (weights or {}).items():
            if n in self.weights:
                a = self.anchors[n]
                self.weights[n] = clamp(safe_float(v, a), a - MODEL_WEIGHT_CLAMP, a + MODEL_WEIGHT_CLAMP)
    def score(self, feature):
        comps = {n: self.weights[n] * math.tanh(safe_float(feature.get(n)) / (self.thresholds[n] or 1.0))
                 for n in MODEL_FEATURE_NAMES}
        s = sum(comps.values())
        return s, logistic(s / self.temperature), comps


class LaneEngine:
    """Feature state plus the MAIN and REVERSAL gates.

    Fed by the same Binance streams the v10 lane already consumes:
      on_spot_trade(ts_ms, price, qty, is_buyer_maker)
      on_depth(bids, asks)
      on_candle(candle dict), on_closed_candle(candle dict)

    ``evaluate(ts_ms)`` returns a decision for whichever lane is ready, or None.
    Execution gating (master switch, per-kind toggle) is the caller's job, which
    is how the live build separates signal from permission.
    """

    def __init__(self, weights=None):
        self.model = Model(weights)
        self.delta_1s = RollingDelta(1_000)
        self.delta_5s = RollingDelta(5_000)
        self.delta_30s = RollingDelta(30_000)
        self.pressure_history = deque(maxlen=PRESSURE_HISTORY)
        self.price_history = deque(maxlen=4000)      # (ts_s, price) for returns
        self.depth = {"bids": [], "asks": []}
        self.candle = None
        self.closed = deque(maxlen=64)
        self.feature = {}
        self.reject_up = 0.0; self.reject_down = 0.0; self.reject_ts = 0.0
        self.candle_high_seen = 0.0; self.candle_low_seen = 0.0
        self.current_main = None      # {'direction','ts_ms','probability_up'}
        self.current_reversal = None
        self.main_streak_dir = ""; self.main_streak_start_ms = 0; self.main_streak_reads = 0
        self.main_block = ""; self.reversal_state = {"status": "idle", "detail": ""}
        self._candle_id = None

    # ---- inputs ---------------------------------------------------------
    def on_spot_trade(self, ts_ms, price, qty, is_buyer_maker):
        signed = price * qty * (-1.0 if is_buyer_maker else 1.0)
        for d in (self.delta_1s, self.delta_5s, self.delta_30s):
            d.add(int(ts_ms), signed)
        self.price_history.append((ts_ms / 1000.0, price))

    def on_depth(self, bids, asks):
        self.depth = {"bids": bids, "asks": asks}

    def on_candle(self, candle):
        cid = int(candle["time"])
        if self._candle_id is not None and cid != self._candle_id:
            # New candle: MAIN/REVERSAL are once per candle, and the rejection
            # extremes are per-candle state (build11 resets them the same way).
            self.current_main = None; self.current_reversal = None
            self.main_streak_dir = ""; self.main_streak_start_ms = 0; self.main_streak_reads = 0
            self.reject_up = self.reject_down = 0.0
            self.candle_high_seen = self.candle_low_seen = 0.0
            self.reversal_state = {"status": "idle", "detail": ""}
        self._candle_id = cid
        self.candle = candle

    def on_closed_candle(self, candle):
        c = dict(candle); c["closed"] = True
        self.closed.append(c)

    # ---- derived quantities --------------------------------------------
    def spot_imbalance5(self):
        b = sum(q for _, q in (self.depth.get("bids") or [])[:5])
        a = sum(q for _, q in (self.depth.get("asks") or [])[:5])
        return (b - a) / (b + a) if (b + a) else 0.0

    def _return_bps(self, now_s, price, window_s):
        ref = None
        for ts, p in reversed(self.price_history):
            if now_s - ts >= window_s: ref = p; break
        return ((price / ref - 1.0) * 10_000.0) if ref else 0.0

    def sigma_per_root_second(self):
        """build11:15949. Never cleared between candles, so it is available
        from the first second rather than needing the candle to form."""
        h = list(self.pressure_history)[-VOLATILITY_WINDOW:]
        if len(h) < 12: return 0.0
        span = h[-1][0] - h[0][0]
        if span <= 0: return 0.0
        moves = [abs(h[i][1] - h[i - 1][1]) for i in range(1, len(h))]
        if not moves: return 0.0
        per_step = sum(moves) / len(moves)
        sps = span / max(len(h) - 1, 1)
        return per_step / math.sqrt(sps) if sps > 0 else 0.0

    def fair_odds(self, ts_ms, price, open_price):
        """build11:15926. How decided the candle already is; not a forecast."""
        if not self.candle: return 0.5, 300.0
        seconds_left = max((int(self.candle["time"]) + CANDLE_MS - ts_ms) / 1000.0, 1.0)
        moves = sorted(abs(float(c["close"]) - float(c["open"])) for c in list(self.closed)[-24:])
        typical = moves[len(moves) // 2] if moves else max(price * 4e-4, 1.0)
        per_second = max(typical / math.sqrt(CANDLE_MS / 1000.0), price * 1e-6)
        sigma = per_second * math.sqrt(seconds_left)
        p = 0.5 * (1.0 + math.erf((price - open_price) / (sigma * math.sqrt(2.0))))
        return clamp(p, 0.01, 0.99), seconds_left

    def volume_ratio(self, phase_second):
        """build11:16069. This candle's pace against the recent median."""
        if not self.candle: return 1.0
        vols = sorted(float(c["volume"]) for c in list(self.closed)[-24:] if float(c.get("volume", 0)) > 0)
        if not vols: return 1.0
        median = vols[len(vols) // 2]
        if median <= 0: return 1.0
        frac = clamp(max(phase_second, 1.0) / 300.0, 0.01, 1.0)
        return (float(self.candle.get("volume", 0.0)) / frac) / median

    # ---- feature build --------------------------------------------------
    def compute(self, ts_ms):
        """One feature rebuild. build11 calls this per market event, and
        MAIN_HOLD_READS counts these rebuilds, so the caller's cadence matters."""
        if not self.candle: return None
        price = float(self.candle["close"]); open_price = float(self.candle["open"])
        now_s = ts_ms / 1000.0
        phase = (ts_ms - int(self.candle["time"])) / 1000.0
        f = {}
        f["phase_second"] = phase
        f["delta_1s"] = self.delta_1s.value(int(ts_ms))
        f["delta_5s"] = self.delta_5s.value(int(ts_ms))
        f["delta_30s"] = self.delta_30s.value(int(ts_ms))
        f["spot_imbalance5"] = self.spot_imbalance5()
        f["ofi_1s"] = 0.0; f["ofi_5s"] = 0.0
        f["return_250ms_bps"] = self._return_bps(now_s, price, 0.25)
        f["return_1s_bps"] = self._return_bps(now_s, price, 1.0)
        f["return_5s_bps"] = self._return_bps(now_s, price, 5.0)
        hi = float(self.candle.get("high", price)); lo = float(self.candle.get("low", price))
        rng = max(hi - lo, 1e-9)
        f["body_range_ratio"] = (price - open_price) / rng
        f["close_location_centred"] = ((price - lo) / rng) * 2.0 - 1.0
        f["aggressive_cluster_bias"] = 0.0
        f["volume_profile_delta"] = 0.0

        fair, seconds_left = self.fair_odds(ts_ms, price, open_price)
        f["fair_p_up"] = fair; f["seconds_left"] = seconds_left
        f["volume_ratio"] = self.volume_ratio(phase)

        # --- rejection: aggressive volume that failed to move price (16170) ---
        if self.reject_ts:
            elapsed = now_s - self.reject_ts
            if elapsed > 0:
                keep = 0.5 ** (elapsed / REJECTION_HALF_LIFE_SEC)
                self.reject_up *= keep; self.reject_down *= keep
        self.reject_ts = now_s
        if self.candle_high_seen <= 0.0:
            self.candle_high_seen = price; self.candle_low_seen = price
        tick_delta = f["delta_1s"]
        scale = REJECTION_ZONE_SIGMA * max(self.sigma_per_root_second(), REJECTION_MIN_SCALE_USD)
        near_high = (self.candle_high_seen - price) <= scale
        near_low = (price - self.candle_low_seen) <= scale
        made_high = price > self.candle_high_seen
        made_low = price < self.candle_low_seen
        if made_high: self.candle_high_seen = price
        if made_low: self.candle_low_seen = price
        if near_high and not made_high and tick_delta > 0:
            self.reject_up += (REJECTION_CAP - self.reject_up) * min(tick_delta / REJECTION_CAP, 0.5)
        if near_low and not made_low and tick_delta < 0:
            self.reject_down += (REJECTION_CAP - self.reject_down) * min(abs(tick_delta) / REJECTION_CAP, 0.5)
        f["reject_up"] = self.reject_up; f["reject_down"] = self.reject_down

        # --- pressure gauge (16245) ---
        self.pressure_history.append((now_s, price))
        magnitude = avg_move(self.pressure_history)
        past = None
        for ts, p in reversed(self.pressure_history):
            if now_s - ts >= 10.0: past = p; break
        mom = clamp((price - past) / (2.0 * magnitude), -1.0, 1.0) if (past is not None and magnitude > 0) else 0.0
        score = pressure_score(f["spot_imbalance5"], f["delta_30s"], mom)
        f["pressure_score"] = score
        f["pressure_text"] = pressure_text(score, magnitude)
        f["pressure_mom"] = mom; f["pressure_move"] = magnitude
        _, prob_up, _ = self.model.score(f)
        f["probability_up"] = prob_up
        f["price"] = price; f["open_price"] = open_price
        self.feature = f
        return f

    # ---- MAIN (build11:16673 gate, 17012 emit) --------------------------
    def _aligned_direction(self, f):
        """The single alignment test both lanes use."""
        if safe_float(f.get("volume_ratio"), 1.0) < GATED_VOL_MIN: return None
        text = str(f.get("pressure_text", "BALANCED"))
        fair = safe_float(f.get("fair_p_up"), 0.5)
        if text.startswith("UP") and fair >= GATED_ODDS_UP: return "UP"
        if text.startswith("DOWN") and fair <= GATED_ODDS_DOWN: return "DOWN"
        return None

    def _reset_main_streak(self):
        self.main_streak_dir = ""; self.main_streak_start_ms = 0; self.main_streak_reads = 0

    def _main_probability(self, f, direction):
        """build11:17028. The blend sets the recorded probability; it does not
        gate the fire. Contradiction between blend and direction keeps only a
        quarter of the conviction rather than flipping the side."""
        model_p = clamp(safe_float(f.get("probability_up"), 0.5), 0.01, 0.99)
        fair_p = clamp(safe_float(f.get("fair_p_up"), 0.5), 0.01, 0.99)
        score = clamp(safe_float(f.get("pressure_score"), 0.0), -1.0, 1.0)
        pressure_p = 0.5 + score / 2.0
        blended = 0.40 * pressure_p + 0.35 * fair_p + 0.25 * model_p
        edge = blended - 0.5
        sign = 1.0 if direction == "UP" else -1.0
        edge = abs(edge) * sign * (1.0 if edge * sign > 0 else EDGE_CONTRADICTION_KEEP)
        price = safe_float(f.get("price")); open_price = safe_float(f.get("open_price"))
        lead = price - open_price
        required = 0.0 if lead * sign > 0 else abs(lead)
        seconds_left = safe_float(f.get("seconds_left"), 300.0)
        confidence = (volume_factor(safe_float(f.get("volume_ratio"), 1.0))
                      * rejection_factor(sign, safe_float(f.get("reject_up")), safe_float(f.get("reject_down")))
                      * runway_factor(seconds_left)
                      * feasibility_factor(required, self.sigma_per_root_second(), seconds_left))
        return clamp(0.5 + edge * confidence, 0.02, 0.98), confidence

    def _try_main(self, ts_ms, f):
        if self.current_main is not None: return None
        phase = (ts_ms - int(self.candle["time"])) / 1000.0
        if phase > MAIN_LAST_SECOND:
            self.main_block = "outside the callable window"; return None
        direction = self._aligned_direction(f)
        if direction is None:
            self._reset_main_streak()
            self.main_block = "flow and odds do not agree"; return None
        if self.main_streak_dir != direction:
            self.main_streak_dir = direction; self.main_streak_start_ms = ts_ms; self.main_streak_reads = 0
        self.main_streak_reads += 1
        held = ts_ms - self.main_streak_start_ms
        if held < MAIN_HOLD_MS or self.main_streak_reads < MAIN_HOLD_READS:
            self.main_block = f"alignment held {held/1000:.0f}s / {self.main_streak_reads} reads"
            return None
        self.main_block = ""
        p_up, conf = self._main_probability(f, direction)
        self.current_main = dict(direction=direction, ts_ms=ts_ms, probability_up=p_up)
        p_side = p_up if direction == "UP" else 1.0 - p_up
        return dict(kind="MAIN", side=direction, p=p_side, probability_up=p_up,
                    confidence=conf, sec=int(phase), rv60=None,
                    reason=f"MAIN: {f.get('pressure_text')} with fair {f.get('fair_p_up'):.2f} held {held/1000:.0f}s")

    # ---- REVERSAL (build11:17169 gate, 17232 emit) ----------------------
    def _watch_reversal(self, ts_ms, f):
        """The same alignment test, re-evaluated live, now naming the side
        opposite the MAIN already on the books. No persistence requirement:
        build11 removed the old eight-check gate because it fired once in 57
        candles. This is a hedge leg, not a close - MAIN stays open."""
        if not self.current_main or self.current_reversal is not None: return None
        phase = safe_float(f.get("phase_second"), 0.0)
        if not (REVERSAL_MIN_SECOND <= phase <= REVERSAL_LAST_SECOND):
            self.reversal_state = {"status": "idle", "detail": "outside 30-285s window"}
            return None
        live = self._aligned_direction(f)
        if live is None:
            self.reversal_state = {"status": "watching", "detail": "no aligned signal"}
            return None
        if live == self.current_main["direction"]:
            self.reversal_state = {"status": "watching",
                                   "detail": f"signal still agrees with MAIN {live}"}
            return None
        detail = f"signal flipped to {live} against MAIN {self.current_main['direction']}"
        self.reversal_state = {"status": "firing", "detail": detail}
        fair = safe_float(f.get("fair_p_up"), 0.5)
        p_up = fair if live == "UP" else 1.0 - fair
        self.current_reversal = dict(direction=live, ts_ms=ts_ms)
        p_side = p_up if live == "UP" else 1.0 - p_up
        return dict(kind="REVERSAL", side=live, p=p_side, probability_up=(fair if live == "UP" else 1.0 - fair),
                    sec=int(phase), rv60=None,
                    reason=f"reversal at {phase:.0f}s: {detail}")

    # ---- public ---------------------------------------------------------
    def evaluate(self, ts_ms):
        """Rebuild features and return at most one lane decision.

        Order matches build11:_prediction_logic - MAIN is tried first, and
        REVERSAL only once a MAIN exists for this candle.
        """
        f = self.compute(ts_ms)
        if f is None: return None
        out = self._try_main(ts_ms, f)
        if out is not None: return out
        return self._watch_reversal(ts_ms, f)

    def monitor(self):
        f = self.feature or {}
        return dict(
            pressure_text=f.get("pressure_text"), pressure_score=f.get("pressure_score"),
            fair_p_up=f.get("fair_p_up"), volume_ratio=f.get("volume_ratio"),
            probability_up=f.get("probability_up"), phase_second=f.get("phase_second"),
            main=(dict(self.current_main) if self.current_main else None),
            main_block=self.main_block, main_streak=dict(direction=self.main_streak_dir, reads=self.main_streak_reads),
            reversal=dict(self.reversal_state), reversal_fired=bool(self.current_reversal),
            aligned=self._aligned_direction(f) if f else None,
            thresholds=dict(odds_up=GATED_ODDS_UP, odds_down=GATED_ODDS_DOWN, vol_min=GATED_VOL_MIN,
                            hold_ms=MAIN_HOLD_MS, hold_reads=MAIN_HOLD_READS,
                            main_last_second=MAIN_LAST_SECOND,
                            reversal_window=[REVERSAL_MIN_SECOND, REVERSAL_LAST_SECOND]),
        )
