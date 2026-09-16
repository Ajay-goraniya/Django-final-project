s = open("build_manifest.py").read()
if "depth20_reconstructed" in s: print("already"); raise SystemExit
add = '''
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

'''
s = s.replace('out = H/"MANIFEST.csv"', add + 'out = H/"MANIFEST.csv"')
open("build_manifest.py","w").write(s); print("patched")
