# Task 15 part 2 — the distance premise on 72,576 candles
H1, 2026-09-11 00:05 UTC. V's task (REQUEST.md 23:55). Engine grading, description only, no gates.

Data: `paths.npz` — 252 days of real Binance spot 1s closes (2026-01-01 .. 09-09), **72,576
five-minute candles**. Buckets fixed in advance (V's): |price(S) − open| in bps —
`<1, 1–2.5, 2.5–5, 5–10, 10–25, 25+`. Cells under 60 candles are printed `--`, never read.

`P(same)` = probability the candle closes on the side the price is **already on** at second S.
0.50 means the lead at second S tells you nothing.

## Answer to V's question: it is the market, not one regime

**Tokyo's 250 fills were right, and the effect is a smooth monotone law.** P(same) rises with
distance in **every single row**, at every second, in both halves, in all four regime quartiles.

| sec | <1 | 1–2.5 | 2.5–5 | 5–10 | 10–25 | 25+ |
|---|---|---|---|---|---|---|
| 15 | 0.526 | 0.582 | 0.630 | 0.656 | 0.704 | 0.723 |
| 20 | 0.527 | 0.581 | 0.634 | 0.681 | 0.717 | 0.774 |
| 30 | 0.526 | 0.593 | 0.639 | 0.698 | 0.748 | 0.817 |
| 45 | 0.527 | 0.594 | 0.659 | 0.715 | 0.782 | 0.876 |
| 60 | 0.544 | 0.595 | 0.666 | 0.740 | 0.806 | 0.885 |
| 90 | 0.541 | 0.618 | 0.688 | 0.769 | 0.848 | 0.921 |
| 120 | 0.555 | 0.631 | 0.711 | 0.792 | 0.876 | 0.945 |

n per cell runs 1,400–32,000 early; the smallest read cell is 101.

**Tokyo's numbers reproduce almost exactly.** Tokyo's 33 fills said `<1 bps` = 51% and `1–2.5` = 61%.
The 72k set says **0.53** and **0.58–0.63** at the early seconds. That is the market, not a regime
and not a small-sample accident.

**It holds in every regime** (Task 13 trailing-12-candle range quartiles, cut at 8.6 / 13.0 / 19.8 bps).
At S=60 the `<1` cell is 0.557 / 0.534 / 0.521 / (Q4) and the `5–10` cell is 0.850 / 0.792 / 0.754 —
the *level* shifts with regime (calm tape is more predictable) but the **monotone ordering never
breaks**. Both halves agree throughout: at S=60, `<1` is 0.548 vs 0.541 and `10–25` is 0.797 vs 0.820.

## Late seconds — and a correction to the premise in the brief

| sec | <1 | 1–2.5 | 2.5–5 | 5–10 | 10–25 | 25+ |
|---|---|---|---|---|---|---|
| 237 | **0.614** | 0.710 | 0.820 | 0.911 | 0.975 | 0.994 |
| 270 | **0.670** | 0.783 | 0.876 | 0.956 | 0.992 | 1.000 |
| 290 | **0.772** | 0.876 | 0.936 | 0.981 | 0.998 | 1.000 |

V asked: *"is P(same side) in that bucket really ~50% on 72k candles?"* — **No. It is 0.614 at
t=237**, and both halves agree (0.611 / 0.617). It is not a coin flip late in the candle.

**So Task 14's 0.494 is not a Binance-structure fact, and I could not explain it away.** I had an
obvious candidate explanation — that Task 14 bucketed on |close − open| (the *final* move, not
knowable at fire time) while this task buckets on |price(S) − open| (observable live) — so I tested
both conditionings on the same 72k candles:

| t=237, <1 bps bucket | n | P(leader wins) |
|---|---|---|
| bucketed on \|price(237) − open\| (observable) | 9,176 | 0.614 |
| bucketed on \|close − open\| (not observable) | 8,399 | **0.595** |

**The two conditionings agree.** My explanation was wrong and I am not offering it. The gap between
0.595 here and 0.494 in Task 14 is real and unexplained, with two candidates I cannot yet separate:

1. **Task 14 measured the *venue's* favourite** (the side with implied ≥ 0.5 from the Predict.fun
   ask), not the Binance price leader. If the venue's favourite drifts off the Binance leader
   precisely in near-zero candles, that is a venue fact and would tie directly to Task 14's main
   result — the two oracles disagree most exactly there.
2. **Noise.** Task 14's cell is n=77; the standard error is ~5.7 pp, so 0.494 against 0.595 is about
   1.8 SE. Suggestive, not decisive.

These are separable once the 09-10 klines are in: compare the venue's implied favourite against the
Binance price leader at t=237 on the same candles. That is queued.

## What this does and does not say

It says the market gives a **smooth, monotone, regime-stable** relationship between how far price has
moved at the fire second and how likely that direction is to hold. It is one of the cleanest
regularities in any H1 study — a genuine premise, on the largest sample available.

It does **not** say to gate on it, and no threshold is proposed. Per the brief this is description
only, and "under 1 bps is a coin flip" is a fact about the tape, not a rule.

## Limits

- 252 days of Binance spot; the venue's own behaviour is only observable on the 54.7 h venue window.
- `25+` cells are thin at early seconds (n=101 at S=15) and Q4/Q1 tails are marked `--` where n < 60.
- P(same) treats an exactly flat close as UP, matching the engine's `close >= open` convention.

Repro: `analysis/h1/task15_distance_premise.py`. Parts 1 and 3 (REST backfill and Task 11.2) follow
separately — the REST route is unblocked, see STATE.md.
