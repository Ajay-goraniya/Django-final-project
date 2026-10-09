#!/usr/bin/env python3
"""Polymarket BTC 5m markets + resolved Chainlink outcome for 2026-08-29/30.
Same shape as ef_arch/polymarket/fiveday/data/markets/btc5m_markets_<date>.json
so the existing report/join code reads it without change. Gamma blocks the
default urllib user-agent, hence the explicit header."""
import datetime, json, pathlib, time, urllib.error, urllib.request

OUT = pathlib.Path("../ef_arch/polymarket/fiveday/data/markets")
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (i + 1)); continue
            if e.code == 404:
                return []
            time.sleep(1 + i)
        except Exception:
            time.sleep(1 + i)
    return None

for D in ("2026-08-29", "2026-08-30"):
    dest = OUT / f"btc5m_markets_{D}.json"
    if dest.exists():
        print(f"  have {dest.name}"); continue
    w0 = int(datetime.datetime.strptime(D, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())
    rows, missing = [], []
    for k in range(288):
        ep = w0 + k * 300
        j = get(f"https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{ep}")
        if not j:
            missing.append(ep); continue
        ev = j[0]
        mk = (ev.get("markets") or [{}])[0]
        rows.append({"k": k, "epoch": ep,
                     "event": {kk: ev.get(kk) for kk in
                               ("id", "slug", "title", "startDate", "endDate", "closed")},
                     "market": mk})
        if k % 48 == 0:
            print(f"  {D} {k}/288  resolved={sum(1 for r in rows if (r['market'].get('umaResolutionStatus')=='resolved'))}", flush=True)
        time.sleep(0.12)
    payload = {"date": D, "W0": w0, "rows": rows, "missing": missing}
    dest.write_text(json.dumps(payload))
    res = sum(1 for r in rows if r["market"].get("outcomePrices"))
    print(f"  {dest.name}: {len(rows)} markets, {res} with outcomes, {len(missing)} missing", flush=True)
print("poly weekend markets complete", flush=True)
