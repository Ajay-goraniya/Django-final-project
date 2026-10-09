# How long were those shares actually available?

Owner, verbatim: *"we saw shares at 0.30 in the book, sent an order, and it was rejected. How long were
those shares actually available, and how fast did they disappear?"*

Read-only. Source: a dedicated 2 h millisecond probe (`analysis/zurich/ms_probe.py`, run 05:30–07:30 UTC
09-27), BTC 5m tokens, **4,170,380 top-of-book events** (50,556 `book` + 4,119,824 `price_change`), 25,163
trade messages, 50 tokens, 23 settled epochs. Nothing else on this box could answer the question:
`decide_log` is throttled to one row per 250 ms and `tape1s` is 1 Hz, so neither resolves a 50 ms event.

Two clocks are logged and used for different things on purpose. Durations **within** the venue's stream use
the venue's own `timestamp`, because those messages share one clock. Anything comparing Binance to
Polymarket uses our local receive time, because two venues' clocks cannot be differenced. Here the two
agree to the millisecond, which is itself a check that the venue's stamps are sane.

## The answer: a median of 6–10 ms, and 95% are gone before we could be matched

| measure | n | p10 | **p50** | p90 | ≤50 ms | ≤100 ms | ≤200 ms | ≤250 ms | ≤500 ms |
|---|---|---|---|---|---|---|---|---|---|
| **LEVEL** — best-ask price, until it is no longer best | 17,314 | 2 ms | **68 ms** | 2,392 ms | 45.5% | 54.4% | 61.8% | 64.9% | 73.3% |
| **SIZE** — the specific (price, size), any change | 357,626 | 1 ms | **6 ms** | 89 ms | 84.9% | 90.9% | 95.3% | 96.4% | 98.5% |
| **SIZE, adverse only** — until the size shrinks or goes | 141,299 | 1 ms | **10 ms** | 120 ms | 80.6% | 88.3% | 93.9% | 95.2% | 97.9% |

Against our ~**230 ms** from seeing the book to being matched:

- **63.7%** of best-ask *price levels* are already gone.
- **94.7%** of the specific *share offerings* are already gone, counting only adverse endings.

The "any change" row is reported but it flatters the picture: **60.5% of those endings were the size
GROWING**, not disappearing. The adverse-only row is the honest answer, and it barely differs — p50 10 ms
instead of 6 ms — so the conclusion does not depend on that choice.

So the shares seen at 0.30 were, at the median, available for about **ten milliseconds**. The rejection is
not a bug in our order path; it is the expected outcome of a 230 ms path against a 10 ms quote.

## How they end: two thirds are CANCELLED, not taken

A level is classified TAKEN if a `last_trade_price` for that token at that price lands within ±100 ms of
the end; otherwise CANCELLED.

| ending | n | share | p50 | ≤50 ms | ≤100 ms | ≤250 ms |
|---|---|---|---|---|---|---|
| **CANCELLED (no trade)** | 11,757 | **67.9%** | **49 ms** | 50.5% | 59.4% | 68.5% |
| TAKEN by a trade | 5,557 | 32.1% | 171 ms | 34.8% | 43.8% | 57.4% |

**Two thirds of best-ask disappearances are cancellations, and cancelled levels die more than three times
faster than traded ones (49 ms vs 171 ms).** That is NC-10's mechanism measured directly from the venue's
own stream: the maker pulls the quote, we are not losing a race to other takers.

## Split by whether the candle settled that way (venue resolution)

| | n | p50 | ≤250 ms | taken by a trade |
|---|---|---|---|---|
| candle went that way | 8,169 | 73 ms | 64.6% | **37.5%** |
| candle went the other way | 8,694 | 60 ms | 66.4% | **27.0%** |
| unsettled inside the window | 451 | 444 ms | 43.2% | 32.4% |

Lifetimes are nearly identical either way (73 ms vs 60 ms), so the *speed* of disappearance is not
informed. What differs is the *ending*: when the candle ends up going the token's way the level is taken
**37.5%** of the time against **27.0%** when it does not — a 10.5 pp adverse-selection gap. The shares we
want are the ones most likely to be lifted by someone else rather than cancelled.

## What this implies

1. **No reduction in our own latency reaches a 10 ms quote.** Going from 230 ms to even 50 ms still
   arrives after 80.6% of adverse size changes.
2. The fix cannot be "be faster on the taker path". It has to be either resting a maker order, or
   accepting a worse price with a cap wide enough to survive the pull, or sizing to what the *second*
   level holds rather than the touch.
3. It also explains the depth number from the ETH shadow: quoting $2.30 at the touch and a 10 ms life are
   the same phenomenon seen from two directions.
