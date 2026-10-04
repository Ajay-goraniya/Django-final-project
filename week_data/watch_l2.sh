#!/bin/bash
# Emit one line per check; exit when done or when the downloader dies unexpectedly.
cd "$(dirname "$0")"
while true; do
  n=$(ls depth/l2 2>/dev/null | wc -l)
  alive=$(pgrep -c -f "[d]l_l2.py")
  if grep -q "^DONE" logs/l2.log 2>/dev/null; then
    echo "L2 COMPLETE: $(grep '^DONE' logs/l2.log | tail -1) files=$n"; exit 0
  fi
  if [ "$alive" -eq 0 ]; then
    echo "L2 DOWNLOADER STOPPED EARLY at $n/144 files — last log: $(tail -1 logs/l2.log)"; exit 1
  fi
  sleep 45
done
