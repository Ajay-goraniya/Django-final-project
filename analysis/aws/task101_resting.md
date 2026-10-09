# Task 101 — would a resting order below the ask have filled, and would it have won?

Source: the three paper journals on the AWS box (8787 12.9.0, 8793 12.8.11, twin_1290 12.9.0).
**Sampling caveat that governs the whole table:** this box has no 1 Hz book logger. The only per-second-ish
price record is the `_ask_up`/`_ask_dn` pair inside each decide diagnostics row — about 19 rows per candle,
median **8 of them after the fire**. So "reachable" here means "seen at or below that price in one of ~8
post-fire samples", which UNDERSTATES true reachability and cannot resolve a 1-tick step. H1's simulator on
the polybook log is the authority; this is a cross-check, not a replacement.

Only post-fire observations are counted — a resting order placed at the fire second can only fill later.

| fire sec bucket | fires | ask−1 reached (candle went the fire's way) | ask−2 | ask−3 |
|---|---|---|---|---|
| 0–60    | 13 | 12 (5) | 12 (5) | 12 (5) |
| 60–120  | 28 | 21 (13) | 21 (13) | 21 (13) |
| 120–180 | 12 | 9 (1) | 9 (1) | 9 (1) |
| 180–240 | 11 | 5 (0) | 5 (0) | 5 (0) |
| **total** | **64** | **47 (19)** | **47 (19)** | **47 (19)** |

Reading, held loosely: 47 of 64 fires saw the ask trade at least 1 tick below the paid price after the fire,
but only 19 of those 47 (40.4%) were candles that went the fire's way — i.e. the cheap re-quote is mostly the
market moving against the position, which is exactly when a resting order fills and then loses. The ask−1,
ask−2 and ask−3 columns are identical because the 8-sample grid cannot separate 1¢ steps; that is a
measurement limit, not a finding about the book.

**Verdict: INSUFFICIENT.** Every cell is under 60 and the 1-tick resolution is not there. No recommendation.

---
**Closure (V, 09-17):** superseded by H1's resting-order test on the real polybook tape - 492 fires,
k=1..5 x TTL 15..299 all negative, FILLED 378 win 40.7% vs NOT-FILLED 114 win 99.1%, Fisher p=7.7e-35
(this is R-18, CLOSED - price capture loses to the touch). This file's n=64 estimate pointed the same
direction and is superseded, not contradicted.
