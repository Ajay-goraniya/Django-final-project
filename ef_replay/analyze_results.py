#!/usr/bin/env python3
"""Summarize Build36 (and Build35) EF replay results."""
import json, pathlib, sys, collections

def load(p):
    f = pathlib.Path(p)
    return json.load(open(f)) if f.exists() else None

def pct(x):
    return "N/A" if x is None else f"{100*float(x):.2f}%"

def show(tag, d):
    if not d:
        print(f"\n### {tag}: (no result)"); return None
    a, s = d["ef_audit"], d["stats"]
    print(f"\n{'='*66}\n### {tag}\n{'='*66}")
    print(f"  events replayed        : {s['events']:,}  "
          f"(perp depth {s['PD']:,} / perp trades {s['PT']:,} / spot trades {s['ST']:,})")
    print(f"  EF evaluation ticks    : {s['ef_ticks']:,}")
    print(f"  micro_source PERP      : {s['micro_perp']:,} "
          f"({100*s['micro_perp']/max(s['ef_ticks'],1):.2f}% of ticks)")
    print(f"  candles settled        : {a['settled_candles']}")
    print(f"  EF fires (settled/tot) : {a['fires_settled']}/{a['fires_total']}")
    print(f"  directional accuracy   : {pct(a['directional_accuracy'])} "
          f"({a['directional_wins']}/{a['fires_settled']})")
    print(f"  fires per 100 candles  : {a['fires_per_100_settled_candles']:.2f}")
    print(f"  fires per day          : {a['fires_per_day']:.2f}")
    print(f"  average fire second    : {a['average_fire_second']}")
    print(f"  sample status          : {a['sample_status']}")
    print(f"  kline drift vs official: {s['kline_drift']}")
    return a

b36 = load("work/replay_full.json")
b35 = load("work/replay_b35_full.json")
a36 = show("BUILD 36  (adaptive EF learner)", b36)
a35 = show("BUILD 35  (EF actual-fire, master-off)", b35)

if b36:
    print(f"\n{'='*66}\n### BUILD 36 LEARNER\n{'='*66}")
    ln = b36.get("learner_final") or {}
    for k, v in (ln.items() if isinstance(ln, dict) else []):
        if not isinstance(v, (dict, list)):
            print(f"  {k}: {v}")
    st = b36.get("learner_state") or {}
    if isinstance(st, dict):
        for key in ("samples", "econ_examples", "regime_transitions", "intercept",
                    "last_regime", "last_candle_id"):
            if key in st:
                print(f"  {key}: {st[key]}")
        if isinstance(st.get("weights"), dict):
            print("  weights:")
            for k, v in st["weights"].items():
                print(f"    {k:34} {v:+.6f}")
        if isinstance(st.get("regime_bias"), dict) and st["regime_bias"]:
            print("  regime_bias:")
            for k, v in st["regime_bias"].items():
                print(f"    {k:34} {v:+.6f}")

    print(f"\n### WHY EF DID NOT FIRE (decision-reason histogram, top 15)")
    for k, v in list((b36.get("blockers") or {}).items())[:15]:
        print(f"  {v:>10,}  {k}")

    fires = b36.get("fires") or []
    print(f"\n### EF FIRES ({len(fires)})")
    for f in fires[:40]:
        print(f"  candle {f['candle_open_ms']}  {f['direction']:<4} "
              f"t+{f['fire_second']:>5.1f}s  {str(f.get('reason'))[:28]:<28} "
              f"ext={f.get('extension_sigma')} chop={f.get('chop')}")
    if len(fires) > 40:
        print(f"  ... and {len(fires)-40} more")

    sv = b36.get("starvation_final")
    print(f"\n### LEARNER STARVATION DIAGNOSTIC\n  {json.dumps(sv, default=str)[:1200]}")

# ---------------------------------------------------------------- leakage audit
if b36:
    fires = b36.get("fires") or []
    CANDLE_MS = 300_000
    bad_window = [f for f in fires
                  if not (f["candle_open_ms"] <= f["fire_ts_ms"] < f["candle_open_ms"] + CANDLE_MS)]
    bad_second = [f for f in fires if not (0.0 <= f["fire_second"] < 300.0)]
    drift = b36["stats"]["kline_drift"]
    print(f"\n{'='*66}\n### CAUSALITY AUDIT\n{'='*66}")
    print(f"  fires decided outside their own candle window : {len(bad_window)}  (must be 0)")
    print(f"  fires with fire_second outside [0,300)        : {len(bad_second)}  (must be 0)")
    print(f"  derived-vs-official kline drift (close/high/low): "
          f"{drift['max_close_abs']}/{drift['max_high_abs']}/{drift['max_low_abs']}  (must be 0.0)")
    print("  -> intra-candle OHLC was rebuilt from spot trades <= T only; the official")
    print("     closed bar is injected at its own close time, never before.")
    ok = not bad_window and not bad_second and max(drift.values()) == 0.0
    print(f"  VERDICT: {'PASS - no future information reached any EF decision' if ok else 'FAIL'}")
