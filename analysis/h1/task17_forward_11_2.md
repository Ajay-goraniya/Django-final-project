# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-12 06:44 UTC._

## ACCUMULATING — 85 of 100 forward fires. NOT READABLE YET.

Accrual: **2.71 fires/hour** (85 over 31.4 h). At that rate the 100-fire verdict lands about **Sat 12 Sep 11:27 UTC**.

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 85 | 44.7% | **-0.121** | -10.25 |
| first half | 42 | — | -0.256 | -10.76 |
| second half | 43 | — | +0.012 | +0.51 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 38 of 85. If the honest-rule 51.5% were the true rate, seeing 38 or fewer hits in 85 fires has probability **0.1261**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 28 | 46% | -0.007 | -0.19 | yes |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 43 | 51% | -0.117 |
| 1-2.5 | 18 | 21% | -0.251 |
| 2.5-5 | 9 | 11% | -0.260 |
| 5-10 | 11 | 13% | +0.008 |
| 10-25 | 4 | 5% | +0.384 |

**Weekend forward fires: 28.** The replay had none, so these are the first weekend evidence for this fire set.

