# Task R-8 — the taker ratio as a feature: parity, retrain, ship test

V, 09-15 19:1x. Script `analysis/h1/task_r8_taker_feature.py`.

**(a) parity passes decisively. (b) the feature does not earn its place. (c) ship condition fails.**

R-7's accuracy ordering is **not** refuted — it is still in the data. What is refuted is the next
claim, that dropping it into v10's feature vector produces a better model. Two different things.

## (a) PARITY — can our own perp tape reproduce the archive series?

The archive lags a day, so a live engine can never read it. The engine *does* already consume the
perp trade stream (`FeatureState.on_perp_trade`, and its deque keeps 20 minutes — a 5-min window
fits with room to spare). Rebuilt taker buy vol / taker sell vol per completed 5-min bar from the
raw futures aggTrades tape, 2026-09-08…09-14:

| | |
|---|---|
| bars rebuilt / archive / common | 2,016 / 2,016 / **2,016** |
| Pearson | **0.9999** |
| Spearman | **0.9998** |
| median \|diff\| | **0.0002** |
| median, ours vs archive | 0.9608 vs 0.9609 |
| **tercile agreement** | **99.4% (2,004/2,016)** |

**The feature is computable live from a tape the engine already has.** Parity is not the blocker.

## (b) RETRAIN — walk-forward by day, v10's own recipe

32,062 evaluated ticks over 8 days, 1,693 candles; labels and PnL on `venues.outcome`. Train on
days < d, test on day d. Recipe is `learner/train.py`'s own logit arm — StandardScaler →
LogisticRegression(C=0.3) → isotonic fitted on inner GroupKFold OOF — which is what
`model_v10.json` actually is. (lightgbm is not installed here; the shipped artifact is the logit
pipeline, so this is faithful to it. Stated, not skipped.)

| model | logloss | fires | hit% | per $1 | total |
|---|---|---|---|---|---|
| frozen v10 | **0.4911** | 758 | 52.6% | +0.131 | **+99.56** |
| retrain, no feature | 0.5078 | 452 | 50.2% | **+0.167** | +75.37 |
| **retrain + taker** | 0.5075 | 443 | 49.9% | +0.160 | +70.98 |

Per day, whole grid, nothing dropped — frozen vs retrain+taker per $1:
09-10 +0.127 / **+0.326**, 09-11 −0.000 / **+0.135**, 09-12 **+0.153** / +0.087,
09-13 +0.126 / **+0.180**, 09-14 **+0.264** / +0.133. Three days up, two down.

**The matched comparison is the one that matters.** Retrain-with-feature vs retrain-without is the
only pair that differs by exactly one thing:

- logloss 0.5078 → 0.5075 — a change of **0.0003**, noise.
- per $1 **+0.167 → +0.160** — the feature makes it *worse*.
- total **+75.37 → +70.98** — worse.

## (c) SHIP CONDITION — fails

> *beats frozen on pooled PnL per $1 **AND** in both halves **AND** verify.py passes*

| clause | result |
|---|---|
| pooled per $1 | +0.160 vs +0.131 → **beats** (+0.029) |
| both halves | h1 +0.063 **beats**, h2 −0.033 **loses** → **FAILS** |
| verify.py | **FAILS** |

`verify.py` on retrain+taker vs frozen:

| check | result |
|---|---|
| sample size | PASS — n=443 |
| **both halves** | **FAIL** — +0.063 / −0.033, sign flips |
| **paired test** | **FAIL** — 403 shared candles, **314 discordant, 156 vs 158, McNemar p=0.955** |
| **beats the null** | **FAIL** — +0.160 vs +0.167 for the same retrain *without* the feature |

The paired test is the cleanest result here: on the 314 candles where the two models disagree they
split **156 / 158**. That is not a weak signal, it is *no* signal, and with 314 discordant pairs it
is a well-powered null rather than an underpowered one.

## Why — and it is not redundancy

The obvious explanation would be that the model already has this information through its order-flow
features. It does not:

`corr(taker, ofi5) +0.053 · ofi15 +0.073 · ofi60 +0.148 · perp_n15 −0.034 · spot_imb60 +0.069`

Every correlation is under 0.15. **The feature carries information the model does not already have,
and the model still cannot turn it into a better forecast.** R-7's ordering is a marginal,
monotone tercile effect; a logistic model with 30 other inputs and 2–7 days of training data does
not extract it.

One caveat stated plainly: **the frozen-vs-retrain comparison is not a fair test of the feature.**
Frozen v10 was trained on much more data than the 2–7 days each walk-forward fold gets, which is
why both retrains lose to it on logloss and total PnL. That handicap applies equally to both
retrain arms, which is exactly why the matched retrain-with vs retrain-without pair is the test
that decides — and the feature loses it.

## Verdict

**Do not build 12.10 on this.** Parity is clean and the feature is live-computable, so the
mechanism is there if it is ever wanted; but inside the model, on the data available, it is worth
nothing (McNemar p=0.955) and slightly negative on PnL.

R-7 stands as a measured property of when the model is cold. It is not, on this evidence, a feature
that makes the model less cold.

What would change it: more labelled days, so a retrain is not fighting a frozen model with a much
larger training set; and a live sample, since all of this is paper at the quoted ask.

Token budget: R-7 + R-8, script, fetches and both reports, ~110k.
