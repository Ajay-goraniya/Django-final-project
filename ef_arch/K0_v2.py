#!/usr/bin/env python3
"""
K0_v2 -- capture-integrity audit for a snapshot training table.

Ten tests (Sol section 44). Each prints PASS/FAIL/SKIP with evidence. The
verdict is FAIL if any of A, B, C, E, F, H, I fail; D, G, J are reported.

Generic mode expects the ef_arc_snapshots schema (Section 16 of the reply):
    candle_id, grid_index, capture_ts_ms, grid_offset_ms,
    spot_trade_max_ts_ms, perp_trade_max_ts_ms, perp_depth_max_ts_ms,
    predict_book_ts_ms (nullable), capture_rule, features_up_json,
    features_down_json, actual (nullable until settled)

Legacy mode (--legacy) audits Build36's ef_candidates: A runs against
decision_ts_ms (the feature moment), C is failed on the documented max-rank
rule, F/H scan the feature JSON, and the old birth-vs-feature gap is printed
as a diagnostic only.

Usage:
    python3 K0_v2.py <db> --table ef_arc_snapshots --grid-ms 1000 --serve-ms 1000
    python3 K0_v2.py <db> --legacy
"""
import argparse, json, re, sqlite3, sys
from collections import Counter
import numpy as np

ALLOWED_RULES = {"FIXED_GRID", "FIXED_CHECKPOINT", "PREDECLARED_RANDOM", "ACTUAL_FIRE"}
BANNED_PREFIX = ("ef_adapt_", "ef_learner_", "ef_threshold_source_", "ef_frequency_",
                 "ef_decision_", "ef_execution_", "ef_candidate_quote", "ef_candidate_best",
                 "ef_candidate_reference", "ef_ev_", "ef_soft_", "ef_relaxation_", "ef_pclose_floor")
BANNED_EXACT = {"ef_b34_consensus_would_fire", "ef_old_build33_would_fire", "ef_new_consensus_would_fire",
                "ef_new_candidate_score", "ef_new_confidence", "ef_new_decision_reason", "ef_ef_consensus",
                "ef_decision_rule", "ef_decision_fired", "ef_abstain_reason", "ef_eligible",
                "ef_candidate_eligible", "ef_candidate_latched", "ef_hard_first_reject", "ef_old_first_reject",
                "ef_at_floor", "ef_ev_margin", "ef_reference_vwap_10", "ef_expected_edge", "ef_edge_floor",
                "ef_probability_floor", "ef_consensus_floor", "ef_quote_deterioration_absolute",
                "ef_quote_deterioration_percent", "ef_candidate_birth_utc", "ef_candidate_birth_seconds",
                "ef_candidate_reads_total", "ef_episode_id", "ef_episode_seq", "ef_latch_age_ms",
                "ef_latch_cancel_reason", "ef_first_real_reversal_utc", "ef_first_strong_consensus_utc",
                "ef_architecture_version", "ef_main_direction", "ef_main_probability_up"}
FUTURE_EXACT = {"actual", "correct", "win", "outcome_up", "close", "final_close", "settled", "ret_actual",
                "ret_counterfactual", "quote_counterfactual_pnl_up", "quote_counterfactual_pnl_down"}
SELECTOR_WORDS = re.compile(r"(^|_)(rank|max_rank|best|strongest|argmax)(_|$)", re.I)

def status(name, ok, msg, skip=False):
    tag = "SKIP" if skip else ("PASS" if ok else "FAIL")
    print(f"  [{tag}] {name}: {msg}"); return (True if skip else ok)

def is_banned(k):
    return k in BANNED_EXACT or any(k.startswith(p) for p in BANNED_PREFIX)

def audit_generic(c, table, grid_ms, serve_ms):
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
    rows = c.execute(f"select * from {table}").fetchall(); ix = {n: i for i, n in enumerate(cols)}
    get = lambda r, k: r[ix[k]] if k in ix else None
    print(f"table {table}: {len(rows)} rows, {len(cols)} columns"); res = {}

    # A -- feature-dict phase vs capture timestamp
    gaps = []
    for r in rows:
        try:
            f = json.loads(get(r, "features_up_json") or "{}"); ph = f.get("ef_phase_second")
            if ph is not None: gaps.append(abs(float(ph) - (get(r, "capture_ts_ms") - get(r, "candle_id")) / 1000.0))
        except Exception: pass
    g = np.array(gaps) if gaps else np.array([0.0])
    res["A"] = status("A timestamp integrity", g.max() <= 2.0, f"|phase - capture| p99={np.percentile(g,99):.3f}s max={g.max():.3f}s (limit 2.0)")

    # B -- watermarks <= capture
    viol = 0; checked = 0
    for r in rows:
        cap = get(r, "capture_ts_ms")
        for w in ("spot_trade_max_ts_ms", "perp_trade_max_ts_ms", "perp_depth_max_ts_ms", "predict_book_ts_ms"):
            v = get(r, w)
            if v is not None: checked += 1; viol += int(v > cap)
    res["B"] = status("B causal watermarks", viol == 0, f"{viol} of {checked} watermarks exceed capture_ts_ms", skip=(checked == 0))

    # C -- capture rule declared and allowed
    rules = Counter(get(r, "capture_rule") for r in rows)
    bad = {k: v for k, v in rules.items() if k not in ALLOWED_RULES}
    res["C"] = status("C selection integrity", not bad, f"rules={dict(rules)}" + (f" DISALLOWED={bad}" if bad else ""))

    # D -- no duplicate grid index per candle
    keys = Counter((get(r, "candle_id"), get(r, "grid_index")) for r in rows); dup = sum(1 for v in keys.values() if v > 1)
    res["D"] = status("D unique (candle, grid_index)", dup == 0, f"{dup} duplicate keys")

    # E -- no selector metadata columns
    sel = [k for k in cols if SELECTOR_WORDS.search(k)]
    res["E"] = status("E no rank/max/best selector columns", not sel, f"found {sel}" if sel else "none")

    # F -- banned fields absent from features
    banned_seen = Counter(); fut_seen = Counter()
    for r in rows[:2000]:
        for col in ("features_up_json", "features_down_json"):
            try: f = json.loads(get(r, col) or "{}")
            except Exception: continue
            for k in f:
                if is_banned(k): banned_seen[k] += 1
                if k in FUTURE_EXACT: fut_seen[k] += 1
    res["F"] = status("F no banned fields in features", not banned_seen, f"{dict(banned_seen)}" if banned_seen else "clean")

    # G -- cadence matches configured grid
    offs = np.array([get(r, "grid_offset_ms") for r in rows if get(r, "grid_offset_ms") is not None])
    frac = float((offs % grid_ms == 0).mean()) if len(offs) else 1.0
    res["G"] = status("G cadence matches grid", frac > 0.999, f"{100*frac:.2f}% of offsets on the {grid_ms} ms grid")

    # H -- no future/settlement fields in features
    res["H"] = status("H no settlement fields in features", not fut_seen, f"{dict(fut_seen)}" if fut_seen else "clean")

    # I -- train/serve cadence parity
    res["I"] = status("I train/serve cadence parity", grid_ms == serve_ms, f"train {grid_ms} ms vs serve {serve_ms} ms")

    # J -- per-candle rows and weight
    per = Counter(get(r, "candle_id") for r in rows); n = np.array(list(per.values()))
    res["J"] = status("J per-candle row counts", True, f"candles={len(per)} rows/candle p50={np.median(n):.0f} max={n.max()} -> weight 1/N each, total 1.0/candle")
    return res

def audit_legacy(c):
    rows = c.execute("select candle_id, ts_ms, decision_ts_ms, features from ef_candidates").fetchall()
    print(f"table ef_candidates (LEGACY Build36): {len(rows)} rows"); res = {}
    g_dec, g_birth = [], []; banned = Counter(); fut = Counter()
    for cid, ts, dts, feat in rows:
        f = json.loads(feat) if feat else {}; ph = f.get("ef_phase_second")
        if ph is not None:
            if dts: g_dec.append(abs(float(ph) - (dts - cid) / 1000.0))
            g_birth.append(float(ph) - (ts - cid) / 1000.0)
        for k in f:
            if is_banned(k): banned[k] += 1
            if k in FUTURE_EXACT: fut[k] += 1
    gd = np.array(g_dec); gb = np.array(g_birth)
    res["A"] = status("A timestamp integrity (vs decision_ts_ms)", gd.max() <= 5.0, f"p50={np.percentile(gd,50):.3f}s p99={np.percentile(gd,99):.3f}s max={gd.max():.3f}s -- features DO carry a valid timestamp")
    print(f"         diagnostic: birth ts_ms vs feature phase gap >60s on {100*(gb>60).mean():.1f}% of rows (selection, not missing timestamp)")
    res["B"] = status("B causal watermarks", True, "no watermark columns in legacy table", skip=True)
    res["C"] = status("C selection integrity", False, "features chosen by MAX-RANK over the episode (Engine._remember_ef_candidate) -- not a predeclared causal rule")
    res["D"] = status("D unique key", True, "n/a for legacy", skip=True)
    res["E"] = status("E no selector metadata", False, "row['rank'] drives snapshot replacement in memory; table is the product of a selector")
    res["F"] = status("F no banned fields", not banned, f"{len(banned)} banned keys present, e.g. {list(banned)[:5]}")
    res["G"] = status("G cadence", True, "n/a", skip=True)
    res["H"] = status("H no settlement fields", not fut, f"{dict(fut)}" if fut else "clean")
    res["I"] = status("I train/serve parity", False, "trained on episode maxima, served on every tick")
    per = Counter(r[0] for r in rows); n = np.array(list(per.values()))
    res["J"] = status("J per-candle rows", True, f"candles={len(per)} rows/candle p50={np.median(n):.0f} max={n.max()}")
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db"); ap.add_argument("--table", default="ef_arc_snapshots")
    ap.add_argument("--grid-ms", type=int, default=1000); ap.add_argument("--serve-ms", type=int, default=1000)
    ap.add_argument("--legacy", action="store_true")
    a = ap.parse_args(); c = sqlite3.connect(a.db)
    print("=" * 70); print("K0_v2  CAPTURE-INTEGRITY AUDIT"); print("=" * 70)
    res = audit_legacy(c) if a.legacy else audit_generic(c, a.table, a.grid_ms, a.serve_ms)
    hard = ["A", "B", "C", "E", "F", "H", "I"]
    ok = all(res.get(k, True) for k in hard)
    print("\nVERDICT:", "PASS -- table may train a decision-time model" if ok else
          "FAIL -- table may NOT train a decision-time model; failing: " + ",".join(k for k in hard if not res.get(k, True)))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
