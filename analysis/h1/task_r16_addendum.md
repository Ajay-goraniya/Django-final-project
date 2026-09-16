# R-16 addendum — the book/trade-inferred split, and what the venue reference actually is

Answers V's addendum (09-16 01:3x): confirm the 17,449 / 4,117 split and its effect on the
venue-stage evidence; entry-time-only reference distance; the Chainlink backfill question.

## 1. Correction to my own wording: they are not "synthetic"

In `task_r12_pipeline_check.md` I called the 17,449 rows "synthetic book". That is wrong and I am
retracting the word. `learner/build_features.py:47` sets `is_book=1` only when
`quote_source == "book"`; everything else is **`trade_inferred`** — the ask/bid inferred from the
trade tape. It is still the market's own price, derived from prints rather than from a resting
touch. Nothing is model-generated. The distinction matters because "synthetic" implies a fabricated
number and would have overstated the problem.

## 2. The split is confirmed, and the sharper fact is worse than the ratio

22,720 rows, 21,566 with `p_venue`: **4,117 book / 17,449 trade-inferred**, as reported.

| date | rows with p_venue | book | trade-inferred |
|---|---|---|---|
| 2026-08-29 | 2,880 | **0** | 2,880 |
| 2026-08-30 | 2,822 | **0** | 2,822 |
| 2026-08-31 | 2,246 | **0** | 2,246 |
| 2026-09-02 | 2,476 | 1,707 | 769 |
| 2026-09-03 | 2,812 | 2,363 | 449 |
| 2026-09-04 | 2,880 | 47 | 2,833 |
| 2026-09-05 | 2,880 | **0** | 2,880 |
| 2026-09-06 | 2,570 | **0** | 2,570 |

**Five of v10's eight training days contain no real book quote at all**, and a sixth has 47 rows.
The entire book contribution to v10 comes from two days.

## 3. It is a property of the rows, not of those days, and not of the clock

On the three days that carry both sources:

| source | n | model acc | price acc | diff | discordant | McNemar p |
|---|---|---|---|---|---|---|
| **book** | 4,117 | 0.7411 | 0.7236 | **+0.0175** | 430 (251 v 179) | **0.0006** |
| trade-inferred | 4,051 | 0.7522 | 0.7554 | −0.0032 | 281 (134 v 147) | 0.4741 |

Same days, so the day is controlled. The obvious null — that trade-inferred rows are simply later in
the candle, where everything scores higher — is also ruled out: mean offset 108.0 s vs 120.4 s (the
*book* rows are later, not earlier), and matched offset by offset the weighted means are unchanged,
**+0.0175 book / −0.0032 trade-inferred over 10 readable buckets each**. The book edge also grows
with the clock (+0.005 at 15 s → +0.059 at 240 s) while the trade-inferred edge stays at ~0 at every
offset.

Read plainly: **the model beats the book *touch*, and does not beat the trade *print*.** The touch
goes stale as the candle resolves; the print keeps up. That is a microstructure fact about the quote
source, not a forecasting edge.

## 4. What this does to the venue-stage evidence

**What it damages.** *(Corrected — see `task_r17_executable_rows.md`. I originally wrote that
`p_venue` is v10's largest coefficient at 1.663. That was wrong: 1.663 is **`move_bps`**, rank 1;
`p_venue` is **−0.0387, rank 16 of 30**. The venue enters through **`lv` = logit(p_venue), +1.5514,
rank 2** — so the substance holds, through a different coefficient than I named.)*
The venue is v10's second-largest input, and **81% of the venue values it was fitted on are trade
prints, not executable quotes, and five of eight days have no book at all.** That is a train/serve mismatch: live, `p_venue` is a real book
touch. And the direction of the mismatch is not neutral — v10's calibration was dominated by exactly
the rows where the price is already as good as the model, which would push the fit to lean *harder*
on `p_venue`. That is consistent with R-13's result that `p ≈ p_venue` and is a plausible mechanism
for it.

**What it does not damage.** R-13, R-12 stage B2 and every R-12s3 arm were measured on the **logged
Polymarket window**, where `p_venue` comes from a live book. Those verdicts are unaffected and stand.

**What it re-labels.** The pipeline check's "v10 beats the book by +1.75pp inside its own training
window" is now precisely located: it is on a **Predict.fun-era book touch**, on **two days**, and it
does not transfer to the live Polymarket book (same test there: **p = 0.937**). I already marked it
NOT A FINDING on sample grounds; this says *why* it was never going to transfer.

## 5. Entry-time-only reference distance (the addendum's first ask)

Already the only version R-16 measured, because "disagreement" is a property of the close and no
engine can see it. The entry-time observable is `|move so far|`:
`corr(|move so far|, |move at close|) = 0.4319`; conditioning on `|move so far| < 1 bps` lifts
`P(|close move| < 2 bps)` from **0.279 to 0.335**. That is the ceiling on any entry-time distance
feature, and it is why R-16 proposes none. Labels were verified against the venue outcomes
independently: `poly_pnl.actual` vs `venues.outcome` **1,019 agree / 0 disagree**. Per-day tables in
`task_r16_settlement_ref.md` are chronological and priced on the lanes' own executable quotes.

## 6. Chainlink backfill: reachable, and the data says do not bother

A public RPC is reachable from this container (`rpc.ankr.com/polygon` → 200; `polygon-rpc.com` → 401,
`eth.llamarpc.com` → 525), so a backfill of on-chain rounds is technically possible.

**The disagreement pattern already rules out a Chainlink-resolved market.** Chainlink BTC/USD updates
on a ~0.5% deviation threshold or a long heartbeat, so a 5-minute candle would very often open and
close inside the *same round* — disagreement with Binance would be large and would not be confined to
near-ties. What is observed is the opposite: 43.3% disagreement at |move| < 1 bps falling to ~1% above
5 bps. Fitting "venue reference = Binance close + N(0, σ)" gives **σ = 3.16 bps**, but that single
Gaussian is rejected by its own fit — it over-predicts the middle (1–2 bps: 32.3% predicted vs 24.2%
observed) and under-predicts the tail (10–20 bps: 0.01% vs 1.58%). The honest reading is a small
timing/composite difference of order 1–3 bps, **plus a ~1.5% floor of disagreement that survives at
large moves — about 6 candles in 2,036, which is `insufficient` and must not be reasoned from.**

So: **the reference is a Binance-equivalent spot price a few basis points away, not a different
oracle family.** Mumbai's Task 98 logger is still worth having for provenance, but it will not
produce a feature, and a historical backfill would buy a number I have already bounded. If those ~6
large-move disagreements grow into a readable cell (≥60), that is the one thing that would reopen
this, and it is worth a standing count rather than a backfill.
