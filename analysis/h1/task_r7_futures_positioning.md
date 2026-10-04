# Task R-7 — futures positioning as a "when is the model cold" signal

V, 09-15 19:1x. Script `analysis/h1/task_r7_futures_positioning.py`.

**One of the four series survives: the taker buy/sell volume ratio orders the model's ACCURACY,
and it is the first thing in R-4 → R-7 that is not the price artifact.** It is a candidate
*feature*, not a gate, and accuracy is not PnL. Details and every deflator below.

## Data — fapi is geo-blocked, and here is what replaced it

- `fapi.binance.com/futures/data/*` → **HTTP 451**, "restricted location". Unusable, as V expected.
- `data-api.binance.vision/futures/data/*` → **HTTP 404**. It serves spot `/api/v3` only.
- **What works:** `data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/` — the daily futures
  metrics archive, which carries all four series at exactly 5-min spacing (288 rows/day, every gap
  verified at 300 s): `sum_open_interest`, `count_long_short_ratio`,
  `sum_toptrader_long_short_ratio`, `sum_taker_long_short_vol_ratio`.
- 2026-09-08 … 09-14 are published; **09-15 is not yet** (the one-day lag CLAUDE.md warns about).

**Causality:** a bar stamped T summarises [T, T+300). A fire at `ts` may use only a bar fully in
the past, `T + 300 <= ts`; the OI change uses the two bars before that. Nothing can see its own
candle. **1,874 graded fires, 1,874 joined, 0 unjoinable** — 1,872 paper, **2 live**.

Terciles fixed from the feature distribution before any outcome was read.

## The whole grid, all fires pooled

| series | T1 low | T2 mid | T3 high | monotone? |
|---|---|---|---|---|
| OI change, per $1 | +0.079 | +0.106 | +0.181 | yes |
| OI change, win% | 53.2 | 54.3 | 58.4 | yes |
| long/short ACCOUNT, per $1 | +0.076 | +0.141 | +0.148 | yes |
| long/short ACCOUNT, win% | 58.7 | 52.7 | 54.5 | **no** |
| top-trader POSITION, per $1 | +0.123 | +0.142 | +0.100 | **no — peaks in the middle** |
| top-trader POSITION, win% | 57.2 | 57.9 | 50.8 | **no** |
| **taker buy/sell, per $1** | **+0.197** | **+0.133** | **+0.036** | **yes (down)** |
| **taker buy/sell, win%** | **58.5** | **56.6** | **50.7** | **yes (down)** |

Every cell is n ≈ 620. `verify.py`'s `null()` passes on 7 of the 12 cells — **and that is worth
nothing**: with three terciles some cell always beats the pooled mean. Monotonicity and replication
are what decide, so those were tested instead.

**The side split kills OI change.** Pooled it looked monotone; split it is not:
UP +0.033 / −0.054 / +0.310, DOWN +0.122 / +0.238 / +0.085. The pooled ordering was a side-mix
artifact. **Taker survives both sides**, monotone in each: UP 58.0 / 56.9 / 50.7 %,
DOWN 58.9 / 56.4 / 50.7 % — nearly identical curves.

## Why the taker ordering is not R-4's price artifact

| taker tercile | n | **median ask** | win% |
|---|---|---|---|
| T1 low | 624 | **0.470** | 58.5% |
| T2 mid | 625 | **0.470** | 56.6% |
| T3 high | 625 | **0.470** | 50.7% |

The median ask is **identical** across all three. Holding ask fixed (ask terciles, split at each
bucket's taker median), taker-low wins more in **all three**: 51.4 vs 45.1, 56.2 vs 52.9,
67.7 vs 56.9. This is an accuracy effect, and win rate does not depend on fill price at all.

- **Permutation** of the series across fires (never the labels): T1−T3 win-rate gap **+7.77 pp**
  observed, permuted mean −0.0002, **p = 0.0065** over 2,000 draws.
- **Halves:** +7.9 pp (n=344/260) and +8.7 pp (n=280/365). Stable.

## Rain or sun — every day, no day dropped

| day | n T1 | win T1 | n T3 | win T3 | gap |
|---|---|---|---|---|---|
| 09-08 | 20 | 70.0% | 15 | 60.0% | +10.0 (thin) |
| 09-09 | 108 | 68.5% | 87 | 54.0% | +14.5 |
| 09-10 | 62 | 51.6% | 38 | 47.4% | +4.2 (thin) |
| 09-11 | 102 | 48.0% | 83 | 44.6% | +3.5 |
| 09-12 | 156 | 57.7% | 198 | 49.5% | +8.2 |
| 09-13 | 94 | 58.5% | 134 | 50.0% | +8.5 |
| 09-14 | 82 | 62.2% | 70 | 58.6% | +3.6 |

**7 of 7 days positive.** Two days have a cell under 60 and are marked thin; they are shown, not
dropped, and the other five carry the result on their own.

## The trivial null V asked for

The model's own last-3 results, causal, per lane: 0-of-3 **+0.251** (n=155), 1-of-3 +0.106,
2-of-3 +0.125, 3-of-3 +0.104. The cold-streak bucket looks best — mean reversion in the model's own
record, the classic noise shape, and non-monotone.

**Taker survives controlling for it**: within streak buckets the T1−T3 win gap is +11.7 pp (n=207/235),
+10.2 pp (269/226), +2.3 pp (108/112), and **−10.2 pp in the 0-of-3 bucket (36/47 — both under 60,
insufficient, not read)**. Three readable buckets, all positive. They are not the same signal.

## What this is, and what it is not

**It is:** a fire-time observable, available before the decision, that separates the model's win
rate by ~8 pp monotonically, on both sides, at identical price, on 7 of 7 days, p = 0.0065.

**It is not a trade, and four things stand between it and one:**

1. **Accuracy is not PnL.** The per-$1 column is paper at the quoted ask; R-3 measured the live
   filled book at **+0.004 per $1 against +0.038 quoted**. The win-rate finding does not depend on
   fill price — but the money does.
2. **Live n = 2.** Everything here is paper.
3. **Seven consecutive days is one regime window**, not a year.
4. **Turning it into a rule means a gate or a size change, and both are banned on a weak score.**
   R-4, R-5 and R-6 each died exactly there. The user's own direction is the way through:
   *"give it a trained brain that knows that move is wrong"* — so the honest next step is
   **`sum_taker_long_short_vol_ratio` as a FEATURE in the next retrain**, never as an on/off gate
   bolted onto the current one.

Token budget: this report, its script and the fetch, ~55k.
