# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800. Engine grading. EV margin 0.15.

**Quote rule: NEXT — the first collector sample at or AFTER the decision second.** The original ledger used the last sample at or *before* it, i.e. a quote up to 5 s older than the price it decided on. That is the Task 20 artifact; those eight fires were discarded and this ledger rebuilt, because a mixed history would be worse than none.

_Last updated 2026-09-17 00:46 UTC._

## VERDICT: >= 100 forward fires reached — read the halves and run verify.py

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 347 | 44.4% | **-0.081** | -28.03 |
| first half | 173 | — | -0.072 | -12.40 |
| second half | 174 | — | -0.090 | -15.62 |

**Baseline: the replay's +0.266 is RETRACTED (Task 20 — stale quote). Under the honest rule the same replay gives +0.018/fire at this margin. That ~0.00 is what this ledger is testing against, not +0.266.**

Forward hit rate is 154 of 347. If the honest-rule 51.5% were the true rate, seeing 154 or fewer hits in 347 fires has probability **0.0047**. n is past the 60-fire bar and past 100, and both halves are reported above; read the verdict block from task17_verdict.py, not this probability alone.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 55 | 45% | -0.147 | -8.07 | no |
| 2026-09-12 | 104 | 48% | -0.001 | -0.11 | yes |
| 2026-09-13 | 75 | 44% | -0.116 | -8.72 | yes |
| 2026-09-14 | 20 | 45% | -0.096 | -1.92 | no |
| 2026-09-15 | 54 | 46% | +0.073 | +3.93 | no |
| 2026-09-16 | 37 | 32% | -0.301 | -11.15 | no |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 231 | 67% | -0.061 |
| 1-2.5 | 60 | 17% | -0.173 |
| 2.5-5 | 28 | 8% | -0.211 |
| 5-10 | 22 | 6% | +0.046 |
| 10-25 | 6 | 2% | +0.204 |

**Weekend forward fires: 179.** The replay had none, so these are the first weekend evidence for this fire set.

