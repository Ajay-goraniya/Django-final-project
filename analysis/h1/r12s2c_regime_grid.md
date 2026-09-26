# R-12 step 2 (c) — the stage-1 per-regime OOS grid, era × vol × trend

V's outstanding item (`learner/REQUEST.md`, reduced at 00:1x to *"deliver only the per-regime OOS
grid (cheap)"*) — *"the 'all regimes' deliverable the user asked for, whatever ships."*
Script `analysis/h1/r12s2c_regime_grid.py`, full output `/tmp/claude-0/r12s2c_full.log`.

**4,030,620 out-of-sample rows**, test years 2019–2026, stage-1 logistic on the 18 BUILT features
(no venue input), walk-forward by year — train on every year strictly before Y, predict Y.

Cuts fixed before any result was read, and **without touching test data**: vol at rv60 0.35/0.75;
trend terciles from **years < 2019 only** (ret60 −1.7929 / 1.9124); era is a reporting axis only,
never a model input (a calendar feature is out of range in every test fold by construction).

## The grid looks strong

| vol | n | hit% | logloss | | trend | n | hit% | logloss |
|---|---|---|---|---|---|---|---|---|
| rv<0.35 | 1,112,443 | 70.46% | 0.5758 | | down | 1,332,449 | 74.45% | 0.5238 |
| rv0.35–0.75 | 1,243,354 | 72.03% | 0.5475 | | flat | 1,401,704 | 67.96% | 0.5933 |
| rv>0.75 | 1,674,823 | 73.62% | 0.5247 | | up | 1,296,467 | 74.64% | 0.5172 |

Era is remarkably flat — 70.52% (2026) to 73.30% (2021), logloss 0.5316–0.5609. All 72 era×vol×trend
cells are readable (smallest 605) and **not one is below 50%**, range 0.652 (2019 rv0.35-0.75/flat)
to 0.770 (2023 rv>0.75/up). Read on its own, that is a model that works in every regime and era.

## Then the obvious null kills it

Most of that 72% is **the clock**, not skill: by second 210 a candle already up 30 bps is nearly
decided. So the only number worth reading is model *minus* the dumb rule "the candle is up so far"
(`move_bps ≥ 0`), on exactly the same cells.

**Overall: model 0.7225, null 0.7278, delta −0.0053.** The model is *worse* than the dumb rule.

Per cell (model − null), every cell, never the best one:

| year | <0.35/down | <0.35/flat | <0.35/up | .35-.75/down | .35-.75/flat | .35-.75/up | >0.75/down | >0.75/flat | >0.75/up |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | +0.0064 | −0.0180 | +0.0083 | −0.0045 | −0.0181 | −0.0109 | −0.0050 | −0.0238 | −0.0069 |
| 2020 | +0.0000 | −0.0074 | −0.0049 | −0.0006 | −0.0026 | −0.0047 | +0.0018 | +0.0002 | −0.0017 |
| 2021 | −0.0017 | −0.0124 | +0.0004 | −0.0002 | −0.0029 | −0.0039 | −0.0001 | +0.0031 | −0.0005 |
| 2022 | −0.0041 | −0.0143 | −0.0104 | −0.0037 | −0.0075 | −0.0043 | −0.0018 | +0.0003 | −0.0003 |
| 2023 | −0.0049 | −0.0110 | −0.0072 | −0.0025 | −0.0070 | −0.0034 | +0.0029 | +0.0048 | +0.0016 |
| 2024 | −0.0069 | −0.0094 | −0.0064 | −0.0036 | −0.0059 | −0.0047 | −0.0022 | −0.0057 | −0.0012 |
| 2025 | −0.0061 | −0.0120 | −0.0084 | −0.0029 | −0.0080 | −0.0044 | +0.0001 | −0.0074 | −0.0011 |
| 2026 | −0.0052 | −0.0094 | −0.0082 | −0.0025 | −0.0082 | −0.0042 | −0.0022 | −0.0049 | −0.0009 |

**The model fails to beat the dumb rule in 61 of 72 cells.** The eleven it wins are scattered, tiny
and mostly the smallest cells in the table (the two largest positives are 2019 rv<0.35/up at n=605
and rv<0.35/down at n=623) — that is the shape of noise, not of a regime where the model works. The
losses are systematic: **every `flat` column is negative in almost every era**, which is where the
momentum rule has least to say and where a real model should win if it had anything.

## What this closes

**R-12 step 2 (c) is answered, on the largest sample this task has: the 109-month history model
carries no regime-specific direction edge. Not in any era, any volatility bucket, or any trend
bucket.** That is the honest version of the answer V asked for ("if GBM does not beat logistic across
years, say so: regimes carry no extra 5-min direction info and that closes the question honestly") —
and here it is stronger than that, because stage 1 does not even beat *momentum*.

One thing it is **not**: a claim the model is worthless. Its logloss is genuinely better than the
null's would be, because the null is a hard 0/1 call and the model is calibrated. **Calibration is
what it has; direction is what it does not have.** That is exactly R-13's shape — the direction call
is not where any edge lives — now confirmed on 4.03M rows across eight years instead of five days.

## Standing-rule note

The `flat` bucket being uniformly the worst is **not** a licence for a trend filter. No gates, no
stake modifiers, no thresholds bolted onto a weak score — and a bucket that is weak for the *null* as
much as for the model is not a regime discovery at all.
