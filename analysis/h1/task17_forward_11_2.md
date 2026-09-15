# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-15 02:44 UTC._

## VERDICT: >= 100 forward fires reached — read the halves and run verify.py

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 257 | 45.5% | **-0.085** | -21.81 |
| first half | 128 | — | -0.076 | -9.79 |
| second half | 129 | — | -0.093 | -12.02 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 117 of 257. If the honest-rule 51.5% were the true rate, seeing 117 or fewer hits in 257 fires has probability **0.0319**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 104 | 48% | -0.001 | -0.11 | yes |
| 2026-09-13 | 75 | 44% | -0.116 | -8.72 | yes |
| 2026-09-14 | 20 | 45% | -0.096 | -1.92 | no |
| 2026-09-15 | 1 | 0% | -1.000 | -1.00 | no |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 191 | 74% | -0.093 |
| 1-2.5 | 32 | 12% | -0.240 |
| 2.5-5 | 16 | 6% | +0.003 |
| 5-10 | 14 | 5% | +0.151 |
| 10-25 | 4 | 2% | +0.384 |

**Weekend forward fires: 179.** The replay had none, so these are the first weekend evidence for this fire set.

