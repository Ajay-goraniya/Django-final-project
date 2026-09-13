#!/usr/bin/env python3
"""Real BTCUSDT USD-M perp L2 incremental depth for the 2026-08-29/30 weekend,
from CryptoHFTData's free tier (no key, 60 req/min). Raw hourly parquet, nothing
transformed. Same source and layout as the six weekday/weekend days already held."""
import pathlib, subprocess, time
OUT = pathlib.Path("depth/l2"); OUT.mkdir(parents=True, exist_ok=True)
DAYS = ["2026-08-29", "2026-08-30"]
jobs = [(d, h) for d in DAYS for h in range(24)]
ok = fail = skip = 0; t0 = time.time()
for i, (d, h) in enumerate(jobs, 1):
    dest = OUT / f"BTCUSDT_orderbook_{d}_{h:02d}.parquet"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        skip += 1; continue
    src = f"binance_futures/{d}/{h:02d}/BTCUSDT_orderbook.parquet"
    r = subprocess.run(["cryptohftdata", "download", "--file", src, "--output", str(dest)],
                       capture_output=True, text=True, timeout=900)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 1_000_000:
        ok += 1
    else:
        fail += 1; dest.unlink(missing_ok=True)
        print(f"  MISS {d} {h:02d}: {(r.stderr or r.stdout).strip()[:110]}", flush=True)
    if i % 6 == 0:
        print(f"  {i}/{len(jobs)}  ok={ok} fail={fail} skip={skip}  {time.time()-t0:.0f}s", flush=True)
print(f"DONE ok={ok} fail={fail} skip={skip} in {time.time()-t0:.0f}s", flush=True)
