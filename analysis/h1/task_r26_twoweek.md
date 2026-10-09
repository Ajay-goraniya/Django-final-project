# R-26 — the second week does not help. And the arm that *did* beat frozen v10 is not a retrain.

The owner's ask, with the venue price this time. V is right that R-12 never answered it: the 109-month
run masked 12 of 30 features including `p_venue`/`lv`/`lv_x_sec`, so it was blind to exactly where
R-13 says the signal is.

**One correction to the brief, and it improves the test.** V said `spread_bps`, `imb5`, `imb20`,
`micro_bps` cannot be rebuilt for week 2 and the design must drop to 26 features. True of *rebuilding
from the archives* — unnecessary, because **the engine logged all four live**: on the 34,121 logged
ticks they are present on 100.0% of rows and non-zero on 100.0%, medians 0.0129 / 0.0211 / 0.0323 /
0.0002 against week 1's 0.0127 / 0.0492 / 0.0561 / 0.0003. So the full 30-feature arm runs, matches
frozen v10's input set exactly, and nothing needed downloading. Both are reported.

Week 1: 22,720 rows / 2,272 candles (08-29..09-06). Week 2: 34,121 rows / 1,906 candles
(09-08..09-16). **Gap: 09-07 has no venue quotes**, so the two weeks are not contiguous.

## The answer to the owner's question

**30 features**, walk-forward by day through week 2:

| arm | logloss | Brier | fires | hit% | per $1 | total |
|---|---|---|---|---|---|---|
| (a) frozen v10 | 0.4987 | 0.1665 | 1033 | 53.2% | +0.141 | +145.81 |
| **(b) week 1 only** | **0.4984** | **0.1664** | 778 | 55.8% | +0.234 | **+182.17** |
| (c) week 1 + week 2 | 0.4994 | 0.1669 | 588 | 55.4% | +0.298 | +175.47 |

**26 features (V's design)**: (a) +145.81, (b) **+178.66**, (c) +161.02.

**In both feature sets the second week makes it worse** — −$6.70 on 30 features, −$17.64 on 26 —
and costs logloss (0.4994 vs 0.4984; 0.4989 vs 0.4978). verify.py, (c) vs (b): halves **+0.180 /
−0.128** sign flip, 205 discordant at 106-vs-99 **McNemar p = 0.675**, and it loses the null.

**The second week buys nothing. Adding it costs money and calibration.**

## The trap in this table, and it is a big one

(b) beats frozen v10 by **$36** with halves **+0.095 / +0.094** — the most stable pair this session —
passing costs to 5 ticks, beating the null, and winning on **7 of 8 readable days**. It fails only the
paired test, at 70 discordant, 43-vs-27, **p = 0.072**.

**That is not a better model, and it must not be relayed as one.** Checked against the shipped
artifact:

| | max abs diff |
|---|---|
| `coef` (30) | **0.000e+00** |
| `scaler_mean`, `scaler_scale` | **0.000e+00** |
| `intercept` | **0.000e+00** |

**(b) is frozen v10.** Same coefficients, same scaler, to the last bit. The single difference is the
**isotonic calibrator** — 152 knots against the shipped 116, because `r12_train.fit` uses
`GroupKFold(4)` for the inner OOF where `finalize.py` used `GroupKFold(8)`. Median |Δp| = 0.0077,
p90 0.022, and the two cross 0.5 differently on **0.511%** of rows.

So the direction call is unchanged. What changes is **which candles clear the EV threshold**: 778
fires instead of 1033, and $36 more money. **An arbitrary fitting detail in the calibrator is worth
$36 per 1,033 fires on this window.** That is not an edge to ship — it is a warning that the fire
threshold sits where calibration noise moves real money, and it deserves its own test rather than a
deployment.

**Correction to my own R-12 verdict doc:** I wrote "nine retrains, not one beats frozen v10 on total
PnL." (b) does beat it. (b) is not a retrain — it is frozen v10 recalibrated — so the sentence stands
for retrains, and I am flagging the asterisk rather than leaving it to be found.

## Caveats

- **(c) is data-starved against (a) in the way I flagged earlier, and less so than before.** (c)
  trains on week 1 plus week-2 days before the test day — 2,272 to ~4,100 candles against frozen's
  2,272 fitted with LODO. By the last test days (c) has nearly twice frozen's data and still loses.
- All three arms are evaluated on the same held-out slice with the same EV rule and grading on
  `venues.outcome`.
- Week-1 features come from `build_features.py` (offline aggTrades), week-2 from the live
  `FeatureState`. Medians line up on all the depth features; `perp_n15` differs (186 vs 89), which
  reads as a market-activity difference rather than a definition mismatch, but it is not proven.
