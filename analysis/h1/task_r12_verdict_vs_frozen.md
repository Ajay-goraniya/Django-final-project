# R-12's acceptance bar, answered: **the bigger training run did not help.**

V is right that I under-reported the most important row in R-25, and right to make frozen v10 the
comparator. Held to that bar, the answer is already in: **nine retrains this session, not one beats
frozen v10 on total PnL.** Said in the words asked for — **a model trained on all regimes does not
beat frozen v10 on a held-out window, and the bigger training run did not help.**

## Every retrain against frozen v10, on its own held-out window

| arm | training data | Brier / logloss | fires | per $1 | **total** | frozen's total, same window |
|---|---|---|---|---|---|---|
| R-12 big | **109 months, 4.75M rows** | 0.1952 / 0.5715 | 1036 | +0.070 | **+72.72** | **+121.43** |
| R-12 big + venue stage | same | 0.1628 | 419 | +0.241 | +100.96 | +98.02 ¹ |
| R-12 step 3: 8 days, 30 feats | logged window | 0.1697 | 453 | +0.171 | +77.63 | +98.02 |
| R-12 step 3: + p_hist | + history output | 0.1701 | 480 | +0.179 | +85.99 | +98.02 |
| R-16 twap60, proxy labels | logged window | — | 487 | +0.145 | +70.67 | +99.56 |
| R-16 twap60, venue labels | logged window | 0.1711 | 440 | +0.183 | +80.71 | +99.56 |
| R-17 executable rows only | 34,102 exec quotes | 0.1707 | 448 | +0.170 | +75.96 | +99.56 |
| R-25 plain 30 | logged window | 0.5092 LL | 505 | +0.176 | +89.12 | **+122.41** |
| R-25 + interactions (×3) | logged window | 0.5099–0.5116 LL | 485–513 | +0.149…+0.182 | 76.33–89.00 | +122.41 |

¹ The one arm that beat frozen on total (+100.96 vs +98.02) is R-12 B2, and verify.py rejected it:
halves **+0.226 / −0.060**, sign flip, and 397 discordant at 201-vs-196, McNemar p=0.841.

**Frozen v10 wins every clean comparison, on total PnL, with more fires and better calibration.**

## The pattern, and the one caveat that is mine not the data's

Every retrain shows the same shape: **fewer fires, better per-$1, lower total.** They fire 440–510
times where frozen fires 750–860, and the per-$1 gain never covers the volume lost. That is R-19's
result in another costume — the retrains keep the cheap half and drop the expensive winners.

**The caveat I have to state, because it limits what this proves.** My walk-forward-by-day fits train
on 2–6 days. Frozen v10 was fitted on 8 days with leave-one-day-out plus isotonic and then frozen.
So the logged-window retrains are data-starved relative to their comparator, and "retrain loses" there
is partly an artifact of the split, not a fact about retraining.

**What is not caveated is the one that matters for V's question.** R-12 big had **109 months and
4.75M rows** — no starvation — and lost on every measure: Brier 0.1952 against 0.1654, logloss 0.5715
against 0.4962, +72.72 against +121.43, with verify.py failing it on the paired test, cost sensitivity
and the null. **That is the clean test of "does the bigger training run help", and the answer is no.**

## Why, in one line

R-13, confirmed six times since: the direction call is the venue price. Frozen v10 gets that for free
through `lv` (its rank-2 coefficient), and every retrain on a short window re-derives a noisier version
of the same thing while firing less. More data does not buy a better forecast when the forecast is
already the market's.

## Recorded

Frozen v10 is R-12's benchmark from here. Any future arm reports against it — logloss, fires, hit%,
per $1, total, with `halves()` and `paired()` against frozen v10 — never against a weaker retrain.
V's cross-build check (12.8.11 vs HEAD `decide()`, 22,720 rows, 475 fires each, identical candles,
sides, seconds and prices, max |dp| = 0) removes build drift as a confound for all of the above.
