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
import argparse, glob, importlib.util, json, os, pathlib, sys, time
import pyarrow.parquet as pq

import datetime as _dt, os as _os
DATE = _os.environ.get("REPLAY_DATE", "2026-08-31")
_W0 = int(_dt.datetime.strptime(DATE, "%Y-%m-%d").replace(tzinfo=_dt.timezone.utc).timestamp())
WIN_START_US = _W0 * 1_000_000
WIN_END_US   = WIN_START_US + 86_400_000_000
WEEK_DATES = [d for d in _os.environ.get("REPLAY_WEEK", DATE).split(",") if d]
CANDLE_LIST = _os.environ.get("CANDLE_LIST", "")
WARMUP_MS = int(_os.environ.get("WARMUP_MS", 900_000))   # 15 min of lead-in per candle
CANDLE_MS    = 300_000

ROOT = pathlib.Path(__file__).resolve().parent
DATA_HOLDER = {"dir": ROOT.parent / DATE / "normalized"}
CURRENT_DAY = [DATE]
HAS_PERP = [True]
REPO = ROOT.parents[1]


def load_price_feed(dates):
    """(window_epoch, SIDE, offset_s) -> (ask, age_s) for the price gate.

    Real venue prices only. Where the archived order book exists the executable
    ask-ladder price is used. Where it does not, the trade-inferred ask is used
    after the measured inferred->executable calibration, because the raw
    inferred print runs ~1.8c cheap and an uncalibrated price would make the
    gate systematically too permissive. Nothing is fabricated: a market-second
    with neither source is simply absent, and the gate treats absence as
    "cannot price, do not fire".
    """
    import pyarrow.parquet as _pq
    sys.path.insert(0, str(ROOT))
    from calibrate_inferred import build as _cal_build, apply as _cal_apply
    edges, eff, _pairs = _cal_build()
    cols = ["window_epoch", "side", "offset_s", "quote_source", "best_ask",
            "ask_inferred", "ask_age_s", "vwap_s10", "shares_s10", "fill_ok_s10"]
    feed, n_book, n_cal = {}, 0, 0
    for d in dates:
        f = REPO / f"week_data/predictfun/quotes_1s_unified/poly_1s_{d}.parquet"
        if not f.exists():
            print(f"  price feed: NO QUOTES for {d}", flush=True)
            continue
        t = _pq.read_table(f, columns=[c for c in cols if c in _pq.read_schema(f).names])
        c = {n: t.column(n).to_pylist() for n in t.column_names}
        for i in range(t.num_rows):
            srcq = c["quote_source"][i]
            if srcq == "none":
                continue
            if srcq == "book":
                a = c.get("vwap_s10", [None] * t.num_rows)[i]
                if not (a and c.get("fill_ok_s10", [None] * t.num_rows)[i]):
                    a = c["best_ask"][i]
                age = 0.0
                n_book += 1
            else:
                raw = c["ask_inferred"][i]
                a = _cal_apply(edges, eff, raw) if raw else None
                age = (c.get("ask_age_s") or [None] * t.num_rows)[i]
                n_cal += 1
            if a is None or not (0.0 < a < 1.0):
                continue
            feed[(c["window_epoch"][i], str(c["side"][i]).upper(), c["offset_s"][i])] = (
                float(a), None if age is None else float(age))
    print(f"  price feed: {len(feed):,} market-seconds  ({n_book:,} book, {n_cal:,} calibrated)", flush=True)
    return feed


def load_module(path):
    spec = importlib.util.spec_from_file_location("b36mod", str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["b36mod"] = mod
    spec.loader.exec_module(mod)
    return mod


class ReplayClock:
    __slots__ = ("ms",)
    def __init__(self): self.ms = WIN_START_US // 1000


import pyarrow.compute as _pc

_TBL_CACHE = {}


def _table(day, h, kind, cols=None):
    """Arrow table for one hour, cached. Reading the parquet is cheap; turning
    it into Python is not, so the raw table is what we keep."""
    key = (day, h, kind)
    t = _TBL_CACHE.get(key)
    if t is None:
        f = DATA_HOLDER["dir"] / f"{kind}_{h:02d}.parquet"
        if not f.exists():
            _TBL_CACHE[key] = False
            return None
        t = pq.read_table(f, columns=cols)
        if len(_TBL_CACHE) > 9:
            for k in list(_TBL_CACHE)[:3]:
                _TBL_CACHE.pop(k, None)
        _TBL_CACHE[key] = t
    return None if t is False else t


def window_events(day, h, t0_ms, t1_ms, clock_src="recv"):
    """Events for hour `h` restricted to [t0_ms, t1_ms).

    Only rows inside the window are converted to Python. A whole hour of
    depth20 is ~11M Python objects; the windows we actually score are a small
    fraction of that, so slicing before converting is what makes this tractable.
    """
    ev = []
    lo, hi = t0_ms * 1000, t1_ms * 1000
    clk = "local_timestamp" if clock_src == "recv" else "timestamp"

    depth_cols = None
    t = _table(day, h, "perp_depth20")
    if t is not None:
        col = t.column(clk)
        t = t.filter(_pc.and_(_pc.greater_equal(col, lo), _pc.less(col, hi)))
        if t.num_rows:
            cols = {c: t.column(c).to_pylist() for c in t.column_names}
            n = t.num_rows
            bpx = [cols[f"bid_px_{i}"] for i in range(20)]
            bqt = [cols[f"bid_qty_{i}"] for i in range(20)]
            apx = [cols[f"ask_px_{i}"] for i in range(20)]
            aqt = [cols[f"ask_qty_{i}"] for i in range(20)]
            lts, xts = cols["local_timestamp"], cols["timestamp"]
            keep = {}
            for i in range(n):
                keep[(lts[i] if clock_src == "recv" else xts[i]) // 100_000] = i
            for i in sorted(keep.values()):
                ev.append((lts[i] // 1000 if clock_src == "recv" else xts[i] // 1000,
                           0, "PD", i))
            depth_cols = (bpx, bqt, apx, aqt, xts, n)

    pt = None
    t = _table(day, h, "perp_trades",
               ["timestamp", "local_timestamp", "id", "aggressor", "price", "quantity"])
    if t is not None:
        col = t.column(clk)
        t = t.filter(_pc.and_(_pc.greater_equal(col, lo), _pc.less(col, hi)))
        if t.num_rows:
            pt = {c: t.column(c).to_pylist() for c in t.column_names}
            for i in range(t.num_rows):
                ev.append((pt[clk][i] // 1000, 1, "PT", i))

    st = None
    t = _table(day, h, "spot_aggtrades",
               ["timestamp", "agg_trade_id", "price", "quantity", "is_buyer_maker"])
    if t is not None:
        col = t.column("timestamp")
        t = t.filter(_pc.and_(_pc.greater_equal(col, lo), _pc.less(col, hi)))
        if t.num_rows:
            st = {c: t.column(c).to_pylist() for c in t.column_names}
            for i in range(t.num_rows):
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
    ap.add_argument("--model", default=str(ROOT / "btc_model_v9_4.py"))
    ap.add_argument("--db", default=str(ROOT.parent / "v94_week.sqlite3"))
    ap.add_argument("--hours", default="0-23")
    ap.add_argument("--out", default=str(ROOT.parent / "v94_week_result.json"))
    ap.add_argument("--clock", default="recv", choices=["recv", "exchange"])
    ap.add_argument("--shard", default="",
                    help="i/n -- replay only shard i of n of the candle list. Safe ONLY for "
                         "builds with no cross-candle state: the r6.4 family has no learner, "
                         "so its candle windows are independent. Sharding a learner build "
                         "would split its learning history and is not equivalent.")
    ap.add_argument("--price-feed", action="store_true",
                    help="attach the archived venue price to engine.ef_price_feed so an "
                         "in-signal price gate can read it (real prices only)")
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
    if hasattr(store, "claim_database_namespace"):
        store.claim_database_namespace()
    engine = b36.Engine(store)
    if args.price_feed:
        PRICES = load_price_feed(WEEK_DATES)

        def _ef_price_feed(direction, ts_ms, _p=PRICES):
            """Causal: only the quote for the second the decision is made in."""
            cid = (int(ts_ms) // CANDLE_MS) * CANDLE_MS
            hit = _p.get((cid // 1000, str(direction).upper(), (int(ts_ms) - cid) // 1000))
            if hit is None:
                return None
            return {"ask": hit[0], "age_s": hit[1]}

        engine.ef_price_feed = _ef_price_feed
        print("  price gate: venue feed attached to engine", flush=True)
    # MASTER must be OFF: signals fire, are recorded, settled and counted, but
    # no venue order is ever built. Assert rather than assume.
    can, why = engine.controls.may_execute("EF", clock.ms)
    assert not can, f"MASTER unexpectedly ON: {why}"
    # In live, the PerpLaneThread websockets declare their lane live. In replay
    # this driver IS the feed, so it makes the same production declaration via
    # the same API. This is feed plumbing, not signal logic: staleness during
    # the 6 real capture gaps is still enforced by _evaluate_readiness_locked.
    HAS_PERP[0] = hasattr(engine, "ef_perp_prep")
    if HAS_PERP[0]:
        live = getattr(b36, "EF_PERP_LANE_LIVE_STATE", None)
        if live is not None:
            engine.ef_perp_prep.set_lane_status("trade", live)
            engine.ef_perp_prep.set_lane_status("depth", live)
    else:
        print("  model has NO perp lane (r6.4 family): depth goes to the spot "
              "depth5@100ms slot only, perp trades are not fed", flush=True)

    # official closed klines, keyed by candle open ms
    kl = pq.read_table(DATA_HOLDER["dir"] / "spot_klines_5m.parquet").to_pandas()
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
    state = {"ef_last": 0, "last_kline_emit": 0, "grid_next": None}
    t0 = time.time()
    spot_depth_last = [0]
    grid_fh = None
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

    def run_hours():
      """Replay ONLY the selected candles, each preceded by WARMUP_MS of real
      data so EF's trade/depth/kline history is warm before the candle opens.
      Windows are walked in chronological order through one engine, so learner
      state carries exactly as it would in a continuous run."""
      import json as _json
      sel = _json.loads(pathlib.Path(CANDLE_LIST).read_text())["candles"]
      if args.shard:
          _i, _n = (int(x) for x in args.shard.split("/"))
          sel = [c for k, c in enumerate(sel) if k % _n == _i]
      todo = [c for c in sel if c["date"] == CURRENT_DAY[0]]
      if not todo:
          return
      cache = {}
      import datetime as _dt2
      day0 = int(_dt2.datetime.strptime(CURRENT_DAY[0], "%Y-%m-%d")
                 .replace(tzinfo=_dt2.timezone.utc).timestamp()) * 1000
      def hour_of(ms):
          return int((ms - day0) // 3_600_000)
      for c in todo:
          c0 = int(c["candle_open_ms"]); c1 = c0 + CANDLE_MS
          t0w = c0 - WARMUP_MS
          hs = sorted({hour_of(t0w), hour_of(c0), hour_of(c1 - 1)})
          hs = [h for h in hs if 0 <= h <= 23]
          ev_all = []
          for h in hs:
              ev, dcols, pt, st = window_events(CURRENT_DAY[0], h, t0w, c1, args.clock)
              for e in ev:
                  ev_all.append((e, dcols, pt, st))
          ev_all.sort(key=lambda x: (x[0][0], x[0][1]))
          for (delivery_ms, _order, kind, i), dcols, pt, st in ev_all:
            bpx = bqt = apx = aqt = xts = None
            if dcols:
                bpx, bqt, apx, aqt, xts, _ = dcols
            if True:
                clock.ms = delivery_ms
                stats["events"] += 1
                stats[kind] += 1

                if kind == "PD":
                    bids = [[bpx[l][i], bqt[l][i]] for l in range(20)
                            if bpx[l][i] is not None and bpx[l][i] == bpx[l][i]]
                    asks = [[apx[l][i], aqt[l][i]] for l in range(20)
                            if apx[l][i] is not None and apx[l][i] == apx[l][i]]
                    if HAS_PERP[0]:
                        engine.ef_perp_prep.on_depth({"b": bids, "a": asks}, delivery_ms)
                    spot_depth_last[0] = delivery_ms
                    if bids and asks:
                        engine._process_message("btcusdt@depth5@100ms",
                                                {"e": "depthUpdate", "E": delivery_ms,
                                                 "bids": [[str(p), str(q)] for p, q in bids[:5]],
                                                 "asks": [[str(p), str(q)] for p, q in asks[:5]]},
                                                delivery_ms)
                        stats["SPOT_DEPTH"] = stats.get("SPOT_DEPTH", 0) + 1
                elif kind == "PT":
                    if not HAS_PERP[0]:
                        continue
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
                        state["last_kline_emit"] = 0
                    cur["h"] = max(cur["h"], px); cur["l"] = min(cur["l"], px)
                    cur["c"] = px; cur["v"] += qty
                    engine._process_message(
                        "btcusdt@aggTrade",
                        {"e": "aggTrade", "E": delivery_ms, "p": px, "q": qty,
                         "m": bool(st["is_buyer_maker"][i]),
                         "a": st["agg_trade_id"][i], "T": delivery_ms}, delivery_ms)
                    if delivery_ms - state["last_kline_emit"] >= 1000:
                        emit_kline(cid, False, delivery_ms)
                        state["last_kline_emit"] = delivery_ms

                if delivery_ms - state["ef_last"] >= b36.EF_COMPUTE_INTERVAL_MS:
                    state["ef_last"] = delivery_ms
                    engine._compute_ef_metrics(delivery_ms)
                    stats["ef_ticks"] += 1
                    em = engine.ef_metrics or {}
                    if em.get("inputs_ready"): stats["perp_ready_ticks"] += 1
                    src_ = em.get("micro_source")
                    if src_ == "PERP": stats["micro_perp"] += 1
                    elif src_: stats["micro_spot"] += 1
                    engine._watch_ef(delivery_ms)
                    reason = str((engine.ef_monitor or {}).get("new_decision_reason")
                                 or (engine.ef_monitor or {}).get("status") or "")[:70]
                    if reason:
                        blockers[reason] = blockers.get(reason, 0) + 1
                    cef = engine.current_ef
                    if cef is not None and engine.candle:
                        key = (int(engine.candle["time"]), cef.direction)
                        if key not in seen_fire:
                            seen_fire.add(key)
                            ev_ = engine.ef_metrics or {}
                            fires.append({
                                "candle_open_ms": key[0], "direction": cef.direction,
                                "fire_ts_ms": delivery_ms,
                                "fire_second": round((delivery_ms - key[0]) / 1000.0, 1),
                                "micro_source": ev_.get("micro_source"),
                                "settlement_probability": ev_.get("settlement_probability"),
                                "reason": (cef.features or {}).get("ef_new_decision_reason"),
                            })
          # close the selected candle so it settles and the learner sees it
          if cur["cid"] is not None:
              emit_kline(cur["cid"], True, cur["cid"] + CANDLE_MS - 1)
              stats["candles_settled"] += 1
              timeline.append(snap_learner(engine, cur["cid"]))
              cur["cid"] = None; cur["o"] = None
          engine.current_ef = None
          stats["windows"] = stats.get("windows", 0) + 1
          if stats["windows"] % 10 == 0:
              sel_ids = {int(x["candle_open_ms"]) for x in sel}
              act = {int(x["candle_open_ms"]): x["actual"] for x in sel}
              hit = [f for f in fires if f["candle_open_ms"] in sel_ids]
              ok = sum(1 for f in hit if f["direction"] == act.get(f["candle_open_ms"]))
              print(f"    [{stats['windows']:3}/100 candles]  fires on selected={len(hit)}  "
                    f"correct={ok}  acc={100*ok/len(hit) if hit else 0:.1f}%  "
                    f"elapsed={time.time()-t0:.0f}s", flush=True)

    # final candle close
    day_stats = {}
    for _day in WEEK_DATES:
        d = ROOT.parent / _day / "normalized"
        if not d.exists():
            print(f"  SKIP {_day}: no normalized data on disk", flush=True); continue
        DATA_HOLDER["dir"] = d
        CURRENT_DAY[0] = _day
        _kl = pq.read_table(d / "spot_klines_5m.parquet").to_pandas()
        official.clear(); official.update({int(r.open_time // 1000): r for r in _kl.itertuples()})
        _c0, _f0 = stats["candles_settled"], len(fires)
        _ls = (_safe(lambda: engine.ef_learner.snapshot()) or {}).get("samples")
        print(f"  === {_day}: start, learner samples carried in = {_ls} ===", flush=True)
        run_hours()
        if cur["cid"] is not None:
            emit_kline(cur["cid"], True, cur["cid"] + CANDLE_MS - 1)
            stats["candles_settled"] += 1
            timeline.append(snap_learner(engine, cur["cid"]))
            cur["cid"] = None; cur["o"] = None
        _ls2 = (_safe(lambda: engine.ef_learner.snapshot()) or {}).get("samples")
        day_stats[_day] = {"candles": stats["candles_settled"] - _c0,
                           "fires": len(fires) - _f0, "learner_samples_after": _ls2}
        print(f"  === {_day}: done, candles {day_stats[_day]['candles']}, "
              f"fires {day_stats[_day]['fires']}, learner samples now {_ls2} ===", flush=True)
    stats["per_day"] = day_stats

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
              "ef_audit": (store.ef_performance_audit()
                           if hasattr(store, "ef_performance_audit") else None)}
    try:
        result["ef_audit_text"] = (b36.format_ef_performance_audit(result["ef_audit"])
                                   if hasattr(b36, "format_ef_performance_audit")
                                   and result["ef_audit"] is not None else "(no audit in this build)")
    except Exception as exc:
        result["ef_audit_text"] = f"(format failed: {exc})"
    pathlib.Path(args.out).write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(stats, indent=2))
    print(result["ef_audit_text"])
    store.close()


if __name__ == "__main__":
    main()
