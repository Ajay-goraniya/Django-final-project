# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-12 02:44 UTC._

## ACCUMULATING — 66 of 100 forward fires. NOT READABLE YET.

Accrual: **2.41 fires/hour** (66 over 27.4 h). At that rate the 100-fire verdict lands about **Sat 12 Sep 16:02 UTC**.

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 66 | 42.4% | **-0.194** | -12.78 |
| first half | 33 | — | -0.283 | -9.35 |
| second half | 33 | — | -0.104 | -3.43 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 28 of 66. If the honest-rule 51.5% were the true rate, seeing 28 or fewer hits in 66 fires has probability **0.0881**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 9 | 33% | -0.301 | -2.71 | yes |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 27 | 41% | -0.220 |
| 1-2.5 | 17 | 26% | -0.302 |
| 2.5-5 | 7 | 11% | -0.476 |
| 5-10 | 11 | 17% | +0.008 |
| 10-25 | 4 | 6% | +0.384 |

**Weekend forward fires: 9.** The replay had none, so these are the first weekend evidence for this fire set.

