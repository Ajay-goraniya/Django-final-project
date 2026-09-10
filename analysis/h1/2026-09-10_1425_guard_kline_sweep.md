# H1 — the decisive kline sweep V asked for: **NO against-lean penalty. Revert the guard.**

V's condition (NOTES_v12, 14:05): *"the same sweep on the 71-day 1-s kline set at t=20 s … If the
against-lean penalty at 20 bps is not there on 20k candles, the guard is reverted at once."*

**It is not there. It is reversed.** Against-lean fires are consistently *more* accurate, at every
threshold, in both halves, at every fire second. The guard blocks the better fires.

## The test

20,448 real 5-minute candles (Binance spot 1s klines, 71 days, 2026-07-01 → 09-09); **20,308** have
nine contiguous prior candles and settle non-flat. Lean = net open→close move of the 9 closed
candles before the fire's candle, in bps — the same definition I used on twin A. "Against-lean" =
the early direction at t=20 s opposes that lean, with |lean| ≥ X. Accuracy = does that early
direction match the settled open→close direction.

| X bps | against-lean n | acc | with-lean n | acc | **gap (pp)** | H1 gap | H2 gap |
|---|---|---|---|---|---|---|---|
| 5 | 7,393 | 60.4% | 7,147 | 57.5% | **+3.0** | +2.1 | +3.9 |
| 10 | 5,810 | 60.0% | 5,601 | 57.0% | **+3.0** | +1.9 | +4.2 |
| 15 | 4,616 | 60.0% | 4,325 | 56.5% | **+3.5** | +2.0 | +5.1 |
| **20 (shipped)** | **3,626** | **59.7%** | **3,371** | **56.2%** | **+3.5** | **+1.1** | **+6.0** |
| 25 | 2,896 | 59.8% | 2,621 | 55.7% | **+4.1** | +2.0 | +6.3 |
| 30 | 2,265 | 59.3% | 2,062 | 56.3% | **+3.0** | +1.5 | +4.6 |
| 40 | 1,461 | 59.9% | 1,268 | 56.5% | **+3.4** | +2.1 | +4.6 |

A negative gap would mean against-lean fires are worse and the guard is justified. **Every gap is
positive.** The premise is not weakly supported or sample-dependent — it is backwards, by 3-4
percentage points, on thousands of candles per cell, with both halves agreeing at every single
threshold.

## And it is not a t=20 s artefact

At |lean| ≥ 20 bps, across fire seconds:

| t | against n | acc | with n | acc | gap |
|---|---|---|---|---|---|
| 5 | 3,142 | 57.0% | 3,099 | 52.5% | **+4.6** |
| 10 | 3,428 | 57.6% | 3,227 | 53.4% | +4.2 |
| 20 | 3,626 | 59.7% | 3,371 | 56.2% | +3.5 |
| 40 | 3,787 | 62.8% | 3,395 | 59.9% | +2.8 |
| 60 | 3,848 | 65.6% | 3,406 | 63.1% | +2.5 |
| 120 | 3,826 | 73.2% | 3,480 | 71.2% | +2.0 |
| 190 | 3,891 | 80.0% | 3,430 | 79.7% | +0.3 |

Positive everywhere, strongest earliest — exactly where EF fires — and decaying to nothing by 190 s.

## What this means

After a sustained multi-candle move, an early counter-move inside the next candle is **more** likely
to carry to the close, not less. That is ordinary short-horizon mean reversion, and the guard is
built on the opposite assumption. The +49.6 the guard scored on twin A's 151 fires was a
25-fire slice of a statistic that runs the other way on 3,626.

**Per V's own stated condition: revert `trend_bps` to 0 now.** It is live on Tokyo with equity
around 17, already under the floor.

## The tempting follow-up, and why not yet

A +3.5pp accuracy edge suggests an *inverse* dial — prefer against-lean fires. **I am not proposing
that.** This is direction accuracy on raw candles, not PnL through quotes: against-lean entries are
counter-trend, so the book is likely to price them differently, and my Task 2(c) and Task 7 pass 2
results both showed accuracy improvements that destroyed PnL by removing cheap winners. The market
data cannot settle it; the fire data can. Worth a shadow twin, not a live dial.

## Caveats

Spot 1s klines rather than the venue's settlement; "early direction at t=20 s" is a proxy for EF's
model output, not the model itself, so this tests the *market premise* of the guard rather than the
engine's implementation of it. That is the right target here — the guard's premise is a claim about
the market, and the claim is false. Cells run 1,268-7,393; halves split at the median candle.
