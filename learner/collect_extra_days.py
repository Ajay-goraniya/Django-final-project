#!/usr/bin/env python3
"""collect_extra_days.py DATE... -- real data for additional training days.
Binance Vision spot + USD-M perp aggTrades, Polymarket markets (Gamma) and
trade tape (data-api). No order-book depth for these days (no free archive),
so depth features are absent; the trainer handles that explicitly.
Writes into the same layout build_features.py already reads."""
import datetime as dt, io, json, pathlib, sys, time, urllib.request, zipfile, concurrent.futures as cf
import numpy as np, pandas as pd, pyarrow as pa, pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://data.binance.vision/data"


def get(url, tries=4, timeout=60):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if "404" in str(e): return None
            time.sleep(2 * (i + 1))
    return None


def csv_zip(url, cols):
    raw = get(url, timeout=600)
    if raw is None: return None
    z = zipfile.ZipFile(io.BytesIO(raw)); txt = z.read(z.namelist()[0]).decode()
    lines = [l for l in txt.splitlines() if l.strip()]
    if lines and not lines[0][0].isdigit(): lines = lines[1:]
    return pd.DataFrame([l.split(",")[:len(cols)] for l in lines], columns=cols)


def binance(d, out):
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "spot_aggtrades_00.parquet").exists():
        s = csv_zip(f"{BASE}/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{d}.zip",
                    ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "timestamp", "is_buyer_maker", "is_best_match"])
        if s is None: return "no spot"
        ts = s.timestamp.astype("int64"); ts = ts * (1000 if ts.iloc[0] < 1e15 else 1)
        t = pa.table({"timestamp": ts.values, "price": s.price.astype(float).values,
                      "quantity": s.quantity.astype(float).values,
                      "is_buyer_maker": s.is_buyer_maker.str.strip().str.lower().eq("true").values})
        pq.write_table(t, out / "spot_aggtrades_00.parquet", compression="zstd")
    if not (out / "perp_trades_00.parquet").exists():
        p = csv_zip(f"{BASE}/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-{d}.zip",
                    ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "timestamp", "is_buyer_maker"])
        if p is None: return "no perp"
        ts = p.timestamp.astype("int64"); ts = ts * (1000 if ts.iloc[0] < 1e15 else 1)
        px = p.price.astype(float).values; q = p.quantity.astype(float).values
        bm = p.is_buyer_maker.str.strip().str.lower().eq("true").values
        agg = np.where(bm, -1, 1).astype(np.int8)
        t = pa.table({"timestamp": ts.values, "price": px, "quantity": q,
                      "signed_quote_notional": px * q * agg, "quote_notional": px * q})
        pq.write_table(t, out / "perp_trades_00.parquet", compression="zstd")
    return "ok"


def gamma(d):
    dest = ROOT / f"ef_arch/polymarket/fiveday/data/markets/btc5m_markets_{d}.json"
    if dest.exists(): return "have"
    w0 = int(dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
    rows, missing = [], []
    for k in range(288):
        ep = w0 + k * 300
        raw = get(f"https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{ep}", timeout=30)
        j = json.loads(raw) if raw else []
        if not j: missing.append(ep); continue
        ev = j[0]; mk = (ev.get("markets") or [{}])[0]
        rows.append({"k": k, "epoch": ep, "event": {kk: ev.get(kk) for kk in ("id", "slug", "title", "startDate", "endDate", "closed")}, "market": mk})
        time.sleep(0.1)
    dest.write_text(json.dumps({"date": d, "W0": w0, "rows": rows, "missing": missing}))
    return f"{len(rows)} markets, {len(missing)} missing"


def run(d):
    out = ROOT / "week_replay" / d / "normalized"
    r1 = binance(d, out)
    r2 = gamma(d)
    r3 = "trades " + str(__import__("subprocess").run([sys.executable, str(ROOT / "ef_arch/polymarket/fiveday/fetch_trades_day.py"), d],
                                                       capture_output=True, text=True, cwd=str(ROOT / "ef_arch/polymarket/fiveday")).stdout.strip()[-60:])
    r4 = __import__("subprocess").run([sys.executable, str(ROOT / "week_data/build_poly_inferred_touch.py"), d],
                                      capture_output=True, text=True, cwd=str(ROOT / "week_data")).stdout.strip()[-70:]
    return f"{d}: binance {r1} | gamma {r2} | {r3} | touch {r4}"


if __name__ == "__main__":
    days = sys.argv[1:]
    with cf.ThreadPoolExecutor(3) as ex:
        for line in ex.map(run, days):
            print(line, flush=True)
