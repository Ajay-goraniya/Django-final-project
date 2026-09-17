#!/usr/bin/env python3
"""Write the 2026-08-29/30 weekend fetch into the exact CSV layout
normalize_day.py already reads, so the new days go through the identical
pipeline as the six days already replayed. Unit handling is explicit because
the Binance archives differ: spot aggTrades and klines are microseconds,
USD-M perp aggTrades are milliseconds. normalize_day's CSV branch multiplies
transact_time by 1000, so every CSV is written in MILLISECONDS."""
import pathlib
import pyarrow.parquet as pq

RAWDIR = pathlib.Path("weekend_raw")
TRADES = pathlib.Path("trades"); TRADES.mkdir(exist_ok=True)
DAYS = ["2026-08-28", "2026-08-29", "2026-08-30"]     # 08-28 klines only, for pre-roll


def to_ms(v):
    return v // 1000 if v > 1e15 else v


for d in DAYS:
    # ---- spot aggTrades (microseconds in archive -> milliseconds on disk)
    f = RAWDIR / f"spot_aggtrades_{d}.parquet"
    out = TRADES / f"BTCUSDT-spot-aggTrades-{d}.csv"
    if f.exists() and not out.exists():
        t = pq.read_table(f)
        c = {n: t.column(n).to_pylist() for n in t.column_names}
        with out.open("w") as fh:
            fh.write("agg_trade_id,price,qty,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n")
            for i in range(t.num_rows):
                fh.write(f"{c['agg_trade_id'][i]},{c['price'][i]},{c['quantity'][i]},"
                         f"{c['first_trade_id'][i]},{c['last_trade_id'][i]},"
                         f"{to_ms(c['timestamp'][i])},{c['is_buyer_maker'][i]}\n")
        print(f"  {out.name}: {t.num_rows:,} rows")

    # ---- perp aggTrades (already milliseconds)
    f = RAWDIR / f"perp_aggtrades_{d}.parquet"
    out = TRADES / f"BTCUSDT-perp-aggTrades-{d}.csv"
    if f.exists() and not out.exists():
        t = pq.read_table(f)
        c = {n: t.column(n).to_pylist() for n in t.column_names}
        with out.open("w") as fh:
            fh.write("agg_trade_id,price,qty,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n")
            for i in range(t.num_rows):
                fh.write(f"{c['agg_trade_id'][i]},{c['price'][i]},{c['quantity'][i]},"
                         f"{c['first_trade_id'][i]},{c['last_trade_id'][i]},"
                         f"{to_ms(c['timestamp'][i])},{c['is_buyer_maker'][i]}\n")
        print(f"  {out.name}: {t.num_rows:,} rows")

    # ---- 5m klines (microseconds in archive -> milliseconds on disk)
    f = RAWDIR / f"spot_klines_5m_{d}.parquet"
    out = TRADES / f"BTCUSDT-spot-klines5m-{d}.csv"
    if f.exists() and not out.exists():
        t = pq.read_table(f)
        c = {n: t.column(n).to_pylist() for n in t.column_names}
        with out.open("w") as fh:
            fh.write("open_time,open,high,low,close,volume,close_time,quote_volume,"
                     "trades,taker_base,taker_quote,ignore\n")
            for i in range(t.num_rows):
                fh.write(f"{to_ms(c['open_time'][i])},{c['open'][i]},{c['high'][i]},{c['low'][i]},"
                         f"{c['close'][i]},{c['volume'][i]},{to_ms(c['close_time'][i])},"
                         f"{c['quote_volume'][i]},{c['trades'][i]},{c['taker_base'][i]},"
                         f"{c['taker_quote'][i]},0\n")
        print(f"  {out.name}: {t.num_rows:,} rows")
print("bridge complete")
