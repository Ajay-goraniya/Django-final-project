#!/usr/bin/env python3
"""Map every 5-minute UTC window of 2026-08-01 to its Polymarket BTC Up/Down market via Gamma."""
import sys as _sys, pathlib as _pl; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import daycfg as CFG
import json, time, urllib.request, sys
W0 = CFG.W0; OUT = str(CFG.MARKETS_JSON)
G = "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}"
rows = []; missing = []
for k in range(288):
    ep = W0 + 300 * k; url = G.format(ep)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research/1.0"}), timeout=30) as r:
                d = json.load(r); break
        except Exception as e:
            d = None; time.sleep(1.5 * (attempt + 1))
    if not d:
        missing.append(ep); continue
    ev = d[0]; mk = (ev.get("markets") or [None])[0]
    rows.append({"k": k, "epoch": ep, "event": {x: ev.get(x) for x in ("id", "slug", "title", "startDate", "endDate", "closed")}, "market": mk})
    if k % 48 == 0: print(f"  k={k} ep={ep} ok  ({len(rows)} mapped)", flush=True)
    time.sleep(0.12)
json.dump({"W0": W0, "rows": rows, "missing": missing}, open(OUT, "w"))
print(f"\nmapped {len(rows)}/288   missing {len(missing)}: {missing[:10]}")
m = rows[0]["market"]
print("\nmarket keys:", sorted(m.keys()))
for k in ("id", "question", "conditionId", "clobTokenIds", "outcomes", "outcomePrices", "closed", "resolvedBy", "umaResolutionStatus",
          "feesEnabled", "makerBaseFee", "takerBaseFee", "fee", "fees", "startDate", "endDate", "resolutionSource", "description"):
    if k in m: print(f"  {k}: {str(m[k])[:300]}")
from collections import Counter
print("\noutcomePrices distribution:", Counter(str(r["market"].get("outcomePrices")) for r in rows).most_common(4))
print("closed:", Counter(str(r["market"].get("closed")) for r in rows))
