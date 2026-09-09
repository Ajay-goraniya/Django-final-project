#!/bin/bash
# Build 11 launcher: relaunches on the feed watchdog exit (code 3) or a crash, on the SAME
# database. Never resets. Usage: ./run_v11.sh --port 8788 --db ~/b11/v11.sqlite3 [--reset once]
cd "$(dirname "$0")"
export V11_MODE="${V11_MODE:-pnl}"
ARGS=("$@")
while true; do
  python3 btc_model_build11.py "${ARGS[@]}"
  code=$?
  # drop --reset after the first launch so a relaunch never wipes the database
  ARGS=("${ARGS[@]/--reset/}")
  if [ "$code" -eq 0 ] || [ "$code" -eq 130 ]; then exit 0; fi
  echo "[run_v11] exited with $code at $(date -u +%T) UTC; relaunching in 5 s (same database)"
  sleep 5
done
