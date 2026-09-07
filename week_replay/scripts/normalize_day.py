#!/usr/bin/env python3
"""
normalize_day.py <DATE> -- assemble one UTC day of the 2026-08-31..09-06 week into the exact
layout the existing replay harness reads, from the real files already collected.

  perp_depth20_HH.parquet   <- week_data/depth/depth20 (reconstructed from CryptoHFTData L2)
  perp_trades_HH.parquet    <- Binance Vision futures tick trades, or the live-REST perp
                               aggTrades for 2026-09-06 which Vision has not published
  spot_aggtrades_HH.parquet <- Binance Vision spot aggTrades (live REST for 09-06)
  spot_klines_5m.parquet    <- Binance Vision spot 5m klines (live REST for 09-06)

Timestamps are normalised to MICROSECONDS, matching the 2026-08-01 bundle. Binance archives carry
milliseconds, so they are multiplied by 1000; no latency is invented. For perp trades there is no
separate capture clock, so local_timestamp is set equal to timestamp and that is recorded here.
"""
import io, pathlib, sys, zipfile
import numpy as np, pandas as pd, pyarrow as pa, pyarrow.parquet as pq

R = pathlib.Path(__file__).resolve().parents[2]
WD = R / "week_data"; RAW = R / "btc_replay_multi/raw"
DATE = sys.argv[1]
OUT = R / "week_replay" / DATE / "normalized"; OUT.mkdir(parents=True, exist_ok=True)
W0 = int(pd.Timestamp(DATE, tz="UTC").timestamp()); HOUR_US = 3_600_000_000
S_US, E_US = W0 * 1_000_000, (W0 + 86400) * 1_000_000

def part(df, prefix, tcol="timestamp"):
    n = 0
    for h in range(24):
        lo, hi = S_US + h * HOUR_US, S_US + (h + 1) * HOUR_US
        d = df[(df[tcol] >= lo) & (df[tcol] < hi)]
        if len(d):
            pq.write_table(pa.Table.from_pandas(d, preserve_index=False),
                           OUT / f"{prefix}_{h:02d}.parquet", compression="zstd")
            n += len(d)
    return n

# ---- perp depth20 (already the right schema; restore floats from the compact form if needed)
import glob
src = sorted(glob.glob(str(WD / f"depth/depth20/perp_depth20_{DATE}_*.parquet")))
for f in src:
    hh = pathlib.Path(f).stem.split("_")[-1]
    t = pq.read_table(f)
    keep = [n for n in t.schema.names if n not in ("is_warmup",)]
    pq.write_table(t.select(keep), OUT / f"perp_depth20_{hh}.parquet", compression="zstd")
print(f"  depth20 hours: {len(src)}")

# ---- perp trades
z = WD / f"trades/BTCUSDT-trades-{DATE}.zip"
c = WD / f"trades/BTCUSDT-perp-aggTrades-{DATE}.csv"
if z.exists():
    with zipfile.ZipFile(z) as zz:
        d = pd.read_csv(zz.open(zz.namelist()[0]))
    d = d.rename(columns={"qty": "quantity", "time": "ts_ms"})
    d["timestamp"] = d.ts_ms.astype("int64") * 1000
    d["aggressor"] = np.where(d.is_buyer_maker, -1, 1).astype("int8")
    src_note = "binance vision futures/trades (tick)"
elif c.exists():
    d = pd.read_csv(c).rename(columns={"qty": "quantity", "transact_time": "ts_ms",
                                       "agg_trade_id": "id"})
    d["timestamp"] = d.ts_ms.astype("int64") * 1000
    d["aggressor"] = np.where(d.is_buyer_maker, -1, 1).astype("int8")
    src_note = "binance futures REST aggTrades (Vision not yet published)"
else:
    raise SystemExit(f"no perp trades for {DATE}")
d["local_timestamp"] = d.timestamp          # no separate capture clock in these sources
d["side"] = np.where(d.aggressor > 0, "buy", "sell")
d["quote_notional"] = d.price * d.quantity
d["signed_quote_notional"] = d.quote_notional * d.aggressor
pt = part(d[["timestamp", "local_timestamp", "id", "side", "aggressor", "price", "quantity",
             "quote_notional", "signed_quote_notional"]].sort_values("timestamp"), "perp_trades")
print(f"  perp trades: {pt:,}  ({src_note})")

# ---- spot aggTrades
z = RAW / f"spot_aggTrades_{DATE}.zip"
c = WD / f"trades/BTCUSDT-spot-aggTrades-{DATE}.csv"
NAMES = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
         "transact_time", "is_buyer_maker", "is_best_match"]
if z.exists():
    with zipfile.ZipFile(z) as zz:
        nm = zz.namelist()[0]
        head = zz.open(nm).readline().decode()
        skip = 1 if not head.split(",")[0].strip().lstrip("-").isdigit() else 0
        s = pd.read_csv(zz.open(nm), header=None, names=NAMES, skiprows=skip)
    # archive is microseconds for spot
    s["timestamp"] = s.transact_time.astype("int64")
    if s.timestamp.iloc[0] < 1e15: s["timestamp"] = s.timestamp * 1000
else:
    s = pd.read_csv(c).rename(columns={"qty": "quantity"})
    s["first_trade_id"] = s.first_trade_id; s["last_trade_id"] = s.last_trade_id
    s["is_best_match"] = True
    s["timestamp"] = s.transact_time.astype("int64") * 1000
s["transact_time"] = s.timestamp
st = part(s[NAMES + ["timestamp"]].sort_values("timestamp"), "spot_aggtrades")
print(f"  spot aggTrades: {st:,}")

# ---- spot klines (target day plus the previous day for pre-roll context)
KN = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
      "trades", "taker_base", "taker_quote", "ignore"]
frames = []
prev = (pd.Timestamp(DATE) - pd.Timedelta("1D")).strftime("%Y-%m-%d")
for day in (prev, DATE):
    zk = RAW / f"spot_klines5m_{day}.zip"; ck = WD / f"trades/BTCUSDT-spot-klines5m-{day}.csv"
    if zk.exists():
        with zipfile.ZipFile(zk) as zz:
            nm = zz.namelist()[0]
            head = zz.open(nm).readline().decode()
            skip = 1 if not head.split(",")[0].strip().lstrip("-").isdigit() else 0
            k = pd.read_csv(zz.open(nm), header=None, names=KN, skiprows=skip)
    elif ck.exists():
        k = pd.read_csv(ck)
        k["open_time"] = k.open_time.astype("int64") * 1000
        k["close_time"] = k.close_time.astype("int64") * 1000
    else:
        continue
    if k.open_time.iloc[0] < 1e15:
        k["open_time"] = k.open_time.astype("int64") * 1000
        k["close_time"] = k.close_time.astype("int64") * 1000
    frames.append(k)
K = pd.concat(frames, ignore_index=True).drop_duplicates("open_time").sort_values("open_time")
pq.write_table(pa.Table.from_pandas(K[KN], preserve_index=False), OUT / "spot_klines_5m.parquet",
               compression="zstd")
print(f"  klines: {len(K)} bars ({K.open_time.min()} .. {K.open_time.max()})")
