#!/bin/bash
# parallel workers: one per date; map markets then pull trade tape
cd "$(dirname "$0")"
for d in 2026-08-22 2026-08-24 2026-08-27 2026-08-31 2026-09-05; do
  ( python3 map_markets_day.py $d && python3 fetch_trades_day.py $d ) > "data/worker_$d.log" 2>&1 &
done
wait; echo ALL_DONE
