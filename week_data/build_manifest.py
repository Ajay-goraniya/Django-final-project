#!/usr/bin/env python3
"""Manifest of every real dataset collected for the 31 Aug - 6 Sep 2026 replay week."""
import csv, glob, json, os, pathlib, zipfile, datetime
import io
H = pathlib.Path(__file__).resolve().parent
ROOT = H.parent
rows = []
def ts(ms): return datetime.datetime.utcfromtimestamp(int(ms)/1000).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+"Z"
def add(**k): rows.append(k)

# --- Binance futures bookDepth (percentage-band depth snapshots, 1/min) ---
for f in sorted(glob.glob(str(H/"depth/BTCUSDT-bookDepth-*.zip"))):
    p = pathlib.Path(f); d = p.stem.split("-")[-3:]; day = "-".join(d)
    with zipfile.ZipFile(p) as z:
        n = z.namelist()[0]
        lines = z.read(n).decode().strip().split("\n")
    body = lines[1:]
    add(filename=p.name, dataset_type="futures_bookDepth_pct_bands_1min", source="Binance Vision (official)",
        url=f"https://data.binance.vision/data/futures/um/daily/bookDepth/BTCUSDT/{p.name}",
        start=body[0].split(",")[0]+"Z", end=body[-1].split(",")[0]+"Z", resolution="1 snapshot/minute, 24 bands (+-1..5%)",
        rows=len(body), bytes=p.stat().st_size, complete="yes (full UTC day)", gaps="NOT an L2 ladder: percentage bands only")
# --- Binance futures trades (tick) ---
for f in sorted(glob.glob(str(H/"trades/BTCUSDT-trades-*.zip"))):
    p = pathlib.Path(f); day = "-".join(p.stem.split("-")[-3:])
    with zipfile.ZipFile(p) as z:
        n = z.namelist()[0]
        with z.open(n) as fh:
            txt = io.TextIOWrapper(fh)
            hdr = txt.readline(); first = txt.readline().split(","); cnt = 2
            last = first
            for line in txt:
                cnt += 1; last = line.split(",")
    add(filename=p.name, dataset_type="futures_trades_tick", source="Binance Vision (official)",
        url=f"https://data.binance.vision/data/futures/um/daily/trades/BTCUSDT/{p.name}",
        start=ts(first[4]), end=ts(last[4]), resolution="every trade", rows=cnt-1, bytes=p.stat().st_size,
        complete="yes (full UTC day)", gaps="")
# --- CSVs fetched live ---
for f in sorted(glob.glob(str(H/"trades/*.csv"))):
    p = pathlib.Path(f)
    with p.open() as fh:
        r = list(csv.reader(fh))
    hdr, body = r[0], r[1:]
    tcol = hdr.index("transact_time") if "transact_time" in hdr else hdr.index("open_time")
    kind = ("perp_aggTrades_tick" if "perp-aggTrades" in p.name else
            "spot_aggTrades_tick" if "spot-aggTrades" in p.name else "spot_klines_5m")
    src = ("Binance USD-M futures REST via www.binance.com" if "perp" in p.name else "data-api.binance.vision REST")
    url = ("https://www.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT" if "perp" in p.name
           else "https://data-api.binance.vision/api/v3/" + ("aggTrades" if "aggTrades" in p.name else "klines") + "?symbol=BTCUSDT")
    add(filename=p.name, dataset_type=kind, source=src, url=url,
        start=ts(body[0][tcol]), end=ts(body[-1][tcol]),
        resolution="every aggTrade" if "aggTrades" in p.name else "5m bars",
        rows=len(body), bytes=p.stat().st_size,
        complete="PARTIAL - day still in progress at collection time", gaps="from 00:00:00Z to collection time only")
# --- Polymarket L2 books (cross-venue proxy for Predict.fun) ---
poly = sorted(glob.glob(str(H/"predictfun/polymarket_l2/*.zip")))
if poly:
    bydate = {}
    for f in poly:
        p = pathlib.Path(f); parts = p.name.split("_")
        day = f"{parts[1]}-{parts[2]}-{parts[3]}"
        bydate.setdefault(day, []).append(p)
    for day, ps in sorted(bydate.items()):
        add(filename=f"predictfun/polymarket_l2/5m_{day.replace('-','_')}_*.zip ({len(ps)} files)",
            dataset_type="polymarket_btc_5m_FULL_L2_orderbook (CROSS-VENUE PROXY, not Predict.fun)",
            source="HuggingFace predict-quant/poly-btc-orderbook",
            url="https://huggingface.co/datasets/predict-quant/poly-btc-orderbook",
            start=day+"T00:00:00Z", end=day+"T23:59:59Z",
            resolution="every book update, full bid+ask ladders, per 5-minute market",
            rows=f"{len(ps)} markets", bytes=sum(x.stat().st_size for x in ps),
            complete="partial day" if len(ps) < 288 else "yes",
            gaps=f"{288-len(ps)} of 288 five-minute markets absent" if len(ps) < 288 else "")
# --- Polymarket trade tape + market metadata (settlement) ---
FD = ROOT/"ef_arch/polymarket/fiveday/data"
for f in sorted(glob.glob(str(FD/"trades/trades_*.parquet"))):
    p = pathlib.Path(f); day = p.stem.replace("trades_", "")
    try:
        import pyarrow.parquet as pq
        t = pq.read_table(p); n = t.num_rows
        tsc = t.column("ts").to_pylist()
        s, e = ts(min(tsc)*1000), ts(max(tsc)*1000)
    except Exception:
        n, s, e = "?", "?", "?"
    add(filename=f"ef_arch/polymarket/fiveday/data/trades/{p.name}", dataset_type="polymarket_btc_5m_executed_trades (CROSS-VENUE PROXY)",
        source="Polymarket data-api", url="https://data-api.polymarket.com/trades?market=<conditionId>",
        start=s, end=e, resolution="every fill (taker side, price, size, 1 s ts)", rows=n, bytes=p.stat().st_size,
        complete="yes for markets that traded", gaps="")
for f in sorted(glob.glob(str(FD/"markets/btc5m_markets_*.json"))):
    p = pathlib.Path(f); day = p.stem.replace("btc5m_markets_", "")
    j = json.load(open(p))
    add(filename=f"ef_arch/polymarket/fiveday/data/markets/{p.name}", dataset_type="polymarket_btc_5m_market_metadata_and_settlement",
        source="Polymarket Gamma API", url="https://gamma-api.polymarket.com/events?slug=btc-updown-5m-<epoch>",
        start=day+"T00:00:00Z", end=day+"T23:59:59Z", resolution="1 record per 5-minute market",
        rows=len(j["rows"]), bytes=p.stat().st_size,
        complete="yes" if len(j["rows"]) == 288 else "partial", gaps=f"{288-len(j['rows'])} markets missing" if len(j["rows"]) != 288 else "")

# --- Binance USD-M perp L2 incremental depth (CryptoHFTData free tier) ---
import collections as _c, pyarrow.parquet as _pq
_l2 = sorted(glob.glob(str(H/"depth/l2/*.parquet")))
_byday = _c.defaultdict(list)
for _f in _l2: _byday[pathlib.Path(_f).stem.split("_")[-2]].append(pathlib.Path(_f))
for _day, _ps in sorted(_byday.items()):
    _rows = sum(_pq.ParquetFile(_p).metadata.num_rows for _p in _ps)
    _hrs = sorted(int(_p.stem.split("_")[-1]) for _p in _ps)
    _missing = [h for h in range(24) if h not in _hrs]
    add(filename="depth/l2/BTCUSDT_orderbook_%s_HH.parquet (%d hourly files)" % (_day, len(_ps)),
        dataset_type="futures_L2_incremental_depth_updates (tier 1: diff depth with update-id chain)",
        source="CryptoHFTData free tier (Binance USD-M perpetual)",
        url="https://api.cryptohftdata.com file binance_futures/<date>/<hh>/BTCUSDT_orderbook.parquet",
        start="%sT%02d:00:00Z" % (_day, _hrs[0]), end="%sT%02d:59:59Z" % (_day, _hrs[-1]),
        resolution="every book diff; received_time ns, event_time+transaction_time ms, first/final/prev_final update ids, side, price, quantity",
        rows=_rows, bytes=sum(_p.stat().st_size for _p in _ps),
        complete="yes (24/24 hours)" if len(_ps) == 24 else "partial (%d/24 hours)" % len(_ps),
        gaps="" if not _missing else "hours %s not published yet (day still in progress)" % _missing)


# --- reconstructed depth20 ladders ---
_d20 = sorted(glob.glob(str(H/"depth/depth20/perp_depth20_*.parquet")))
_bd = _c.defaultdict(list)
for _f in _d20: _bd[pathlib.Path(_f).stem.split("_")[-2]].append(pathlib.Path(_f))
for _day, _ps in sorted(_bd.items()):
    _rows = sum(_pq.ParquetFile(_p).metadata.num_rows for _p in _ps)
    add(filename="depth/depth20/perp_depth20_%s_HH.parquet (%d hourly files)" % (_day, len(_ps)),
        dataset_type="futures_depth20_ladders_RECONSTRUCTED from the L2 diff feed",
        source="derived by reconstruct_depth20.py from the CryptoHFTData L2 rows",
        url="local reconstruction; see reconstruct_depth20.py and depth/depth20/validation.json",
        start=_day+"T00:00:00Z", end=_day+"T23:59:59Z",
        resolution="one 20-level ladder per book event (~28 ms apart)",
        rows=_rows, bytes=sum(_p.stat().st_size for _p in _ps),
        complete="yes (24/24 hours)" if len(_ps)==24 else "partial (%d/24 hours)" % len(_ps),
        gaps="diff-only feed with no snapshot: first 20k events per day carry is_warmup=1; 64.6%% of real trades print inside the touch vs 72.6%% for the Tardis 2026-08-01 control")

# --- Polymarket quote history ---
for _f in sorted(glob.glob(str(H/"predictfun/quotes/poly_quotes_*.parquet"))):
    _p = pathlib.Path(_f); _day = _p.stem.replace("poly_quotes_","")
    _t = _pq.read_table(_p)
    add(filename="predictfun/quotes/"+_p.name,
        dataset_type="polymarket_btc_5m_quote_history (CROSS-VENUE PROXY, both tokens)",
        source="Polymarket CLOB prices-history",
        url="https://clob.polymarket.com/prices-history?market=<token>&fidelity=1",
        start=_day+"T00:00:00Z", end=_day+"T23:59:59Z",
        resolution="fidelity=1, about one price point per minute per token",
        rows=_t.num_rows, bytes=_p.stat().st_size, complete="yes (all 288 markets, both tokens)",
        gaps="coarse: ~5 points per 5-minute market; not executable depth")

out = H/"MANIFEST.csv"
cols = ["filename","dataset_type","source","url","start","end","resolution","rows","bytes","complete","gaps"]
with out.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow(r)
print(f"wrote {out} with {len(rows)} entries")
for r in rows: print(f"  {r['filename'][:58]:<58} {r['dataset_type'][:38]:<38} rows={r['rows']} {r['complete']}")
