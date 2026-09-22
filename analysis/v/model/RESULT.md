# New model attempt — result. 2026-09-22 (V). Data and runs: Mumbai (box-side, read-only), script analysis/v/model/train_snapshots.py.
Training set: every decision snapshot the 8795/8796 engines evaluated (fired or not), 30 engine features, walk-forward by day,
21,648 snapshots / 821 candles / 09-16 → 09-22. Label: Polymarket resolution (results.actual = Gamma; venues.outcome on the
Mumbai box ends 09-16 17:15 so it could not be used). Labels exist only for candles the lane traded → "on the candles we trade".
Local pilot on Zurich journals (6,091 snapshots, 2 test days): both models worse than the venue price (Brier .1718/.1792 vs .1627).

| forecaster | Brier | acc | discordant vs venue (model right / venue right) |
|---|---|---|---|
| venue price | 0.2245 | 63.2% | – |
| live v10 | 0.2271 | 63.1% | |
| logistic (new) | **0.2190** | 63.9% | 15–60 s 488/487 · **60–150 s 662/550 p<.001** · 150–241 s 227/225 |
| gradient boosting | 0.2484 | 58.5% | loses all three bands → dropped |

Trading one/candle after fee: logit@0.10 n=602 **+0.436/$1** (H1 +.41 | H2 +.45); v10@0.10 n=447 +0.263.
Permutation null (shuffle logit predictions within second band, 50 draws): @0.10 real +0.436 vs null median +0.294, p95 +0.334;
@0.15 real +0.543 vs p95 +0.396 → passes, but the null itself is +0.29: most of the raw per$1 is ask structure.
**Paired vs v10 on the 429 candles both trade:** same side 72%; logit +0.507/$1 vs v10 +0.260; discordant 46 (logit won) vs 75
(v10 won), exact McNemar **p=0.011 in v10's favour.** The new model is the WORSE forecaster on shared candles and makes more
money only because it buys cheaper: ask median 0.36 (v10 0.43); 43.5% of its buys are under 0.35 at 44% hit and +0.76/$1;
0.45–0.55 earns −0.01; hit rises with ask while per$1 falls — longshot pricing at the paper quote.

## Verdict
Not a better signal. It is the same spread-capture (R-13) pushed further down the ask ladder, where live fills are worst
(R-18: 41% fill at the touch, rejects concentrate on the cheap side). It does not ship and does not go to paper as a "model".
Gates not run: costs/slippage on the ask<0.45 bucket (the whole edge); settlement-line features run (--klines) still executing
on Mumbai — a concatenation bug (day files overlap 600 s → unsorted array into searchsorted) is fixed in this commit.
What would be needed to try again: labels for ALL candles (the venues outcome logger must run on the box that trains),
features the market does not already price (order-book depth beyond top, Chainlink lag), and the fill model in the objective.

## Settlement-line features (--klines) — Mumbai run, same journals, 20,832 snapshots (630 rows drop where the pre-open minute is incomplete)
| | without | with klines |
|---|---|---|
| Brier venue / v10 / logit | 0.2243 / 0.2269 / 0.2188 | 0.2232 / 0.2258 / 0.2180 |
| logit vs venue, 60–150 s discordant | 662/550 p<.001 | 662/599 p=0.08 |
Logit's gain (−0.0008) is smaller than the venue's and v10's gain (−0.0011) on the same reduced rows → the row set, not the
features. The only significant band weakens. gbm fails its permutation null in all runs. **Settlement-line inputs do not help
the forecaster.** The kline overlap bug (600 s) changed nothing material (3rd decimal). Recommendation adopted: not added.

## v11 (Predict.fun build11) calls priced on Polymarket's book — Mumbai run, 09-21 12:50 → 09-22 01:55
Source: owner's export (236 graded calls); ask = 8795 snapshot ≤25 s before the call for the called side; label = Polymarket
results.actual where the epoch was traded (149) else TWAP60 proxy (70). 219 matched. Polymarket fee 1.67% of shares both ways.
| kind | n | PM ask median | hit vs PM settlement | PM per $1 | exact-label | proxy-label | Predict per $1 (own quote) |
|---|---|---|---|---|---|---|---|
| **MAIN** | **65** | 0.72 | **86.2%** | **+0.266** | +0.286 (n39) | +0.238 (n26) | +0.088 (q 0.75) |
| REVERSAL | 12* | 0.545 | 75% | outlier-driven (one 0.02 ask) | +0.907 (n11) | – | +0.097 |
| EF | 142 | 0.58 | 57.7% | −0.072 | −0.152 (n99) | +0.112 (n43) | +0.125 (q 0.51) |
MAIN by second: <90 s n25 +0.099 (exact −0.10 / proxy +0.32, unread) · 90–180 s n23 hit 95.7% +0.365 · ≥180 s n17 hit 100% +0.381 — all under 60.
MAIN mean +0.266, median +0.277, not outlier-driven; both label sources positive. EF inverts sign between venues: Polymarket
prices EF's edge away, Predict does not. Proxy and exact labels disagree in sign on EF and MAIN<90 s → proxy-only cells unread.
Verdict: **v11's MAIN leg survives Polymarket prices on 65 calls (the one cell at the bar), 13 hours, paper quotes.** The
Polymarket engine already carries build11's MAIN port (12.14/12.15.5) with `main_enabled=false` on every lane. Owner decides
whether to enable MAIN on the Zurich paper lane; V's instruction to Zurich was blocked by the sandbox (engine change).
