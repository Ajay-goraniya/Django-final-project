# H1 — kline premise test for the EF ask floor

**The premise is confirmed, and far more cleanly than the trend guard's ever was: monotone across the
whole range, in both halves, at three fire seconds, on tens of thousands of candles. But confirming
the premise is not the same as confirming the dial — the test measures accuracy, and you pay for
accuracy in the ask.**

## What is actually testable

The ask is not in kline data. Its market proxy at the fire second is **|distance from open|**: a high
ask means price has already moved decisively and the book is confident. So the premise underneath the
floor is *"when price has moved further by the fire second, the early direction holds to the close
more often"* — and that is testable on 72,331 graded candles.

## Accuracy by distance quintile

| t=20 s quintile | n | acc | H1 | H2 |
|---|---|---|---|---|
| 0.0-0.2 bps | 14,464 | **51.0%** | 51.0% | 51.0% |
| 0.2-1.0 | 14,463 | 54.1% | 53.6% | 54.5% |
| 1.0-2.0 | 14,463 | 57.2% | 56.2% | 58.3% |
| 2.0-3.8 | 14,463 | 61.8% | 61.2% | 62.4% |
| **>3.8 bps** | 14,464 | **67.5%** | 66.4% | 69.2% |

| t=60 s quintile | n | acc | H1 | H2 |
|---|---|---|---|---|
| 0.0-0.8 bps | 14,466 | 53.5% | 53.6% | 53.5% |
| 0.8-1.9 | 14,466 | 58.0% | 57.1% | 58.7% |
| 1.9-3.4 | 14,466 | 63.4% | 61.8% | 64.9% |
| 3.4-6.2 | 14,466 | 69.7% | 67.9% | 71.5% |
| **>6.2 bps** | 14,467 | **77.6%** | 76.5% | 79.1% |

**Perfectly monotone at t=20, t=30 and t=60, and monotone within each half separately.** A candle
that has barely moved by the fire second is a coin flip (51.0%); one that has moved decisively is
67.5% at t=20 and 77.6% at t=60.

## Threshold sweep — no spike anywhere

Keep only fires where |dist| ≥ X bps at t=20 s (baseline 72,317 fires, 58.3%):

| X bps | kept | acc | **gap** | H1 | H2 | removed | removed acc |
|---|---|---|---|---|---|---|---|
| 0.5 | 52,413 | 60.9% | +2.5 | 60.4% | 61.3% | 19,904 | 51.7% |
| 1.0 | 43,501 | 62.2% | +3.8 | 61.5% | 62.9% | 28,816 | 52.5% |
| 1.5 | 35,669 | 63.5% | +5.2 | 62.9% | 64.2% | 36,648 | 53.3% |
| 2.0 | 28,964 | 64.6% | +6.3 | 63.9% | 65.5% | 43,353 | 54.1% |
| 3.0 | 19,406 | 66.3% | +8.0 | 65.3% | 67.7% | 52,911 | 55.4% |
| 4.0 | 13,412 | 67.9% | +9.5 | 66.9% | 69.3% | 58,905 | 56.2% |
| 6.0 | 6,668 | 69.6% | **+11.2** | 68.7% | 71.0% | 65,649 | 57.2% |

**Monotone increasing across the entire range**, both halves, and the removed group's accuracy rises
smoothly as the threshold rises (51.7% → 57.2%) exactly as it should. This is the opposite signature
to the trend guard, which spiked at one value and inverted below it. On premise alone, this is the
best-supported thing either of us has looked at today.

## The caveat that matters, and it is not small

**This measures accuracy, not PnL, and the ask rises with confidence.** Every time today an accuracy
improvement has met a real book, it has cost money — the on/off gate, the stake modifier, and my own
Task 2(c) result all removed cheap winners and lost PnL doing it. A high-ask fire is right more often
*and* pays more for the privilege; whether the first outweighs the second is a question only the fire
data can settle, and there the evidence was 4 of 5 sets improving with one contradicting.

So: **premise confirmed, dial still unproven.** Those are different claims and the ledger should
carry them separately. What this does establish is that the floor is not fitted to noise — there is a
real, large, monotone market regularity underneath it. That removes the main reason for suspicion,
without supplying proof of profit.

On V's honest counter-note (last 3 h, 11 sub-0.48 fills at +1.20): 11 fires against an 18-hour record
of 51 fills at −9.60 with both halves negative. It does not overturn anything, and the post-deploy
paired test against twin C remains the right adjudicator.

## Caveats

|distance from open| is a proxy for the ask, not the ask — the mapping is monotone but noisy, and a
wide spread or a stale book breaks it. Spot 1s klines rather than Predict.fun settlement. Accuracy
only; no fee, spread or fill model. Quintiles are ~14,400 candles each; sweep cells 6,668 to 52,413.
