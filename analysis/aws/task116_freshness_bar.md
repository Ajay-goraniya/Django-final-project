# Task 116 - grid the 0.75 s freshness bar against real settled outcomes

2026-09-16 14:0x UTC. Pool: 1,598 graded fires, 658 distinct candles, 6 days (09-11 to 09-16),
from poly_pnl, v10_poly_long4 and v12_poly_lane. **All 1,598 graded on `venues.outcome`** (every row
matched the oracle; none fell back to a lane's own actual). Fires carry the book age the lane saw at
the fire - `book_age_ms` in the first two lanes, `quote_age_ms` in v12_lane - which is what makes the
counterfactual possible: these fires really happened, at ages the live 0.75 s bar would refuse.

## 1. The bar sweep, as asked, every cell

| bar | ADMITTED n | W | hit% | pnl/$1 | pnl $ | +days | REFUSED n | W | hit% | pnl/$1 | pnl $ | +days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.25 s | 1431 | 741 | 51.8 | +0.1560 | +2232.23 | 4/6 | 167 | 106 | 63.5 | +0.3552 | +593.11 | 5/6 |
| 0.50 s | 1443 | 749 | 51.9 | +0.1565 | +2257.84 | 4/6 | 155 | 98 | 63.2 | +0.3661 | +567.50 | 5/6 |
| **0.75 s (live)** | 1448 | 754 | 52.1 | +0.1602 | +2319.85 | 4/6 | **150** | 93 | **62.0** | **+0.3370** | **+505.49** | 5/6 |
| 1 s | 1454 | 754 | 51.9 | +0.1554 | +2259.85 | 4/6 | 144 | 93 | 64.6 | +0.3927 | +565.49 | 5/6 |
| 2 s | 1472 | 765 | 52.0 | +0.1577 | +2321.75 | 4/6 | 126 | 82 | 65.1 | +0.3997 | +503.59 | 5/6 |
| 5 s | 1516 | 795 | 52.4 | +0.1670 | +2531.67 | 4/6 | 82 | 52 | 63.4 | +0.3581 | +293.67 | 5/5 |
| 10 s | 1598 | 847 | 53.0 | +0.1768 | +2825.34 | 4/6 | 0 | - | - | - | - | insufficient |
| none | 1598 | 847 | 53.0 | +0.1768 | +2825.34 | 4/6 | 0 | - | - | - | - | insufficient |

Read naively this says the bar refuses the best trades at every setting. **That reading is wrong, and
the next section is why.**

## 2. The confound: the refused cohort is a fire-second cohort, not an age cohort

Fire second in the refused cohort: p10 31 s, median 35 s, p90 39 s. In the admitted cohort: p10 18 s,
median 69 s, p90 185 s. **142 of the 150 refused fires sit in the 30-45 s band.** That is the second
after the 5-minute rollover, when the new market's book has not been quoted yet - so "stale book" and
"just after rollover" are the same population. Paid price is nearly identical between cohorts
(median 0.470 refused vs 0.450 admitted), so it is not an extreme-odds artifact either.

| fire second | age <= 750 ms: n / hit% / pnl per $1 | age > 750 ms: n / hit% / pnl per $1 |
|---|---|---|
| 0-30 s | 332 / 48.2 / -0.0010 | 3 / 100.0 / +0.9608 (insufficient) |
| **30-45 s** | **99 / 62.6 / +0.3453** | **142 / 61.3 / +0.3292** |
| 45-90 s | 428 / 52.8 / +0.1943 | 0 (insufficient) |
| 90-180 s | 410 / 53.7 / +0.2318 | 5 (insufficient) |
| 180-300 s | 179 / 48.0 / +0.1114 | 0 (insufficient) |

## 3. The decisive cell - matched on fire second, the age carries no information

| cell | n | hit% | pnl/$1 | pnl $ | +days | halves | 0c | 1c | 2c | 3c | 5c |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 30-45 s, age <= 250 ms | 89 | 62.9 | +0.3479 | +309.62 | 5/6 | +0.552 / +0.148 | +0.348 | +0.319 | +0.291 | +0.265 | +0.215 |
| 30-45 s, age > 5 s | 82 | 63.4 | +0.3581 | +293.67 | 5/5 | +0.258 / +0.458 | +0.358 | +0.329 | +0.301 | +0.275 | +0.224 |
| 30-45 s, age <= 750 ms | 99 | 62.6 | +0.3453 | +341.87 | 5/6 | +0.483 / +0.211 | +0.345 | +0.316 | +0.289 | +0.262 | +0.213 |
| 30-45 s, age > 750 ms | 142 | 61.3 | +0.3292 | +467.41 | 5/6 | +0.086 / +0.572 | +0.329 | +0.300 | +0.273 | +0.246 | +0.197 |
| 45-300 s, age <= 750 ms | 1017 | 52.3 | +0.1948 | +1981.31 | 4/6 | +0.106 / +0.283 | +0.195 | +0.167 | +0.141 | +0.116 | +0.069 |

A book more than 5 seconds old and a book under a quarter of a second old, fired in the same window,
return **+0.3581 and +0.3479 per dollar** - a gap of 0.01 on samples of 82 and 89. No sign flip in
halves on any readable cell. The edge survives the costs axis on both: at 5c over the quote the
30-45 s cells still pay +0.215 and +0.224, against +0.069 for everything after 45 s.

Finer age splits inside 30-45 s: <=250 ms +0.3479 (n=89), 250-750 ms +0.3225 (n=10), 750-2000 ms
-0.0387 (n=19), 2-5 s +0.4417 (n=41), >5 s +0.3581 (n=82). **Non-monotone, and every middle cell is
under 60.** Per your own rule that is noise, and it is not read.

## 4. Answer to the question as posed

**The bar is not earning its keep as a staleness filter.** Staleness does not predict a worse
outcome: matched on fire second, a 5-second-old book performs the same as a 250-millisecond-old one,
across 171 fires, two independent halves and five cost levels.

**But the money it costs is not the money the sweep in section 1 appears to show.** What the bar
actually does is refuse the 30-45 s window disproportionately, and that window is where the edge is:
+0.345 per dollar against +0.195 for everything after 45 s and -0.001 for everything before 30 s.
Over these 6 days the bar refused 142 fires that returned +$467 at 0c and +$280 at 5c.

## 5. What this grid does NOT license

The 1,228 live decide rows blocked by the bar never became fires, so **no outcome exists for them**
and none is in this sample. Everything above is measured on fires that did happen at high age. The
grid establishes that age is not predictive of outcome; it does **not** establish that the blocked
1,228 would have earned the 30-45 s rate had they been let through. Those rows were blocked before a
side or a p was computed (`decide_now` returns at the `publish()` gate), so their intent is not
recoverable from the journal. Testing them needs a lane that logs the decision it would have made
with the bar off, which is a build change and V's call.

**No engine was touched. Read-only throughout.**
