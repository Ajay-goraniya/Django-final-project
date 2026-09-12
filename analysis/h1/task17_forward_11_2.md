# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-12 08:44 UTC._

## ACCUMULATING — 95 of 100 forward fires. NOT READABLE YET.

Accrual: **2.84 fires/hour** (95 over 33.4 h). At that rate the 100-fire verdict lands about **Sat 12 Sep 09:40 UTC**.

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 95 | 45.3% | **-0.104** | -9.85 |
| first half | 47 | — | -0.207 | -9.71 |
| second half | 48 | — | -0.003 | -0.14 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 43 of 95. If the honest-rule 51.5% were the true rate, seeing 43 or fewer hits in 95 fires has probability **0.1327**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 38 | 47% | +0.006 | +0.22 | yes |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 52 | 55% | -0.069 |
| 1-2.5 | 19 | 20% | -0.291 |
| 2.5-5 | 9 | 9% | -0.260 |
| 5-10 | 11 | 12% | +0.008 |
| 10-25 | 4 | 4% | +0.384 |

**Weekend forward fires: 38.** The replay had none, so these are the first weekend evidence for this fire set.

