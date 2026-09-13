#!/usr/bin/env python3
"""
build_poly_second_quotes.py -- PER-SECOND Polymarket BTC 5m quotes from the real L2 event stream.

Input : predictfun/polymarket_l2/5m_<Y>_<M>_<D>_btc-updown-5m-<epoch>.zip
        one jsonl per market carrying book snapshots, price_change events (which embed
        best_bid/best_ask) and last_trade_price prints.
Output: predictfun/quotes_1s/poly_quotes_1s_<date>.parquet
        one row per (market, token, second 0..299):
            best_bid, best_ask, mid, spread          <- latest price_change/book at or before T
            quote_age_ms                             <- how stale that top-of-book is
            ask ladder VWAP for $2/$5/$10/$100       <- latest FULL book snapshot at or before T
            book_age_ms, n_ask_levels, n_bid_levels, ask_depth_top5, bid_depth_top5
            last_trade_price, last_trade_age_ms
Causal: a row at second T uses only events with timestamp <= market_open + T. Nothing is
interpolated; where no event has arrived yet the fields are null.
"""
import glob, json, pathlib, sys, zipfile
import numpy as np, pandas as pd
H = pathlib.Path(__file__).resolve().parent
SRC = H / "predictfun/polymarket_l2"
MK = H.parent / "ef_arch/polymarket/fiveday/data/markets"
OUT = H / "predictfun/quotes_1s"; OUT.mkdir(parents=True, exist_ok=True)
STAKES = (2.0, 5.0, 10.0, 100.0)

def walk(levels, stake):
    left = stake; sh = 0.0; cost = 0.0; n = 0
    for p, s in levels:
        if left <= 1e-9: break
        take = min(s, left / p); sh += take; cost += take * p; left -= take * p; n += 1
    if sh <= 0: return np.nan, 0.0, 0, False
    return cost / sh, sh, n, left <= 1e-6

def market_rows(zpath, tokmap):
    ep = int(zpath.stem.split("-")[-1]); ws = ep * 1000
    with zipfile.ZipFile(zpath) as z:
        lines = z.read(z.namelist()[0]).decode().strip().split("\n")
    books = {}; tops = {}; trades = {}
    for ln in lines:
        try: d = json.loads(ln)
        except Exception: continue
        ts = int(d["timestamp"]); et = d.get("event_type")
        if et == "book":
            a = d.get("asset_id")
            bids = sorted(((float(x["price"]), float(x["size"])) for x in d.get("bids", [])), key=lambda x: -x[0])
            asks = sorted(((float(x["price"]), float(x["size"])) for x in d.get("asks", [])), key=lambda x: x[0])
            books.setdefault(a, []).append((ts, bids, asks))
            if bids and asks: tops.setdefault(a, []).append((ts, bids[0][0], asks[0][0]))
        elif et == "price_change":
            for c in d.get("price_changes", []):
                a = c.get("asset_id")
                try: bb = float(c["best_bid"]); ba = float(c["best_ask"])
                except Exception: continue
                tops.setdefault(a, []).append((ts, bb, ba))
        elif et == "last_trade_price":
            trades.setdefault(d.get("asset_id"), []).append((ts, float(d["price"])))
    rows = []
    for a, side in tokmap.get(ep, {}).items():
        bk = sorted(books.get(a, []), key=lambda x: x[0])
        tp = sorted(tops.get(a, []), key=lambda x: x[0])
        tr = sorted(trades.get(a, []), key=lambda x: x[0])
        bts = np.array([x[0] for x in bk]) if bk else np.array([], dtype=np.int64)
        tts = np.array([x[0] for x in tp]) if tp else np.array([], dtype=np.int64)
        rts = np.array([x[0] for x in tr]) if tr else np.array([], dtype=np.int64)
        for sec in range(300):
            T = ws + sec * 1000
            r = dict(window_epoch=ep, side=side, asset_id=a, offset_s=sec, decision_ts_ms=T)
            i = np.searchsorted(tts, T, side="right") - 1 if len(tts) else -1
            if i >= 0:
                _, bb, ba = tp[i]
                r.update(best_bid=bb, best_ask=ba, mid=(bb + ba) / 2, spread=ba - bb,
                         quote_age_ms=int(T - tts[i]))
            j = np.searchsorted(bts, T, side="right") - 1 if len(bts) else -1
            if j >= 0:
                _, bids, asks = bk[j]
                r.update(book_age_ms=int(T - bts[j]), n_bid_levels=len(bids), n_ask_levels=len(asks),
                         bid_depth_top5=float(sum(s for _, s in bids[:5])),
                         ask_depth_top5=float(sum(s for _, s in asks[:5])))
                for st in STAKES:
                    v, sh, nl, ok = walk(asks, st); k = f"s{int(st)}"
                    r[f"vwap_{k}"] = v; r[f"shares_{k}"] = sh; r[f"levels_{k}"] = nl; r[f"fill_ok_{k}"] = ok
            k = np.searchsorted(rts, T, side="right") - 1 if len(rts) else -1
            if k >= 0:
                r["last_trade_price"] = tr[k][1]; r["last_trade_age_ms"] = int(T - rts[k])
            rows.append(r)
    return rows

def run(day):
    y, m, d = day.split("-")
    zs = sorted(SRC.glob(f"5m_{y}_{m}_{d}_btc-updown-5m-*.zip"))
    if not zs: print(f"{day}: no L2 files"); return
    M = json.load(open(MK / f"btc5m_markets_{day}.json"))
    tokmap = {}
    for r in M["rows"]:
        mk = r["market"]; toks = json.loads(mk["clobTokenIds"]); outs = json.loads(mk["outcomes"])
        tokmap[r["epoch"]] = {t: o.upper() for t, o in zip(toks, outs)}
    rows = []
    for i, z in enumerate(zs):
        rows += market_rows(z, tokmap)
        if i % 40 == 0: print(f"  {day} {i}/{len(zs)} markets, {len(rows):,} rows", flush=True)
    D = pd.DataFrame(rows)
    out = OUT / f"poly_quotes_1s_{day}.parquet"
    D.to_parquet(out, compression="zstd", index=False)
    q = D[D.best_ask.notna()] if "best_ask" in D else D
    print(f"DONE {day}: {len(D):,} rows, {D.window_epoch.nunique()} markets -> {out.name}")
    if len(q):
        print(f"   quoted seconds {100*len(q)/len(D):.1f}%  quote age p50 {q.quote_age_ms.median():.0f} ms  "
              f"spread p50 {q.spread.median():.3f}  $10 fill_ok {100*D.fill_ok_s10.fillna(False).mean():.1f}%", flush=True)

if __name__ == "__main__":
    for d in sys.argv[1:]: run(d)
