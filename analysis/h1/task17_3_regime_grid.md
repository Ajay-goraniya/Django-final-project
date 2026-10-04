# Task 17.3 — rain or sun for 11.2
H1, 2026-09-11 03:05 UTC. V's task. Buckets fixed in advance: Task 13 trailing-12-candle-range
quartiles (cuts 8.6 / 13.0 / 19.8 bps), 8-hour UTC blocks, weekday vs weekend.

Two parts, because **the literal ask cannot be answered at the available sample**, and saying so
plainly is the deliverable.

## A. The PnL grid over the 91 venue-window fires — reported, not read

| bucket | n | per-fire | |
|---|---|---|---|
| Q1 calm | 13 | −0.059 | insufficient |
| Q2 | 38 | +0.296 | insufficient |
| Q3 | 24 | +0.420 | insufficient |
| Q4 busy | 16 | +0.211 | insufficient |
| 00–08 | 20 | +0.358 | insufficient |
| 08–16 | 32 | +0.123 | insufficient |
| 16–24 | 39 | +0.329 | insufficient |
| weekday | **91** | +0.263 | the whole sample |
| **weekend** | **0** | — | **see below** |
| per UTC hour | 1–11 | −1.000 … +0.980 | all insufficient |

### The weekend cell is empty, and that matters

**Every one of the 91 fires is on a weekday.** The venue window (09-08 → 09-10) is Tuesday to
Thursday, so **the 11.2 replay contains no weekend candles at all.** The +0.266/fire headline is a
weekday-only number.

This is worth V's attention because **Sat–Sun is the planned live test window.** The forward test
will be the first weekend evidence for the fire set that has ever existed. Part B below is the only
weekend evidence available today, and it is about the signal, not the fires.

**1 of 9 cells reaches the 60-fire bar — and that one cell is "weekday", which is simply the entire
sample.** Per-hour cells run n=1 to n=11 and swing from −1.000 to
+0.980, which is exactly what noise looks like at that size. The full grid is in
`task17_3_regime_grid.py` output; I am not reproducing the numbers here as a table because doing so
invites reading them.

**Verdict: the rain-or-sun question cannot be answered for the 11.2 *fire set* at this sample.**
It needs the Task 17.2 forward test. Anyone who wants a regime switch out of this data is fitting
noise — which is the thing the user banned.

## B. The part that *is* answerable: is the direction signal regime-stable?

The fire set is small, but the **signal** can be measured at scale. A **diagnostic** model — trained
on the first 80% of pre-cutoff candles, evaluated on the held-out 20% — gives **14,442 out-of-sample
candles**, every cell far above the bar.

> This diagnostic model is **not** the frozen artifact. `models/ef11_2_gbm_seed0.joblib` is never
> retrained; a retrain is always a new file, or the forward test loses its meaning.

**Accuracy, not PnL.** Stated up front because it is the rule we keep re-learning: this says the
signal holds across regimes, **not** that it is profitable in each one.

| bucket | n | S=20 | S=60 | S=120 |
|---|---|---|---|---|
| Q1 calm | 6,208 | 0.581 | 0.643 | 0.714 |
| Q2 | 3,626 | 0.583 | 0.648 | 0.719 |
| Q3 | 2,803 | 0.578 | 0.634 | 0.719 |
| Q4 busy | 1,805 | 0.572 | 0.649 | 0.724 |
| **weekday** | 10,410 | 0.576 | 0.643 | 0.719 |
| **weekend** | 4,032 | **0.588** | 0.645 | 0.714 |
| 00–08 | 4,800 | 0.581 | 0.636 | 0.712 |
| 08–16 | 4,827 | 0.579 | 0.649 | 0.729 |
| 16–24 | 4,815 | 0.578 | 0.645 | 0.712 |
| **overall** | 14,442 | **0.580** | **0.643** | **0.718** |

**The signal is rain-or-sun in the user's exact sense.** The spread across all nine cells is
**1.6 pp at S=20, 1.5 pp at S=60, 1.7 pp at S=120** — flat. No regime switch is warranted, and
building one would be fitting noise to a 1.6-point spread.

**On the user's weekend concern specifically:** weekend accuracy is **higher** than weekday at
S=20 (0.588 vs 0.576) and equal at S=60 (0.645 vs 0.643), marginally lower at S=120 (0.714 vs
0.719). On 4,032 weekend candles there is **no weekend decay in the direction signal.** That is
reassuring for the Sat–Sun live test window, with the caveat below.

## What this does and does not establish

**Does:** the model's directional edge is stable across volatility regime, hour of day and day type,
out of sample, on 14k candles. Nothing in the tape argues for switching it on and off.

**Does not:** say anything about PnL by regime. Profitability depends on the *ask* as much as the
direction, and the ask is only observable on the 648-candle venue window — where, per part A, every
cell is too small. **A stable signal can still be unprofitable in a regime where the venue prices it
correctly.** Task 16's null is the standing reminder: 59.2% accuracy still lost money.

## Limits

- Part B uses a diagnostic model, so its absolute accuracy is not the frozen artifact's. The
  **stability** is the finding, not the level.
- Held-out slice is contiguous and pre-cutoff — it is a different period, not a different year.
- Part A's grid is engine-graded on the venue window; part B has no grading dependence (it compares
  the model's call to the Binance close directly).

Repro: `analysis/h1/task17_3_regime_grid.py`.
