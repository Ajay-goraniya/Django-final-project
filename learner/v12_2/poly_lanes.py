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
# 12.15.3, port fidelity. build11 medians `list(self.candles)[-24:]` filtered on
# `closed`, and its `candles` deque CONTAINS THE LIVE CANDLE as its last element
# (btc_model_build11.py:15699-15708 updates it in place on every kline). After the
# filter that is 23 closed candles, taking index 11. This port keeps closed candles
# in a separate deque, so `[-24:]` gave 24 and took index 12 - the upper of the two
# middles. Both the move median (fair odds) and the volume median are affected, and
# both are biased the same way: a higher `typical` pulls fair_p_up toward 0.5 and a
# higher volume median lowers volume_ratio, so the port was systematically tighter
# than build 11 on BOTH lane gates, on every candle. Small, free to fix, and it is
# the difference between a port and an approximation.
MEDIAN_WINDOW = 23

REVERSAL_MIN_SECOND = 30.0
REVERSAL_LAST_SECOND = 285.0
# 12.15.5, port fidelity - THE LANES DO NOT USE EF'S EV THRESHOLD. build11's
# _record_trade (btc_model_build11.py:16804-16820) consults may_execute (the
# switches and halts) and, for REVERSAL only, an optional maximum entry PRICE cap
# `v11_rev_max_entry` (default 0.0 = off). There is no EV gate, no model-p-versus-
# price test, for either lane. This port handed every lane decision EF's v10
# regime threshold (0.15/0.25) and order_plan refused on it - so REVERSAL on
# Polymarket faced a rule it was never designed to clear, and two of its first
# four post-fix signals died to it. The owner: "reversal is different thing and it
# has different parameters." These are them. The one thing kept is the
# fee-inclusive breakeven (threshold 0.0 = p must beat cost), because build11's
# venue has no fee model and this one does; a lane buying a price it cannot beat
# even when right is not a strategy difference, it is a loss.
LANE_EV_FLOOR = 0.0          # breakeven only; EF's regime table does not apply
REV_MAX_ENTRY_DEFAULT = 0.0  # build11 v11_rev_max_entry default: no cap
# 12.18.0: a lane's p is RECORDED, not a price gate (build11:17028 - "the blend sets
# the recorded probability; it does not gate the fire"). v11's own MAIN fired with
# p(side) at or below the quote on 58 of 73 calls (owner's 09-21 export) and was
# right 85%. Routing MAIN/REVERSAL through EF's `p/cost-1 >= threshold` test refused
# 86 of 101 MAIN plans on the Zurich paper lane in its first 45 minutes ON
# ("price fails model EV", asks 0.60-0.98, p ~0.75). The lane's only price control
# is a maximum entry: above LANE_MAX_ASK the payout cannot cover the fee at the hit
# rates seen (v11 MAIN priced on Polymarket: hit 86% at ask 0.72, 100% at 0.83,
# n=65/17). An economics floor, not a signal gate: grid it on paper, do not tune it.
LANE_MAX_ASK = 0.90

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


class RollingSignedMean:
    """Rolling mean of already-normalised signed values, used for OFI (build11:4393)."""
    def __init__(self, window_ms):
        self.window_ms = int(window_ms); self.items = deque(); self.total = 0.0
    def add(self, ts_ms, value):
        self.items.append((ts_ms, value)); self.total += value; self.prune(ts_ms)
    def prune(self, ts_ms):
        cutoff = ts_ms - self.window_ms
        while self.items and self.items[0][0] < cutoff:
            _, v = self.items.popleft(); self.total -= v
    def value(self, ts_ms):
        self.prune(ts_ms)
        return self.total / len(self.items) if self.items else 0.0


# 12.15.4, port fidelity (build11:555-561). Four of the thirteen weighted MAIN
# features - ofi_1s (0.85), ofi_5s (0.60), aggressive_cluster_bias (0.25) and
# volume_profile_delta (0.35) - were hardcoded to 0.0 in this port, so the score
# the lane actually ran was not the declared 13-feature score: 2.05 of 8.75
# total anchor weight was permanently silent. All four are now computed exactly
# as build11 computes them, from the same inputs the port already receives.
OFI_QUOTE_SCALE = 1_000.0     # OFI is reported in thousands of USD
CLUSTER_WINDOW = 300          # depth samples kept for the mean/sigma estimate
CLUSTER_MIN_SAMPLES = 30      # below this the z-score is reported as zero
CLUSTER_SIGMA = 2.0           # a spike must exceed mean + 2 sigma
CLUSTER_SIGMA_FLOOR = 0.01


def quote_ofi(previous, current):
    """build11:15730. Signed change of top-of-book quote value, in $thousands.
    Classic OFI accounting on price and size, valued in quote currency and
    deliberately NOT divided by resting depth."""
    pbp, pbq, pap, paq = previous
    cbp, cbq, cap, caq = current
    if cbp > pbp: bid_term = cbq * cbp
    elif cbp == pbp: bid_term = (cbq - pbq) * cbp
    else: bid_term = -pbq * pbp
    if cap < pap: ask_term = caq * cap
    elif cap == pap: ask_term = (caq - paq) * cap
    else: ask_term = -paq * pap
    return (bid_term - ask_term) / OFI_QUOTE_SCALE


def cluster_z(history, value):
    """build11:15767. Excess z-score of `value`; zero unless it clears CLUSTER_SIGMA."""
    count = len(history)
    if count < CLUSTER_MIN_SAMPLES: return 0.0
    mean = sum(history) / count
    variance = sum((item - mean) ** 2 for item in history) / count
    sigma = max(math.sqrt(variance), abs(mean) * CLUSTER_SIGMA_FLOOR)
    if sigma <= 1e-9: return 0.0
    z = (value - mean) / sigma
    return clamp(z, 0.0, 8.0) if z >= CLUSTER_SIGMA else 0.0


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



# ---- 12.16.0: build 11's adapt_ratio (btc_model_build11.py:863-877, :15805-15958) ----
# Fast (3 min) over slow (1 h) robust RMS of one-second log returns, winsorised,
# with an identity band so ordinary variation leaves fair odds exactly as before.
# It scales `typical` in fair_odds (build11:15976, :16062): when the last minutes
# are moving faster than the last hour the 23-candle median lags the onset and
# fair_p_up over-states how decided the candle is; the ratio bridges that.
ADAPT_ENABLED = True
ADAPT_BUCKET_MS = 1_000
ADAPT_FAST_SEC = 180
ADAPT_SLOW_SEC = 3_600
ADAPT_MIN_FAST = 60
ADAPT_MIN_SLOW = 600
ADAPT_RATIO_LO = 0.30
ADAPT_RATIO_HI = 6.00
ADAPT_IDENTITY_LO = 0.85
ADAPT_IDENTITY_HI = 1.15
ADAPT_FULL_LO = 0.67
ADAPT_FULL_HI = 1.50
ADAPT_WINSOR_SIGMAS = 5.0
ADAPT_MIN_ACTIVE_SHARE = 0.10
ADAPT_STALE_BUCKETS = 5


def _robust_rms(values, minimum):
    """build11:4485-4519. Winsorised RMS; 0.0 until `minimum` returns exist."""
    n = len(values)
    if n < minimum: return 0.0
    mags = sorted(abs(v) for v in values)
    median_abs = mags[n // 2]
    if median_abs <= 0.0:
        pos = [m for m in mags if m > 0.0]
        if len(pos) < max(8, int(math.ceil(n * ADAPT_MIN_ACTIVE_SHARE))): return 0.0
        median_abs = pos[len(pos) // 2]
    cap = ADAPT_WINSOR_SIGMAS * 1.4826 * median_abs
    return math.sqrt(sum(min(m, cap) ** 2 for m in mags) / n)


def engaged_adapt_ratio(raw):
    """build11:15919. Identity inside the band, log-linear ramp to full outside it."""
    raw = clamp(raw, ADAPT_RATIO_LO, ADAPT_RATIO_HI)
    if ADAPT_IDENTITY_LO <= raw <= ADAPT_IDENTITY_HI: return 1.0
    if raw > ADAPT_IDENTITY_HI:
        width = math.log(ADAPT_FULL_HI) - math.log(ADAPT_IDENTITY_HI)
        eng = clamp((math.log(raw) - math.log(ADAPT_IDENTITY_HI)) / width, 0.0, 1.0)
    else:
        width = math.log(ADAPT_IDENTITY_LO) - math.log(ADAPT_FULL_LO)
        eng = clamp((math.log(ADAPT_IDENTITY_LO) - math.log(raw)) / width, 0.0, 1.0)
    return math.exp(math.log(raw) * eng)


class AdaptRatio:
    """build11:15805-15958 on one deque. Causal: a second's close is only known
    once a later second arrives. A gap over ADAPT_STALE_BUCKETS breaks the return
    chain and drops the factor to 1.0 rather than turning the gap into a move."""
    def __init__(self):
        self.returns = deque(maxlen=ADAPT_SLOW_SEC + 600)   # (bucket, r)
        self.bucket = None; self.bucket_close = 0.0
        self.done_bucket = None; self.done_close = 0.0
        self.raw = 1.0; self.cache = 1.0

    def add(self, ts_ms, price):
        if price <= 0.0 or not math.isfinite(price): return
        b = int(ts_ms) // ADAPT_BUCKET_MS
        if self.bucket is not None and b < self.bucket: return
        if self.bucket is None: self.bucket = b; self.bucket_close = price; return
        if b == self.bucket: self.bucket_close = price; return
        if b - self.bucket > ADAPT_STALE_BUCKETS: self.raw = self.cache = 1.0
        cb, cc = self.bucket, self.bucket_close
        appended = False
        if self.done_bucket is not None and self.done_close > 0.0:
            gap = cb - self.done_bucket
            if 0 < gap <= ADAPT_STALE_BUCKETS:
                r = math.log(cc / self.done_close) / math.sqrt(float(gap))
                if math.isfinite(r): self.returns.append((cb, r)); appended = True
            elif gap > ADAPT_STALE_BUCKETS: self.raw = self.cache = 1.0
        self.done_bucket, self.done_close = cb, cc
        self.bucket, self.bucket_close = b, price
        if appended: self.refresh()

    def _window(self, seconds):
        if not self.returns: return []
        cut = self.returns[-1][0] - seconds
        return [r for b, r in self.returns if b >= cut]

    def refresh(self):
        fast = _robust_rms(self._window(ADAPT_FAST_SEC), ADAPT_MIN_FAST)
        slow = _robust_rms(self._window(ADAPT_SLOW_SEC), ADAPT_MIN_SLOW)
        if fast <= 0.0 or slow <= 0.0: self.raw = self.cache = 1.0; return
        self.raw = clamp(fast / slow, ADAPT_RATIO_LO, ADAPT_RATIO_HI)
        self.cache = engaged_adapt_ratio(self.raw)

    def value(self):
        return self.cache if ADAPT_ENABLED else 1.0

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
        # 12.15.4: the four previously-zeroed inputs (build11:14527, :14610-14616)
        self.ofi_1s = RollingSignedMean(1_000)
        self.ofi_5s = RollingSignedMean(5_000)
        self.previous_top = None
        self.bid_volume_history = deque(maxlen=CLUSTER_WINDOW)
        self.ask_volume_history = deque(maxlen=CLUSTER_WINDOW)
        self.aggressive_bid_cluster = 0.0; self.aggressive_ask_cluster = 0.0
        self.candle_buy_quote = 0.0; self.candle_sell_quote = 0.0
        self.pressure_history = deque(maxlen=PRESSURE_HISTORY)
        self.price_history = deque(maxlen=4000)      # (ts_s, price) for returns
        self.adapt = AdaptRatio()                     # 12.16.0
        self.depth = {"bids": [], "asks": []}
        self.candle = None
        self.closed = deque(maxlen=64)
        self.feature = {}
        self.reject_up = 0.0; self.reject_down = 0.0; self.reject_ts = 0.0
        self.candle_high_seen = 0.0; self.candle_low_seen = 0.0
        # A signal is not a position. current_main is set only once an order has
        # actually been placed; main_signal records that the lane called the
        # candle whether or not it could be bought. v12.2.3 conflated the two, so
        # a MAIN refused by the EV guard still showed on the dashboard as though
        # it had traded, and still consumed the candle so it could never retry.
        self.current_main = None      # a REAL position: {'direction','ts_ms','probability_up'}
        self.main_signal = None       # the call, executed or not
        self.main_attempts = 0
        self.main_last_reason = ''
        self.current_reversal = None  # a REAL hedge position
        self.reversal_signal = None   # the call, executed or not
        self.reversal_attempts = 0
        # A decision is outstanding between being returned and the engine saying
        # what happened to it. Without this the lane would call the same candle
        # again on the very next evaluation.
        self.pending = {'MAIN': False, 'REVERSAL': False}
        self.main_streak_dir = ""; self.main_streak_start_ms = 0; self.main_streak_reads = 0
        self.main_block = ""; self.reversal_state = {"status": "idle", "detail": ""}
        self._candle_id = None

    # ---- inputs ---------------------------------------------------------
    def on_spot_trade(self, ts_ms, price, qty, is_buyer_maker):
        signed = price * qty * (-1.0 if is_buyer_maker else 1.0)
        for d in (self.delta_1s, self.delta_5s, self.delta_30s):
            d.add(int(ts_ms), signed)
        if signed >= 0.0: self.candle_buy_quote += price * qty
        else: self.candle_sell_quote += price * qty
        self.price_history.append((ts_ms / 1000.0, price))
        self.adapt.add(ts_ms, price)

    def on_depth(self, bids, asks, ts_ms=None):
        self.depth = {"bids": bids, "asks": asks}
        if not bids or not asks: return
        ts = int(ts_ms if ts_ms is not None else time.time() * 1000)
        current_top = (float(bids[0][0]), float(bids[0][1]), float(asks[0][0]), float(asks[0][1]))
        if self.previous_top is not None:
            v = quote_ofi(self.previous_top, current_top)
            self.ofi_1s.add(ts, v); self.ofi_5s.add(ts, v)
        self.previous_top = current_top
        bid_quote = sum(float(p) * float(q) for p, q in bids[:5])
        ask_quote = sum(float(p) * float(q) for p, q in asks[:5])
        self.aggressive_bid_cluster = cluster_z(self.bid_volume_history, bid_quote)
        self.aggressive_ask_cluster = cluster_z(self.ask_volume_history, ask_quote)
        self.bid_volume_history.append(bid_quote); self.ask_volume_history.append(ask_quote)

    def on_candle(self, candle):
        cid = int(candle["time"])
        if self._candle_id is not None and cid != self._candle_id:
            # New candle: MAIN/REVERSAL are once per candle, and the rejection
            # extremes are per-candle state (build11 resets them the same way).
            self.current_main = None; self.current_reversal = None
            self.main_signal = None; self.main_attempts = 0; self.main_last_reason = ''
            self.reversal_signal = None; self.reversal_attempts = 0
            self.pending = {'MAIN': False, 'REVERSAL': False}
            self.main_streak_dir = ""; self.main_streak_start_ms = 0; self.main_streak_reads = 0
            self.reject_up = self.reject_down = 0.0
            self.candle_high_seen = self.candle_low_seen = 0.0
            self.candle_buy_quote = 0.0; self.candle_sell_quote = 0.0
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
        moves = sorted(abs(float(c["close"]) - float(c["open"])) for c in list(self.closed)[-MEDIAN_WINDOW:])
        typical = (moves[len(moves) // 2] * self.adapt.value()) if moves else max(price * 4e-4, 1.0)
        per_second = max(typical / math.sqrt(CANDLE_MS / 1000.0), price * 1e-6)
        sigma = per_second * math.sqrt(seconds_left)
        p = 0.5 * (1.0 + math.erf((price - open_price) / (sigma * math.sqrt(2.0))))
        return clamp(p, 0.01, 0.99), seconds_left

    def volume_ratio(self, phase_second):
        """build11:16069. This candle's pace against the recent median."""
        if not self.candle: return 1.0
        vols = sorted(float(c["volume"]) for c in list(self.closed)[-MEDIAN_WINDOW:] if float(c.get("volume", 0)) > 0)
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
        f["ofi_1s"] = self.ofi_1s.value(int(ts_ms)); f["ofi_5s"] = self.ofi_5s.value(int(ts_ms))
        f["return_250ms_bps"] = self._return_bps(now_s, price, 0.25)
        f["return_1s_bps"] = self._return_bps(now_s, price, 1.0)
        f["return_5s_bps"] = self._return_bps(now_s, price, 5.0)
        hi = float(self.candle.get("high", price)); lo = float(self.candle.get("low", price))
        rng = max(hi - lo, 1e-9)
        f["body_range_ratio"] = (price - open_price) / rng
        f["close_location_centred"] = ((price - lo) / rng) * 2.0 - 1.0
        f["aggressive_cluster_bias"] = self.aggressive_bid_cluster - self.aggressive_ask_cluster
        aggressive_volume = self.candle_buy_quote + self.candle_sell_quote
        f["volume_profile_delta"] = ((self.candle_buy_quote - self.candle_sell_quote) / aggressive_volume
                                     if aggressive_volume > 0.0 else 0.0)

        fair, seconds_left = self.fair_odds(ts_ms, price, open_price)
        f["fair_p_up"] = fair; f["seconds_left"] = seconds_left; f["adapt_ratio"] = self.adapt.value()
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

    # 12.15.3: was 6 against poly_core's MAX_ATTEMPTS_PER_CANDLE of 4. The journal
    # stops re-arming the candle at 4, so attempts 5 and 6 could never reach the
    # venue: fire() returned at `not self.db.reserve(...)` with no status write, the
    # caller read back the stale prior status, and the lane counted a silent no-op
    # against its own retry budget. Two caps for one thing is one cap too many.
    MAIN_MAX_ATTEMPTS = 4
    def confirm(self, kind, placed, reason=''):
        """Told by the engine what actually happened to the order.

        Placed means the venue has it. Refused means the signal stands but the
        price was not payable, so the lane keeps watching and may fire again in
        the same candle if the book improves. Attempts are capped so a signal
        that is never payable cannot retry all candle.
        """
        self.pending[kind] = False
        if kind == 'MAIN':
            self.main_last_reason = reason or ''
            if placed and self.main_signal:
                # 12.15.3: `dict(self.main_signal or {})` could set current_main to
                # {} - falsy but `is not None` - and this file tests it both ways:
                # `is not None` at the MAIN once-per-candle guard (would kill the
                # lane), `or` at the REVERSAL reference (would fall through), and
                # `is not None` again for `main_placed` (would claim a position that
                # does not exist). Four sites, two truth tests, inconsistent answers.
                # A placed MAIN with no signal is not a position; keep the guard.
                self.current_main = dict(self.main_signal)
            elif not placed:
                self.main_attempts += 1
        elif kind == 'REVERSAL':
            if placed:
                self.current_reversal = dict(self.reversal_signal or {})
            else:
                # A refused REVERSAL is simply not a hedge. The call stands and
                # may be retried while the flip holds and the window is open.
                self.reversal_attempts += 1

    def _try_main(self, ts_ms, f):
        # A placed position ends the candle for this lane. A refused one does not,
        # until the attempt cap is reached.
        if self.current_main is not None or self.pending.get('MAIN'): return None
        if self.main_attempts >= self.MAIN_MAX_ATTEMPTS:
            self.main_block = f'not payable after {self.main_attempts} attempts'
            return None
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
        self.main_signal = dict(direction=direction, ts_ms=ts_ms, probability_up=p_up)
        self.pending['MAIN'] = True
        p_side = p_up if direction == "UP" else 1.0 - p_up
        return dict(kind="MAIN", side=direction, p=p_side, probability_up=p_up,
                    confidence=conf, sec=int(phase), rv60=None, adapt_ratio=self.adapt.value(), threshold=LANE_EV_FLOOR,
                    price_rule='lane_cap', max_ask=LANE_MAX_ASK,
                    reason=f"MAIN:{f.get('pressure_text')} with fair {f.get('fair_p_up'):.2f} held {held/1000:.0f}s")

    # ---- REVERSAL (build11:17169 gate, 17232 emit) ----------------------
    def _watch_reversal(self, ts_ms, f):
        """The same alignment test, re-evaluated live, now naming the side
        opposite the MAIN already on the books. No persistence requirement:
        build11 removed the old eight-check gate because it fired once in 57
        candles. This is a hedge leg, not a close - MAIN stays open."""
        # 12.14.0: REVERSAL watches the MAIN *call*, not the MAIN *order*.
        #
        # This port had it the other way ("a refused MAIN is nothing to hedge"),
        # and that was a deviation from build11 dressed up as prudence. Read
        # build11 itself: btc_model_build11.py:17151 sets current_main the moment
        # store.add_prediction succeeds - the prediction, not a fill - and
        # _record_trade only consults controls.may_execute(kind) AFTERWARDS, at
        # 16804, to decide whether an order goes out. So on the Tokyo box with
        # MAIN switched OFF the MAIN prediction is still made, current_main is
        # still set, and REVERSAL at 17209 still fires. The owner's 09-16
        # screenshot is exactly that: MAIN BLOCKED, EF BLOCKED, REVERSAL TRADING,
        # runtime 5d - and it is the configuration that earns there.
        #
        # Under the old rule, MAIN off meant current_main never set, so REVERSAL
        # returned None on every candle forever. EF+REV without MAIN orders was
        # not expressible, which is why Task 113 had to arm MAIN as well.
        #
        # Yes, a REVERSAL on an unplaced MAIN is an outright position. That is
        # what build11 does and what the live Predict lane has been doing for
        # five days; naming it honestly is the fix, refusing to port it was not.
        main = self.current_main or self.main_signal
        if not main or self.current_reversal is not None: return None
        if self.pending.get('REVERSAL'): return None
        if self.reversal_attempts >= self.MAIN_MAX_ATTEMPTS:
            self.reversal_state = {"status": "watching", "detail": "hedge not payable"}
            return None
        phase = safe_float(f.get("phase_second"), 0.0)
        if not (REVERSAL_MIN_SECOND <= phase <= REVERSAL_LAST_SECOND):
            self.reversal_state = {"status": "idle", "detail": "outside 30-285s window"}
            return None
        live = self._aligned_direction(f)
        if live is None:
            self.reversal_state = {"status": "watching", "detail": "no aligned signal"}
            return None
        if live == main["direction"]:
            self.reversal_state = {"status": "watching",
                                   "detail": f"signal still agrees with MAIN {live}"}
            return None
        placed = self.current_main is not None
        detail = (f"signal flipped to {live} against MAIN {main['direction']}"
                  + ("" if placed else " (call only - MAIN order not placed)"))
        self.reversal_state = {"status": "firing", "detail": detail}
        # 12.15.0: this flipped the probability TWICE and so handed order_plan the
        # probability of the side it was NOT buying.
        #
        #   fair  = P(UP)
        #   p_up  = fair if UP else 1-fair      <- already the SIDE's probability,
        #                                          despite the name
        #   p_side = p_up if UP else 1-p_up     <- flipped again: back to P(UP)
        #
        # Verified on the running module: a DOWN reversal with fair_p_up 0.0100
        # was handed p=0.0100 when P(DOWN) was 0.9900, and reported
        # probability_up=0.9900 when P(UP) was 0.0100. Both fields exactly swapped.
        # _aligned_direction only names DOWN when fair_p_up <= GATED_ODDS_DOWN
        # (0.40), so the p reaching the EV gate was always <= 0.40 against a DOWN
        # ask around 0.60 - EV about -0.35. DOWN REVERSAL COULD NEVER FIRE, and it
        # failed as "price fails model EV", which reads as a pricing problem. MAIN
        # at line 476 flips once and has always been correct, so this was a
        # deviation in this function and not a house convention.
        fair = safe_float(f.get("fair_p_up"), 0.5)
        p_side = fair if live == "UP" else 1.0 - fair
        self.reversal_signal = dict(direction=live, ts_ms=ts_ms)
        self.pending['REVERSAL'] = True
        return dict(kind="REVERSAL", side=live, p=p_side, probability_up=fair,
                    sec=int(phase), rv60=None, adapt_ratio=self.adapt.value(), threshold=LANE_EV_FLOOR,
                    price_rule='lane_cap', max_ask=LANE_MAX_ASK,
                    reason=f"reversal at {phase:.0f}s: {detail}")

    # ---- public ---------------------------------------------------------
    def still_valid(self, kind, side, ts_ms):
        """12.15.4: is a decision the lane returned earlier STILL the call, now?

        EF re-runs decide_now() inside the executor's retry loop, so a signal that
        has gone stale between decide and submit is caught. MAIN and REVERSAL
        handed the executor a lambda returning the ORIGINAL frozen dict, so a
        lane's p was held constant against a moving book across up to four
        attempts and two seconds, and a signal the market had already reversed
        could still be submitted. This recomputes the features and re-applies the
        same alignment test the lane fired on, without touching pending or any
        per-candle state - it is a read, not a second call.
        """
        f = self.compute(int(ts_ms))
        if f is None: return False
        live = self._aligned_direction(f)
        if kind == 'MAIN':
            return live == side
        if kind == 'REVERSAL':
            main = self.current_main or self.main_signal
            return bool(main) and live == side and live != main.get('direction')
        return True

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
            fair_p_up=f.get("fair_p_up"), volume_ratio=f.get("volume_ratio"), adapt_ratio=self.adapt.value(),
            probability_up=f.get("probability_up"), phase_second=f.get("phase_second"),
            main=(dict(self.current_main) if self.current_main else None),
            main_signal=(dict(self.main_signal) if self.main_signal else None),
            main_placed=bool(self.current_main),
            main_attempts=self.main_attempts, main_last_reason=self.main_last_reason,
            main_block=self.main_block, main_streak=dict(direction=self.main_streak_dir, reads=self.main_streak_reads),
            reversal=dict(self.reversal_state,
                          direction=(self.current_reversal or {}).get('direction')),
            reversal_fired=bool(self.current_reversal),
            reversal_signal=(dict(self.reversal_signal) if self.reversal_signal else None),
            reversal_placed=bool(self.current_reversal), reversal_attempts=self.reversal_attempts,
            pending=dict(self.pending),
            aligned=self._aligned_direction(f) if f else None,
            thresholds=dict(odds_up=GATED_ODDS_UP, odds_down=GATED_ODDS_DOWN, vol_min=GATED_VOL_MIN,
                            hold_ms=MAIN_HOLD_MS, hold_reads=MAIN_HOLD_READS,
                            main_last_second=MAIN_LAST_SECOND, lane_max_ask=LANE_MAX_ASK,
                            reversal_window=[REVERSAL_MIN_SECOND, REVERSAL_LAST_SECOND]),
        )
