#!/usr/bin/env python3
"""
compact_depth20.py -- shrink the depth20 ladders LOSSLESSLY for transport.

Two transforms, both exactly reversible:
  1. prices -> int32 tenths of a dollar. BTCUSDT perp ticks at 0.1, so price*10 is an exact
     integer; verified per file. NaN (level absent) becomes 0.
     quantities -> float32, with NaN as -1.0.
  2. consecutive ladders whose 80 top-20 fields are all identical are dropped. A consumer takes
     the latest ladder at or before T, so a repeated row can never change an answer. The row kept
     is the FIRST of each run, so its timestamp is the moment that book state began.

read_compact() in this file restores the original float schema.
"""
import glob, pathlib, sys
import numpy as np, pyarrow as pa, pyarrow.parquet as pq
H = pathlib.Path(__file__).resolve().parent
SRC = H / "depth/depth20"; OUT = H / "depth/depth20_compact"; OUT.mkdir(parents=True, exist_ok=True)

def compact(f):
    t = pq.read_table(f)
    names = t.schema.names
    lad = [n for n in names if "_px_" in n or "_qty_" in n]
    M = np.column_stack([np.nan_to_num(t.column(n).combine_chunks().to_numpy(zero_copy_only=False), nan=-1.0) for n in lad])
    keep = np.ones(len(M), bool)
    if len(M) > 1: keep[1:] = ~np.all(M[1:] == M[:-1], axis=1)
    cols = {}
    for n in names:
        a = t.column(n).combine_chunks().to_numpy(zero_copy_only=False)[keep]
        if "_px_" in n:
            v = np.where(np.isnan(a), 0, np.round(a * 10)).astype(np.int64)
            nz = v != 0
            assert np.all(np.abs(v[nz] / 10 - a[nz]) < 1e-9), f"{f} {n} not a 0.1 tick"
            cols[n] = pa.array(v.astype(np.int32))
        elif "_qty_" in n:
            cols[n] = pa.array(np.nan_to_num(a, nan=-1.0).astype(np.float32))
        else:
            cols[n] = pa.array(a)
    out = OUT / pathlib.Path(f).name
    pq.write_table(pa.table(cols), out, compression="zstd", compression_level=15, use_dictionary=False,
                   column_encoding={c: "DELTA_BINARY_PACKED" for c in cols if "_px_" in c}, version="2.6")
    return len(M), int(keep.sum()), out.stat().st_size

def read_compact(path):
    """Restore the original float64 prices / float64 quantities schema."""
    t = pq.read_table(path); cols = {}
    for n in t.schema.names:
        a = t.column(n).combine_chunks().to_numpy(zero_copy_only=False)
        if "_px_" in n: cols[n] = pa.array(np.where(a == 0, np.nan, a / 10.0).astype(np.float64))
        elif "_qty_" in n: cols[n] = pa.array(np.where(a == -1.0, np.nan, a).astype(np.float64))
        else: cols[n] = t.column(n)
    return pa.table(cols)

if __name__ == "__main__":
    for day in sys.argv[1:]:
        fs = sorted(glob.glob(str(SRC / f"perp_depth20_{day}_*.parquet")))
        r0 = r1 = b = 0
        for f in fs:
            a, k, s = compact(f); r0 += a; r1 += k; b += s
        print(f"{day}: {r0:,} -> {r1:,} ladders ({100*(1-r1/r0):.1f}% dropped as exact repeats), {b/1e6:.0f} MB", flush=True)
