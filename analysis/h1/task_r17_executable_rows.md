# R-17 — executable-quote rows only, and a correction to my own claim

## 0. Correction first

In the R-16 addendum (and twice to V) I wrote that **`p_venue` is v10's largest coefficient at
1.663**. That is wrong. Reading the shipped `model_v10.json`:

| rank | feature | coefficient |
|---|---|---|
| 1 | **`move_bps`** | **+1.6629** |
| 2 | **`lv`** = logit(p_venue) | **+1.5514** |
| 3 | `mv_x_sec` | −0.9822 |
| 4 | `imb20` | +0.1328 |
| 5 | `lv_x_sec` | −0.1010 |
| … | | |
| 16 | **`p_venue`** | **−0.0387** |

1.663 is `move_bps`; I read `coef[0]` and attributed it to the wrong name. **The venue's influence is
real and large but it arrives through `lv`, rank 2, not through `p_venue`, rank 16.** The addendum's
substance survives — the venue is v10's second-biggest input and 81% of the values behind it are
trade prints — but the sentence naming `p_venue` as the largest coefficient was false and V was told
it twice. Corrected in `task_r16_addendum.md` as well.

## 1. Row counts first, as the brief requires

Executable-quote rows (a real quoted ask, `0 < ask < 1`, with features) in the logged window:

| source | table | total | per day |
|---|---|---|---|
| poly_pnl | decisions | 16,852 | 670 / 2,680 / 2,204 / 2,051 / 2,409 / 2,721 / 2,103 / 1,951 / 63 |
| v10_poly_long4 | decisions | 12,812 | 09-08..09-14 |
| v12_poly_lane | decisions | 7,724 | 09-11..09-14 |
| polybook | 1 s snapshots, `live websocket` | 285,802 | 09-11..09-15 |
| zurich_2 | live fills | 70 | 09-15 |

Merged across lanes: **34,102 rows over 9 days** (881 / 5,099 / 2,358 / 3,863 / 7,655 / 7,917 /
4,241 / 2,039 / 49). **Not insufficient** — the brief's stop condition does not trigger.

## 2. Part A — what the trade prints do to the venue weight, on v10's own table

Same recipe, same 30 features, v10's own training table; only the row set changes.

| fit on | n | `lv` | `move_bps` | `p_venue` |
|---|---|---|---|---|
| all rows (≈ shipped v10) | 21,566 | **+1.5232** | +1.03 | +0.1762 |
| **executable book rows only** | 4,117 | **+1.0861** | **+1.38** | +0.0929 |
| trade-print rows only | 17,449 | **+1.6719** | +0.57 | +0.2453 |

**The addendum's hypothesis is confirmed, via `lv`.** Dropping the trade prints cuts the venue weight
by 29% (1.52 → 1.09) and moves that weight onto the price action (`move_bps` 1.03 → 1.38). The
print-only fit goes the other way (1.67). So v10's reliance on the venue *is* partly an artifact of
which rows it was fitted on.

(The all-rows refit gives 1.5232 against the shipped 1.5514 because `finalize.py` fits on all 22,720
rows with `fillna(0)`, not only the 21,566 with a venue price. The pipeline check reproduced the
shipped fit exactly when run its way.)

## 3. Part B — retrain on executable rows in the logged window

34,102 executable rows, walk-forward by day, same recipe. The result is the opposite of Part A and it
is the more important one:

| feature | shipped v10 | retrained on executable Polymarket rows | delta |
|---|---|---|---|
| `lv` | +1.5514 | **+1.8045** | +0.2531 |
| `move_bps` | +1.6629 | **−0.0161** | **−1.6790** |
| `mv_x_sec` | −0.9822 | −0.0313 | +0.9509 |
| `p_venue` | −0.0387 | −0.0792 | −0.0404 |

Top six retrained: `lv +1.80`, `lv_x_sec +0.16`, `perp_n15 +0.12`, `micro_bps +0.11`, `imb5 −0.11`,
`rv60 −0.10`.

**Given a real, executable Polymarket book, the recipe throws `move_bps` away entirely and reads the
price.** The largest coefficient in the deployed model drops from +1.66 to −0.02. That is the most
direct statement of R-13 this session has produced: it is not that the model *happens* to track the
price — when fitted on executable quotes, tracking the price is what the fit *converges to*.

The contrast with Part A is real and worth keeping: on the Predict.fun-era book the fit leans on
`move_bps`; on the Polymarket book it leans entirely on `lv`. Different venue, different book quality,
opposite conclusion — so neither is a general law, and Part B is the one that matches what runs live.

Calibration (walk-forward, 28,122 rows) is serviceable but drifts under-confident in the upper middle:

| bin | n | claimed | actual |
|---|---|---|---|
| 0.00–0.20 | 4,935 | 0.078 | 0.090 |
| 0.20–0.35 | 4,082 | 0.275 | 0.284 |
| 0.35–0.45 | 1,856 | 0.383 | 0.420 |
| 0.45–0.55 | 6,087 | 0.487 | 0.465 |
| 0.55–0.65 | 3,558 | 0.599 | 0.639 |
| 0.65–0.80 | 3,245 | 0.727 | **0.787** |
| 0.80–1.01 | 4,359 | 0.929 | 0.929 |

**Brier: retrained 0.1707 vs frozen v10 0.1637 — the retrain is worse.**

## 4. PnL and verdict

The trading arm of this exact fit is already measured (`task_r16_retrain.md`, "recipe, old centring",
which is this model): **448 fires, 50.4% hit, +0.170/$1, +75.96 total, maxDD 14.24**, against frozen
v10's **758 fires, 52.6%, +0.131/$1, +99.56, maxDD 14.09**. Better per fire, 40% fewer fires, **$24
less money**, and verify.py fails it against frozen v10 on halves, the paired test and the null.

**R-17 does not ship.** No paper twin. What it delivers is the diagnostic V asked for, and it lands
harder than the retrain would have: fitted on nothing but executable quotes, the recipe's answer is
*read the book*. There is no version of this feature set that beats the price it is reading.
