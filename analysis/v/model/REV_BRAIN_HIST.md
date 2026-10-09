# REV brain on history (Binance microstructure model): V 09-27

## Verdict: NOT A FINDING. The brain does not beat the venue-only null. Nothing ships.
- **Model quality:** the Binance features add nothing over the Polymarket price. Walk-forward AUC for "the underdog wins": FULL 0.746 vs NULL (ask+sec) 0.750-0.754. BIN (Binance only) is 0.71-0.72. The market alone scores 0.751. Same result on the REAL REV call rows: FULL 0.741-0.751, NULL 0.742-0.750, market 0.752, lane p 0.656.
- **ALL candles (buy the underdog when the model says EV >= theta):** every FULL and NULL cell loses in both arms. FULL is London -0.29 to -0.49/$1, and 3/5 to 9/9 test days are negative. The first qualifying second picks the model's most over-confident read.
- **Brain as a filter on REV (age-0 quote, the primary arm):** FULL cells range -0.10 to +0.41 London/$1, and every cell above +0.2 has n<60. The same cell with the venue-only NULL learner is usually as good or better. None of the 32 age-0 REV cells beats the NULL at p<.05 on the paired candle-PnL test. McNemar at p<.05 is mixed: 3 cells favour FULL and 4 favour NULL. Best FULL cell with n>=60: arm B REV GBM th .03, n64, **+0.150** London, vs its NULL cell **+0.178** (n59). verify.py: FAIL beats-the-null, FAIL paired (28v27, p=1.0).
- **Against the lane baseline** (REV R1, age 0, same 9 days; +0.061 here, +0.065 in MAIN_REV_LONDON_EXEC): many filtered cells beat it on points. So does the NULL learner, which uses only a calibrated venue price. Whatever helps is calibration of the price, not the Binance brain.
- **Age-1 quote cells** look better (best FULL +0.161, n65), but verify FAILS quote-age: a stale quote with fresher Binance data is the known selection artifact. They still lose to their NULL cell (+0.188).
- **Leakage:** garbage-truncation test 0/40 rows changed; every bookDepth snapshot is <= t-1; train days < test day is asserted. Parity with the live feature parquet: ret5, ofi15, spot_imb15 and basis corr 1.000; move corr 0.958 (line vs first trade). The REV lane baseline reproduces (n149, 77.9%, paper +0.170).
- Side note, not tested as a finding: REV calls filtered by the calibrated venue price alone (NULL learner) give +0.12 to +0.18 on n59-65 at theta .03. Only window 2 can say whether that is real.

## Setup (fixed before any result)
- Rows: every Polymarket tape row with both asks at sec 30-240. The tape runs about every 5 s. The quote is from the same second (age 0). 79,936 rows on 2,048 candles, 09-08 to 09-16.
- Label: y = 1 if the side opposite the spot leader (spot vs the TWAP60 line) wins on **venues.outcome**.
- Features: rebuilt from data.binance.vision (spot 1 s klines, spot and perp aggTrades, perp bookDepth). A row at t reads buckets <= t-1 only. Directional features are oriented to the leader. The list: move/sigma, move/(sigma*sqrt(time left)), ret 5/15/30/60, range position, retreat from the extreme, cross excursion, sigma, vol ratio, perp basis, perp ret 5/15, perp OFI 5/15/60, activity, spot taker imbalance 5/15/60, depth imbalance at 1/2/5% and depth age.
- Sets: NULL = [logit ask_underdog, sec]; BIN = Binance + sec; FULL = NULL + Binance. Learners: L2 LR (C=0.1) and HistGBM (depth 3, lr .05, 150 iterations, leaf 200, l2 10).
- Walk-forward by day. **Arm A:** tape days only, at least 3 prior days, tested on 09-11 to 09-16. **Arm B:** adds v10_features_8days.parquet (08-29 to 09-06, 19,426 rows) as train-only prior days and tests all 9 tape days, the same days as the baseline. Its y is Polymarket's Gamma resolution, the same oracle as venues.outcome. There is no overlap to cross-check it; the TWAP60 proxy agrees 0.980 there and 0.968 with venues.outcome. Its asks are mostly trade-inferred (is_book=0).
- Rules: one trade per candle, the first second where p/(ask*cost)-1 >= theta and ask <= 0.90, with theta in {0, .03, .05, .10}. Universes: ALL (buy the underdog); REV (the real REVERSAL call seconds, calls_rev.csv, repriced past-only at age 0 or <=1 s, using the model p for REV's side); REV&R1 (REV plus the lane's own R1). Note: REV buys the current spot leader (underdog on only 1.6% of rows), so for REV the brain answers "does the new leader hold".
- London exec: lane_exec_sim.py model (fill 54.1% if it would win, 65.0% if it would lose; slippage -1/+2/+11c; fee; $10; 1000 runs). Permutation: flip the side and price it at the OPPOSITE ask. Paired vs NULL: McNemar, where right = the better decision on that candle (traded and won, or stayed out while the other rule's trade lost), plus a sign-flip test on the candle-PnL difference ("dPnL").

Scripts: `analysis/v/model/rev_brain_fetch.py` (archives to per-second npz) and `analysis/v/model/rev_brain_hist.py` (everything else, incl. verify.py).

## Full output (whole grid, every cell; * = n<60, insufficient)
```
rows: tape 79936 on 2048 candles, days ['09-08', '09-09', '09-10', '09-11', '09-12', '09-13', '09-14', '09-15', '09-16']; parquet 19426 on 2160 candles

== LEAKAGE CHECKS
 truncation test: 40 random rows recomputed with EVERY bucket >= t (and bookDepth >= t) replaced by garbage -> 0 feature values changed (must be 0)
 bookDepth age at decision (s): median 15, max 36; asserted snapshot ts <= t-1 on every row
 parity vs parquet (live features) ret5_raw ~ ret5_pq corr +1.000 (n 19426)
 parity vs parquet (live features) ofi15_raw ~ ofi15_pq corr +1.000 (n 19426)
 parity vs parquet (live features) simb15_raw ~ spot_imb15 corr +1.000 (n 19426)
 parity vs parquet (live features) basis_raw ~ basis_bps corr +1.000 (n 19426)
 parity vs parquet (live features) move_line_bps ~ move_bps_pq corr +0.958 (n 19426)
 label context: Binance-spot TWAP60 proxy agrees with venues.outcome 0.968 (n 2232), with parquet y 0.980 (n 2160)
 REV calls sec 0..240: 16549; with a past-only quote age 0: 3284 rows / 211 candles, age<=1: 6563 / 217; REV side = underdog on 1.6% of rows

== MODEL QUALITY on walk-forward test rows (label: underdog wins; pooled over test days)
 arm learner set n_rows base AUC Brier | AUC by test day
 A LR NULL 53867 0.234 0.7540 0.1536 | 0.735 0.746 0.800 0.758 0.734 0.745
 A LR BIN 53867 0.234 0.7109 0.1635 | 0.698 0.628 0.748 0.736 0.713 0.716
 A LR FULL 53867 0.234 0.7464 0.1558 | 0.733 0.704 0.792 0.754 0.731 0.749
 A GBM NULL 53867 0.234 0.7520 0.1541 | 0.733 0.745 0.798 0.757 0.733 0.745
 A GBM BIN 53867 0.234 0.7124 0.1624 | 0.701 0.646 0.758 0.726 0.715 0.722
 A GBM FULL 53867 0.234 0.7387 0.1572 | 0.724 0.683 0.790 0.744 0.735 0.748
 B LR NULL 79936 0.238 0.7503 0.1558 | 0.756 0.735 0.745 0.734 0.746 0.798 0.757 0.734 0.746
 B LR BIN 79936 0.238 0.7156 0.1638 | 0.706 0.700 0.715 0.699 0.680 0.759 0.741 0.716 0.717
 B LR FULL 79936 0.238 0.7457 0.1569 | 0.750 0.724 0.739 0.732 0.732 0.797 0.756 0.733 0.749
 B GBM NULL 79936 0.238 0.7493 0.1560 | 0.756 0.734 0.746 0.734 0.746 0.798 0.757 0.734 0.745
 B GBM BIN 79936 0.238 0.7240 0.1614 | 0.740 0.701 0.730 0.718 0.683 0.762 0.735 0.719 0.725
 B GBM FULL 79936 0.238 0.7459 0.1569 | 0.757 0.723 0.745 0.736 0.716 0.795 0.750 0.737 0.748
 market alone (1 - ask_leader normalised, no fit), arm-B rows: AUC 0.7512 Brier 0.1558
 on the REAL REV call rows (age 0; label = REV side wins; p = model p for that side):
 A LR NULL n 2089 base 0.802 AUC 0.7434 Brier 0.1430
 A LR BIN n 2089 base 0.802 AUC 0.7155 Brier 0.1510
 A LR FULL n 2089 base 0.802 AUC 0.7430 Brier 0.1424
 A GBM NULL n 2089 base 0.802 AUC 0.7417 Brier 0.1426
 A GBM BIN n 2089 base 0.802 AUC 0.7139 Brier 0.1486
 A GBM FULL n 2089 base 0.802 AUC 0.7413 Brier 0.1429
 B LR NULL n 3284 base 0.823 AUC 0.7502 Brier 0.1310
 B LR BIN n 3284 base 0.823 AUC 0.7295 Brier 0.1381
 B LR FULL n 3284 base 0.823 AUC 0.7508 Brier 0.1314
 B GBM NULL n 3284 base 0.823 AUC 0.7499 Brier 0.1308
 B GBM BIN n 3284 base 0.823 AUC 0.7150 Brier 0.1383
 B GBM FULL n 3284 base 0.823 AUC 0.7465 Brier 0.1322
 market alone on the same rows: AUC 0.7522; lane p: AUC 0.6560

== BASELINES (lane as it is), same test days, London exec
 arm A REV R1 lane-p age0 n 104 hit 76.0% ask 0.64 | paper +0.133 H1/H2 +0.185/+0.081 neg days 0/6 perm p 0.000 | LONDON +0.027/$1 tot $+16 [p05 -39, p95 +75]
 arm A REV R0 first call age0 n 135 hit 73.3% ask 0.69 | paper +0.064 H1/H2 +0.069/+0.060 neg days 0/6 perm p 0.055 | LONDON -0.041/$1 tot $-32 [p05 -96, p95 +30]
 arm A REV R1 lane-p age1 n 108 hit 76.9% ask 0.63 | paper +0.364 H1/H2 +0.468/+0.261 neg days 0/6 perm p 0.000 | LONDON +0.210/$1 tot $+131 [p05 +29, p95 +240]
 arm A REV R0 first call age1 n 137 hit 73.0% ask 0.68 | paper +0.230 H1/H2 +0.300/+0.161 neg days 2/6 perm p 0.012 | LONDON +0.087/$1 tot $+69 [p05 -34, p95 +182]
 arm B REV R1 lane-p age0 n 149 hit 77.9% ask 0.64 | paper +0.170 H1/H2 +0.239/+0.102 neg days 0/9 perm p 0.000 | LONDON +0.061/$1 tot $+53 [p05 -14, p95 +121]
 arm B REV R0 first call age0 n 201 hit 75.1% ask 0.69 | paper +0.091 H1/H2 +0.127/+0.055 neg days 0/9 perm p 0.019 | LONDON -0.014/$1 tot $-16 [p05 -88, p95 +58]
 arm B REV R1 lane-p age1 n 163 hit 76.1% ask 0.63 | paper +0.289 H1/H2 +0.202/+0.375 neg days 0/9 perm p 0.000 | LONDON +0.149/$1 tot $+141 [p05 +31, p95 +260]
 arm B REV R0 first call age1 n 208 hit 73.1% ask 0.67 | paper +0.177 H1/H2 +0.108/+0.245 neg days 3/9 perm p 0.001 | LONDON +0.048/$1 tot $+59 [p05 -63, p95 +194]

== arm A universe ALL quote age 0 s
 LR NULL theta 0.00 n 51* hit 74.5% ask 0.76 | paper -0.036 H1/H2 -0.185/+0.108 neg days 3/5 perm p 0.524 | LONDON -0.122/$1 tot $-36 [p05 -68, p95 -3]
 LR FULL theta 0.00 n 617 hit 37.6% ask 0.43 | paper -0.140 H1/H2 -0.127/-0.153 neg days 6/6 perm p 0.976 | LONDON -0.299/$1 tot $-1164 [p05 -1398, p95 -939] | vs NULL: McNemar 213v388 p=0.000, dPnL -84.7$1 sign-flip p=1.000
 LR NULL theta 0.03 none
 LR FULL theta 0.03 n 432 hit 35.9% ask 0.41 | paper -0.132 H1/H2 -0.030/-0.233 neg days 5/6 perm p 0.942 | LONDON -0.297/$1 tot $-814 [p05 -1020, p95 -608] | vs NULL: McNemar 155v277 p=0.000, dPnL -57.0$1 sign-flip p=0.991
 LR NULL theta 0.05 none
 LR FULL theta 0.05 n 349 hit 33.5% ask 0.41 | paper -0.168 H1/H2 -0.008/-0.326 neg days 5/6 perm p 0.971 | LONDON -0.328/$1 tot $-730 [p05 -918, p95 -543] | vs NULL: McNemar 117v232 p=0.000, dPnL -58.5$1 sign-flip p=0.992
 LR NULL theta 0.10 none
 LR FULL theta 0.10 n 229 hit 32.3% ask 0.37 | paper -0.153 H1/H2 -0.074/-0.232 neg days 3/5 perm p 0.893 | LONDON -0.324/$1 tot $-474 [p05 -635, p95 -314] | vs NULL: McNemar 74v155 p=0.000, dPnL -35.1$1 sign-flip p=0.942
 GBM NULL theta 0.00 n 594 hit 28.1% ask 0.27 | paper -0.168 H1/H2 -0.207/-0.130 neg days 5/6 perm p 0.958 | LONDON -0.355/$1 tot $-1365 [p05 -1661, p95 -1008]
 GBM FULL theta 0.00 n 908 hit 26.3% ask 0.28 | paper -0.178 H1/H2 -0.252/-0.104 neg days 5/6 perm p 0.982 | LONDON -0.367/$1 tot $-2168 [p05 -2586, p95 -1678] | vs NULL: McNemar 257v435 p=0.000, dPnL -61.8$1 sign-flip p=0.894
 GBM NULL theta 0.03 n 383 hit 24.0% ask 0.27 | paper -0.228 H1/H2 -0.291/-0.166 neg days 5/6 perm p 0.977 | LONDON -0.415/$1 tot $-1040 [p05 -1304, p95 -748]
 GBM FULL theta 0.03 n 818 hit 23.7% ask 0.26 | paper -0.208 H1/H2 -0.289/-0.127 neg days 6/6 perm p 0.995 | LONDON -0.399/$1 tot $-2140 [p05 -2547, p95 -1615] | vs NULL: McNemar 206v450 p=0.000, dPnL -83.0$1 sign-flip p=0.960
 GBM NULL theta 0.05 n 262 hit 18.7% ask 0.22 | paper -0.330 H1/H2 -0.440/-0.221 neg days 5/6 perm p 0.991 | LONDON -0.504/$1 tot $-873 [p05 -1092, p95 -612]
 GBM FULL theta 0.05 n 766 hit 21.7% ask 0.24 | paper -0.214 H1/H2 -0.319/-0.109 neg days 5/6 perm p 0.993 | LONDON -0.411/$1 tot $-2070 [p05 -2508, p95 -1554] | vs NULL: McNemar 178v461 p=0.000, dPnL -77.4$1 sign-flip p=0.942
 GBM NULL theta 0.10 n 53* hit 1.9% ask 0.03 | paper -0.558 H1/H2 -0.099/-1.000 neg days 5/6 perm p 0.885 | LONDON -0.750/$1 tot $-275 [p05 -405, p95 -56]
 GBM FULL theta 0.10 n 668 hit 18.3% ask 0.22 | paper -0.315 H1/H2 -0.362/-0.268 neg days 6/6 perm p 1.000 | LONDON -0.489/$1 tot $-2166 [p05 -2562, p95 -1690] | vs NULL: McNemar 131v504 p=0.000, dPnL -180.5$1 sign-flip p=1.000

== arm A universe REV quote age 0 s
 LR NULL theta 0.00 n 103 hit 78.6% ask 0.76 | paper +0.035 H1/H2 +0.059/+0.010 neg days 3/6 perm p 0.231 | LONDON -0.054/$1 tot $-32 [p05 -77, p95 +15]
 LR FULL theta 0.00 n 94 hit 77.7% ask 0.74 | paper +0.033 H1/H2 +0.018/+0.048 neg days 4/6 perm p 0.097 | LONDON -0.058/$1 tot $-31 [p05 -76, p95 +13] | vs NULL: McNemar 13v20 p=0.296, dPnL -0.5$1 sign-flip p=0.534
 LR NULL theta 0.03 n 29* hit 79.3% ask 0.71 | paper +0.149 H1/H2 +0.287/+0.020 neg days 3/6 perm p 0.135 | LONDON +0.050/$1 tot $+8 [p05 -21, p95 +39]
 LR FULL theta 0.03 n 44* hit 77.3% ask 0.70 | paper +0.075 H1/H2 +0.121/+0.029 neg days 2/6 perm p 0.066 | LONDON -0.020/$1 tot $-5 [p05 -37, p95 +27] | vs NULL: McNemar 17v10 p=0.248, dPnL -1.0$1 sign-flip p=0.605
 LR NULL theta 0.05 n 16* hit 75.0% ask 0.66 | paper +0.183 H1/H2 +0.402/-0.037 neg days 2/6 perm p 0.262 | LONDON +0.063/$1 tot $+6 [p05 -20, p95 +30]
 LR FULL theta 0.05 n 29* hit 72.4% ask 0.71 | paper +0.039 H1/H2 +0.071/+0.010 neg days 2/6 perm p 0.432 | LONDON -0.065/$1 tot $-11 [p05 -37, p95 +14] | vs NULL: McNemar 12v7 p=0.359, dPnL -1.8$1 sign-flip p=0.698
 LR NULL theta 0.10 n 2* hit 50.0% ask 0.65 | paper -0.176 H1/H2 -1.000/+0.648 neg days 1/1 perm p 0.748 | LONDON -0.297/$1 tot $-4 [p05 -10, p95 +7]
 LR FULL theta 0.10 n 9* hit 77.8% ask 0.67 | paper +0.156 H1/H2 +0.397/-0.036 neg days 2/5 perm p 0.299 | LONDON +0.046/$1 tot $+2 [p05 -12, p95 +18] | vs NULL: McNemar 6v1 p=0.125, dPnL +1.8$1 sign-flip p=0.156
 GBM NULL theta 0.00 n 110 hit 77.3% ask 0.73 | paper +0.073 H1/H2 +0.067/+0.080 neg days 2/6 perm p 0.119 | LONDON -0.019/$1 tot $-12 [p05 -64, p95 +40]
 GBM FULL theta 0.00 n 75 hit 78.7% ask 0.65 | paper +0.164 H1/H2 +0.237/+0.092 neg days 2/6 perm p 0.006 | LONDON +0.058/$1 tot $+25 [p05 -21, p95 +74] | vs NULL: McNemar 18v35 p=0.027, dPnL +4.2$1 sign-flip p=0.169
 GBM NULL theta 0.03 n 28* hit 85.7% ask 0.62 | paper +0.344 H1/H2 +0.535/+0.154 neg days 1/6 perm p 0.000 | LONDON +0.231/$1 tot $+37 [p05 +8, p95 +67]
 GBM FULL theta 0.03 n 46* hit 76.1% ask 0.62 | paper +0.191 H1/H2 +0.305/+0.077 neg days 2/6 perm p 0.014 | LONDON +0.076/$1 tot $+20 [p05 -20, p95 +59] | vs NULL: McNemar 17v13 p=0.585, dPnL -0.9$1 sign-flip p=0.579
 GBM NULL theta 0.05 n 16* hit 87.5% ask 0.63 | paper +0.456 H1/H2 +0.734/+0.178 neg days 1/5 perm p 0.022 | LONDON +0.338/$1 tot $+31 [p05 +6, p95 +56]
 GBM FULL theta 0.05 n 36* hit 72.2% ask 0.59 | paper +0.230 H1/H2 +0.393/+0.067 neg days 2/6 perm p 0.039 | LONDON +0.099/$1 tot $+21 [p05 -20, p95 +63] | vs NULL: McNemar 16v12 p=0.572, dPnL +1.0$1 sign-flip p=0.421
 GBM NULL theta 0.10 n 3* hit 66.7% ask 0.59 | paper +0.608 H1/H2 +2.178/-0.176 neg days 1/2 perm p 0.503 | LONDON +0.378/$1 tot $+7 [p05 -10, p95 +26]
 GBM FULL theta 0.10 n 9* hit 77.8% ask 0.57 | paper +0.291 H1/H2 +0.342/+0.251 neg days 1/5 perm p 0.132 | LONDON +0.162/$1 tot $+9 [p05 -9, p95 +27] | vs NULL: McNemar 8v4 p=0.388, dPnL +0.8$1 sign-flip p=0.412

== arm A universe REV&R1 quote age 0 s
 LR NULL theta 0.00 n 71 hit 81.7% ask 0.77 | paper +0.068 H1/H2 +0.142/-0.003 neg days 2/6 perm p 0.043 | LONDON -0.016/$1 tot $-7 [p05 -43, p95 +32]
 LR FULL theta 0.00 n 66 hit 80.3% ask 0.73 | paper +0.077 H1/H2 +0.079/+0.074 neg days 2/6 perm p 0.018 | LONDON -0.013/$1 tot $-5 [p05 -39, p95 +29] | vs NULL: McNemar 11v16 p=0.442, dPnL +0.2$1 sign-flip p=0.494
 LR NULL theta 0.03 n 23* hit 78.3% ask 0.69 | paper +0.160 H1/H2 +0.115/+0.201 neg days 2/6 perm p 0.173 | LONDON +0.053/$1 tot $+7 [p05 -19, p95 +34]
 LR FULL theta 0.03 n 31* hit 74.2% ask 0.69 | paper +0.029 H1/H2 +0.095/-0.034 neg days 2/6 perm p 0.248 | LONDON -0.070/$1 tot $-13 [p05 -39, p95 +15] | vs NULL: McNemar 11v9 p=0.824, dPnL -2.8$1 sign-flip p=0.767
 LR NULL theta 0.05 n 14* hit 78.6% ask 0.64 | paper +0.262 H1/H2 +0.424/+0.101 neg days 2/6 perm p 0.141 | LONDON +0.147/$1 tot $+12 [p05 -12, p95 +36]
 LR FULL theta 0.05 n 24* hit 70.8% ask 0.70 | paper +0.006 H1/H2 +0.026/-0.014 neg days 3/6 perm p 0.456 | LONDON -0.096/$1 tot $-14 [p05 -38, p95 +14] | vs NULL: McNemar 9v7 p=0.804, dPnL -3.5$1 sign-flip p=0.840
 LR NULL theta 0.10 n 1* hit 100.0% ask 0.59 | paper +0.648 H1/H2 +nan/+0.648 neg days 0/1 perm p 0.498 | LONDON +0.560/$1 tot $+3 [p05 +0, p95 +7]
 LR FULL theta 0.10 n 8* hit 87.5% ask 0.66 | paper +0.301 H1/H2 +0.397/+0.205 neg days 1/5 perm p 0.047 | LONDON +0.213/$1 tot $+10 [p05 -3, p95 +23] | vs NULL: McNemar 6v1 p=0.125, dPnL +1.8$1 sign-flip p=0.145
 GBM NULL theta 0.00 n 82 hit 79.3% ask 0.69 | paper +0.129 H1/H2 +0.103/+0.154 neg days 2/6 perm p 0.009 | LONDON +0.030/$1 tot $+14 [p05 -28, p95 +62]
 GBM FULL theta 0.00 n 65 hit 76.9% ask 0.61 | paper +0.180 H1/H2 +0.250/+0.112 neg days 2/6 perm p 0.004 | LONDON +0.069/$1 tot $+26 [p05 -21, p95 +73] | vs NULL: McNemar 11v24 p=0.041, dPnL +1.2$1 sign-flip p=0.384
 GBM NULL theta 0.03 n 24* hit 83.3% ask 0.59 | paper +0.340 H1/H2 +0.537/+0.143 neg days 1/6 perm p 0.003 | LONDON +0.220/$1 tot $+30 [p05 +1, p95 +60]
 GBM FULL theta 0.03 n 42* hit 76.2% ask 0.59 | paper +0.222 H1/H2 +0.315/+0.128 neg days 2/6 perm p 0.008 | LONDON +0.105/$1 tot $+26 [p05 -14, p95 +66] | vs NULL: McNemar 15v9 p=0.307, dPnL +1.1$1 sign-flip p=0.371
 GBM NULL theta 0.05 n 13* hit 92.3% ask 0.59 | paper +0.557 H1/H2 +0.804/+0.346 neg days 0/5 perm p 0.002 | LONDON +0.446/$1 tot $+33 [p05 +10, p95 +56]
 GBM FULL theta 0.05 n 33* hit 72.7% ask 0.57 | paper +0.264 H1/H2 +0.341/+0.191 neg days 2/6 perm p 0.029 | LONDON +0.129/$1 tot $+25 [p05 -13, p95 +65] | vs NULL: McNemar 14v10 p=0.541, dPnL +1.5$1 sign-flip p=0.360
 GBM NULL theta 0.10 n 2* hit 100.0% ask 0.44 | paper +1.413 H1/H2 +2.178/+0.648 neg days 0/2 perm p 0.238 | LONDON +1.224/$1 tot $+14 [p05 +0, p95 +29]
 GBM FULL theta 0.10 n 9* hit 77.8% ask 0.57 | paper +0.291 H1/H2 +0.342/+0.251 neg days 1/5 perm p 0.109 | LONDON +0.162/$1 tot $+9 [p05 -9, p95 +27] | vs NULL: McNemar 7v4 p=0.549, dPnL -0.2$1 sign-flip p=0.531

== arm A universe REV quote age 1 s
 LR NULL theta 0.00 n 107 hit 77.6% ask 0.75 | paper +0.047 H1/H2 +0.096/-0.000 neg days 3/6 perm p 0.240 | LONDON -0.046/$1 tot $-28 [p05 -79, p95 +25]
 LR FULL theta 0.00 n 97 hit 77.3% ask 0.74 | paper +0.064 H1/H2 +0.080/+0.049 neg days 2/6 perm p 0.114 | LONDON -0.030/$1 tot $-17 [p05 -61, p95 +34] | vs NULL: McNemar 14v20 p=0.392, dPnL +1.2$1 sign-flip p=0.403
 LR NULL theta 0.03 n 34* hit 79.4% ask 0.70 | paper +0.194 H1/H2 +0.393/-0.005 neg days 2/6 perm p 0.147 | LONDON +0.082/$1 tot $+16 [p05 -18, p95 +50]
 LR FULL theta 0.03 n 50* hit 76.0% ask 0.69 | paper +0.112 H1/H2 +0.210/+0.013 neg days 2/6 perm p 0.146 | LONDON +0.007/$1 tot $+2 [p05 -35, p95 +42] | vs NULL: McNemar 17v11 p=0.345, dPnL -1.0$1 sign-flip p=0.605
 LR NULL theta 0.05 n 20* hit 70.0% ask 0.66 | paper +0.159 H1/H2 +0.230/+0.088 neg days 2/6 perm p 0.531 | LONDON +0.036/$1 tot $+4 [p05 -25, p95 +37]
 LR FULL theta 0.05 n 35* hit 71.4% ask 0.69 | paper +0.077 H1/H2 +0.242/-0.079 neg days 2/6 perm p 0.559 | LONDON -0.033/$1 tot $-7 [p05 -40, p95 +28] | vs NULL: McNemar 14v7 p=0.189, dPnL -0.5$1 sign-flip p=0.544
 LR NULL theta 0.10 n 5* hit 60.0% ask 0.59 | paper +0.181 H1/H2 +1.129/-0.451 neg days 1/3 perm p 0.716 | LONDON +0.032/$1 tot $+1 [p05 -16, p95 +18]
 LR FULL theta 0.10 n 14* hit 71.4% ask 0.64 | paper +0.156 H1/H2 +0.406/-0.094 neg days 3/6 perm p 0.432 | LONDON +0.040/$1 tot $+3 [p05 -19, p95 +27] | vs NULL: McNemar 7v2 p=0.180, dPnL +1.3$1 sign-flip p=0.252
 GBM NULL theta 0.00 n 113 hit 76.1% ask 0.69 | paper +0.107 H1/H2 +0.141/+0.073 neg days 3/6 perm p 0.087 | LONDON +0.004/$1 tot $+2 [p05 -57, p95 +64]
 GBM FULL theta 0.00 n 82 hit 76.8% ask 0.64 | paper +0.196 H1/H2 +0.305/+0.087 neg days 1/6 perm p 0.017 | LONDON +0.084/$1 tot $+40 [p05 -17, p95 +97] | vs NULL: McNemar 16v31 p=0.040, dPnL +4.0$1 sign-flip p=0.169
 GBM NULL theta 0.03 n 36* hit 80.6% ask 0.59 | paper +0.383 H1/H2 +0.691/+0.075 neg days 1/6 perm p 0.018 | LONDON +0.255/$1 tot $+53 [p05 +8, p95 +99]
 GBM FULL theta 0.03 n 55* hit 76.4% ask 0.61 | paper +0.272 H1/H2 +0.431/+0.119 neg days 1/6 perm p 0.005 | LONDON +0.143/$1 tot $+46 [p05 -6, p95 +100] | vs NULL: McNemar 20v13 p=0.296, dPnL +1.2$1 sign-flip p=0.390
 GBM NULL theta 0.05 n 23* hit 78.3% ask 0.59 | paper +0.471 H1/H2 +0.769/+0.197 neg days 1/5 perm p 0.154 | LONDON +0.319/$1 tot $+43 [p05 +3, p95 +83]
 GBM FULL theta 0.05 n 44* hit 72.7% ask 0.59 | paper +0.305 H1/H2 +0.493/+0.117 neg days 1/6 perm p 0.029 | LONDON +0.162/$1 tot $+42 [p05 -6, p95 +91] | vs NULL: McNemar 20v13 p=0.296, dPnL +2.6$1 sign-flip p=0.279
 GBM NULL theta 0.10 n 7* hit 71.4% ask 0.49 | paper +0.942 H1/H2 +1.924/+0.206 neg days 1/4 perm p 0.312 | LONDON +0.691/$1 tot $+29 [p05 -7, p95 +65]
 GBM FULL theta 0.10 n 13* hit 69.2% ask 0.57 | paper +0.418 H1/H2 +0.706/+0.172 neg days 2/6 perm p 0.267 | LONDON +0.247/$1 tot $+19 [p05 -16, p95 +54] | vs NULL: McNemar 8v6 p=0.791, dPnL -1.2$1 sign-flip p=0.614

== arm A universe REV&R1 quote age 1 s
 LR NULL theta 0.00 n 73 hit 80.8% ask 0.76 | paper +0.097 H1/H2 +0.182/+0.013 neg days 2/6 perm p 0.055 | LONDON +0.007/$1 tot $+3 [p05 -37, p95 +42]
 LR FULL theta 0.00 n 70 hit 81.4% ask 0.70 | paper +0.149 H1/H2 +0.179/+0.119 neg days 1/6 perm p 0.001 | LONDON +0.054/$1 tot $+21 [p05 -18, p95 +64] | vs NULL: McNemar 13v14 p=1.000, dPnL +3.4$1 sign-flip p=0.208
 LR NULL theta 0.03 n 30* hit 80.0% ask 0.69 | paper +0.217 H1/H2 +0.278/+0.156 neg days 2/6 perm p 0.091 | LONDON +0.109/$1 tot $+19 [p05 -13, p95 +51]
 LR FULL theta 0.03 n 37* hit 73.0% ask 0.68 | paper +0.090 H1/H2 +0.296/-0.104 neg days 3/6 perm p 0.352 | LONDON -0.018/$1 tot $-4 [p05 -37, p95 +29] | vs NULL: McNemar 9v10 p=1.000, dPnL -3.2$1 sign-flip p=0.818
 LR NULL theta 0.05 n 19* hit 73.7% ask 0.64 | paper +0.220 H1/H2 +0.228/+0.213 neg days 2/6 perm p 0.399 | LONDON +0.098/$1 tot $+11 [p05 -18, p95 +40]
 LR FULL theta 0.05 n 30* hit 70.0% ask 0.69 | paper +0.056 H1/H2 +0.229/-0.116 neg days 4/6 perm p 0.575 | LONDON -0.051/$1 tot $-9 [p05 -40, p95 +23] | vs NULL: McNemar 10v7 p=0.629, dPnL -2.5$1 sign-flip p=0.745
 LR NULL theta 0.10 n 4* hit 75.0% ask 0.54 | paper +0.477 H1/H2 +1.129/-0.176 neg days 1/3 perm p 0.510 | LONDON +0.299/$1 tot $+7 [p05 -10, p95 +22]
 LR FULL theta 0.10 n 13* hit 76.9% ask 0.64 | paper +0.245 H1/H2 +0.260/+0.233 neg days 3/6 perm p 0.259 | LONDON +0.141/$1 tot $+11 [p05 -11, p95 +32] | vs NULL: McNemar 7v2 p=0.180, dPnL +1.3$1 sign-flip p=0.285
 GBM NULL theta 0.00 n 86 hit 77.9% ask 0.66 | paper +0.172 H1/H2 +0.238/+0.106 neg days 1/6 perm p 0.003 | LONDON +0.065/$1 tot $+32 [p05 -20, p95 +86]
 GBM FULL theta 0.00 n 72 hit 76.4% ask 0.60 | paper +0.227 H1/H2 +0.325/+0.129 neg days 1/6 perm p 0.005 | LONDON +0.107/$1 tot $+45 [p05 -9, p95 +100] | vs NULL: McNemar 11v21 p=0.110, dPnL +1.5$1 sign-flip p=0.321
 GBM NULL theta 0.03 n 32* hit 81.2% ask 0.58 | paper +0.426 H1/H2 +0.713/+0.139 neg days 1/6 perm p 0.012 | LONDON +0.289/$1 tot $+53 [p05 +11, p95 +97]
 GBM FULL theta 0.03 n 50* hit 78.0% ask 0.59 | paper +0.330 H1/H2 +0.447/+0.212 neg days 1/6 perm p 0.001 | LONDON +0.194/$1 tot $+56 [p05 +7, p95 +107] | vs NULL: McNemar 18v10 p=0.185, dPnL +2.9$1 sign-flip p=0.209
 GBM NULL theta 0.05 n 20* hit 80.0% ask 0.57 | paper +0.539 H1/H2 +0.960/+0.118 neg days 1/5 perm p 0.091 | LONDON +0.381/$1 tot $+44 [p05 +5, p95 +84]
 GBM FULL theta 0.05 n 40* hit 75.0% ask 0.57 | paper +0.371 H1/H2 +0.561/+0.181 neg days 1/6 perm p 0.003 | LONDON +0.218/$1 tot $+51 [p05 +0, p95 +104] | vs NULL: McNemar 18v10 p=0.185, dPnL +4.1$1 sign-flip p=0.178
 GBM NULL theta 0.10 n 6* hit 83.3% ask 0.45 | paper +1.266 H1/H2 +1.924/+0.608 neg days 1/4 perm p 0.149 | LONDON +0.993/$1 tot $+35 [p05 -1, p95 +70]
 GBM FULL theta 0.10 n 12* hit 75.0% ask 0.56 | paper +0.537 H1/H2 +1.028/+0.045 neg days 2/6 perm p 0.071 | LONDON +0.361/$1 tot $+26 [p05 -7, p95 +59] | vs NULL: McNemar 8v6 p=0.791, dPnL -1.2$1 sign-flip p=0.615

== arm B universe ALL quote age 0 s
 LR NULL theta 0.00 n 21* hit 4.8% ask 0.08 | paper -0.700 H1/H2 -0.371/-1.000 neg days 1/1 perm p 0.986 | LONDON -0.790/$1 tot $-114 [p05 -170, p95 -62]
 LR FULL theta 0.00 n 1130 hit 32.4% ask 0.38 | paper -0.100 H1/H2 -0.028/-0.172 neg days 7/9 perm p 0.927 | LONDON -0.293/$1 tot $-2118 [p05 -2602, p95 -1602] | vs NULL: McNemar 371v750 p=0.000, dPnL -98.1$1 sign-flip p=0.944
 LR NULL theta 0.03 n 7* hit 0.0% ask 0.03 | paper -1.000 H1/H2 -1.000/-1.000 neg days 1/1 perm p 1.000 | LONDON -1.000/$1 tot $-49 [p05 -74, p95 -21]
 LR FULL theta 0.03 n 854 hit 28.9% ask 0.36 | paper -0.180 H1/H2 -0.099/-0.261 neg days 7/9 perm p 0.993 | LONDON -0.362/$1 tot $-1999 [p05 -2401, p95 -1538] | vs NULL: McNemar 250v603 p=0.000, dPnL -147.0$1 sign-flip p=0.998
 LR NULL theta 0.05 n 5* hit 0.0% ask 0.03 | paper -1.000 H1/H2 -1.000/-1.000 neg days 1/1 perm p 1.000 | LONDON -1.000/$1 tot $-35 [p05 -53, p95 -21]
 LR FULL theta 0.05 n 704 hit 26.4% ask 0.34 | paper -0.200 H1/H2 -0.174/-0.226 neg days 7/9 perm p 0.987 | LONDON -0.391/$1 tot $-1790 [p05 -2222, p95 -1340] | vs NULL: McNemar 189v516 p=0.000, dPnL -135.6$1 sign-flip p=0.992
 LR NULL theta 0.10 n 1* hit 0.0% ask 0.00 | paper -1.000 H1/H2 +nan/-1.000 neg days 1/1 perm p 1.000 | LONDON -1.000/$1 tot $-7 [p05 -11, p95 +0]
 LR FULL theta 0.10 n 445 hit 23.4% ask 0.29 | paper -0.209 H1/H2 -0.171/-0.246 neg days 6/9 perm p 0.945 | LONDON -0.412/$1 tot $-1200 [p05 -1566, p95 -762] | vs NULL: McNemar 104v340 p=0.000, dPnL -91.9$1 sign-flip p=0.959
 GBM NULL theta 0.00 n 910 hit 22.4% ask 0.22 | paper -0.200 H1/H2 -0.073/-0.327 neg days 8/9 perm p 0.996 | LONDON -0.396/$1 tot $-2369 [p05 -2741, p95 -1959]
 GBM FULL theta 0.00 n 1532 hit 27.0% ask 0.29 | paper -0.177 H1/H2 -0.135/-0.218 neg days 9/9 perm p 1.000 | LONDON -0.361/$1 tot $-3595 [p05 -4055, p95 -3130] | vs NULL: McNemar 390v625 p=0.000, dPnL -88.4$1 sign-flip p=0.896
 GBM NULL theta 0.03 n 609 hit 15.9% ask 0.13 | paper -0.220 H1/H2 -0.229/-0.211 neg days 9/9 perm p 0.985 | LONDON -0.439/$1 tot $-1786 [p05 -2197, p95 -1352]
 GBM FULL theta 0.03 n 1377 hit 23.8% ask 0.27 | paper -0.205 H1/H2 -0.165/-0.245 neg days 9/9 perm p 1.000 | LONDON -0.392/$1 tot $-3529 [p05 -4010, p95 -3046] | vs NULL: McNemar 350v685 p=0.000, dPnL -148.4$1 sign-flip p=0.985
 GBM NULL theta 0.05 n 409 hit 11.0% ask 0.12 | paper -0.386 H1/H2 -0.303/-0.469 neg days 8/9 perm p 0.998 | LONDON -0.578/$1 tot $-1594 [p05 -1939, p95 -1214]
 GBM FULL theta 0.05 n 1251 hit 23.0% ask 0.24 | paper -0.206 H1/H2 -0.123/-0.288 neg days 8/9 perm p 0.999 | LONDON -0.397/$1 tot $-3252 [p05 -3707, p95 -2796] | vs NULL: McNemar 319v708 p=0.000, dPnL -99.3$1 sign-flip p=0.924
 GBM NULL theta 0.10 n 153 hit 3.3% ask 0.04 | paper -0.654 H1/H2 -0.532/-0.775 neg days 9/9 perm p 1.000 | LONDON -0.791/$1 tot $-831 [p05 -1038, p95 -562]
 GBM FULL theta 0.10 n 1011 hit 21.0% ask 0.21 | paper -0.151 H1/H2 -0.022/-0.280 neg days 8/9 perm p 0.974 | LONDON -0.367/$1 tot $-2449 [p05 -2908, p95 -1979] | vs NULL: McNemar 231v690 p=0.000, dPnL -52.6$1 sign-flip p=0.778

== arm B universe REV quote age 0 s
 LR NULL theta 0.00 n 182 hit 77.5% ask 0.72 | paper +0.090 H1/H2 +0.110/+0.069 neg days 3/9 perm p 0.021 | LONDON -0.005/$1 tot $-6 [p05 -75, p95 +65]
 LR FULL theta 0.00 n 177 hit 78.0% ask 0.70 | paper +0.094 H1/H2 +0.136/+0.053 neg days 2/9 perm p 0.002 | LONDON -0.003/$1 tot $-3 [p05 -72, p95 +64] | vs NULL: McNemar 11v12 p=1.000, dPnL +0.4$1 sign-flip p=0.460
 LR NULL theta 0.03 n 65 hit 80.0% ask 0.66 | paper +0.231 H1/H2 +0.322/+0.143 neg days 3/9 perm p 0.008 | LONDON +0.124/$1 tot $+46 [p05 +1, p95 +92]
 LR FULL theta 0.03 n 104 hit 80.8% ask 0.68 | paper +0.204 H1/H2 +0.226/+0.182 neg days 2/9 perm p 0.000 | LONDON +0.099/$1 tot $+59 [p05 +6, p95 +113] | vs NULL: McNemar 41v16 p=0.001, dPnL +6.2$1 sign-flip p=0.090
 LR NULL theta 0.05 n 34* hit 79.4% ask 0.65 | paper +0.273 H1/H2 +0.341/+0.204 neg days 2/9 perm p 0.176 | LONDON +0.157/$1 tot $+31 [p05 -4, p95 +68]
 LR FULL theta 0.05 n 65 hit 76.9% ask 0.65 | paper +0.210 H1/H2 +0.327/+0.096 neg days 2/9 perm p 0.024 | LONDON +0.093/$1 tot $+35 [p05 -11, p95 +81] | vs NULL: McNemar 27v12 p=0.024, dPnL +4.4$1 sign-flip p=0.139
 LR NULL theta 0.10 n 9* hit 66.7% ask 0.57 | paper +0.439 H1/H2 +1.031/-0.035 neg days 2/5 perm p 0.587 | LONDON +0.244/$1 tot $+13 [p05 -15, p95 +43]
 LR FULL theta 0.10 n 21* hit 76.2% ask 0.64 | paper +0.263 H1/H2 +0.560/-0.007 neg days 3/8 perm p 0.160 | LONDON +0.139/$1 tot $+17 [p05 -11, p95 +46] | vs NULL: McNemar 13v5 p=0.096, dPnL +1.6$1 sign-flip p=0.348
 GBM NULL theta 0.00 n 164 hit 78.0% ask 0.70 | paper +0.104 H1/H2 +0.132/+0.075 neg days 4/9 perm p 0.042 | LONDON +0.003/$1 tot $+3 [p05 -65, p95 +66]
 GBM FULL theta 0.00 n 119 hit 78.2% ask 0.66 | paper +0.130 H1/H2 +0.208/+0.052 neg days 1/9 perm p 0.004 | LONDON +0.028/$1 tot $+19 [p05 -37, p95 +75] | vs NULL: McNemar 18v43 p=0.002, dPnL -1.6$1 sign-flip p=0.637
 GBM NULL theta 0.03 n 59* hit 81.4% ask 0.64 | paper +0.290 H1/H2 +0.311/+0.269 neg days 1/9 perm p 0.002 | LONDON +0.178/$1 tot $+60 [p05 +16, p95 +104]
 GBM FULL theta 0.03 n 64 hit 79.7% ask 0.62 | paper +0.264 H1/H2 +0.368/+0.159 neg days 2/9 perm p 0.001 | LONDON +0.150/$1 tot $+55 [p05 +10, p95 +104] | vs NULL: McNemar 28v27 p=1.000, dPnL -0.2$1 sign-flip p=0.523
 GBM NULL theta 0.05 n 34* hit 76.5% ask 0.64 | paper +0.302 H1/H2 +0.270/+0.334 neg days 2/8 perm p 0.032 | LONDON +0.176/$1 tot $+35 [p05 -6, p95 +75]
 GBM FULL theta 0.05 n 48* hit 79.2% ask 0.60 | paper +0.284 H1/H2 +0.389/+0.178 neg days 1/9 perm p 0.000 | LONDON +0.168/$1 tot $+46 [p05 +5, p95 +90] | vs NULL: McNemar 25v15 p=0.154, dPnL +3.4$1 sign-flip p=0.213
 GBM NULL theta 0.10 n 11* hit 72.7% ask 0.54 | paper +0.460 H1/H2 +0.310/+0.586 neg days 1/5 perm p 0.469 | LONDON +0.300/$1 tot $+19 [p05 -10, p95 +49]
 GBM FULL theta 0.10 n 22* hit 81.8% ask 0.56 | paper +0.539 H1/H2 +0.485/+0.592 neg days 0/8 perm p 0.000 | LONDON +0.390/$1 tot $+50 [p05 +13, p95 +84] | vs NULL: McNemar 15v6 p=0.078, dPnL +6.8$1 sign-flip p=0.068

== arm B universe REV&R1 quote age 0 s
 LR NULL theta 0.00 n 134 hit 78.4% ask 0.69 | paper +0.131 H1/H2 +0.181/+0.082 neg days 3/9 perm p 0.001 | LONDON +0.030/$1 tot $+23 [p05 -31, p95 +84]
 LR FULL theta 0.00 n 124 hit 79.8% ask 0.69 | paper +0.154 H1/H2 +0.206/+0.102 neg days 1/9 perm p 0.000 | LONDON +0.056/$1 tot $+39 [p05 -19, p95 +97] | vs NULL: McNemar 13v15 p=0.851, dPnL +1.5$1 sign-flip p=0.325
 LR NULL theta 0.03 n 45* hit 80.0% ask 0.64 | paper +0.278 H1/H2 +0.379/+0.181 neg days 2/9 perm p 0.013 | LONDON +0.159/$1 tot $+41 [p05 +2, p95 +82]
 LR FULL theta 0.03 n 78 hit 79.5% ask 0.66 | paper +0.217 H1/H2 +0.266/+0.168 neg days 2/9 perm p 0.009 | LONDON +0.111/$1 tot $+50 [p05 +1, p95 +101] | vs NULL: McNemar 31v12 p=0.005, dPnL +4.4$1 sign-flip p=0.132
 LR NULL theta 0.05 n 27* hit 77.8% ask 0.63 | paper +0.297 H1/H2 +0.317/+0.278 neg days 2/9 perm p 0.211 | LONDON +0.173/$1 tot $+27 [p05 -7, p95 +59]
 LR FULL theta 0.05 n 45* hit 77.8% ask 0.64 | paper +0.280 H1/H2 +0.384/+0.180 neg days 2/9 perm p 0.012 | LONDON +0.157/$1 tot $+41 [p05 -4, p95 +84] | vs NULL: McNemar 18v8 p=0.076, dPnL +4.6$1 sign-flip p=0.092
 LR NULL theta 0.10 n 8* hit 75.0% ask 0.54 | paper +0.619 H1/H2 +1.031/+0.206 neg days 2/5 perm p 0.479 | LONDON +0.451/$1 tot $+21 [p05 -6, p95 +49]
 LR FULL theta 0.10 n 16* hit 81.2% ask 0.61 | paper +0.393 H1/H2 +0.623/+0.162 neg days 2/8 perm p 0.065 | LONDON +0.277/$1 tot $+26 [p05 -1, p95 +52] | vs NULL: McNemar 10v4 p=0.180, dPnL +1.3$1 sign-flip p=0.355
 GBM NULL theta 0.00 n 118 hit 81.4% ask 0.68 | paper +0.188 H1/H2 +0.257/+0.119 neg days 2/9 perm p 0.000 | LONDON +0.089/$1 tot $+60 [p05 +1, p95 +116]
 GBM FULL theta 0.00 n 100 hit 77.0% ask 0.64 | paper +0.133 H1/H2 +0.217/+0.049 neg days 2/9 perm p 0.001 | LONDON +0.026/$1 tot $+15 [p05 -37, p95 +73] | vs NULL: McNemar 8v28 p=0.001, dPnL -8.9$1 sign-flip p=0.993
 GBM NULL theta 0.03 n 44* hit 79.5% ask 0.58 | paper +0.320 H1/H2 +0.273/+0.366 neg days 1/9 perm p 0.000 | LONDON +0.195/$1 tot $+50 [p05 +8, p95 +93]
 GBM FULL theta 0.03 n 57* hit 78.9% ask 0.59 | paper +0.279 H1/H2 +0.417/+0.146 neg days 2/9 perm p 0.001 | LONDON +0.160/$1 tot $+53 [p05 +6, p95 +99] | vs NULL: McNemar 24v17 p=0.349, dPnL +1.8$1 sign-flip p=0.358
 GBM NULL theta 0.05 n 25* hit 76.0% ask 0.57 | paper +0.376 H1/H2 +0.323/+0.426 neg days 2/8 perm p 0.030 | LONDON +0.237/$1 tot $+35 [p05 -2, p95 +73]
 GBM FULL theta 0.05 n 44* hit 77.3% ask 0.57 | paper +0.303 H1/H2 +0.427/+0.178 neg days 1/9 perm p 0.002 | LONDON +0.177/$1 tot $+45 [p05 +2, p95 +89] | vs NULL: McNemar 22v11 p=0.080, dPnL +3.9$1 sign-flip p=0.163
 GBM NULL theta 0.10 n 9* hit 77.8% ask 0.54 | paper +0.618 H1/H2 +0.262/+0.903 neg days 1/5 perm p 0.425 | LONDON +0.434/$1 tot $+23 [p05 -4, p95 +52]
 GBM FULL theta 0.10 n 22* hit 81.8% ask 0.55 | paper +0.564 H1/H2 +0.535/+0.592 neg days 0/8 perm p 0.000 | LONDON +0.411/$1 tot $+52 [p05 +16, p95 +87] | vs NULL: McNemar 14v5 p=0.064, dPnL +6.8$1 sign-flip p=0.060

== arm B universe REV quote age 1 s
 LR NULL theta 0.00 n 185 hit 76.2% ask 0.69 | paper +0.117 H1/H2 +0.156/+0.079 neg days 1/9 perm p 0.022 | LONDON +0.017/$1 tot $+18 [p05 -61, p95 +95]
 LR FULL theta 0.00 n 188 hit 75.0% ask 0.69 | paper +0.100 H1/H2 +0.131/+0.068 neg days 3/9 perm p 0.015 | LONDON -0.004/$1 tot $-5 [p05 -81, p95 +73] | vs NULL: McNemar 10v13 p=0.678, dPnL -3.0$1 sign-flip p=0.779
 LR NULL theta 0.03 n 73 hit 79.5% ask 0.65 | paper +0.239 H1/H2 +0.298/+0.181 neg days 2/9 perm p 0.009 | LONDON +0.122/$1 tot $+51 [p05 +3, p95 +97]
 LR FULL theta 0.03 n 121 hit 78.5% ask 0.66 | paper +0.221 H1/H2 +0.236/+0.207 neg days 1/9 perm p 0.000 | LONDON +0.110/$1 tot $+76 [p05 +10, p95 +137] | vs NULL: McNemar 45v19 p=0.002, dPnL +9.4$1 sign-flip p=0.066
 LR NULL theta 0.05 n 44* hit 75.0% ask 0.64 | paper +0.216 H1/H2 +0.306/+0.126 neg days 3/9 perm p 0.301 | LONDON +0.091/$1 tot $+23 [p05 -16, p95 +65]
 LR FULL theta 0.05 n 82 hit 75.6% ask 0.64 | paper +0.247 H1/H2 +0.334/+0.160 neg days 2/9 perm p 0.021 | LONDON +0.122/$1 tot $+58 [p05 -1, p95 +122] | vs NULL: McNemar 32v12 p=0.004, dPnL +10.7$1 sign-flip p=0.029
 LR NULL theta 0.10 n 14* hit 64.3% ask 0.54 | paper +0.305 H1/H2 +0.312/+0.298 neg days 2/7 perm p 0.595 | LONDON +0.151/$1 tot $+13 [p05 -20, p95 +44]
 LR FULL theta 0.10 n 29* hit 72.4% ask 0.59 | paper +0.356 H1/H2 +0.486/+0.234 neg days 3/8 perm p 0.114 | LONDON +0.203/$1 tot $+35 [p05 -8, p95 +75] | vs NULL: McNemar 15v6 p=0.078, dPnL +6.0$1 sign-flip p=0.148
 GBM NULL theta 0.00 n 167 hit 77.2% ask 0.69 | paper +0.131 H1/H2 +0.179/+0.083 neg days 2/9 perm p 0.034 | LONDON +0.024/$1 tot $+23 [p05 -46, p95 +91]
 GBM FULL theta 0.00 n 138 hit 76.8% ask 0.65 | paper +0.154 H1/H2 +0.235/+0.074 neg days 2/9 perm p 0.006 | LONDON +0.044/$1 tot $+35 [p05 -34, p95 +100] | vs NULL: McNemar 14v31 p=0.016, dPnL -0.5$1 sign-flip p=0.536
 GBM NULL theta 0.03 n 71 hit 80.3% ask 0.64 | paper +0.317 H1/H2 +0.357/+0.277 neg days 1/9 perm p 0.001 | LONDON +0.194/$1 tot $+79 [p05 +25, p95 +134]
 GBM FULL theta 0.03 n 88 hit 75.0% ask 0.62 | paper +0.234 H1/H2 +0.345/+0.122 neg days 1/9 perm p 0.010 | LONDON +0.109/$1 tot $+56 [p05 -7, p95 +116] | vs NULL: McNemar 30v29 p=1.000, dPnL -1.9$1 sign-flip p=0.625
 GBM NULL theta 0.05 n 44* hit 75.0% ask 0.61 | paper +0.327 H1/H2 +0.388/+0.267 neg days 2/8 perm p 0.030 | LONDON +0.188/$1 tot $+48 [p05 -3, p95 +99]
 GBM FULL theta 0.05 n 65 hit 75.4% ask 0.58 | paper +0.295 H1/H2 +0.454/+0.141 neg days 3/9 perm p 0.001 | LONDON +0.161/$1 tot $+61 [p05 +6, p95 +115] | vs NULL: McNemar 30v19 p=0.152, dPnL +4.8$1 sign-flip p=0.166
 GBM NULL theta 0.10 n 18* hit 72.2% ask 0.53 | paper +0.610 H1/H2 +0.188/+1.032 neg days 2/7 perm p 0.368 | LONDON +0.415/$1 tot $+44 [p05 +1, p95 +90]
 GBM FULL theta 0.10 n 30* hit 80.0% ask 0.55 | paper +0.604 H1/H2 +0.653/+0.554 neg days 1/9 perm p 0.005 | LONDON +0.436/$1 tot $+76 [p05 +29, p95 +124] | vs NULL: McNemar 16v6 p=0.052, dPnL +7.1$1 sign-flip p=0.045

== arm B universe REV&R1 quote age 1 s
 LR NULL theta 0.00 n 142 hit 76.8% ask 0.66 | paper +0.165 H1/H2 +0.214/+0.116 neg days 1/9 perm p 0.004 | LONDON +0.054/$1 tot $+44 [p05 -21, p95 +114]
 LR FULL theta 0.00 n 141 hit 76.6% ask 0.65 | paper +0.169 H1/H2 +0.220/+0.118 neg days 1/9 perm p 0.001 | LONDON +0.057/$1 tot $+47 [p05 -22, p95 +114] | vs NULL: McNemar 13v14 p=1.000, dPnL +0.4$1 sign-flip p=0.445
 LR NULL theta 0.03 n 57* hit 78.9% ask 0.64 | paper +0.266 H1/H2 +0.302/+0.230 neg days 2/9 perm p 0.015 | LONDON +0.153/$1 tot $+50 [p05 +4, p95 +97]
 LR FULL theta 0.03 n 95 hit 76.8% ask 0.63 | paper +0.244 H1/H2 +0.273/+0.215 neg days 1/9 perm p 0.002 | LONDON +0.123/$1 tot $+67 [p05 +6, p95 +132] | vs NULL: McNemar 34v16 p=0.015, dPnL +8.0$1 sign-flip p=0.100
 LR NULL theta 0.05 n 36* hit 72.2% ask 0.62 | paper +0.210 H1/H2 +0.188/+0.232 neg days 3/9 perm p 0.358 | LONDON +0.088/$1 tot $+19 [p05 -22, p95 +59]
 LR FULL theta 0.05 n 64 hit 75.0% ask 0.62 | paper +0.293 H1/H2 +0.354/+0.231 neg days 2/9 perm p 0.014 | LONDON +0.155/$1 tot $+58 [p05 -0, p95 +113] | vs NULL: McNemar 25v9 p=0.009, dPnL +11.2$1 sign-flip p=0.015
 LR NULL theta 0.10 n 13* hit 69.2% ask 0.52 | paper +0.405 H1/H2 +0.531/+0.298 neg days 2/7 perm p 0.495 | LONDON +0.247/$1 tot $+19 [p05 -13, p95 +50]
 LR FULL theta 0.10 n 27* hit 74.1% ask 0.59 | paper +0.405 H1/H2 +0.495/+0.322 neg days 2/8 perm p 0.063 | LONDON +0.253/$1 tot $+40 [p05 -2, p95 +82] | vs NULL: McNemar 14v6 p=0.115, dPnL +5.7$1 sign-flip p=0.159
 GBM NULL theta 0.00 n 125 hit 80.0% ask 0.66 | paper +0.217 H1/H2 +0.301/+0.134 neg days 1/9 perm p 0.000 | LONDON +0.107/$1 tot $+77 [p05 +14, p95 +142]
 GBM FULL theta 0.00 n 114 hit 76.3% ask 0.63 | paper +0.175 H1/H2 +0.240/+0.109 neg days 2/9 perm p 0.000 | LONDON +0.065/$1 tot $+43 [p05 -19, p95 +108] | vs NULL: McNemar 9v24 p=0.014, dPnL -7.2$1 sign-flip p=0.962
 GBM NULL theta 0.03 n 55* hit 78.2% ask 0.58 | paper +0.346 H1/H2 +0.364/+0.329 neg days 1/9 perm p 0.004 | LONDON +0.217/$1 tot $+69 [p05 +21, p95 +120]
 GBM FULL theta 0.03 n 77 hit 76.6% ask 0.59 | paper +0.281 H1/H2 +0.378/+0.186 neg days 2/9 perm p 0.000 | LONDON +0.150/$1 tot $+67 [p05 +9, p95 +127] | vs NULL: McNemar 29v19 p=0.193, dPnL +2.6$1 sign-flip p=0.297
 GBM NULL theta 0.05 n 36* hit 72.2% ask 0.57 | paper +0.343 H1/H2 +0.420/+0.266 neg days 2/8 perm p 0.052 | LONDON +0.190/$1 tot $+40 [p05 -7, p95 +90]
 GBM FULL theta 0.05 n 59* hit 76.3% ask 0.57 | paper +0.341 H1/H2 +0.479/+0.208 neg days 2/9 perm p 0.000 | LONDON +0.198/$1 tot $+68 [p05 +14, p95 +120] | vs NULL: McNemar 28v13 p=0.028, dPnL +7.8$1 sign-flip p=0.043
 GBM NULL theta 0.10 n 16* hit 75.0% ask 0.52 | paper +0.717 H1/H2 +0.148/+1.286 neg days 2/7 perm p 0.237 | LONDON +0.524/$1 tot $+50 [p05 +6, p95 +94]
 GBM FULL theta 0.10 n 29* hit 82.8% ask 0.54 | paper +0.678 H1/H2 +0.669/+0.686 neg days 1/9 perm p 0.000 | LONDON +0.512/$1 tot $+86 [p05 +40, p95 +134] | vs NULL: McNemar 16v5 p=0.027, dPnL +8.2$1 sign-flip p=0.025

== verify.py: arm B REV age 1 GBM FULL theta 0.05
==============================================================================
FINDING: REV brain B/REV/age1/GBM/th0.05 (+0.161/fire, n=65)
==============================================================================
 [PASS] grading provenance venues_outcome vs v12_lane_actual disagree on 0/26 (0.0%)
 [FAIL] quote age rule=stale, max age 1.0s from Polymarket tape q <- the quote can PREDATE the decision; the fire rule will select the randomly cheap ones
 [PASS] sample size all 1 cells >= 60
 [PASS] both halves h1 +0.454 / h2 +0.141
 [PASS] permutation control coin-flip side at the opposite ask, p=0.001
 [PASS] sweep shape monotone: [0.044 0.109 0.161 0.436]
 [PASS] cost sensitivity +0c:+0.295 +2c:+0.248 +5c:+0.185
 [PASS] beats the null mine +0.161 vs REV R1 lane-p baseline (London) +0.149
 [FAIL] beats the null mine +0.161 vs same cell, venue-only NULL learner (London) +0.188
 [FAIL] paired test n=79, agree on 30, discordant 49 (30 vs 19), edge +0.139, exact McNemar p=0.152
------------------------------------------------------------------------------
 VERDICT: NOT A FINDING - failed: quote age, beats the null, paired test


== verify.py: arm B REV age 0 GBM FULL theta 0.03
==============================================================================
FINDING: REV brain B/REV/age0/GBM/th0.03 (+0.150/fire, n=64)
==============================================================================
 [PASS] grading provenance venues_outcome vs v12_lane_actual disagree on 0/27 (0.0%)
 [PASS] quote age rule=same-instant, max age 0.0s from Polymarket tape q
 [PASS] sample size all 1 cells >= 60
 [PASS] both halves h1 +0.368 / h2 +0.159
 [PASS] permutation control coin-flip side at the opposite ask, p=0.001
 [PASS] sweep shape monotone: [0.028 0.15 0.168 0.39 ]
 [PASS] cost sensitivity +0c:+0.264 +2c:+0.223 +5c:+0.168
 [PASS] beats the null mine +0.150 vs REV R1 lane-p baseline (London) +0.061
 [FAIL] beats the null mine +0.150 vs same cell, venue-only NULL learner (London) +0.178
 [FAIL] paired test n=89, agree on 34, discordant 55 (28 vs 27), edge +0.011, exact McNemar p=1.000
------------------------------------------------------------------------------
 VERDICT: NOT A FINDING - failed: beats the null, paired test


```
