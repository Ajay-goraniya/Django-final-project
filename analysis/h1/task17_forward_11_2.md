# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-12 12:44 UTC._

## VERDICT: >= 100 forward fires reached — read the halves and run verify.py

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 111 | 48.6% | **-0.030** | -3.32 |
| first half | 55 | — | -0.147 | -8.07 |
| second half | 56 | — | +0.085 | +4.74 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 54 of 111. If the honest-rule 51.5% were the true rate, seeing 54 or fewer hits in 111 fires has probability **0.3062**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 54 | 54% | +0.125 | +6.74 | yes |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 66 | 59% | +0.021 |
| 1-2.5 | 20 | 18% | -0.242 |
| 2.5-5 | 9 | 8% | -0.260 |
| 5-10 | 12 | 11% | +0.075 |
| 10-25 | 4 | 4% | +0.384 |

**Weekend forward fires: 54.** The replay had none, so these are the first weekend evidence for this fire set.

