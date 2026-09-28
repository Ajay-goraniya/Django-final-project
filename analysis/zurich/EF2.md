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
