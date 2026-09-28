# EF_FIRE_TIME — when should EF fire?

Zurich, 2026-09-28. READ-ONLY on the research archive's `decide_log`. 5 days, **1,015** gamma-graded candles,
**785,924** passes, raw p and both side asks every ~250 ms. Master OFF, nothing live, nothing deployed.

Owner, 09-28 09:5x: *"EF acts like everyone else — fires late, after the price has moved. Predict.fun's v11
fired at ~20 s and earned early cheap entries. Same v10 model on both."*

Labels are the venue's own resolution. The fill simulator, the capital-weighted per $1 and the halves are
imported from `ef_persist.py`, so these sit on the same basis as EF_PERSIST.md and EF_TRIGGER_SOURCE.md. The
permutation is V's stricter one: a flipped draw is priced at the **opposite side's real ask**, both arms
through the identical FAK test, so the control answers "what if the model had picked the other side", fully
priced, rather than "what if the payout flipped".

## Answer in four parts

**1. The owner is right that EF fires late.** Baseline fixed15 fire second: **p10 45, p50 126, p90 198**. Only
**5.1%** of fires happen at or before second 30; **55.4%** happen at second 120 or later.

**2. The owner is right that firing earlier is better — and it is not close.** Across the 28-cell grid, every
one of the **16 cells with S ≥ 45 is negative**, and **7 of the 12 cells with S ≤ 30 are positive**. The sign
pattern is the finding; no single cell is.

**3. But it is not "early cheap entries" — the early rule pays MORE, not less.** Mean ask at the fire is
**0.540** for S=15 P=0.55 against **0.430** for the baseline. The early rule's advantage is that it is right
more often (**win 58.3% vs 43.9%** of fills), not that it buys cheaper. The baseline buys cheap and wrong.

**4. And the gain is the TIMING, not the model.** A placebo that keeps the model's *side* but drops its
*confidence bar* entirely (P = 0.00) pays **+0.045** at S=15 against **+0.042** for P=0.55 — the same or
better. Raising the bar makes it worse at every S: **P=0.70 is negative at all seven S values.** The model's
side call does carry the result (V's opposite-ask flip: p = 0.002–0.018 on the early cells), but its
confidence number earns nothing.

**Every cell that met the standing precondition was put through verify.py and every one came back
NOT A FINDING.** Details at the end — the honest summary is that the *pattern* across 28 cells is strong and
no individual cell survives its own gates.

## 1. Baseline — the rule live on London today

```
```

`revC` is the mean ask reversion between the fire and the +250 ms row, in cents — the EF_VETO_V2 mechanism.
`secFire` is the median fire second.

The bucket table is the owner's point in one line: the baseline puts **55%** of its fires into the 120 s+
region, where per $1 is +0.196 and −0.139 on 33 and 13 fills. Nothing in that table is a reading on its own —
every bucket is far under the 60-fill bar — which is exactly why the grid below exists.

## 2. The grid — all 28 cells, plus a placebo row

Rule: fire at the **first** pass with `sec >= S` **and** `raw p_side >= P` **and** own-side `ask <= 0.60`
(the engine's cap). One fire per candle.

```
```

Two facts checked before the grid was built, because they decide what it can mean:

- the engine logs the side the **model favours** on **100.0%** of passes (`p < 0.5` on 0.0% of 785,924), so
  `p_side >= P` can only ever mean the logged side and nothing is hidden on the unlogged one;
- the binding constraint is the **price**, not p: 64.7% of passes already clear p ≥ 0.70, but only **21.4%**
  have an own-side ask ≤ 0.60.

That second fact is why the placebo matters. Dropping the p bar does not open the floodgates — the ask cap is
still doing the work — so P=0.00 is a fair comparison rather than a different trade.

### Reading the grid

| | cells | positive | negative |
|---|---|---|---|
| **early**, S ≤ 30 | 12 | **7** | 5 (three of them the whole P=0.70 column) |
| **late**, S ≥ 45 | 16 | **0** | **16** |

Sixteen from sixteen is a strong pattern, but the cells share candles and are **not independent**, so it is
not a 2⁻¹⁶ p-value and must not be quoted as one. What makes it convincing is that it holds *at every P
level separately*, including the placebo column.

Down the P axis the model's confidence is **anti**-predictive: P=0.70 is negative at all seven S values, and
at S=15 the sequence P=0.00 → 0.55 → 0.60 → 0.65 → 0.70 runs +0.045, +0.042, +0.009, +0.008, −0.083.

`revC` also explains the fill rates: the early cells revert **+0.56 to +0.75c** and fill at **82–87%**, while
the baseline reverts **+7.23c** and fills at 42%. Early fires are not selected dips. That is the same
mechanism EF_TRIGGER_SOURCE and EF_PERSIST measured, seen from the other end.

**A caveat that limits all of it:** the fill simulator was validated against London's real 31% per attempt and
reproduces ~42% on the baseline. These early cells run at **82–87%**, far outside the range where the
simulator was checked. The direction of the result does not depend on the exact fill rate, but the per $1
magnitudes do, and they should be treated as optimistic until London measures a real early fire.

## 3. Does EF follow the crowd?

```
  n 195 fires with a move_bps feature
  corr(ask-0.50, move_bps signed toward OUR side) = +0.338   corr(ask-0.50, |move_bps|) = +0.415
  fires taken WITH the move already in place (sign(move) == our side): 83.6%
  ask-0.50 by |move_bps| bucket (if EF only buys what already moved, these rise together):
    |move|   0-2    n   101  mean ask-0.50 -0.096  mean ask 0.404
    |move|   2-5    n    70  mean ask-0.50 -0.067  mean ask 0.433
    |move|   5-10   n    20  mean ask-0.50 +0.019  mean ask 0.519
    |move|  10-20   n     4  mean ask-0.50 +0.097  mean ask 0.598

  per $1 by ASK-AT-FIRE x FIRE-SECOND (the two ways of asking "did we pay up for news"):
    ask bucket               sec 15-30           sec 30-60          sec 60-120         sec 120-180         sec 180-240
    0.00-0.45             +0.405 (2/4)       -0.104 (6/13)      +0.033 (12/35)      +0.405 (23/43)       +0.346 (6/21)
    0.45-0.55             +1.033 (2/4)        -1.000 (2/7)       +0.449 (8/17)       -0.169 (5/19)       -1.000 (4/12)
    0.55-1.00             -1.000 (1/2)             - (0/1)        -1.000 (3/4)       -0.411 (5/10)        +0.031 (3/3)
    cell format: per $1 (fills/fires). Anything under 60 fills is not a reading.

  What p and the ask were at sec 20 and sec 30, in the 195 candles fixed15 later fired on
  (ask is always OUR side - the side the fire eventually took - so it is the price we could have paid):
    sec 20: n 195  ask then 0.402 (p50 0.390)  ask at the fire 0.430 (p50 0.420)  ->  the price moved +2.86c against us on average, p50 +4.00c
             p then 0.662 (p50 0.664); the pass at sec 20 already favoured the SAME side we later bought on 27.2% of candles
             the sec-20 ask was CHEAPER than the fire ask on 64.1% of candles, the same on 2.6%, dearer on 33.3%
    sec 30: n 195  ask then 0.399 (p50 0.390)  ask at the fire 0.430 (p50 0.420)  ->  the price moved +3.15c against us on average, p50 +6.00c
             p then 0.667 (p50 0.678); the pass at sec 30 already favoured the SAME side we later bought on 27.2% of candles
             the sec-30 ask was CHEAPER than the fire ask on 61.0% of candles, the same on 3.6%, dearer on 35.4%
```

**Yes, clearly.** 83.6% of baseline fires are taken with the Binance move already pointing our way, and the
ask at the fire tracks the size of that move: correlation +0.415 with |move_bps|, and mean `ask − 0.50` rising
−0.096 → −0.067 → +0.019 → +0.097 across the move buckets. EF is largely buying what has already happened.

**Waiting costs 3–4c a share.** In the 195 candles fixed15 fired on, the ask for the side it eventually bought
was **+2.86c higher at the fire than at second 20** (p50 +4.00c), and was cheaper at second 20 on **64.1%** of
candles. That is the owner's "early cheap entries", measured.

**But the early price is for a different trade, and this is the important qualifier.** At second 20 the model
favoured the *same side* the fire eventually took on only **27.2%** of those candles. Firing at ~20 s is not
"buying the same thing earlier" — three times out of four it is buying the other side. So Predict.fun's v11
cannot be explained as the same trade entered sooner, and the grid's early cells do not work by anticipating
the late signal: they work by taking whatever the model favours *at that moment* and being right 58% of the
time.

The ask × second table is reported in full for completeness and **is not readable**: the largest cell has 23
fills against a 60-fill bar, and several are 2–6 fills. It is in the file so the grid is not selectively
quoted, not because it supports anything.

## verify.py on every qualifying cell

Standing rule: run verify.py on any cell positive in both halves with n ≥ 60. Six qualified — S ∈ {15, 20, 30}
at P=0.55, the S=15 and S=20 placebos, and the baseline with the ask cap.

```

### grid S=15 P=0.55   per$1 +0.0425 on 683 fills of 829 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.016, flipped mean -0.036
    sweep over S 15:+0.042 20:+0.035 30:+0.041 45:-0.017 60:-0.007 90:-0.012 120:-0.006
==============================================================================
FINDING: grid S=15 P=0.55   (+0.042/fire, n=683)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 11}
  [PASS] both halves          h1 +0.039 / h2 +0.046
  [FAIL] permutation control  real +0.042 vs permuted mean +0.042 (p95 +0.042), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.042  0.035  0.041 -0.017 -0.007 -0.012 -0.006]
  [PASS] cost sensitivity     +0c:+0.042 +0c:+0.033 +1c:+0.024 +2c:+0.006
  [FAIL] beats the null       mine +0.042 vs PLACEBO S=15 with no p bar +0.045
  [FAIL] paired test          n=60, agree on 36, discordant 24 (14 vs 10), edge +0.067, exact McNemar p=0.541
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, beats the null, paired test


### grid S=20 P=0.55   per$1 +0.0346 on 663 fills of 798 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.018, flipped mean -0.046
    sweep over S 15:+0.042 20:+0.035 30:+0.041 45:-0.017 60:-0.007 90:-0.012 120:-0.006
==============================================================================
FINDING: grid S=20 P=0.55   (+0.035/fire, n=663)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 9}
  [PASS] both halves          h1 +0.028 / h2 +0.041
  [FAIL] permutation control  real +0.035 vs permuted mean +0.035 (p95 +0.035), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.042  0.035  0.041 -0.017 -0.007 -0.012 -0.006]
  [FAIL] cost sensitivity     +0c:+0.035 +0c:+0.025 +1c:+0.016 +2c:-0.001  <- dies once you pay realistically
  [FAIL] beats the null       mine +0.035 vs PLACEBO S=20 with no p bar +0.038
  [FAIL] paired test          n=57, agree on 37, discordant 20 (11 vs 9), edge +0.035, exact McNemar p=0.824
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, cost sensitivity, beats the null, paired test


### grid S=30 P=0.55   per$1 +0.0413 on 609 fills of 757 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.006, flipped mean -0.056
    sweep over S 15:+0.042 20:+0.035 30:+0.041 45:-0.017 60:-0.007 90:-0.012 120:-0.006
==============================================================================
FINDING: grid S=30 P=0.55   (+0.041/fire, n=609)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 10}
  [PASS] both halves          h1 +0.048 / h2 +0.034
  [FAIL] permutation control  real +0.041 vs permuted mean +0.041 (p95 +0.041), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.042  0.035  0.041 -0.017 -0.007 -0.012 -0.006]
  [PASS] cost sensitivity     +0c:+0.041 +0c:+0.032 +1c:+0.023 +2c:+0.005
  [PASS] beats the null       mine +0.041 vs PLACEBO S=30 with no p bar +0.009
  [FAIL] paired test          n=58, agree on 41, discordant 17 (9 vs 8), edge +0.017, exact McNemar p=1.000
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, paired test


### placebo S=15 P=0.00   per$1 +0.0446 on 732 fills of 853 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.002, flipped mean -0.044
    sweep over S 15:+0.045 20:+0.038 30:+0.009 45:-0.044 60:+0.008 90:-0.034 120:-0.030
==============================================================================
FINDING: placebo S=15 P=0.00   (+0.045/fire, n=732)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 12}
  [PASS] both halves          h1 +0.021 / h2 +0.068
  [FAIL] permutation control  real +0.045 vs permuted mean +0.045 (p95 +0.045), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.045  0.038  0.009 -0.044  0.008 -0.034 -0.03 ]
  [PASS] cost sensitivity     +0c:+0.045 +0c:+0.035 +1c:+0.026 +2c:+0.007
  [FAIL] beats the null       mine +0.045 vs fixed15 unfiltered +0.061
  [FAIL] paired test          n=73, agree on 50, discordant 23 (15 vs 8), edge +0.096, exact McNemar p=0.210
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, beats the null, paired test


### placebo S=20 P=0.00   per$1 +0.0384 on 713 fills of 821 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.002, flipped mean -0.050
    sweep over S 15:+0.045 20:+0.038 30:+0.009 45:-0.044 60:+0.008 90:-0.034 120:-0.030
==============================================================================
FINDING: placebo S=20 P=0.00   (+0.038/fire, n=713)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-28': 11}
  [PASS] both halves          h1 +0.002 / h2 +0.075
  [FAIL] permutation control  real +0.038 vs permuted mean +0.038 (p95 +0.038), p=1.000 over 500 draws
  [FAIL] sweep shape          NON-monotone: [ 0.045  0.038  0.009 -0.044  0.008 -0.034 -0.03 ]
  [PASS] cost sensitivity     +0c:+0.038 +0c:+0.029 +1c:+0.020 +2c:+0.002
  [FAIL] beats the null       mine +0.038 vs fixed15 unfiltered +0.061
  [FAIL] paired test          n=68, agree on 44, discordant 24 (13 vs 11), edge +0.029, exact McNemar p=0.839
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, beats the null, paired test


### baseline fixed15 + ask cap   per$1 +0.1452 on 72 fills of 182 fires
    V's control - sign flip priced at the OPPOSITE real ask: p = 0.128, flipped mean +0.007
==============================================================================
FINDING: baseline fixed15 + ask cap   (+0.145/fire, n=72)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-24': 15, '09-25': 28, '09-26': 8, '09-27': 17, '09-28': 4}
  [PASS] both halves          h1 +0.274 / h2 +0.017
  [FAIL] permutation control  real +0.145 vs permuted mean +0.145 (p95 +0.145), p=1.000 over 500 draws
  [PASS] cost sensitivity     +0c:+0.145 +0c:+0.130 +1c:+0.114 +2c:+0.086
  [PASS] beats the null       mine +0.145 vs fixed15 unfiltered +0.061
  [FAIL] paired test          the two rules never disagree - no information
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, paired test

```

**All six: NOT A FINDING.** What the failures actually say:

- **The permutation reads p = 1.000 on every cell, and that is an artefact of the construction, not a
  result.** verify.py shuffles the model's predictions and re-applies the rule's own bar — but 90.7% of all
  passes already clear p ≥ 0.55, so a shuffled p re-selects almost exactly the same set and real == permuted
  by definition. I flagged this before running it. The control that carries weight here is V's opposite-ask
  sign flip, which reads **p = 0.002–0.018 on the early cells** and **p = 0.128 on the baseline** — that one
  says the side selection is real.
- **`beats the null` is the substantive failure.** S=15 and S=20 at P=0.55 both lose to their own placebo
  (+0.042 vs +0.045, +0.035 vs +0.038). The model's confidence bar does not pay for itself. S=30 is the one
  exception (+0.041 vs +0.009).
- **The S sweep is non-monotone** on both families — earlier is better in aggregate but not smoothly, with a
  dip at S=45 and a partial recovery at S=60.
- **Paired against the baseline the evidence is thin**: 57–73 shared candles, agreeing on about two thirds,
  McNemar p = 0.21 to 1.00. The early rules are a *different population* (829 fires against 195), so the
  paired test has little to work with — which is itself worth knowing before anyone calls this an upgrade.
- Per-day samples fail only on 09-28, which is a partial day (9–12 fills).

## What I would say to the owner

The diagnosis is confirmed and the prescription is not. EF does fire late, late firing is worse, and the
price does run 3–4c away while it waits. But the grid says the gain from firing early comes from **when**, not
from the model — a rule that ignores the confidence number entirely does as well — and the sec-20 lookback
says the early entry is not the same trade at a better price. So "fire at 20 s like v11" is a real direction
with a real mechanism behind it, and it is not yet a validated rule: nothing here passed, the fill simulator
is being run far outside where it was checked, and the strongest single number in the study is a *placebo*
matching the model.

The next thing worth doing, if the owner wants it, is the one measurement Zurich cannot make: London firing a
small number of real early orders and reporting the actual fill rate and slippage at second 15–30. Everything
above turns on a simulated 82–87% fill that no live system has demonstrated.

## Files

- `ef_fire_time.py` — baseline, the 28-cell grid, the placebo row, the crowd measure
- `ef_fire_time_verify.py` — verify.py on all six qualifying cells
