# EF_DRAWDOWN — can a pause remove EF's drawdown without wasting profit? **No pause can. The calibration already did.**

Owner (09-22 22:5x): *"i want profitable ef that has no drawdowns by tomorrow. You can stop trading
in drawdown period or when market is wrong for us or something else but don't waste profit."*

`r38_ef_drawdown.py`. 1,108 venue-graded v10 EF fires, 09-08 17:35 → 09-16 17:10, **stake $3**,
graded on `venues.outcome`, fees = measured live Polymarket (1.67% of shares, winners *and* losers).
Calibrated arm = pooled Platt `a=1.0677, b=−0.3208`, clamped never to raise `p`.
Every bucket and grid cell was fixed by V **before** any number was read, and all are reported.
Row-level data for the engine side: **`analysis/h1/ef_fires_1108.csv`**.

## The headline

| arm | n | W% | per $1 | **total** | **maxDD** | longest loss run |
|---|---|---|---|---|---|---|
| RAW | 1108 | 52.6% | +0.1512 | **$+502.43** | **$53.01** | 8 |
| CALIBRATED | 390 | 56.4% | +0.3024 | $+353.79 | **$27.18** | 6 |

**Calibration alone cuts maxDD 49% ($53.01 → $27.18) and doubles per-$1.** It costs $149 of the
$502 total. That is the only drawdown reduction in this file that survives its null.

## (1) Do EF losses cluster? **No. This decides everything after it.**

| arm | n | runs | expected | z | **p** |
|---|---|---|---|---|---|
| RAW | 1108 | 548 | 553.5 | −0.33 | **0.741** |
| CALIBRATED | 390 | 194 | 192.8 | +0.12 | **0.901** |

Lag-1..5 autocorrelation of win/loss and of the residual `(win − p_cal)`:

| series | lag1 | lag2 | lag3 | lag4 | lag5 | 2·se |
|---|---|---|---|---|---|---|
| RAW win/loss | +0.009 | −0.019 | −0.000 | −0.033 | −0.036 | 0.060 |
| RAW residual | +0.014 | −0.010 | +0.019 | −0.025 | −0.022 | 0.060 |
| CAL win/loss | −0.009 | −0.115 | −0.019 | −0.062 | −0.024 | 0.101 |
| CAL residual | +0.002 | −0.102 | −0.004 | −0.047 | −0.021 | 0.101 |

Every value is inside ±2·se except CAL lag-2 (−0.115 vs 0.101), which is one marginal cell out of
20 tested — noise. **EF losses are independent.** Therefore pausing after a losing run removes fires
that are no worse than any other fires, and **no pause rule can beat random removal.** The grid
below is the confirmation, not the test.

## (2) The pause grid — **on RAW, every single cell makes drawdown WORSE**

RAW baseline: n=1108, per$1 +0.1512, total $+502.43, **maxDD $53.01**. Random removal of the same
count gives maxDD ≈ $50–53.

| cell | n | per$1 | total$ | **maxDD$** | null DD mean | null p95 |
|---|---|---|---|---|---|---|
| L=2 pause 15m | 889 | +0.1314 | +350.52 | **77.54** | 50.44 | 69.97 |
| L=2 pause 30m | 863 | +0.1346 | +348.48 | 66.88 | 48.95 | 63.06 |
| L=2 pause 60m | 858 | +0.1346 | +346.36 | 66.88 | 51.61 | 68.46 |
| L=2 pause 120m | 857 | +0.1359 | +349.36 | 63.88 | 50.02 | 65.31 |
| L=3 pause 15m | 1013 | +0.1365 | +414.78 | 71.11 | 53.34 | 65.80 |
| L=3 pause 30m | 1002 | +0.1392 | +418.33 | 65.11 | 51.15 | 64.57 |
| L=3 pause 60m/120m | 998 | +0.1396 | +418.04 | 65.11 | 52.31 | 64.76 |
| L=4 pause 15m | 1070 | +0.1482 | +475.83 | 55.32 | 52.72 | 60.95 |
| L=4 pause 30m | 1065 | +0.1461 | +466.95 | 55.32 | 52.67 | 61.90 |
| L=4 pause 60m/120m | 1062 | +0.1475 | +469.80 | 55.32 | 52.37 | 60.39 |
| trail10 < −2 stk | 931 | +0.1525 | +425.80 | 57.53 | 52.03 | 69.08 |
| trail10 < −3 stk | 987 | +0.1433 | +424.40 | 61.41 | 51.81 | 63.09 |
| trail10 < −4 stk | 1038 | +0.1481 | +461.18 | 59.71 | 52.02 | 63.45 |

**13 of 13 cells raise maxDD above the $53.01 baseline, and 13 of 13 are worse than random removal
of the same number of fires.** They also destroy $27–$152 of profit. Pausing after losses on the raw
lane is strictly harmful on both of the owner's objectives at once.

On the CALIBRATED arm the cells look better, and that is the trap — see (4).

## (3) "Market wrong" buckets — the direction is the **opposite** of the intuition

| bucket | RAW per$1 | RAW DD$ | CAL per$1 | CAL DD$ |
|---|---|---|---|---|
| realised vol LO / MID / HI | +0.081 / +0.161 / **+0.212** | 40.4 / 35.7 / 32.2 | ins. / +0.240 / +0.334 | – / 20.7 / 20.7 |
| \|body\| bps LO / MID / HI | +0.037 / +0.173 / **+0.243** | 39.4 / 35.4 / 28.5 | ins. / +0.408 / +0.312 | – / 18.2 / 37.4 |
| hour 00-06 / 06-12 / 12-18 / 18-24 | +0.123 / +0.178 / +0.171 / +0.132 | 34.7 / 28.0 / 30.2 / 38.9 | +0.396 / +0.406 / +0.228 / +0.275 | 9.0 / 9.9 / 20.8 / 27.2 |
| ask 0.30-0.40 / 0.40-0.50 / 0.50-0.60 | **+0.240** / +0.113 / +0.106 | 42.9 / 46.8 / 47.5 | +0.442 / +0.238 / +0.179 | 25.0 / 24.9 / 24.6 |
| sec 0-30 / 30-60 / 60-120 / 120-300 | **+0.024** / +0.223 / +0.155 / +0.167 | 42.3 / 31.6 / 41.0 / 31.3 | +0.036 / +0.345 / +0.273 / +0.380 | 26.7 / 14.1 / 22.1 / 15.3 |

The market is **not** "wrong" in high volatility — high vol and large body are EF's *best* buckets
(+0.212, +0.243) with the *lowest* drawdowns. The weak buckets are quiet tape (+0.081, +0.037) and
the first 30 seconds (+0.024). Reported as a grid; I am **not** proposing any of these as a switch —
that is a gate, and the standing rule forbids one.

## (4) Is any pause cell honest? **None.**

A cell must be monotone in its own sweep and beat its null. On the calibrated arm:

| sweep | maxDD across the knob | shape |
|---|---|---|
| L=2 over M | 24.22 22.48 29.92 26.92 | **NON-MONOTONE** |
| L=3 over M | 24.77 ×4 | flat |
| L=4 over M | 21.18 21.18 24.33 24.33 | monotone |
| M=15m over L | 24.22 24.77 **21.18** | **NON-MONOTONE** |
| M=30m over L | 22.48 24.77 **21.18** | **NON-MONOTONE** |

And the reason the best-looking cell looks good:

| cell | **fires removed** | maxDD$ | ΔDD |
|---|---|---|---|
| L=4 pause 15m | **2** | 21.18 | **−6.00** |
| L=4 pause 30m | 4 | 21.18 | −6.00 |
| L=3 pause 15m | 10 | 24.77 | −2.41 |
| L=2 pause 30m | 56 | 22.48 | −4.70 |

**The winning cell removes 2 fires out of 390 and that alone moves maxDD by $6.** That is one
coincidence at the equity trough, not a rule — and its L-sweep is non-monotone. **Verdict: no pause
cell passes. There is nothing here to ship.**

## What to tell the owner

**"Stop trading in the drawdown period" does not work, and the data says why: the losses are
independent.** There is no drawdown *period* to stop in — a loss carries no information about the
next fire (p=0.741). Every pause rule tested either raised the drawdown or cut profit, usually both.

**What does cut the drawdown is already done and costs nothing extra: the calibration.**
$53.01 → $27.18, with per-$1 doubling from +0.151 to +0.302. That is the honest half of the ask.

**What I cannot deliver is "no drawdowns."** A 52–56% bet at ~0.43 has losing runs by construction —
this sample's longest is 8 raw / 6 calibrated, and that is variance, not a fault to be engineered
out. Cutting it further means fewer fires, which is the profit the owner said not to waste.

**And none of this is live.** All paper at the quoted ask; live has only ever taken 41% of these
candles and is running at −10.66% of stake (EF_BRAIN.md §A).
