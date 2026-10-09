# EF_BRAIN — can v10 EF be made to work? (owner, 09-22 22:1x)

Scripts: `r34_live_vs_paper.py` (A), `r35_ef_calibration.py` (B), `r36_ef_brain.py` (C).
All Polymarket, all graded on **`venues.outcome`** (the venue's own oracle), never `candles.actual`.
Fees are the **measured** live Polymarket fee — 1.67% of shares, charged on winners AND losers
(R-30b, `pnl − venue_pnl − venue_fees == 0` on every journal row) — not `per1()`'s 7%-of-winnings.

**I could not verify the "paper +0.22/$1 on 742 fills (Mumbai 8795, 09-16→22)" claim: that dataset
is not on the branch.** Newest `live_backup` is 09-17 12:45 and `venues.sqlite3.gz` is 09-16 18:23.
Everything below uses what is actually here.

---

## (A) Live vs paper — **it is none of the three. They are not trading the same candles.**

Overlap window 09-15 00:30 → 09-16 17:10 (the intersection, *not* paper's span — comparing live
against all of paper's 09-08→09-16 fires counts six days when live was not running and inflates
"missed fires" into a meaningless number).

In that window: **live fired 108, paper fired 182, only 74 shared.** Live took 34 paper never took.
**Live fires on 41% of the candles paper fires on.**

| | result |
|---|---|
| **fill price** | live mean ask **0.4238** vs paper **0.4258** — live paid *less*, median difference **exactly 0.0000**. **Not the cause.** |
| **signal (shared candles)** | same side **71/74 = 95.9%**. Live right 44.6%, paper right 48.6% — and that whole gap is **3 candles**. Exact McNemar **p = 0.250** on **3 discordant pairs**. Far under the 60 bar: **not a finding.** |
| **fire set** | 74 of 182. This is the real difference and it is not execution — the two are not the same rule. |

So the "+0.22 paper vs −45.87 live" comparison was never like-for-like. Live account, all 151
settled EF fires: gross **−39.84**, fees **20.80**, **net −55.36** on 519.55 staked = **−10.66% of stake**.

---

## (B) Calibration — **`p` is overconfident by ~7 points, everywhere.** This is the real defect.

1,108 graded fires on the venue oracle:

| ask bucket | n | mean p | realised | **gap** |
|---|---|---|---|---|
| 0.30–0.40 | 257 | 0.5227 | 0.4591 | **−0.0636** |
| 0.40–0.50 | 494 | 0.5795 | 0.5040 | **−0.0755** |
| 0.50–0.60 | 300 | 0.6718 | 0.6033 | **−0.0685** |
| **all** | 1108 | 0.5968 | 0.5262 | **−0.0706** |

All three buckets clear n≥60 and all three land within 1.2pp of each other. That is a **systematic
bias, not noise** — and it is almost exactly the size of the lane's own 0.06 margin. **The trade rule
`p >= ask + 0.06 + fee` is spending its entire safety margin on a calibration error.**

`p` is still marginally the better forecast than the raw ask (Brier 0.2469 vs 0.2497 overall; `p`
wins in all four rows) — consistent with R-13, where the edge over the book is real but thin.

---

## (C) The retrained brain — **it does not beat sorting by v10's own margin.**

Walk-forward by day (train days 1..k, read day k+1 only). Rule **fixed before any result**:
`ask ≤ 0.60 and p ≥ ask + 0.06 + 0.0167`. Never swept.

Calibration is genuinely fixed — but the money is not:

| arm | mean p | realised | gap | n | W% | per $1 | total | maxDD |
|---|---|---|---|---|---|---|---|---|
| v10 EF as shipped | 0.5971 | 0.5238 | −0.0733 | 907 | 52.0% | +0.1532 | **+138.99** | 17.54 |
| Platt-recalibrated | 0.5268 | 0.5238 | **−0.0031** | 349 | 57.0% | +0.2613 | +91.20 | **9.46** |
| fresh 30-feature fit | 0.5298 | 0.5238 | −0.0060 | 452 | 50.9% | +0.1923 | +86.94 | 17.20 |

**The paired gate returned ZERO discordant pairs.** That is not a pass — it means every retrained arm
is a strict **subset** of v10's fires and **never changes a single side**. These are not brains, they
are threshold shifts. So the R-19 null decides it:

| arm | n | per $1 | total | maxDD |
|---|---|---|---|---|
| Platt-recalibrated | 349 | +0.2613 | +91.20 | 9.46 |
| **null: top-349 by v10's own margin (p − ask)** | 349 | **+0.2849** | **+99.44** | 12.77 |
| null: 349 cheapest asks | 349 | +0.2477 | +86.43 | 9.24 |
| fresh 30-feature fit | 452 | +0.1923 | +86.94 | 17.20 |
| **null: top-452 by margin** | 452 | **+0.2496** | **+112.81** | 12.77 |

**Both retrains lose to the trivial null.** Sorting v10's existing fires by its own `p − ask` beats
the recalibrated brain and crushes the fresh fit. Nothing was learned that v10's score did not
already contain.

---

## What this says about the owner's order

*"remove the drawdowns first and make it profitable."* On paper, firing less does cut drawdown —
**17.54 → 9.46** — and raises per-$1 from +0.153 to +0.261. **But total money falls, +139 → +91.**
That is the R-19 signature again: fewer, cheaper fires, not a better call. And the drawdown
reduction is bought with profit, which is the trade the owner should be the one to make.

**What I am not willing to claim:** that any of this makes EF profitable *live*. Every number in
(B) and (C) is paper at the quoted ask with zero slippage — an upper bound — and (A) shows live has
only ever taken 41% of those candles. Live is −10.66% of stake.

**The one non-gate, non-fitted change these numbers support** is fixing the calibration itself:
`p` is overconfident by a near-constant 7pp across all buckets, so the lane fires on trades that do
not clear the bar it thinks they clear. Correcting that is honest arithmetic, not a threshold pick.
It did **not** make more money here — but it is the only change that makes the score mean what it says.

## Limits, stated

1. Every row is a candle **v10 EF already chose to fire on**. A retrain on that set can re-rank or
   drop v10's own fires; it cannot find fires v10 never took.
2. The Mumbai 8795 set (742 fills, 09-16→22) is not on the branch — its +0.22 is unverified here.
3. Live n=151 settled EF fires; the shared-candle comparison rests on 74, with 3 discordant pairs.
4. `venues.q` ends 09-16 17:25, which caps every venue-graded number above.

---

# (D) The pooled Platt pair for the engine's `_calibrate` hook (V, 09-22 22:3x)

`r37_pooled_platt.py`. `p' = sigmoid(a·logit(p) + b)`, clamped to never exceed `p`. Rule unchanged
and still fixed before the test: `ask ≤ 0.60 and p' ≥ ask + 0.06 + 0.0167`.

## (1) The pair

**Pooled fit on all 1,108 venue-graded fires: `a = 1.0677`, `b = −0.3208`.**
In-sample it closes the bias exactly: mean p 0.5968 → p' 0.5262, realised 0.5262, gap −0.0706 → **0.0000**.

Note `a ≈ 1.07`, not < 1 — **the defect is a near-constant logit SHIFT (b), not a slope problem.**
That is consistent with (B), where the gap was ~7pp in all three ask buckets.

Fitting on all 1,108 and then reading those same days is in-sample, so the honest number is
**leave-one-day-out**: refit without day *d*, read on *d*.

| day | n | a | b | gap raw p | **gap p′** | per$1 p′ |
|---|---|---|---|---|---|---|
| 09-08 | 46 | 1.0101 | −0.3159 | +0.0285 | +0.1030 | +0.1451 |
| 09-09 | 136 | 0.9823 | −0.2791 | −0.0853 | −0.0166 | +0.2774 |
| 09-10 | 159 | 1.0389 | −0.3055 | −0.0771 | −0.0069 | +0.3083 |
| 09-11 | 170 | 1.0102 | −0.2569 | −0.1254 | −0.0658 | +0.1110 |
| 09-12 | 148 | 1.1186 | −0.3469 | −0.0612 | +0.0115 | +0.3559 |
| 09-13 | 117 | 1.1254 | −0.3520 | −0.0537 | +0.0202 | +0.4272 |
| 09-14 | 146 | 1.1177 | −0.3716 | −0.0207 | +0.0575 | +0.4920 |
| 09-15 | 93 | 1.1360 | −0.3737 | +0.0004 | +0.0760 | +0.0872 |
| 09-16 | 93 | 1.0280 | −0.2670 | −0.1721 | **−0.1107** | −0.0235 |

Raw gap spans −0.172 … +0.029; calibrated spans −0.111 … +0.103. **Better centred, not cured** —
09-16 is still 11pp overconfident even after calibration.

Per ask bucket (pooled vs leave-one-day-out — they agree to 3 decimals, so the pair is not
bucket-specific overfitting):

| ask | n | gap raw p | gap p′ pooled | gap p′ LOO |
|---|---|---|---|---|
| 0.30–0.40 | 257 | −0.0636 | +0.0146 | +0.0133 |
| 0.40–0.50 | 494 | −0.0755 | −0.0021 | −0.0024 |
| 0.50–0.60 | 300 | −0.0685 | −0.0063 | −0.0066 |

## (2) The rule with the pooled pair

| arm | n | W% | per $1 | total | **maxDD** |
|---|---|---|---|---|---|
| v10 EF, raw p | 1084 | 52.2% | +0.1529 | **+165.72** | 17.54 |
| pooled a,b (**in-sample**) | 390 | 56.4% | +0.3024 | +117.93 | **9.06** |
| **pooled a,b (leave-one-day-out)** | 406 | 53.7% | **+0.2313** | **+93.92** | **11.08** |
| null: top-n by raw `p − ask` | 390 | 54.1% | **+0.2739** | **+106.82** | 14.06 |

**The honest (LOO) pair still loses to the null on money** — +0.2313 vs +0.2739 per $1, +93.92 vs
+106.82 total. Only the in-sample row beats it, and that row is the flattery. Same verdict as the
daily refit in (C).

**But it wins on what the owner asked for.** Drawdown: **17.54 → 11.08**, lower than the null's
14.06 and lower than every other arm except the in-sample one. If the objective is "cut the
drawdown", the calibrated pair does that better per dollar of profit surrendered than the null does.

Day by day with the pooled pair (rain or sun) — **positive every day, 9/9**:
+0.190, +0.281, +0.327, +0.205, +0.464, +0.426, +0.461, +0.212, +0.141. Five of nine days are under
60 fires and marked insufficient; the four readable days are +0.327, +0.205, +0.461, +0.281.

## (3) Refit cadence — **do not refit daily; the day-to-day wobble is noise, not drift**

| fit on | a range | a sd | b sd |
|---|---|---|---|
| single day (n=93–170) | 0.258 … 1.310 | **0.3785** | 0.3224 |
| ~960 rows (leave-one-day-out) | 0.982 … 1.136 | **0.0570** | 0.0421 |

Single-day estimates scatter **6.6× (a) and 7.7× (b)** wider than estimates from ~960 rows. If the
pair genuinely drifted day to day, the large-sample estimates would move too; they do not. So the
per-day spread is sampling noise, and **a daily refit would inject that noise straight into the
trade rule.**

**Recommendation: refit on a rolling window of ≥1,000 graded fires (~1 week at the current rate),
not daily.** On this data a fixed pair costs little — LOO (a pair that never saw the day it reads)
gives +0.2313 against +0.3024 in-sample, and the LOO pairs sit in a 0.98–1.14 / −0.37…−0.26 band.

## Two things I will not let this section imply

1. **It is still paper.** Quoted ask, zero slippage, upper bound. Live has only ever taken 41% of
   these candles (section A), and live is −10.66% of stake.
2. **It does not beat the trivial null on money.** It beats it on drawdown. Those are different
   objectives and the choice between them is the owner's, not mine.
