# Task R-10 — the model's own ACCURACY mode, replayed

V, 09-15 20:3x: the user wants a safer / less dangerous mode.
Script `analysis/h1/task_r10_accuracy_mode.py`.

**The accuracy claim in the model file is TRUE — 86.4% against a claimed 87.6%. And it is worth
almost exactly nothing: +$0.31 across the whole sample, against +$123.13 for the rule running
today.** This is the project's own "accuracy is not PnL" rule, in numbers.

32,062 evaluated ticks, 1,693 candles, 8 days, graded on `venues.outcome`, same cost model, same
one-fire-per-candle rule. Paper at the quoted ask, so per-$1 is an upper bound; **accuracy is not —
a hit rate does not depend on fill price.**

## The three rules side by side

| rule | fires/day | fires | hit% | per $1 | total | positive days |
|---|---|---|---|---|---|---|
| pnl rule (running today) | 134.3 | 940 | 52.9% | **+0.131** | **+123.13** | **6/7** |
| accuracy 0.85 / 0.02 | 50.6 | 354 | **86.4%** | +0.001 | **+0.31** | 4/7 |
| accuracy `regime_floors` | 49.1 | 344 | 74.1% | −0.040 | **−13.74** | **2/7** |

The model file's own `oos_8day` block claims 81.8 trades/day, 87.6% accuracy, 8/8 positive days,
$263 over 8 days. **The accuracy half of that claim reproduces (86.4 vs 87.6).** The money half does
not survive the move to Polymarket pricing.

**Note the third row.** `regime_floors` is the *configured default* for accuracy mode, and it is the
worst of the three on this data: lower accuracy than the fixed floors, negative per-$1, and only
2 of 7 days positive. If accuracy mode is ever switched on, the shipped defaults are the variant to
avoid.

## The whole grid — the trade-off the user asked to see

Hit rate, conf_floor × ev_floor (`!` = n < 60, insufficient, not read):

| | ev ≥ 0.02 | ev ≥ 0.05 | ev ≥ 0.08 |
|---|---|---|---|
| p ≥ 0.70 | 840 / 71.3% | 596 / 70.3% | 385 / 70.1% |
| p ≥ 0.75 | 570 / 77.9% | 330 / 72.1% | 202 / 73.8% |
| p ≥ 0.80 | 461 / 82.0% | 210 / 75.2% | 126 / 75.4% |
| p ≥ 0.85 | 354 / 86.4% | 123 / 79.7% | 65 / 73.8% |
| p ≥ 0.90 | 241 / 89.2% | 63 / 77.8% | 28 / 82.1% `!` |

Per $1, same grid:

| | ev ≥ 0.02 | ev ≥ 0.05 | ev ≥ 0.08 |
|---|---|---|---|
| p ≥ 0.70 | +0.006 | +0.028 | +0.063 |
| p ≥ 0.75 | −0.011 | −0.040 | +0.008 |
| p ≥ 0.80 | −0.007 | −0.037 | −0.004 |
| p ≥ 0.85 | +0.001 | −0.032 | −0.076 |
| p ≥ 0.90 | −0.007 | −0.087 | +0.007 `!` |

**Read the two tables against each other.** Accuracy climbs monotonically with the confidence floor
— 71.3% → 89.2% — and the money column never leaves the band −0.087 … +0.063. Fifteen cells, and
the largest is smaller than the pnl rule's +0.131. The confidence you demand is bought at an ask
that already prices it: paying ~0.86 to win 1.00 with a 7% fee leaves nothing, whether you are
right 86% of the time or 89%.

## Verification vs the pnl rule

| check | result |
|---|---|
| sample size | PASS — n=354 |
| both halves | PASS — −0.105 / −0.170 (consistently *worse*) |
| **paired test** | **FAIL** — 81 shared candles, 46 discordant, 26 vs 20, p=0.461 |
| **permutation** | **FAIL** — real +0.001 vs permuted mean +0.034, p=0.970 |
| **beats the null** | **FAIL** — +0.31 vs the pnl rule's +123.13 |

**VERDICT: NOT A FINDING.**

Read the paired line carefully: on the shared candles accuracy mode *is* right slightly more often
(26 vs 20). **That is the mode working exactly as designed** — it is not broken, and this is not a
criticism of it. The permutation result is the sharper one: a randomly permuted confidence, fired
through the same floors, does *better* (+0.034 vs +0.001, p=0.970), because what the floors mostly
select is a price band, not a skill band.

## The answer to the user's question

Accuracy mode is **safer in the sense they probably mean** — it is wrong far less often, 86% versus
53%, and that claim in the model file is honest. It is **not safer in money**: it turns a +$123 book
into a +$0.31 book, and the shipped `regime_floors` default turns it into −$13.74.

If "less dangerous" means smaller swings rather than more profit, the honest way to get that is a
smaller stake on the current rule — not a mode that trades accuracy for the entire edge. Stake and
gates remain untouched here; Kelly stays out under the two-confirmation rule.

Token budget: R-10, ~40k.
