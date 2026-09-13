# Task 11.2 — the direction model, scored as PnL at the ask

> ## RETRACTED 2026-09-11 03:55 — every PnL number below is a stale-quote artifact.
>
> **V was right (REQUEST.md Task 20).** The replay read the price path at second S but paid an ask
> forward-filled from a collector sample **up to 5 s earlier** (median age 1 s, p90 3 s). Re-run with
> the quote taken at or after the observation:
>
> | margin 0.15 | per-fire |
> |---|---|
> | ORIGINAL (what this page reports) | **+0.207** |
> | NEXT (quote at or after the observation) | **−0.077** |
> | STRICT (observation and quote same instant) | **+0.018** |
>
> **55 of 97 fires vanish under STRICT, and they were worth +0.290/fire** — the profit was the fires
> that never existed. The mechanism: the stale quote is *unbiased* (median difference 0.000) but
> differs by >5c on 17.3% of samples, and the EV filter **selects the randomly cheap ones**.
>
> Every check in `verify.py` tested the signal; none tested whether the **price was real**. The cost
> sensitivity row added a haircut to a fictional ask. `verify.py` now has a `quote_age()` check.
>
> **The direction signal itself is not retracted** — Task 15's premise and Task 17.3's regime
> stability are accuracy-based and stand. What is retracted is that it can be monetised at these
> quotes. See `task20_stale_quote.md`. Text below is left as the record of the claim.

H1, 2026-09-11 02:20 UTC. Per V's ack (01:40): evaluated as **PnL at the recorded ask** on the venue
window, engine grading, never accuracy. A direction model, not a gate.

**This is the first thing in this project to pass every check in `verify.py`.** It is a **shadow
candidate**, not a ship — the same status candidate J had at this stage.

## Setup

- **Training: 505,365 rows from 72,207 candles that all end BEFORE the venue window opens.**
  Walk-forward by construction; the model never sees an evaluation candle.
- Features, all computable live by the engine from its own price path at the fire second:
  signed and absolute distance from open, returns over 5/15/30 s, realised vol, candle range,
  position in range, open-crossings so far, the second itself, and the trailing 12-candle range.
- Evaluation: 648 venue-window candles. Firing uses **the engine's own EV arithmetic at the recorded
  ask** — identical machinery to Task 16 — so model, prior and current EF are compared like for like.
- Model: gradient boosting. A logistic model on the same features is materially worse (+0.104/fire at
  margin 0.15), so the gain is not just the distance feature repackaged.

## Result

| | n | hit | per-fire | halves |
|---|---|---|---|---|
| **GBM direction model @ margin 0.15** | **89** | **62.7%** | **+0.266** | **+0.356 / +0.177** |
| market prior (Task 16) @ 0.20 | 76 | 55.3% | +0.137 | +0.207 / +0.068 |
| current EF fire set | 220 | 53.6% | +0.049 | −0.01 / +10.83 *(total)* |
| naive null, every candle @ S=20 | 638 | 59.2% | **−0.019** | both negative |

**It beats the market prior (≈2×), the current EF fire set (≈5×), and the naive null (which loses).**

### verify.py — all seven checks pass

| check | result |
|---|---|
| grading provenance | PASS — engine `candles` table throughout |
| sample size | PASS — n=89, above the 60 bar |
| both halves | PASS — +0.356 / +0.177 |
| **permutation control** | **PASS — real +0.263 vs permuted mean −0.043, p=0.000 over 200 draws** |
| sweep shape | PASS — monotone: +0.266 / +0.213 / +0.210 / +0.146 / −0.045 |
| beats the null | PASS — +0.266 vs prior +0.137 |
| cost sensitivity | PASS — see below, measured not assumed |

**Seed stability (5 seeds, margin 0.15):** +0.263, +0.246, +0.217, +0.299, +0.308 — **mean +0.266,
sd 0.034, every seed positive**, n stable at 86–92.

### Real slippage — measured by re-paying the ask, not approximated

| haircut | 0.15 | 0.20 | 0.25 | 0.30 | 0.40 |
|---|---|---|---|---|---|
| +0c | +0.242 | +0.181 | +0.193 | +0.149 | −0.085 |
| +3c | +0.168 | +0.108 | +0.116 | +0.071 | −0.151 |
| +5c | +0.124 | +0.064 | +0.070 | +0.024 | −0.190 |
| +10c | **+0.027** | −0.032 | −0.030 | −0.076 | −0.273 |

Still positive at a **10-cent** haircut. Applying J's measured recorded-quote→real-fill ratio of
**≈2.5×** gives a realistic expectation of about **+0.10 per fire**.

### It reaches the band the current model ignores

Fire-distance profile vs the Task 15 part-3 baseline:

| bps at fire | model | current EF |
|---|---|---|
| <1 | 39% | 46% |
| 1–2.5 | 26% | 35% |
| 2.5–5 | 20% | 17% |
| **5–10** | **9%** | **1%** |
| **10–25** | **6%** | ~0% |

This is the mechanism Task 15 part 3 predicted: the model moves fires out of the coin-flip region
and into the band where direction is actually predictable.

## Two things I got wrong on the way, both corrected here

1. **I first reported this as failing on sweep shape** (+0.263 / +0.192 / +0.204 / +0.061 / −0.128).
   That was **one seed**. Averaged over five, the sweep is cleanly monotone. Single-seed sweeps at
   n=14–34 are noise; the seed table above is the honest version.
2. **I diagnosed the decline as miscalibration. That was wrong and I tested it rather than asserting
   it.** On a held-out pre-window slice the model is already well calibrated (raw 0.285 → actual
   0.279; raw 0.713 → actual 0.712), and isotonic calibration changed the result very little. The
   real explanation is the one the monotone sweep shows: the edge is **broad but shallow** — it is
   largest when the model is allowed to take many modest disagreements with the venue, and it decays
   as you demand rarer, more extreme disagreements, where 1/ask leverage amplifies small errors.

## Limits — why this is a shadow candidate and not a ship

- **n=89 fires over 648 candles, ~2.3 days, one regime.** Above the bar, not large.
- **Paper.** Recorded quotes, one fire per candle, no queue position, no partial fills. The +10c row
  and the 2.5× J ratio are the honest guide, not the +0.266.
- The `<1 bps` bucket — 39% of its fires — carries the ~2.5% label-error caveat from part 3.
- No rain-or-sun grid yet; 648 candles cannot support one.

## Recommendation

Run it as a **forward shadow on the live book**, exactly as J was: log what it would have fired,
grade on the engine's actual, verdict at **≥100 graded with the sign holding on both halves**.
Do not deploy it on the strength of a 648-candle replay.

Repro: `analysis/h1/task11_2_direction_model.py`.
