#!/usr/bin/env python3
"""Analyze locally extracted pmxt hour files: event mix, fee_rate_bps, book-snapshot timing per window."""
import sys, json, pathlib, pandas as pd, pyarrow.parquet as pq
HERE = pathlib.Path(__file__).resolve().parent
for h in [int(x) for x in sys.argv[1].split(",")]:
    f = HERE / "books" / f"hour_{h:02d}.parquet"
    if not f.exists(): print(f"hour {h:02d}: missing"); continue
    d = pq.read_table(f).to_pandas()
    d["ts"] = (d.timestamp.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1ms")
    d["tsr"] = (d.timestamp_received.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1ms")
    print(f"=== hour {h:02d}: {len(d):,} rows, {d.asset_id.nunique()} tokens, {d.window_epoch.nunique()} windows ===")
    print("  event_type:", d.event_type.value_counts().to_dict())
    tr = d[d.event_type == "last_trade_price"]
    print("  fee_rate_bps on trades:", tr.fee_rate_bps.value_counts().to_dict() if len(tr) else "no trades")
    print("  received - source latency ms: p50", int((d.tsr - d.ts).median()), "p99", int((d.tsr - d.ts).quantile(0.99)))
    for ep, g in list(d.groupby("window_epoch"))[:4]:
        ws, we = ep * 1000, (ep + 300) * 1000
        for lab, s in g.groupby("side_label"):
            bk = s[s.event_type == "book"]; inwin = s[(s.ts >= ws) & (s.ts < we)]
            pre = s[s.ts < ws]
            print(f"  window {ep} {lab:<4} rows={len(s):>6} book_events={len(bk):>3} book_ts_rel_start_s={[int((t-ws)/1000) for t in bk.ts.head(8)]} "
                  f"rows_before_window={len(pre):>5} rows_in_window={len(inwin):>5} price_changes_in_window={(inwin.event_type=='price_change').sum():>5} trades_in_window={(inwin.event_type=='last_trade_price').sum()}")
    # sample a book event and a price_change to learn encodings
    b = d[d.event_type == "book"].iloc[0] if (d.event_type == "book").any() else None
    if b is not None:
        bids = json.loads(b.bids); asks = json.loads(b.asks)
        print("  sample book: n_bids", len(bids), "n_asks", len(asks), "first bids", bids[:3], "first asks", asks[:3])
    pcs = d[d.event_type == "price_change"].head(3)
    print("  sample price_change rows:\n", pcs[["ts", "side", "price", "size", "best_bid", "best_ask"]].to_string())
