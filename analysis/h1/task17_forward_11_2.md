# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-12 16:44 UTC._

## VERDICT: >= 100 forward fires reached — read the halves and run verify.py

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 128 | 46.1% | **-0.076** | -9.79 |
| first half | 64 | — | -0.168 | -10.78 |
| second half | 64 | — | +0.015 | +0.99 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 59 of 128. If the honest-rule 51.5% were the true rate, seeing 59 or fewer hits in 128 fires has probability **0.1281**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 71 | 48% | +0.004 | +0.28 | yes |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 82 | 64% | -0.070 |
| 1-2.5 | 21 | 16% | -0.197 |
| 2.5-5 | 9 | 7% | -0.260 |
| 5-10 | 12 | 9% | +0.075 |
| 10-25 | 4 | 3% | +0.384 |

**Weekend forward fires: 71.** The replay had none, so these are the first weekend evidence for this fire set.

