# Task 21 — venue settlement disagreement, and whether the 1.5c gap is a crossing prior
H1, 2026-09-11 13:40 UTC. Asked by V in `REQUEST.md` 12:55. Two numbers, no sweep, as requested.

Data: `learner/live_backup/` snapshot at 13:19 UTC — `venues.sqlite3` (`outcome` = Polymarket's
resolution; `q` = 5-s book), `build11/predict_pnl/twin_c_thr1.sqlite3` (`candles` = Predict.fun's
settling source), `poly_pnl.sqlite3` (Polymarket paper), `tokyo_orders.json` (479 real orders, 427
filled). Grading is `candles.actual` throughout. Cross-check: `candles.actual` and Tokyo's
`financial_result` agree on **383 of 383** shared candles, so the settling label is not in doubt.

---

## 21a — both numbers are right. Mine is the population, V's is the fired subset.

| set | n | disagree | rate |
|---|---|---|---|
| **full overlap** | 803 | 90 | **11.21% ± 1.11** |
| candles the Polymarket paper FIRED on | 426 | 59 | **13.85% ± 1.67** |
| candles it did not fire on | 377 | 31 | 8.22% ± 1.41 |

V's 31/218 = 14.2% is the middle row measured on a shorter window: on the current snapshot the same
subset reads 13.85%. The 10.4% on record is the first row measured on a smaller window (n=627); it
is now 11.21% on n=803. **Both numbers are correct for what they measure and they are not in
conflict** — 11.2% is the rate over all candles, 13.9% is the rate over the candles the paper trades.

**It is not a keying bug.** A one-candle misalignment does not look like this:

| keying | disagreement |
|---|---|
| aligned (`candle_id//1000` == `candle_epoch`) | 11.2% |
| shifted −600 / −300 / +300 / +600 s | 48.8% / 45.1% / 48.1% / 49.8% |

A misalignment reads as a coin flip. Also: every epoch in both tables is a multiple of 300, the three
engine DBs produce **0** conflicting labels where they overlap, and `poly_pnl.candle_epoch` lines up
with `candle_id//1000` with no offset. The keying is fine.

**What actually drives it — the venues can only disagree when the move is near zero:**

| candle move (bps, quartiles of the full overlap) | n | disagreement |
|---|---|---|
| 0.0 – 2.3 | 201 | **29.9%** |
| 2.3 – 5.2 | 200 | 12.5% |
| 5.2 – 9.4 | 201 | 1.0% |
| 9.4 – 62.9 | 201 | 1.5% |

Predict.fun settles on Binance close ≥ open; Polymarket on its own Chainlink TWAP. On a 10 bps candle
both oracles see the same direction. On a 1 bps candle they are reading noise, and they split almost
a third of the time. The paper fires more often on small-move candles (median 4.5 bps vs 5.2 bps over
all candles), so its subset inherits the higher rate. Both halves of the window agree on the ordering
(fired 12.1% vs not-fired 9.4% in the first half; 15.4% vs 6.9% in the second), and the gap is about
2.6 standard errors — selection, not noise.

**Consequence for the record:** the standing "~10% cross-venue disagreement" understates the risk of
grading with the wrong venue, because a *fired* subset is selected toward exactly the candles where
the two oracles disagree. Use **13.9%** when reasoning about traded candles, 11.2% for population
statements. `verify.py`'s `grading()` check already fails on any mismatch at all, so nothing on the
branch depends on which of the two you quote.

---

## 21b — No. The number you want is not 1.5c, it is 0.5c ± 0.1c, and the 1.5c is mostly not crossing.

Matching live fills to the paper on candle AND side reproduces your gap, then splits it:

| EF, n=120 matched | value |
|---|---|
| live fill | 0.5008 |
| the quote **Tokyo itself saw** at the order (book age median 151 ms) | 0.4982 |
| paper quote | 0.4890 |
| **total gap, fill − paper** | **+1.18c ± 0.81c** |
| ├ crossing: fill − Tokyo's own fresh quote | **+0.26c ± 0.18c** |
| └ quote difference: Tokyo's quote − paper's quote | +0.92c ± 0.82c |

The total is 1.5 standard errors from zero — on its own it is not distinguishable from no gap at all.
And the part of it that is genuinely an *execution* cost, the only part that could transfer to another
venue's book, is the first row.

Measured on the full live-fill set rather than the matched subset:

| | n | fill − quote |
|---|---|---|
| **EF** | **380** | **+0.46c ± 0.09c** (first half +0.46c, second half +0.47c) |
| REVERSAL | 47 | −1.21c ± 0.36c (favourable) |
| all fills | 427 | +0.28c ± 0.10c |

`verify.py` passes this one: grading provenance, quote age (same-instant — the order carries its own
book age), sample size, both halves. **Crossing on Predict.fun costs about half a cent per $1 of
entry price, and it is stable across both halves of the sample.**

**Why the 1.5c is the wrong quantity.** Run the same decomposition on REVERSAL and its "gap" is
**+15.4c**. Nobody would call that a crossing cost. It is the same thing the EF number is, only
larger: the paper and the live engine are quoting the same market at different moments, and REVERSAL
fires late, when the price has moved most. A live-minus-paper price difference measures *quote
timing between two feeds*, not what it costs to cross a book. The two only look alike because on EF
the number happens to be small.

**So: do not use 1.5c as the Polymarket prior.** If you want a crossing prior, the defensible one is
**+0.5c ± 0.1c**, with these limits:
- it is measured at $1–$4 stakes, where the top of book almost always covers the order — which is
  why it is near zero. It says nothing about larger size, on either venue.
- it is Predict.fun's book. Polymarket's top-of-book depth is a different number and I have not
  measured it. On stake this small I would expect the same order of magnitude, not 3× larger.
- Polymarket's fee (`shares × rate × p × (1−p)`, makers free) is a separate cost and already in the
  paper's PnL model; do not double-count it as crossing.

On that prior, the Polymarket paper's +0.187/$1 goes to roughly **+0.18, not +0.10**.

### But that is not the number that should decide the go/no-go — this is

**The Polymarket paper's own ask does not come from the exact second it logs.** Only **23 of 427**
paper asks equal the 5-s collector's `poly_up`/`poly_dn` value at the same second. The paper is
therefore reading a quote from *some other moment*, and I cannot certify which from the committed
snapshots — the trades table has no `book_age_ms` column, unlike `tokyo_orders.json`, which is how
the Predict.fun number above could be checked at all.

That is the same exposure that turned my 11.2 replay's +0.27/fire into ~0.00 (Task 20): a quote-age
error is unbiased on average, but the EV filter selects the randomly cheap side of it. **+0.187 is
not yet an honest number, and a crossing haircut applied to it does not make it one.**

**Unblocking it is one column, on your side:** log `book_age_ms` (or the quote's own timestamp) on
each Polymarket paper trade, the way `tokyo_orders.json` already does. `poly1s.py` has been logging
at 1 Hz since 06:03 UTC, so the freshness may well already be good — it just cannot be demonstrated
from what is committed. Once that column exists I can re-run +0.187 under the at-or-after rule and
give you a number that survives `verify.py`'s `quote_age()`.

### Status
- 21a **DONE** — 11.21% ± 1.11 population, 13.85% ± 1.67 on fired candles; keying ruled out.
- 21b **DONE, answer is no** — use +0.5c ± 0.1c if you need a crossing prior; the go/no-go is blocked
  on the Polymarket paper's quote age, not on crossing cost.
