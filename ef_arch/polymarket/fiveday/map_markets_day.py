#!/usr/bin/env python3
"""Map every 5-minute UTC window of a date to its Polymarket BTC Up/Down market via Gamma.
usage: map_markets_day.py YYYY-MM-DD   -> data/markets/btc5m_markets_<date>.json"""
import json, time, urllib.request, sys, datetime, pathlib
HERE = pathlib.Path(__file__).resolve().parent
G = "https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{}"
def run(date):
    W0 = int(datetime.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())
    out = HERE / "data" / "markets" / f"btc5m_markets_{date}.json"
    if out.exists(): print(date, "cached"); return out
    rows = []; missing = []
    for k in range(288):
        ep = W0 + 300 * k; d = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(G.format(ep), headers={"User-Agent": "research/1.0"}), timeout=30) as r:
                    d = json.load(r); break
            except Exception:
                time.sleep(1.5 * (attempt + 1))
        if not d: missing.append(ep); continue
        ev = d[0]; mk = (ev.get("markets") or [None])[0]
        rows.append({"k": k, "epoch": ep, "event": {x: ev.get(x) for x in ("id", "slug", "title", "startDate", "endDate", "closed")}, "market": mk})
        time.sleep(0.1)
    json.dump({"date": date, "W0": W0, "rows": rows, "missing": missing}, open(out, "w"))
    print(f"{date}: mapped {len(rows)}/288 missing {len(missing)}", flush=True); return out
if __name__ == "__main__":
    run(sys.argv[1])
