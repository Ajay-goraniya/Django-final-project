# EF2 — NC-17, the recreated EF. v0 (logistic walk-forward)

Zurich, 2026-09-28. READ-ONLY. **Master OFF, nothing live, nothing deployed.** London keeps fixed15.

EF-2 is ONE model of `P(win | buy THIS side at THIS ask at THIS second)` — no direction model plus a gate. So
every pass contributes two candidate rows, one per side, and the model has to learn that buying the expensive
side of a decided market is a bad trade rather than being told so by a separate rule.

## The acceptance bar (V, owner, 09-28 11:2x)

London is **not** paused and keeps fixed15 until EF-2 beats it on **profit AND execution**, same days,
walk-forward. Every arm below goes through one scoring function with one set of columns on one candidate
table, so the only thing differing between rows is the rule.

## Answer up front: no version passes, and the comparison is not the one it looks like

**1. No margin passes both columns.** Not one of the four.

**2. Execution: EF-2 wins decisively.** 89.6% sim fill against fixed15's 42.4%; no-fill 10.4% against 57.6%.

**3. Profit: it depends which "profit" means, and I am not going to pick for you.** Per $1, fixed15 wins
(+0.050 vs +0.016). In total dollars, EF-2 wins by 5× (+128.0 vs +26.5) — on 6.7× the fires, 221/day against
33/day, which is a different risk profile and a stake question, not only a model question.

**4. But fixed15's +0.050 is not a measurement.** It rests on **56 fills**, its own halves are **+0.277 /
−0.177** — they disagree in sign — and its permutation reads **0.448**. EF-2 at margin 0.02 rests on **791
fills**, halves **+0.018 / +0.013**, and V's opposite-ask flip reads **p = 0.007**. Comparing +0.050 against
+0.016 as though both were established numbers is the error; the baseline is the noisier of the two.

**5. The placebo beats the trained model.** The S=15 rule from EF_FIRE_TIME — model still picks the side, its
confidence bar dropped entirely — pays **+0.067/$1** on 615 fills, both halves positive, and is the only arm
on the board that passes cost sensitivity *and* beats the null. Fifty-two features and 1.6M training rows do
not beat "buy the model's side at the first pass where the ask is under 0.60".

**6. On V's question (5), the honest answer is "directionally yes, but it does not matter".** Ask dynamics
carry **0.113** of standardised coefficient mass against the move's **0.084** — so yes, the model leans on
the record of being picked off more than on `move_bps`. Both are dwarfed by the price itself at **1.443**.
And `p_side` **alone** scores AUC 0.8580 against the full 52-feature model's 0.8608: **the whole apparatus
adds +0.003 AUC over the p the engine already computes.**

## 1. Rows

1,606,978 candidate rows = 822,331 passes × both sides, 1,015 gamma-graded candles, 5 days, sec 15–240, 52
features (all 44 engine features as logged + `own_ask`, `opp_ask`, `d_ask_1s/5s/30s`, `dip30`, `sec`,
`p_side`). Every feature finite on 100.0% of rows. The other side's p is `1 − p`, forced by the outcome being
binary and exhaustive.

| | base rate P(this side wins) |
|---|---|
| all candidate rows | 0.4904 |
| rows that FILL | **0.4881** |
| rows that DO NOT fill | **0.5495** |

**The rows that do not fill win 6.1 pp more often.** That is adverse selection measured on the whole
candidate population rather than inferred from a fired subset. Sim fill over all candidates is 96.26%; over
fixed15's actual fires it is 42.4%. The selection destroys the fill, not the market.

## 2. Walk-forward

Day k fitted on days < k, scaler on the training rows alone, first day never scored, one fire per candle.

```
  day 09-25: train   213,594  test 451,704   AUC logistic 0.8529   stumps 0.8527
  day 09-26: train   665,298  test 472,299   AUC logistic 0.8540   stumps 0.8545
  day 09-27: train 1,137,597  test 445,563   AUC logistic 0.8741   stumps 0.8728
  day 09-28: train 1,583,160  test  23,818   AUC logistic 0.8962   stumps 0.8932
  pooled: logistic 0.8608   stumps 0.8599   the ask alone 0.8611   p_side alone 0.8580
```

The pooled AUC looks impressive and is mostly mechanical — by second 240 the ask is nearly the answer:

```
    sec  15-29   n 101,738   model 0.7187   ask alone 0.7189   p_side alone 0.7147
    sec  30-59   n 191,184   model 0.7467   ask alone 0.7469   p_side alone 0.7413
    sec  60-119  n 406,132   model 0.8237   ask alone 0.8237   p_side alone 0.8236
    sec 120-179  n 388,928   model 0.9007   ask alone 0.9018   p_side alone 0.8979
    sec 180-240  n 305,402   model 0.9274   ask alone 0.9281   p_side alone 0.9241
```

At every horizon the model, the ask alone and the engine's existing p are within 0.005 of each other. A
numpy gradient-boosted stump ensemble was run beside the logistic purely to check whether linearity was the
limit: it is not (0.8599 vs 0.8608).

## 3. The acceptance table

```
ACCEPTANCE TABLE - fixed15 vs EF-2, same candles, same fill simulator, same days
==============================================================================================================================
  arm                        fires  /day fills  fill% nofill%  slip c   win%    per$1   total$      H1      H2  permP
  fixed15 (London, live)       132    33    56  42.4%   57.6%   -0.04  42.9%   +0.050    +26.5  +0.277  -0.177  0.448  *n<60
  ----------------------------------------------------------------------------------------------------------------------------
  EF-2 margin 0.00             883   221   817  92.5%    7.5%   -0.03  65.4%   +0.013   +103.8  -0.009  +0.034  0.015
  EF-2 margin 0.02             883   221   791  89.6%   10.4%   -0.04  65.9%   +0.016   +128.0  +0.018  +0.013  0.007
  EF-2 margin 0.05             874   218   734  84.0%   16.0%   -0.02  59.4%   -0.014    -94.0  -0.024  -0.004  0.090
  EF-2 margin 0.10             791   198   715  90.4%    9.6%   -0.11  15.0%   -0.236  -1674.4  -0.213  -0.259  0.970
  ----------------------------------------------------------------------------------------------------------------------------
  S=15 placebo                 724   181   615  84.9%   15.1%   -0.27  58.0%   +0.067   +416.1  +0.078  +0.057  0.000
  raw25 (EV>=0.25)             264    66   112  42.4%   57.6%   -0.09  42.9%   +0.053    +58.0  +0.183  -0.078  0.235

  VERDICT against the owner's bar - a version must win PROFIT and EXECUTION, not one of them:
    margin 0.00: profit lose (per$1 +0.013 vs +0.050, total +103.8 vs +26.5)   execution lose (fill 92.5% vs 42.4%, slip -0.03c vs -0.04c)   -> does not pass
    margin 0.02: profit lose (per$1 +0.016 vs +0.050, total +128.0 vs +26.5)   execution WIN  (fill 89.6% vs 42.4%, slip -0.04c vs -0.04c)   -> does not pass
    margin 0.05: profit lose (per$1 -0.014 vs +0.050, total -94.0 vs +26.5)   execution lose (fill 84.0% vs 42.4%, slip -0.02c vs -0.04c)   -> does not pass
    margin 0.10: profit lose (per$1 -0.236 vs +0.050, total -1674.4 vs +26.5)   execution WIN  (fill 90.4% vs 42.4%, slip -0.11c vs -0.04c)   -> does not pass

```

`slip c` is the fill price minus the QUOTED ask, in cents. The decision is taken on the quoted ask; the
economics are settled at the sim fill price (V, 09-28: "yes, exactly").

```
  LOOKAHEAD VARIANT (decision taken at the fill price) - to size that choice, not to be quoted:
  arm                        fires  /day fills  fill% nofill%  slip c   win%    per$1   total$      H1      H2  permP
  lookahead 0.00               883   221   883 100.0%    0.0%   -0.40  63.5%   -0.008    -65.7  -0.031  +0.015  0.040
  lookahead 0.02               883   221   883 100.0%    0.0%   -0.74  63.0%   -0.020   -172.8  -0.025  -0.015  0.077
  lookahead 0.05               883   221   883 100.0%    0.0%   -1.92  60.1%   +0.009    +71.5  +0.016  +0.002  0.077
  lookahead 0.10               877   219   877 100.0%    0.0%   -5.65  44.0%   -0.152  -1319.3  -0.137  -0.168  0.757

```

The lookahead variant is reported only to size that choice. Deciding at the fill price buys a 100% fill by
construction and −0.40c to −5.65c of slippage, and per $1 gets *worse*, so the sound version is not being
handicapped by the honest reading.

## 4. verify.py on the two cells that qualified

Positive in both halves with n ≥ 60 fills: EF-2 at margin 0.02, and the S=15 placebo. **fixed15 itself does
not qualify** — halves +0.277 / −0.177 — which is the first thing to say about any comparison against it.

```

### EF-2 margin 0.02: 883 fires, 791 fills, per$1 +0.0158, win 65.9%
    V's control - flip priced at the OPPOSITE real ask: p = 0.007
    sweep over the margin (0.0, 0.02, 0.05, 0.1) -> +0.013 +0.016 -0.014 -0.236
==============================================================================
FINDING: EF-2 margin 0.02   (+0.016/fire, n=791)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms; DECISION on the quoted ask
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 17}
  [PASS] both halves          h1 +0.018 / h2 +0.013
  [FAIL] permutation control  real +0.016 vs permuted mean +0.020 (p95 +0.054), p=0.585 over 400 draws
  [FAIL] sweep shape          NON-monotone: [ 0.013  0.016 -0.014 -0.236]  <- peaks at an interior point, classic overfit
  [FAIL] cost sensitivity     +0c:+0.016 +0c:+0.008 +1c:+0.000 +2c:-0.015  <- dies once you pay realistically
  [FAIL] beats the null       mine +0.016 vs fixed15 (the live London rule) +0.050
  [FAIL] paired test          n=49, agree on 8, discordant 41 (24 vs 17), edge +0.143, exact McNemar p=0.349
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, cost sensitivity, beats the null, paired test


### S=15 placebo: 724 fires, 615 fills, per$1 +0.0675, win 58.0%
    V's control - flip priced at the OPPOSITE real ask: p = 0.000
==============================================================================
FINDING: S=15 placebo   (+0.067/fire, n=615)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms; DECISION on the quoted ask
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 10}
  [PASS] both halves          h1 +0.078 / h2 +0.057
  [FAIL] permutation control  real +0.067 vs permuted mean +0.067 (p95 +0.067), p=1.000 over 400 draws
  [PASS] cost sensitivity     +0c:+0.067 +0c:+0.058 +1c:+0.048 +2c:+0.029
  [PASS] beats the null       mine +0.067 vs fixed15 (the live London rule) +0.050
  [FAIL] paired test          n=49, agree on 39, discordant 10 (7 vs 3), edge +0.082, exact McNemar p=0.344
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, paired test

```

**Both NOT A FINDING.** EF-2 0.02 fails on permutation (p=0.585), a non-monotone margin sweep, cost
sensitivity (dies by +2c), the null, and the paired test. The placebo fails on a degenerate permutation
(p=1.000 — with no p bar there is no selection to shuffle) and the paired test, but passes cost sensitivity
and beats the null.

The paired numbers are worth reading directly. EF-2 and fixed15 share 49 candles and **agree on only 8 of
them** — 41 discordant. They are not two settings of one rule, they are two different strategies, and a
per-$1 comparison between them is closer to a comparison of two populations than of two methods.

## 5. Feature importance

```
FEATURE IMPORTANCE - |standardised coefficient|, mean over the walk-forward fits
==============================================================================================================================
     1. own_ask          0.6678  <- the price
     2. opp_ask          0.5924  <- the price
     3. p_side           0.3674  <- the engine p
     4. ref_open         0.2148
     5. ref_now          0.1121
     6. _price           0.1025
     7. bn_line_now      0.1010
     8. ref_inst         0.0918
     9. bn_line_open     0.0621
    10. _ask_dn          0.0615  <- the price
    11. _ask_up          0.0571  <- the price
    12. move_bps         0.0556  <- the move
    13. d_ask_30s        0.0555  <- ASK DYNAMICS
    14. ref_gap_bps      0.0470
    15. lv               0.0405  <- the price
    16. mv_x_sec         0.0281  <- the move
    17. ref_move_bps     0.0273
    18. lv_x_sec         0.0255

  block totals - V's question is whether the first line beats the third:
    ask dynamics (d1,d5,d30,dip30)     0.1128
    the price (ask/lv/p_venue)         1.4430
    the move (move_bps,mv_x_sec)       0.0837
    the engine model p (p_side)        0.3674
```

## What I would put to the owner

EF-2 does exactly what it was asked to do — one model, both sides, no separate gate — and it produces a
lane that fires 6.7× as often, fills at 90% instead of 42%, and wins 66% of its fills instead of 43%. On
execution it is not close. On profit per dollar it loses to a baseline whose own halves disagree.

The finding underneath is not about EF-2's architecture. It is that **the price already contains the
answer**: the ask alone scores 0.8611, the engine's existing p scores 0.8580, and 52 features and 1.6M rows
score 0.8608. A model built on those inputs cannot do much more than restate the market, and the arm that
does best on this board is the one that stops trying to — the placebo.

That does not make EF-2 worthless. Firing 221 times a day at a 90% fill is a genuinely different machine
from firing 33 times at 42%, and if the owner's objective is total dollars rather than return on deployed
capital, the table already favours it. But it does not clear the bar as written, and I am not going to
present a cell that fails five gates as though it did.

---

# v1 — gradient boosting (sklearn HistGradientBoosting)

Neither lightgbm nor sklearn was on this box. sklearn 1.9.1 went into a **separate** venv at
`/home/ubuntu/pm_ml_venv`; the engine's interpreter and its numpy were checked afterwards and are untouched.

**v1 is worse than v0 on everything.** Pooled AUC **0.8386** against the logistic's 0.8608, and worse on every
day (0.8177 / 0.8402 / 0.8656 / 0.8839 against 0.8529 / 0.8540 / 0.8741 / 0.8962). It is also worse than
`p_side` alone (0.8580) at every second bucket. Its best margin, 0.02, pays +0.002/$1 and +19.6 total — it
loses to fixed15 on both profit measures, where v0 at least won on total dollars. No margin passes.

## A correction to what I told V about feature importance

In the v0 report I said ask dynamics beat the move, 0.113 against 0.084 of standardised coefficient mass, and
called it "directionally yes" on V's question. **That does not survive the better measurement.** v1 gives
PERMUTATION importance — how much AUC is lost when a column is shuffled — which is the right instrument,
because a coefficient can be large purely from collinearity with another feature. It says:

```
    block ask dynamics   -0.0008
    block the price      +0.0969
    block the move       -0.0003
    block the engine p   +0.0526
```

Ask dynamics and the move are both **negative**: shuffling them very slightly *improves* AUC, which is what
noise looks like. So the honest answer to "does the model lean on ask dynamics rather than move_bps" is
**no — it leans on neither.** It leans on the price and on the p the engine already computes. I withdraw the
v0 phrasing.

---

# The London table: a failure that AUC would not have shown

London's final-test table carries 35 feature keys; the model has 52. The exported scorer imputes a missing
feature at its training mean. Running that on Zurich's own rows:

| | AUC | win% | per $1 | total $ |
|---|---|---|---|---|
| full 52 keys, margin 0.02 | 0.8608 | 65.9% | **+0.016** | +128.0 |
| **imputed to London's 35** | 0.8573 | **32.5%** | **−0.076** | **−573.4** |
| imputed, with dip30 added back | 0.8576 | 30.7% | −0.102 | −774.2 |

**AUC moved by 0.0034. The win rate halved and the sign of the money flipped.** AUC is rank-based and
survives imputation; the *decision* is not a ranking, it is the calibrated **level** of `p_win` against the
price, and the 8 imputed features carry **34.2%** of the coefficient mass. Move the level and the EV rule
selects the wrong trades.

This is the ETH_SOL_DIAG failure again — the ranking transfers, the level does not — arriving through
imputation instead of through a different coin. Had London scored its 654 attempts with the imputed model it
would have produced a confident negative, and it would have read as EF-2 failing rather than as the
imputation failing. Adding `dip30` back makes it worse, so this is not about the selected-dip feature.

## The fix: train on what London will have

Not a better imputer — the right feature list. Refitting the whole walk-forward on London's 44 available
features, same rows and same protocol:

```
  day 09-25 AUC 0.8532   day 09-26 0.8540   day 09-27 0.8741   day 09-28 0.8961   pooled 0.8609
```

**0.8609 on 44 features against 0.8608 on 52.** The eight dropped features add nothing when the model is
properly calibrated on the rest, and the entire −0.076 disaster was an artefact of imputing them. The
acceptance table on the refit is the best EF-2 variant so far:

| arm | fires/day | fill% | win% | per $1 | total $ | H1 / H2 | permP |
|---|---|---|---|---|---|---|---|
| fixed15 | 33 | 42.4% | 42.9% | +0.050 | +26.5 | +0.277 / −0.177 | 0.448 |
| **EF-2 London refit, m=0.02** | 220 | 89.8% | **66.0%** | **+0.020** | **+161.1** | +0.028 / +0.012 | **0.007** |

It still does not pass — per $1 is +0.020 against fixed15's +0.050 — but it is the model London should
actually run, and it is exported as `learner/v12_2/ef2/ef2_model_london.json` with the reason written into
the file so it cannot be confused with the 52-feature object.

---

# v0b — TIMING ONLY, the survivor

V, 09-28: *"the ask alone matches any model at every horizon... The only survivor twice now is TIMING."*

Fire at the **first** pass with `sec >= S`, on the **model's side**, buy at the quoted ask if `ask <= cap`.
One fire per candle. Nothing is fitted, so no day has to be held out and all **5** days are used — fixed15
included, which makes this comparison like-for-like on 5 days rather than 4. v0b is **not** model-free: the
model still picks the side, and that is its entire remaining content.

## The grid, 16 cells

The full table is in the run output. The cell that stands out:

| | fires/day | fill% | win% | per $1 | total $ | H1 / H2 | flipP | +1c | +2c | +3c |
|---|---|---|---|---|---|---|---|---|---|---|
| **S=15 cap=0.60** | 168 | **85.0%** | 57.4% | **+0.057** | **+410.0** | +0.039 / +0.076 | **0.000** | +0.038 | +0.019 | +0.001 |
| fixed15, same 5 days | 36 | 41.0% | 46.6% | +0.104 | +73.8 | +0.327 / **−0.113** | 0.350 | +0.075 | +0.048 | +0.023 |

Execution is not close — 85% fill against 41%. Total dollars is 5.6× fixed15. Per $1 it loses, +0.057 against
+0.104. And it is the only cell in the grid that survives a **+3c** haircut while staying positive in both
halves with a flip control at 0.000.

## But it is not rain or sun, and neither is the baseline

```
  cell                     09-24       09-25       09-26       09-27       09-28  days +ve
  S=15 cap=0.60           -0.006      +0.097      -0.011      +0.126      -0.116     2/5
  S=15 cap=0.65           +0.016      -0.000      +0.014      +0.047      +0.170     4/5
  S=25 cap=0.60           +0.032      +0.035      +0.043      +0.007      -0.338     4/5
  fixed15                 +0.282      +0.324      -0.020      -0.229      -0.477     2/5
```

**The best cell is positive on 2 days of 5.** The cells that are positive on 4 of 5 pay +0.022 and +0.023 —
a third of the headline. And fixed15 is *also* 2 of 5, with a +0.28/+0.32 pair carrying it. Both rules are
carried by a couple of days, which is the more important fact about this table than either mean.

## Does the venue catch up to the model? No.

V's mechanism question, and the answer is the clearest thing in this document. For each candle, take the side
the model favours at the first pass at sec >= 15 and follow **that same side's** ask forward:

```
             n   ask@15   ask@45   ask@120   d15->45   d15->120  % risen@45  % risen@120
  all     1004    0.619    0.619     0.629     -0.05      +0.92       53.9%        58.7%
  won      644    0.632    0.657     0.746     +2.56     +11.46       62.1%        76.2%
  lost     360    0.597    0.550     0.418     -4.71     -17.92       39.2%        27.2%
```

Over all candles the model-side ask moves **+0.9c in 105 seconds** — flat. It rises 11.5c on the candles that
win and falls 17.9c on the candles that lose, which is simply the price tracking the outcome; every price does
that. **If the model led the crowd, the ask would rise on the losers too**, because the crowd would be moving
toward the model's side before the outcome was known. It does not. There is no lead to harvest, and the rule
is not buying ahead of the venue.

## verify.py

```
  [PASS] grading provenance     gamma_btc5 vs gamma_btc5b disagree on 0/140
  [PASS] quote age              at-or-after, decision on the quoted ask
  [PASS] sample size            fires 839 / filled 713
  [FAIL] sample size            under 60: {'09-28': 10}
  [PASS] both halves            h1 +0.039 / h2 +0.076
  [FAIL] permutation control    p=1.000 - degenerate, there is no p bar to shuffle
  [FAIL] sweep shape            cap: [-0.041 +0.019 +0.057 +0.022] peaks at an interior point
  [PASS] sweep shape            S: [+0.057 +0.046 +0.023 +0.009] MONOTONE
  [PASS] cost sensitivity       +0c +0.057  +1c +0.038  +2c +0.019  +3c +0.001
  [FAIL] beats the null         +0.057 vs fixed15 +0.104
  [FAIL] paired test            n=64, agree 48, discordant 16, McNemar p=0.454
  VERDICT: NOT A FINDING
```

**The one gate that passes and matters: the S sweep is monotone.** +0.057, +0.046, +0.023, +0.009 as S goes
15 → 20 → 25 → 30. Earlier is smoothly better, which is exactly what a real timing effect looks like and is
the strongest single piece of evidence any arm has produced in this document. The cap sweep is not monotone,
it peaks at the value that was chosen.

## Where v0b leaves it

Timing is real as a **direction** — the monotone S sweep is hard to explain away. It is not established as a
**level**: the headline cell is two good days out of five, the mechanism V proposed is measurably absent, and
it loses the per-$1 comparison to a baseline that is itself two good days out of five.

The comparison the owner's bar asks for cannot really be settled on 5 days when both sides of it are carried
by two of them. What would settle it is more days of the same tape, not another model.

## Files

- `ef2_rows.py` — the candidate table
- `ef2_fit.py` / `ef2_model.py` — the walk-forward fits, cached
- `ef2_report.py` — the acceptance table, lookahead variant, importance
- `ef2_verify.py` — verify.py on the qualifying cells
- `ef2_london.py` — what the model loses on London's 35-key table
- `ef2_export.py` → `learner/v12_2/ef2/` — the exported model and scorer

---

# v0 ACCEPTANCE DETAIL — and the conflict it exposes

V, 09-28 12:2x, relaying the owner: 5m only, EF-2 v0 is the candidate, give it the detail the bar needs.

## The conflict, first, because it may decide the whole thing

**v0 is the early-fire arm.** At margin 0.02 it fires at **second 15 on 89.6% of candles** — fire-second
p10/p50/p90 = 15/15/31. At margin 0.00 it is 96.4% at or before second 30. fixed15 fires at p50 second **123**
and is early on 3.8%.

And that is where its money is:

```
  arm       sec p10  p50  p90   <=30s        15-30s          30-60s         60-120s        120-180s
  m=0.02        15   15   31    89.6%   +0.031 (713)    -0.066 (59)    -0.247 (16)     -0.466 (3)
  fixed15       45  123  202     3.8%   -0.300 (3)      -0.147 (9)     -0.043 (13)     +0.272 (24)
```

Positive in the 15–30s bucket on 713 fills, **negative in every later bucket**. The owner ruled early fires
out at 11:5x as "guess and gambling", and v0b was dropped on that basis. v0 at margin 0.02 is the same thing
reached by a different route. The 24 h shadow is running as instructed, but whether v0 survives the owner's
own ruling is his call and should be made before anything is read into it.

## (1) Per day — the one genuinely good result

| arm | 09-25 | 09-26 | 09-27 | 09-28 | days +ve |
|---|---|---|---|---|---|
| m=0.00 | −0.011 | −0.025 | +0.060 | +0.207 | 2/4 |
| **m=0.02** | **+0.008** | **+0.019** | **+0.007** | **+0.233** | **4/4** |
| m=0.03 | −0.009 | −0.012 | +0.056 | +0.180 | 2/4 |
| m=0.05 | −0.070 | +0.066 | −0.043 | +0.027 | 2/4 |
| fixed15 | +0.324 | −0.020 | −0.229 | −0.477 | **1/4** |

m=0.02 is the only arm positive on every day. fixed15's entire +0.050 is one day. The caveat that belongs
next to it: 09-28 is a partial day (17 fills, +0.233); the three full days are +0.008 / +0.019 / +0.007.

## (2) Cost sensitivity at London's real bound

London caps at ask + 1 tick, so **+1c is the bound that matters**.

| arm | +0.5c | +1.0c | +1.5c |
|---|---|---|---|
| m=0.02 | +0.008 (3/4 days) | **+0.000 (2/4)** | −0.007 (1/4) |
| m=0.00 | +0.005 | −0.003 | −0.010 |
| m=0.03 | +0.008 | −0.000 | −0.008 |
| m=0.05 | −0.026 | −0.038 | −0.049 |
| fixed15 | +0.035 (1/4) | **+0.021 (1/4)** | +0.008 (1/4) |

**At +1c, v0 m=0.02 is exactly break-even.** fixed15 is +0.021 but on one day of four. Neither arm is money
anyone should bet on at the realistic cost.

## (4) They are opposite trades

v0 buys at ask p50 **0.62** and earns in the 0.55–0.70 bucket (+0.039 on 518 fills). fixed15 buys at p50
**0.43**. v0 buys the favourite, fixed15 buys the underdog — which is why they share 49 candles and agree on
8 of them.

## (5) Calibration — the healthiest number in the document

Mean p_win **0.672** against a realised **0.659**: over-confident by **1.3 pp**. After ETH/SOL's 17 pp and
the London imputation's inversion, a level that is right to within a point and a half is worth noting.

But the deciles do not order returns: gaps run −0.138 to +0.113, and per $1 by decile is −0.186, +0.274,
+0.021, +0.044, −0.092, +0.091, +0.054, −0.103, +0.093, −0.036. The level is right in aggregate; the ranking
inside it does not convert into ordered money.

## The shadow

`/home/ubuntu/pm_ef2shadow/ef2_shadow.py`, started 12:32:01, PAPER only, own sqlite, flock keep-alive, **all
four margins** so no cell is chosen in advance. It tails the engine's `decide_log` read-only, so it and the
offline replay see byte-identical inputs. No order path: standard library only, no `poly_live`, no
credentials, master never read or written.

First live candles reproduce the replay exactly — m=0.02 firing at mean second **16.0** at mean ask **0.637**,
against the replay's second 15 and ask p50 0.62.

Two of my own defects showed up in it and are recorded rather than quietly fixed: the London imputation change
made `Scorer.score` return `(p, info)` while the shadow was written against the old float signature, which its
guard loop caught and logged instead of dying; and the follow-up patch that was meant to log an imputed-feature
count was a **silent `str.replace` no-op** with the wrong indentation — the second one today. It has been
replaced with a count of candidates *skipped* for missing features, which is the informative number anyway
since a missing feature skips the candidate before scoring, and every replacement in that patch now asserts
its target was found.

---

# VERDICT — EF-2 is out

V, 09-28 12:4x, relaying the owner: the 11:5x ruling stands — early fires are gambling — so **EF-2 v0 is
OUT**. Recorded in NC-17. The shadow and its keep-alive are stopped.

It is out on the owner's judgement about *what kind of trade he is willing to make*, not because the numbers
were bad. Both facts belong in the record:

- v0 at margin 0.02 was the only arm in this entire document positive on **4 of 4 days**, at 89.6% sim fill
  against fixed15's 42.4%, with calibration right to 1.3 pp.
- **89.6% of its fires are at second 15**, and every later second bucket is negative. It is an early-fire
  strategy whatever else it is, and the owner has ruled that out.

The measurement that made the call possible was section (3) of the acceptance detail — the fire-second
distribution — which V asked for precisely because it decides this. Without it the 4-of-4 per-day stability
would have read as a candidate worth arming.

What EF-2 leaves behind, which is not nothing:

| result | where |
|---|---|
| the ask alone scores AUC 0.8611, the engine's p 0.8580, a 52-feature model 0.8608 | v0 |
| trees are worse than linear, so capacity was never the constraint | v1 |
| ask dynamics contribute **−0.0008** by permutation importance — the record of being picked off is not information | v1 |
| imputing 34% of coefficient mass keeps AUC and **inverts** the money | london44 |
| the 15m market is not softer — the same market on a longer clock | EF2_15M |
| the rows that do not fill win **6.1 pp more often** than the rows that do | ef2_rows |

`learner/v12_2/ef2/ef2_model_london.json` (london44) stays exported for London's own scoring of its 654
attempts. It is a scorer, not a config, and it arms nothing.

---

# After second 200 — the owner's direct question, answered twice

Owner, 09-28 12:5x: *"What's the profit and accuracy in trades taken after 200 s in the candle, and what's the
worst drawdown?"* Two independent reads, and they disagree. Both are here because the disagreement is the
answer.

```
A. stable_ef fire set: 543 fires, 10 days, venue-graded

  --- A / FIXED ---
  cut             n   win%|  paper$1   paper$    pDD$|   LON$1     LON$  lonDD$| lose-run  days+
  ALL           248  55.6%|   +0.089   +228.4   233.4|  -0.065    -97.5   196.5|        7   6/10
  sec < 200     206  52.9%|   +0.021    +44.7   212.9|  -0.124   -157.2   200.3|        8   5/10
  sec >= 180     67  65.7%|   +0.313   +217.2    56.9|  +0.154    +61.6    58.5|        4   7/10
  sec >= 200     42  69.0%|   +0.422   +183.6    46.9|  +0.260    +65.1    39.7|        4    9/9  *n<60
  sec >= 220     19  57.9%|   +0.210    +41.5    30.0|  +0.054     +6.3    31.5|        3    7/8  *n<60

  --- A / RAW ---
  cut             n   win%|  paper$1   paper$    pDD$|   LON$1     LON$  lonDD$| lose-run  days+
  ALL           295  49.2%|   +0.045   +137.0   258.4|  -0.116   -210.8   271.4|        7   5/10
  sec < 200     254  46.9%|   -0.005    -12.2   216.5|  -0.166   -260.8   298.6|        7   5/10
  sec >= 180     70  55.7%|   +0.192   +139.5    76.0|  +0.019     +8.0    74.0|        6   8/10
  sec >= 200     41  63.4%|   +0.350   +149.2    60.0|  +0.183    +45.3    46.3|        6    8/9  *n<60
  sec >= 220     16  56.2%|   +0.220    +36.6    40.0|  +0.049     +4.9    32.5|        4    6/8  *n<60

B. EF_FIRE_TIME decide_log baseline (fixed15, ef_persist FAK): 195 fires, 5 days

  --- B / fixed15, SIM FILLS ONLY (a no-fill is not a trade) ---
  cut          fires fills   win%    per$1   total$     DD$ lose-run  days+
  ALL            195    82  43.9%   +0.056    +47.8    85.3        7    2/5
  sec < 200      176    78  44.9%   +0.078    +63.2    75.3        7    2/5
  sec >= 180      36    13  38.5%   -0.135    -18.2    43.8        4    1/4  *n<60
  sec >= 200      19     4  25.0%   -0.372    -15.4    30.0        3    1/3  *n<60
  sec >= 220       8     2   0.0%   -0.968    -20.0    20.0        2    0/2  *n<60
```

## They disagree, and the reason is the FILL

Read A says late fires are the good ones (FIXED sec ≥ 200: 69.0% win, +0.422/$1 paper, 9 of 9 days positive).
Read B says they are the worst (sec ≥ 200: 25.0% win, −0.372/$1).

The whole gap is **whether a late fire fills**. B simulates each fire's FAK explicitly and measures the fill
rate collapsing with the second:

```
  fires -> fills     ALL 195->82 (42%)   sec<200 176->78 (44%)   sec>=180 36->13 (36%)
                     sec>=200 19->4 (21%)   sec>=220 8->2 (25%)
```

A's London column applies P(fill|win) 54.1% / P(fill|lose) 65.0% — **flat, with no dependence on the second
at all**. So A prices late fires as though they fill like early ones, and B's direct measurement says they do
not: 21% against 44%.

That makes A's London figure for sec ≥ 200 optimistic by construction, and it is the column the owner would
be trading on.

## What I would say plainly

The paper numbers after 200 s are good and consistent — 69% right, +0.42 per $1, nine of nine days positive,
worst drawdown $46.9 at a $10 stake, longest losing run 4. If those fills were real it would be the best
thing on this box.

They are 42 fires, under the 60 bar, and the one read that models the fill second-by-second says only about a
fifth of them land, and that the ones that do lose. Two samples of 42 and 4, pointing opposite ways, on a
question that turns on a fill model neither of them measures well.

The honest state: **not established either way, and the cheap thing that would settle it is London reporting
its real fill rate for attempts after second 200** — it has the only real fills anyone has.

---

# The SECOND TRIGGER — the owner's design, tested

Owner, 09-28 13:0x: keep the current EF, add a second trigger in the same candle that can only fire after the
first, at any time after it. His reasoning: London's real 60–120 s fires re-cross the line 65% of the time and
then win 25%, so the second trigger is *"a brain that knows the move is wrong and reverses"*.

First fire = the current rule exactly. Second fire = the first strictly later pass clearing the same bar, in
three variants: **A** either side, **B** opposite only (the reversal), **C** same side only (the add). Fills
are ef_persist's per-pass simulator, so the fill collapse with the second is inside every number rather than
applied as a flat rate. 1,015 candles, 5 days, venue labels.

```
decide_log both-sides candidates: 1015 candles, 1,606,978 rows, days ['09-24', '09-25', '09-26', '09-27', '09-28']
Fills are the ef_persist per-pass simulator, so the fill collapse with the second is inside every number below.

============================================================================================================================================
raw25: FIRST FIRE (the current rule) - 326 candles, 138 fills (42.3%), win 44.2%, per$1 +0.079, total +107.3$, DD 98.4$, longest losing run 5
============================================================================================================================================
  variant                     cands  fill%   win%   2nd$1     2nd$   CANDLE$   vs 1st     DD$  run      H1      H2
  A either side                 278  64.7%  34.4%  -0.154   -275.4    -179.2   -275.4   411.3   13  -0.021  -0.287
  B opposite only (reversal)     38  52.6%   5.0%  -0.795   -158.7     -84.0   -158.7   138.0    6  -0.590  -1.000  *n<60
  C same side only (add)        260  65.0%  36.7%  -0.111   -187.4    -103.0   -187.4   313.1   15  -0.038  -0.183

  per-day CANDLE $ (both legs) minus first-only, by variant:
    variant                          09-24       09-25       09-26       09-27       09-28
    A either                         +57.4      -105.8      -155.4       -43.5       -28.1
    B opposite                       -10.0        +1.3       -90.0       -60.0           -
    C same                           +57.4      -127.7       -85.4        -3.5       -28.1

  2nd fire SPLIT by FIRST-fire second (rows) x 2nd-fire second (cols), variant B (reversal):
    1st sec             2nd 15-120         2nd 120-200         2nd 200-241
    15-120            -1.000 (2/6)        +0.032 (4/9)        -1.000 (4/8)
    120-200                      -        -1.000 (2/4)       -1.000 (7/10)
    200-241                      -                   -        -1.000 (1/1)

  WHERE THE FIRST FIRE LOST - did a qualifying OPPOSITE-side pass appear later?
    first fire FILLED and LOST   n   77  opposite pass appeared on    4 (  5.2%)  its ask p10/p50/p90 0.19/0.44/0.57  sec p50 194  it would fill 0.0%
    first fire FILLED and WON    n   61  opposite pass appeared on    9 ( 14.8%)  its ask p10/p50/p90 0.04/0.09/0.49  sec p50 226  it would fill 55.6%

============================================================================================================================================
fixed15: FIRST FIRE (the current rule) - 178 candles, 73 fills (41.0%), win 46.6%, per$1 +0.104, total +73.8$, DD 75.8$, longest losing run 6
============================================================================================================================================
  variant                     cands  fill%   win%   2nd$1     2nd$   CANDLE$   vs 1st     DD$  run      H1      H2
  A either side                 131  55.7%  45.2%  +0.020    +14.2    +111.2    +14.2   145.9    8  +0.193  -0.147
  B opposite only (reversal)     10  60.0%  50.0%  +0.017     +1.1     -18.9     +1.1    22.9    2  +0.192  -0.157  *n<60
  C same side only (add)        125  55.2%  44.9%  +0.011     +7.1    +124.1     +7.1   135.9    8  +0.195  -0.167

  per-day CANDLE $ (both legs) minus first-only, by variant:
    variant                          09-24       09-25       09-26       09-27       09-28
    A either                          -0.1       +62.8       -13.3        +4.9       -40.0
    B opposite                        -6.0       +17.1        +0.0       -10.0           -
    C same                            -0.1       +45.7       -13.3       +14.9       -40.0

  2nd fire SPLIT by FIRST-fire second (rows) x 2nd-fire second (cols), variant B (reversal):
    1st sec             2nd 15-120         2nd 120-200         2nd 200-241
    15-120            -0.368 (4/4)          +nan (0/2)                   -
    120-200                      -        +0.399 (1/2)        +1.187 (1/2)
    200-241                      -                   -                   -

  WHERE THE FIRST FIRE LOST - did a qualifying OPPOSITE-side pass appear later?
    first fire FILLED and LOST   n   39  opposite pass appeared on    2 (  5.1%)  its ask p10/p50/p90 0.38/0.41/0.44  sec p50 148  it would fill 100.0%
    first fire FILLED and WON    n   34  no opposite pass

```

## The answer: the reversal fires when you were RIGHT, and is absent when you were WRONG

This is the whole result, and it is the exact inverse of what the design needs.

| arm | first fire FILLED and **LOST** | first fire FILLED and **WON** |
|---|---|---|
| raw25 | qualifying opposite pass on **4 of 77 (5.2%)**, and those 4 would fill **0.0%** | on **9 of 61 (14.8%)**, filling **55.6%** |
| fixed15 | on **2 of 39 (5.1%)** | **none at all** |

A "brain that knows the move is wrong" has to appear *when the move is wrong*. On raw25 it appears three times
more often when the move was **right**, and on the losing candles — the ones it exists for — it appears on one
in twenty and would not have filled once.

**Why, mechanically:** the second trigger requires the opposite side to clear the same EV bar on *its own* p,
which is 1 − p and therefore usually below 0.5. The only way that clears is if the opposite ask has become
very cheap — and an ask becomes cheap precisely when that side is losing. On raw25's winning candles the
qualifying opposite ask has a median of **0.09**. That is not a reversal signal, it is a lottery ticket on the
side that is already dead, and raw25's B arm wins **5.0%** of the time accordingly.

## What it costs

| arm | first only | +A either | +B reversal | +C add |
|---|---|---|---|---|
| raw25 total $ | **+107.3** | −179.2 | −84.0 | −103.0 |
| raw25 drawdown $ | **98.4** | 411.3 | 138.0 | 313.1 |
| raw25 longest losing run | **5** | 13 | 6 | 15 |
| fixed15 total $ | **+73.8** | +111.2 | −18.9 | +124.1 |
| fixed15 drawdown $ | **75.8** | 145.9 | 22.9 | 135.9 |

On raw25 every variant turns a profit into a loss and multiplies the drawdown up to 4×. On fixed15 the two
non-reversal variants add a little (+$14.2 and +$7.1 of second-leg money) while roughly doubling the drawdown
— and their halves flip sign, +0.193 / −0.147.

The reversal itself is also simply **rare**: 38 candles on raw25 and **10 on fixed15** across five days, two a
day, which is not a mechanism anyone could lean on even if it worked.

## What I would say to the owner

The premise is sound and the implementation cannot express it. London's 65% re-cross is a real observation
about the *price*, but "the opposite side clears the same EV bar" is not the same event — it fires on
cheapness, not on the move being wrong, and cheapness arrives when you are winning.

If he wants the reversal tested properly, the second trigger needs its own condition — something like *the
reference has re-crossed the opening line since the first fire* — not a re-run of the entry rule on the other
side. That is a different test and I have not run it.

---

# The reversal on its OWN condition — the reference re-crosses the line

V, 09-28 13:2x, confirming the owner's intent. The previous test re-ran the entry rule on the other side,
which fires on cheapness. This one fires on what he actually means: **the settlement reference has crossed
back through the opening line**, so the move that justified the first leg is now wrong.

Trigger: the first second after the first fire at which `ref_px` is on the other side of the candle's TWAP60
opening line from our leg, and has been there for **K consecutive seconds** (K = 0, 2, 5, 10), all K seconds
strictly before the trigger. Two actions: **(i)** buy the opposite side at its ask with the ef_persist FAK
fill, **(ii)** sell the first leg at its bid, priced as `1 − opposite ask` since the two tokens are
complements, with the 0.07·sh·p·(1−p) fee charged on the exit as well as the entry.

```
candles 1015, days ['09-24', '09-25', '09-26', '09-27', '09-28']; opening line from the Chainlink ref on 1015 of them; ref seconds held 490,244

======================================================================================================================================================
raw25: first fire on 326 candles with a line, 138 fills, total +107.3$, DD 98.4$, run 5
======================================================================================================================================================
  K / action                    trig  fill% win/save   leg$1     leg$   CANDLE$   vs 1st    DD$  run      H1      H2  oppAsk
  K=0 i BUY opposite             300  96.2%    60.0%  -0.030    -38.9     -22.4    -37.0   92.0    5  -0.158  +0.094    0.56
  K=0 ii SELL first leg          300 100.0%    59.2%  -0.109   -141.5    -124.9   -139.5  127.2   29  -0.330  +0.112    0.56
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  K=2 i BUY opposite             298  95.3%    59.3%  -0.036    -45.0     -18.1    -42.7   88.3    5  -0.180  +0.104    0.56
  K=2 ii SELL first leg          298 100.0%    58.9%  -0.109   -140.1    -113.1   -137.7  115.4   28  -0.305  +0.085    0.56
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  K=5 i BUY opposite             292  94.5%    59.5%  -0.039    -48.3     -37.2    -46.6   93.4    5  -0.205  +0.122    0.57
  K=5 ii SELL first leg          292 100.0%    59.4%  -0.102   -130.1    -119.1   -128.5  121.3   28  -0.312  +0.109    0.57
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  K=10 i BUY opposite            283  96.1%    60.7%  -0.020    -25.2     -26.5    -24.0   79.1    5  -0.198  +0.157    0.57
  K=10 ii SELL first leg         283 100.0%    59.8%  -0.098   -125.0    -126.2   -123.7  128.5   28  -0.347  +0.146    0.57
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  NULL at K=2: the opposite ask AT THE TRIGGER is p10 0.43 p50 0.56 p90 0.67; on candles where the first leg went on to LOSE it is p50 0.58, where it WON p50 0.55
  SPLIT by first-fire second, K=2, action (i) buy opposite:
    1st 15-120: n 184  opp win  54.3%  per$1  -0.043  opp ask p50 0.56
    1st 120-200: n  76  opp win  55.3%  per$1  -0.079  opp ask p50 0.60
    1st 200-241: n  19  opp win  42.1%  per$1  -0.088  opp ask p50 0.52  *n<60

======================================================================================================================================================
fixed15: first fire on 178 candles with a line, 73 fills, total +73.8$, DD 75.8$, run 6
======================================================================================================================================================
  K / action                    trig  fill% win/save   leg$1     leg$   CANDLE$   vs 1st    DD$  run      H1      H2  oppAsk
  K=0 i BUY opposite             149  96.7%    62.1%  +0.016     +9.5      +6.8    +11.4   67.6    6  -0.098  +0.131    0.55  *n<60
  K=0 ii SELL first leg          149 100.0%    61.7%  -0.105    -62.8     -65.5    -60.9   67.5   20  -0.340  +0.131    0.55
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  K=2 i BUY opposite             147  96.6%    61.4%  -0.015     -8.5      -1.0     -6.3   64.7    6  -0.119  +0.085    0.56  *n<60
  K=2 ii SELL first leg          147 100.0%    61.0%  -0.121    -71.1     -63.6    -68.9   65.5   19  -0.323  +0.075    0.56  *n<60
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  K=5 i BUY opposite             145  96.6%    60.7%  -0.011     -6.6     +11.3     -4.0   54.3    6  -0.110  +0.087    0.56  *n<60
  K=5 ii SELL first leg          145 100.0%    60.3%  -0.117    -68.0     -50.1    -65.4   52.0   18  -0.309  +0.075    0.56  *n<60
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  K=10 i BUY opposite            138  96.5%    60.0%  -0.030    -17.2     +11.0    -14.4   55.4    6  -0.155  +0.088    0.56  *n<60
  K=10 ii SELL first leg         138 100.0%    59.6%  -0.137    -78.0     -49.8    -75.2   51.8   18  -0.357  +0.076    0.56  *n<60
  ----------------------------------------------------------------------------------------------------------------------------------------------------
  NULL at K=2: the opposite ask AT THE TRIGGER is p10 0.39 p50 0.56 p90 0.71; on candles where the first leg went on to LOSE it is p50 0.56, where it WON p50 0.55
  SPLIT by first-fire second, K=2, action (i) buy opposite:
    1st 15-120: n  63  opp win  54.0%  per$1  -0.024  opp ask p50 0.56
    1st 120-200: n  61  opp win  54.1%  per$1  -0.091  opp ask p50 0.57
    1st 200-241: n  15  opp win  73.3%  per$1  +0.530  opp ask p50 0.44  *n<60
```

## Three reasons it does not work, in order of how much they matter

**1. The re-cross is not an event, it is the weather.** It fires on **300 of 326** raw25 candles (92%) and
**149 of 178** fixed15 candles (84%). A condition that occurs nine times in ten cannot select anything. That
alone makes it unusable as a trigger, before any money is counted.

**2. The crowd has already priced it — this is the null V asked for, and it is decisive.** At the trigger the
opposite ask is already **p50 0.56**. And it barely moves with the eventual outcome: on candles where the
first leg went on to **lose** it is 0.58 (raw25) / 0.56 (fixed15); where it **won**, 0.55 / 0.55. Three
cents, or none.

That is exactly what section 6 predicts. Binance leads the Chainlink reference by **2–3 seconds** at a
correlation of 0.81, so by the time the settlement reference confirms a re-cross, the book has had seconds to
absorb it. The trigger is looking at a lagged copy of information the price already has.

**3. Both actions lose.** Buying the opposite is negative at every K on raw25 (−0.020 to −0.039 per $1,
candle total −$24 to −$47 against first-fire-only). Exiting is worse and is uniformly bad: −0.098 to −0.109
per $1, candle total **−$113 to −$126**, which turns raw25's +$107.3 into roughly −$6 to −$19. The longest
losing run goes from **5 to 28**.

Exiting fails for a structural reason worth stating: the exit bid is `1 − 0.56 = 0.44` on a leg bought near
0.45, so it crystallises a small loss **plus a second fee**, on 100% of triggers — and since the trigger
fires on 84–92% of candles, it exits almost everything, winners included.

## K does not matter here, which is itself informative

Across K = 0, 2, 5, 10 the raw25 buy-opposite arm moves only −0.030 → −0.036 → −0.039 → −0.020. Compare the
Chainlink-divergence rule, where shifting the read by **one second** flipped the sign. This trigger is not
knife-edge; it is flat and slightly negative, which is what a condition carrying no information looks like.

## The one positive corner, reported and not sold

fixed15, first fire at second ≥ 200, K=2, buy opposite: **n=15**, opposite wins 73.3%, per $1 **+0.530**,
opposite ask p50 0.44. Fifteen trades. It is the only positive corner in the whole grid and it is a quarter of
the way to the sample bar. It is here because the grid is reported in full, not because it is a candidate.

## Answer

The owner's mechanism is real as an observation and empty as a trigger. The reference does re-cross — almost
always — and by the time it does, the price has already moved. Acting on it loses money in both directions,
and the exit version is the more expensive of the two.

---

# fixed15 after 220 s — the slice and the rule give opposite answers

Owner, 09-28 13:3x: *"test fixed on the 10 days data and see the fires only after 220 s."* Two different
things, and the difference is the answer.

```
(1) SLICE - stable_ef FIXED fires, 249 fires over 10 days ['09-15', '09-16', '09-21', '09-22', '09-23', '09-24', '09-25', '09-26', '09-27', '09-28']
  cut             n  lost   win%  paper$1   paper$   pDD$   LON$1    LON$  lonDD$  run  days+
  ALL           249   110  55.8%   +0.093   +240.3  233.4  -0.057   -86.3   194.0    7   6/10
  sec >= 200     42    13  69.0%   +0.422   +183.6   46.9  +0.260   +65.1    40.5    4    9/9  *n<60
  sec >= 220     19     8  57.9%   +0.210    +41.5   30.0  +0.054    +6.3    31.2    3    7/8  *n<60
  sec >= 230      7     3  57.1%   +0.298    +21.7   11.0  +0.127    +5.5    13.8    1    2/4  *n<60
  per day at sec >= 220: 09-15 n1 +9$  09-16 n2 +1$  09-21 n4 +4$  09-22 n5 -17$  09-23 n2 +1$  09-24 n3 +20$  09-26 n1 +10$  09-28 n1 +13$

(2) RULE - fixed15 may only fire at the first qualifying pass with sec >= S. 1015 candles, 5 days ['09-24', '09-25', '09-26', '09-27', '09-28']
  rule           fires  /day fills  fill%  lost   win%   FAK$1    FAK$    DD$  paper$1   LON$1    LON$  run  days+
  sec >= 200        60  12.0    27  45.0%    15  44.4%  -0.124   -34.6   74.1   +0.074  -0.089   -32.8    5    1/5  *n<60
      per day (FAK $): 09-24 +39  09-25 -38  09-26 -25  09-27 -1  09-28 -10
  sec >= 220        33   6.6    17  51.5%    10  41.2%  -0.234   -41.2   44.3   -0.070  -0.206   -42.0    3    1/5  *n<60
      per day (FAK $): 09-24 -4  09-25 +2  09-26 -20  09-27 -9  09-28 -10
  sec >= 230        19   3.8    13  68.4%     8  38.5%  -0.232   -31.2   35.4   -0.147  -0.295   -35.4    3    1/4  *n<60
      per day (FAK $): 09-24 -7  09-25 +5  09-26 -20  09-27 -9  09-28 +0
```

## The slice wins; the rule loses

| | n | win% | paper $ | London $ | days + |
|---|---|---|---|---|---|
| **(1) slice**, fires that landed at ≥220 | 19 | **57.9%** | **+41.5** | +6.3 | 7/8 |
| **(2) rule**, may only fire at ≥220 | 33 fires / 17 fills | **41.2%** | −0.070/$1 | −42.0 | **1/5** |

**This is survivorship, and it is the whole explanation.** The slice's 19 fires are the candles where the
normal rule *found nothing until second 220* — a set selected after the fact by the rule's own silence. You
cannot trade it, because at second 20 you do not know the rule will stay quiet.

The rule version forces a fire at 220+ on every candle, including the ones the normal rule would have taken
early. Those are different candles and they are worse: win rate falls from 57.9% to **41.2%**, and only **1
of 5 days** is positive against 7 of 8.

The same reversal holds at every cut. At ≥200 the slice is 69.0% and +$183.6; the rule is 44.4% and −$34.6.

## And the fill finishes it

The rule's paper column is +0.074 at ≥200 — marginally positive if every fire filled at the quoted ask. Under
the per-pass FAK simulator it is **−0.124**, on a **45.0%** fill rate. Half the fires do not land, and the
half that do are the wrong half. That is the same adverse selection measured everywhere else on this box:
the rows that fail to fill win more often than the rows that fill.

## Answer

Restricting fixed15 to fire only after 220 s does not work. The attractive after-220 numbers describe fires
the existing rule already makes and cannot be turned into a rule, and when the restriction is actually
imposed the result is negative on paper, more negative after fills, and positive on one day in five.

Every cell in (1) and (2) is below the 60-fill bar and marked.

---

## 2026-09-28 14:2x — known-wrong numbers in this document (fixed15 only)

**Every `fixed15` figure in this file was computed with a free extra tick and is wrong by roughly that
much.** `raw25` and every EF-2 v0 / v1 / london44 figure is unaffected and stands as written.

The cause, in full, is in [EF3.md](EF3.md) under "Correction — a free extra tick on the fixed15 arm":
`ef2_rows.npz` stores the ask as float32, which defeats the `Decimal(str(x))` tick-grid guard that
`pad_cost` relies on, so `ROUND_CEILING` adds one tick on 44.8% of rows. Only the padded profile
(`fixed15`) uses that path.

Fixed in `ef2_v0b.py`, `ef2_report.py`, `ef2_second.py`, `ef2_recross.py`, `ef2_v0_detail.py` and
`ef2_compare.py`, each with an assert that `pad_cost(float32(a)) == pad_cost(a)`. **The scripts are
correct now; the numbers written into this document were produced before the fix and have not been
re-run.** For the direction of the change, the one arm that has been recomputed moved like this:

| fixed15 S≥0, 5 days | as published | recomputed |
|---|---|---|
| $ total / worst DD / P/DD | +73.8 / 75.8 / 0.97 | +54.5 / 85.3 / 0.64 |
| fires/day / per $1 | 35.6 / +0.104 | 39.2 / +0.068 |

So fixed15 baselines here are **too flattering on per $1 and too kind on drawdown**, and every place this
document uses fixed15 as the null or the control understates the bar. None of EF-2's conclusions turned
on a fixed15 margin that small, so I have not re-run the document; I have marked it instead. If any
fixed15 number here is about to be used for a decision, re-run its script first — the scripts are fixed.
