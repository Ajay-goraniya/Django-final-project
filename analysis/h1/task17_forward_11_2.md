# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-11 09:16 UTC._

## ACCUMULATING — 21 of 100 forward fires. NOT READABLE YET.

Accrual: **2.05 fires/hour** (21 over 10.2 h). At that rate the 100-fire verdict lands about **Sat 12 Sep 23:18 UTC**.

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 21 | 38.1% | **-0.202** | -4.24 |
| first half | 10 | — | -0.310 | -3.10 |
| second half | 11 | — | -0.104 | -1.14 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 8 of 21. If the honest-rule 51.5% were the true rate, seeing 8 or fewer hits in 21 fires has probability **0.1561**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 19 | 42% | -0.118 | -2.24 | no |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 11 | 52% | +0.032 |
| 1-2.5 | 8 | 38% | -0.532 |
| 2.5-5 | 1 | 5% | -1.000 |
| 5-10 | 1 | 5% | +0.661 |

**Weekend forward fires: 0.** Still none — the replay had none either, so there is still no weekend evidence for this fire set.

