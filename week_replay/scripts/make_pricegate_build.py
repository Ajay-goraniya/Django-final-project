#!/usr/bin/env python3
"""Generate Build 36-PG from Build 36 by adding a venue PRICE GATE inside the
EF signal. Run:  make_pricegate_build.py btc_model_v9_3_build36.py

The model files themselves are not tracked in this repository (they are
supplied per-run), so the gate lives here as a patch: this script is the
reviewable diff. It adds 101 lines and changes exactly one (BUILD_REVISION);
no existing EF logic is modified.

WHERE THE GATE SITS AND WHY
  _watch_ef computes the BTC decision through _ef_decide, then either emits the
  fire or records an abstain. The gate is inserted BETWEEN those two, and runs
  only when `fire` is already True, so it can suppress a signal but never
  create one.

  A suppressed tick falls through to the ordinary not-fired path, which:
    * does NOT set self._r5_ef_terminal_latch
    * leaves self.current_ef as None
    * does NOT call ef_learner.mark_fired
  so EF keeps re-evaluating every EF_COMPUTE_INTERVAL_MS and CAN STILL FIRE
  LATER IN THE SAME CANDLE once the price becomes acceptable. The gate delays
  and filters; it does not kill the candle. This is the whole point, and it is
  why the gate cannot be implemented as a post-hoc filter over the database.
"""
import pathlib
import sys

CONST_ANCHOR = 'EF_FREQUENCY_STATE_KEY = "ef_final_frequency_build30_v1"'

CONSTS = '''EF_FREQUENCY_STATE_KEY = "ef_final_frequency_build30_v1"

# ---------------------------------------------------------------- price gate
# Build 36-PG: a venue PRICE gate that sits INSIDE the EF signal, evaluated on
# every EF tick immediately after _ef_decide and before the fire is emitted.
#
# It can only ever SUPPRESS a fire, never create one. A suppressed tick takes
# the ordinary not-fired path: no terminal latch is set, current_ef stays None
# and mark_fired is not called, so EF keeps re-evaluating every EF_COMPUTE_
# INTERVAL_MS and FIRES LATER IN THE SAME CANDLE the moment the price is
# acceptable. That is the whole point: the gate delays and filters, it does not
# kill the candle.
#
# Two independent conditions, both causal (only decision-time information):
#   1. hard ceiling   ask <= EF_PRICE_GATE_MAX_ASK
#   2. model edge     settlement_probability - fee_adjusted_cost(ask) >= EF_PRICE_GATE_MIN_EDGE
# where fee_adjusted_cost(q) = q / (1 - r(1-q)) is what $1 of payout really
# costs after the venue's taker fee, i.e. the break-even probability.
EF_PRICE_GATE_ENABLED = True
EF_PRICE_GATE_MAX_ASK = 0.55        # never pay above this for a 5m contract
EF_PRICE_GATE_MIN_EDGE = 0.0        # model probability must beat break-even by this
EF_PRICE_GATE_FEE_RATE = 0.07       # venue feeSchedule.rate, takerOnly
EF_PRICE_GATE_MAX_QUOTE_AGE_S = 20  # a quote older than this is not a price
EF_PRICE_GATE_BLOCK_WHEN_NO_QUOTE = True   # cannot buy what cannot be priced'''

WATCH_MARK = "    def _watch_ef(self, ts_ms: int) -> None:"

GATE = '''    def _ef_price_gate(
        self, direction: str, ts_ms: int, evidence: Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Venue price gate, evaluated inside the signal on every EF tick.

        Returns (allow, reason, telemetry). Price comes from the live cached
        Predict.fun book in production; a replay driver may inject the archived
        venue book through `ef_price_feed`, which must be a callable
        (direction, ts_ms) -> {"ask": float, "age_s": float} using only data at
        or before ts_ms. No outcome information is ever consulted.
        """
        info: Dict[str, Any] = {
            "price_gate_ask": None, "price_gate_age_s": None,
            "price_gate_breakeven": None, "price_gate_edge": None,
            "price_gate_blocked": 0.0,
        }
        if not EF_PRICE_GATE_ENABLED:
            return True, "", info

        ask = age_s = None
        feed = getattr(self, "ef_price_feed", None)
        if feed is not None:
            try:
                q = feed(direction, int(ts_ms)) or {}
                ask = finite_float(q.get("ask"))
                age_s = finite_float(q.get("age_s"))
            except Exception as problem:
                self.record_error(f"EF price feed: {problem}")
        if ask is None:
            quote = self._ef_cached_quote(direction)
            if quote.get("available"):
                ask = finite_float(quote.get("reference_vwap")) or finite_float(quote.get("best_ask"))
                a_ms = finite_float(quote.get("age_ms"))
                age_s = None if a_ms is None else a_ms / 1000.0

        if ask is None or not (0.0 < ask < 1.0):
            info["price_gate_blocked"] = 1.0 if EF_PRICE_GATE_BLOCK_WHEN_NO_QUOTE else 0.0
            if EF_PRICE_GATE_BLOCK_WHEN_NO_QUOTE:
                return False, "price gate: no venue quote", info
            return True, "", info

        info["price_gate_ask"] = ask
        info["price_gate_age_s"] = age_s
        if age_s is not None and age_s > EF_PRICE_GATE_MAX_QUOTE_AGE_S:
            info["price_gate_blocked"] = 1.0
            return False, f"price gate: quote stale {age_s:.0f}s", info

        r = EF_PRICE_GATE_FEE_RATE
        breakeven = ask / (1.0 - r * (1.0 - ask))          # fee-adjusted cost of $1 payout
        p_model = clamp(safe_float(evidence.get("settlement_probability"), 0.0), 0.0, 1.0)
        edge = p_model - breakeven
        info["price_gate_breakeven"] = breakeven
        info["price_gate_edge"] = edge

        if ask > EF_PRICE_GATE_MAX_ASK:
            info["price_gate_blocked"] = 1.0
            return False, f"price gate: ask {ask:.3f} > {EF_PRICE_GATE_MAX_ASK:.2f}", info
        if edge < EF_PRICE_GATE_MIN_EDGE:
            info["price_gate_blocked"] = 1.0
            return False, (f"price gate: edge {edge:+.3f} < {EF_PRICE_GATE_MIN_EDGE:+.3f} "
                           f"(p={p_model:.3f} vs breakeven {breakeven:.3f})"), info
        return True, "", info

'''

HOOK_OLD = '''        evidence.update(fields)
        evidence["abstain_reason"] = "; ".join(blockers)
        self.ef_ledger.observe_compute(
            "ef_watch_compute_ms", (mono_ns() - watch_start_ns) / 1_000_000.0)

        if not fire:'''

HOOK_NEW = '''        evidence.update(fields)
        evidence["abstain_reason"] = "; ".join(blockers)

        # Build 36-PG: PRICE GATE, inside the signal. Runs only when the BTC
        # decision already says fire, so it can suppress but never create one.
        # Suppression falls through to the ordinary not-fired path below, which
        # sets no terminal latch and leaves current_ef None, so the next EF tick
        # re-evaluates and may fire later in this same candle at a better price.
        if fire:
            allowed, gate_reason, gate_info = self._ef_price_gate(
                direction, int(ts_ms), gate_evidence)
            evidence.update(gate_info)
            if not allowed:
                fire = False
                blockers = [gate_reason] + list(blockers)
                evidence["abstain_reason"] = "; ".join(blockers)

        self.ef_ledger.observe_compute(
            "ef_watch_compute_ms", (mono_ns() - watch_start_ns) / 1_000_000.0)

        if not fire:'''


def patch(text):
    for anchor in (CONST_ANCHOR, WATCH_MARK, HOOK_OLD):
        if text.count(anchor) != 1:
            raise SystemExit(f"anchor not unique ({text.count(anchor)}x): {anchor[:60]!r}")
    text = text.replace(CONST_ANCHOR, CONSTS, 1)
    text = text.replace(WATCH_MARK, GATE + WATCH_MARK, 1)
    text = text.replace(HOOK_OLD, HOOK_NEW, 1)
    text = text.replace('BUILD_REVISION = "9.3-build36-adaptive-ef-learner"',
                        'BUILD_REVISION = "9.3-build36-adaptive-ef-learner+price-gate"', 1)
    return text


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "btc_model_v9_3_build36.py")
    dest = src.with_name(src.stem + "_pg.py")
    out = patch(src.read_text())
    compile(out, str(dest), "exec")          # refuse to write anything that will not import
    dest.write_text(out)
    print(f"{dest}: +{len(out.splitlines()) - len(src.read_text().splitlines())} lines")
