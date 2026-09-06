#!/usr/bin/env python3
"""
reconstruct_depth20.py -- rebuild BTCUSDT USD-M perpetual top-20 ladders from the CryptoHFTData
L2 incremental depth feed, one UTC day at a time.

SOURCE SHAPE (verified, not assumed): the feed is Binance's @depth DIFF stream. Every row is one
price level of one book event; rows sharing final_update_id are one event. There are NO snapshot
rows and last_update_id is never set, so the absolute book cannot be seeded from the feed. The
book is therefore accumulated from diffs and the opening stretch of each day is marked
is_warmup=1 rather than presented as a settled book. Nothing is interpolated or back-filled.

CAUSALITY: events are applied in received_time order; the ladder emitted at event M reflects only
rows from events <= M. Sequence continuity is checked with Binance's own rule
(prev_final_update_id of event i == final_update_id of event i-1); a break sets is_resync=1 on
that event and is counted, never patched.

OUTPUT: perp_depth20_<DATE>_<HH>.parquet with the same schema as the 2026-08-01 Tardis
reconstruction, plus is_warmup:
  timestamp (exchange us), local_timestamp (receive us), bid_px_0..19, bid_qty_0..19,
  ask_px_0..19, ask_qty_0..19, is_resync, n_bid_levels, n_ask_levels, is_crossed, is_warmup
"""
import glob, json, pathlib, sys, time
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
from sortedcontainers import SortedDict

K = 20
H = pathlib.Path(__file__).resolve().parent
SRC = H / "depth/l2"
OUT = H / "depth/depth20"; OUT.mkdir(parents=True, exist_ok=True)
WARMUP_EVENTS = 20_000            # declared up front, not tuned on the output

SCHEMA = pa.schema(
    [("timestamp", pa.int64()), ("local_timestamp", pa.int64())]
    + [(f"bid_px_{i}", pa.float64()) for i in range(K)]
    + [(f"bid_qty_{i}", pa.float64()) for i in range(K)]
    + [(f"ask_px_{i}", pa.float64()) for i in range(K)]
    + [(f"ask_qty_{i}", pa.float64()) for i in range(K)]
    + [("is_resync", pa.uint8()), ("n_bid_levels", pa.int32()),
       ("n_ask_levels", pa.int32()), ("is_crossed", pa.uint8()), ("is_warmup", pa.uint8())])
COLS = [f.name for f in SCHEMA]


def run_day(day):
    files = sorted(glob.glob(str(SRC / f"BTCUSDT_orderbook_{day}_*.parquet")))
    if not files: return None
    bids, asks = SortedDict(), SortedDict()      # price -> qty, ascending
    st = dict(day=day, hours=len(files), events=0, rows=0, resyncs=0, crossed=0,
              emitted=0, warmup_events=WARMUP_EVENTS, first_ts=None, last_ts=None,
              max_gap_ms=0, thin_events=0)
    t0 = time.time(); prev_u = None
    for f in files:
        hh = pathlib.Path(f).stem.split("_")[-1]
        t = pq.read_table(f, columns=["received_time", "event_time", "final_update_id",
                                      "prev_final_update_id", "side", "price", "quantity"]).to_pandas()
        t = t.sort_values(["received_time", "final_update_id"], kind="stable")
        st["rows"] += len(t)
        buf = {c: [] for c in COLS}
        recv = t.received_time.to_numpy(); evt = t.event_time.to_numpy()
        fu = t.final_update_id.to_numpy(); pu = t.prev_final_update_id.to_numpy()
        side = t.side.to_numpy(); px = t.price.to_numpy(dtype=float); qy = t.quantity.to_numpy(dtype=float)
        n = len(t); i = 0; last_evt = None
        while i < n:
            j = i
            u = fu[i]
            while j < n and fu[j] == u: j += 1
            resync = 0
            if prev_u is not None and pu[i] == pu[i] and int(pu[i]) != int(prev_u):
                resync = 1; st["resyncs"] += 1
            prev_u = u
            for k in range(i, j):
                book = bids if side[k] == "bid" else asks
                if qy[k] == 0.0: book.pop(px[k], None)
                else: book[px[k]] = qy[k]
            st["events"] += 1
            e_ms = int(evt[i]); r_ns = int(recv[i])
            if last_evt is not None:
                st["max_gap_ms"] = max(st["max_gap_ms"], e_ms - last_evt)
            last_evt = e_ms
            if st["first_ts"] is None: st["first_ts"] = e_ms
            st["last_ts"] = e_ms
            nb, na = len(bids), len(asks)
            bk = bids.keys(); ak = asks.keys()
            row_b_px = [bk[-1 - x] if x < nb else np.nan for x in range(K)]
            row_a_px = [ak[x] if x < na else np.nan for x in range(K)]
            crossed = int(nb > 0 and na > 0 and row_b_px[0] >= row_a_px[0])
            st["crossed"] += crossed
            if nb < K or na < K: st["thin_events"] += 1
            buf["timestamp"].append(e_ms * 1000)
            buf["local_timestamp"].append(r_ns // 1000)
            for x in range(K):
                buf[f"bid_px_{x}"].append(row_b_px[x])
                buf[f"bid_qty_{x}"].append(bids[row_b_px[x]] if x < nb else np.nan)
                buf[f"ask_px_{x}"].append(row_a_px[x])
                buf[f"ask_qty_{x}"].append(asks[row_a_px[x]] if x < na else np.nan)
            buf["is_resync"].append(resync); buf["n_bid_levels"].append(nb)
            buf["n_ask_levels"].append(na); buf["is_crossed"].append(crossed)
            buf["is_warmup"].append(1 if st["events"] <= WARMUP_EVENTS else 0)
            i = j
        tbl = pa.Table.from_pydict({c: buf[c] for c in COLS}, schema=SCHEMA)
        pq.write_table(tbl, OUT / f"perp_depth20_{day}_{hh}.parquet", compression="zstd")
        st["emitted"] += tbl.num_rows
        print(f"  {day} {hh}  events {tbl.num_rows:,}  book {len(bids)}x{len(asks)}  {time.time()-t0:.0f}s", flush=True)
    st["elapsed_s"] = round(time.time() - t0, 1)
    st["final_book_levels"] = [len(bids), len(asks)]
    json.dump(st, open(OUT / f"recon_stats_{day}.json", "w"), indent=1)
    print(f"DONE {day}: {st['emitted']:,} ladders from {st['rows']:,} rows, "
          f"resyncs {st['resyncs']}, crossed {st['crossed']}, thin {st['thin_events']:,}, {st['elapsed_s']}s", flush=True)
    return st


if __name__ == "__main__":
    for d in sys.argv[1:]:
        run_day(d)
