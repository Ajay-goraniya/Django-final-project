# R-12 step 3 — drawdown on the same four arms

User, 09-16 00:4x: *"now check the max drawdowns in same test that you just shown me."* Same rows,
same walk-forward-by-day fits, same EV fire rule, same grading as `r12s3_full_features.py`; the only
change is that per-fire PnL is kept as a chronological sequence instead of being averaged.
Script: `analysis/h1/r12s3_drawdown.py`. 5 tested days (09-10 .. 09-14), 25,704 rows.

**Units are $1 of stake per fire. The live stake is $10 flat — multiply every $ number by 10.**

| arm | fires | total | maxDD | worst-underwater | DD/total | longest losing run | recovered |
|---|---|---|---|---|---|---|---|
| frozen v10 (live) | 751 | +98.02 | 13.09 | **9.45** | 0.13 | 8 | yes |
| 8 days, 30 feats | 453 | +77.63 | 10.86 | 2.21 | 0.14 | 8 | yes |
| 8 days, 30 + p_hist | 480 | +85.99 | **9.88** | 1.00 | **0.11** | 8 | yes |
| p_hist alone (18) | 839 | +56.52 | **14.94** | 6.68 | **0.26** | 9 | yes |

- **maxDD** — worst peak-to-trough fall on the cumulative curve.
- **worst-underwater** — deepest the curve ever went *below zero* from a standing start. This is the
  bankroll number: it is what you must be able to lose before the strategy has ever made anything.
- **DD/total** — drawdown per unit of profit.

Worst stretch for each arm:

| arm | from | to | hours | fires | fall |
|---|---|---|---|---|---|
| frozen v10 (live) | 09-11 12:10 | 09-12 00:20 | 12.2 | 96 | −13.09 |
| 8 days, 30 feats | 09-12 05:35 | 09-13 04:55 | 23.3 | 81 | −10.86 |
| 8 days, 30 + p_hist | 09-12 05:10 | 09-12 16:00 | 10.8 | 52 | −9.88 |
| p_hist alone (18) | 09-12 22:10 | 09-13 12:35 | 14.4 | 103 | −14.94 |

Per-day PnL ($1 units) — every day, not the best one:

| arm | 09-10 | 09-11 | 09-12 | 09-13 | 09-14 | positive days |
|---|---|---|---|---|---|---|
| frozen v10 (live) | +18.69 | −0.10 | +23.40 | +15.37 | +40.67 | 4/5 |
| 8 days, 30 feats | +29.96 | +15.77 | +8.55 | +12.20 | +11.14 | 5/5 |
| 8 days, 30 + p_hist | +34.04 | +18.87 | +8.60 | +14.91 | +9.57 | 5/5 |
| p_hist alone (18) | −2.61 | +22.53 | +6.52 | −3.91 | +33.99 | 3/5 |

## Reading

1. **The history model is the worst arm on path as well as on level.** `p_hist alone` has the deepest
   drawdown (14.94), the worst pain-per-profit (0.26, double everything else), the longest losing run
   and the only losing days. Nothing here rescues it — it confirms the step-3 verdict from a second
   direction.

2. **Live v10 carries the largest bankroll requirement.** At the live $10 stake its curve was **$94.50
   under water** before it had made anything, and its worst stretch lost **$130.90 over 12.2 hours and
   96 fires**. That is the number to hold against it, and it is the only arm whose worst-underwater is
   large; the 8-day arms start winning almost immediately (2.21 and 1.00).

3. **The p_hist column still does not earn its place.** Arm 3 vs arm 2 is the only near-paired pair
   here (same recipe, one extra input): DD 9.88 vs 10.86 and DD/total 0.11 vs 0.14. That is a ~1-unit
   improvement, in the same direction as its +8.4 PnL and its +0.010/fire — and step 3 already showed
   that edge is **24 discordant pairs, McNemar p=0.541**. A drawdown that moves by 1 unit on n=480 is
   not evidence the paired test could not already see.

4. **Do not read the four maxDDs as a like-for-like ranking.** The arms fire on different candles
   (751 / 453 / 480 / 839), so their curves are different paths, not four versions of one path. Only
   arm 3 vs arm 2 shares most of its fires. Across different fire counts, DD/total is the fairer
   column and the raw maxDD is not.

5. **Five days is not a drawdown sample.** A worst case estimated from five days of one market regime
   is a lower bound on the real one, not a measurement of it. The honest statement is "at least 13
   units at the live model's fire rate over this window", not "the drawdown is 13 units".

**Nothing changes.** The step-3 verdict stands: the history model does not ship, alone or as an input.
Drawdown adds one fact that was not in the level numbers — the live model's equity path is the most
punishing of the four before it turns profitable.
