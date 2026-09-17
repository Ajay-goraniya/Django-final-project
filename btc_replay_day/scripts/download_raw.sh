#!/bin/bash
# Acquire raw provider files for 2026-08-01 24h window (+ pre-roll from Binance).
# Files are saved permanently under raw/ and never modified afterwards.
set -u
cd "$(dirname "$0")/.."; DATE="${DATE:-2026-08-01}"; PREV=$(date -u -d "$DATE -1 day" +%F); Y=${DATE:0:4}; M=${DATE:5:2}; DD=${DATE:8:2}; mkdir -p "$DATE/raw/tardis" "$DATE/raw/binance"
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
dl "$T/incremental_book_L2/$Y/$M/$DD/BTCUSDT.csv.gz" "$DATE/raw/tardis/binance-futures_incremental_book_L2_${DATE}_BTCUSDT.csv.gz"
dl "$T/trades/$Y/$M/$DD/BTCUSDT.csv.gz" "$DATE/raw/tardis/binance-futures_trades_${DATE}_BTCUSDT.csv.gz"
dl "$T/book_snapshot_25/$Y/$M/$DD/BTCUSDT.csv.gz" "$DATE/raw/tardis/binance-futures_book_snapshot_25_${DATE}_BTCUSDT.csv.gz"

# --- Binance Vision: spot klines + spot/perp aggTrades, target day + pre-roll day ---
for d in "$DATE" "$PREV"; do
  dl "$B/spot/daily/klines/BTCUSDT/5m/BTCUSDT-5m-$d.zip"          "$DATE"/raw/binance/spot_klines5m_$d.zip
  dl "$B/spot/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-$d.zip"   "$DATE"/raw/binance/spot_aggTrades_$d.zip
  dl "$B/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-aggTrades-$d.zip" "$DATE"/raw/binance/perp_aggTrades_$d.zip
done
echo "=== DOWNLOAD PHASE DONE ==="
ls -la "$DATE"/raw/tardis "$DATE"/raw/binance
