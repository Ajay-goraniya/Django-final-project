#!/usr/bin/env python3
"""Targeted extraction of BTC 5m Up/Down books from pmxt hourly files for 2026-08-01.
For each hour: prune row groups by conditionId range, filter to the hour's token ids,
write books/hour_HH.parquet. --analyze prints event-type and book-snapshot timing."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import daycfg as CFG; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent.parent / "ef_arch" / "polymarket"))
import json, sys, time, pathlib
import pyarrow as pa, pyarrow.parquet as pq, pyarrow.compute as pc
from pmxt_range_reader import open_hour
HERE = pathlib.Path(__file__).resolve().parent.parent.parent / "ef_arch" / "polymarket"; sys.path.insert(0, str(HERE)); OUT = CFG.BOOKS
M = json.load(open(CFG.MARKETS_JSON)); W0 = M["W0"]
def windows_for_hour(h):
    """windows whose 5-min range intersects [h, h+1) UTC, plus the one before (book warm-up)."""
    lo, hi = W0 + h * 3600, W0 + (h + 1) * 3600
    return [r for r in M["rows"] if lo - 300 <= r["epoch"] < hi]
def extract_hour(h, analyze=False):
    hour = f"{CFG.DATE}T{h:02d}"; wins = windows_for_hour(h)
    if (OUT / f"hour_{h:02d}.parquet").exists() and not analyze:
        print(f"{hour}: exists, skip"); return None
    tokens = {}; conds = []
    for r in wins:
        mk = r["market"]; up, dn = json.loads(mk["clobTokenIds"]); conds.append(mk["conditionId"].encode())
        tokens[up] = (r["epoch"], "UP"); tokens[dn] = (r["epoch"], "DOWN")
    t0 = time.time(); f, pf = open_hour(hour); md = pf.metadata
    mi = pf.schema_arrow.get_field_index("market"); kept = []; scanned = 0
    for i in range(md.num_row_groups):
        sm = md.row_group(i).column(mi).statistics
        if sm and sm.has_min_max and not any(sm.min <= c <= sm.max for c in conds): continue
        scanned += 1
        t = pf.read_row_group(i, columns=["timestamp_received", "timestamp", "market", "event_type", "asset_id",
                                          "bids", "asks", "price", "size", "side", "best_bid", "best_ask", "fee_rate_bps"])
        sub = t.filter(pc.is_in(t.column("asset_id"), value_set=pa.array(list(tokens))))
        if sub.num_rows: kept.append(sub)
    if not kept:
        print(f"{hour}: NO ROWS (scanned {scanned}/{md.num_row_groups} rg, fetched {f.fetched/1e6:.0f} MB)"); return None
    res = pa.concat_tables(kept)
    ep = pa.array([tokens[a][0] for a in res.column("asset_id").to_pylist()]); sd = pa.array([tokens[a][1] for a in res.column("asset_id").to_pylist()])
    res = res.append_column("window_epoch", ep).append_column("side_label", sd)
    pq.write_table(res, OUT / f"hour_{h:02d}.parquet", compression="zstd")
    print(f"{hour}: {res.num_rows:,} rows from {scanned}/{md.num_row_groups} row groups, fetched {f.fetched/1e6:.0f} of {f.size/1e6:.0f} MB, {time.time()-t0:.0f}s", flush=True)
    if analyze:
        d = res.to_pandas()
        print("  event_type:", d.event_type.value_counts().to_dict())
        print("  fee_rate_bps on trades:", d[d.event_type == "last_trade_price"].fee_rate_bps.value_counts().to_dict())
        for a, (epch, lab) in list(tokens.items())[:6]:
            s = d[d.asset_id == a]; bk = s[s.event_type == "book"]
            ws, we = epch * 1000, (epch + 300) * 1000
            inwin = s[(s.timestamp >= ws) & (s.timestamp < we)]
            print(f"  window {epch} {lab}: rows={len(s)} book_events={len(bk)} book_ts_rel_to_window_start_s={[round((int(x.timestamp())*1000-ws)/1000) for x in bk.timestamp[:6]]} in-window rows={len(inwin)} price_changes_in_window={(inwin.event_type=='price_change').sum()}")
    return res
if __name__ == "__main__":
    hours = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 and sys.argv[1] != "all" else list(range(24))
    for h in hours: extract_hour(h, analyze="--analyze" in sys.argv)
