# Task R-6 — calibrated `p` inside the EV rule, walk-forward

V, 09-15 02:3x. Not a gate: the brain's own `p` corrected by its own record. R-5 run 2 measured
the defect this is meant to fix — `p` overconfident in all five bins.
Script `analysis/h1/task_r6_calibrated_p.py`.

**Verdict: neither calibrator ships. Both lose on V's stated condition.**

## Setup, and why the candidate stream had to be rebuilt

`trades` holds only the ticks that fired; `decisions` holds only the ones that did not (its `fire`
column is 0 on every row of all three lanes). Neither alone can answer "fires **added**", so the
stream is their union: **29,779 ticks over 1,709 candles** (1,698 fired, 28,081 not).

The rule is read from the engine's own `model_v10.json` — fee 0.07, rv60 edges 0.1668 / 0.3653,
thresholds low 0.15 / mid 0.25 / high 0.25, one fire per candle at the first qualifying tick.

**Rule sanity check, run before anything else: replaying the raw rule reproduces 946 of the
engine's 948 fires and proposes 0 candles the engine did not fire.** The replay is the engine's
rule, not an approximation of it.

`p` is p_side (0.5098–0.99 in both tables), so calibration **cannot change the side** — only
whether the EV rule fires. That is the entire mechanism under test.

Split at the median graded fire: **train 848 fires, test stream 16,406 ticks over 694 candles.**

Platt fitted on the training half: a = −0.470, b = 1.357. Mappings:

| raw `p` | Platt | isotonic |
|---|---|---|
| 0.55 | 0.451 | 0.483 |
| 0.65 | 0.591 | 0.591 |
| 0.80 | 0.804 | **1.000** |

## Second half — the whole grid

### Platt

| book | n | win% | per $1 | total |
|---|---|---|---|---|
| raw | 369 | 54.5% | +0.176 | **+64.90** |
| calibrated | 42 | 61.9% | **+0.466** | **+19.57** |
| **DROPPED** | 327 | 54.1% | **+0.154** | **+50.38** |

Fires 370 → 42: **kept 42, dropped 328, added 0.** It declines 89% of the book — and **the book it
declines was profitable**, +0.154 per $1 and +50.38 in total. Calibration is not finding losers; it
is finding near-average trades and refusing them.

### Isotonic

| book | n | win% | per $1 | total |
|---|---|---|---|---|
| raw | 369 | 54.5% | +0.176 | **+64.90** |
| calibrated | 345 | 73.3% | +0.067 | **+23.24** |
| DROPPED | 230 | 54.3% | +0.129 | +29.58 |
| ADDED | 206 | 85.4% | +0.124 | +25.54 |

Kept 139, dropped 231, **added 206**. The added set wins 85.4% of the time and still only makes
+0.124 per $1 — they are expensive favourites. The cause is visible in the mapping table:
**isotonic saturates at 1.000 for p = 0.80**, because the top training bin happened to be all wins.
A forecast of exactly 1.000 makes EV explode, so the rule fires on anything dear. That is an
overfit step, not a calibration.

### Rolling refit every 200 graded fires

| calibrator | refits | fires | per $1 | total |
|---|---|---|---|---|
| Platt | 8 | 184 | +0.307 | +56.57 |
| isotonic | 8 | 781 | +0.078 | +60.86 |

Both still below the raw book's total on the same window.

## Verification

| check | Platt | isotonic |
|---|---|---|
| sample size | **FAIL** — 42 calibrated fires, under the 60 bar | PASS |
| both halves | PASS — +0.119 / +0.388 | PASS — −0.062 / −0.148 |
| permutation (calibrated predictions permuted, never labels) | PASS — p=0.000 | PASS — p=0.000 |
| **beats the null** (V's ship metric: total PnL, same candles) | **FAIL** — +19.57 vs +64.90 | **FAIL** — +23.24 vs +64.90 |
| paired | **FAIL** — no discordant pairs | **FAIL** — no discordant pairs |

**VERDICT: NOT A FINDING, both.**

On `paired()`: wherever both rules fire they fire the same side — `p_side` ≥ 0.5 by construction
and calibration is monotone — so there are no discordant pairs and the test carries no information
here. Reported failing for that reason, not because the rules tie. The informative statistic is the
**DROPPED** book, above.

## The one thing in R-6 that is not dead

Platt-calibrated EV reads **+0.466 per $1 on its 42 fires**, with both halves positive
(+0.119 / +0.388) and a permutation p of 0.000. **At n=42 that is under the 60 bar, so it is marked
insufficient and not read** — and the same lesson has already been paid for twice here (the 09-12
weekend cell at n=62, and R-5 run 1 at n=1,543 reversing at n=1,872).

It is also directly contradicted by the dropped book: the 328 fires Platt declines made **+50.38**.
A rule that concentrates per-$1 while declining profitable trades is only worth having if capital,
not candles, is the binding constraint — and on this lane it is not, the same reason R-5's Kelly
book failed.

**Re-run when the Platt cell passes 60 fires.** Nothing else in R-6 is worth revisiting.

## Live

Not run. 5 graded live fires (`analysis/h1/task_r5_zurich_readiness.md`); a calibration fit needs
a training half. Blocked on sample, not access.
