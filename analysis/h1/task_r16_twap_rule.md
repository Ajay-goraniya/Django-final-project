# R-16 — the settlement line is a TWAP, and the engine has been aiming at the wrong one

**This corrects my own R-16 verdict of 40 minutes ago.** I concluded the venue reference was
"Binance-equivalent, a few basis points away, no feature there" and told V not to backfill. That was
wrong in the part that mattered: the reference is not a different *price*, it is a different
*quantity*. Mumbai found the rule in gamma — market `btc-5m-twap-60`, outcome = Chainlink **60 s TWAP
at candle end vs the same 60 s TWAP at eventStartTime**. Testing it changes the answer.

Script `analysis/h1/r16_twap_rule.py`. Binance 1 s spot, 09-07..09-14, **1,797 candles** with a venue
settlement. Chainlink is not Binance, but a *level* offset cancels in a TWAP-minus-TWAP comparison,
so Binance is a usable proxy for the **sign**, which is all the outcome depends on.

## 1. The rule is confirmed, decisively

| rule | agrees with `venues.outcome` |
|---|---|
| `close ≥ open` (what the engine labels on) | **86.81%** |
| `TWAP60(end) ≥ TWAP60(open)` | **96.66%** |

The two rules disagree with each other on **217 of 1,797** candles. On those, `close-vs-open` is right
**9.2%** and `TWAP-vs-TWAP` is right **90.8%** — exact binomial **p = 9.4e-38**. Switching the line
removes three quarters of the disagreement with the venue (13.2% → 3.3%). The residual 3.3% is the
Binance-for-Chainlink proxy error and bounds how much a live reference feed could still add.

## 2. And the correct line is known AT FIRE TIME

`ref_open` = the 60 s TWAP over the window **before the candle opens**. It is fully determined when
the candle starts, so it is available at every decision second — no lookahead. The engine currently
measures everything from `open`. The two differ: median gap **0.00 bps**, median **|gap| 0.86 bps**,
p10 −2.26 / p90 +2.45. Tiny in absolute terms, and decisive because most candles are near-ties.

Aiming at the TWAP line instead of the open, at each fire second (the same price, only the reference
changes):

| sec | n | open-rule | TWAP-rule | discordant | open right | TWAP right | McNemar p |
|---|---|---|---|---|---|---|---|
| 15 | 1797 | 57.87% | **62.60%** | 477 | 41.1% | 58.9% | 1.2e-04 |
| 30 | 1797 | 59.54% | **64.27%** | 369 | 38.5% | 61.5% | 1.1e-05 |
| 45 | 1797 | 63.05% | **67.00%** | 331 | 39.3% | 60.7% | — |
| 60 | 1797 | 65.94% | **68.61%** | 316 | 42.4% | 57.6% | 8.1e-03 |
| 90 | 1797 | 70.12% | **72.12%** | 232 | 42.2% | 57.8% | — |
| 120 | 1797 | 72.45% | **74.90%** | 212 | 39.6% | 60.4% | 3.1e-03 |
| 150 | 1797 | 74.68% | **77.52%** | 179 | 35.8% | 64.2% | — |
| 180 | 1797 | 78.19% | **81.25%** | 187 | 35.3% | 64.7% | 7.0e-05 |
| 210 | 1797 | 83.36% | **86.64%** | 179 | 33.5% | 66.5% | — |
| 240 | 1797 | 86.92% | **91.54%** | 157 | 23.6% | 76.4% | 2.0e-11 |

**All 10 of 10 fire seconds improve.** The sweep has no peak at a chosen value — it is positive across
the whole range, which is the opposite of the fit-to-noise shape the method rules warn about.

## 3. Rain or sun

Improvement (TWAP accuracy − open accuracy) per fire second × UTC day, every cell:

| sec | 09-08 | 09-09 | 09-10 | 09-11 | 09-12 | 09-13 | 09-14 | h1 | h2 |
|---|---|---|---|---|---|---|---|---|---|
| 15 | +0.049 | +0.028 | +0.049 | +0.080 | +0.003 | +0.068 | +0.056 | +0.052 | +0.042 |
| 30 | +0.087 | +0.056 | +0.064 | +0.059 | +0.017 | +0.047 | +0.026 | +0.063 | +0.031 |
| 45 | +0.039 | +0.049 | +0.035 | +0.073 | +0.014 | +0.050 | +0.015 | +0.049 | +0.030 |
| 60 | +0.000 | +0.031 | +0.042 | +0.049 | +0.003 | +0.047 | −0.004 | +0.032 | +0.021 |
| 90 | +0.019 | +0.045 | +0.032 | +0.031 | +0.017 | +0.011 | −0.019 | +0.038 | +0.002 |
| 120 | +0.000 | +0.035 | +0.042 | +0.021 | +0.014 | +0.043 | +0.000 | +0.031 | +0.018 |
| 150 | +0.010 | +0.035 | +0.035 | +0.028 | +0.035 | +0.050 | −0.007 | +0.032 | +0.024 |
| 180 | +0.029 | +0.024 | +0.018 | +0.052 | +0.024 | +0.043 | +0.022 | +0.032 | +0.029 |
| 210 | +0.019 | +0.035 | +0.039 | +0.056 | +0.003 | +0.057 | +0.011 | +0.038 | +0.028 |
| 240 | +0.087 | +0.028 | +0.049 | +0.073 | +0.045 | +0.050 | +0.015 | +0.057 | +0.036 |

**64 of 70 readable cells positive**; the three negatives are −0.004, −0.007 and −0.019, all on 09-14.
Halves positive at every second (h1 +0.031…+0.063, h2 +0.002…+0.042) — no sign flip anywhere.
Permutation of the TWAP rule's predictions at S=120: real 0.7490 vs permuted mean 0.5001, **p = 0.0000**.

## 4. What this is, and what it is not

**It is a label and feature correction, not a gate.** No fire is suppressed, no threshold is swept, no
stake is modified. The market settles against `TWAP60(open)`; every open-referenced feature the engine
computes — `move_bps`, `pos_in_range`, `dist_hi_bps`, `dist_lo_bps`, and `mv_x_sec` through
`move_bps` — is centred on the wrong line, and so is the training label `close ≥ open`.

**It is not yet PnL.** Accuracy is not PnL, and this is a rule-vs-rule accuracy comparison, not the
engine. The next step is the one that decides whether anything ships: rebuild the features centred on
`ref_open`, **relabel on the TWAP rule**, retrain chronologically with the venue stage, and run the
paired test against frozen v10 on the logged window with verify.py. Only that answers the question.

**It is on 8 days and a proxy.** 1,797 candles, one week, and Binance standing in for Chainlink. The
3.3% residual disagreement is the proxy's error budget; Task 98's `ref_stream` will let that be
calibrated rather than assumed.

**What it probably explains.** R-16's "near-tie candles bleed" (n=284, win 41.5%, −0.144/$1) and the
whole 12.7% disagreement rate are the same phenomenon seen through the wrong line: a candle that is a
near-tie *against the open* is often not a near-tie against the TWAP, and the engine was betting on
the wrong side of a line it could have computed exactly.
