"""Build 11.4 autopilot: the engine manages the dials that were managed by hand on 09-10.

Pure rule functions (unit-tested, no engine needed) + a small controller that the engine
calls from its 500 ms tick and after every settlement. Every automatic change is written to
the autopilot_log table with the numbers behind it, and nothing here ever raises max_stake,
sets a stop-loss, or resets a database.

Rules (spec: learner/AUTOPILOT_11.4.md):
  A  auto_arm      after a restart, once the execution preflight is ready, turn the master
                   switch back ON (per-lane switches already persist).
  B  ladder        stake by wallet: $1 below 30, $2 at >= 30, +$1 per +10 above, capped by the
                   configured max (never above 20 by the engine).
  C  rev_guard     REVERSAL kill rules on its live fills; automatic resume when the shadow
                   record recovers.  ef_rolling: EF shadow-and-resume on a bad rolling window.
  D  dial_verdict  every N graded refusals, loosen or keep the REVERSAL cap / EF floor from
                   the refused group's own PnL on both halves.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_SETTINGS: Dict[str, Any] = {
    "auto_arm": False,
    "ladder": False,
    "rev_guard": False,
    "ef_rolling": False,
    "dial_verdict": False,
    # thresholds (all editable through /api/controls/autopilot)
    "rev_first_n": 6, "rev_first_max_wins": 1,
    "rev_slip_n": 20, "rev_slip_max": 0.03,
    "rev_pnl_n": 20, "rev_pnl_min": -3.0,
    "rev_resume_candles": 30, "rev_resume_min_rate": 0.60,
    "ef_window": 20, "ef_max_wins": 8, "ef_shadow_min": 30,
    "verdict_n": 100, "floor_min": 0.40, "floor_max": 0.55, "cap_min": 0.50, "cap_max": 0.70,
    "arm_delay_s": 30,
}

LADDER_FIRST_STEP = 30.0     # wallet at which the stake first rises to $2
LADDER_STEP = 10.0           # +$1 per +$10 of wallet above that
HARD_MAX_STAKE = 20.0        # the engine never sizes above this, whatever the config says


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- rule functions (pure)
def ladder_stake(balance: float, min_stake: float = 1.0, max_stake: float = HARD_MAX_STAKE) -> float:
    """$1 below 30, $2 at >= 30, $3 at >= 40, +$1 per +10; steps down again below a rung."""
    try:
        bal = float(balance)
    except (TypeError, ValueError):
        bal = 0.0
    if not math.isfinite(bal) or bal < LADDER_FIRST_STEP:
        stake = 1.0
    else:
        stake = 2.0 + math.floor((bal - LADDER_FIRST_STEP) / LADDER_STEP)
    cap = min(float(max_stake), HARD_MAX_STAKE)
    return round(max(float(min_stake), min(cap, stake)), 2)


def rev_kill_decision(fills: Sequence[Dict[str, Any]], s: Dict[str, Any]) -> Optional[str]:
    """fills: the lane's LIVE settled fills since it was (re)enabled, oldest first, each with
    quoted_price, fill_price, correct, pnl (at the stake used).  Returns the kill reason or None."""
    n = len(fills)
    if n == 0:
        return None
    first_n = int(s.get("rev_first_n", 6))
    if n >= first_n:
        wins = sum(1 for f in fills[:first_n] if f.get("correct"))
        if wins <= int(s.get("rev_first_max_wins", 1)):
            return f"first {first_n} live fills {wins}/{first_n}"
    slip_n = int(s.get("rev_slip_n", 20))
    if n >= slip_n:
        slips = [float(f["fill_price"]) - float(f["quoted_price"]) for f in fills
                 if f.get("fill_price") is not None and f.get("quoted_price") is not None]
        if slips and sum(slips) / len(slips) > float(s.get("rev_slip_max", 0.03)):
            return f"average fill {sum(slips) / len(slips):.3f} worse than quote over {len(slips)} fills"
    pnl_n = int(s.get("rev_pnl_n", 20))
    if n >= pnl_n:
        # PnL per $1 of stake so the rule does not depend on the ladder
        per_unit = sum(float(f.get("pnl") or 0.0) / max(float(f.get("stake") or 1.0), 1e-9) for f in fills)
        if per_unit < float(s.get("rev_pnl_min", -3.0)):
            return f"real PnL {per_unit:+.2f} per $1 over {n} fills"
    return None


def rev_resume_decision(shadow: Sequence[Dict[str, Any]], s: Dict[str, Any]) -> bool:
    """shadow: graded shadow/refused REVERSAL rows since the kill, at quotes <= the cap.
    Resume once there are enough and the would-have record is good enough."""
    need = int(s.get("rev_resume_candles", 30))
    graded = [r for r in shadow if r.get("would_win") is not None]
    if len(graded) < need:
        return False
    rate = sum(1 for r in graded if r["would_win"]) / len(graded)
    return rate >= float(s.get("rev_resume_min_rate", 0.60))


def ef_rolling_decision(results: Sequence[bool], s: Dict[str, Any]) -> bool:
    """results: EF settled outcomes, oldest first.  True = put EF in shadow now."""
    window = int(s.get("ef_window", 20))
    if len(results) < window:
        return False
    recent = list(results)[-window:]
    return sum(1 for r in recent if r) <= int(s.get("ef_max_wins", 8))


def dial_verdict(refused: Sequence[Dict[str, Any]], current: float, kind: str, s: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """refused: graded rows the dial refused (each with price and would_win), oldest first.
    kind: 'cap' (REVERSAL max entry) or 'floor' (EF min ask).  Returns (new value or None, reason).
    Loosen one notch only when the refused group made money on BOTH halves at $1; otherwise keep."""
    need = int(s.get("verdict_n", 100))
    rows = [r for r in refused if r.get("would_win") is not None and r.get("price")]
    if len(rows) < need:
        return None, f"{len(rows)}/{need} graded refusals"
    rows = rows[-need:]
    half = len(rows) // 2

    def pnl(part: Sequence[Dict[str, Any]]) -> float:
        return sum((1.0 / (float(r["price"]) * 1.02) - 1.0) if r["would_win"] else -1.0 for r in part)

    h1, h2 = pnl(rows[:half]), pnl(rows[half:])
    if h1 > 0 and h2 > 0:
        if kind == "cap":
            new = min(float(s.get("cap_max", 0.70)), round(current + 0.05, 2))
        else:
            new = max(float(s.get("floor_min", 0.40)), round(current - 0.02, 2))
        if abs(new - current) < 1e-9:
            return None, f"refused group +{h1:.1f}/+{h2:.1f} but {kind} already at its bound"
        return new, f"refused group made money on both halves ({h1:+.1f}/{h2:+.1f} at $1): {kind} {current:.2f} -> {new:.2f}"
    return None, f"refused group {h1:+.1f}/{h2:+.1f} at $1: keep {kind} at {current:.2f}"


# ---------------------------------------------------------------- controller
class Autopilot:
    """Duck-typed on the engine: needs .store (db, lock, control_row, capital_state),
    .controls (apply_change, apply_signal_toggle, snapshot), .executor (refresh_live_readiness),
    .started_ms, .v11_rev_max_entry, .v11_ef_min_ask, .apply_v11_settings, .record_error."""

    META_SETTINGS = "autopilot_settings"
    META_STATE = "autopilot_state"

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.state: Dict[str, Any] = {
            "armed_this_run": False, "rev_live_since_ms": None, "rev_killed_ms": None,
            "rev_kill_reason": None, "ef_shadow_until_ms": None, "ef_shadow_count": 0,
            "last_verdict_cap_ms": 0, "last_verdict_floor_ms": 0, "last_ladder_stake": None,
            "verdict_cap_seen": 0, "verdict_floor_seen": 0,
        }
        self._ensure_table()
        self._load()

    # -- persistence
    def _ensure_table(self) -> None:
        st = self.engine.store
        with st.lock:
            st.db.execute(
                "CREATE TABLE IF NOT EXISTS autopilot_log("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL, rule TEXT NOT NULL, "
                "action TEXT NOT NULL, detail TEXT)"
            )
            st.db.commit()

    def _meta_get(self, key: str) -> Dict[str, Any]:
        st = self.engine.store
        with st.lock:
            row = st.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        try:
            v = json.loads(row[0]) if row else {}
        except Exception:
            v = {}
        return v if isinstance(v, dict) else {}

    def _meta_set(self, key: str, value: Dict[str, Any]) -> None:
        st = self.engine.store
        body = json.dumps(value, allow_nan=False, separators=(",", ":"))
        with st.lock:
            st.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, body))
            st.db.commit()

    def _load(self) -> None:
        saved = self._meta_get(self.META_SETTINGS)
        for k, v in saved.items():
            if k in DEFAULT_SETTINGS:
                self.settings[k] = v
        st = self._meta_get(self.META_STATE)
        for k, v in st.items():
            if k in self.state:
                self.state[k] = v
        self.state["armed_this_run"] = False

    def _save_state(self) -> None:
        self._meta_set(self.META_STATE, self.state)

    def log(self, rule: str, action: str, detail: str = "") -> None:
        st = self.engine.store
        try:
            with st.lock:
                st.db.execute("INSERT INTO autopilot_log(ts_ms,rule,action,detail) VALUES(?,?,?,?)",
                              (now_ms(), rule, action, detail[:800]))
                st.db.commit()
        except Exception as problem:  # pragma: no cover
            self.engine.record_error(f"autopilot log: {problem}")

    def recent_log(self, limit: int = 30) -> List[Dict[str, Any]]:
        st = self.engine.store
        with st.lock:
            rows = st.db.execute("SELECT ts_ms,rule,action,detail FROM autopilot_log ORDER BY id DESC LIMIT ?",
                                 (int(limit),)).fetchall()
        return [{"ts_ms": r[0], "rule": r[1], "action": r[2], "detail": r[3]} for r in rows]

    # -- settings API
    def apply_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "autopilot settings must be an object"}
        new = dict(self.settings)
        for k, v in payload.items():
            if k not in DEFAULT_SETTINGS:
                continue
            if isinstance(DEFAULT_SETTINGS[k], bool):
                if not isinstance(v, bool):
                    return {"ok": False, "error": f"{k} must be true or false"}
                new[k] = v
            else:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    return {"ok": False, "error": f"{k} must be a number"}
                if not math.isfinite(fv):
                    return {"ok": False, "error": f"{k} must be finite"}
                new[k] = int(fv) if isinstance(DEFAULT_SETTINGS[k], int) else fv
        if not (0.0 <= float(new["floor_min"]) <= float(new["floor_max"]) <= 0.95):
            return {"ok": False, "error": "floor bounds must satisfy 0 <= floor_min <= floor_max <= 0.95"}
        if not (0.05 <= float(new["cap_min"]) <= float(new["cap_max"]) <= 0.99):
            return {"ok": False, "error": "cap bounds must satisfy 0.05 <= cap_min <= cap_max <= 0.99"}
        changed = {k: (self.settings.get(k), new[k]) for k in new if new[k] != self.settings.get(k)}
        self.settings = new
        self._meta_set(self.META_SETTINGS, self.settings)
        if changed:
            self.log("settings", "changed", json.dumps(changed))
        return {"ok": True, "settings": dict(self.settings)}

    def snapshot(self) -> Dict[str, Any]:
        return {"settings": dict(self.settings), "state": dict(self.state), "log": self.recent_log(20)}

    # -- data access helpers
    def _rev_live_fills(self) -> List[Dict[str, Any]]:
        since = int(self.state.get("rev_live_since_ms") or 0)
        st = self.engine.store
        with st.lock:
            rows = st.db.execute(
                "SELECT quoted_price,fill_price,correct,pnl,stake FROM trades WHERE kind='REVERSAL' AND filled=1 "
                "AND correct IS NOT NULL AND ts_ms>=? ORDER BY ts_ms", (since,)).fetchall()
        return [{"quoted_price": r[0], "fill_price": r[1], "correct": bool(r[2]), "pnl": r[3], "stake": r[4]} for r in rows]

    def _rev_shadow_since_kill(self) -> List[Dict[str, Any]]:
        since = int(self.state.get("rev_killed_ms") or 0)
        cap = float(getattr(self.engine, "v11_rev_max_entry", 0.0) or 0.0)
        st = self.engine.store
        with st.lock:
            rows = st.db.execute(
                "SELECT t.quoted_price,t.direction,c.actual FROM trades t LEFT JOIN candles c ON c.candle_id=t.candle_id "
                "WHERE t.kind='REVERSAL' AND (t.filled=0 OR t.filled IS NULL) AND t.ts_ms>=? AND t.quoted_price IS NOT NULL "
                "ORDER BY t.ts_ms", (since,)).fetchall()
        out = []
        for q, d, actual in rows:
            if cap > 0 and float(q) > cap:
                continue
            out.append({"price": q, "would_win": (None if actual in (None, "") else actual == d)})
        return out

    def _ef_recent_results(self, n: int) -> List[bool]:
        st = self.engine.store
        with st.lock:
            rows = st.db.execute(
                "SELECT correct FROM trades WHERE kind='EF' AND filled=1 AND correct IS NOT NULL "
                "ORDER BY ts_ms DESC LIMIT ?", (int(n),)).fetchall()
        return [bool(r[0]) for r in reversed(rows)]

    def _refused_rows(self, kind: str) -> List[Dict[str, Any]]:
        st = self.engine.store
        if kind == "cap":
            with st.lock:
                rows = st.db.execute(
                    "SELECT t.quoted_price,t.direction,c.actual FROM trades t LEFT JOIN candles c ON c.candle_id=t.candle_id "
                    "WHERE t.kind='REVERSAL' AND t.failure_reason LIKE '%REVERSAL entry cap%' ORDER BY t.ts_ms").fetchall()
            return [{"price": q, "would_win": (None if a in (None, "") else a == d)} for q, d, a in rows]
        with st.lock:
            rows = st.db.execute(
                "SELECT g.price,g.direction,COALESCE(g.actual,c.actual) FROM gated_predictions g "
                "LEFT JOIN candles c ON c.candle_id=g.candle_id WHERE g.reason LIKE '%below EF floor%' ORDER BY g.ts_ms").fetchall()
        return [{"price": p, "would_win": (None if a in (None, "") else a == d)} for p, d, a in rows]

    # -- hooks
    def on_lane_toggle(self, kind: str, enabled: bool) -> None:
        """Called whenever a lane switch changes (by a human or by a rule) so the counters restart."""
        if kind == "REVERSAL":
            if enabled:
                self.state["rev_live_since_ms"] = now_ms()
                self.state["rev_killed_ms"] = None
                self.state["rev_kill_reason"] = None
            self._save_state()

    def on_settled(self, kind: str, won: bool) -> None:
        s = self.settings
        try:
            if kind == "REVERSAL" and s.get("rev_guard"):
                row = self.engine.store.control_row("REVERSAL")
                if bool(row.get("manual_enabled")):
                    reason = rev_kill_decision(self._rev_live_fills(), s)
                    if reason:
                        self.engine.controls.apply_signal_toggle("REVERSAL", False)
                        self.state["rev_killed_ms"] = now_ms()
                        self.state["rev_kill_reason"] = reason
                        self._save_state()
                        self.log("rev_guard", "REVERSAL OFF", reason)
            if kind == "EF" and s.get("ef_rolling"):
                row = self.engine.store.control_row("EF")
                if bool(row.get("manual_enabled")) and ef_rolling_decision(self._ef_recent_results(int(s["ef_window"])), s):
                    self.engine.controls.apply_signal_toggle("EF", False)
                    until = now_ms() + int(float(s["ef_shadow_min"]) * 60000)
                    self.state["ef_shadow_until_ms"] = until
                    self.state["ef_shadow_count"] = int(self.state.get("ef_shadow_count") or 0) + 1
                    self._save_state()
                    self.log("ef_rolling", "EF SHADOW", f"last {s['ef_window']} settled <= {s['ef_max_wins']} wins; resume at {until}")
            if s.get("ladder"):
                self._apply_ladder()
        except Exception as problem:
            self.engine.record_error(f"autopilot on_settled: {problem}")

    def _apply_ladder(self) -> None:
        st = self.engine.store
        cfg = dict(st.control_row("SYSTEM")["stake"])
        try:
            capital = st.capital_state()
            balance = float(capital.get("balance") or 0.0)
        except Exception:
            return
        target = ladder_stake(balance, float(cfg.get("min_stake", 1.0) or 1.0), float(cfg.get("max_stake", HARD_MAX_STAKE) or HARD_MAX_STAKE))
        current = float(cfg.get("fixed_stake", cfg.get("current_stake", 1.0)) or 1.0)
        if str(cfg.get("mode")) == "fixed" and abs(target - current) < 1e-9:
            return
        if self.state.get("last_ladder_stake") == target and str(cfg.get("mode")) == "fixed":
            return
        new_cfg = dict(cfg)
        new_cfg["mode"] = "fixed"
        new_cfg["fixed_stake"] = target
        new_cfg["max_stake"] = min(float(cfg.get("max_stake", HARD_MAX_STAKE) or HARD_MAX_STAKE), HARD_MAX_STAKE)
        out = self.engine.controls.apply_change("SYSTEM", stake=new_cfg)
        if out.get("ok"):
            self.state["last_ladder_stake"] = target
            self._save_state()
            self.log("ladder", f"stake -> ${target:.0f}", f"wallet {balance:.2f}; {'parked until positions settle' if out.get('pending') else 'applied'}")
        else:
            self.log("ladder", "rejected", str(out.get("error")))

    def tick(self) -> None:
        """Called from the engine's 500 ms decision tick."""
        s = self.settings
        t = now_ms()
        try:
            if s.get("auto_arm") and not self.state.get("armed_this_run"):
                if t - int(getattr(self.engine, "started_ms", t)) >= int(s.get("arm_delay_s", 30)) * 1000:
                    self._try_arm()
            if s.get("ef_rolling") and self.state.get("ef_shadow_until_ms") and t >= int(self.state["ef_shadow_until_ms"]):
                self.state["ef_shadow_until_ms"] = None
                self._save_state()
                self.engine.controls.apply_signal_toggle("EF", True)
                self.log("ef_rolling", "EF ON", "shadow window over")
            if s.get("rev_guard") and self.state.get("rev_killed_ms"):
                if rev_resume_decision(self._rev_shadow_since_kill(), s):
                    self.engine.controls.apply_signal_toggle("REVERSAL", True)
                    self.on_lane_toggle("REVERSAL", True)
                    self.log("rev_guard", "REVERSAL ON", f"shadow record recovered over >= {s['rev_resume_candles']} candles at >= {s['rev_resume_min_rate']:.0%}")
            if s.get("dial_verdict"):
                self._verdicts(t)
        except Exception as problem:
            self.engine.record_error(f"autopilot tick: {problem}")

    def _try_arm(self) -> None:
        eng = self.engine
        row = eng.store.control_row("SYSTEM")
        if bool(row.get("manual_enabled")):
            self.state["armed_this_run"] = True
            return
        try:
            capital = eng.store.capital_state()
            from_cfg = row["stake"]
            required = ladder_stake(float(capital.get("balance") or 0.0)) if self.settings.get("ladder") else float(from_cfg.get("fixed_stake", 1.0) or 1.0)
            readiness = eng.executor.refresh_live_readiness(force=True, required_stake=required)
        except Exception as problem:
            self.log("auto_arm", "waiting", f"readiness check failed: {problem}")
            return
        if not readiness.get("ready"):
            return
        out = eng.controls.apply_change("SYSTEM", manual_enabled=True)
        if out.get("ok"):
            self.state["armed_this_run"] = True
            self._save_state()
            self.log("auto_arm", "master ON", "preflight ready after restart; per-lane switches as persisted")
        else:
            self.log("auto_arm", "rejected", str(out.get("error")))

    def _verdicts(self, t: int) -> None:
        s = self.settings
        # cap
        rows = self._refused_rows("cap")
        graded = [r for r in rows if r["would_win"] is not None]
        if len(graded) >= int(s["verdict_n"]) and len(graded) // int(s["verdict_n"]) > int(self.state.get("verdict_cap_seen") or 0):
            cur = float(getattr(self.engine, "v11_rev_max_entry", 0.0) or 0.0)
            if cur > 0:
                new, reason = dial_verdict(graded, cur, "cap", s)
                if new is not None:
                    self.engine.apply_v11_settings({"rev_max_entry": new})
                self.log("dial_verdict", f"cap {'-> %.2f' % new if new is not None else 'kept'}", reason)
            self.state["verdict_cap_seen"] = len(graded) // int(s["verdict_n"])
            self._save_state()
        rows = self._refused_rows("floor")
        graded = [r for r in rows if r["would_win"] is not None]
        if len(graded) >= int(s["verdict_n"]) and len(graded) // int(s["verdict_n"]) > int(self.state.get("verdict_floor_seen") or 0):
            cur = float(getattr(self.engine, "v11_ef_min_ask", 0.0) or 0.0)
            if cur > 0:
                new, reason = dial_verdict(graded, cur, "floor", s)
                if new is not None:
                    self.engine.apply_v11_settings({"ef_min_ask": new})
                self.log("dial_verdict", f"floor {'-> %.2f' % new if new is not None else 'kept'}", reason)
            self.state["verdict_floor_seen"] = len(graded) // int(s["verdict_n"])
            self._save_state()


# ---------------------------------------------------------------- tests
if __name__ == "__main__":
    import unittest

    class AutopilotRuleTests(unittest.TestCase):
        def test_ladder(self):
            self.assertEqual(ladder_stake(16.9), 1.0)
            self.assertEqual(ladder_stake(29.99), 1.0)
            self.assertEqual(ladder_stake(30.0), 2.0)
            self.assertEqual(ladder_stake(39.99), 2.0)
            self.assertEqual(ladder_stake(40.0), 3.0)
            self.assertEqual(ladder_stake(75.0), 6.0)
            self.assertEqual(ladder_stake(1000.0), 20.0)            # hard cap
            self.assertEqual(ladder_stake(1000.0, max_stake=50.0), 20.0)
            self.assertEqual(ladder_stake(1000.0, max_stake=5.0), 5.0)
            self.assertEqual(ladder_stake(float("nan")), 1.0)
            self.assertEqual(ladder_stake(None), 1.0)

        def test_rev_kill(self):
            s = dict(DEFAULT_SETTINGS)
            f = lambda c, q=0.5, p=None, pnl=None: {"quoted_price": q, "fill_price": q if p is None else p, "correct": c, "pnl": (0.9 if c else -1.0) if pnl is None else pnl, "stake": 1.0}
            self.assertIsNone(rev_kill_decision([], s))
            self.assertIsNone(rev_kill_decision([f(False)] * 5, s))                      # too early
            self.assertIn("first 6", rev_kill_decision([f(False)] * 5 + [f(True)], s))    # 1/6
            self.assertIsNone(rev_kill_decision([f(True), f(True)] + [f(False)] * 4, s))  # 2/6 survives
            good = [f(True)] * 14 + [f(False)] * 6
            self.assertIsNone(rev_kill_decision(good, s))
            slippy = [dict(x, fill_price=x["quoted_price"] + 0.05) for x in good]
            self.assertIn("worse than quote", rev_kill_decision(slippy, s))
            bad = [f(True)] * 8 + [f(False)] * 12                                         # 8*0.9-12 = -4.8
            self.assertIn("real PnL", rev_kill_decision(bad, s))
            scaled = [dict(x, pnl=x["pnl"] * 3, stake=3.0) for x in bad]                  # same per $1
            self.assertIn("real PnL", rev_kill_decision(scaled, s))

        def test_rev_resume(self):
            s = dict(DEFAULT_SETTINGS)
            self.assertFalse(rev_resume_decision([{"would_win": True}] * 29, s))
            self.assertTrue(rev_resume_decision([{"would_win": True}] * 18 + [{"would_win": False}] * 12, s))
            self.assertFalse(rev_resume_decision([{"would_win": True}] * 17 + [{"would_win": False}] * 13, s))
            self.assertFalse(rev_resume_decision([{"would_win": None}] * 40, s))

        def test_ef_rolling(self):
            s = dict(DEFAULT_SETTINGS)
            self.assertFalse(ef_rolling_decision([False] * 19, s))
            self.assertTrue(ef_rolling_decision([True] * 8 + [False] * 12, s))
            self.assertFalse(ef_rolling_decision([True] * 9 + [False] * 11, s))
            self.assertTrue(ef_rolling_decision([True] * 30 + [False] * 12 + [True] * 8, s))  # only the last 20 count

        def test_dial_verdict(self):
            s = dict(DEFAULT_SETTINGS)
            win = {"price": 0.64, "would_win": True}; loss = {"price": 0.64, "would_win": False}
            self.assertEqual(dial_verdict([win] * 99, 0.60, "cap", s)[0], None)             # not enough
            new, why = dial_verdict([win] * 100, 0.60, "cap", s); self.assertEqual(new, 0.65)
            new, why = dial_verdict([win] * 50 + [loss] * 50, 0.60, "cap", s); self.assertIsNone(new)  # h2 negative
            new, why = dial_verdict([win, loss] * 50, 0.60, "cap", s); self.assertIsNone(new)          # ~ -0.44/fire pair
            new, why = dial_verdict([win] * 100, 0.70, "cap", s); self.assertIsNone(new)               # at the bound
            fw = {"price": 0.40, "would_win": True}
            new, why = dial_verdict([fw] * 100, 0.48, "floor", s); self.assertEqual(new, 0.46)
            new, why = dial_verdict([fw] * 100, 0.40, "floor", s); self.assertIsNone(new)

    unittest.main()
