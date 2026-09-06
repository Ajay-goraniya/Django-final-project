#!/usr/bin/env python3
"""
replay_r64.py -- drive the REAL 9.1.1-r6.4-true-hot-ef production code over the same causal
2026-08-01 replay dataset that Build 36 was run on, with MASTER OFF.

Production code untouched: _process_message -> _on_trade/_on_depth/_on_kline, _compute_features,
_compute_ef_metrics, _watch_ef, _emit_ef, Store settlement, the adaptation/regime machinery.

Deviations, all forced by what public archives contain (identical in spirit to the Build 36 harness):
  1. now_ms()/mono_ns() are driven by the replay event clock.
  2. Spot depth5@100ms does not exist in any public archive. r6.4 has no perp lane, so the harness
     feeds RECONSTRUCTED PERP depth (top 5 of the Tardis L2 book) into the depth stream. Build 36's
     own production code makes the same substitution internally (micro_source=PERP on 99.8% of ticks
     in its replay), so both builds' EF book features come from the same perp book.
  3. Trades are the real Binance SPOT aggTrades, which is what r6.4 subscribes to in production
     (btcusdt@aggTrade). Candle geometry is spot, matching the official spot klines used at close.
  4. Predict.fun books are unavailable; EF direction/frequency are faithful, quote economics are not
     (they are supplied afterwards from the real Polymarket ladders, as for Build 36).
ROUTER MODE: --router A|B loads one of Sol's three frozen six-number presets at each candle
open, chosen by nearest frozen centroid over seven statistics of CLOSED prior candles. The r6.4
_watch_ef logic then runs unchanged; the six thresholds it reads are module globals.
"""
import argparse, importlib.util, json, pathlib, sys, time
import pyarrow.parquet as pq
import market_router as MR

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT.parent.parent / "btc_replay_2026-08-01_24h" / "normalized"
WIN_START_US = 1785542400_000_000
CANDLE_MS = 300_000


def load_module(path):
    spec = importlib.util.spec_from_file_location("r64mod", str(path))
    mod = importlib.util.module_from_spec(spec); sys.modules["r64mod"] = mod
    spec.loader.exec_module(mod); return mod


class ReplayClock:
    __slots__ = ("ms",)
    def __init__(self): self.ms = WIN_START_US // 1000


def hour_events(h):
    ev = []
    f = DATA / f"perp_depth20_{h:02d}.parquet"
    depth_cols = None
    if f.exists():
        t = pq.read_table(f); cols = {c: t.column(c).to_pylist() for c in t.column_names}
        n = len(cols["timestamp"])
        bpx = [cols[f"bid_px_{i}"] for i in range(5)]; bqt = [cols[f"bid_qty_{i}"] for i in range(5)]
        apx = [cols[f"ask_px_{i}"] for i in range(5)]; aqt = [cols[f"ask_qty_{i}"] for i in range(5)]
        lts = cols["local_timestamp"]
        # r6.4 subscribes to btcusdt@depth5@100ms: ten book states per second. The Tardis
        # reconstruction carries every tick (~37/s), four times production rate, which also
        # makes EF's 320-entry ef_depth_history ring cover 8.6 s instead of the 32 s it spans
        # live. Deliver the LAST reconstructed book of each 100 ms bucket so the lane matches
        # production cadence. No book state is invented; every delivered snapshot is a real
        # reconstructed book carried at its own receive time.
        keep = {}
        for i in range(n):
            keep[lts[i] // 100_000] = i          # local_timestamp is microseconds
        for i in sorted(keep.values()): ev.append((lts[i] // 1000, 0, "PD", i))
        depth_cols = (bpx, bqt, apx, aqt, n)
    f = DATA / f"spot_aggtrades_{h:02d}.parquet"
    st = None
    if f.exists():
        t = pq.read_table(f, columns=["timestamp", "agg_trade_id", "price", "quantity", "is_buyer_maker"])
        st = {c: t.column(c).to_pylist() for c in t.column_names}
        for i in range(len(st["timestamp"])): ev.append((st["timestamp"][i] // 1000, 2, "ST", i))
    ev.sort(key=lambda r: (r[0], r[1], r[2]))
    return ev, depth_cols, st


def _safe(fn):
    try: return fn()
    except Exception as exc: return {"error": f"{type(exc).__name__}: {exc}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(ROOT / "btc_model_v9_1_1_r6_4.py"))
    ap.add_argument("--db", default=str(ROOT / "replay_r64.sqlite3"))
    ap.add_argument("--out", default=str(ROOT / "replay_r64_result.json"))
    ap.add_argument("--hours", default="0-23")
    ap.add_argument("--progress", type=int, default=500_000)
    ap.add_argument("--router", default="off", choices=["off", "A", "B", "CLEAN6"],
                    help="off = static r6.4 baseline; A/B = Sol's frozen 3-bucket router (normalisation mode)")
    args = ap.parse_args()
    a, b = args.hours.split("-"); hours = list(range(int(a), int(b) + 1))

    m = load_module(args.model)
    clock = ReplayClock()
    m.now_ms = lambda: clock.ms
    m.mono_ns = lambda: clock.ms * 1_000_000

    dbp = pathlib.Path(args.db)
    if dbp.exists(): dbp.unlink()
    store = m.Store(dbp)
    engine = m.Engine(store)
    can, why = engine.controls.may_execute("EF", clock.ms)
    assert not can, f"MASTER unexpectedly ON: {why}"

    kl = pq.read_table(DATA / "spot_klines_5m.parquet").to_pandas()
    official = {int(r.open_time // 1000): r for r in kl.itertuples()}

    # ---- external market router (Sol's frozen presets; EF itself untouched) ----
    if args.router == "CLEAN6":
        import pandas as _pd
        _cs = _pd.read_parquet(ROOT / "candle_stats_2026-08-01.parquet")
        CSTAT = {int(r.cid): r for r in _cs.itertuples()}
        router = MR.Clean6Router()
    elif args.router == "off":
        router = None; CSTAT = None
    else:
        router = MR.MarketRouter(); CSTAT = None
    base = dict(reach=m.EF_EARLY_REACH_MIN, control=m.EF_EARLY_CONTROL_MIN,
                settlement=m.EF_EARLY_SETTLEMENT_MIN, quality=m.EF_EARLY_QUALITY_MIN,
                chop=m.EF_EARLY_CHOP_MAX, score=m.EF_EARLY_SCORE_MIN)
    assert all(abs(base[k] - MR.STATIC[k]) < 1e-12 for k in base), f"r6.4 baseline drifted: {base}"
    bucket_log = []
    cur_bucket = {"b": None, "preset": dict(MR.STATIC)}

    def route_for_candle(cid):
        """Decide the bucket for candle cid from CLOSED candles strictly before it, then load
        the six frozen numbers into the untouched r6.4 module."""
        if router is None:
            return
        b, preset, feats = router.bucket() if args.router == "CLEAN6" else router.bucket(args.router)
        cur_bucket["b"] = b; cur_bucket["preset"] = preset
        MR.apply_preset(m, preset)
        bucket_log.append({"candle_open_ms": int(cid), "bucket": b,
                           "features": None if feats is None else [round(float(x), 6) for x in feats]})

    stats = {"events": 0, "PD": 0, "ST": 0, "KL": 0, "candles_started": 0, "candles_settled": 0,
             "ef_inputs_ready_ticks": 0, "ef_ticks_seen": 0}
    cur = {"cid": None, "o": None, "h": None, "l": None, "c": None, "v": 0.0}
    blockers = {}; fires = []; timeline = []; seen_fire = set(); last_kline_emit = 0
    t0 = time.time()

    def emit_kline(cid, closed, ts_ms):
        if cur["o"] is None: return
        if closed and cid in official:
            r = official[cid]
            k = {"t": cid, "o": float(r.open), "h": float(r.high), "l": float(r.low),
                 "c": float(r.close), "v": float(r.volume), "x": True, "T": int(r.close_time // 1000)}
        else:
            k = {"t": cid, "o": cur["o"], "h": cur["h"], "l": cur["l"], "c": cur["c"], "v": cur["v"],
                 "x": False, "T": cid + CANDLE_MS - 1}
        engine._process_message("btcusdt@kline_5m", {"e": "kline", "E": ts_ms, "k": k}, ts_ms)
        stats["KL"] += 1

    def observe():
        em = engine.ef_metrics or {}
        stats["ef_ticks_seen"] += 1
        if em.get("inputs_ready"): stats["ef_inputs_ready_ticks"] += 1
        mon = engine.ef_monitor or {}
        reason = str(mon.get("new_decision_reason") or mon.get("status") or "")[:70]
        if reason: blockers[reason] = blockers.get(reason, 0) + 1
        cef = engine.current_ef
        if cef is not None and engine.candle:
            key = (int(engine.candle["time"]), cef.direction)
            if key not in seen_fire:
                seen_fire.add(key)
                fires.append({"candle_open_ms": key[0], "direction": cef.direction,
                              "fire_ts_ms": clock.ms, "fire_second": round((clock.ms - key[0]) / 1000.0, 1),
                              "settlement_probability": em.get("settlement_probability"),
                              "real_reversal_score": em.get("real_reversal_score"),
                              "chop": em.get("chop"), "control_transfer": em.get("control_transfer"),
                              "regime": (engine.feature or {}).get("regime"),
                              "router_bucket": cur_bucket["b"],
                              "thresholds": dict(cur_bucket["preset"]),
                              "reason": (cef.features or {}).get("ef_new_decision_reason")})

    for h in hours:
        ev, dcols, st = hour_events(h)
        bpx = bqt = apx = aqt = None
        if dcols: bpx, bqt, apx, aqt, _ = dcols
        for delivery_ms, _order, kind, i in ev:
            clock.ms = delivery_ms
            stats["events"] += 1; stats[kind] += 1
            if kind == "PD":
                bids = [[bpx[l][i], bqt[l][i]] for l in range(5) if bpx[l][i] is not None]
                asks = [[apx[l][i], aqt[l][i]] for l in range(5) if apx[l][i] is not None]
                if not bids or not asks: continue
                engine._process_message("btcusdt@depth5@100ms",
                                        {"e": "depthUpdate", "bids": bids, "asks": asks}, delivery_ms)
                observe()
            elif kind == "ST":
                px, qty = st["price"][i], st["quantity"][i]
                cid = (delivery_ms // CANDLE_MS) * CANDLE_MS
                if cur["cid"] != cid:
                    if cur["cid"] is not None:
                        emit_kline(cur["cid"], True, cur["cid"] + CANDLE_MS - 1)
                        stats["candles_settled"] += 1
                        if router is not None:
                            if args.router == "CLEAN6":
                                cs = CSTAT.get(int(cur["cid"]))
                                if cs is not None:
                                    router.add_closed_candle(cs.rv, cs.eff, cs.wick, cs.crosses,
                                                             getattr(cs, "dir"), cs.body, getattr(cs, "range"))
                            else:
                                k = official.get(cur["cid"])
                                if k is not None:
                                    router.add_closed_candle(k.open, k.high, k.low, k.close, k.volume)
                                else:
                                    router.add_closed_candle(cur["o"], cur["h"], cur["l"], cur["c"], cur["v"])
                        timeline.append({"candle_open_ms": cur["cid"],
                                         "regime": (engine.feature or {}).get("regime"),
                              "router_bucket": cur_bucket["b"],
                              "thresholds": dict(cur_bucket["preset"]),
                                         "adapt_ratio": _safe(lambda: engine.adapt_ratio()),
                                         "model": _safe(lambda: engine.model.snapshot() if hasattr(engine, "model") and hasattr(engine.model, "snapshot") else {})})
                    cur.update(cid=cid, o=px, h=px, l=px, c=px, v=0.0)
                    stats["candles_started"] += 1; last_kline_emit = 0
                    route_for_candle(cid)
                cur["h"] = max(cur["h"], px); cur["l"] = min(cur["l"], px); cur["c"] = px; cur["v"] += qty
                engine._process_message("btcusdt@aggTrade",
                                        {"e": "aggTrade", "E": delivery_ms, "p": px, "q": qty,
                                         "m": bool(st["is_buyer_maker"][i]), "a": st["agg_trade_id"][i],
                                         "T": delivery_ms}, delivery_ms)
                observe()
                if delivery_ms - last_kline_emit >= 1000:
                    emit_kline(cid, False, delivery_ms); last_kline_emit = delivery_ms
            if stats["events"] % args.progress == 0:
                el = time.time() - t0
                print(f"  h{h:02d} ev={stats['events']:,} fires={len(fires)} "
                      f"rate={stats['events']/max(el,1e-9):,.0f}/s elapsed={el:,.0f}s", flush=True)
    if cur["cid"] is not None:
        emit_kline(cur["cid"], True, cur["cid"] + CANDLE_MS - 1); stats["candles_settled"] += 1
    stats["elapsed_s"] = round(time.time() - t0, 1)
    stats["router_mode"] = args.router
    json.dump({"stats": stats, "blockers": blockers, "fires": fires, "timeline": timeline,
               "bucket_log": bucket_log, "presets": MR.PRESETS, "static": MR.STATIC},
              open(args.out, "w"), indent=1, default=str)
    print(json.dumps(stats, indent=1))
    print("fires:", len(fires))
    print("top blockers:", sorted(blockers.items(), key=lambda x: -x[1])[:8])


if __name__ == "__main__":
    main()
