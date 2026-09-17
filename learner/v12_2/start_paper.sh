#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if command -v termux-wake-lock >/dev/null 2>&1; then termux-wake-lock; fi
exec python btc_model_v12_polymarket.py --mode pnl --capital 50 --db polymarket_v12_paper.sqlite3 --port 8787 "$@"
