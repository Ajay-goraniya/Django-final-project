# How many ms before the book moves against us?

Read-only. Same 2 h probe (05:30–07:30 UTC 09-27): Binance `bookTicker` mid against the Polymarket BTC 5m
best ask on the side the move favours (BTC up → the UP token). **296,362 Binance book updates**, 32,878
trades, 50 Polymarket tokens with a top-of-book series.

**Clock choice, and it is not cosmetic: this comparison uses only our local receive time.** Binance's
`bookTicker` on the combined stream carries **no event timestamp at all** (the field is absent, so the
venue-clock column would be zero), and even where both venues stamp a message their clocks cannot be
differenced — a latency built from two clocks is fiction. Local receive time is one clock, and it is the
clock our own engine lives on.

A move is counted when the mid differs from its value 1 s earlier by ≥ the threshold, with a 1 s cooldown
per direction so one sustained move is not counted hundreds of times. Reaction = the first moment the
favoured side's best ask **rises or is pulled**, i.e. the moment the price we decided on is gone.

## The window was quiet, and that bounds what can be said

| statistic | value |
|---|---|
| BTC mid range over the whole 2 h | **30.2 bps** (84,399 → 84,654) |
| \|1 s move\| p50 / p90 / p99 / p99.9 / **max** | 0.00 / 1.17 / 4.20 / 5.20 / **5.24 bps** |
| share of samples ≥3 bps / ≥5 bps / ≥10 bps | 1.714% / 0.179% / **0.000%** |

So a **≥10 bps 1-second move never happened** in this window and ≥5 bps happened twice. V's specified
3/5/10 bps rows are printed with their real n and marked insufficient rather than dressed up; the lower
thresholds are added so there is a usable number at all.

## Reaction time of the favoured side's best ask (local-receive ms, 5 s horizon)

| move | events | measured | p10 | **p50** | p90 | ≤50 ms | ≤100 ms | ≤200 ms | ≤500 ms | no reaction |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.5 bps | 183 | **153** | 6 | **136** | 713 | 29.4% | 41.8% | **77.1%** | 88.9% | 16.4% |
| 1 bps | 89 | **74** | 5 | **128** | 615 | 33.8% | 43.2% | **79.7%** | 89.2% | 16.9% |
| 2 bps | 27 | 24* | 4 | 110 | 705 | 29.2% | 45.8% | 83.3% | 83.3% | 11.1% |
| 3 bps | 6 | 5* | 1 | 47 | 2,707 | 60.0% | 60.0% | 60.0% | 80.0% | 16.7% |
| 5 bps | 2 | 1* | 5 | 5 | 5 | 100% | 100% | 100% | 100% | 50.0% |
| 10 bps | 0 | — | — | — | — | — | — | — | — | no events this size |

`*` = under 60 measured, not a reading.

## Against our order path

Our ~**230 ms** from seeing the book to being matched sits **past the median reaction and past the 200 ms
bucket**: on the two rows with real sample, the venue has already moved the favoured ask in **77–80%** of
cases before we could be filled. Reaction p50 is **128–136 ms**, roughly half our path.

That is the same conclusion `ASK_LIFETIME_MS.md` reaches from the other side, and the lifetime measurement
is the stronger of the two — 17,314 level episodes and 141,299 adverse size changes against 153 move
events here. Where they differ in emphasis, prefer the lifetime file: it needs no Binance move to exist
and no cross-venue clock reasoning at all.

**What is still missing:** a volatile window. The ≥10 bps row is the one the owner's question most needs
and this capture cannot supply it. A re-run during a high-volatility hour would fill the 3/5/10 bps rows;
the probe is a standalone script and can be re-armed at any time.
