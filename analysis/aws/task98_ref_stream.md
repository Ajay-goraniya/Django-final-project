2026-09-16 02:0x UTC — logger source committed as analysis/aws/ref_stream_logger.py; 12 verbatim frames in
analysis/aws/ref_stream_samples.jsonl (subscribe frame, the empty ack frame the server sends first, then 5
crypto_prices_chainlink btc/usd and 5 crypto_prices btcusdt). Endpoint wss://ws-live-data.polymarket.com/ , no credentials.
2026-09-16 09:2x UTC snapshot — ref_stream.sqlite3.gz: 109,980 ticks over 7.77 h (crypto_prices_chainlink btc/usd
54,574; crypto_prices btcusdt 55,406), 95 market rows, 30 gaps totalling 747.3 s (3.3% of the span, all websocket
reconnects, no backfill available). gz 2,530,878 bytes. Committed locally as ed2d86a; this box cannot push.

## Task 108 — how far the Binance TWAP60 proxy sits from the real Chainlink line
Window: 2026-09-16 01:44–09:29 UTC, 7.80 h, 26,993 seconds carrying both series.

(1) Level error, bps of the Chainlink value:
    |chainlink − binance spot|        n=26,993  median 8.4  p90 9.3   max 18.6
    |chainlink − TWAP60(binance)|     n=26,952  median 8.3  p90 10.8  max 18.4
    Sign: Binance is above Chainlink in 100.0% of seconds, both measures. This is a persistent basis
    (BTC/USDT premium vs Chainlink's cross-venue USD aggregate), not noise.

(2) Per candle, TWAP60(close) vs TWAP60(open), on epochs fully covered and present in venues.outcome:
    n=72 candles. proxy vs chainlink 2x2 — (UP,UP) 39, (DOWN,DOWN) 32, (UP,DOWN) 1, (DOWN,UP) 0.
    chainlink rule vs venue 72/72 (100%);  proxy rule vs venue 71/72 (98.6%);  proxy agrees with chainlink 71/72.
    The single discordant candle: Chainlink right, proxy wrong.
    n=72 is under 60 per CELL (the off-diagonal is 1), so the agreement rate is reportable but the
    disagreement rate is INSUFFICIENT — one flip cannot be turned into a probability.

(3) Gap exclusion: 89 epochs in the window had a venue outcome; 15 touched one of the 30 stream gaps and
    were dropped; 74 clean; 72 of those had all four TWAPs computable (>=45 of 60 seconds present).

(4) Verdict: the proxy is SAFE FOR DIRECTION and unsafe for level. The 8.4 bps basis is one-sided and
    cancels in a close-minus-open comparison; what matters is the error in the MOVE, which is median
    0.22 bps, p90 0.68, max 1.02. The typical candle move is 5.4 bps (p10 1.1). So the error budget is
    ~1 bps against a 5 bps signal — comfortable in the middle, marginal on the smallest tenth of candles,
    which is exactly where the one observed flip sits. Never substitute the proxy for the settlement LEVEL.

## 2026-09-16 11:55 UTC - CORRECTION: the tick counts I reported were doubled

Two copies of `ref_logger.py` have been running since ~01:44 UTC - pids 121526 and 121543, both
orphaned to init, started 40 s apart. `ticks` had no unique constraint and the insert was a plain
`INSERT`, so both processes wrote every tick.

| | rows |
|---|---|
| ticks as stored | 142,940 |
| unique (topic, symbol, src_ts_ms, value) | 72,212 |
| exact duplicates | 70,728 (49.5%) |

Span is unchanged at 10.10 h, 2026-09-16 01:44:17 -> 11:50:34 UTC; markets 123, gaps 41. **Every
tick count I have reported for Task 98/107 since 01:44 is roughly 2x the real one** - the 110k and
141,780 figures should read ~55k and ~72,212. No value is wrong and nothing is missing; the rows are
byte-identical copies, so the deduplicate is exact and no analysis conclusion changes. The true rate
is ~1 tick/s per topic, which is what the design intended.

Fixed so far:
- `learner/live_backup/ref_stream.sqlite3.gz` now holds the **deduplicated** snapshot
  (`ref_stream_dedup.sqlite3`, 72,212 ticks, built with sqlite `backup()` so the live writers were
  not disturbed). Previous uploads of this artifact were doubled.
- `ref_logger.py` now creates `UNIQUE INDEX ticks_u ON ticks(topic, symbol, src_ts_ms, value)` and
  inserts with `INSERT OR IGNORE`, so a second writer or a replayed frame after a reconnect is a
  no-op. Backup of the old file at `ref_logger.py.bak`.

**Still open:** the patch is on disk only. Both loggers are still running the old code, so the live
`ref_stream.sqlite3` keeps doubling. `kill 121526` was refused by this session's permission layer
(Interfere With Workloads). One of the two processes has to be stopped by hand, and the survivor
restarted so it picks up the unique index - until then every fresh snapshot needs the same dedupe
pass. This is the third time a stray duplicate process has corrupted a logger table on this box
(book1s depth/trades on 09-16, now ref_stream); the unique index is the durable fix, not the kill.
