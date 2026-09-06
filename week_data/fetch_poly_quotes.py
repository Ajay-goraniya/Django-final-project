#!/usr/bin/env python3
"""Real Polymarket BTC 5m price history for every market of a day, both tokens.
Source: clob.polymarket.com/prices-history at fidelity=1 (the venue's finest public setting,
about one point per minute). Real quotes only; no interpolation, no synthetic points."""
import json, pathlib, sys, time, urllib.request, concurrent.futures as cf
import pandas as pd
H = pathlib.Path(__file__).resolve().parent
MK = H.parent / "ef_arch/polymarket/fiveday/data/markets"
OUT = H / "predictfun/quotes"; OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "research/1.0"}
def get(u):
    for a in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40) as r:
                return json.load(r)
        except Exception:
            if a == 4: return None
            time.sleep(1.2 * (a + 1))
def one(args):
    ep, side, tok = args
    h = get(f"https://clob.polymarket.com/prices-history?market={tok}&startTs={ep}&endTs={ep+300}&fidelity=1")
    if not h: return []
    return [dict(window_epoch=ep, side=side, token_id=tok, ts=x["t"], price=float(x["p"]))
            for x in h.get("history", [])]
def run(day):
    out = OUT / f"poly_quotes_{day}.parquet"
    if out.exists(): print(day, "cached"); return
    M = json.load(open(MK / f"btc5m_markets_{day}.json"))
    jobs = []
    for r in M["rows"]:
        m = r["market"]; toks = json.loads(m["clobTokenIds"]); outs = json.loads(m["outcomes"])
        for t, o in zip(toks, outs): jobs.append((r["epoch"], o.upper(), t))
    rows = []
    with cf.ThreadPoolExecutor(6) as ex:
        for i, res in enumerate(ex.map(one, jobs)):
            rows += res
            if i % 200 == 0: print(f"  {day} {i}/{len(jobs)} pts={len(rows):,}", flush=True)
    D = pd.DataFrame(rows)
    D.to_parquet(out, compression="zstd", index=False)
    print(f"DONE {day}: {len(D):,} quote points, {D.window_epoch.nunique()} markets -> {out.name}", flush=True)
if __name__ == "__main__":
    for d in sys.argv[1:]: run(d)
