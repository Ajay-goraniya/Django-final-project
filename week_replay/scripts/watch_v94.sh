#!/bin/bash
cd "$(dirname "$0")"
while true; do
  done_n=$(grep -l "^ *\"elapsed_s\"" ../2026-*/v94_result_*.json 2>/dev/null | wc -l)
  alive=$(pgrep -fc "[r]eplay_v94.py")
  tot=$(for d in 2026-08-31 2026-09-02 2026-09-03 2026-09-04 2026-09-05 2026-09-06; do
          python3 -c "
import sqlite3
try: print(sqlite3.connect('file:../$d/v94_$d.sqlite3?mode=ro',uri=True).execute('select count(*) from candles').fetchone()[0])
except Exception: print(0)" 2>/dev/null; done | paste -sd+ | bc)
  if [ "$done_n" -ge 6 ]; then echo "V94 ALL 6 DAYS COMPLETE (candles $tot/1728)"; exit 0; fi
  if [ "$alive" -eq 0 ]; then echo "V94 STOPPED EARLY: $done_n/6 days done, $alive procs, candles $tot/1728"; exit 1; fi
  sleep 60
done
