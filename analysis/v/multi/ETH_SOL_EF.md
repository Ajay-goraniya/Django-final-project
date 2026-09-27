# ETH / SOL 5-minute Polymarket markets on their own, and BTC as information (V/multi, 09-27)

**Verdict (14 days 09-13..09-26 per coin, walk-forward by day, 12 test days, graded on each market's own Polymarket resolution):**
- **ETH: EF does NOT work alone.** Venue-only EF: paper at the real exec print -0.04..-0.09/$1, London-exec -0.20..-0.29 (all 4 thetas, 7-9 of 12 days negative).
- **SOL: EF does NOT work alone.** Venue-only EF: paper -0.08..+0.08 (no permutation pass, p 0.08-0.91), London-exec -0.16..-0.32.
- **No cell of 32 is positive under London execution** - not even with London's fill odds alone and zero extra slippage (best: SOL -0.004, ETH -0.019).
- **The one real signal is Binance leading the venue print by seconds** (arms iii/iv, no venue in the model): paper +0.10/+0.11 at theta 0.25,
  perm p 0.000, both halves +, SOL 0/12 and ETH 2/12 negative days. It dies at +5c cost and under London's adverse fill (54%/65%).
- **BTC info does not help.** Own-move model with vs without BTC (iii vs iv): within 0.006/$1 in every cell. Venue + BTC (ii) vs venue (i):
  paper better in 5 of 8 cells, worse in 3; paired McNemar p<0.05 in 1 of 4 thetas per coin, still negative London-exec. Lead-lag AUC: Zurich, 30 days,
  0.000 gain in all 32 cells (analysis/zurich/MULTI_MARKET.md, 34cf8ad) - not re-run here (V, 09-27).
- **Data quality limits this:** the only history is data-api taker prints. Past ask proxy age p50 4 s (ETH) / 6 s (SOL), p90 15 s / 28 s.
  Deciding AND paying on that stale proxy inflates every cell by +0.1..+0.4/$1 (column "paper past proxy") - the 09-11 quote-age trap.
  Here the decision uses the past print (<=5 s old) and the trade is priced at the FIRST print at-or-after the decision (<=4 s), so
  verify.quote_age passes; a 1 Hz book recorder (Zurich has started one) is needed for a clean answer.
- Spread (ask_up + ask_dn - 1, both prints <=2 s old): **ETH p50 1.0c, SOL p50 1.0c** (p75 1.7c / 2.0c) - not 8c.

## Setup (defined before looking)
- Data: gamma (markets + outcomePrices), data-api /trades (all taker prints; ETH 949k, SOL 452k, BTC 6.1M), Binance 1 s klines
  (data-api.binance.vision). clob prices-history not used (single price, ~60 s grain; V/Zurich: unusable).
- Ask proxy: taker BUY of a side at p = that side's ask; taker SELL of the other side at q = ask 1-q (mirrored books). Per-second mean of prints.
- Features at second s use only klines closing <= ep+s and prints stamped <= ep+s-1. line = Binance mean of the minute before the open (TWAP60).
- Arms: (i) Platt on logit venue mid (+ x s/240); (ii) (i) + BTC time-scaled move + BTC venue mid; (iii) own + BTC time-scaled move, no venue;
  (iv) own move only (control for iii). Walk-forward by day (train all earlier days; first 2 days train only).
- Rule: first s in 15..240 where max-side EV = p/(ask(1+0.07(1-ask))) - 1 >= theta, ask proxy <= 5 s old, 0.02..0.98; one trade per candle.
- London-exec: fill 54.1% if it would win / 65.0% if it would lose, slippage p10/p50/p90 -1/+2/+11 c ON TOP of the exec print, fee
  0.07*sh*p*(1-p), $10, 1000 runs. "fill odds only" = same fills, no extra slippage (the exec print is already an after-decision price).
- perm p = shuffle the sides, price each flipped side at ITS OWN exec print. paired = McNemar on candles where both arms fired.
- Grading: gamma outcomePrices (the venue's own settlement). Cross-check vs post-close prints: ETH 23/24, SOL 32/32 (thin: few prints after close).
  Binance TWAP60 proxy agrees 98.1% (ETH) / 98.6% (SOL) - information only, never used as a label.

## Full output - ETH
```
# ETH: 4030 candles, 14 days 09-13..09-26, test days 12 (09-15..09-26)
grading: Polymarket outcome vs post-close prints agree 0.9583 (read 0.006); vs Binance TWAP60 proxy agree 0.981; UP rate 0.500
trades/candle median 216; past-proxy age (UP, s 15..240) p50 4s p90 15s, share <=2s 0.37, <=5s 0.63; exec print within 4 s: 0.63
spread (ask_up+ask_dn-1, both prints <=2 s old, n=157423): p25 -0.000 p50 +0.010 p75 +0.017;  exec - past (same side) mean -0.0041

BTC venue mid available on 0.97 of decision seconds

## T2/T3 EF grid (walk-forward, test days only). paper = every order fills at the exec print; London-exec adds fill odds + slippage ON TOP of the exec print
| arm | theta | n | hit | med ask | med sec | paper/$1 (exec) | paper/$1 (past proxy) | H1 | H2 | neg days | London-exec/$1 | fill odds only/$1 | London total $ [p05, p95] | perm p | paired vs (i): disc b/c, p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (i) venue | 0.05 | 2170 | 0.479 | 0.49 | 82 | -0.041 | +0.055 | -0.053 | -0.029 | 9/12 | -0.201 | -0.133 | -2695.5 [-3119.2, -2267.7] | 0.778 |  |
| (i) venue | 0.10 | 1008 | 0.365 | 0.35 | 131 | -0.049 | +0.155 | -0.029 | -0.069 | 8/12 | -0.240 | -0.159 | -1540.7 [-1906.9, -1166.7] | 0.802 |  |
| (i) venue | 0.15 | 516 | 0.312 | 0.29 | 155 | -0.093 | +0.190 | -0.104 | -0.082 | 7/12 | -0.288 | -0.205 | -959.3 [-1246.2, -678.8] | 0.818 |  |
| (i) venue | 0.25 | 183 | 0.251 | 0.22 | 164 | -0.040 | +0.454 | +0.017 | -0.096 | 8/12 | -0.279 | -0.167 | -334.3 [-533.6, -129.7] | 0.640 |  |
| (ii) venue+BTC | 0.05 | 2403 | 0.485 | 0.51 | 79 | -0.019 | +0.114 | -0.037 | -0.002 | 6/12 | -0.187 | -0.112 | -2766.9 [-3304.0, -2207.2] | 0.762 | 2099 common, 182/167, p=0.454 |
| (ii) venue+BTC | 0.10 | 1280 | 0.403 | 0.38 | 132 | -0.027 | +0.195 | -0.087 | +0.033 | 8/12 | -0.212 | -0.128 | -1709.4 [-2141.6, -1263.3] | 0.552 | 944 common, 85/60, p=0.046 |
| (ii) venue+BTC | 0.15 | 693 | 0.336 | 0.31 | 162 | -0.031 | +0.231 | -0.145 | +0.082 | 7/12 | -0.245 | -0.144 | -1089.2 [-1492.2, -686.4] | 0.640 | 464 common, 24/19, p=0.542 |
| (ii) venue+BTC | 0.25 | 275 | 0.269 | 0.24 | 190 | -0.115 | +0.343 | -0.340 | +0.108 | 8/12 | -0.322 | -0.227 | -576.4 [-811.8, -317.6] | 0.746 | 158 common, 2/6, p=0.289 |
| (iii) model own+BTC | 0.05 | 3415 | 0.530 | 0.51 | 21 | +0.000 | +0.083 | +0.023 | -0.023 | 6/12 | -0.149 | -0.087 | -3104.2 [-3569.4, -2636.3] | 0.002 | 2168 common, 547/434, p=0.000 |
| (iii) model own+BTC | 0.10 | 3369 | 0.493 | 0.48 | 29 | +0.012 | +0.137 | +0.050 | -0.026 | 6/12 | -0.153 | -0.082 | -3179.9 [-3742.6, -2590.1] | 0.002 | 1004 common, 315/181, p=0.000 |
| (iii) model own+BTC | 0.15 | 3259 | 0.462 | 0.43 | 41 | +0.047 | +0.221 | +0.103 | -0.009 | 4/12 | -0.138 | -0.055 | -2794.0 [-3406.2, -2180.5] | 0.000 | 510 common, 162/75, p=0.000 |
| (iii) model own+BTC | 0.25 | 2940 | 0.401 | 0.34 | 76 | +0.099 | +0.403 | +0.132 | +0.066 | 2/12 | -0.124 | -0.019 | -2298.0 [-3018.1, -1566.3] | 0.000 | 176 common, 52/16, p=0.000 |
| (iv) model own-only | 0.05 | 3416 | 0.530 | 0.51 | 21 | +0.005 | +0.088 | +0.036 | -0.026 | 6/12 | -0.145 | -0.082 | -3033.4 [-3505.4, -2554.2] | 0.000 | 2169 common, 557/443, p=0.000 |
| (iv) model own-only | 0.10 | 3364 | 0.495 | 0.48 | 28 | +0.018 | +0.144 | +0.059 | -0.023 | 4/12 | -0.148 | -0.076 | -3065.3 [-3644.2, -2510.0] | 0.000 | 1004 common, 314/177, p=0.000 |
| (iv) model own-only | 0.15 | 3263 | 0.457 | 0.43 | 41 | +0.033 | +0.205 | +0.080 | -0.015 | 4/12 | -0.150 | -0.069 | -3049.0 [-3698.2, -2419.5] | 0.000 | 510 common, 161/77, p=0.000 |
| (iv) model own-only | 0.25 | 2953 | 0.399 | 0.34 | 76 | +0.097 | +0.381 | +0.121 | +0.073 | 2/12 | -0.125 | -0.021 | -2344.5 [-3102.3, -1572.0] | 0.000 | 175 common, 52/16, p=0.000 |
(* = under 60 fires: insufficient)

## T4 verify.Finding on the best cell by London-exec: (iii) model own+BTC theta 0.25
==============================================================================
FINDING: ETH EF (iii) model own+BTC theta 0.25   (+0.099/fire, n=2940)
==============================================================================
  [FAIL] grading provenance   gamma_outcome vs post_close_prints disagree on 1/24 (4.2%) - results are only valid on the settling source
  [PASS] quote age            rule=at-or-after, max age 0.0s from first print at-or-after the decision second (decision uses a past print <=5 s old)
  [PASS] sample size          all 1 cells >= 60
  [PASS] both halves          h1 +0.132 / h2 +0.066
  [PASS] permutation control  real +0.099 vs permuted mean +0.001 (p95 +0.040), p=0.000 over 1000 draws
  [FAIL] sweep shape          NON-monotone: [-0.149 -0.153 -0.138 -0.124]
  [FAIL] cost sensitivity     +0c:+0.099 +1c:+0.056 +2c:+0.018 +5c:-0.076  <- dies once you pay realistically
  [PASS] beats the null       mine +0.099 vs buy the cheaper side, same second +0.071
  [PASS] paired test          n=176, agree on 108, discordant 68 (52 vs 16), edge +0.205, exact McNemar p=0.000
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: grading provenance, sweep shape, cost sensitivity

```

## Full output - SOL
```
# SOL: 4031 candles, 14 days 09-13..09-26, test days 12 (09-15..09-26)
grading: Polymarket outcome vs post-close prints agree 1.0000 (read 0.008); vs Binance TWAP60 proxy agree 0.986; UP rate 0.498
trades/candle median 105; past-proxy age (UP, s 15..240) p50 6s p90 28s, share <=2s 0.23, <=5s 0.44; exec print within 4 s: 0.44
spread (ask_up+ask_dn-1, both prints <=2 s old, n=66178): p25 -0.000 p50 +0.010 p75 +0.020;  exec - past (same side) mean -0.0032

BTC venue mid available on 0.97 of decision seconds

## T2/T3 EF grid (walk-forward, test days only). paper = every order fills at the exec print; London-exec adds fill odds + slippage ON TOP of the exec print
| arm | theta | n | hit | med ask | med sec | paper/$1 (exec) | paper/$1 (past proxy) | H1 | H2 | neg days | London-exec/$1 | fill odds only/$1 | London total $ [p05, p95] | perm p | paired vs (i): disc b/c, p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (i) venue | 0.05 | 2140 | 0.425 | 0.36 | 76 | +0.041 | +0.140 | +0.024 | +0.057 | 7/12 | -0.156 | -0.069 | -2099.8 [-2643.8, -1530.1] | 0.084 |  |
| (i) venue | 0.10 | 1426 | 0.351 | 0.31 | 109 | +0.052 | +0.203 | +0.077 | +0.027 | 6/12 | -0.178 | -0.070 | -1627.7 [-2217.5, -941.4] | 0.204 |  |
| (i) venue | 0.15 | 952 | 0.309 | 0.27 | 128 | +0.080 | +0.254 | +0.127 | +0.033 | 6/12 | -0.176 | -0.054 | -1085.9 [-1646.6, -431.7] | 0.256 |  |
| (i) venue | 0.25 | 489 | 0.243 | 0.22 | 150 | -0.081 | +0.196 | -0.143 | -0.021 | 8/12 | -0.315 | -0.207 | -1009.8 [-1355.2, -644.5] | 0.914 |  |
| (ii) venue+BTC | 0.05 | 2437 | 0.448 | 0.39 | 74 | +0.068 | +0.186 | +0.069 | +0.067 | 5/12 | -0.130 | -0.039 | -1971.4 [-2550.5, -1394.1] | 0.012 | 2073 common, 170/152, p=0.343 |
| (ii) venue+BTC | 0.10 | 1727 | 0.392 | 0.33 | 113 | +0.079 | +0.270 | +0.107 | +0.050 | 5/12 | -0.140 | -0.037 | -1528.7 [-2095.3, -947.1] | 0.038 | 1347 common, 87/59, p=0.025 |
| (ii) venue+BTC | 0.15 | 1193 | 0.340 | 0.29 | 138 | +0.051 | +0.301 | +0.070 | +0.033 | 5/12 | -0.186 | -0.073 | -1421.8 [-1994.3, -768.8] | 0.322 | 880 common, 38/33, p=0.635 |
| (ii) venue+BTC | 0.25 | 631 | 0.298 | 0.24 | 164 | +0.065 | +0.494 | +0.032 | +0.098 | 5/12 | -0.199 | -0.064 | -812.5 [-1313.1, -147.7] | 0.420 | 439 common, 12/10, p=0.832 |
| (iii) model own+BTC | 0.05 | 3386 | 0.555 | 0.55 | 26 | +0.011 | +0.115 | -0.021 | +0.044 | 5/12 | -0.134 | -0.072 | -2753.8 [-3234.6, -2284.5] | 0.002 | 2132 common, 642/398, p=0.000 |
| (iii) model own+BTC | 0.10 | 3279 | 0.519 | 0.50 | 36 | +0.033 | +0.181 | -0.003 | +0.069 | 3/12 | -0.131 | -0.058 | -2640.6 [-3180.3, -2025.5] | 0.000 | 1405 common, 426/211, p=0.000 |
| (iii) model own+BTC | 0.15 | 3108 | 0.487 | 0.45 | 54 | +0.082 | +0.285 | +0.067 | +0.097 | 1/12 | -0.105 | -0.018 | -2026.1 [-2723.9, -1367.1] | 0.000 | 912 common, 270/118, p=0.000 |
| (iii) model own+BTC | 0.25 | 2706 | 0.425 | 0.37 | 91 | +0.112 | +0.437 | +0.122 | +0.101 | 0/12 | -0.110 | -0.004 | -1871.9 [-2616.6, -1190.0] | 0.000 | 445 common, 141/45, p=0.000 |
| (iv) model own-only | 0.05 | 3389 | 0.554 | 0.55 | 26 | +0.009 | +0.112 | -0.025 | +0.043 | 6/12 | -0.136 | -0.074 | -2804.4 [-3268.7, -2329.7] | 0.000 | 2132 common, 643/402, p=0.000 |
| (iv) model own-only | 0.10 | 3287 | 0.519 | 0.50 | 36 | +0.030 | +0.180 | -0.005 | +0.065 | 4/12 | -0.132 | -0.060 | -2667.3 [-3204.1, -2091.2] | 0.000 | 1407 common, 425/214, p=0.000 |
| (iv) model own-only | 0.15 | 3102 | 0.488 | 0.45 | 54 | +0.086 | +0.291 | +0.076 | +0.097 | 1/12 | -0.104 | -0.015 | -1990.2 [-2639.1, -1311.3] | 0.000 | 912 common, 268/117, p=0.000 |
| (iv) model own-only | 0.25 | 2717 | 0.425 | 0.36 | 91 | +0.109 | +0.421 | +0.120 | +0.099 | 0/12 | -0.112 | -0.006 | -1917.1 [-2656.5, -1115.5] | 0.000 | 443 common, 140/46, p=0.000 |
(* = under 60 fires: insufficient)

## T4 verify.Finding on the best cell by London-exec: (iv) model own-only theta 0.15
==============================================================================
FINDING: SOL EF (iv) model own-only theta 0.15   (+0.086/fire, n=3102)
==============================================================================
  [PASS] grading provenance   gamma_outcome vs post_close_prints disagree on 0/32 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from first print at-or-after the decision second (decision uses a past print <=5 s old)
  [PASS] sample size          all 1 cells >= 60
  [PASS] both halves          h1 +0.076 / h2 +0.097
  [PASS] permutation control  real +0.086 vs permuted mean -0.030 (p95 +0.003), p=0.000 over 1000 draws
  [FAIL] sweep shape          NON-monotone: [-0.136 -0.132 -0.104 -0.112]  <- peaks at an interior point, classic overfit
  [FAIL] cost sensitivity     +0c:+0.086 +1c:+0.052 +2c:+0.021 +5c:-0.057  <- dies once you pay realistically
  [PASS] beats the null       mine +0.086 vs buy the cheaper side, same second -0.006
  [PASS] paired test          n=912, agree on 527, discordant 385 (268 vs 117), edge +0.166, exact McNemar p=0.000
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sweep shape, cost sensitivity

```

## Reproduce
```
python3 analysis/v/multi/fetch_poly.py poly.sqlite3 1789257600 1790467200 eth sol btc
python3 analysis/v/multi/fetch_1s_multi.py k1s.sqlite3 1789254000 1790467200 BTCUSDT ETHUSDT SOLUSDT
python3 analysis/v/multi/build_panel.py poly.sqlite3 k1s.sqlite3 eth eth.npz     # and sol
python3 analysis/v/multi/analyze.py eth.npz eth > out_eth.txt                     # --t1 adds the Binance lead-lag table
```
