# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-16 04:44 UTC._

## VERDICT: >= 100 forward fires reached — read the halves and run verify.py

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 309 | 46.0% | **-0.051** | -15.88 |
| first half | 154 | — | -0.082 | -12.64 |
| second half | 155 | — | -0.021 | -3.24 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 142 of 309. If the honest-rule 51.5% were the true rate, seeing 142 or fewer hits in 309 fires has probability **0.0292**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 104 | 48% | -0.001 | -0.11 | yes |
| 2026-09-13 | 75 | 44% | -0.116 | -8.72 | yes |
| 2026-09-14 | 20 | 45% | -0.096 | -1.92 | no |
| 2026-09-15 | 53 | 47% | +0.093 | +4.93 | no |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 212 | 69% | -0.053 |
| 1-2.5 | 49 | 16% | -0.109 |
| 2.5-5 | 23 | 7% | -0.132 |
| 5-10 | 20 | 6% | +0.072 |
| 10-25 | 5 | 2% | +0.445 |

**Weekend forward fires: 179.** The replay had none, so these are the first weekend evidence for this fire set.

