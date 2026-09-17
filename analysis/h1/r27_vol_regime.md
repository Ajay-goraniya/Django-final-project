# R-27 — EF per volatility regime. **It is not high vol. It is MID, and it is the first 30 seconds.**

Buckets fixed first: realised vol of the **prior 6 candles** (strictly earlier), cut at the 33rd/67th
percentile — **rv6 = 4.05 / 8.56 bps**. Same buckets everywhere below. 2,076 graded Polymarket fires
(poly_pnl + v12 lanes), graded on `venues.outcome`; Predict.fun lanes excluded rather than pooled.
Full grid: `analysis/h1/r27_grid_full.txt` (560 cells, 541 readable, 329 insufficient and unread).

## The plain answer to "is it high vol" — no

| bucket | n | W% | per $1 | total | med ask |
|---|---|---|---|---|---|
| **LOW** | 685 | **57.4%** | **+0.200** | +136.96 | 0.470 |
| **MID** | 706 | 50.4% | **+0.095** | +66.94 | 0.450 |
| **HIGH** | 685 | 51.7% | +0.114 | +77.89 | 0.450 |

**MID is the worst bucket, HIGH is not.** Low vol earns twice what either of the others does on the
current parameters. The premise that high volatility is where EF struggles is not what the record shows.

## Does any parameter need to differ by regime? Only one

Marginal response per axis, per bucket — the whole-grid read, so no best cell is picked out of 231
candidates:

| EV floor | LOW | MID | HIGH |
|---|---|---|---|
| 0.00 | +0.200 (685) | +0.095 (706) | +0.114 (685) |
| 0.25 | +0.478 (212) | +0.207 (414) | +0.131 (579) |
| 0.30 | **+0.615** (120) | +0.401 (216) | **+0.146** (251) |

| max entry price | LOW | MID | HIGH |
|---|---|---|---|
| ≤0.40 | +0.410 (132) | +0.253 (231) | +0.212 (217) |
| ≤0.80 | +0.200 (685) | +0.095 (706) | +0.114 (684) |

**Both move the same direction in every bucket** — a higher EV floor and a cheaper cap help
everywhere, most in LOW and least in HIGH. Same sign, same ordering, so these are **not** regime
parameters; they are restrictions that help everywhere, and by R-19 they help because they select
cheap. `min |p−0.5|` is non-monotone and inconsistent across buckets — noise shape, nothing to read.

**The fire-second window is the one axis whose sign depends on the bucket:**

| fire second | LOW | MID | HIGH |
|---|---|---|---|
| **0–30** | **+0.148** (185) | **−0.057** (120) | **−0.139** (109) |
| 30–45 | +0.314 (104) | +0.261 (93) | +0.265 (124) |
| 45–60 | +0.338 (67) | +0.123 (72) | +0.086 (92) |
| 60+ | +0.165 (329) | +0.097 (421) | +0.145 (360) |

Halves on that row, because a sign difference selected from a 560-cell sweep needs it:

| bucket, first 30 s | n | per $1 | h1 | h2 |
|---|---|---|---|---|
| LOW | 185 | +0.148 | +0.104 | +0.191 |
| MID | 120 | −0.057 | −0.143 | **+0.030** ← flips |
| HIGH | 109 | **−0.139** | **−0.142** | **−0.136** ← stable |

**In high vol the first 30 seconds loses money consistently — −0.139, halves −0.142 / −0.136, as
tight as anything measured this session. In low vol the same seconds make +0.148.** The rest of the
candle is positive in every bucket (30 s+: +0.219 / +0.126 / +0.162).

## What I am and am not claiming

**Claiming:** the current parameters already work worst in MID, not HIGH; and the only parameter whose
*sign* is regime-dependent is when in the candle you fire, with early fires losing in high vol and
paying in low vol.

**Not claiming a shipping rule.** This axis was chosen *after* seeing the marginals, from 560 cells;
the halves pass is necessary, not sufficient. n=109 is barely over the bar. And "don't fire early in
high vol" is gate-shaped — the owner asked for per-regime *parameters*, and a fire-second window is
one, but it would need its own forward test before it goes near an engine.

**Cheapest next step if V wants it tested:** run the 30 s+ window in high vol only as a paper twin and
let it accumulate its own record, rather than gridding this sample again.
