# R-16 retrain — the line was wrong, the fix is real, and it does not ship. Here is why.

Spec: engine 12.11.1 (`learner/v12_2`), `open_reference="twap60"`, train == serve.
Script `analysis/h1/r16_retrain.py`. 32,014 logged ticks over 7 days; walk-forward by day; training
label = `TWAP60(end) ≥ TWAP60(open)`; **PnL graded on `venues.outcome`**, the oracle Polymarket
settles on. Label agreement rule-vs-venue on these rows: **0.9554**.

Features: 30 recentred + `ref_open_bps` + `ref_move_bps` = 32. Two of the four offered extras were
excluded on purpose — `ref_gap_bps` is *exactly* `move_bps` once the open is the TWAP line, and
`ref_src` is 0 on every historical row and will be 1 in live serving, i.e. out of range by
construction, which would ship into live money. Parity against the running artifact first:
reconstructing the engine's own `move_bps` from my 1 s grid on the same first-trade line gives median
difference 0.0000 bps, p90 |diff| 0.81 bps, corr 0.9893.

**Recentring flips the sign of `move_bps` on 14.18% of ticks.** It is not a cosmetic change.

## The result

| arm | fires | hit% | per $1 | total | maxDD |
|---|---|---|---|---|---|
| frozen v10 (live) | 758 | 52.6% | +0.131 | **+99.56** | 14.09 |
| recipe, old centring | 448 | 50.4% | +0.170 | +75.96 | 14.24 |
| recipe, **twap60 line** | 487 | 50.3% | +0.145 | +70.67 | 14.04 |

verify.py on the candidate vs frozen v10: **NOT A FINDING** — halves flip (**+0.100 / −0.137**),
paired 311 discordant **155 vs 156, exact McNemar p = 1.000**, and it loses to the null (+70.67 vs
+99.56). Per day it is +0.601 / +0.047 / +0.132 / +0.058 / +0.063 against frozen v10's
+0.127 / −0.000 / +0.153 / +0.126 / +0.264 — the whole margin is 09-10.

And the telling comparison is not against v10 at all: **the twap60 arm ≈ the old-centring arm**
(+0.145 vs +0.170, 487 vs 448 fires). Fixing the line changed almost nothing *through the model*.

## Why — and this is the useful part

Score `p_venue ≥ 0.5` against three different labels on the same 32,014 ticks:

| scored against | p_venue | frozen v10 |
|---|---|---|
| `venues.outcome` (truth) | **0.7498** | 0.7496 |
| `TWAP60(end) ≥ TWAP60(open)` | **0.7453** | 0.7512 |
| `close ≥ open` (what the engine labels on) | **0.6839** | 0.6939 |

**The book has been pricing the TWAP rule the whole time.** The venue price is 6.6 points more
accurate against the settlement rule than against `close ≥ open` — it was never confused about which
line the market settles on. Only our label was.

And because `p ≈ p_venue` (R-13), **frozen v10 already inherits that**: it scores 0.7512 against the
TWAP rule while its own training label scores 0.6939. v10 is effectively forecasting the settlement
rule already — through the price, not through its features.

The naive-line correction is still real and large:

| rule, scored on `venues.outcome` | accuracy |
|---|---|
| `sign(move_bps)` — open line | 0.7069 |
| `sign(move_bps)` recentred — TWAP line | **0.7321** |

4,540 discordant ticks, TWAP right 2,673 vs open 1,867, **McNemar p ≈ 5e-33**. But 0.7321 is still
below the book's 0.7498, and the model reaches the book's number for free. **Correcting the line
closes a gap the model had already routed around.**

## Verdict

1. **Mumbai's rule is right and my earlier "no feature there" was wrong** — that retraction stands
   (`task_r16_twap_rule.md`, 96.66% vs 86.81%).
2. **The retrain does not ship.** verify.py fails three gates; the candidate loses $29 to the model
   it was meant to replace on the same window.
3. **The mechanism is R-13, for the fifth independent time.** R-3, R-4, R-5, R-6, R-8/R-9, R-10,
   R-12 B2, R-15, and now R-16 all die the same way: anything that improves the *direction forecast*
   cannot help, because the output is pinned to a price that is already at least as good.
4. **What should still change**, independent of any model: the engine's own `candles.actual` /
   training label is `close ≥ open`, which is **13.2% wrong** about how the market settles. That is a
   correctness fix for grading and for every future retrain, worth making whether or not a model
   ships on it. It is not a signal edge.
5. **Where an edge could still be:** the residual between 0.7321 (best naive line) and 0.7498 (book)
   is small, but the gap between the book and *perfect* is 25 points. Nothing in the feature set has
   ever closed any of it. On this evidence the direction forecast is finished as a line of attack.
