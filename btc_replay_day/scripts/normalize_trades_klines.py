#!/usr/bin/env python3
"""
normalize_trades_klines.py

Normalize Binance Vision spot klines / spot aggTrades / perp aggTrades and
Tardis perp trades into replay-ready Parquet.

Canonical clock: UTC. Canonical timestamp column: `timestamp`, int64 MICROSECONDS.

Timestamp semantics of the RAW sources (verified by inspection, not assumed):
  * Binance spot klines archive   -> MICROSECONDS  (e.g. 1785542400000000)
  * Binance spot aggTrades archive-> MICROSECONDS  (e.g. 1785542400207874)
  * Binance perp aggTrades archive-> MILLISECONDS  (e.g. 1785542400081)  <-- differs
  * Tardis trades `timestamp`     -> MICROSECONDS, exchange clock
  * Tardis trades `local_timestamp`-> MICROSECONDS, Tardis collector receive clock
No timestamp is rewritten to local time; no latency is invented.
"""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import daycfg as CFG
import io, json, pathlib, zipfile, gzip
import pandas as pd, pyarrow as pa, pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAWB, RAWT = CFG.RAWB, CFG.RAWT
OUT = CFG.NORM

WIN_START = CFG.WIN_START_US
WIN_END   = CFG.WIN_END_US
PRE_START = WIN_START - 900_000_000  # 15 min pre-roll
HOUR = 3_600_000_000
report = {}

def read_zip_csv(path, names, header_maybe):
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            head = fh.readline()
        skip = 1 if head.decode().split(",")[0] == header_maybe else 0
        with z.open(name) as fh:
            return pd.read_csv(fh, header=None, names=names, skiprows=skip)

def write_partitioned(df, prefix):
    """Hourly parquet for the measured window + one pre-roll file."""
    counts = {}
    pre = df[(df.timestamp >= PRE_START) & (df.timestamp < WIN_START)]
    if len(pre):
        pq.write_table(pa.Table.from_pandas(pre, preserve_index=False),
                       OUT / f"{prefix}_preroll.parquet", compression="zstd")
        counts["preroll"] = len(pre)
    win = df[(df.timestamp >= WIN_START) & (df.timestamp < WIN_END)]
    for h in range(24):
        part = win[(win.timestamp >= WIN_START + h * HOUR) &
                   (win.timestamp < WIN_START + (h + 1) * HOUR)]
        if len(part):
            pq.write_table(pa.Table.from_pandas(part, preserve_index=False),
                           OUT / f"{prefix}_{h:02d}.parquet", compression="zstd")
        counts[f"{h:02d}"] = len(part)
    counts["window_total"] = len(win)
    return counts

# ---------------------------------------------------------------- spot klines
KC = ["open_time", "open", "high", "low", "close", "volume", "close_time",
      "quote_volume", "trade_count", "taker_buy_base_volume",
      "taker_buy_quote_volume", "ignore"]
kl = pd.concat([read_zip_csv(RAWB / f"spot_klines5m_{d}.zip", KC, "open_time")
                for d in (CFG.PREV, CFG.DATE)], ignore_index=True)
kl = kl.drop(columns=["ignore"]).sort_values("open_time").drop_duplicates("open_time")
kl["timestamp"] = kl["open_time"]

meas = kl[(kl.open_time >= WIN_START) & (kl.open_time < WIN_END)].reset_index(drop=True)
pre = kl[(kl.open_time >= PRE_START) & (kl.open_time < WIN_START)].reset_index(drop=True)
pq.write_table(pa.Table.from_pandas(meas.drop(columns=["timestamp"]), preserve_index=False),
               OUT / "spot_klines_5m.parquet", compression="zstd")
if len(pre):
    pq.write_table(pa.Table.from_pandas(pre.drop(columns=["timestamp"]), preserve_index=False),
                   OUT / "spot_klines_5m_preroll.parquet", compression="zstd")
report["spot_klines_5m"] = {
    "measured_candles": len(meas), "preroll_candles": len(pre),
    "first_open_us": int(meas.open_time.iloc[0]), "last_open_us": int(meas.open_time.iloc[-1]),
    "last_close_us": int(meas.close_time.iloc[-1]),
    "gaps_unique_us": sorted(set(meas.open_time.diff().dropna().astype("int64"))),
    "duplicate_open_times": int(meas.open_time.duplicated().sum()),
    "all_completed": bool((meas.close_time < WIN_END).all()),
}
print("klines:", report["spot_klines_5m"]["measured_candles"], "measured,",
      report["spot_klines_5m"]["preroll_candles"], "pre-roll")

# ----------------------------------------------------------- spot aggTrades
SC = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
      "transact_time", "is_buyer_maker", "is_best_match"]
sp = pd.concat([read_zip_csv(RAWB / f"spot_aggTrades_{d}.zip", SC, "agg_trade_id")
                for d in (CFG.PREV, CFG.DATE)], ignore_index=True)
sp["is_buyer_maker"] = sp.is_buyer_maker.astype(str).str.lower() == "true"
sp["timestamp"] = sp.transact_time.astype("int64")            # already microseconds
sp["aggressor"] = (~sp.is_buyer_maker).map({True: 1, False: -1}).astype("int8")
sp["quote_notional"] = sp.price * sp.quantity
sp["signed_quote_notional"] = sp.quote_notional * sp.aggressor
sp = sp.sort_values(["timestamp", "agg_trade_id"], kind="stable")
report["spot_aggtrades"] = {"partitions": write_partitioned(sp, "spot_aggtrades")}
print("spot aggTrades window rows:", report["spot_aggtrades"]["partitions"]["window_total"])

# ----------------------------------------------------------- perp aggTrades
PC = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
      "transact_time", "is_buyer_maker"]
pp = pd.concat([read_zip_csv(RAWB / f"perp_aggTrades_{d}.zip", PC, "agg_trade_id")
                for d in (CFG.PREV, CFG.DATE)], ignore_index=True)
pp["is_buyer_maker"] = pp.is_buyer_maker.astype(str).str.lower() == "true"
pp["transact_time_ms"] = pp.transact_time.astype("int64")
pp["timestamp"] = pp.transact_time_ms * 1000                   # ms -> us (raw is ms)
pp["aggressor"] = (~pp.is_buyer_maker).map({True: 1, False: -1}).astype("int8")
pp["quote_notional"] = pp.price * pp.quantity
pp["signed_quote_notional"] = pp.quote_notional * pp.aggressor
pp = pp.drop(columns=["transact_time"]).sort_values(["timestamp", "agg_trade_id"], kind="stable")
report["perp_aggtrades"] = {"partitions": write_partitioned(pp, "perp_aggtrades")}
print("perp aggTrades window rows:", report["perp_aggtrades"]["partitions"]["window_total"])

# ------------------------------------------------- perp trades (Tardis, tick)
tt = pd.read_csv(RAWT / f"binance-futures_trades_{CFG.DATE}_BTCUSDT.csv.gz")
tt = tt.rename(columns={"amount": "quantity"})
tt["timestamp"] = tt.timestamp.astype("int64")
tt["local_timestamp"] = tt.local_timestamp.astype("int64")
tt["aggressor"] = tt.side.map({"buy": 1, "sell": -1}).fillna(0).astype("int8")
tt["quote_notional"] = tt.price * tt.quantity
tt["signed_quote_notional"] = tt.quote_notional * tt.aggressor
tt = tt[["timestamp", "local_timestamp", "id", "side", "aggressor", "price",
         "quantity", "quote_notional", "signed_quote_notional"]]
tt = tt.sort_values(["timestamp", "id"], kind="stable")
report["perp_trades_tardis"] = {"partitions": write_partitioned(tt, "perp_trades")}
print("perp trades (Tardis) window rows:",
      report["perp_trades_tardis"]["partitions"]["window_total"])

(ROOT / "validation").mkdir(exist_ok=True)
(ROOT / "validation/normalize_trades_report.json").write_text(json.dumps(report, indent=2))
print("wrote validation/normalize_trades_report.json")
