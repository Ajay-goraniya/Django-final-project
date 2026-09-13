#!/usr/bin/env python3
"""
probe_sources.py -- Reproducible availability probe for the BTC 24h replay dataset.

Target window : 2026-08-30 00:00:00 UTC -> 2026-08-31 00:00:00 UTC (end exclusive)
Pre-roll      : 2026-08-29 23:45:00 UTC (15 min warm-up)

This script does NOT fabricate, infer or substitute any market data. It only
records, per candidate source, whether the exact historical artefact required by
btc_model_v9_3_BUILD36.py is actually retrievable, and emits the raw HTTP
evidence to validation/source_probe.json.

Run:  python3 probe_sources.py
"""
import json, subprocess, sys, datetime, pathlib

OUT = pathlib.Path(__file__).parent / "validation" / "source_probe.json"
BV = "https://data.binance.vision/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DAY = "2026-08-30"

def curl(url, method="GET", timeout=30):
    """Return (http_code, bytes_downloaded, first 200 bytes of body)."""
    cmd = ["curl", "-sS", "--max-time", str(timeout), "-o", "/tmp/_probe_body",
           "-w", "%{http_code} %{size_download}"]
    if method == "HEAD":
        cmd.append("-I")
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        code, size = (r.stdout.strip().split() + ["0", "0"])[:2]
        body = pathlib.Path("/tmp/_probe_body").read_bytes()[:200]
        return code, int(size), body.decode("utf-8", "replace")
    except Exception as e:
        return "ERR", 0, str(e)

def s3_keys(prefix, max_keys=50):
    """Authoritative object listing -- HEAD on data.binance.vision can 200 on
    objects that do not exist, so the S3 listing is the source of truth."""
    code, _, _ = curl(f"{S3}?delimiter=/&prefix={prefix}&max-keys={max_keys}")
    body = pathlib.Path("/tmp/_probe_body").read_text("utf-8", "replace")
    import re
    return [k for k in re.findall(r"<Key>([^<]*)</Key>", body) if not k.endswith(".CHECKSUM")]

# ---- what BUILD36 needs, per the task specification -------------------------
REQUIREMENTS = [
    ("spot_klines_5m",   "A.1", "5-minute klines, 288 completed candles",            True),
    ("spot_aggtrades",   "A.2", "spot aggTrades, every event in window",             True),
    ("spot_depth5",      "A.3", "spot depth5@100ms equivalent, price levels",        True),
    ("perp_aggtrades",   "B.1", "perp aggTrades, every event in window",             True),
    ("perp_depth20",     "B.2", "perp depth20@100ms, top-20 bids+asks price levels", True),
    ("predict_books",    "C",   "Predict.fun 5m market order books / quote VWAP",    True),
]

def main():
    ev = {
        "probed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "target_window_utc": {"start": "2026-08-30T00:00:00Z",
                              "end":   "2026-08-31T00:00:00Z",
                              "end_exclusive": True},
        "preroll_utc": {"start": "2026-08-29T23:45:00Z", "minutes": 15},
        "binance_vision": {}, "third_party": {}, "predict_fun": {}, "requirements": {},
    }

    # -- 1. Which dataset families does the Binance public archive publish at all?
    for market, prefix in [("spot", "data/spot/daily/"),
                           ("futures_um", "data/futures/um/daily/"),
                           ("futures_um_monthly", "data/futures/um/monthly/")]:
        code, _, _ = curl(f"{S3}?delimiter=/&prefix={prefix}")
        body = pathlib.Path("/tmp/_probe_body").read_text("utf-8", "replace")
        import re
        fams = [p.split("/")[-2] for p in re.findall(r"<Prefix>([^<]*)</Prefix>", body)
                if p.rstrip("/") != prefix.rstrip("/") and p.endswith("/")]
        ev["binance_vision"][market + "_dataset_families"] = sorted(set(f for f in fams if f))

    # -- 2. Exact per-file availability for the target day (S3 listing = truth)
    files = {
        "spot_klines_5m":  f"data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-{DAY}.zip",
        "spot_aggtrades":  f"data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{DAY}.zip",
        "perp_aggtrades":  f"data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{DAY}.zip",
        "perp_bookticker": f"data/futures/um/daily/bookTicker/BTCUSDT/BTCUSDT-bookTicker-{DAY}.zip",
        "perp_bookdepth":  f"data/futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-{DAY}.zip",
    }
    for name, key in files.items():
        listed = s3_keys(key)
        code, size, _ = curl(BV + key, method="GET" if name != "perp_aggtrades" else "HEAD")
        ev["binance_vision"][name] = {
            "key": key, "listed_in_s3": bool(listed),
            "http_code": code, "bytes": size,
        }

    # -- 3. Guessed L2 depth paths (prove absence, do not assume it)
    ev["binance_vision"]["l2_depth_path_probes"] = {
        p: {"keys_found": len(s3_keys(p, 3))} for p in [
            "data/futures/um/daily/depth/BTCUSDT/",
            "data/futures/um/daily/bookSnapshot/BTCUSDT/",
            "data/futures/um/daily/incrementalDepth/BTCUSDT/",
            "data/spot/daily/depth/BTCUSDT/",
        ]
    }

    # -- 4. Third-party historical L2 providers
    probes = {
        "tardis_book_snapshot_25_target_day":
            f"https://datasets.tardis.dev/v1/binance-futures/book_snapshot_25/2026/08/30/BTCUSDT.csv.gz",
        "tardis_incremental_book_L2_target_day":
            f"https://datasets.tardis.dev/v1/binance-futures/incremental_book_L2/2026/08/30/BTCUSDT.csv.gz",
        "tardis_free_sample_first_of_month":
            f"https://datasets.tardis.dev/v1/binance-futures/book_snapshot_25/2026/08/01/BTCUSDT.csv.gz",
        "coinapi_orderbook_history":
            "https://rest.coinapi.io/v1/orderbooks/BINANCEFTS_PERP_BTC_USDT/history?time_start=2026-08-30T00:00:00",
        "kaiko_order_book_snapshots":
            "https://us.market-api.kaiko.io/v2/data/order_book_snapshots.v1/exchanges/bnce/spot/btc-usdt/snapshots/full",
        "cryptohftdata_api": "https://api.cryptohftdata.com/v1/datasets",
        "binance_rest_futures_depth": "https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20",
    }
    for name, url in probes.items():
        code, size, body = curl(url)
        ev["third_party"][name] = {"url": url, "http_code": code, "bytes": size,
                                   "body_head": body[:180]}

    # -- 5. Predict.fun
    for name, url in {
        "root": "https://api.predict.fun/",
        "v1_markets": "https://api.predict.fun/v1/markets",
        "docs": "https://api.predict.fun/docs",
    }.items():
        code, size, body = curl(url)
        ev["predict_fun"][name] = {"url": url, "http_code": code, "bytes": size,
                                   "body_head": body[:180]}

    # -- 6. Verdict per requirement
    bv = ev["binance_vision"]
    status = {
        "spot_klines_5m": bv["spot_klines_5m"]["listed_in_s3"],
        "spot_aggtrades": bv["spot_aggtrades"]["listed_in_s3"],
        "spot_depth5":    False,
        "perp_aggtrades": bv["perp_aggtrades"]["listed_in_s3"],
        "perp_depth20":   False,
        "predict_books":  ev["predict_fun"]["v1_markets"]["http_code"] == "200",
    }
    for key, sec, desc, required in REQUIREMENTS:
        ev["requirements"][key] = {"spec_section": sec, "description": desc,
                                   "required": required, "obtainable": status[key]}

    blocking = [k for k, v in ev["requirements"].items()
                if v["required"] and not v["obtainable"]]
    ev["blocking_requirements"] = blocking
    # depth is the hard-stop family per the task's STOP CONDITIONS
    if "perp_depth20" in blocking:
        ev["verdict"] = "NOT_REPLAY_READY"
    elif "predict_books" in blocking:
        ev["verdict"] = "DIRECTIONAL_REPLAY_READY"
    else:
        ev["verdict"] = "FULL_REPLAY_READY"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ev, indent=2))
    print(json.dumps({"verdict": ev["verdict"], "blocking": blocking}, indent=2))
    print("wrote", OUT)

if __name__ == "__main__":
    sys.exit(main())
