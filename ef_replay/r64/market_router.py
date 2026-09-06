#!/usr/bin/env python3
"""
market_router.py -- the EXTERNAL 3-bucket static market router supplied by GPT-5.6 Sol
(R6.4 STATIC MARKET ROUTER, 1200-candle frozen validation, 2026-09-06).

It is external to EF. Its only authority is to select one of three FROZEN six-number
threshold presets for r6.4's Early-EF gate. No learner, no online clustering, no EF change.

CAUSALITY: every router input is computed from CLOSED 5-minute candles strictly BEFORE the
candle being traded. The router state is fixed for the whole of a candle and is decided at
that candle's open from history alone.

SCALER NOTE (stated because it matters): Sol supplied the three centroids but not the
StandardScaler fitted during synthetic development. Two frozen, Aug-1-blind normalisations are
therefore implemented and BOTH are reported:
  A (primary)   per-feature standardisation using the mean/std OF THE THREE SUPPLIED CENTROIDS.
                Derived only from Sol's numbers; uses no replay data at all.
  B (sensitivity) expanding causal z-score of the live features (past candles only), with the
                centroids standardised the same way.
No preset number is altered under either mode.
"""
import numpy as np

FEATURES = ("rv_ratio", "eff", "wick", "crosses", "persistence", "absret", "activity_ratio")

# --- Sol's frozen development-state centroid means (section 6 of the handoff) ---
CENTROIDS = np.array([
    [0.958, 0.256, 0.541, 3.699, 0.295, 0.610, 0.960],   # bucket 0 chop / range-like
    [0.963, 0.617, 0.233, 1.214, 0.330, 0.864, 0.979],   # bucket 1 clean / trend-like
    [1.525, 0.420, 0.387, 2.151, 0.280, 0.730, 1.535],   # bucket 2 fast / expansion-like
])

# --- Sol's frozen six-number presets, verbatim ---
PRESETS = {
    0: dict(reach=0.4615913066, control=0.4020830019, settlement=0.4669857019,
            quality=0.4050821172, chop=0.8939130756, score=0.5298997543),
    1: dict(reach=0.3506519544, control=0.3539356981, settlement=0.5486660651,
            quality=0.5279217934, chop=0.8997420804, score=0.5960210648),
    2: dict(reach=0.4251309237, control=0.5013739592, settlement=0.4044831510,
            quality=0.4721038758, chop=0.8787401212, score=0.6217909853),
}
BUCKET_NAMES = {0: "CHOP/RANGE", 1: "CLEAN/TREND", 2: "FAST/EXPANSION"}

# r6.4 baseline (static run uses exactly these; they are the file's own values)
STATIC = dict(reach=0.380, control=0.440, settlement=0.480, quality=0.510, chop=0.880, score=0.535)

_C_MEAN = CENTROIDS.mean(axis=0)
_C_STD = np.where(CENTROIDS.std(axis=0) > 1e-9, CENTROIDS.std(axis=0), 1.0)
_C_Z = (CENTROIDS - _C_MEAN) / _C_STD

FAST, SLOW = 6, 36          # 30 minutes and 3 hours of 5-minute candles


class MarketRouter:
    """Feed closed candles in order; ask for the bucket of the NEXT candle."""

    def __init__(self):
        self.o = []; self.h = []; self.l = []; self.c = []; self.v = []
        self._hist = []                      # past feature vectors, for mode B only

    def add_closed_candle(self, o, h, l, c, v):
        self.o.append(float(o)); self.h.append(float(h)); self.l.append(float(l))
        self.c.append(float(c)); self.v.append(float(v))

    def ready(self):
        return len(self.c) >= SLOW + 1

    def features(self):
        """The seven router inputs, from closed candles only. All unit-free."""
        if not self.ready():
            return None
        c = np.array(self.c); o = np.array(self.o); h = np.array(self.h); l = np.array(self.l); v = np.array(self.v)
        ret = np.diff(np.log(c))
        rf = ret[-FAST:]; rs = ret[-SLOW:]
        rv_fast = float(rf.std()); rv_slow = float(rs.std())
        rv_slow = rv_slow if rv_slow > 1e-12 else 1e-12
        rv_ratio = rv_fast / rv_slow
        seg = c[-(FAST + 1):]
        travel = float(np.abs(np.diff(seg)).sum())
        eff = abs(float(seg[-1] - seg[0])) / travel if travel > 1e-12 else 0.0
        rng = (h[-FAST:] - l[-FAST:])
        body_hi = np.maximum(o[-FAST:], c[-FAST:]); body_lo = np.minimum(o[-FAST:], c[-FAST:])
        wick = float(np.mean(np.where(rng > 1e-12, ((h[-FAST:] - body_hi) + (body_lo - l[-FAST:])) / np.where(rng > 1e-12, rng, 1.0), 0.0)))
        sign = np.sign(c[-FAST:] - o[-FAST:])
        crosses = float(np.sum(sign[1:] != sign[:-1]))
        persistence = float(abs(np.mean(np.sign(rf))))
        absret = float(np.mean(np.abs(rf))) / rv_slow
        vf = float(np.mean(v[-FAST:])); vs = float(np.mean(v[-SLOW:]))
        activity_ratio = vf / vs if vs > 1e-12 else 1.0
        return np.array([rv_ratio, eff, wick, crosses, persistence, absret, activity_ratio])

    def bucket(self, mode="A"):
        """Nearest frozen centroid. Returns (bucket, preset, features) or (None, STATIC, None)."""
        f = self.features()
        if f is None:
            return None, dict(STATIC), None
        if mode == "A":
            z = (f - _C_MEAN) / _C_STD
        else:
            self._hist.append(f)
            H = np.array(self._hist[:-1])          # strictly past vectors only
            if len(H) < SLOW:
                z = (f - _C_MEAN) / _C_STD
            else:
                mu = H.mean(axis=0); sd = np.where(H.std(axis=0) > 1e-9, H.std(axis=0), 1.0)
                z = (f - mu) / sd
        b = int(np.argmin(((_C_Z - z) ** 2).sum(axis=1)))
        return b, dict(PRESETS[b]), f


def apply_preset(mod, preset):
    """Load the six numbers into the untouched r6.4 module. Nothing else is touched."""
    mod.EF_EARLY_REACH_MIN = float(preset["reach"])
    mod.EF_EARLY_CONTROL_MIN = float(preset["control"])
    mod.EF_EARLY_SETTLEMENT_MIN = float(preset["settlement"])
    mod.EF_EARLY_QUALITY_MIN = float(preset["quality"])
    mod.EF_EARLY_CHOP_MAX = float(preset["chop"])
    mod.EF_EARLY_SCORE_MIN = float(preset["score"])


# ======================================================================
# CLEAN6 -- GPT-5.6 Sol's FINAL VERIFIED spec (2026-09-06), superseding the 6/36 handoff.
# fast = 8 completed candles, slow = last min(24, available), ready after 8.
# Six observable features; the seventh (activity = volatility/liquidity) was a synthetic latent
# and is deliberately dropped rather than proxied. Scaler and projected centroids supplied frozen.
# ======================================================================
CLEAN6_FEATURES = ("rv_ratio", "eff", "wick", "crosses", "persistence", "absret")
CLEAN6_MEAN = np.array([1.0348285036518456, 0.4121866807706514, 0.4057648354836863,
                        2.5682788051209102, 0.3061877667140825, 0.720658426519248])
CLEAN6_SCALE = np.array([0.2900799519226345, 0.2040954907833692, 0.17490636923715536,
                         1.6256444142333286, 0.24919667010393015, 0.15961425080790148])
CLEAN6_CENTROIDS = np.array([
    [-0.26553490135703633, -0.7646776850192353, 0.7711519301034174, 0.695770017878343, -0.04385751230090337, -0.6905242524035625],
    [-0.2466323639125014, 1.0023376091885732, -0.9857024488974996, -0.8329381481051576, 0.09616864074326485, 0.8960368055888578],
    [1.6884282259927006, 0.037584739562221726, -0.10867559209508662, -0.2569695851409911, -0.10681472681742876, 0.0595784599156762],
])
CLEAN6_FAST, CLEAN6_SLOW, CLEAN6_READY = 8, 24, 8


class Clean6Router:
    """Sol's final verified router. Consumes CLOSED candle statistics only.

    Each closed candle contributes (rv, eff, wick, crosses, dir, body, range) where eff and
    crosses are measured on the real trade path inside that candle (precompute_candle_stats.py),
    which is what the synthetic generator supplied natively and an OHLC bar cannot.
    """

    def __init__(self):
        self.hist = []          # list of dicts, oldest first

    def add_closed_candle(self, rv, eff, wick, crosses, direction, body, rng):
        self.hist.append(dict(rv=float(rv), eff=float(eff), wick=float(wick), crosses=float(crosses),
                              dir=float(direction), body=float(body), rng=float(rng)))
        if len(self.hist) > CLEAN6_SLOW:
            self.hist = self.hist[-CLEAN6_SLOW:]          # "previous max 24 completed candles only"

    def ready(self):
        return len(self.hist) >= CLEAN6_READY

    def features(self):
        if not self.ready():
            return None
        h = self.hist[-CLEAN6_SLOW:]
        fast = h[-CLEAN6_FAST:]
        rv_fast = np.mean([x["rv"] for x in fast]); rv_slow = np.mean([x["rv"] for x in h])
        rv_ratio = rv_fast / rv_slow if rv_slow > 1e-15 else 1.0
        eff = float(np.mean([x["eff"] for x in fast]))
        wick = float(np.mean([x["wick"] for x in fast]))
        crosses = float(np.mean([x["crosses"] for x in fast]))
        persistence = float(abs(np.mean([x["dir"] for x in fast])))
        mb = float(np.mean([x["body"] for x in fast])); mr = float(np.mean([x["rng"] for x in fast]))
        absret = mb / mr if mr > 1e-12 else 0.0
        return np.array([rv_ratio, eff, wick, crosses, persistence, absret])

    def bucket(self):
        f = self.features()
        if f is None:
            return None, dict(STATIC), None
        z = (f - CLEAN6_MEAN) / CLEAN6_SCALE
        b = int(np.argmin(((CLEAN6_CENTROIDS - z) ** 2).sum(axis=1)))
        return b, dict(PRESETS[b]), f
