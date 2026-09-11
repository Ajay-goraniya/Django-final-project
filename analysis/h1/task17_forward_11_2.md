# Task 17.2 — forward ledger, frozen 11.2 model

Cumulative, append-only. Frozen artifact `models/ef11_2_gbm_seed0.joblib`, never refitted. Forward = candles strictly after epoch 1789078800, the last candle of the replay that produced the +0.266 headline. Engine grading. EV margin 0.15.

_Last updated 2026-09-11 03:44 UTC._

## ACCUMULATING — 8 of 100 forward fires. NOT READABLE YET.

| | n | hit | per-fire | total |
|---|---|---|---|---|
| **forward, all** | 8 | 12.5% | **-0.734** | -5.87 |
| first half | 4 | — | -1.000 | -4.00 |
| second half | 4 | — | -0.467 | -1.87 |

**Replay baseline to beat: +0.266/fire, 62.7% hit (weekday-only, n=91).**

Forward hit rate is 1 of 8. If the replay's 62.7% were the true rate, seeing 1 or fewer hits in 8 fires has probability **0.0054**. That is context, **not a verdict** — n is far below the 60-fire bar, let alone 100, and a run this short can do this by chance. It is recorded so the trend is visible from the start rather than discovered at fire 100.

## By UTC day

| day | n | hit | per-fire | total | weekend |
|---|---|---|---|---|---|
| 2026-09-10 | 2 | 0% | -1.000 | -2.00 | no |
| 2026-09-11 | 6 | 17% | -0.645 | -3.87 | no |

## Fire-distance profile (forward)

| bps at fire | n | share | per-fire |
|---|---|---|---|
| <1 | 2 | 25% | -1.000 |
| 1-2.5 | 3 | 38% | -0.290 |
| 2.5-5 | 3 | 38% | -1.000 |

**Weekend forward fires: 0.** Still none — the replay had none either, so there is still no weekend evidence for this fire set.

