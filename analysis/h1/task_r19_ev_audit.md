# R-19 — the EV formula is correct. The fee constant barely matters. EV sorts price, not accuracy.

User: *"how can you be sure it's correct?"* Script `analysis/h1/task_r19_ev_audit.py`.

## 1. The formula is the engine's own — verified, not reconstructed

Recomputing `ev = ps·(1/cost(ask) − 1) − (1 − ps)` with `cost(q) = q/(1 − fee·(1−q))`, fee 0.07,
against the engine's **own logged `ev`** on 16,852 decision rows: **max |diff| 0.000126, median
0.000034.** And replaying the whole fire rule reproduces `r12_train.fire_set` exactly —
**1033 / 1033 / 1033 shared**. So the arithmetic in use is the arithmetic I have been testing.

## 2. Fees: V's observation is half right, and the half that is right does not matter

**Confirmed, two independent ways:** `fills.fees` is 0 on all 76 live fills, and `spent − shares×price`
is **0.0000000000** on all 76 — two fields that are not the same read. **No fee is taken at execution.**

**But `results.venue_fees` is non-zero on all 76 rows** (0.0896 … 0.2504, sum 12.13). Its semantics are
unresolved: not monotone in `venue_ts`, so not a cumulative counter; roughly constant per row, so not
obviously a per-trade charge. Recorded and **not concluded from**: that sum is 1.3% from the 12.29 a
7%-on-winnings model would charge on the same fills. **A fee exists somewhere.** Changing a live fire
constant on the strength of a field I cannot interpret is exactly the error this project keeps paying
for.

It is moot anyway. Replaying the fire rule with the constant swept, same `p`, same asks, PnL always
booked at the real model:

| fee_rate | fires | win% | per $1 | total |
|---|---|---|---|---|
| **0.07 (live)** | 1033 | 53.2% | +0.141 | **+145.81** |
| 0.05 | 1036 | 53.3% | +0.141 | +145.98 |
| 0.03 | 1041 | 53.2% | +0.140 | +145.63 |
| 0.00 | 1070 | 53.3% | +0.134 | **+143.84** |

Dropping 7% → 0% unlocks **37 candles out of 1033 (3.6%)** and total PnL goes **down**. The EV
distribution is not dense at the threshold, so the ~1.8c of extra edge we demand costs almost nothing.
**Recommendation: leave `fee_rate` at 0.07.** Not because it is certainly right, but because it is
worth ±$2 either way and the evidence for changing it is a field we cannot read.

## 3. The inversion explained: EV is a price sort with a forecast's name

Paper, poly_pnl n=1020, graded on `venues.outcome`, by EV quartile:

| Q | n | mean ev | mean ask | **win%** | per $1 |
|---|---|---|---|---|---|
| Q1 | 254 | 0.162 | 0.514 | **54.3%** | +0.016 |
| Q2 | 243 | 0.222 | 0.473 | **53.1%** | +0.072 |
| Q3 | 267 | 0.281 | 0.452 | **52.8%** | +0.126 |
| Q4 | 255 | 0.446 | 0.382 | **53.3%** | +0.349 |

The PnL ordering is perfect and monotone. **The win rate is flat — 1.5 points of spread, and it
points the wrong way.** What moves monotonically is the **ask: 0.514 → 0.382**.

`corr(ev, win) = −0.0338`. `corr(ev, ask) = −0.2387`.

**EV does not rank candles by how likely we are to be right. It ranks them by how cheap they are.**
The +0.016 → +0.349 gradient is payoff arithmetic: a win at 0.38 returns 1.55 per $1, a win at 0.51
returns 0.86. Same accuracy, better odds. Same story in `v10_poly_long4` (Q1 +0.001 → Q4 +0.298 on
flat win rates).

**That is the whole inversion.** On paper we book at the *quoted* ask, which the standing rule already
calls an upper bound. Live, we only *get* the cheap ask when the market is moving against the side we
picked — R-18 measured exactly this on the same book: orders that fill at a better price win **40.7%**,
the ones that do not fill win **99.1%**. So Q4, the quartile that looks best on paper, is the one most
exposed to the selection that live execution imposes. The live sample V cites (n = 12/49/8) is
insufficient on its own, but it has a mechanism behind it and the mechanism is measured.

**Said plainly, as the brief asks: EV is already a price-capture rule; it is not a forecast rule and it
never was.** Its paper gradient is real and its live gradient is that gradient minus adverse selection.
Rebuilding it "around price capture" would not change what it does — it would only make the objective
honest, and it would have to price the selection cost, which for the cheapest quartile is the largest.

I have not touched R-10's EV modes. The sweep does not move once the fee is right, because the fee
was never what was moving it.
