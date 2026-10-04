#!/usr/bin/env python3
"""Pick a FIXED random sample of 100 candles from the replay data on disk.

Written once, seeded, and saved to disk so every model is tested on exactly
the same candles. Only candles that have (a) normalized market data, (b) a
resolved Chainlink outcome and (c) a real Polymarket quote are eligible, so no
model is scored on a candle that cannot be priced or graded.
"""
import json, pathlib, random, sys, collections
import pyarrow.parquet as pq

ROOT = pathlib.Path(__file__).resolve().parents[2]
DAYS = ["2026-08-29", "2026-08-30", "2026-08-31", "2026-09-02",
        "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
SEED = 20260908
N = 100
CANDLE_MS = 300_000
OUT = ROOT / "week_replay" / "candles100.json"

settle, quoted = {}, collections.Counter()
for d in DAYS:
    f = ROOT / f"ef_arch/polymarket/fiveday/data/markets/btc5m_markets_{d}.json"
    for r in json.loads(f.read_text())["rows"]:
        m = r["market"]
        try:
            names = json.loads(m["outcomes"]); prices = json.loads(m["outcomePrices"])
        except Exception:
            continue
        w = [n for n, p in zip(names, prices) if str(p) == "1"]
        if len(w) == 1:
            settle[int(r["epoch"])] = w[0].strip().upper()
    q = ROOT / f"week_data/predictfun/quotes_1s_unified/poly_1s_{d}.parquet"
    t = pq.read_table(q, columns=["window_epoch", "side", "quote_source"])
    ep = t.column("window_epoch").to_pylist(); sd = t.column("side").to_pylist()
    qs = t.column("quote_source").to_pylist()
    for i in range(t.num_rows):
        if qs[i] != "none":
            quoted[(ep[i], str(sd[i]).upper())] += 1

elig = collections.defaultdict(list)
for d in DAYS:
    day_dir = ROOT / "week_replay" / d / "normalized"
    if not day_dir.exists():
        continue
    import datetime as dt
    w0 = int(dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())
    for k in range(288):
        ep = w0 + k * 300
        # need >= 3 candles of warm-up inside the same day, both sides quoted, and an outcome
        if k < 3:
            continue
        if ep not in settle:
            continue
        if quoted[(ep, "UP")] < 120 or quoted[(ep, "DOWN")] < 120:
            continue
        elig[d].append(ep)

tot = sum(len(v) for v in elig.values())
print(f"eligible candles: {tot}")
for d in DAYS:
    print(f"  {d}: {len(elig[d])}")

rnd = random.Random(SEED)
# stratify: proportional across days so no single day dominates
picked = []
per = {d: max(1, round(N * len(elig[d]) / tot)) for d in elig}
while sum(per.values()) > N:
    per[max(per, key=per.get)] -= 1
while sum(per.values()) < N:
    per[min(per, key=per.get)] += 1
for d in DAYS:
    if d in elig and per.get(d):
        picked += [(d, e) for e in rnd.sample(elig[d], min(per[d], len(elig[d])))]
picked.sort(key=lambda x: x[1])
rows = [{"date": d, "epoch": e, "candle_open_ms": e * 1000,
         "actual": settle[e]} for d, e in picked]
OUT.write_text(json.dumps({"seed": SEED, "n": len(rows), "days": DAYS,
                           "candles": rows}, indent=1))
print(f"\npicked {len(rows)} candles -> {OUT}")
byday = collections.Counter(r["date"] for r in rows)
for d in DAYS:
    print(f"  {d}: {byday[d]}")
up = sum(1 for r in rows if r["actual"] == "UP")
print(f"\noutcome balance: UP {up}  DOWN {len(rows)-up}")
