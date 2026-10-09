# S1 — a signal built on Polymarket's settlement rule itself. 2026-09-21 (V)
Owner: "every time when signal fires we need to be sure that candle is gonna settle as per Polymarket rules."

Construction: at second s of the candle, compute the settlement quantity mechanically. line_open = TWAP60(Binance) over
[open−60, open). Closing TWAP = mean over [240, 300): the part [240, s) is already known, the remaining (300−s) seconds are
assumed to stay at the current price with Brownian uncertainty (1 s vol from the candle's first 240 s).
P(UP) = Φ(margin / sd). Venue ask from polybook (1 Hz, ≤2 s old). Label venues.outcome. 672 candles, 09-11 → 09-16,
seconds 245…295 (the last minute, where the rule gives mechanical information the raw close does not).

## Calibration of the mechanical P(UP)
| s | P<0.1 → realised | 0.3–0.7 | P>0.9 → realised |
|---|---|---|---|
| 245 | 0.06 (n230) | 0.51 (n84) | 0.96 (n232) |
| 265 | 0.06 (n116) | 0.51 (n41) | 0.93 (n130) |
| 285 | 0.24 (n49) | 0.64 (n11) | 0.84 (n49) |
| 295 | 0.36 (n25) | – | 0.81 (n26) |
Sharp at 245–265 s; degrades in the last 15 s. Chainlink lags Binance by ~5 s (T0: corr peaks at a 5 s lag) and carries
its own aggregation, so the last seconds of Binance are not what settles. The proxy is a good ruler at the open and a
worse one in the final 15 s.

## Does the venue misprice it?
Rows where the mechanical P was >95% and the venue ask on that side was <0.90: 293 of 1,970 (106 candles).
The mechanical side was right only **71.7%** there (median ask 0.51). When my calculation and the market disagree,
the market is closer. The venue already prices the TWAP rule.

## Trading it (one trade per candle, buy when p·(1−fee) − ask > m, per $1 after fee, H1|H2)
| m | 245–265 s | 275–285 s | 290–295 s |
|---|---|---|---|
| 0.00 | n485 63% −0.001 (+0.06|−0.06) | n163 49% −0.090 (−0.20|+0.04) | n73 51% +0.203 (+0.01|+0.57) |
| 0.02 | n351 57% +0.112 (+0.23|−0.01) | n136 43% −0.065 | n66 45% +0.224 (+0.01|+0.65) |
| 0.05 | n269 52% +0.082 (+0.25|−0.10) | n124 44% −0.136 | n63 44% +0.250 (+0.04|+0.65) |
| 0.10 | n191 48% +0.064 (+0.25|−0.15) | n106 42% −0.136 | n61 44% +0.274 (+0.06|+0.65) |
No cell is positive in both halves except 290–295 s, which is 61–73 longshots at ask ~0.15 with H1 ≈ 0 and H2 carrying
everything: not readable, and it sits in the seconds where the proxy is least reliable. **Verdict: no signal here that the
market does not already have. FAIL as a tradeable edge; PASS as a ruler (T0).**

## What is left on the signal side, honestly
1. The rule is now in the code path (T0) and any model we train uses it. That removes the 11.6% label noise. It does not add edge.
2. T1 (features), S1 (mechanics): neither beats the venue price. The venue price is the best forecaster of the venue's own rule on this data.
3. The one unread positive cell across all tests: model disagrees with the market by ≥12c (T1), 57 candles, +0.35/$1. Zurich paper is now logging the rows to bring that to 60+.
Scripts: scratchpad `t0/s1_settle_lock.py`. Token budget S1: ~25k.
