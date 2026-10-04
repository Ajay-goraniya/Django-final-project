# Task 15 part 3 — where the current model's fires actually land
H1, 2026-09-11 00:52 UTC. V's question: *does the retrained model's fire set avoid the sub-1-bps
coin flips on its own, or does it inherit the current model's 46%?* This establishes the baseline
that question needs, and answers it for the **current** model. 276 of 282 Tokyo filled orders
matched to klines (the set now runs through 09-10 via the REST route).

## The answer: the current model does not avoid the coin flips — it prefers them

**82% of EF fires land under 2.5 bps of movement**, the region where the tape is least informative.

| bps at fire | EF fires | share | all candles at the same second | ratio |
|---|---|---|---|---|
| <1 | 120 | **47%** | 41% | **1.15×** |
| 1–2.5 | 89 | **35%** | 27% | **1.27×** |
| 2.5–5 | 40 | 16% | 19% | 0.81× |
| 5–10 | 5 | 2% | 10% | **0.20×** |
| 10–25 | 2 | 1% | 3% | 0.30× |

The engine is **over-represented** in the two flattest buckets and fires at **one fifth** the base
rate in the 5–10 bps band — the band where Task 15 part 2 showed direction is most predictable
(P(same side) ≈ 0.70 at the median fire second, against ≈ 0.53 under 1 bps).

This is a **counting fact about the fire set**, independent of any outcome label, and it holds in
both halves (88% then 75% of fires under 2.5 bps). It is the honest answer to V's question:
**there is no avoidance to inherit — the current model concentrates in the flat region**, so a
retrained model that merely matches it will inherit that concentration.

## What I could NOT establish, and a caveat that applies to my other work

My first pass said EF beats the trivial "follow the move already underway" rule by **+5.0pp** inside
the `<1 bps` bucket (52.5% vs 47.5%, n=120, both halves +5.0pp). `verify.py` failed it on grading
provenance, and the failure was real:

**Tokyo's venue-reported `actual` and my Binance-spot-derived close disagree on 2.18% of orders
(7 of 321) — and every disagreement is in a candle under ~1 bps.** Inside the `<1 bps` EF bucket the
disagreement is **2.5%**, against 1.5% outside it. My Binance spot feed is not a perfect proxy for
what the venue settles on, and the mismatch is concentrated exactly where this claim lives.

Re-graded on **Tokyo's own labels** — the settling source, which V verified against `financial_result`
on 264 fills — the edge drops:

| grading | EF | follow-the-move | edge | halves |
|---|---|---|---|---|
| Binance close (mine) | 0.525 | 0.475 | +5.0pp | +5.0 / +5.0 |
| **Tokyo venue (settles)** | 0.533 | 0.500 | **+3.3pp** | **+5.0 / +1.7** |

**+3.3pp on 120 fires with a second half of +1.7pp is inside noise.** So: **not established.** I am
not claiming EF has skill in the flat bucket, and I am not claiming it lacks it — the sample cannot
tell. It needs roughly 400+ flat-bucket fires to separate +3pp from zero.

**The caveat travels.** Every kline-graded H1 number in the `<1 bps` bucket — including Task 15
part 2's `<1` cells on the 72,863-candle set — carries ~2.5% label error relative to what the venue
actually pays. It does **not** overturn part 2's distance premise: that effect runs 0.53 → 0.82
across the buckets, far larger than 2.5%, and the monotone ordering is untouched. But the flattest
cell is the least trustworthy one in all of my work, and should be read that way.

## Not read (n < 60)

The `2.5–5` cell shows EF at 45.0% against a 70.0% null — **−25pp** — which would be a serious
result if it were real. **n=40, under the bar.** I am marking it, not reading it. It is the single
most valuable cell to revisit as fills accumulate, because it is the one that would say whether the
engine actively fights real moves.

REVERSAL: n=20 total, insufficient throughout; it agreed with the move on 100% of its fires, which
at n=20 says nothing.

## Limits

- 256 EF fills over ~2 days of live trading, one regime.
- Distance is measured from the Binance path at the recorded `seconds_into_candle`; the engine's own
  `signal_price` may differ slightly from the 1s close at that second.
- The market-baseline comparison uses the EF median fire second (19–20 s) for all candles, so it is a
  like-for-like share comparison, not a per-fire match.

Repro: `analysis/h1/task15_part3_fire_profile.py`. Kline set extended through 09-10 by
`analysis/h1/append_day.py` + `fetch_rest_klines.py` (72,863 candles).
