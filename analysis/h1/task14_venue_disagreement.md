# Task 14 — where and why the two venues resolve differently
H1, 2026-09-10 23:55 UTC. Assigned by V (REQUEST.md, 23:40). **Description only — no rule proposals.**
Everything graded on the engine's `actual` (Binance close ≥ open), which Tokyo's real
`financial_result` confirms is what Predict.fun pays on.

Data: `venues.sqlite3` + `build11` / `predict_pnl` / `twin_c_thr1` candles (23:26 snapshots),
`tokyo_orders.json` (315 orders, 268 filled and graded). 641 common candles, 54.7 h.
Buckets fixed in advance: |close − open| at Binance close, in bps — `<1, 1–2.5, 2.5–5, 5–10, 10–25, 25+`.

## Headline

**The disagreement is almost entirely a near-zero-candle phenomenon, and it is not uncertainty —
it is two confident answers from two different resolution sources.**

**66 of 641 candles disagree (10.3%)**, 35 UP→DOWN and 31 DOWN→UP — symmetric, so it is not a bias
in one direction. Median |close − open| is **1.41 bps on disputed candles vs 5.44 bps overall**.

## 1. Disputed rate by |close − open|

| bps | n | disputed | rate | rate h1 | rate h2 | share of all disputes |
|---|---|---|---|---|---|---|
| <1 | 79 | 26 | **32.9%** | 35.7% | 29.7% | 39.4% |
| 1–2.5 | 79 | 17 | 21.5% | 17.9% | 25.0% | 25.8% |
| 2.5–5 | 140 | 19 | 13.6% | 15.7% | 11.4% | 28.8% |
| 5–10 | 186 | 1 | **0.5%** | 1.1% | 0.0% | 1.5% |
| 10–25 | 136 | 3 | 2.2% | 3.2% | 1.4% | 4.5% |
| 25+ | 21 | 0 | 0.0% | 0.0% | 0.0% | 0.0% |

Monotone down to the 5–10 bucket and holds in **both halves** in every row. The 5–10 vs 10–25
inversion is 1 candle against 3 — noise, not a pattern. **94% of all disputes sit under 5 bps.**

**It is not that Polymarket was unsure.** On the disputed candles, Polymarket's price for *its own*
winning side at t=287 s is **median 0.990, and ≥0.90 on 94% of them** (n=66). Both venues are
confidently right by their own oracle. This is a resolution-source difference, not a pricing error.

## 2. Where the losses sit — Tokyo's real fills

TOKYO EF, n=250, total **+8.97**, gross losses −118.10:

| bps | n | hit | PnL | per-fire | share of gross loss |
|---|---|---|---|---|---|
| <1 | 33 | **39%** | −9.58 | **−0.290** | 19% |
| 1–2.5 | 33 | 61% | +5.19 | +0.157 | 12% |
| 2.5–5 | 60 | 48% | −5.12 | −0.085 | 28% |
| 5–10 | 71 | 62% | +11.23 | +0.158 | 23% |
| 10–25 | 50 | 60% | +6.30 | +0.126 | 18% |
| 25+ | 3 | 67% | +0.95 | +0.318 | 1% |

**Both negative cells are the two smallest buckets.** Candles finishing inside 5 bps are 126 of 250
EF fills (50%) and carry **59% of gross losses**; every bucket at 5 bps or wider is profitable.
All-fills table is the same shape (<1 bps −0.269/fire, ≥5 bps all positive).

Tokyo REVERSAL is **n=18 — insufficient**, so from the paper twins (A + C pooled), accuracy only
(those tables carry the BTC signal price, not the entry ask, so PnL is not reconstructable):

| bps | EF twins n / hit | REVERSAL twins n / hit |
|---|---|---|
| <1 | 56 / **43%** | 15 / *insufficient* |
| 1–2.5 | 59 / 54% | 22 / 82% |
| 2.5–5 | 111 / 46% | 34 / 74% |
| 5–10 | 131 / 60% | 26 / 77% |
| 10–25 | 95 / 58% | 17 / *insufficient* |
| overall | 458 / 53% | 114 / **80%** |

**EF's accuracy tracks the bucket; REVERSAL's does not** (82/74/77 across the three readable cells).
On the evidence available, the near-zero problem is an **EF** problem, not a REVERSAL one — though
REVERSAL's `<1 bps` cell is exactly the one too thin to read, so that is a gap, not a clearance.

## 3. Is the late Predict.fun ask fair? (t ≥ 237 s, favoured side)

| bps | n | mean ask | realised win rate | gap |
|---|---|---|---|---|
| <1 | 77 | 0.729 | **0.494** | **−0.236** |
| 1–2.5 | 76 | 0.729 | 0.737 | +0.008 |
| 2.5–5 | 138 | 0.808 | 0.848 | +0.040 |
| 5–10 | 186 | 0.895 | 0.952 | +0.056 |
| 10–25 | 136 | 0.949 | 0.985 | +0.036 |
| 25+ | 21 | 0.985 | 1.000 | +0.015 |

**This is the sharpest number in the study, and it answers V's question directly: no.** The late ask
is fair-to-cheap in every bucket at 1 bps and above (gap +0.008 to +0.056, monotone in the middle).
In the `<1 bps` bucket it is badly wrong — **you pay 0.729 for a side that wins 49.4%**, a −0.236 gap
on n=77.

The mechanism is not mysterious: with under a basis point of separation four seconds from the close,
whichever side leads at t=240 is close to a coin flip by settlement, but the book still prices it
like a near-decided market. **Late fills in near-zero candles are systematically overpriced.**

## Limits

- 641 candles over 54.7 hours, **one regime**. My kline studies run on 20k–72k candles. This has not
  been through a rain-or-sun grid and should not be treated as a stable regularity yet.
- `25+ bps` (n=21) and both REVERSAL tail cells are under the 60-fire bar — marked, not read.
- Part 3 forward-fills each quote field independently to t=237; requiring one sample with poly and
  both Predict asks present simultaneously drops most of the data.
- Tokyo REVERSAL fills (n=18) cannot support a PnL claim; the twin numbers are accuracy only.

**No rule is proposed here, per the brief.** The observation that a bucket is unprofitable is not a
gate — it is a fact about how this venue settles, and turning it into a threshold is exactly what the
user banned.

Repro: `analysis/h1/task14_disagreement.py`. Raw output: appended below.

```
engine candles=644  polymarket outcomes=666  common=641  DISPUTED=66 (10.3%)
direction of disagreement (poly -> engine): {('UP', 'DOWN'): 35, ('DOWN', 'UP'): 31}

========================================================================================
1. DISPUTED RATE BY |close-open| BUCKET (buckets fixed in advance), both halves
========================================================================================
bps            n  disputed      rate |   rate h1   rate h2 | share of all disputes
----------------------------------------------------------------------------------------
<1            79        26     32.9% |     35.7%     29.7% |  39.4%
1-2.5         79        17     21.5% |     17.9%     25.0% |  25.8%
2.5-5        140        19     13.6% |     15.7%     11.4% |  28.8%
5-10         186         1      0.5% |      1.1%      0.0% |   1.5%
10-25        136         3      2.2% |      3.2%      1.4% |   4.5%
25+           21         0      0.0% |      0.0%      0.0% |   0.0%
median |close-open|: all candles 5.44 bps, disputed 1.41 bps

========================================================================================
   POLYMARKET UP PRICE ON DISPUTED vs AGREED CANDLES (its own book, late in the candle)
========================================================================================
group      sec             n     median        p25        p75
...
```
