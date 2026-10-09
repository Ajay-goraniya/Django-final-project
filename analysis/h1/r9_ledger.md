# R-9 standing ledger — the cold-regime brain

One line per attempt. Message V only on a verdict change. Detail in the per-task file named.

| # | date | attempt | result | verify.py | verdict |
|---|---|---|---|---|---|
| 1 | 2026-09-15 19:5x | **stacked 2nd-stage brain** on frozen v10 (side from stage 1, confidence from stage 2; inputs ps, ev, ask, sec, rv60, taker, last3/last10, hour, regime; walk-forward by day; logit + lgbm) | Brier **0.1631 frozen vs 0.1635 logit / 0.1668 lgbm** — neither improves it. lgbm 54.7% hit on 698 fires but per-$1 **identical +0.131** and total **+91.52 vs +99.56**. logit fires 67 of 758. | logit: paired FAIL (7 discordant, p=0.453), null FAIL. lgbm: **halves FAIL, paired 29-vs-29 p=1.000**, null FAIL | **DOES NOT SHIP** |

**Run 1 also caught a leak worth keeping.** The first version accumulated `last3`/`last10` **per
tick**; since a candle is evaluated many times and every tick shares its label, later ticks saw
their own candle's outcome as "previous result". It printed **83.8% hit and +414 PnL** — caught
because the number was implausible, not because a check fired. Streaks are now per candle and
strictly earlier. **Any outcome-derived feature has this failure mode wherever the decision loop
evaluates a candle more than once** — `build11.streak_events` included.

Next in the program: **item 2, extend the labelled days backward.** Every negative result so far
has been decided on 5–8 days, and R-8 showed a retrain handicapped by exactly that.
