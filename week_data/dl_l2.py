#!/usr/bin/env python3
"""Real BTCUSDT USD-M perp L2 incremental depth for the missing replay days, from CryptoHFTData's
free tier (no key, 60 req/min). One raw hourly parquet per hour, nothing transformed."""
import pathlib, subprocess, sys, time
OUT = pathlib.Path("depth/l2"); OUT.mkdir(parents=True, exist_ok=True)
DAYS = ["2026-08-31", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
jobs = [(d, h) for d in DAYS for h in range(24)]
ok = fail = skip = 0; t0 = time.time()
for d, h in jobs:
    dest = OUT / f"BTCUSDT_orderbook_{d}_{h:02d}.parquet"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        skip += 1; continue
    src = f"binance_futures/{d}/{h:02d}/BTCUSDT_orderbook.parquet"
    r = subprocess.run(["cryptohftdata", "download", "--file", src, "--output", str(dest)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode == 0 and dest.exists() and dest.stat().st_size > 1_000_000:
        ok += 1
    else:
        fail += 1; dest.unlink(missing_ok=True)
        print(f"  MISS {d} {h:02d}: {(r.stderr or r.stdout).strip()[:110]}", flush=True)
    if (ok + fail) % 12 == 0:
        mb = sum(f.stat().st_size for f in OUT.glob('*.parquet')) / 1e6
        print(f"  {ok} ok / {fail} miss / {skip} cached  {mb:,.0f} MB  {time.time()-t0:.0f}s", flush=True)
    time.sleep(1.05)
mb = sum(f.stat().st_size for f in OUT.glob('*.parquet')) / 1e6
print(f"DONE ok={ok} miss={fail} cached={skip} files={len(list(OUT.glob('*.parquet')))} {mb:,.0f} MB {time.time()-t0:.0f}s")
