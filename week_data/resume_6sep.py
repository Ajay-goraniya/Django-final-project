#!/usr/bin/env python3
"""Resume the 2026-09-06 aggTrade pulls from the last id already on disk. Real rows only."""
import csv, json, sys, time, urllib.request, pathlib
DAY0, DAY1 = 1788652800000, 1788652800000 + 86400000
def get(u):
    for a in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "curl/8.5.0"}), timeout=45) as r:
                return json.load(r)
        except Exception:
            if a == 7: raise
            time.sleep(1.5 * (a + 1))
def resume(path, base):
    p = pathlib.Path(path)
    with p.open() as f:
        last = None
        for row in csv.reader(f):
            last = row
    cur = int(last[0]) + 1
    n = 0; lastT = int(last[5]); t0 = time.time()
    with p.open("a", newline="") as f:
        w = csv.writer(f)
        while True:
            d = get(f"{base}?symbol=BTCUSDT&fromId={cur}&limit=1000")
            if not d: break
            stop = False
            for x in d:
                if x["T"] >= DAY1: stop = True; break
                w.writerow([x["a"], x["p"], x["q"], x["f"], x["l"], x["T"], x["m"]]); n += 1; lastT = x["T"]
            cur = d[-1]["a"] + 1
            if stop or len(d) < 1000: break
            if n % 100000 < 1000: print(f"  +{n:,} rows, {time.time()-t0:.0f}s", flush=True)
            time.sleep(0.05)
    print(f"DONE {p.name}: +{n:,} rows, last T {lastT}", flush=True)
resume(sys.argv[1], sys.argv[2])
