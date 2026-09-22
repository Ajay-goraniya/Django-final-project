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
