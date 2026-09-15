# Task R-5 — dynamic staking as a trained model. Pass 1: DOES NOT SHIP.

V, 09-15 02:2x: R-4 closed the fixed-bucket version; the user's direction is the same as for EF —
not a gate, a trained brain. Standing task, re-run at every +100 graded live fires.
Script `analysis/h1/task_r5_kelly_sizing.py`. Ledger `analysis/h1/r5_ledger.md`.

**Verdict: does not ship. Stake stays fixed 3.0.**

## Build

Walk-forward ridge on per-$1 PnL from inputs known at fire time (`p`, `ev`, `ask`, `sec`, `rv60`,
lane), fit on the **first half by time**, used to size the **second half**. Sizing = fractional
Kelly (0.25) on the model's predicted edge, capped at 3× the fixed stake. Polymarket lanes graded
on `venues.outcome`. 1,543 paper trades (v10 777 + v12 766). **All paper fills are at the quoted
ask — an upper bound, never a live number.**

## V's ship condition: same trades, more money

| | staked | total PnL | per $1 |
|---|---|---|---|
| fixed-3 | 2,316 | **+405.75** | +0.175 |
| Kelly (capped) | 98 | **+24.24** | +0.248 |

**No.** It is behind by **−381.51**, and it gets the higher per-$1 by staking **4% of the capital**.
Per $1 is the wrong scorecard for this lane: the binding constraint is the number of 5-minute
candles, not capital, and the unused 96% has nowhere else to go inside the same candles.
Trades better/worse: 343 / 429 — more of the book is made worse than better.

## The steelman: same total capital, let it lever up

Rescaled ×23.7 so both books stake 2,316 in total: **normalised Kelly +573.72 vs fixed-3 +405.75 —
it wins by +168 on paper.** What that costs:

- **339 of 772 trades get a zero stake.** That is a **gate on 44% of the book** — the exact shape
  the standing rule bans — not a sizing curve.
- Max single stake **$31 vs $3**; largest single-trade loss **−$22 vs −$3**.
- Median stake **$0.81**: most of the book is sized to almost nothing anyway.

## The ablation that decides it

Refit with `ask` removed:

| model | per-$1 delta vs flat |
|---|---|
| all features | **+0.073** |
| **`ask` removed** | **−0.146** |

The learned weights say the same thing (standardised): `p` +0.329, **`ask` −0.292**, `ev` −0.086,
`rv60` −0.087, `sec` −0.012. **The entire gain is the ask coefficient.** The model re-learned R-4's
result — cheap quotes pay more per $1 — which is a price effect, not an accuracy effect, and it
carries R-4's quote-age failure unchanged.

Per-lane, the same shape: v10 alone **−0.039** (it does not even help there), v12 alone +0.118 with
an `ask` weight of **−0.900**, the largest in the whole study.

## Verification, second half only

| check | result |
|---|---|
| sample size | PASS — n=772 |
| both halves | PASS — +0.050 / +0.096 (per $1 staked) |
| beats the null | PASS — +0.248 vs +0.175 fixed-3 |
| **quote age** | **FAIL** — ffill, max 10.0 s, unchanged from R-4 |
| **paired test** | **FAIL** — no discordant pairs |

**VERDICT: NOT A FINDING.**

On `paired()`: sizing never changes *which* trades are right — both rules take the same trades and
differ only in how much. So the paired accuracy test has no discordant pairs and no information
here. It is reported failing for that reason, not because the two rules tie. The informative
paired statistic is the per-trade PnL difference, which is 343 better / 429 worse.

## Live fills: cannot be scored at all

78 graded live fills exist (`r3_submissions.csv`). The live journal records **no `p`, no EV and no
`rv60`**, so this model cannot be run on them — not "did badly", *could not be run*. Until the live
journal carries the feature vector, every number above is paper-only, and R-3 measured what paper
is worth live: **+0.004 per $1 at the price actually paid vs +0.038 at the quote.**

## What would change the verdict

1. The live journal recording `p`, `ev` and `rv60` per fire, so the model can be scored on real
   fills instead of quoted ones.
2. 100+ graded live fires per re-run, per the standing schedule.
3. An ablation where the edge survives removing `ask`. Until then this is the R-4 artifact with a
   regression on top.

**Until it passes: stake stays fixed 3.0.**
