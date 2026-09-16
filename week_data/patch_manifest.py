s = open("build_manifest.py").read()
if "L2_incremental" in s:
    print("already patched")
else:
    add = '''
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

'''
    s = s.replace('out = H/"MANIFEST.csv"', add + 'out = H/"MANIFEST.csv"')
    open("build_manifest.py","w").write(s); print("patched")
