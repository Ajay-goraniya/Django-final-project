# Task 18 — does 11.2 transfer to Polymarket?
H1, 2026-09-11 02:45 UTC. V's task (REQUEST.md 02:25); the user is weighing the platform.

**Grading is the substance of this task, so every number below is labelled.** Trading Predict.fun
grades on the engine's candles (Binance close ≥ open). Trading **Polymarket grades on Polymarket's
own resolution** — it settles on a Chainlink 60-s TWAP, so its `outcome` table is the settling
source here. **This is the one place that table is correct.** On these 648 candles the two
resolutions disagree on **68 (10.5%)**.

## Headline: 11.2 does NOT transfer. The current EF fire set does.

### The frozen 11.2 model at Polymarket asks, 7% taker fee

| margin | n | **graded POLYMARKET (settling)** | graded engine (contrast) |
|---|---|---|---|
| 0.10 | 352 | 45.5% hit, **−0.024** | 56.0% hit, +0.272 |
| 0.15 | 279 | 41.9% hit, **−0.042** | 54.5% hit, +0.318 |
| 0.20 | 230 | 42.2% hit, **−0.007** | 56.1% hit, +0.407 |
| 0.25 | 193 | 39.4% hit, **−0.029** | 56.0% hit, +0.466 |
| 0.30 | 174 | 36.8% hit, **−0.063** | 54.6% hit, +0.480 |
| 0.40 | 135 | 36.3% hit, **−0.025** | 54.8% hit, +0.585 |

**Negative at every margin on the settling source.** Note the hit rate: **36–45%, i.e. below
random.** That is not indifference, it is anti-correlation, and the mechanism is clear:

> 11.2 predicts the **Binance close**. Polymarket does not pay on the Binance close — it pays on a
> Chainlink TWAP, and the two differ on 10.5% of candles. The model fires precisely where it
> **disagrees with the Polymarket ask**, and the Polymarket ask is correct about Polymarket's own
> resolution. So the fire rule selects, almost by construction, the candles where the model's
> target and the payout disagree.

The engine-graded column confirms the model is not broken — it is still right about Binance close
(54–56%) and would still earn +0.27 to +0.59 if Polymarket paid on that. It doesn't.

**Staleness makes it worse** (margin 0.15, Polymarket grading): +0c −0.042 · +5c −0.157 ·
+10c −0.256. On Polymarket the signal *is* the venue's own price, so the quote can be gone on
arrival — this is the more punishing venue for a late fill, not the more forgiving one.

### The current EF fire set at Polymarket asks — this one transfers

| margin | n | **graded POLYMARKET (settling)** | graded engine (contrast) |
|---|---|---|---|
| 0.10 | 95 | 57.9% hit, **+0.174** | 58.9% hit, +0.195 |
| 0.15 | 69 | 59.4% hit, **+0.281** | 60.9% hit, +0.310 |
| 0.25 | 35 *(n<60)* | 57.1% hit, +0.396 | 60.0% hit, +0.457 |

**Positive under *both* gradings**, both halves positive (+0.230 / +0.330 at margin 0.15), monotone
sweep. And the reason is the mirror image of 11.2's failure: **EF's signal already is Polymarket**,
so it is aligned with the venue that pays.

`verify.py` on this claim returns **FAIL on grading provenance** — correctly, because two outcome
sources disagree by 10.6% and the harness is conservative. The honest resolution: for a Polymarket
trade the settling source is Polymarket's resolution, and **the claim is positive under both
gradings**, so the disagreement does not change the conclusion. Every other check passes (sample,
halves, sweep, cost, beats the v10 paper run's +0.148).

## What this means for the platform decision

1. **A model trained on Binance close is a Predict.fun model.** It does not become a Polymarket
   model by paying Polymarket's prices. If we want 11.2-style modelling on Polymarket, it has to be
   **retrained against Polymarket's own resolution** — that is a new artifact, not a redeploy.
2. **The thing that already transfers is the existing EF signal**, because it is Polymarket-derived
   in the first place. On this window it does better at Polymarket prices (+0.281/fire, n=69) than
   the same fire set does on Predict.fun (+0.049/fire, n=220 — Task 16).
3. That is consistent with V's v10 Polymarket paper run (+0.148 after the real taker fee), and
   points the same way: **the Polymarket-native signal is the one worth testing on Polymarket.**

## Limits

- 648 candles, ~2.3 days, one regime. The `n<60` rows are marked and not read.
- Polymarket asks are the collector's 5-second samples, forward-filled; `book1s` does not carry
  Polymarket yet, so sub-5s timing is invisible here.
- The EF cost row is non-monotone (+0c +0.281, +5c +0.199, +10c +0.260) because the haircut also
  changes *which* fires clear the margin — the +10c cell is a different, smaller set, not the same
  trades priced worse. Do not read it as "slippage helps".
- Fee model: `0.07 × p × (1−p)` per share ⇒ `0.07 × (1−ask)` per $1 staked. Makers free; everything
  here is priced as a taker.
- **This says nothing about whether 11.2 works on Predict.fun.** That result stands and its forward
  test (Task 17) is unaffected.

Repro: `analysis/h1/task18_polymarket_transfer.py`.
