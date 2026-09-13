#!/bin/bash
# Package the replay bundle for download + emit SHA256SUMS.
# The 404 MB Tardis incremental_book_L2 raw file is excluded from the archive by
# default (INCLUDE_BIG_RAW=1 to include it): its source URL and SHA256 are in
# manifest.json and scripts/ regenerate every derived file from it byte-for-byte.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="btc_replay_2026-08-01_24h"
DEST="$(cd .. && pwd)"
BIG="raw/tardis/binance-futures_incremental_book_L2_2026-08-01_BTCUSDT.csv.gz"

EXCL=(--exclude=logs --exclude='*.part' --exclude=.gitignore)
[ "${INCLUDE_BIG_RAW:-0}" = "1" ] || EXCL+=("--exclude=$(basename "$BIG")")

cd ..
tar czf "$DEST/$NAME.tar.gz" "${EXCL[@]}" "$NAME"
cd "$DEST"

SIZE=$(stat -c%s "$NAME.tar.gz")
LIMIT=$((1500 * 1024 * 1024))
if [ "$SIZE" -gt "$LIMIT" ]; then
  split -b 1400m -d -a 2 "$NAME.tar.gz" "$NAME.part"
  rm -f "$NAME.tar.gz"
  sha256sum "$NAME".part* > "${NAME}_SHA256SUMS.txt"
else
  sha256sum "$NAME.tar.gz" > "${NAME}_SHA256SUMS.txt"
fi
# also record hashes of the normalized payload itself
( cd "$NAME" && find normalized validation manifest.json README.md -type f -exec sha256sum {} \; ) \
  >> "${NAME}_SHA256SUMS.txt"
echo "--- package ready ---"
ls -la "$DEST"/"$NAME"*.tar.gz "$DEST"/"$NAME".part* 2>/dev/null || true
cat "${NAME}_SHA256SUMS.txt" | head -3
