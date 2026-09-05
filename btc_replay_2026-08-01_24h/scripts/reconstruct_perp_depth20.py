#!/usr/bin/env python3
"""
reconstruct_perp_depth20.py

Rebuild BTCUSDT USD-M perpetual top-20 order book from Tardis
`incremental_book_L2` for 2026-08-01, strictly chronologically.

Causality guarantees:
  * Rows are consumed in file order, which is provider-guaranteed chronological
    by (timestamp, local_timestamp). The book state emitted at message M
    reflects ONLY rows from messages <= M. No later row is ever consulted.
  * `is_snapshot` blocks reset the book (initial state and post-reconnect
    resync). They are genuine provider snapshots, not interpolation.
  * Levels with amount == 0 are deletions.
  * Nothing is interpolated, back-filled or repaired using future information.
    Intervals where the book is unusable are flagged, not patched.

Output: normalized/perp_depth20_<HH>.parquet, one file per UTC hour.
Schema : timestamp (exchange us), local_timestamp (Tardis capture us),
         bid_px_0..19, bid_qty_0..19, ask_px_0..19, ask_qty_0..19,
         is_resync (uint8), n_bid_levels, n_ask_levels, is_crossed (uint8)
"""
import gzip, io, json, os, subprocess, sys, pathlib
from sortedcontainers import SortedDict
import pyarrow as pa, pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "raw/tardis/binance-futures_incremental_book_L2_2026-08-01_BTCUSDT.csv.gz"
OUTDIR = ROOT / "normalized"; OUTDIR.mkdir(exist_ok=True)
STATS = ROOT / "validation/perp_depth20_recon_stats.json"

WIN_START_US = 1785542400_000_000   # 2026-08-01T00:00:00Z
WIN_END_US   = 1785628800_000_000   # 2026-08-02T00:00:00Z (exclusive)
K = 20

bids = SortedDict()   # price -> amount  (ascending; best bid = last)
asks = SortedDict()   # price -> amount  (ascending; best ask = first)

COLS = (["timestamp", "local_timestamp"]
        + [f"bid_px_{i}" for i in range(K)] + [f"bid_qty_{i}" for i in range(K)]
        + [f"ask_px_{i}" for i in range(K)] + [f"ask_qty_{i}" for i in range(K)]
        + ["is_resync", "n_bid_levels", "n_ask_levels", "is_crossed"])
SCHEMA = pa.schema(
    [("timestamp", pa.int64()), ("local_timestamp", pa.int64())]
    + [(f"bid_px_{i}", pa.float64()) for i in range(K)]
    + [(f"bid_qty_{i}", pa.float64()) for i in range(K)]
    + [(f"ask_px_{i}", pa.float64()) for i in range(K)]
    + [(f"ask_qty_{i}", pa.float64()) for i in range(K)]
    + [("is_resync", pa.uint8()), ("n_bid_levels", pa.int32()),
       ("n_ask_levels", pa.int32()), ("is_crossed", pa.uint8())])

buf = {c: [] for c in COLS}
stats = {
    "source_file": SRC.name, "rows_read": 0, "messages": 0, "emitted": 0,
    "snapshot_blocks": 0, "crossed_books": 0, "emitted_outside_window": 0,
    "thin_book_messages": 0, "per_hour": {}, "first_ts": None, "last_ts": None,
    "max_gap_us": 0, "gaps_us": [],
}
cur_hour = None
prev_ts = None

def flush(hour):
    if not buf["timestamp"]:
        return
    tbl = pa.Table.from_pydict(buf, schema=SCHEMA)
    pq.write_table(tbl, OUTDIR / f"perp_depth20_{hour:02d}.parquet",
                   compression="zstd", compression_level=6)
    stats["per_hour"][f"{hour:02d}"] = len(buf["timestamp"])
    for c in COLS:
        buf[c].clear()

def emit(ts, lts, resync):
    """Snapshot current top-20. Only state from messages <= this one exists."""
    global cur_hour, prev_ts
    if not (WIN_START_US <= ts < WIN_END_US):
        stats["emitted_outside_window"] += 1
        return
    hour = (ts - WIN_START_US) // 3_600_000_000
    if cur_hour is None:
        cur_hour = hour
    elif hour != cur_hour:
        flush(cur_hour); cur_hour = hour

    nb, na = len(bids), len(asks)
    if nb < K or na < K:
        stats["thin_book_messages"] += 1
    # SortedDict is price-ascending: best bid = highest = iterate from the end.
    bk = bids.keys(); ak = asks.keys()
    bpx = [bk[nb - 1 - i] if i < nb else None for i in range(K)]
    apx = [ak[i] if i < na else None for i in range(K)]
    crossed = 1 if (nb and na and bk[nb - 1] >= ak[0]) else 0
    stats["crossed_books"] += crossed

    buf["timestamp"].append(ts); buf["local_timestamp"].append(lts)
    for i in range(K):
        buf[f"bid_px_{i}"].append(bpx[i])
        buf[f"bid_qty_{i}"].append(bids[bpx[i]] if bpx[i] is not None else None)
        buf[f"ask_px_{i}"].append(apx[i])
        buf[f"ask_qty_{i}"].append(asks[apx[i]] if apx[i] is not None else None)
    buf["is_resync"].append(resync); buf["n_bid_levels"].append(nb)
    buf["n_ask_levels"].append(na); buf["is_crossed"].append(crossed)

    stats["emitted"] += 1
    if stats["first_ts"] is None:
        stats["first_ts"] = ts
    stats["last_ts"] = ts
    if prev_ts is not None:
        g = ts - prev_ts
        if g > stats["max_gap_us"]:
            stats["max_gap_us"] = g
        stats["gaps_us"].append(g)
    prev_ts = ts

def main():
    proc = subprocess.Popen(["zcat", str(SRC)], stdout=subprocess.PIPE, bufsize=1 << 22)
    fh = proc.stdout
    fh.readline()  # header

    msg_ts = msg_lts = None
    msg_resync = 0
    was_snapshot = False

    for line in fh:
        stats["rows_read"] += 1
        # exchange,symbol,timestamp,local_timestamp,is_snapshot,side,price,amount
        p = line.rstrip(b"\n").split(b",")
        if len(p) < 8:
            continue
        ts = int(p[2]); lts = int(p[3])
        is_snap = p[4] == b"true"
        side = p[5]; price = float(p[6]); amount = float(p[7])

        if (ts, lts) != (msg_ts, msg_lts):
            if msg_ts is not None:
                emit(msg_ts, msg_lts, msg_resync)
                stats["messages"] += 1
            msg_ts, msg_lts, msg_resync = ts, lts, 1 if is_snap else 0
        if is_snap and not was_snapshot:
            # new provider snapshot block -> discard prior state, rebuild
            bids.clear(); asks.clear()
            stats["snapshot_blocks"] += 1
            msg_resync = 1
        was_snapshot = is_snap

        book = bids if side == b"bid" else asks
        if amount == 0.0:
            book.pop(price, None)
        else:
            book[price] = amount

        if stats["rows_read"] % 10_000_000 == 0:
            print(f"  rows={stats['rows_read']:,} msgs={stats['messages']:,} "
                  f"emitted={stats['emitted']:,}", flush=True)

    if msg_ts is not None:
        emit(msg_ts, msg_lts, msg_resync); stats["messages"] += 1
    if cur_hour is not None:
        flush(cur_hour)
    proc.wait()

    g = sorted(stats.pop("gaps_us"))
    if g:
        stats["gap_us_p50"] = g[len(g) // 2]
        stats["gap_us_p95"] = g[int(len(g) * 0.95)]
        stats["gap_us_p99"] = g[int(len(g) * 0.99)]
    STATS.parent.mkdir(exist_ok=True)
    STATS.write_text(json.dumps(stats, indent=2))
    print(json.dumps({k: v for k, v in stats.items() if k != "per_hour"}, indent=2))

if __name__ == "__main__":
    main()
