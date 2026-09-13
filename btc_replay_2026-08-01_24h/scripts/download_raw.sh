#!/bin/bash
# Acquire raw provider files for 2026-08-01 24h window (+ pre-roll from Binance).
# Files are saved permanently under raw/ and never modified afterwards.
set -u
cd "$(dirname "$0")/.."
T="https://datasets.tardis.dev/v1/binance-futures"
B="https://data.binance.vision/data"

dl(){ # url dest
  local url="$1" dest="$2" try=0
  [ -s "$dest" ] && { echo "SKIP  $dest"; return 0; }
  while [ $try -lt 4 ]; do
    if curl -sS --fail --max-time 3600 -o "$dest.part" "$url"; then
      mv "$dest.part" "$dest"; echo "OK    $dest ($(stat -c%s "$dest") bytes)"; return 0
    fi
    try=$((try+1)); echo "RETRY($try) $url"; sleep $((2**try))
  done
  echo "FAIL  $url"; rm -f "$dest.part"; return 1
}

# --- Tardis: BTCUSDT USD-M perpetual microstructure (2026-08-01, free tier) ---
dl "$T/incremental_book_L2/2026/08/01/BTCUSDT.csv.gz" raw/tardis/binance-futures_incremental_book_L2_2026-08-01_BTCUSDT.csv.gz
dl "$T/trades/2026/08/01/BTCUSDT.csv.gz"              raw/tardis/binance-futures_trades_2026-08-01_BTCUSDT.csv.gz
dl "$T/book_snapshot_25/2026/08/01/BTCUSDT.csv.gz"    raw/tardis/binance-futures_book_snapshot_25_2026-08-01_BTCUSDT.csv.gz

# --- Binance Vision: spot klines + spot/perp aggTrades, target day + pre-roll day ---
for d in 2026-08-01 2026-07-31; do
  dl "$B/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-$d.zip"          raw/binance/spot_klines5m_$d.zip
  dl "$B/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-$d.zip"   raw/binance/spot_aggTrades_$d.zip
  dl "$B/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-$d.zip" raw/binance/perp_aggTrades_$d.zip
done
echo "=== DOWNLOAD PHASE DONE ==="
ls -la raw/tardis raw/binance
