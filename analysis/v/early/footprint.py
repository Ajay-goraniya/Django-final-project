#!/usr/bin/env python3
"""Footprint features from Binance aggTrades (V, 09-28, owner: "order flow, delta, footprint, perp data, order book").
The engine already carries windowed delta / OFI / book imbalance and they are already in the venue price (NC-16). What it does NOT
compute is the FOOTPRINT - volume by price level inside the candle. This builds, per 5m candle and second S, from PERP (the venue
that leads) and SPOT aggTrades:
  absorb30    aggressor delta over 30 s divided by (|30 s return| + 1 bps): big one-sided aggression that failed to move price
  stack_up/dn number of consecutive $5 levels in the last 60 s where buy vol >= 3x sell vol (dn: the reverse), nearest the price
  poc_vs_px   (price - point of control since candle open) in bps; poc_vs_line (POC - TWAP60 line) in bps
  acc_above   share of candle volume traded above the TWAP60 line
  big_delta   delta of prints >= the day's 99th-percentile size, since open, normalised by total volume
  cvd_div     sign(price at new high/low of the candle) x -sign(CVD change over the same 30 s) : price extreme not confirmed by CVD
Output: footprint_rows.json keyed by candle epoch -> {S: {feature: value}} for S in SECS.
usage: footprint.py <YYYY-MM-DD> [<YYYY-MM-DD> ...]"""
import sys, os, io, csv, json, zipfile, urllib.request, socket, datetime as dt, collections, math
import numpy as np
socket.setdefaulttimeout(60)
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get('FP_CACHE', '/tmp/claude-0/-home-user-Django-final-project/6e3b6e11-d14f-50d1-8719-c1998d0e6b9a/scratchpad/aggtrades')
URL = {'perp': 'https://data.binance.vision/data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{d}.zip',
       'spot': 'https://data.binance.vision/data/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{d}.zip'}
SECS = (60, 120, 150, 180, 200, 220, 240)
LEVEL = 5.0


def load(kind, day):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, f'{kind}-{day}.zip')
    if not os.path.exists(fn):
        req = urllib.request.Request(URL[kind].format(d=day), headers={'User-Agent': 'v-check'})
        with urllib.request.urlopen(req, timeout=120) as r, open(fn, 'wb') as f: f.write(r.read())
    z = zipfile.ZipFile(fn); name = z.namelist()[0]
    ts, px, qty, sell = [], [], [], []
    with z.open(name) as fh:
        for row in csv.reader(io.TextIOWrapper(fh)):
            if not row or not row[0][0].isdigit(): continue
            t = int(row[5]); t = t // 1000 if t > 10**14 else t          # spot 2025+ is microseconds
            ts.append(t); px.append(float(row[1])); qty.append(float(row[2])); sell.append(row[6].strip().lower() in ('true', '1'))
    o = np.argsort(ts, kind='stable')
    return np.array(ts)[o], np.array(px)[o], np.array(qty)[o], np.array(sell)[o]


def feats_for_day(day, closes_line):
    """closes_line: epoch -> TWAP60 line (from spot 1 s closes). Returns {epoch: {S: feats}}."""
    ts, px, q, sell = load('perp', day)
    sgn = np.where(sell, -1.0, 1.0)
    big = np.quantile(q, 0.99)
    d0 = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp())
    out = {}
    for e in range(d0, d0 + 86400, 300):
        L = closes_line.get(e)
        if L is None: continue
        i0, i1 = np.searchsorted(ts, e * 1000), np.searchsorted(ts, (e + 300) * 1000)
        if i1 - i0 < 200: continue
        T, P, Q, G = ts[i0:i1], px[i0:i1], q[i0:i1], sgn[i0:i1]
        per = {}
        for S in SECS:
            k = np.searchsorted(T, (e + S) * 1000)
            if k < 50: continue
            t, p, qq, g = T[:k], P[:k], Q[:k], G[:k]
            now = p[-1]
            w30 = t >= (e + S - 30) * 1000; w60 = t >= (e + S - 60) * 1000
            if w30.sum() < 5: continue
            d30 = float((qq[w30] * g[w30]).sum()); v30 = float(qq[w30].sum()) + 1e-9
            r30 = (now / p[w30][0] - 1) * 1e4
            absorb = (d30 / v30) / (abs(r30) + 1.0)
            lv = np.floor(p[w60] / LEVEL); bv = collections.Counter(); sv = collections.Counter()
            for l, x, s in zip(lv, qq[w60], g[w60]):
                (bv if s > 0 else sv)[l] += x
            cur = math.floor(now / LEVEL)
            def stack(buy):
                n = 0
                for off in range(0, 8):
                    for l in ((cur - off,) if buy else (cur + off,)):
                        a, b = (bv[l], sv[l]) if buy else (sv[l], bv[l])
                        if a >= 3 * b and a > 0: n += 1
                        elif n: return n
                return n
            vol_lv = collections.Counter()
            for l, x in zip(np.floor(p / LEVEL), qq): vol_lv[l] += x
            poc = (max(vol_lv, key=vol_lv.get) + 0.5) * LEVEL
            above = float(qq[p >= L].sum()) / float(qq.sum())
            bd = float((qq[qq >= big] * g[qq >= big]).sum()) / float(qq.sum())
            hi, lo = p.max(), p.min()
            ext = 1 if now >= hi - 0.5 else (-1 if now <= lo + 0.5 else 0)
            cvd_div = float(ext * -np.sign(d30)) if ext else 0.0
            per[S] = dict(absorb30=absorb, stack_up=stack(True), stack_dn=stack(False), poc_vs_px=(now - poc) / now * 1e4,
                          poc_vs_line=(poc - L) / L * 1e4, acc_above=above, big_delta=bd, cvd_div=cvd_div, d30=d30 / v30, r30=r30)
        if per: out[str(e)] = {str(S): v for S, v in per.items()}
    return out


if __name__ == '__main__':
    sys.path.insert(0, os.path.join(HERE, '..', 'twap'))
    bnf = os.path.join(HERE, 'binance_1s_btc.json')
    bn = {int(k): v for k, v in json.load(open(bnf)).items()}
    line = {}
    for e in range(min(bn) // 300 * 300 + 300, max(bn), 300):
        v = [bn[k] for k in range(e - 60, e) if k in bn]
        if len(v) >= 45: line[e] = sum(v) / len(v)
    outf = os.path.join(HERE, 'footprint_rows.json')
    allrows = json.load(open(outf)) if os.path.exists(outf) else {}
    for day in sys.argv[1:]:
        r = feats_for_day(day, line); allrows.update(r)
        print(f'{day}: {len(r)} candles', flush=True)
        json.dump(allrows, open(outf, 'w'))
