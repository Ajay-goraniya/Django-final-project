#!/bin/bash
# Full faithful EF day: DATE=YYYY-MM-DD ./run_day.sh   (Tardis free day: 1st of month; pmxt v2 must have the day)
set -u; cd "$(dirname "$0")"; export DATE="${DATE:?set DATE}"; LOG="../$DATE/run_day.log"; mkdir -p "../$DATE"
echo "=== $DATE start $(date -u +%FT%TZ)" | tee -a "$LOG"
( ./download_raw.sh && python3 reconstruct_perp_depth20.py && python3 normalize_trades_klines.py && python3 replay_build36_day.py --hours 0-23 ) >> "$LOG" 2>&1 &
BTC=$!
( python3 map_markets.py && python3 extract_day.py all && python3 build_ladders.py ) >> "../$DATE/polymarket.log" 2>&1 &
PM=$!
wait $BTC; echo "btc side exit $?" | tee -a "$LOG"; wait $PM; echo "polymarket side exit $?" | tee -a "$LOG"
python3 reprice_ef_fires.py > "../$DATE/ef_repriced_$DATE.txt" 2>&1; echo "=== $DATE done $(date -u +%FT%TZ)" | tee -a "$LOG"
