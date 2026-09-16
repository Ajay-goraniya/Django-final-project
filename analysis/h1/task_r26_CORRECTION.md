# CORRECTION — the wrong-side ask, and everything it inflated

**V caught this and V's number was right.** Posted here rather than quietly edited into the originals,
because "$36 of calibration noise" reached `NOTES_v12` and had to be pulled the same day.

## The bug

`r12_train.lane_ticks` carries `r['ask']` as **the lane's chosen-side ask**, not a side-neutral price.
`fire_set` picked its *own* side and then priced at that logged ask. Any arm choosing a different side
from the lane paid the **other side's** quote — and on a binary market the two asks sum to about 1, so
the subsidy is large and signed by the direction of the disagreement.

**Frozen v10 is immune: side mismatch 0.0%, because frozen *is* the lane's model.** That is exactly
why it reproduced to the cent through two independent harnesses and hid the bug from both of us. The
error was invisible on the one arm everyone checks.

## What it inflated

| arm | as published | corrected | inflation |
|---|---|---|---|
| frozen v10 | 1033 f, +145.81 | 1033 f, +145.81 | **+0.00** |
| R-26 (b) week 1 | 778 f, +182.17 | **733 f, +145.45** | **+36.71** |
| R-26 (c) two weeks | 588 f, +175.47 | **315 f, +69.48** | **+105.99** |
| R-17 / R-25 plain 30 | 551 f, +125.88 | **444 f, −17.06** | **+142.94** |

**The bug rewarded divergence from the live model** — the worst possible shape for it to have, because
every candidate this session was measured by how far it departs from frozen.

## Retracted

**"An arbitrary calibrator detail is worth $36 per 1,033 fires."** It is not. On V's row set the gap is
**−$0.36**; on my refreshed snapshot **+$1.85**. Arm (b) and frozen v10 are a tie, which is what two
models with identical coefficients and a 0.5% direction difference should be. The sensitivity claim,
the "five-point threshold move" equivalence built on it, and the fragility framing all go with it.

## Corrected table, fixed harness, refreshed snapshot (39,237 ticks / 2,038 candles)

| arm | fires | hit% | per $1 | total |
|---|---|---|---|---|
| (a) frozen v10 | 1101 | 52.9% | +0.132 | **+144.81** |
| (b) week 1 only | 802 | 54.6% | +0.183 | **+146.66** |
| (c) week 1 + week 2 | 325 | 56.0% | +0.202 | **+65.63** |

**R-26's conclusion is strengthened, not reversed.** The second week now costs **$81** against week 1
alone, where the buggy run said $6.70. *"The second week does not help"* was the right answer for the
wrong-sized reason.

Every "does not ship" verdict from today stands and stands harder — the plain-30 walk-forward arm is
**negative** once priced correctly. The directions were right; the magnitudes were not.

## V's threshold-stability question: **confirmed**

Frozen v10 on week 2, corrected pricing:

| thr | 0.10 | 0.15 | 0.20 | 0.25 | 0.30 |
|---|---|---|---|---|---|
| total | +107.22 | +134.81 | **+148.86** | +145.58 | +112.24 |
| fires | 1377 | 1189 | 777 | 683 | 375 |

**Week 1 peaks at 0.10. Week 2 peaks at 0.20, and 0.10 is the *worst* cell of the band.** The optimum
does not merely shift — it relocates to where the other week was weakest, on adjacent weeks of the
same market and the same model.

**So the EV threshold is not a parameter to tune, and V should tell the owner so plainly.** This is
worse than the non-monotone-sweep failure the method rules warn about: there, a peak is noise; here
the peak moves to the opposite end between one week and the next.

## What I am changing in how I work

`fire_set` now prices `feat['_ask_up']` / `feat['_ask_dn']` for the side it chose. And the general
lesson, which is the one that cost the day: **an arm that agrees with the live model cannot validate a
harness that only mis-prices disagreement.** Frozen reproducing to the cent felt like proof the
pipeline was sound. It was proof of nothing about the arms that mattered.
