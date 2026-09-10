# H1 — Task 7: intra-candle reversal tree (pass 1 of an ongoing task)

**Status: promising but NOT shippable. It fails V's ship rule on sample size (79 kept fires vs the
100 required), and its gain is concentrated in one half of the sample. Do not gate Tokyo on this.**

Built per the user's 12:47 correction: **continuous, every second, no fixed offsets.**

## Data and method

- **20,448 real 5-minute candles** (20,317 graded) from Binance spot BTCUSDT **1-second** klines,
  2026-07-01 → 09-09, 71 days. Real prints only — no synthetic paths, no resampling.
- Path encoding: `sign(price − open)` at every second 0..299, carried through zeros so a "crossing"
  is a genuine side change. Features at time t: current side, signed distance from open (bps),
  crossings so far (capped 6), log seconds since last crossing, realised range so far (bps), t/300.
- **Walk-forward only.** For the market tables, fit on the first half of days and evaluate on the
  second. For the fire replay, fit **only on candles strictly earlier than the first real fire** —
  19,959 candles, zero leakage into the replay.
- Code: `analysis/h1/build_paths.py`, `analysis/h1/tree.py`.

## 1. The base rates the user asked for — P(it flips again), every second

| t (s) | P(side at t == close) | **P(flip)** | mean crossings so far | mean \|dist\| bps |
|---|---|---|---|---|
| 5 | 54.6% | **45.4%** | 1.15 | 0.8 |
| **20** *(EF's typical fire)* | 58.2% | **41.8%** | 1.47 | 1.8 |
| 60 | 64.5% | 35.5% | 1.90 | 3.2 |
| 120 | 71.6% | 28.4% | 2.35 | 4.5 |
| **190** *(REVERSAL's median fire)* | ~78.4% | **~21.6%** | 2.69 | 5.5 |
| 240 | 84.8% | 15.2% | 2.97 | 6.2 |
| 280 | ~94% | ~6% | 3.18 | 6.8 |

**This is the user's intuition confirmed and quantified: at EF's fire time, 41.8% of candles have at
least one more crossing of the open still to come.** The lane is committing capital while the side
it can see is wrong more than two times in five.

## 2. Crossings-so-far is a weak feature early and a real one late

Accuracy of "side at t" split by how many crossings already happened (k = crossings after the
opening side was established):

| t | k=1 | k=2 | k≥3 |
|---|---|---|---|
| 20 | 57.9% (n=12,956) | 59.4% (n=5,845) | 56.3% (n=1,507) |
| 60 | 64.9% (n=9,152) | 65.8% (n=6,986) | 61.5% (n=4,179) |
| 190 | 82.3% (n=5,522) | 81.3% (n=6,279) | **76.6%** (n=8,516) |
| 240 | 87.9% (n=4,990) | 86.6% (n=5,940) | **82.1%** (n=9,387) |

At t=20 the spread is ~3pp and **not monotone** — choppy candles are barely distinguishable that
early. By t=190 the spread is ~6pp and clean. **The "how choppy is this candle" signal exists, but
it arrives too late for EF and in good time for REVERSAL.**

## 3. Time profile — when the tree becomes reliable (V's explicit question)

Walk-forward AUC on held-out days, model vs the raw sign it would replace:

| t | AUC sign | **AUC model** | acc sign | acc model |
|---|---|---|---|---|
| 5 | 0.5465 | 0.5608 | 54.6% | 54.3% |
| **20** | 0.5828 | **0.6132** | 58.3% | 58.3% |
| 60 | 0.6448 | **0.6919** | 64.5% | 64.5% |
| 120 | 0.7243 | 0.7861 | 72.4% | 72.4% |
| 180 | 0.7968 | 0.8652 | 79.7% | 79.7% |
| 240 | 0.8666 | 0.9312 | 86.7% | 86.7% |

Two things matter here:

1. **The model beats the raw sign on AUC at every single t** (+0.030 at t=20, +0.047 at t=60,
   +0.068 at t=180) — but **accuracy at the 0.5 threshold is identical**. It does not change the
   call; it ranks confidence. That is exactly what a *gate* needs, and exactly what a *direction
   flip* cannot use. Use it to decide whether to fire, never to decide which way.
2. **There is no cliff — AUC rises smoothly with t.** At EF's fire time it is 0.61, which is weak.
   It passes 0.70 only around t≈100 s and 0.80 around t≈180 s. **Answering V directly: the tree is
   genuinely reliable only in REVERSAL's window, not EF's.**

## 4. The replay over real fires — the only test that counts

143 real EF fires from the v10 engine (09-08 18:05 → 09-09 23:51) matched to kline candles by
`candle_id`; the model is read **at each fire's actual second** (min 5, median 64, max 275 — never a
fixed offset). PnL at $1 with the 2% fee model. "conf" = the model's probability for **the side the
lane actually took**.

| gate | kept | hit | PnL | removed | removed record | h1 | h2 |
|---|---|---|---|---|---|---|---|
| baseline | 143 | 55% | +10.80 | 0 | — | +3.73 | **+7.08** |
| conf ≥ 0.45 | 93 | 60% | +11.91 | 50 | 22/28, −1.11 | +8.67 | +3.24 |
| conf ≥ 0.50 | 87 | 62% | +14.06 | 56 | 24/32, −3.26 | +11.67 | +2.39 |
| **conf ≥ 0.55** | **79** | **65%** | **+16.36** | 64 | 27/37, −5.56 | +13.90 | **+2.47** |
| conf ≥ 0.60 | 45 | 64% | +9.32 | 98 | 49/49, +1.48 | +4.47 | +4.85 |

At first glance `conf ≥ 0.55` looks strong: +16.36 vs +10.80, hit rate 65% vs 55%, both halves
positive, and the 64 fires it removes went 27/37 for −5.56. **Two things stop me recommending it.**

- **It fails V's ship rule on size.** The rule is ≥100 kept fires; the best gate keeps **79**. Even
  `conf ≥ 0.45` keeps only 93. Not eligible.
- **The gain is not stable across the sample.** Baseline earns +3.73 / +7.08 across halves; the gate
  earns +13.90 / +2.47. So it beats baseline by +10.17 in the first half and **loses to it by −4.61
  in the second**. It clears "sign positive on both halves" literally, but the honest reading is
  that the edge is first-half-driven, and in the second half the gate removed winners. One more
  regime like that second half and this table looks very different.

## What is a finding vs what is not

**Findings** (large samples, walk-forward, real prints): the P(flip) curve in §1; that crossings
inform late and not early (§2); that the model adds ranking but not accuracy (§3); that the tree's
AUC only reaches useful levels around t≈150-200 s (§3). These are stable over 20,317 candles and
71 days.

**Not a finding:** that the conf gate improves EF. 143 matched fires, best gate keeps 79, and the
advantage lives in one half. **Insufficient.**

## Next iterations (this task stays open)

1. **More real fires.** 45 of 188 EF fires had no kline candle match — my klines end 09-09 and the
   fires run to 09-10 10:36. Pulling 09-10 (and each new day as it closes) lifts the matched set
   and is the fastest route to the 100-fire bar. The twin DBs (A/B/C) add more once their candles
   are covered.
2. **Apply it where it is actually strong.** The AUC profile says this belongs on **REVERSAL**
   (fires 60-281 s, median 188 s, AUC ≈0.86 there) far more than on EF. That also connects to my
   Task 1 result that REVERSAL's edge is concentrated in cheap late entries. Worth testing on
   REVERSAL's 110 fires next.
3. **Per-second models rather than a 10-second grid**, and a shallow tree against the logistic, once
   the fire count justifies the extra fitting.
4. **Interaction with the ask.** A gate that keeps only high-confidence fires may be systematically
   keeping expensive ones; the PnL table above already nets fees, but the entry-price interaction
   needs its own split.

## Caveats

Spot 1s klines, one instrument, 71 days; the engine watches perp and Predict.fun settles its own
5-min candle, so a small number of my candle boundaries and settled directions may differ from the
venue's. The fire replay covers the v10 engine's EF lane only (the longest real record my klines
span) — not Tokyo's live fills, whose candles fall mostly on 09-10. No slippage beyond the 2% fee;
Tokyo's real fills average +0.41c worse than quote.
