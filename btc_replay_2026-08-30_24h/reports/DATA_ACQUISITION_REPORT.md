# BTC 24h Full-Replay Dataset — Acquisition Report

**Status: `NOT_REPLAY_READY` — acquisition STOPPED at the stop condition.**

Target window: **2026-08-30 00:00:00 UTC → 2026-08-31 00:00:00 UTC (end exclusive)**
(Sunday → Monday, 288 × 5-minute candles). Canonical clock: UTC.
Europe/London label for the window start: 2026-08-30 01:00 BST (UTC+1).

Probed: 2026-09-05 (see `validation/source_probe.json` for raw HTTP evidence).
Reproduce with `python3 probe_sources.py`.

---

## 1. Verdict

Per the task's **STOP CONDITIONS**:

> If you cannot obtain enough historical PERP depth to reconstruct the exact model
> features, STOP after documenting the attempted sources. Do not downgrade to OHLC
> and continue pretending it is equivalent.

That condition is met. **BTCUSDT perpetual `depth20@100ms` for 2026-08-30 is not
obtainable from any free or public source, and no paid-provider credentials exist
in this environment.** No replay bundle was built, because any bundle produced
without perp depth would misrepresent itself as able to drive Build36's EF core.

Nothing was fabricated, interpolated, or substituted. No orders were placed. MASTER
was not enabled. No Build36 logic was modified (see §2 — it is not present).

## 2. Blockers

### B1 — Perp `depth20@100ms` unavailable *(hard stop)*

Build36's EF core is specified to compute zone 1–5 / 6–10 / 11–20 imbalance,
~800–1800 ms replenishment, event OFI, microprice, deep persistence and book
handoff. All of these require **per-price-level top-20 book state at ~100 ms
cadence**. The Binance public archive does not publish any L2 dataset:

| Archive tree | Dataset families actually published |
|---|---|
| `data/spot/daily/` | `aggTrades`, `klines`, `trades` |
| `data/futures/um/daily/` | `aggTrades`, `bookDepth`, `bookTicker`, `klines`, `trades`, `metrics`, `indexPriceKlines`, `markPriceKlines`, `premiumIndexKlines` |
| `data/futures/um/monthly/` | same minus `bookDepth`/`metrics` |

There is **no** `depth`, `bookSnapshot` or `incrementalDepth` path — each returned
0 keys on an authoritative S3 listing (not merely a 404 guess).

**`bookDepth` is not a substitute.** Inspected directly for the target day:

```
timestamp,percentage,depth,notional
2026-08-30 00:00:04,-5.00,9904.59500000,756745782.18470000
2026-08-30 00:00:04,-1.00,2091.68600000,162747079.02620000
2026-08-30 00:00:04,-0.20,397.23600000,31030556.94590000
```

It is **12 cumulative percentage buckets (±0.2/1/2/3/4/5 %) sampled every 30 s**
(34,560 rows / 12 = 2,880 snapshots/day). It carries no individual price levels
and no 100 ms cadence, so it cannot yield zone imbalance, replenishment, event OFI
or microprice. Using it in place of depth20 would be exactly the prohibited
downgrade.

**`bookTicker` (top-of-book L1) is also unavailable for this date** — the S3
listing contains no `2026-08` key and a direct GET returns HTTP 404. So even a
degraded L1-only book lane cannot be built for 2026-08-30.

### B2 — Predict.fun historical books unavailable

`GET https://api.predict.fun/v1/markets` → **HTTP 401 unauthorized**. No
Predict.fun API key or read credential is present in this environment. Marked
`PREDICT_BOOK_HISTORY_UNAVAILABLE`. No 0–1 price was synthesized from BTC
movement.

### B3 — Build36 / Build35 source not present *(independent blocker)*

`btc_model_v9_3_BUILD36.py` and `btc_model_v9_3_BUILD35.py` do not exist anywhere
on this filesystem (repo is an unrelated Django project). The task requires
deriving input requirements from source and driving production methods
(`EFPerpPrep.on_trade` / `on_depth`). Without the source, a "Build36-compatible
adapter" could only be guessed — which the task explicitly forbids. Deliverable
#10 is therefore not producible even if depth data were obtained.

## 3. Sources attempted

| Source | Artefact requested | Result |
|---|---|---|
| Binance Vision (S3 listing) | any spot/perp L2 depth path | **0 keys — dataset does not exist** |
| Binance Vision | perp `bookTicker` 2026-08-30 (L1 fallback) | **HTTP 404 — not published** |
| Binance Vision | perp `bookDepth` 2026-08-30 | HTTP 200 — %-buckets @30 s, **insufficient** |
| Binance REST `fapi/v1/depth` | live depth | **HTTP 451** geo-restricted (and live-only; cannot be retro-fetched) |
| Tardis.dev | `book_snapshot_25` 2026-08-30 | **HTTP 401** — "only … the first day of each month are available" |
| Tardis.dev | `incremental_book_L2` 2026-08-30 | **HTTP 401** — same gate |
| Tardis.dev | `book_snapshot_25` 2026-08-01 (control) | HTTP 200, 47.7 MB — *proves the data exists but is paywalled for our date* |
| CoinAPI | orderbook history | **HTTP 401** — paid key required |
| Kaiko | order-book snapshots | **HTTP 403** — paid |
| CryptoHFTData | dataset API | **HTTP 404** — no public/anonymous access |
| Predict.fun | `/v1/markets` | **HTTP 401** — no credential |

The Tardis control request is the decisive evidence: the exact required dataset
*is* archived by commercial vendors, but every retrieval path for **2026-08-30**
is credential-gated. Free historical Binance L2 does not exist; the only free
route is live WebSocket capture, which cannot be performed retroactively.

## 4. What *is* obtainable for this window (not built)

Verified present and downloadable, should you want a flow-only dataset:

| Artefact | Size | Notes |
|---|---|---|
| spot klines 5m | 15.1 KB | **288 candles verified**, consecutive, unique, no gaps, all completed |
| spot aggTrades | 10.9 MB | full event stream |
| perp aggTrades | 10.0 MB | full event stream |
| perp bookDepth | 560 KB | %-buckets @30 s — diagnostic only |

Kline sanity check (first/last rows of the target day):

```
open  1788048000000000  o=78230.00  h=78238.22  l=78205.15  c=78205.15
close 1788134100000000  o=77571.54  h=77734.61  l=77556.41  c=77682.00
```

**Timestamp semantics note for any future acquisition code:** current Binance
archives emit **microsecond** epochs (`1788048000000000`), not milliseconds. Naive
`ts/1000` parsing yields year 58630.

That set supports trade-flow and candle-geometry work only. It **cannot** support
zone imbalance, replenishment, OFI, microprice, deep persistence, book handoff, or
Build36 quote economics — i.e. it is not the causal event dataset requested, and I
have not packaged it as one.

## 5. Clock semantics (for the record)

| Clock | Availability |
|---|---|
| `exchange_time` | available in aggTrades/klines archives |
| `provider_capture_time` | not provided by Binance Vision |
| `local_download_time` | recordable at acquisition |
| `original_receive_time` | **not available** → `LIVE_RECEIVE_CLOCK_NOT_EXACT` |

No latency jitter was invented.

## 6. To unblock

1. **Perp + spot depth (required).** A Tardis.dev subscription covering
   2026-08-30 (`incremental_book_L2` for exact reconstruction, or
   `book_snapshot_25` to derive top-20 directly); Kaiko, CoinAPI or CryptoHFTData
   are equivalent alternatives. Provide the key as an env var — the acquisition
   script can then stream, reconstruct the book chronologically and emit causal
   top-20 snapshots.
2. **Predict.fun read credential**, plus confirmation that historical 5-minute
   market books are retained and exposed. Without it the ceiling is
   `DIRECTIONAL_REPLAY_READY`, never `FULL_REPLAY_READY`.
3. **`btc_model_v9_3_BUILD36.py` (and BUILD35)** added to the repo, so the schema
   and adapter are derived from source rather than guessed.
4. **Alternative:** pick a window on the **first day of a month**, where Tardis
   serves full L2 free. E.g. 2026-08-01 00:00→2026-08-02 00:00 UTC is a Saturday
   and its `book_snapshot_25` file is confirmed retrievable (HTTP 200, 47.7 MB).
   That trades the Sunday→Monday session profile for genuine depth data — the only
   route to a real full replay at zero cost.

---

## Final summary

```
WINDOW:
2026-08-30 00:00:00 UTC -> 2026-08-31 00:00:00 UTC

CANDLES:
288 / 288 (available, not packaged)

SPOT AGGTRADES:
available, not downloaded (10.9 MB archive)

SPOT DEPTH:
0 - DATASET DOES NOT EXIST IN ANY PUBLIC ARCHIVE

PERP AGGTRADES:
available, not downloaded (10.0 MB archive)

PERP DEPTH:
0 - depth20@100ms UNOBTAINABLE (paywalled at every vendor for this date)

PREDICT MARKETS:
0/288 - PREDICT_BOOK_HISTORY_UNAVAILABLE (HTTP 401, no credential)

PREDICT BOOK COVERAGE:
0%

DATASET SIZE:
n/a - no dataset packaged

REPLAY VERDICT:
NOT_REPLAY_READY

BLOCKERS:
1. BTCUSDT perp depth20@100ms unavailable for 2026-08-30 (hard stop).
   Binance publishes no L2; Tardis/CoinAPI/Kaiko/CryptoHFTData all
   credential-gated for this date; bookTicker L1 fallback also absent (404).
2. Predict.fun historical books require auth (HTTP 401); no key present.
3. btc_model_v9_3_BUILD35.py / BUILD36.py absent, so no faithful adapter
   can be written and no schema can be derived from source.
```

No strategy performance claims are made. The next task (running Build35/Build36
over these 288 candles) **cannot** proceed faithfully until blocker 1 is resolved.
