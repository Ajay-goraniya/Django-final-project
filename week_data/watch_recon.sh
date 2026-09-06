#!/bin/bash
cd "$(dirname "$0")"
while true; do
  n=$(ls depth/depth20 2>/dev/null | grep -c "^perp_depth20_.*\.parquet$")
  done_days=$(grep -l "^DONE" logs/recon_2026-*.log 2>/dev/null | wc -l)
  alive=$(pgrep -c -f "[r]econstruct_depth20.py")
  if [ "$done_days" -eq 6 ]; then echo "RECON COMPLETE: $n hourly ladder files"; exit 0; fi
  if [ "$alive" -eq 0 ]; then
    echo "RECON STOPPED EARLY: $done_days/6 days finished, $n files. Errors: $(grep -ihE 'error|traceback' logs/recon_2026-*.log | tail -2)"; exit 1
  fi
  sleep 45
done
