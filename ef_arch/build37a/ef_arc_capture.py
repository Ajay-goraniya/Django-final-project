# ======================================================================
# EF ARC-DUAL CAPTURE  (Build 37A)  -- additive research infrastructure
# ======================================================================
# Fixed 1-second wall-clock grid capture of the live EF feature state, both
# Predict.fun sides' cached quotes, causal watermarks, a zero-parameter L0
# prior, a coherent shadow L1, and seven frozen shadow policies.
#
# Invariants (enforced by construction, tested in ArcSelfTests):
#   * ARC observes. It never fires, sizes, blocks, delays or relabels
#     anything. MAIN/REV/EF decisions, staking, settlement, execution and
#     MASTER authority are untouched. Every hook is wrapped so an ARC
#     failure cannot reach the host.
#   * Sampling depends only on the clock (capture_rule = FIXED_GRID). No
#     max-rank, best, strongest or future-selected snapshot exists anywhere.
#   * Rows are immutable after insert except the settlement columns.
#   * P_DOWN = 1 - P_UP exactly (one logit).
#   * Economics use the project's settlement truth:
#         P_BE = q/(1-fee);  win = (1-fee)/q - 1;  loss = -1
#   * No REST call in the signal path: quotes come from the cached book.
#   * Pure standard library, same as the host file.
#
# Storage: a SIDECAR SQLite file next to the owned database
# (<db stem>_arc.sqlite3). The host Store's schema is not modified.
# ======================================================================
import json as _arc_json, math as _arc_math, os as _arc_os, queue as _arc_queue
import sqlite3 as _arc_sqlite3, struct as _arc_struct, threading as _arc_threading
import time as _arc_time, unittest as _arc_unittest
from collections import deque as _arc_deque

ARC_VERSION = "37A.1"
ARC_MODE = _arc_os.getenv("BTC_ARC_MODE", "capture").strip().lower()   # off | capture | shadow
ARC_GRID_MS = int(_arc_os.getenv("BTC_ARC_GRID_MS", "1000"))
ARC_DECISION_MS = 5000            # policies evaluate on grid rows at this cadence
ARC_REF_STAKE_USD = 10.0
ARC_SIGMA_WINDOW_S = 600
ARC_SIGMA_MIN_SAMPLES = 60
ARC_L1_MIN_CANDLES = 300          # shadow L1 stays off until this many settled candles
ARC_L1_WINDOW_CANDLES = 864       # 72 h
ARC_L1_REFIT_EVERY = 48
ARC_QUEUE_MAX = 20000
ARC_CANDLE_MS = 300_000

# ---------------------------------------------------------------- manifest
# frame: sym = identical for both sides; market = already signed toward UP;
#        reversal = signed toward the EF reversal side (mapped toward UP by
#        the direction sign at capture).
ARC_FEATURES = [
    # ---- side-symmetric geometry / time / vol
    ("phase_second", "sym"), ("seconds_left", "sym"), ("extension_sigma", "sym"),
    ("distance_to_open", "sym"), ("distance_from_extreme_to_open", "sym"),
    ("recovery_fraction", "sym"), ("recovery_from_extreme", "sym"),
    ("reachability", "sym"), ("settlement_feasibility", "sym"), ("runway_v2_score", "sym"),
    ("stay_score", "sym"), ("chop", "sym"), ("path_quality", "sym"),
    ("sigma_per_root_second", "sym"), ("perp_sigma_per_root_second", "sym"),
    ("volatility_capacity", "sym"), ("speed_capacity", "sym"), ("flow_flips_5s", "sym"),
    ("ef_uncertainty", "sym"), ("perp_deep_persistence", "sym"),
    ("perp_replenishment_1_5", "sym"), ("perp_replenishment_6_10", "sym"),
    ("perp_replenishment_11_20", "sym"), ("book_replenishment", "sym"),
    ("flow_persistent_buckets", "sym"), ("flow_profile_buckets", "sym"),
    ("flow_support_fraction", "sym"), ("reversal_quality", "sym"),
    ("rev_proximity", "sym"), ("exceptional_early", "sym"),
    # ---- market-signed (+ = toward UP)
    ("delta_250ms", "market"), ("delta_1s", "market"), ("delta_2s", "market"),
    ("delta_5s", "market"), ("delta_30s", "market"), ("book5", "market"),
    ("event_ofi", "market"), ("microprice", "market"),
    ("perp_book_1_5", "market"), ("perp_book_6_10", "market"), ("perp_book_11_20", "market"),
    # ---- reversal-frame (+ = supports the EF reversal side)
    ("control_transfer", "reversal"), ("old_side_exhaustion", "reversal"),
    ("flow_persistence", "reversal"), ("flow_transition", "reversal"),
    ("effectiveness_transfer", "reversal"), ("new_side_effectiveness", "reversal"),
    ("old_side_effectiveness", "reversal"), ("old_side_aggression", "reversal"),
    ("old_side_book_replenishment", "reversal"), ("new_side_book_support", "reversal"),
    ("opposite_flow", "reversal"), ("opposite_book", "reversal"), ("rejection", "reversal"),
    ("fake_reversal_penalty", "reversal"), ("real_reversal_score", "reversal"),
    ("memory_old_aggression", "reversal"), ("memory_aggression_decay", "reversal"),
    ("memory_effectiveness_decay", "reversal"), ("memory_control_handoff", "reversal"),
    ("memory_book_handoff", "reversal"), ("memory_exhaustion_score", "reversal"),
    ("memory_old_side_futility", "reversal"),
    ("settlement_probability_base", "reversal"), ("settlement_probability", "reversal"),
]
ARC_SYM_KEYS = [k for k, f in ARC_FEATURES if f == "sym"]
ARC_DIR_KEYS = [(k, f) for k, f in ARC_FEATURES if f != "sym"]
ARC_SCHEMA_VERSION = 1

# --------------------------------------------------------------- helpers
def _arc_f(v, default=float("nan")):
    try:
        x = float(v)
        return x if _arc_math.isfinite(x) else default
    except (TypeError, ValueError):
        return default

def _arc_phi(z):
    return 0.5 * (1.0 + _arc_math.erf(z / _arc_math.sqrt(2.0)))

def _arc_pack(values):
    return _arc_struct.pack("<%df" % len(values), *[(v if _arc_math.isfinite(v) else float("nan")) for v in values])

def _arc_unpack(blob):
    n = len(blob) // 4
    return list(_arc_struct.unpack("<%df" % n, blob)) if n else []

def _arc_logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return _arc_math.log(p / (1 - p))

def _arc_sigmoid(z):
    if z >= 0:
        e = _arc_math.exp(-z); return 1 / (1 + e)
    e = _arc_math.exp(z); return e / (1 + e)

# ------------------------------------------------------------- economics
def arc_break_even(q, fee):
    """Settlement truth: payout shares = shares*(1-fee)  =>  P_BE = q/(1-fee)."""
    return q / max(1.0 - fee, 1e-9)

def arc_return(win, q, fee):
    return (1.0 - fee) / q - 1.0 if win else -1.0

def arc_expected_return(p, q, fee):
    return p * (1.0 - fee) / q - 1.0

# ------------------------------------------------------------------ L0
class ArcL0:
    """Driftless terminal prior: P_UP = Phi(ln(p/O) / (sigma sqrt(tau))),
    sigma = trailing RMS of 1-second log returns over the last 600 s, using
    only returns that ended strictly before the current second."""
    def __init__(self):
        self.ring = _arc_deque(maxlen=ARC_SIGMA_WINDOW_S + 5)   # (sec, price)
        self.sq = _arc_deque(maxlen=ARC_SIGMA_WINDOW_S)          # squared 1 s log returns

    def observe(self, sec, price):
        if price is None or not _arc_math.isfinite(price) or price <= 0:
            return
        if self.ring and self.ring[-1][0] == sec:
            return
        if self.ring and sec - self.ring[-1][0] == 1:
            r = _arc_math.log(price / self.ring[-1][1]); self.sq.append(r * r)
        elif self.ring and sec - self.ring[-1][0] > 5:
            self.sq.clear()                                        # feed gap: restart the window
        self.ring.append((sec, price))

    def sigma(self):
        if len(self.sq) < ARC_SIGMA_MIN_SAMPLES:
            return float("nan")
        return _arc_math.sqrt(max(sum(self.sq) / len(self.sq), 1e-18))

    def p_up(self, price, open_price, seconds_left):
        s = self.sigma()
        if not _arc_math.isfinite(s) or price <= 0 or open_price <= 0:
            return 0.5, s
        tau = max(float(seconds_left), 1.0)
        z = _arc_math.log(price / open_price) / max(s * _arc_math.sqrt(tau), 1e-12)
        return min(max(_arc_phi(z), 0.02), 0.98), s

# ------------------------------------------------------------------ L1
class ArcResidualLogistic:
    """Coherent residual over L0:  logit(P_UP) = a*logit(P0) + w.x_dir + v.x_sym + b
    Pure-Python ridge logistic, gradient ascent, train-only standardisation.
    Fit only on settled rows; used only for shadow scoring."""
    def __init__(self, l2=0.01, iters=200, lr=0.5):
        self.l2, self.iters, self.lr = l2, iters, lr
        self.a, self.b, self.w, self.v = 1.0, 0.0, None, None
        self.mu, self.sd, self.fitted, self.version = None, None, False, "L0"

    def _design(self, p0, xs, xd):
        return [_arc_logit(p0)] + list(xd) + list(xs)

    def fit(self, rows, version):
        """rows: iterable of (p0, x_sym, x_dir, y, weight). Returns True if fitted."""
        data = [(self._design(p0, xs, xd), y, w) for p0, xs, xd, y, w in rows
                if all(_arc_math.isfinite(t) for t in xs) and all(_arc_math.isfinite(t) for t in xd)]
        if len(data) < 200:
            return False
        n = len(data[0][0]); W = sum(w for _, _, w in data)
        mu = [sum(w * r[j] for r, _, w in data) / W for j in range(n)]
        sd = [max(_arc_math.sqrt(sum(w * (r[j] - mu[j]) ** 2 for r, _, w in data) / W), 1e-9) for j in range(n)]
        mu[0], sd[0] = 0.0, 1.0                                        # keep the L0 logit unscaled
        X = [[(r[j] - mu[j]) / sd[j] for j in range(n)] for r, _, _ in data]
        theta = [1.0] + [0.0] * (n - 1); bias = 0.0
        for _ in range(self.iters):
            g = [0.0] * n; gb = 0.0
            for x, y, w in zip(X, (d[1] for d in data), (d[2] for d in data)):
                p = _arc_sigmoid(sum(t * xi for t, xi in zip(theta, x)) + bias); e = (y - p) * w
                gb += e
                for j in range(n): g[j] += e * x[j]
            for j in range(n):
                reg = self.l2 * (theta[j] - (1.0 if j == 0 else 0.0))   # ridge toward a=1, others 0
                theta[j] += self.lr * (g[j] / W - reg)
            bias += self.lr * gb / W
        self.mu, self.sd, self.a, self.b = mu, sd, theta[0], bias
        nd = len(ARC_DIR_KEYS); self.w = theta[1:1 + nd]; self.v = theta[1 + nd:]
        self.fitted, self.version = True, version
        return True

    def predict(self, p0, xs, xd):
        if not self.fitted:
            return p0
        r = self._design(p0, xs, xd)
        if any(not _arc_math.isfinite(t) for t in r):
            return p0
        z = self.b
        theta = [self.a] + list(self.w) + list(self.v)
        for j, t in enumerate(theta):
            z += t * (r[j] - self.mu[j]) / self.sd[j]
        return min(max(_arc_sigmoid(z), 0.01), 0.99)

class ArcPlatt:
    def __init__(self):
        self.a, self.c, self.fitted, self.version = 1.0, 0.0, False, "none"
    def fit(self, pairs, version, iters=300, lr=0.1):
        pairs = [(_arc_logit(p), y, w) for p, y, w in pairs]
        if len(pairs) < 200: return False
        a, c = 1.0, 0.0; W = sum(w for _, _, w in pairs)
        for _ in range(iters):
            ga = gc = 0.0
            for z, y, w in pairs:
                e = (y - _arc_sigmoid(a * z + c)) * w; ga += e * z; gc += e
            a += lr * ga / W; c += lr * gc / W
        self.a, self.c, self.fitted, self.version = a, c, True, version
        return True
    def apply(self, p):
        return p if not self.fitted else min(max(_arc_sigmoid(self.a * _arc_logit(p) + self.c), 0.01), 0.99)

# ------------------------------------------------------------- policies
# Frozen, predeclared (Sol section 36). Constants are NOT tuned here.
ARC_POLICIES = {
    0: dict(name="P0 greedy",      margin=0.03, roi_min=0.10, buffer=0.03, time_buffer=False, p_floor=None, persist=1, runway=None, governor=None),
    1: dict(name="P1 runway",      margin=0.03, roi_min=0.10, buffer=0.03, time_buffer=False, p_floor=None, persist=1, runway=60,   governor=None),
    2: dict(name="P2 persist2",    margin=0.03, roi_min=0.10, buffer=0.03, time_buffer=False, p_floor=None, persist=2, runway=None, governor=None),
    3: dict(name="P3 timebuffer",  margin=0.03, roi_min=0.10, buffer=0.05, time_buffer=True,  p_floor=None, persist=1, runway=None, governor=None),
    4: dict(name="P4 floor.35",    margin=0.03, roi_min=0.10, buffer=0.03, time_buffer=False, p_floor=0.35, persist=1, runway=None, governor=None),
    5: dict(name="P5 P2+P3+P4",    margin=0.03, roi_min=0.10, buffer=0.05, time_buffer=True,  p_floor=0.35, persist=2, runway=60,   governor=None),
    6: dict(name="P6 P5+governor", margin=0.03, roi_min=0.10, buffer=0.05, time_buffer=True,  p_floor=0.35, persist=2, runway=60,   governor=4.0),
}

def arc_policy_admits(cfg, p_up, side, q, seconds_left, fee, streak_ok, dd_units):
    """Pure function. Returns (admit, p_safe, p_be, edge, roi). Deterministic."""
    if q is None or not _arc_math.isfinite(q) or not (0.02 <= q <= 0.98):
        return False, None, None, None, None
    p = p_up if side == "UP" else 1.0 - p_up
    buf = cfg["buffer"] * (_arc_math.sqrt(300.0 / max(seconds_left, 1.0)) if cfg["time_buffer"] else 1.0)
    p_safe = min(max(p - buf, 0.01), 0.99)
    p_be = arc_break_even(q, fee)
    edge = p_safe - p_be; roi = p_safe / p_be - 1.0
    ok = edge >= cfg["margin"] and roi >= cfg["roi_min"]
    if cfg["p_floor"] is not None and p_safe < cfg["p_floor"]: ok = False
    if cfg["runway"] is not None and seconds_left < cfg["runway"]: ok = False
    if cfg["persist"] > 1 and not streak_ok: ok = False
    if cfg["governor"] is not None and dd_units >= cfg["governor"]: ok = False
    return ok, p_safe, p_be, edge, roi

# ------------------------------------------------------------- sidecar DB
ARC_DDL = [
    """CREATE TABLE IF NOT EXISTS ef_arc_snapshots(
        candle_id INTEGER NOT NULL, grid_index INTEGER NOT NULL,
        capture_ts_ms INTEGER NOT NULL, grid_offset_ms INTEGER NOT NULL,
        capture_rule TEXT NOT NULL CHECK(capture_rule IN ('FIXED_GRID','FIXED_CHECKPOINT','PREDECLARED_RANDOM','ACTUAL_FIRE')),
        body_side TEXT, ef_direction TEXT, spot REAL, open_price REAL, seconds_left REAL,
        spot_trade_max_ts_ms INTEGER, perp_trade_max_ts_ms INTEGER, perp_depth_max_ts_ms INTEGER, predict_book_ts_ms INTEGER,
        schema_version INTEGER NOT NULL, x_sym BLOB, x_dir BLOB,
        p0_up REAL, sigma_l0 REAL, p_raw_up REAL, p_cal_up REAL, model_version TEXT, calibrator_version TEXT,
        up_best_ask REAL, up_best_bid REAL, up_mid REAL, up_spread REAL, up_vwap_actual REAL, up_vwap_ref REAL, up_shares_ref REAL, up_quote_age_ms INTEGER, up_quote_reason TEXT, up_p_be REAL,
        dn_best_ask REAL, dn_best_bid REAL, dn_mid REAL, dn_spread REAL, dn_vwap_actual REAL, dn_vwap_ref REAL, dn_shares_ref REAL, dn_quote_age_ms INTEGER, dn_quote_reason TEXT, dn_p_be REAL,
        b36_triggered TEXT, b36_decision_reason TEXT, main_direction TEXT, main_probability_up REAL,
        micro_source TEXT, inputs_ready INTEGER,
        actual TEXT, outcome_up INTEGER, ret_cf_up REAL, ret_cf_dn REAL, weight REAL,
        PRIMARY KEY(candle_id, grid_index))""",
    """CREATE TABLE IF NOT EXISTS ef_arc_feature_manifest(
        schema_version INTEGER, vector TEXT, position INTEGER, name TEXT, frame TEXT,
        PRIMARY KEY(schema_version, vector, position))""",
    """CREATE TABLE IF NOT EXISTS ef_arc_policy_shadow(
        candle_id INTEGER NOT NULL, policy_id INTEGER NOT NULL, side TEXT, fire_grid_index INTEGER,
        fire_ts_ms INTEGER, q REAL, p_up REAL, p_safe REAL, p_be REAL, edge REAL, roi REAL,
        quote_source TEXT, actual TEXT, win INTEGER, ret_cf REAL,
        PRIMARY KEY(candle_id, policy_id))""",
    """CREATE TABLE IF NOT EXISTS ef_arc_versions(
        version TEXT PRIMARY KEY, kind TEXT, created_ts_ms INTEGER, train_from_candle INTEGER,
        train_to_candle INTEGER, n_candles INTEGER, params TEXT)""",
    """CREATE TABLE IF NOT EXISTS ef_arc_meta(key TEXT PRIMARY KEY, value TEXT)""",
]

class ArcWriter:
    """Off-hot-path writer: bounded queue, one thread, batched commits."""
    def __init__(self, path):
        self.path = str(path); self.q = _arc_queue.Queue(maxsize=ARC_QUEUE_MAX)
        self.dropped = 0; self.written = 0; self.errors = 0; self.last_error = ""
        self._stop = _arc_threading.Event()
        self.db = _arc_sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA synchronous=NORMAL")
        for ddl in ARC_DDL: self.db.execute(ddl)
        self.db.commit()
        self.t = _arc_threading.Thread(target=self._loop, name="arc-writer", daemon=True); self.t.start()

    def submit(self, sql, params):
        try: self.q.put_nowait((sql, params))
        except _arc_queue.Full: self.dropped += 1

    def _drain(self, limit=5000):
        batch = []
        while len(batch) < limit:
            try: batch.append(self.q.get_nowait())
            except _arc_queue.Empty: break
        if not batch: return 0
        try:
            for sql, params in batch: self.db.execute(sql, params)
            self.db.commit(); self.written += len(batch)
        except Exception as exc:                                 # never propagate to the host
            self.errors += 1; self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            try: self.db.rollback()
            except Exception: pass
        return len(batch)

    def _loop(self):
        while not self._stop.is_set():
            if self._drain() == 0: _arc_time.sleep(0.5)

    def flush(self):
        """Synchronous: drain everything now (replay end, shutdown, tests)."""
        while self._drain(): pass
        try: self.db.commit()
        except Exception: pass

    def close(self):
        self._stop.set()
        try: self.t.join(timeout=2.0)
        except Exception: pass
        self.flush()
        try: self.db.close()
        except Exception: pass

# --------------------------------------------------------------- capture
class ArcCapture:
    """Attach to an Engine. Called from three host hooks:
         on_tick(ts_ms)               after _compute_ef_metrics
         on_settle(candle, ts_ms)     at the start of _settle_candle
         close()                      from Engine.close
       Everything is guarded; any exception is counted and swallowed."""
    def __init__(self, engine, fee, candle_ms=ARC_CANDLE_MS, db_path=None):
        self.engine, self.fee, self.candle_ms = engine, float(fee), int(candle_ms)
        store_path = getattr(getattr(engine, "store", None), "path", None)
        if db_path is None:
            db_path = (str(store_path)[:-len(".sqlite3")] + "_arc.sqlite3") if store_path and str(store_path).endswith(".sqlite3") \
                      else (str(store_path) + "_arc.sqlite3" if store_path else "ef_arc.sqlite3")
        self.writer = ArcWriter(db_path)
        self.l0 = ArcL0(); self.l1 = ArcResidualLogistic(); self.platt = ArcPlatt()
        self.last_sec = None; self.open_rows = {}          # candle_id -> list of (grid_index, up_q, dn_q, p_cal, x_sym, x_dir, p0)
        self.settled_candles = 0; self.settled_since_fit = 0
        self.history = _arc_deque(maxlen=ARC_L1_WINDOW_CANDLES)   # per-candle settled training rows
        self.prequential = _arc_deque(maxlen=4000)                # (p_raw, y, w) for Platt
        self.policy_state = {pid: dict(streak=0, dd=0.0, peak=0.0, cum=0.0, fired_candle=None) for pid in ARC_POLICIES}
        self.errors = 0; self.last_error = ""; self.rows_captured = 0
        self._write_manifest()

    # ---- infrastructure
    def _write_manifest(self):
        for i, k in enumerate(ARC_SYM_KEYS):
            self.writer.submit("INSERT OR REPLACE INTO ef_arc_feature_manifest VALUES(?,?,?,?,?)", (ARC_SCHEMA_VERSION, "x_sym", i, k, "sym"))
        for i, (k, f) in enumerate(ARC_DIR_KEYS):
            self.writer.submit("INSERT OR REPLACE INTO ef_arc_feature_manifest VALUES(?,?,?,?,?)", (ARC_SCHEMA_VERSION, "x_dir", i, k, f))
        self.writer.submit("INSERT OR REPLACE INTO ef_arc_meta VALUES(?,?)", ("arc_version", ARC_VERSION))
        self.writer.submit("INSERT OR REPLACE INTO ef_arc_meta VALUES(?,?)", ("grid_ms", str(ARC_GRID_MS)))
        self.writer.submit("INSERT OR REPLACE INTO ef_arc_meta VALUES(?,?)", ("mode", ARC_MODE))
        self.writer.submit("INSERT OR REPLACE INTO ef_arc_meta VALUES(?,?)", ("fee", repr(self.fee)))

    def _err(self, exc):
        self.errors += 1; self.last_error = f"{type(exc).__name__}: {exc}"[:200]

    # ---- quotes (cached book only; never REST)
    def _quote(self, side, capture_ts):
        out = dict(best_ask=None, best_bid=None, mid=None, spread=None, vwap_actual=None, vwap_ref=None,
                   shares_ref=None, age_ms=None, reason="NO_BOOK", book_ts=None)
        book = getattr(self.engine, "book", None)
        if book is None: return out
        try:
            q = book.quote(side)
        except Exception as exc:
            out["reason"] = f"QUOTE_ERROR:{type(exc).__name__}"; return out
        ask = _arc_f(q.get("price"), None) if isinstance(q, dict) else None
        if ask is None:
            out["reason"] = str((q or {}).get("source") or "NO_CACHED_BOOK").upper().replace(" ", "_")[:60]; return out
        out["best_ask"] = ask; out["spread"] = _arc_f(q.get("spread"), None); out["age_ms"] = q.get("age_ms")
        if out["spread"] is not None: out["best_bid"] = ask - out["spread"]; out["mid"] = ask - out["spread"] / 2.0
        if out["age_ms"] is not None:
            try: out["book_ts"] = int(capture_ts) - int(out["age_ms"])
            except (TypeError, ValueError): pass
        stake_actual = _arc_f(getattr(getattr(self.engine, "executor", None), "_ef_hot_stake_hint", None), None)
        if stake_actual is None or stake_actual <= 0: stake_actual = ARC_REF_STAKE_USD
        for key, stake in (("vwap_actual", stake_actual), ("vwap_ref", ARC_REF_STAKE_USD)):
            try:
                ex = book.executable_vwap(side, stake)
                if isinstance(ex, dict) and ex.get("ok"):
                    out[key] = _arc_f(ex.get("vwap"), None)
                    if key == "vwap_ref": out["shares_ref"] = _arc_f(ex.get("shares"), None)
                elif key == "vwap_ref":
                    out["reason"] = str((ex or {}).get("reason") or "VWAP_UNAVAILABLE")[:60]
            except Exception as exc:
                out["reason"] = f"VWAP_ERROR:{type(exc).__name__}"
        if out["vwap_ref"] is not None: out["reason"] = "OK"
        return out

    # ---- features
    def _vectors(self, em):
        d = str(em.get("direction") or "").upper(); s = 1.0 if d == "UP" else (-1.0 if d == "DOWN" else 0.0)
        xs = [_arc_f(em.get(k)) for k in ARC_SYM_KEYS]
        xd = []
        for k, f in ARC_DIR_KEYS:
            v = _arc_f(em.get(k))
            xd.append(v if f == "market" else (v * s if s != 0.0 else float("nan")))
        return xs, xd, d

    # ---- hooks
    def on_tick(self, ts_ms):
        if ARC_MODE == "off": return
        try:
            self._on_tick(int(ts_ms))
        except Exception as exc:
            self._err(exc)

    def _on_tick(self, ts):
        e = self.engine
        sec = ts // 1000
        candle = getattr(e, "candle", None); feat = getattr(e, "feature", None) or {}
        if not candle or not feat: return
        if self.last_sec is not None and sec <= self.last_sec: return
        self.last_sec = sec
        cid = int(candle.get("time") or 0)
        if cid <= 0 or candle.get("closed") or not (cid <= ts < cid + self.candle_ms): return
        spot = _arc_f(feat.get("price"), None); opn = _arc_f(candle.get("open"), None)
        if spot is None or opn is None: return
        self.l0.observe(sec, spot)
        em = getattr(e, "ef_metrics", None) or {}
        seconds_left = _arc_f(feat.get("seconds_left"), (cid + self.candle_ms - ts) / 1000.0)
        grid_offset = ts - cid; grid_index = grid_offset // ARC_GRID_MS
        p0, sigma = self.l0.p_up(spot, opn, seconds_left)
        xs, xd, ef_dir = self._vectors(em)
        p_raw = self.l1.predict(p0, xs, xd) if self.l1.fitted else p0
        p_cal = self.platt.apply(p_raw)
        up = self._quote("UP", ts); dn = self._quote("DOWN", ts)
        body = "UP" if spot > opn else ("DOWN" if spot < opn else "FLAT")
        cur = getattr(e, "current_ef", None)
        b36 = str(getattr(cur, "direction", "") or "") if cur is not None else ""
        mon = getattr(e, "ef_monitor", None) or {}
        pp = getattr(e, "ef_perp_prep", None)
        row = (cid, int(grid_index), ts, int(grid_offset), "FIXED_GRID", body, ef_dir, spot, opn, seconds_left,
               int(getattr(e, "last_exchange_ms", 0) or 0), int(getattr(pp, "last_trade_recv_ms", 0) or 0),
               int(getattr(pp, "last_depth_recv_ms", 0) or 0), up["book_ts"],
               ARC_SCHEMA_VERSION, _arc_pack(xs), _arc_pack(xd),
               p0, sigma if _arc_math.isfinite(sigma) else None, p_raw, p_cal, self.l1.version, self.platt.version,
               up["best_ask"], up["best_bid"], up["mid"], up["spread"], up["vwap_actual"], up["vwap_ref"], up["shares_ref"], up["age_ms"], up["reason"],
               arc_break_even(up["vwap_ref"], self.fee) if up["vwap_ref"] else None,
               dn["best_ask"], dn["best_bid"], dn["mid"], dn["spread"], dn["vwap_actual"], dn["vwap_ref"], dn["shares_ref"], dn["age_ms"], dn["reason"],
               arc_break_even(dn["vwap_ref"], self.fee) if dn["vwap_ref"] else None,
               b36, str(mon.get("new_decision_reason") or mon.get("status") or "")[:80],
               str(em.get("main_direction") or ""), _arc_f(em.get("main_probability_up"), None),
               str(em.get("micro_source") or ""), 1 if em.get("inputs_ready") else 0)
        assert len(row) == 49, len(row)                       # 49 captured + 5 settlement columns = 54
        self.writer.submit("INSERT OR IGNORE INTO ef_arc_snapshots VALUES(" + ",".join("?" * 49) + ",NULL,NULL,NULL,NULL,NULL)", row)
        self.open_rows.setdefault(cid, []).append((int(grid_index), up["vwap_ref"], dn["vwap_ref"], p_cal, p_raw, xs, xd, p0, ts))
        self.rows_captured += 1
        if ARC_MODE == "shadow" and grid_offset % ARC_DECISION_MS == 0:
            self._shadow_policies(cid, int(grid_index), ts, body, p_cal, up["vwap_ref"], dn["vwap_ref"], seconds_left)

    def _shadow_policies(self, cid, gi, ts, body, p_up, up_q, dn_q, seconds_left):
        if body not in ("UP", "DOWN"): return
        rev_side = "DOWN" if body == "UP" else "UP"; q = dn_q if rev_side == "DOWN" else up_q
        for pid, cfg in ARC_POLICIES.items():
            st = self.policy_state[pid]
            if st["fired_candle"] == cid: continue
            ok, p_safe, p_be, edge, roi = arc_policy_admits(cfg, p_up, rev_side, q, seconds_left, self.fee,
                                                            st["streak"] >= cfg["persist"] - 1, st["dd"])
            raw_ok = ok or (cfg["persist"] > 1 and p_safe is not None and edge is not None and edge >= cfg["margin"] and roi >= cfg["roi_min"])
            st["streak"] = st["streak"] + 1 if raw_ok else 0
            if ok:
                st["fired_candle"] = cid; st["fired_q"] = q; st["fired_side"] = rev_side
                self.writer.submit("INSERT OR IGNORE INTO ef_arc_policy_shadow VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL)",
                                   (cid, pid, rev_side, gi, ts, q, p_up, p_safe, p_be, edge, roi, "CACHED_BOOK"))

    def on_settle(self, candle, ts_ms):
        if ARC_MODE == "off": return
        try:
            self._on_settle(candle, int(ts_ms))
        except Exception as exc:
            self._err(exc)

    def _on_settle(self, candle, ts):
        cid = int(candle.get("time") or 0); rows = self.open_rows.pop(cid, None)
        if cid <= 0 or not rows: return
        opn = _arc_f(candle.get("open"), None); cl = _arc_f(candle.get("close"), None)
        if opn is None or cl is None or cl == opn: actual = "FLAT"
        else: actual = "UP" if cl > opn else "DOWN"
        y = 1 if actual == "UP" else 0; n = len(rows); w = 1.0 / n
        for gi, upq, dnq, p_cal, p_raw, xs, xd, p0, _ in rows:
            ret_up = arc_return(actual == "UP", upq, self.fee) if upq else None
            ret_dn = arc_return(actual == "DOWN", dnq, self.fee) if dnq else None
            self.writer.submit("UPDATE ef_arc_snapshots SET actual=?, outcome_up=?, ret_cf_up=?, ret_cf_dn=?, weight=? WHERE candle_id=? AND grid_index=?",
                               (actual, y, ret_up, ret_dn, w, cid, gi))
            if actual != "FLAT":
                self.history.append((p0, xs, xd, float(y), w))
                self.prequential.append((p_raw, float(y), w))
        for pid, st in self.policy_state.items():
            if st["fired_candle"] == cid:
                self.writer.submit("UPDATE ef_arc_policy_shadow SET actual=?, win=(side=?), ret_cf=CASE WHEN side=? THEN (1-?)/q-1 ELSE -1 END WHERE candle_id=? AND policy_id=?",
                                   (actual, actual, actual, self.fee, cid, pid))
                # governor state uses only the realised shadow PnL of THIS policy (causal: past trades only)
                if actual != "FLAT" and st.get("fired_q"):
                    st["cum"] += arc_return(actual == st.get("fired_side"), st["fired_q"], self.fee)
                    st["peak"] = max(st["peak"], st["cum"]); st["dd"] = st["peak"] - st["cum"]
        if actual != "FLAT":
            self.settled_candles += 1; self.settled_since_fit += 1
            if self.settled_candles >= ARC_L1_MIN_CANDLES and self.settled_since_fit >= ARC_L1_REFIT_EVERY:
                self._refit(cid)

    def _refit(self, cid):
        self.settled_since_fit = 0
        rows = list(self.history); version = f"L1@{cid}"
        if self.l1.fit(rows, version):
            self.writer.submit("INSERT OR REPLACE INTO ef_arc_versions VALUES(?,?,?,?,?,?,?)",
                               (version, "L1", cid, None, cid, len(rows), _arc_json.dumps(dict(l2=self.l1.l2, iters=self.l1.iters))))
        if len(self.prequential) >= 300:
            pv = f"platt@{cid}"
            if self.platt.fit(list(self.prequential), pv):
                self.writer.submit("INSERT OR REPLACE INTO ef_arc_versions VALUES(?,?,?,?,?,?,?)",
                                   (pv, "PLATT", cid, None, cid, len(self.prequential), _arc_json.dumps(dict(a=self.platt.a, c=self.platt.c))))

    def health(self):
        return dict(arc_version=ARC_VERSION, mode=ARC_MODE, rows_captured=self.rows_captured,
                    written=self.writer.written, queued=self.writer.q.qsize(), dropped=self.writer.dropped,
                    writer_errors=self.writer.errors, writer_last_error=self.writer.last_error,
                    capture_errors=self.errors, last_error=self.last_error,
                    settled_candles=self.settled_candles, l1=self.l1.version, platt=self.platt.version,
                    sigma_l0=self.l0.sigma(), db=self.writer.path)

    def flush(self):
        self.writer.flush()

    def close(self):
        try: self.writer.close()
        except Exception as exc: self._err(exc)

# ------------------------------------------------------------ self-tests
class ArcSelfTests(_arc_unittest.TestCase):
    def test_K5_probability_coherence(self):
        m = ArcResidualLogistic()
        for p0 in (0.05, 0.3, 0.5, 0.77, 0.95):
            p = m.predict(p0, [0.0] * len(ARC_SYM_KEYS), [0.0] * len(ARC_DIR_KEYS))
            self.assertLess(abs(p + (1 - p) - 1.0), 1e-9)
    def test_K6_economic_identity(self):
        for q in (0.10, 0.20, 0.40, 0.50, 0.70):
            for fee in (0.0, 0.02):
                self.assertAlmostEqual(arc_break_even(q, fee), q / (1 - fee), 12)
                self.assertAlmostEqual(arc_expected_return(arc_break_even(q, fee), q, fee), 0.0, 12)
                self.assertAlmostEqual(arc_return(True, q, fee), (1 - fee) / q - 1, 12)
                self.assertEqual(arc_return(False, q, fee), -1.0)
    def test_L0_monotone_and_bounded(self):
        l0 = ArcL0()
        for i in range(700): l0.observe(i, 100.0 * _arc_math.exp(0.0002 * ((-1) ** i)))
        ps = [l0.p_up(100.0 * (1 + d), 100.0, 120)[0] for d in (-0.01, -0.001, 0.0, 0.001, 0.01)]
        self.assertEqual(ps, sorted(ps)); self.assertTrue(all(0.02 <= p <= 0.98 for p in ps))
        self.assertAlmostEqual(l0.p_up(100.0, 100.0, 120)[0], 0.5, 6)
        self.assertEqual(ArcL0().p_up(101.0, 100.0, 60)[0], 0.5)          # no history -> neutral
    def test_blob_roundtrip_and_manifest(self):
        v = [1.5, float("nan"), -2.25]; u = _arc_unpack(_arc_pack(v))
        self.assertEqual(u[0], 1.5); self.assertTrue(_arc_math.isnan(u[1])); self.assertEqual(u[2], -2.25)
        self.assertEqual(len(set(k for k, _ in ARC_FEATURES)), len(ARC_FEATURES))
        banned = ("adapt_", "learner_", "threshold_source", "frequency_", "quote", "vwap", "would_fire", "decision_")
        self.assertFalse([k for k, _ in ARC_FEATURES if any(b in k for b in banned)])
    def test_policies_deterministic_and_frozen(self):
        for pid, cfg in ARC_POLICIES.items():
            a = arc_policy_admits(cfg, 0.60, "UP", 0.40, 150.0, 0.02, True, 0.0)
            b = arc_policy_admits(cfg, 0.60, "UP", 0.40, 150.0, 0.02, True, 0.0)
            self.assertEqual(a, b)
        ok, ps, pbe, edge, roi = arc_policy_admits(ARC_POLICIES[0], 0.60, "UP", 0.40, 150.0, 0.02, True, 0.0)
        self.assertTrue(ok); self.assertAlmostEqual(pbe, 0.40 / 0.98, 9); self.assertAlmostEqual(ps, 0.57, 9)
        self.assertFalse(arc_policy_admits(ARC_POLICIES[1], 0.60, "UP", 0.40, 30.0, 0.02, True, 0.0)[0])   # runway
        self.assertFalse(arc_policy_admits(ARC_POLICIES[4], 0.36, "UP", 0.20, 150.0, 0.02, True, 0.0)[0])  # floor
        self.assertFalse(arc_policy_admits(ARC_POLICIES[6], 0.60, "UP", 0.40, 150.0, 0.02, True, 4.0)[0])  # governor
        self.assertFalse(arc_policy_admits(ARC_POLICIES[0], 0.60, "UP", None, 150.0, 0.02, True, 0.0)[0])  # no quote
    def test_capture_end_to_end_no_network(self):
        import tempfile
        class _Book:
            def quote(self, side): return {"price": 0.42 if side == "UP" else 0.55, "spread": 0.02, "age_ms": 40, "source": "test"}
            def executable_vwap(self, side, stake): return {"ok": True, "vwap": 0.43 if side == "UP" else 0.56, "shares": stake / 0.43}
        class _Perp: last_trade_recv_ms = 0; last_depth_recv_ms = 0
        class _Eng:
            def __init__(s): s.store = None; s.book = _Book(); s.ef_perp_prep = _Perp(); s.candle = None; s.feature = {}; s.ef_metrics = {}; s.current_ef = None; s.ef_monitor = {}; s.last_exchange_ms = 0; s.executor = None
        with tempfile.TemporaryDirectory() as d:
            eng = _Eng(); arc = ArcCapture(eng, 0.02, db_path=_arc_os.path.join(d, "t_arc.sqlite3"))
            base = 1_700_000_000_000
            for c in range(3):
                cid = base + c * ARC_CANDLE_MS; eng.candle = {"time": cid, "open": 100.0, "closed": False}
                for s in range(0, 300):
                    ts = cid + s * 1000; px = 100.0 + (0.01 * s if c % 2 == 0 else -0.01 * s)
                    eng.feature = {"price": px, "seconds_left": 300 - s}; eng.last_exchange_ms = ts
                    eng.ef_perp_prep.last_trade_recv_ms = ts; eng.ef_perp_prep.last_depth_recv_ms = ts
                    eng.ef_metrics = {"direction": "DOWN" if px > 100 else "UP", "delta_1s": 1.0, "control_transfer": 0.5, "seconds_left": 300 - s, "main_direction": "UP", "main_probability_up": 0.6}
                    arc.on_tick(ts + 7)
                    if s > 0: arc.on_tick(ts + 400)              # second tick in the same second must not add a row
                arc.on_settle({"time": cid, "open": 100.0, "close": px}, cid + ARC_CANDLE_MS - 1)
            arc.flush()
            self.assertEqual(arc.writer.errors, 0, arc.writer.last_error); self.assertEqual(arc.errors, 0, arc.last_error)
            db = _arc_sqlite3.connect(arc.writer.path)
            n = db.execute("select count(*) from ef_arc_snapshots").fetchone()[0]; self.assertEqual(n, 900)
            self.assertEqual(db.execute("select count(distinct candle_id) from ef_arc_snapshots").fetchone()[0], 3)
            self.assertEqual(db.execute("select count(*) from ef_arc_snapshots where actual is null").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from ef_arc_snapshots where capture_rule!='FIXED_GRID'").fetchone()[0], 0)
            self.assertEqual(db.execute("select count(*) from ef_arc_snapshots where spot_trade_max_ts_ms>capture_ts_ms or perp_depth_max_ts_ms>capture_ts_ms").fetchone()[0], 0)
            self.assertAlmostEqual(db.execute("select sum(weight) from ef_arc_snapshots where candle_id=?", (base,)).fetchone()[0], 1.0, 6)
            self.assertEqual(db.execute("select count(*) from ef_arc_feature_manifest").fetchone()[0], len(ARC_FEATURES))
            r = db.execute("select ret_cf_up, ret_cf_dn, up_p_be from ef_arc_snapshots where candle_id=? limit 1", (base,)).fetchone()
            self.assertAlmostEqual(r[0], (1 - 0.02) / 0.43 - 1, 9); self.assertEqual(r[1], -1.0); self.assertAlmostEqual(r[2], 0.43 / 0.98, 9)
            self.assertEqual(arc.errors, 0); self.assertEqual(arc.writer.errors, 0, arc.writer.last_error)
            arc.close()

def arc_run_self_tests():
    suite = _arc_unittest.defaultTestLoader.loadTestsFromTestCase(ArcSelfTests)
    return _arc_unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()

if __name__ == "__main__":
    raise SystemExit(0 if arc_run_self_tests() else 1)
