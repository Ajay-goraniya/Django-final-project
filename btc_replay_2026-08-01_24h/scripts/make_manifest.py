#!/usr/bin/env python3
"""make_manifest.py -- hashes + provenance for every raw and normalized file."""
import datetime, hashlib, json, pathlib
import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent

SOURCES = {
    "binance-futures_incremental_book_L2_2026-08-01_BTCUSDT.csv.gz":
        "https://datasets.tardis.dev/v1/binance-futures/incremental_book_L2/2026/08/01/BTCUSDT.csv.gz",
    "binance-futures_trades_2026-08-01_BTCUSDT.csv.gz":
        "https://datasets.tardis.dev/v1/binance-futures/trades/2026/08/01/BTCUSDT.csv.gz",
    "binance-futures_book_snapshot_25_2026-08-01_BTCUSDT.csv.gz":
        "https://datasets.tardis.dev/v1/binance-futures/book_snapshot_25/2026/08/01/BTCUSDT.csv.gz",
    "spot_klines5m_2026-08-01.zip":
        "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-08-01.zip",
    "spot_klines5m_2026-07-31.zip":
        "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-2026-07-31.zip",
    "spot_aggTrades_2026-08-01.zip":
        "https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-08-01.zip",
    "spot_aggTrades_2026-07-31.zip":
        "https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-07-31.zip",
    "perp_aggTrades_2026-08-01.zip":
        "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-08-01.zip",
    "perp_aggTrades_2026-07-31.zip":
        "https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-07-31.zip",
}

def sha256(p, buf=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(buf), b""):
            h.update(b)
    return h.hexdigest()

def describe(p):
    d = {"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha256(p)}
    if p.suffix == ".parquet":
        d["rows"] = pq.ParquetFile(p).metadata.num_rows
        d["compression"] = "zstd"
    elif p.name in SOURCES:
        d["source_url"] = SOURCES[p.name]
        d["provider"] = "tardis.dev" if p.name.startswith("binance-futures_") else "Binance Vision"
    return d

man = {
    "dataset": "btc_replay_2026-08-01_24h",
    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "target_window_utc": {"start": "2026-08-01T00:00:00Z", "end": "2026-08-02T00:00:00Z",
                          "end_exclusive": True, "expected_5m_candles": 288},
    "preroll_utc": {"start": "2026-07-31T23:45:00Z", "end": "2026-08-01T00:00:00Z",
                    "minutes": 15,
                    "coverage": "spot klines + spot aggTrades + perp aggTrades only; "
                                "perp L2 depth NOT available (Tardis free tier is "
                                "first-day-of-month only)"},
    "symbols": {"spot": "BTCUSDT (Binance spot)",
                "perp": "BTCUSDT (Binance USD-M perpetual)"},
    "providers": {
        "tardis.dev": "BTCUSDT perpetual incremental_book_L2, trades, book_snapshot_25 "
                      "(free first-day-of-month tier, unauthenticated)",
        "Binance Vision": "spot 5m klines, spot aggTrades, USD-M perp aggTrades",
    },
    "timestamp_semantics": {
        "canonical_column": "timestamp",
        "canonical_unit": "microseconds since UNIX epoch, UTC",
        "raw_binance_spot_klines": "microseconds (exchange clock)",
        "raw_binance_spot_aggtrades": "microseconds (exchange clock)",
        "raw_binance_perp_aggtrades": "MILLISECONDS in the archive; multiplied by 1000 "
                                      "during normalization. Original kept as transact_time_ms.",
        "raw_tardis_timestamp": "microseconds, exchange clock",
        "raw_tardis_local_timestamp": "microseconds, Tardis collector RECEIVE clock",
        "receive_clock": "AVAILABLE for all Tardis-sourced rows via local_timestamp. "
                         "Binance Vision archives carry exchange time only -> for those "
                         "rows LIVE_RECEIVE_CLOCK_UNAVAILABLE. No latency was invented.",
        "ordering_rule": "sort by (timestamp, then id/agg_trade_id); for depth, provider "
                         "file order within equal (timestamp, local_timestamp)",
    },
    "missing_data_notes": [
        "SPOT_DEPTH_UNAVAILABLE - Binance publishes no historical spot L2 depth publicly.",
        "PREDICT_BOOK_HISTORY_UNAVAILABLE - api.predict.fun/v1/markets returns HTTP 401.",
        "PRE_ROLL_PERP_DEPTH_UNAVAILABLE - Tardis free tier covers 2026-08-01 only.",
        "SEQUENCE_IDS_UNAVAILABLE for depth - Tardis incremental_book_L2 CSV has no "
        "exchange update id column; ordering relies on provider chronological file order.",
    ],
    "files": {"raw": [], "normalized": [], "validation": [], "scripts": []},
}
for kind, pat in (("raw", "raw/**/*"), ("normalized", "normalized/*"),
                  ("validation", "validation/*"), ("scripts", "scripts/*")):
    for p in sorted(ROOT.glob(pat)):
        if p.is_file():
            man["files"][kind].append(describe(p))

for k in man["files"]:
    man.setdefault("totals", {})[k] = {
        "files": len(man["files"][k]),
        "bytes": sum(f["bytes"] for f in man["files"][k]),
    }
(ROOT / "manifest.json").write_text(json.dumps(man, indent=2))
print(json.dumps(man["totals"], indent=2))
print("wrote manifest.json")
