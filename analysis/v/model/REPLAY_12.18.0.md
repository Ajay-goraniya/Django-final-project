# 12.18.0 lane rule replayed on existing journals (2026-09-22)

Script: `analysis/v/model/replay_lane_cap.py`. First MAIN/REVERSAL decision per candle, accepted iff ask(side) <= cap,
5-share top-up, fee 1.67%. Label: `results.actual` (Polymarket) where traded, else TWAP60 proxy. `*` = n<60, insufficient.

## Mumbai 8796+8795, 09-16 20:20 -> 09-22 08:25 (774 candles: 409 exact, 365 proxy)
MAIN 621 candles, ask med 0.83, sec med 105
| cap | n | hit | per$1 | H1 | H2 | exact-only(n) |
|---|---|---|---|---|---|---|
| 0.70 | 131 | 58.8% | -0.044 | -0.022 | -0.064 | -0.094 (86) |
| 0.80 | 273 | 68.1% | -0.025 | +0.042 | -0.081 | -0.121 (150) |
| 0.85 | 355 | 71.5% | -0.024 | +0.041 | -0.081 | -0.126 (179) |
| 0.90 | 458 | 74.5% | -0.033 | +0.002 | -0.065 | -0.138 (228) |
| 0.95 | 539 | 77.2% | -0.031 | -0.000 | -0.061 | -0.128 (263) |
| 1.00 | 621 | 79.7% | -0.030 | -0.002 | -0.059 | -0.118 (300) |
sec bands cap 0.90: 0-90s n249 -0.036 | 90-180s n155 -0.055 | 180-300s n54* +0.049

REVERSAL 153 candles, ask med 0.63, sec med 184
| cap | n | hit | per$1 | H1 | H2 | exact-only(n) |
|---|---|---|---|---|---|---|
| 0.70 | 92 | 54.3% | +1.373 | +0.946 | +1.781 | +0.506 (72) |
| 0.80 | 116 | 61.2% | +1.118 | +0.748 | +1.463 | +0.438 (87) |
| 0.90 | 140 | 66.4% | +0.937 | +0.608 | +1.275 | +0.394 (98) |
| 1.00 | 153 | 68.6% | +0.853 | +0.571 | +1.131 | +0.348 (109) |
sec bands cap 0.90: 0-90s n19* +0.416 | 90-180s n52* +0.106 | 180-300s n69 +1.706

## Mumbai REAL paper fills, arm 8796, kind=REVERSAL (analysis/aws/task118_drawdown_fills.csv)
n=43*, hit 55.8%, pnl +120.99 on 124.05 spent = +0.975/$1. H1 21: +0.792, H2 22: +1.164. Fill med 0.42, sec med 158.
Without top-3 winners: +67.94. Days: 09-17 10 fills +18.28 | 09-18 8 +29.14 | 09-19 9 +42.56 | 09-20 9 +43.24 | 09-21 6 -18.16.
Null (buy same side at same price, market-implied hit 37.0%): -0.027/$1. Actual hit 55.8%.
Same window, EF: 8795 742 fills +0.222/$1, 8796 752 fills +0.220/$1.

## Zurich 09-15 02:05 -> 09-17 12:15 (271 candles: 58 exact, 213 proxy)
MAIN 252: cap 0.90 n171 hit 78.9% +0.011 (H1 -0.042 | H2 +0.066), exact-only +0.003 (40*); cap 1.00 -0.007.
REVERSAL 19*: -0.34..-0.46 at every cap.

## Zurich 12.18.0 paper journal 09-21 17:20 -> 09-22 10:35 (40 exact)
MAIN 32*: cap 0.90 n26 hit 76.9% +0.032. REVERSAL 8*: hit 29% -0.58. All insufficient.

## Read
- MAIN (late favourite at ask ~0.83): negative on the 6-day sample at every cap, exact-only worse (-0.12..-0.14). Not the v11 +0.266.
- REVERSAL (side named by Binance-based fair against MAIN, bought at 0.1-0.55 on the Polymarket book): positive in replay
  (n140, both halves, exact-only +0.39) AND in Mumbai's real paper fills (n43*, +0.975/$1, 5 of 6 days). Null -0.03.
  Open before it is called a finding: permutation on the row dump (requested from Mumbai), depth at cheap asks, Zurich's
  small negative samples. Verified only on Mumbai's own journal + fills, not a reconstruction.
