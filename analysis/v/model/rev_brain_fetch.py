#!/usr/bin/env python3
"""REV brain, step 1: rebuild per-second Binance series from data.binance.vision (V, 09-27).

For each UTC day writes <out>/<day>.npz with arrays indexed by second-of-day s (bucket s = events with
timestamp in [s, s+1) seconds, so bucket s is COMPLETE only at time s+1 - the feature builder reads bucket <= t-1):
  spot 1s klines   : sc (close), sh, sl, sv (volume), stb (taker-buy volume)
  spot aggTrades   : sbuy, ssell (taker buy / sell base qty)
  perp aggTrades   : pc (last trade price in the second, NaN if none), pbuy, psell, pn (agg trades)
  perp bookDepth   : bd_ts (snapshot unix s), bd (n x 12 depth at -5,-4,-3,-2,-1,-0.2,0.2,1,2,3,4,5 %)
Spot archive timestamps are microseconds (2025+), perp milliseconds; both are normalised here.
Zips are streamed and deleted - the container has ~4 GB free."""
import argparse, io, os, subprocess, zipfile, datetime as dt, numpy as np, pandas as pd

ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--days', nargs='+', required=True)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
B = 'https://data.binance.vision/data/'
PCT = [-5, -4, -3, -2, -1, -0.2, 0.2, 1, 2, 3, 4, 5]

def get(path):
    r = subprocess.run(['curl', '-sSf', '--retry', '3', B + path], capture_output=True, check=True)
    z = zipfile.ZipFile(io.BytesIO(r.stdout)); return z.open(z.namelist()[0]).read()

def to_s(ts):                                     # -> float seconds, handles us / ms
    ts = np.asarray(ts, dtype=np.float64)
    return np.where(ts > 1e14, ts / 1e6, ts / 1e3)

for day in a.days:
    fn = os.path.join(a.out, day + '.npz')
    if os.path.exists(fn): print(day, 'exists'); continue
    d0 = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp())
    N = 86400; out = {'d0': d0}
    # spot 1s klines
    k = pd.read_csv(io.BytesIO(get(f'spot/daily/klines/BTCUSDT/1s/BTCUSDT-1s-{day}.zip')), header=None)
    s = (to_s(k[0].values) - d0).astype(int); ok = (s >= 0) & (s < N)
    for nm, col in (('sc', 4), ('sh', 2), ('sl', 3)):
        x = np.full(N, np.nan); x[s[ok]] = k[col].values[ok]; out[nm] = x
    for nm, col in (('sv', 5), ('stb', 9)):
        x = np.zeros(N); x[s[ok]] = k[col].values[ok]; out[nm] = x
    # spot aggTrades
    t = pd.read_csv(io.BytesIO(get(f'spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{day}.zip')), header=None, usecols=[2, 5, 6])
    s = np.floor(to_s(t[5].values) - d0).astype(int); ok = (s >= 0) & (s < N)
    mk = t[6].astype(str).str.lower().values == 'true'                     # buyer is maker -> taker SELL
    q = t[2].values
    out['sbuy'] = np.bincount(s[ok & ~mk], q[ok & ~mk], N); out['ssell'] = np.bincount(s[ok & mk], q[ok & mk], N)
    del t
    # perp aggTrades
    t = pd.read_csv(io.BytesIO(get(f'futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{day}.zip')))
    s = np.floor(to_s(t['transact_time'].values) - d0).astype(int); ok = (s >= 0) & (s < N)
    mk = t['is_buyer_maker'].astype(str).str.lower().values == 'true'; q = t['quantity'].values; p = t['price'].values
    out['pbuy'] = np.bincount(s[ok & ~mk], q[ok & ~mk], N); out['psell'] = np.bincount(s[ok & mk], q[ok & mk], N)
    out['pn'] = np.bincount(s[ok], None, N).astype(float)
    ss, pp, tt = s[ok], p[ok], t['transact_time'].values[ok]
    o = np.lexsort((np.arange(len(tt)), tt)); ss, pp = ss[o], pp[o]             # time order, file order on ties
    u, li = np.unique(ss[::-1], return_index=True)                             # LAST trade of each second
    pc = np.full(N, np.nan); pc[u] = pp[::-1][li]; out['pc'] = pc
    del t
    # perp bookDepth
    b = pd.read_csv(io.BytesIO(get(f'futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-{day}.zip')))
    b['ts'] = (pd.to_datetime(b['timestamp'], utc=True) - pd.Timestamp('1970-01-01', tz='UTC')) // pd.Timedelta('1s')
    w = b.pivot_table(index='ts', columns='percentage', values='depth', aggfunc='last').sort_index()
    w = w.reindex(columns=PCT); out['bd_ts'] = w.index.values.astype(np.int64); out['bd'] = w.values
    np.savez_compressed(fn, **out)
    print(day, 'klines', int(np.isfinite(out['sc']).sum()), 'perp secs', int(np.isfinite(out['pc']).sum()), 'depth rows', len(w), flush=True)
