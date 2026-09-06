#!/usr/bin/env python3
"""
pmxt_range_reader.py -- read pmxt Polymarket v2 hourly parquet files over
HTTP range requests with pyarrow only (no DuckDB / fsspec available here).

The files are sorted by (market, asset_id, timestamp_received) and written in
~1M-row row groups, so the footer's per-row-group statistics on `market` let
us fetch only the row groups that can contain our target condition IDs.

Usage (inspect footer):
    python3 pmxt_range_reader.py inspect 2026-08-01T00
Usage (extract rows for given asset_ids to a local parquet):
    python3 pmxt_range_reader.py extract 2026-08-01T00 out.parquet ASSET_ID [ASSET_ID ...]
"""
import io, sys, time, urllib.request
import pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc

BASE = "https://r2v2.pmxt.dev/polymarket_orderbook_{}.parquet"
BLOCK = 4 << 20   # 4 MiB read-ahead blocks


class HTTPRangeFile:
    """Seekable read-only file over HTTP Range requests with a block cache."""
    def __init__(self, url, block=BLOCK):
        self.url, self.block, self.pos, self.cache, self.fetched = url, block, 0, {}, 0
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "curl/8.5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])

    def _get(self, start, end):
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}", "User-Agent": "curl/8.5.0"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read(); self.fetched += len(data); return data
            except Exception:
                if attempt == 4: raise
                time.sleep(2 ** attempt)

    def _block(self, i):
        if i not in self.cache:
            s = i * self.block; e = min(s + self.block, self.size) - 1
            self.cache[i] = self._get(s, e)
            if len(self.cache) > 64:                       # bounded memory
                self.cache.pop(next(iter(self.cache)))
        return self.cache[i]

    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        out = bytearray(); pos = self.pos; end = min(self.pos + n, self.size)
        while pos < end:
            b = pos // self.block; blk = self._block(b); off = pos - b * self.block
            take = min(len(blk) - off, end - pos); out += blk[off:off + take]; pos += take
        self.pos = pos; return bytes(out)

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off); return self.pos
    def tell(self): return self.pos
    def readable(self): return True
    def seekable(self): return True
    def close(self): pass
    @property
    def closed(self): return False


def open_hour(hour):
    f = HTTPRangeFile(BASE.format(hour)); return f, pq.ParquetFile(pa.PythonFile(f, mode="r"))


def inspect(hour):
    f, pf = open_hour(hour); md = pf.metadata
    print(f"{hour}: {f.size/1e6:.1f} MB  rows={md.num_rows:,}  row_groups={md.num_row_groups}  footer fetched {f.fetched/1e6:.2f} MB")
    print(pf.schema_arrow)
    mi = pf.schema_arrow.get_field_index("market"); ai = pf.schema_arrow.get_field_index("asset_id")
    for i in range(md.num_row_groups):
        rg = md.row_group(i); sm = rg.column(mi).statistics; sa = rg.column(ai).statistics
        m0 = sm.min.hex()[:12] if sm and sm.has_min_max and isinstance(sm.min, bytes) else (str(sm.min)[:12] if sm and sm.has_min_max else "?")
        m1 = sm.max.hex()[:12] if sm and sm.has_min_max and isinstance(sm.max, bytes) else (str(sm.max)[:12] if sm and sm.has_min_max else "?")
        print(f"  rg{i:>3}: rows={rg.num_rows:>9,} bytes={rg.total_byte_size/1e6:6.1f}MB market[{m0}..{m1}] asset_id_stats={'yes' if sa and sa.has_min_max else 'no'}")


def extract(hour, out, asset_ids, markets=None):
    f, pf = open_hour(hour); md = pf.metadata
    mi = pf.schema_arrow.get_field_index("market")
    want = set(asset_ids); tables = []
    for i in range(md.num_row_groups):
        rg = md.row_group(i); sm = rg.column(mi).statistics
        if markets and sm and sm.has_min_max:
            lo, hi = sm.min, sm.max
            if not any(lo <= m <= hi for m in markets):
                continue                                   # prune by market range
        t = pf.read_row_group(i, columns=["timestamp_received", "timestamp", "market", "event_type",
                                          "asset_id", "bids", "asks", "price", "size", "side",
                                          "best_bid", "best_ask", "fee_rate_bps"])
        mask = pc.is_in(t.column("asset_id"), value_set=pa.array(list(want)))
        sub = t.filter(mask)
        if sub.num_rows: tables.append(sub)
    if not tables:
        print(f"{hour}: no rows for {len(want)} asset_ids (fetched {f.fetched/1e6:.1f} MB)"); return 0
    res = pa.concat_tables(tables); pq.write_table(res, out, compression="zstd")
    print(f"{hour}: {res.num_rows:,} rows -> {out}  (fetched {f.fetched/1e6:.1f} MB of {f.size/1e6:.1f} MB)")
    return res.num_rows


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "inspect": inspect(sys.argv[2])
    elif cmd == "extract": extract(sys.argv[2], sys.argv[3], sys.argv[4:])
