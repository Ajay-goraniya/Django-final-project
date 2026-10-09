# R-12 pipeline check — my recipe **is** v10's recipe (exact)

V pushed v10's own training table (`learner/live_backup/v10_features_8days.parquet.gz`, 4c302bb):
22,720 rows × 46 cols, 2026-08-29 00:00 .. 09-06 21:20, offsets 15..240 s, all 30 features present.
`model_v10.json` independently records `n_rows=22720`, `n_candles=2272` and exactly those 8 dates, so
this is the real input to `learner/finalize.py`, not a reconstruction of it.

Script: `analysis/h1/r12_pipeline_check.py`.

## Why this had to be run before any earlier R-12 number counts

Every R-12 arm trained "v10's recipe" from **my own reading** of `train.py` / `finalize.py`. If that
reading were wrong in any detail — the C, the isotonic fold count, the derived-feature formulas, the
`fillna` — then R-12, R-12b, R-12c and step 3 were all comparing a big-history model against
something that is not the live model, and every verdict in that sequence would be void. This is the
"verify against the running artifact, never against a reconstruction of it" rule applied to the one
place it had not yet been applied.

## Result: bit-for-bit

Refit `finalize.py`'s export path (inner `GroupKFold(8)` OOF → isotonic → logistic on all rows) on
that table and compare every exported number against the shipped `model_v10.json`:

| exported field | max abs diff | max rel diff |
|---|---|---|
| `scaler_mean` (30) | 0.000e+00 | 0.000e+00 |
| `scaler_scale` (30) | 0.000e+00 | 0.000e+00 |
| `coef` (30) | 0.000e+00 | 0.000e+00 |
| `intercept` | 0.000e+00 | 0.000e+00 |
| `iso_x` (116 knots) | 0.000e+00 | 0.000e+00 |
| `iso_y` (116 knots) | 0.000e+00 | 0.000e+00 |

Feature order identical to the shipped list. The two derived numbers in the file also reproduce
exactly: `oos_logloss_book` 0.504180 vs 0.504180, `venue_logloss_book` 0.521720 vs 0.521720, and
`rv60_edges` 0.1668167347 / 0.3652950622 to ten decimals.

**Every earlier R-12 comparison was against the genuine v10.** Nothing in R-12 … R-12c or step 3
needs re-running.

## Second result: v10's edge over the price existed in training and did not survive

The same run answers R-13's question on v10's *own* window, leave-one-day-out (each day predicted by
a model that never saw it). On the 4,117 **real-book** rows:

| | acc | Brier | logloss |
|---|---|---|---|
| v10, LODO | **0.7411** | 0.1705 | 0.5042 |
| venue price alone | 0.7236 | 0.1785 | 0.5217 |

Paired: 430 discordant, model right 251 / venue right 179, **exact McNemar p = 0.0006**. Both halves
positive (+0.009 / +0.026).

That is the opposite of R-13's live-window verdict (92.1% agreement, 2,531 discordant, 1,263 vs
1,268, **p = 0.937**). Two reasons it is not a contradiction, and neither makes it a finding:

1. **Rain or sun fails on its face.** Real-book rows exist on only two readable days in this window
   (09-02 n=1707, 09-03 n=2363; 09-04 has 47 = insufficient). A two-day result is not a result.
2. **LODO removes day leakage, not design leakage.** `finalize.py` chose the feature set, the C, the
   isotonic scheme and the regime edges *on these 8 days as a whole*. Holding out one day at a time
   does not undo a design selected on all eight.

Split by row type, the agreement rate is a population effect and not drift:

| rows | n | agree% | corr(p, p_venue) | acc model | acc venue |
|---|---|---|---|---|---|
| all with `p_venue` | 21,566 | 92.9% | 0.9757 | 0.7451 | 0.7418 |
| real book (`is_book==1`) | 4,117 | 89.6% | 0.9520 | 0.7411 | 0.7236 |
| synthetic book | 17,449 | 93.7% | 0.9814 | 0.7460 | 0.7461 |

On synthetic rows the model and the price are the same thing to four decimals (0.7460 / 0.7461) —
those rows carry no information about whether v10 beats a market. All of the training-window edge
lives in the 4,117 real-book rows, on two days.

**So R-13 is confirmed, and now has a mechanism.** v10 was selected on a window where it out-predicted
the book by 1.75 points; in the live window that margin is 0.0 points at p=0.937. The edge was in the
design choice, not in the model. Nothing here changes the R-13 conclusion that the live engine's
direction call is the venue price and its EV is the book spread.

verify.py on the training-window edge: **NOT A FINDING** — `sample()` fails (2 readable day-cells),
and it does not reproduce out of window.
