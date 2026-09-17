#!/usr/bin/env python3
"""Spot aggTrades + 5m klines and USD-M perp aggTrades for 2026-08-29/30,
straight from Binance Vision daily archives. Real exchange data, unmodified."""
import io, pathlib, sys, urllib.request, zipfile
import pyarrow as pa, pyarrow.parquet as pq

DAYS = ["2026-08-29", "2026-08-30"]
BASE = "https://data.binance.vision/data"
OUT = pathlib.Path("weekend_raw"); OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}

SPEC = {
    "spot_aggtrades": (f"{BASE}/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{{d}}.zip",
        ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
         "timestamp", "is_buyer_maker", "is_best_match"]),
    "spot_klines_5m": (f"{BASE}/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-{{d}}.zip",
        ["open_time", "open", "high", "low", "close", "volume", "close_time",
         "quote_volume", "trades", "taker_base", "taker_quote", "ignore"]),
    "perp_aggtrades": (f"{BASE}/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{{d}}.zip",
        ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
         "timestamp", "is_buyer_maker"]),
}
NUM = {"price", "quantity", "open", "high", "low", "close", "volume",
       "quote_volume", "taker_base", "taker_quote"}
INT = {"agg_trade_id", "first_trade_id", "last_trade_id", "timestamp",
       "open_time", "close_time", "trades"}

for d in DAYS:
    for name, (tmpl, cols) in SPEC.items():
        dest = OUT / f"{name}_{d}.parquet"
        if dest.exists():
            print(f"  have {dest.name}"); continue
        url = tmpl.format(d=d)
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600).read()
        except Exception as exc:
            print(f"  FAIL {name} {d}: {exc}", flush=True); continue
        z = zipfile.ZipFile(io.BytesIO(raw))
        text = z.read(z.namelist()[0]).decode()
        lines = [l for l in text.splitlines() if l.strip()]
        if lines and not lines[0][0].isdigit():        # some archives carry a header row
            lines = lines[1:]
        data = {c: [] for c in cols}
        for line in lines:
            parts = line.split(",")
            for c, v in zip(cols, parts):
                data[c].append(v)
        arrays, names = [], []
        for c in cols:
            v = data[c]
            if c in INT:
                arrays.append(pa.array([int(x) for x in v], pa.int64()))
            elif c in NUM:
                arrays.append(pa.array([float(x) for x in v], pa.float64()))
            elif c.startswith("is_"):
                arrays.append(pa.array([x.strip().lower() == "true" for x in v], pa.bool_()))
            else:
                arrays.append(pa.array(v, pa.string()))
            names.append(c)
        t = pa.Table.from_arrays(arrays, names=names)
        pq.write_table(t, dest, compression="zstd")
        print(f"  {dest.name}: {t.num_rows:,} rows", flush=True)
print("binance weekend fetch complete", flush=True)
