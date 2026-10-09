# Task 97 — how drawdowns can be stopped (signal side only). Standing, 4-hourly.

## 2026-09-16 00:5x UTC — first pass: INSUFFICIENT, no verdict

Data actually on this box, all journals pooled (paper 8787 12.9.0, paper 8793 12.8.11, twin_1290,
live archive to 09-14 01:03, live 09-14 01:03→23:47): **152 graded results.**

(1) Loss runs ≥4 same-side: **1** in 152 results — live archive, UP, length 4, starting epoch 1789300500.
n=1. Nothing can be said about when they start (hour, rv60, prior-15m/1h return, candle streak) or how
long they last from a single run. INSUFFICIENT.

(2) Fires inside a run vs outside: 4 fires inside, 148 outside. Every cell of any book/Binance grid built
on this would be n≤4. INSUFFICIENT — not computed rather than computed and caveated.

(3) Candidate features: none tested. A walk-forward with halves needs ≥60 graded fires per arm per
CLAUDE.md; the run arm has 4.

**What would make this answerable:** the two paper engines produce ~20 graded results/day between them
(8787 n=18, 8793 n=10 since 20:45/22:36 UTC). At that rate a ≥60-fire run arm is weeks away from paper
alone. The live archive is the only dense source and it is closed. No engine change proposed.

## 2026-09-16 11:50 UTC - pooled dense lanes (V's addendum), 2,541 graded fires, 7.6 days

Pool: poly_pnl 1060 + v10_long4 778 + v12_lane 620 + zurich_2 83, graded on `venues.outcome`
(2,519 of 2,541 oracle-graded), 09-08 17:35 -> 09-16 08:50 UTC, overall win 52.6%.

(1) **Loss runs >=4 same-side: 19, covering 79 fires (3.1%), -$716.62.** Lengths 4x17, 5x1, 6x1.
Those 19 collapse to **10 distinct (epoch, side) starts** - 8 of them appear in more than one lane
on the same candles, so the independent-event count is 10, not 19. Start hours spread across 9
different UTC hours, 13 DOWN vs 6 UP, rv60 at the start 0.14-1.27 with no clustering. **Nothing in
the calendar or the volatility state marks a run before it begins.**

(2) Fires inside a run vs outside, biggest median gaps in pooled SD: imb5 -0.630 vs -0.136 (0.65 SD),
imb20 -0.679 vs -0.199 (0.63), basis_bps -5.01 vs -4.52 (0.58), pos_in_range 0.326 vs 0.524 (0.46),
ofi15 -0.242 vs -0.070 (0.27). p at the fire is identical (0.594 vs 0.591), so this is not a model
confidence story - it is the book leaning away from the side we take. That comparison is in-sample
by construction (a run IS a loss streak), so it only nominates features; the test below decides.

(3) **Walk-forward, thresholds fixed on the first half (09-08..09-12, n=1269), measured on the
second (09-12..09-16, n=1272).** Sign the feature by our side: `s = f if side==UP else -f`.

| gate (s >= thr) | fires | stake $ | pnl $ | pnl/$1 | runs>=4 | run fires | longest | max DD $ |
|---|---|---|---|---|---|---|---|---|
| none | 1272 | 12139 | 1961.26 | +0.1616 | 8 | 35 | 6 | -387.77 |
| ofi15 >= 0.00 | 919 | 8714 | 1724.01 | +0.1978 | 4 | 17 | 5 | -375.26 |
| pos_in_range >= -0.20 | 1070 | 10273 | 1804.11 | +0.1756 | 3 | 12 | 4 | -346.64 |
| **both** | **781** | **7467** | **1608.74** | **+0.2154** | **0** | **0** | **0** | **-297.30** |

Stability on the held-out half: the pair gate improves 4 of 5 days (09-12 +0.131->+0.156,
09-13 +0.131->+0.242, 09-14 +0.282->+0.320, 09-15 +0.273->+0.318) and **fails on 09-16**
(-0.273 -> -0.348, n=99). It improves all four lanes (poly_pnl +0.172->+0.221, v10_long4
+0.124->+0.194, v12_lane +0.174->+0.220, zurich_2 +0.018->+0.208). The 491 fires it drops were
still net positive at +0.069/$1, so it is trimming low-yield fires, not cutting losers out.

**VERDICT (changed):** the drawdowns are a book-imbalance phenomenon, not a time-of-day, volatility
or model-confidence one. A signed order-flow-imbalance + position-in-range pair gate, fitted on the
first half only, removed every >=4 loss run from the second half and cut peak-to-trough from
-$387.77 to -$297.30 (-23%) while raising pnl per $1 from +0.1616 to +0.2154 - at the cost of 39%
of fires and $353 of total pnl. **Sample caveat: 8 runs -> 0 runs is 8 events, far under the 60 bar,
and the gate was picked from a 6-value grid on two features, so the run-count line is INSUFFICIENT
on its own.** The pnl/$1 line rests on 781 held-out fires and is not. Nothing changes on any engine
without V.

---
**Standing note (V, 09-17): this gate does NOT ship.** Routed to H1 as R-25 - "no gates" is a binding
user rule ("EF should know when to fire and it cannot be decided by a gate... give it a trained brain
that knows that move is wrong and it will reverse"; four such attempts already failed on 09-10). Filed
for the record, not as a live proposal.
