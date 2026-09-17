"""Causal fast/slow volatility state shared by EF and MAIN/REVERSAL.

The tracker uses one-second closes, not trade-count-weighted samples.  Fast
volatility is a robust RMS over ~3 minutes; slow volatility is the same measure
over ~1 hour.  Their ratio measures a *transition* in volatility, not an
absolute LOW/MID/HIGH label.

A stale gap breaks the fast segment so pre-gap observations cannot make the
adapter immediately re-engage.  The slow history is retained as a baseline.

Closed 5-minute candles may seed a slow-volatility prior for lane startup.
That prior is only used while the one-second slow window is still warming and
is gradually replaced by observed one-second returns.
"""
import math
from collections import deque

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

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def _robust_rms(values, minimum):
    """Winsorised RMS of log returns.  Returns 0 until `minimum` values exist."""
    n = len(values)
    if n < minimum:
        return 0.0
    mags = sorted(abs(float(v)) for v in values if math.isfinite(float(v)))
    n = len(mags)
    if n < minimum:
        return 0.0
    median_abs = mags[n // 2]
    if median_abs <= 0.0:
        pos = [m for m in mags if m > 0.0]
        if len(pos) < max(8, int(math.ceil(n * ADAPT_MIN_ACTIVE_SHARE))):
            return 0.0
        median_abs = pos[len(pos) // 2]
    cap = ADAPT_WINSOR_SIGMAS * 1.4826 * median_abs
    if cap <= 0.0:
        return 0.0
    return math.sqrt(sum(min(m, cap) ** 2 for m in mags) / n)

def engaged_adapt_ratio(raw):
    """Identity around 1, then a smooth log-linear ramp to the measured ratio."""
    raw = clamp(float(raw), ADAPT_RATIO_LO, ADAPT_RATIO_HI)
    if ADAPT_IDENTITY_LO <= raw <= ADAPT_IDENTITY_HI:
        return 1.0
    if raw > ADAPT_IDENTITY_HI:
        width = math.log(ADAPT_FULL_HI) - math.log(ADAPT_IDENTITY_HI)
        eng = clamp((math.log(raw) - math.log(ADAPT_IDENTITY_HI)) / width, 0.0, 1.0)
    else:
        width = math.log(ADAPT_IDENTITY_LO) - math.log(ADAPT_FULL_LO)
        eng = clamp((math.log(ADAPT_IDENTITY_LO) - math.log(raw)) / width, 0.0, 1.0)
    return math.exp(math.log(raw) * eng)

class AdaptRatio:
    """Causal fast/slow realized-volatility ratio on one-second closes.

    `value()` is the engaged ratio used by strategies.  `raw` is fast/slow
    before the identity ramp.  The stale-gap rule deliberately resets the
    engaged value to 1.0 and starts a fresh FAST segment; it does not erase the
    slower baseline.
    """
    def __init__(self):
        self.returns = deque(maxlen=ADAPT_SLOW_SEC + 600)  # (bucket, log-return/root-second)
        self.bucket = None
        self.bucket_close = 0.0
        self.done_bucket = None
        self.done_close = 0.0
        self.segment_start = None
        self.raw = 1.0
        self.cache = 1.0
        self.fast_rms = 0.0
        self.slow_rms = 0.0
        self.fast_count = 0
        self.slow_count = 0
        self.prior_slow_rms = 0.0
        self.prior_candles = 0
        self.ready = False

    def reset_fast(self, new_segment_bucket=None):
        """Reset only transition state; keep the one-hour history as a baseline."""
        self.raw = self.cache = 1.0
        self.fast_rms = 0.0
        self.fast_count = 0
        self.ready = False
        if new_segment_bucket is not None:
            self.segment_start = int(new_segment_bucket)

    def add(self, ts_ms, price):
        try:
            price = float(price)
            b = int(ts_ms) // ADAPT_BUCKET_MS
        except Exception:
            return
        if price <= 0.0 or not math.isfinite(price):
            return
        if self.bucket is not None and b < self.bucket:
            return
        if self.bucket is None:
            self.bucket = b
            self.bucket_close = price
            self.segment_start = b
            return
        if b == self.bucket:
            self.bucket_close = price
            return

        incoming_gap = b - self.bucket
        stale_incoming = incoming_gap > ADAPT_STALE_BUCKETS
        if stale_incoming:
            # Important: do this before finalising the old bucket and do NOT
            # refresh from the pre-gap return.  The old implementation reset
            # here and then immediately overwrote the reset with refresh().
            self.reset_fast(new_segment_bucket=b)

        cb, cc = self.bucket, self.bucket_close
        appended = False
        if self.done_bucket is not None and self.done_close > 0.0:
            gap = cb - self.done_bucket
            if 0 < gap <= ADAPT_STALE_BUCKETS:
                r = math.log(cc / self.done_close) / math.sqrt(float(gap))
                if math.isfinite(r):
                    self.returns.append((cb, r))
                    appended = True
            elif gap > ADAPT_STALE_BUCKETS:
                self.reset_fast(new_segment_bucket=b)

        self.done_bucket, self.done_close = cb, cc
        self.bucket, self.bucket_close = b, price

        if appended and not stale_incoming:
            self.refresh()

    def _window(self, seconds, *, current_segment=False):
        if not self.returns:
            return []
        last = self.returns[-1][0]
        cut = last - int(seconds)
        seg = self.segment_start if current_segment else None
        return [r for b, r in self.returns if b >= cut and (seg is None or b >= seg)]

    def seed_slow_from_candles(self, candles):
        """Seed a one-hour volatility prior from closed 5-minute OHLC candles.

        Uses Parkinson's high/low estimator, expressed as log-volatility per
        sqrt(second), so it is dimensionally compatible with one-second returns.
        The median makes a single candle spike unable to dominate startup.
        """
        vals = []
        try:
            rows = list(candles)[-24:]
        except Exception:
            rows = []
        for c in rows:
            try:
                h = float(c["high"]); l = float(c["low"])
                if not (math.isfinite(h) and math.isfinite(l) and h > l > 0.0):
                    continue
                log_range = math.log(h / l)
                sigma = log_range / math.sqrt(4.0 * math.log(2.0) * 300.0)
                if math.isfinite(sigma) and sigma > 0.0:
                    vals.append(sigma)
            except Exception:
                continue
        if vals:
            vals.sort()
            self.prior_slow_rms = vals[len(vals)//2]
            self.prior_candles = len(vals)
        return self.prior_slow_rms

    def refresh(self):
        fast_vals = self._window(ADAPT_FAST_SEC, current_segment=True)
        slow_vals = self._window(ADAPT_SLOW_SEC, current_segment=False)
        self.fast_count = len(fast_vals)
        self.slow_count = len(slow_vals)

        fast = _robust_rms(fast_vals, ADAPT_MIN_FAST)
        slow = _robust_rms(slow_vals, ADAPT_MIN_SLOW)

        # During startup, a seeded 5-minute OHLC prior prevents MAIN/REVERSAL
        # from being blind for ten minutes.  Replace it smoothly as one-second
        # observations accumulate.  EF already has a ten-minute warmup gate,
        # but using the same state keeps both paths consistent.
        if fast > 0.0 and slow <= 0.0 and self.prior_slow_rms > 0.0:
            partial = _robust_rms(slow_vals, min(ADAPT_MIN_FAST, len(slow_vals))) if slow_vals else 0.0
            if partial > 0.0:
                w = clamp(len(slow_vals) / float(ADAPT_MIN_SLOW), 0.0, 1.0)
                slow = math.sqrt(w * partial * partial + (1.0 - w) * self.prior_slow_rms * self.prior_slow_rms)
            else:
                slow = self.prior_slow_rms

        self.fast_rms = fast
        self.slow_rms = slow
        if fast <= 0.0 or slow <= 0.0:
            self.raw = self.cache = 1.0
            self.ready = False
            return
        self.raw = clamp(fast / slow, ADAPT_RATIO_LO, ADAPT_RATIO_HI)
        self.cache = engaged_adapt_ratio(self.raw)
        self.ready = True

    def value(self):
        return self.cache if ADAPT_ENABLED else 1.0

    def metrics(self):
        return dict(
            raw=float(self.raw),
            ratio=float(self.value()),
            fast_rms=float(self.fast_rms),
            slow_rms=float(self.slow_rms),
            fast_count=int(self.fast_count),
            slow_count=int(self.slow_count),
            prior_slow_rms=float(self.prior_slow_rms),
            prior_candles=int(self.prior_candles),
            ready=bool(self.ready),
        )
