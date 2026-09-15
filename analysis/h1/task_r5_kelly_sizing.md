# Task R-5 — dynamic staking as a trained model. **DOES NOT SHIP.**

V, 09-15 02:2x, standing task: re-run at every +100 graded live fires, one line per run in
`analysis/h1/r5_ledger.md`, report only on a change of verdict.
Script `analysis/h1/task_r5_kelly_sizing.py`.

**Verdict: does not ship. Stake stays fixed 3.0.**

> **Run 1b supersedes run 1.** Run 1 used `v10_poly_long4` (777 trades). `poly_pnl` turns out to be
> a **superset** — all 777 of v10's rows are in it by (epoch, ts) — running 125 trades fresher, to
> 2026-09-15 00:41. Adding it and the accuracy-mode lane `poly_acc` takes the sample from 1,543 to
> **1,872**, and **the verdict gets stronger, not weaker**: the per-$1 delta that read **+0.073** on
> the stale subset reads **−0.008** on the full one. Same lesson as the 09-12 weekend cell — a
> number that looked mildly positive was a small-sample artifact. Run 1's figures are kept in the
> ledger rather than deleted.

## Build

Walk-forward ridge on per-$1 PnL from inputs known at fire time (`p`, `ev`, `ask`, `sec`, `rv60`,
lane), fit on the **first half by time**, used to size the **second half**. Sizing = fractional
Kelly (0.25) on the predicted edge, capped at 3× the fixed stake. Polymarket lanes graded on
`venues.outcome`; provenance 0 disagreements against each lane's own recorded `actual`.
**1,872 paper trades** (poly_pnl + poly_acc 1,106 + v12 766). `poly_acc` is the accuracy-mode lane
and carries its own lane flag — never pooled blind with a different decision rule.

All three lanes are **paper at the quoted ask**: recorded PnL matches the quoted-ask payout to
**0.0000 on all 929** poly_pnl rows. Upper bound, never a live number.

## V's ship condition: same trades, more money

| | staked | total PnL | per $1 |
|---|---|---|---|
| fixed-3 | 2,727 | **+505.53** | +0.185 |
| Kelly (capped) | 141 | **+25.08** | +0.177 |

**No.** Behind by **−480.44**, staking 5% of the capital — and on the fuller sample it no longer
even wins on per-$1 (−0.008). Trades better/worse: **405 / 504.**

## The steelman: same total capital, let it lever up

Rescaled ×19.3 so both books stake 2,727: **normalised Kelly +483.98 vs fixed-3 +505.53 — Kelly
LOSES by −21.54.** On run 1's stale subset this was the one comparison Kelly won (+168); on the
full sample it loses too. And it would still cost:

- **365 of 936 trades at a zero stake** — a **gate on 39% of the book**, the exact shape the
  standing rule bans.
- Max single stake **$31 vs $3**; largest single-trade loss **−$26 vs −$3**; median stake **$1.17**.

## The ablation

| model | per-$1 delta vs flat |
|---|---|
| all features | −0.008 |
| **`ask` removed** | **−0.138** |

Standardised weights: `p` +0.361, **`ask` −0.300**, `ev` −0.061, `rv60` −0.053, `sec` +0.017. What
little the model has is the ask coefficient — R-4's result re-learned, cheap quotes pay more per $1,
a price effect and not an accuracy one, carrying R-4's quote-age failure unchanged.

Per lane: poly_pnl + poly_acc alone **−0.060** (`ask` weight only −0.039 — it barely finds anything
there); v12 alone +0.118 with an `ask` weight of **−0.900**, the largest in the study. The apparent
edge lives entirely in the one lane where the model leans hardest on price.

## Verification, second half only

| check | result |
|---|---|
| sample size | PASS — n=936 |
| **both halves** | **FAIL** — −0.146 / +0.111, sign flips |
| **beats the null** | **FAIL** — +0.177 vs +0.185 fixed-3 |
| **quote age** | **FAIL** — ffill, max 10.0 s, unchanged from R-4 |
| **paired test** | **FAIL** — no discordant pairs |

**VERDICT: NOT A FINDING**, now failing four checks where run 1 failed two.

On `paired()`: sizing never changes *which* trades are right — both rules take the same trades and
differ only in how much — so there are no discordant pairs and the test carries no information
here. Reported failing for that reason, not because the rules tie. The informative paired statistic
is the per-trade PnL difference: 405 better / 504 worse.

## Live fills: still zero scored, and the reason is narrower than run 1 said

**Correction to run 1's wording.** V is right that the v12 journals record `p`, `ev` and `rv60` —
this task reads exactly those for the paper set, so "the live journal records nothing" was wrong.

The accurate blocker: **the only live-fill rows H1 can reach are `analysis/h1/r3_submissions.csv`**,
a 14-column CSV the AWS box sent by chat, which carries no `p`, no EV and no `rv60`. The Zurich
live journal that would carry them **is not on the branch** — 18 snapshots in `learner/live_backup`,
none named zurich, and no table named `signals` or `diagnostics` in any of them. **One pushed
snapshot unblocks pass 2; nothing else does.**

## What would change the verdict

1. A pushed Zurich journal snapshot, so the model is scored on **real fills** rather than quotes.
   R-3 measured the gap: **+0.004 per $1 actually paid vs +0.038 at the quote.**
2. 100+ graded live fires per re-run, per the standing schedule.
3. An ablation where the edge survives removing `ask`. Until then this is R-4's artifact with a
   regression on top.

**Until it passes: stake stays fixed 3.0.**

---

# Pass 2 amendment (V, 09-15 02:2x) — calibration and shrunk Kelly

## (1) Reliability of `p` — is the number we would size on even calibrated?

PAPER, 1,872 graded fires, model `p` vs outcome. Every bin is over the 60 bar and readable:

| bin | n | mean `p` | observed | gap |
|---|---|---|---|---|
| 0.50–0.55 | 606 | 0.525 | 0.474 | **−0.051** |
| 0.55–0.60 | 328 | 0.582 | 0.543 | **−0.039** |
| 0.60–0.65 | 335 | 0.624 | 0.522 | **−0.102** |
| 0.65–0.70 | 266 | 0.679 | 0.560 | **−0.119** |
| 0.70–1.01 | 310 | 0.793 | 0.742 | **−0.051** |

**The model is overconfident in all five bins, with no exception and no sign change.** The
0.65–0.70 bin promises 67.9% and delivers 56.0%. The 0.60–0.65 bin promises 62.4% and delivers
52.2% — barely a coin.

**Brier: model 0.2435, venue's own price 0.2463.** The forecast we would size on beats the price
already on the screen by **0.0028** — 1.1% relative. That is the whole informational advantage,
before any cost.

LIVE, 78 graded fills: the model curve **cannot be drawn** — `r3_submissions.csv` carries no `p`.
The venue price is shown instead, binned over its own range (live asks run 0.24–0.58; the paper
bins start at 0.50 and would have silently dropped most of the set):

| bin | n | mean price | observed | gap |
|---|---|---|---|---|
| 0.20–0.35 | 2 | 0.285 | 0.000 | −0.285 |
| 0.35–0.42 | 16 | 0.391 | 0.562 | +0.171 |
| 0.42–0.47 | 22 | 0.438 | 0.318 | −0.120 |
| 0.47–0.52 | 16 | 0.494 | 0.562 | +0.069 |
| 0.52–1.01 | 22 | 0.546 | 0.591 | +0.045 |

**Every live cell is INSUFFICIENT (n = 2–22) and none is read.** Brier of the live venue price:
0.2450, n=78 — reported alone, since there is no model column to compare it against on live rows.

## (2) Shrunk Kelly from the measured `p` error

After Baker & McHale (2013), *Optimal Betting Under Parameter Uncertainty: Improving the Kelly
Criterion*, Decision Analysis 10(3):189–199 — the Kelly stake should be shrunk when the win
probability is an estimate, because substituting sample estimates for population parameters makes
out-of-sample performance worse than in-sample.

**What I implemented, stated plainly:** the paper's *principle* with a shrinkage **measured from
this data** — the calibration slope of the outcome on (`p` − 0.5), fitted on the **training half
only** and applied forward. I did not reproduce their closed form; I have not read the paper
itself and will not transcribe a formula from an abstract. The measured slope is the quantity the
shrinkage is meant to estimate, and unlike a copied constant it is checkable against the data here.

- calibration slope, **training half: 0.699**
- same slope on the test half (not used to size, shown for honesty): **0.474**

The slope falls out of sample — which is precisely the effect the paper is about, visible in our
own numbers.

| book | staked | total PnL | per $1 |
|---|---|---|---|
| fixed 0.25 Kelly (run 1b) | 141.3 | +25.08 | +0.177 |
| **shrunk Kelly, k=0.699** | 395.4 | **+70.17** | +0.177 |
| fixed-3 flat | 2,727.0 | **+505.53** | +0.185 |

**Ship test (unchanged): both LOSE.** Shrinking the fraction from 0.25 to a measured 0.699 puts
2.8× more capital to work and earns 2.8× more, leaving per-$1 unchanged at +0.177 — still below
flat's +0.185, and still −435 behind on total PnL.

## Pass 2 verdict

**Unchanged: does not ship. Stake stays fixed 3.0.**

Pass 2 adds the *reason*, which passes 1 and 1b could only infer. Sizing on `p` fails not because
the Kelly fraction was mistuned — tuning it by the measured error changes nothing — but because
**`p` is overconfident in every bin and carries 0.0028 of Brier over the venue's own price.**
There is no calibrated edge for a stake curve to amplify.

The live half of both requests is still unanswerable at n=78 with no `p` column. Unchanged blocker:
**one pushed Zurich journal snapshot.**
