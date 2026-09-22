# EF reversal lane (12.22.0, poly_ef) on stored data — 2026-09-22 16:4x UTC (V)

Owner: "test test test and improve, use the data that we hold". Data: Binance 1 s klines 09-08 -> 09-16 (738,149 s, 2,460
candles) + the 1 Hz Polymarket tape (venues.q, 129,544 rows) + venues.outcome (2,179). Harness `replay_lanes_1s.py` drives
the REAL `poly_lanes.LaneEngine`; no depth stream is stored, so book features read neutral. Fee 1.67%. `*` = n<60.

## The harness reproduces the live lanes (fidelity, pending H1's independent check)
| lane | n | hit | ask med | per$1 | H1 | H2 | live reference |
|---|---|---|---|---|---|---|---|
| MAIN | 1319 | 70.1% | 0.72 | -0.021 | -0.063 | +0.020 | Mumbai 6 d: -0.033 |
| REVERSAL | 457 | 62.6% | 0.60 | +0.461 | +0.144 | +0.777 | Mumbai real fills: +0.689 |

## EF lane as built (all 12 gates at build11's anchors + 250 ms latch + price rule): FAILS
n=130, hit 33.1%, ask med 0.40, sec med 66, per$1 **-0.142** (H1 -0.412 | H2 +0.129).

## EF real-score grid (price rule true, first read per candle with real >= theta, no other gate) — whole grid
| theta | n | hit | ask med | per$1 | H1 | H2 | null: implied | opposite side | perm mean / p95 / p(>=real) | +0.02 / +0.05 | without REVERSAL's candles |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.30 | 1456 | 30.3% | 0.31 | +0.049 | -0.037 | +0.134 | | | | | |
| 0.40 | 1367 | 30.1% | 0.31 | +0.056 | -0.049 | +0.161 | | | | | |
| 0.50 | 1210 | 31.3% | 0.32 | +0.145 | +0.096 | +0.194 | -0.028 | -0.051 | +0.116 / +0.219 / **0.31** | +0.020 / -0.103 | n843 **-0.190** |
| 0.56 | 1043 | 32.8% | 0.32 | +0.166 | +0.089 | +0.244 | -0.028 | -0.068 | +0.138 / +0.256 / **0.33** | +0.041 / -0.081 | n721 **-0.153** |
| 0.60 | 818 | 34.8% | 0.34 | +0.201 | +0.157 | +0.245 | -0.028 | -0.084 | +0.169 / +0.286 / **0.32** | +0.084 / -0.036 | n554 **-0.092** |
Days at 0.56 (9): -0.19 +0.07 +0.12 +0.30 -0.06 +0.36 +0.63 -0.05 -0.19 — 4 of 9 negative.

## Verdict (verify gates)
- grading PASS (venues.outcome), sample PASS, sweep PASS (monotone), halves PASS at theta>=0.50.
- **permutation FAIL**: shuffling the SIDES and paying the shuffled side's ask gives +0.12..+0.17 with p(>=real) 0.31-0.33.
  The money is "a cheap side bought at these moments", not the EF side pick (same mechanism as REVERSAL's +0.14 null).
- **costs FAIL**: +0.02 on the ask leaves +0.02..+0.08; +0.05 turns it negative.
- **paired FAIL**: 70% of EF's calls sit on REVERSAL's own candles and side; on the candles REVERSAL does not trade EF is
  **negative at every theta** (-0.09..-0.19). EF adds nothing REVERSAL does not already take.
- rain-or-sun FAIL: 4 of 9 days negative.
**The base port has no edge of its own on Polymarket over these 8 days.** REVERSAL remains the reversal catcher that
works (+0.46 replay, +0.69 real). What the stored data cannot test: the perp lane, the aged depth history and the online
learner (build11's real inputs); those exist live. Next test that costs nothing: Zurich SHADOW with `ef_engine=build11`
(full live features), graded on the venue, against v10 EF's known +0.22/$1 paper record. H1 is re-running this
independently (analysis/h1/REQUEST.md) including the harness-fidelity check on 09-15/16.

## RETRACTION 09-22 23:4x (V): REVERSAL +0.461/$1 is one ticket
H1 r40_late_reversal_depth.md, confirmed on V's own rows (replay_lanes_1s.py, both --open arms): the single biggest REVERSAL fill is +97.3/$1 at ask 0.010, sec 270 - unfillable at any real stake (300 shares at $3). Without it REVERSAL is **+0.249/$1** (n 456); without the top 3 +0.157..+0.185. Every "+0.46 replay" number quoted for REVERSAL is withdrawn; +0.25 is the replay figure. The late 240-285 s bucket is that one fire (other 55 net -0.77), so the executor's 240 s cutoff costs nothing measurable and stays. Mumbai real fills +0.689/$1 on 46 are a separate record and are not re-checked here for concentration.
