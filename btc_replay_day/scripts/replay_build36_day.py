#!/usr/bin/env python3
"""
replay_build36.py -- drive the REAL Build36 production code over the 2026-08-01
replay dataset, causally, with MASTER OFF.

What is production and untouched:
  * EFPerpPrep.on_trade / on_depth            (perp microstructure)
  * Engine._process_message -> _on_trade/_on_kline  (spot lane, live path)
  * Engine._compute_features / _compute_ef_metrics / _watch_ef / _ef_decide / _emit_ef
  * Store settlement, grading, MASTER-OFF shadow accounting, EFLearner
No signal logic, threshold or gate is modified.

Deviations from live, all documented in the output JSON:
  1. now_ms()/mono_ns() are driven by the REPLAY EVENT CLOCK, not wall clock.
     Required: latch/confirm windows and freshness are measured in event time.
  2. Spot depth does not exist in any public archive. Build36 handles this in
     production: _compute_ef_metrics sets micro_source="PERP" whenever
     ef_perp_prep.snapshot(...)["ready"], and then EVERY EF microstructure input
     (deltas, path, zone books, replenishment, OFI, microprice) comes from the
     perp lane. Spot supplies candle/settlement geometry only.
  3. Live EF recompute cadence is driven by spot message arrival (>=10ms apart).
     Spot depth@100ms is unarchived, so the 10ms EF tick is driven by real perp
     depth arrivals instead. Only data with timestamp <= T is ever used.
  4. Intra-candle klines are derived causally from spot aggTrades in
     [candle_open, T]. The CLOSED bar uses the official archived kline at its
     own close time (complete = not future). Derived-vs-official drift is
     reported as a validation metric.
  5. Predict.fun books are unavailable. Build36 reads them only in
     _ef_cached_quote, whose docstring states it is diagnostic and "nothing here
     can veto or delay EF"; _watch_ef states "Predict.fun is not read here".
     So EF direction/frequency/accuracy are faithful; quote ECONOMICS are not.
"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import daycfg as CFG
import argparse, glob, importlib.util, json, os, pathlib, sys, time
import pyarrow.parquet as pq

WIN_START_US = CFG.WIN_START_US
WIN_END_US   = CFG.WIN_END_US
CANDLE_MS    = 300_000

ROOT = pathlib.Path(__file__).resolve().parent
DATA = CFG.NORM


def load_module(path):
    spec = importlib.util.spec_from_file_location("b36mod", str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["b36mod"] = mod
    spec.loader.exec_module(mod)
    return mod


class ReplayClock:
    __slots__ = ("ms",)
    def __init__(self): self.ms = WIN_START_US // 1000


def hour_events(h, clock_src="recv"):
    """Yield (delivery_ms, order, kind, payload) for one UTC hour, merged."""
    ev = []
    # ---- perp depth20 (Tardis incremental_book_L2 reconstruction)
    f = DATA / f"perp_depth20_{h:02d}.parquet"
    if f.exists():
        t = pq.read_table(f)
        cols = {c: t.column(c).to_pylist() for c in t.column_names}
        n = len(cols["timestamp"])
        bpx = [cols[f"bid_px_{i}"] for i in range(20)]
        bqt = [cols[f"bid_qty_{i}"] for i in range(20)]
        apx = [cols[f"ask_px_{i}"] for i in range(20)]
        aqt = [cols[f"ask_qty_{i}"] for i in range(20)]
        lts, xts = cols["local_timestamp"], cols["timestamp"]
        for i in range(n):
            ev.append((lts[i] // 1000 if clock_src == "recv" else xts[i] // 1000,
                       0, "PD", i))
        depth_cols = (bpx, bqt, apx, aqt, xts, n)
    else:
        depth_cols = None
    # ---- perp trades (Tardis tick)
    f = DATA / f"perp_trades_{h:02d}.parquet"
    pt = None
    if f.exists():
        t = pq.read_table(f, columns=["timestamp", "local_timestamp", "id",
                                      "aggressor", "price", "quantity"])
        pt = {c: t.column(c).to_pylist() for c in t.column_names}
        for i in range(len(pt["timestamp"])):
            ev.append((pt["local_timestamp"][i] // 1000 if clock_src == "recv"
                       else pt["timestamp"][i] // 1000, 1, "PT", i))
    # ---- spot aggTrades (exchange clock only; no receive clock archived)
    f = DATA / f"spot_aggtrades_{h:02d}.parquet"
    st = None
    if f.exists():
        t = pq.read_table(f, columns=["timestamp", "agg_trade_id", "price",
                                      "quantity", "is_buyer_maker"])
        st = {c: t.column(c).to_pylist() for c in t.column_names}
        for i in range(len(st["timestamp"])):
            ev.append((st["timestamp"][i] // 1000, 2, "ST", i))
    ev.sort(key=lambda r: (r[0], r[1], r[3]))
    return ev, depth_cols, pt, st


def _safe(fn):
    try:
        return fn()
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def snap_learner(engine, cid):
    row = {"candle_open_ms": cid}
    row["learner"] = _safe(lambda: engine.ef_learner.snapshot())
    row["frequency_ratio"] = _safe(lambda: engine.ef_learner.frequency_ratio())
    row["frequency_guard"] = _safe(lambda: engine.ef_learner.frequency_guard_active())
    row["starvation"] = _safe(lambda: engine.ef_learner.starvation_warning())
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT.parent.parent / "ef_replay" / "work" / "btc_model_v9_3_BUILD36.py"))
    ap.add_argument("--db", default=str(CFG.DAYROOT / f"build36_replay_{CFG.DATE}.sqlite3"))
    ap.add_argument("--hours", default="0-23")
    ap.add_argument("--out", default=str(CFG.DAYROOT / f"replay_result_{CFG.DATE}.json"))
    ap.add_argument("--clock", default="recv", choices=["recv", "exchange"])
    ap.add_argument("--progress", type=int, default=250_000)
    ap.add_argument("--grid-dump", default=None,
                    help="CSV path: dump Build36's own fair_p_up / sigma / "
                         "settlement_probability_base on a fixed 1-second grid "
                         "(harness-side observation, no model change)")
    args = ap.parse_args()

    a, _, b = args.hours.partition("-")
    hours = list(range(int(a), int(b or a) + 1))

    b36 = load_module(args.model)
    clock = ReplayClock()
    # Drive every model clock from replay event time (deviation 1).
    b36.now_ms = lambda: clock.ms
    b36.mono_ns = lambda: clock.ms * 1_000_000

    dbp = pathlib.Path(args.db)
    if dbp.exists():
        dbp.unlink()
    store = b36.Store(dbp)
    # Stamp this build's ownership marker so the finished database can be read
    # straight back with `--ef-report` instead of being refused as foreign.
    store.claim_database_namespace()
    engine = b36.Engine(store)
    # MASTER must be OFF: signals fire, are recorded, settled and counted, but
    # no venue order is ever built. Assert rather than assume.
    can, why = engine.controls.may_execute("EF", clock.ms)
    assert not can, f"MASTER unexpectedly ON: {why}"
    # In live, the PerpLaneThread websockets declare their lane live. In replay
    # this driver IS the feed, so it makes the same production declaration via
    # the same API. This is feed plumbing, not signal logic: staleness during
    # the 6 real capture gaps is still enforced by _evaluate_readiness_locked.
    engine.ef_perp_prep.set_lane_status("trade", b36.EF_PERP_LANE_LIVE_STATE)
    engine.ef_perp_prep.set_lane_status("depth", b36.EF_PERP_LANE_LIVE_STATE)

    # official closed klines, keyed by candle open ms
    kl = pq.read_table(DATA / "spot_klines_5m.parquet").to_pandas()
    official = {int(r.open_time // 1000): r for r in kl.itertuples()}

    stats = {"events": 0, "PD": 0, "PT": 0, "ST": 0, "KL": 0, "ef_ticks": 0,
             "perp_ready_ticks": 0, "micro_perp": 0, "micro_spot": 0,
             "candles_started": 0, "candles_settled": 0,
             "kline_drift": {"max_close_abs": 0.0, "max_high_abs": 0.0,
                             "max_low_abs": 0.0}}
    cur = {"cid": None, "o": None, "h": None, "l": None, "c": None, "v": 0.0}
    blockers = {}
    fires = []
    timeline = []
    seen_fire = set()
    last_kline_emit = 0
    ef_last = 0
    t0 = time.time()
    grid_fh = None; grid_next = None
    if args.grid_dump:
        grid_fh = open(args.grid_dump, "w")
        grid_fh.write("ts_ms,candle_open_ms,phase_s,seconds_left,spot,fair_p_up,"
                      "sigma_per_root_second,ef_direction,settlement_probability_base,"
                      "settlement_probability,extension_sigma,inputs_ready,micro_source\n")

    def emit_kline(cid, closed, ts_ms):
        if cur["o"] is None:
            return
        if closed and cid in official:
            r = official[cid]
            k = {"t": cid, "o": float(r.open), "h": float(r.high), "l": float(r.low),
                 "c": float(r.close), "v": float(r.volume), "x": True,
                 "T": int(r.close_time // 1000)}
            stats["kline_drift"]["max_close_abs"] = max(
                stats["kline_drift"]["max_close_abs"], abs(float(r.close) - cur["c"]))
            stats["kline_drift"]["max_high_abs"] = max(
                stats["kline_drift"]["max_high_abs"], abs(float(r.high) - cur["h"]))
            stats["kline_drift"]["max_low_abs"] = max(
                stats["kline_drift"]["max_low_abs"], abs(float(r.low) - cur["l"]))
        else:
            k = {"t": cid, "o": cur["o"], "h": cur["h"], "l": cur["l"],
                 "c": cur["c"], "v": cur["v"], "x": False, "T": cid + CANDLE_MS - 1}
        engine._process_message("btcusdt@kline_5m",
                                {"e": "kline", "E": ts_ms, "k": k}, ts_ms)
        stats["KL"] += 1

    for h in hours:
        ev, dcols, pt, st = hour_events(h, args.clock)
        bpx = bqt = apx = aqt = xts = None
        if dcols:
            bpx, bqt, apx, aqt, xts, _ = dcols
        for delivery_ms, _order, kind, i in ev:
            clock.ms = delivery_ms
            stats["events"] += 1
            stats[kind] += 1

            if kind == "PD":
                bids = [[bpx[l][i], bqt[l][i]] for l in range(20) if bpx[l][i] is not None]
                asks = [[apx[l][i], aqt[l][i]] for l in range(20) if apx[l][i] is not None]
                # update_id left None on purpose: the reconstruction carries no
                # exchange update id and inventing one would be fabrication.
                engine.ef_perp_prep.on_depth({"b": bids, "a": asks}, delivery_ms)
            elif kind == "PT":
                engine.ef_perp_prep.on_trade(
                    {"p": pt["price"][i], "q": pt["quantity"][i],
                     "m": pt["aggressor"][i] < 0, "a": pt["id"][i],
                     "T": pt["timestamp"][i] // 1000}, delivery_ms)
            elif kind == "ST":
                px, qty = st["price"][i], st["quantity"][i]
                cid = (delivery_ms // CANDLE_MS) * CANDLE_MS
                if cur["cid"] != cid:
                    if cur["cid"] is not None:
                        emit_kline(cur["cid"], True, cur["cid"] + CANDLE_MS - 1)
                        stats["candles_settled"] += 1
                        timeline.append(snap_learner(engine, cur["cid"]))
                    cur.update(cid=cid, o=px, h=px, l=px, c=px, v=0.0)
                    stats["candles_started"] += 1
                    last_kline_emit = 0
                cur["h"] = max(cur["h"], px); cur["l"] = min(cur["l"], px)
                cur["c"] = px; cur["v"] += qty
                engine._process_message(
                    "btcusdt@aggTrade",
                    {"e": "aggTrade", "E": delivery_ms, "p": px, "q": qty,
                     "m": bool(st["is_buyer_maker"][i]),
                     "a": st["agg_trade_id"][i], "T": delivery_ms}, delivery_ms)
                if delivery_ms - last_kline_emit >= 1000:
                    emit_kline(cid, False, delivery_ms)
                    last_kline_emit = delivery_ms

            # EF tick at the production interval, driven by real event arrivals
            if delivery_ms - ef_last >= b36.EF_COMPUTE_INTERVAL_MS:
                ef_last = delivery_ms
                engine._compute_ef_metrics(delivery_ms)
                stats["ef_ticks"] += 1
                if grid_fh is not None:
                    # fixed wall-clock 1 s grid: first EF tick at or after each
                    # whole second records the state that exists at that moment
                    sec = delivery_ms // 1000
                    if grid_next is None or sec >= grid_next:
                        grid_next = sec + 1
                        fe = engine.feature or {}; em_ = engine.ef_metrics or {}
                        cid_ = int(engine.candle["time"]) if engine.candle else 0
                        grid_fh.write(f"{delivery_ms},{cid_},{(delivery_ms-cid_)/1000:.3f},"
                                      f"{fe.get('seconds_left','')},{fe.get('price','')},"
                                      f"{fe.get('fair_p_up','')},{fe.get('sigma_per_root_second','')},"
                                      f"{em_.get('direction','')},{em_.get('settlement_probability_base','')},"
                                      f"{em_.get('settlement_probability','')},{em_.get('extension_sigma','')},"
                                      f"{int(bool(em_.get('inputs_ready')))},{em_.get('micro_source','')}\n")
                em = engine.ef_metrics or {}
                if em.get("inputs_ready"): stats["perp_ready_ticks"] += 1
                src = em.get("micro_source")
                if src == "PERP":
                    stats["micro_perp"] += 1
                elif src:
                    stats["micro_spot"] += 1
                engine._watch_ef(delivery_ms)
                reason = str((engine.ef_monitor or {}).get("new_decision_reason")
                             or (engine.ef_monitor or {}).get("status") or "")[:70]
                if reason:
                    blockers[reason] = blockers.get(reason, 0) + 1
                cef = engine.current_ef
                if cef is not None:
                    key = (int(engine.candle["time"]), cef.direction)
                    if key not in seen_fire:
                        seen_fire.add(key)
                        ev_ = engine.ef_metrics or {}
                        fires.append({
                            "candle_open_ms": key[0], "direction": cef.direction,
                            "fire_ts_ms": delivery_ms,
                            "fire_second": round((delivery_ms - key[0]) / 1000.0, 1),
                            "micro_source": ev_.get("micro_source"),
                            "extension_sigma": ev_.get("extension_sigma"),
                            "real_reversal_score": ev_.get("real_reversal_score"),
                            "settlement_probability": ev_.get("settlement_probability"),
                            "chop": ev_.get("chop"),
                            "control_transfer": ev_.get("control_transfer"),
                            "reason": (cef.features or {}).get("ef_new_decision_reason"),
                        })

            if stats["events"] % args.progress == 0:
                el = time.time() - t0
                print(f"  h{h:02d} ev={stats['events']:,} ef_ticks={stats['ef_ticks']:,} "
                      f"perp={stats['micro_perp']:,} "
                      f"rate={stats['events']/max(el,1e-9):,.0f}/s "
                      f"elapsed={el:.0f}s", flush=True)

    # final candle close
    if cur["cid"] is not None:
        emit_kline(cur["cid"], True, cur["cid"] + CANDLE_MS - 1)
        stats["candles_settled"] += 1

    if grid_fh is not None:
        grid_fh.close()
    stats["elapsed_s"] = round(time.time() - t0, 1)
    result = {"stats": stats, "blockers": dict(sorted(blockers.items(),
                   key=lambda kv: -kv[1])[:40]), "fires": fires, "timeline": timeline,
              "learner_final": _safe(lambda: engine.ef_learner.snapshot()),
              "learner_state": _safe(lambda: engine.ef_learner.as_dict()),
              "starvation_final": _safe(lambda: engine.ef_learner.starvation_warning()),
              "ef_metrics_sample": {k: v for k, v in list((engine.ef_metrics or {}).items())[:40]},
              "store_metrics": store.metrics(),
              "ef_audit": store.ef_performance_audit()}
    try:
        result["ef_audit_text"] = b36.format_ef_performance_audit(result["ef_audit"])
    except Exception as exc:
        result["ef_audit_text"] = f"(format failed: {exc})"
    pathlib.Path(args.out).write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(stats, indent=2))
    print(result["ef_audit_text"])
    store.close()


if __name__ == "__main__":
    main()
