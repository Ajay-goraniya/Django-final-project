# btc_replay_2026-08-01_24h

Real BTCUSDT market data for a causal 24-hour replay.

**Window:** `2026-08-01 00:00:00 UTC` → `2026-08-02 00:00:00 UTC` (end exclusive) — 288 × 5-minute candles.
**Pre-roll:** `2026-07-31 23:45:00 UTC` → `2026-08-01 00:00:00 UTC` (partial — see *Missing data*).

Canonical clock is **UTC**. Every normalized file uses a `timestamp` column of
**int64 microseconds** since the UNIX epoch. No timestamp was rewritten to local
time and no network latency was invented.

This bundle is **data only** — no model, adapter, backtest or strategy report.

---

## Layout

```
raw/          original provider files, byte-for-byte unmodified
normalized/   replay-ready Parquet (zstd), hourly partitions
validation/   validation.json + reconstruction stats
scripts/      acquisition, normalization, validation, manifest
manifest.json SHA256 + provenance for every file
```

## Normalized files

### `spot_klines_5m.parquet` — 288 rows (+ `..._preroll.parquet`, 3 rows)
Binance spot 5-minute klines.
`open_time, open, high, low, close, volume, close_time, quote_volume,
trade_count, taker_buy_base_volume, taker_buy_quote_volume`
`open_time` / `close_time` are exchange microseconds.

### `perp_depth20_<HH>.parquet` — top-20 book, hourly (00–23)
Reconstructed from Tardis `incremental_book_L2` strictly chronologically.

| column | meaning |
|---|---|
| `timestamp` | exchange clock, µs |
| `local_timestamp` | Tardis collector **receive** clock, µs |
| `bid_px_0..19`, `bid_qty_0..19` | bids, index 0 = best (highest) |
| `ask_px_0..19`, `ask_qty_0..19` | asks, index 0 = best (lowest) |
| `is_resync` | 1 = row is a provider snapshot block (book reset here) |
| `n_bid_levels`, `n_ask_levels` | full book depth held at that moment |
| `is_crossed` | 1 if best_bid ≥ best_ask |

One row per book-update message. Sufficient to derive zone 1‑5 / 6‑10 / 11‑20
imbalance, ~800‑1800 ms replenishment, event OFI, microprice and deep-book
persistence by differencing consecutive rows.

### `perp_trades_<HH>.parquet` — tick trades (Tardis)
`timestamp, local_timestamp, id, side, aggressor, price, quantity,
quote_notional, signed_quote_notional`
`aggressor` is `+1` buy / `-1` sell (taker side). Supports 250 ms / 1 s / 2 s /
5 s / 30 s flow and 120 s microstructure memory.

### `perp_aggtrades_<HH>.parquet` — Binance USD-M aggregated trades
`agg_trade_id, price, quantity, first_trade_id, last_trade_id,
transact_time_ms, timestamp, is_buyer_maker, aggressor, quote_notional,
signed_quote_notional`
Raw archive is **milliseconds**; `timestamp` is the µs-normalized value and
`transact_time_ms` preserves the original.

### `spot_aggtrades_<HH>.parquet` — Binance spot aggregated trades
Same shape, plus `is_best_match`. Raw archive is already microseconds.

Each trade family also has a `*_preroll.parquet`.

## Causality

* The book at row *N* reflects only messages ≤ *N*. No later row repairs an
  earlier one; nothing is interpolated or back-filled.
* `is_snapshot` blocks are genuine provider snapshots used for initialization
  and resync — they reset the book rather than patching it.
* Levels with `amount == 0` are deletions.
* Rows carry the provider's own timestamps. Consumers must not read row *N+1*
  when serving time *N*.

## Verification

`validation/validation.json` contains kline/trade/depth checks. The reconstruction
is additionally cross-checked level-by-level against Tardis' independently
produced `book_snapshot_25` at identical timestamps — see
`depth_reconstruction_crosscheck`.

Reproduce end-to-end:
```
scripts/download_raw.sh
python3 scripts/reconstruct_perp_depth20.py
python3 scripts/normalize_trades_klines.py
python3 scripts/validate.py
python3 scripts/make_manifest.py
```

## Missing data

| Marker | Detail |
|---|---|
| `SPOT_DEPTH_UNAVAILABLE` | Binance publishes no historical spot L2 depth publicly (spot daily families: aggTrades, klines, trades only). |
| `PREDICT_BOOK_HISTORY_UNAVAILABLE` | `api.predict.fun/v1/markets` → HTTP 401; no read credential. |
| `PRE_ROLL_PERP_DEPTH_UNAVAILABLE` | Tardis free tier serves only the first day of each month, so 2026‑07‑31 perp L2 cannot be retrieved. Pre-roll covers spot klines/aggTrades and perp aggTrades only. |
| `SEQUENCE_IDS_UNAVAILABLE` | Tardis `incremental_book_L2` CSV carries no exchange update id; ordering is provider file order within equal `(timestamp, local_timestamp)`. |

Receive clock **is** available for all Tardis rows (`local_timestamp`); Binance
Vision archives carry exchange time only.
