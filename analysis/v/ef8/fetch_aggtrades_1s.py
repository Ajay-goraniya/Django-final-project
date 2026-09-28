#!/usr/bin/env python3
"""Binance BTCUSDT aggTrades (spot + um-futures) from data.binance.vision, binned to 1 s: last price, signed taker volume (BTC,
+ = taker buy), trade count. usage: fetch_aggtrades_1s.py <outdir> <day> [<day> ...]  -> <outdir>/agg1s_<mkt>_<day>.npz"""
import sys, io, zipfile, urllib.request, csv, numpy as np, os
out = sys.argv[1]
for day in sys.argv[2:]:
    for mkt, path in (('spot', 'spot/daily'), ('perp', 'futures/um/daily')):
        f = f'{out}/agg1s_{mkt}_{day}.npz'
        if os.path.exists(f): continue
        raw = urllib.request.urlopen(f'https://data.binance.vision/data/{path}/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{day}.zip', timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(raw)); name = z.namelist()[0]
        sec = {}; 
        with z.open(name) as fh:
            for row in csv.reader(io.TextIOWrapper(fh)):
                if not row[0].isdigit(): continue
                px, q, t, maker = float(row[1]), float(row[2]), int(row[5]), row[6].strip().lower() == 'true'
                s = (t // 1000) if t < 1e13 else (t // 1000000)
                a = sec.get(s)
                if a is None: sec[s] = [px, (-q if maker else q), 1]
                else: a[0] = px; a[1] += (-q if maker else q); a[2] += 1
        ks = np.array(sorted(sec), dtype=np.int64); v = np.array([sec[k] for k in ks])
        np.savez_compressed(f, t=ks, px=v[:, 0], flow=v[:, 1], n=v[:, 2]); print(mkt, day, len(ks), flush=True)
