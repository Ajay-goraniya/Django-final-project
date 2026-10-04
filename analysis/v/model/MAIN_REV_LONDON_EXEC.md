# MAIN / REVERSAL under London-like execution + a quote-timing fix - V 09-27

Script `analysis/v/model/lane_exec_sim.py` on the window-1 call streams (09-07..09-16, lane_ev_replay.py). London
execution = LONDON_EXEC_MODEL.md (fill 54% if it would win / 65% if it would lose, slippage -1/+2/+11c, fee, $10).

## The replay quote was flattering the lanes (lookahead / stale price)
replay_lanes_1s.py and lane_ev_replay.py price a call at the tape row NEAREST the call within +-5 s - it can be a
FUTURE row, or one taken before a fast move. Re-priced with PAST-ONLY quotes, REVERSAL 0-240 s R1 (London-exec, per $1):
| quote age allowed | 5 s | 2 s | 1 s | 0 s (same second) |
|---|---|---|---|---|
| paper | +0.937 | +0.430 | +0.289 | +0.170 |
| London exec | +0.633 | +0.262 | +0.151 | **+0.065** (total p05 -7, p95 +122, n149) |
Monotone in the quote age: the fresher the price, the smaller the edge. The same-second number matches Zurich's live
shadow REVERSAL (+0.064 on 77). **Every earlier replay REVERSAL/MAIN number built on the +-5 s quote is an upper bound.**

## Verdict
- **MAIN: dead in every window and every quote age.** Its "+0.186 after 240 s" was the future quote. Past-only, 240-295 s
  MAIN is n18-27, negative. Changing the 240 s rule for MAIN would buy nothing.
- **REVERSAL (as it is, R1 lane-p breakeven, 0-240 s): about +0.07/$1 under London execution, not proven** (p05 of the
  total below zero). Consistent with Zurich shadow. Not a finding; Zurich window 2 and more shadow fills decide it.
- Calibrated EV (R2) helped neither lane (MAIN_REV_EV_WINDOW1.md).

## Full output (ages 2, 5, 0, 1 s)
```
== past-only quote age <= 2 s

MAIN: 35538 calls with a past-only quote <= 2s old
  0-240 s   R0 first call          n 827  hit 76.7% ask 0.79 | paper -0.023 (H1 -0.013 H2 -0.034, w/o top3 -0.029) | LONDON-EXEC -0.107/$1, total $-506.1 [p05 -623.5, p95 -371.9]
  0-240 s   R1 lane-p breakeven    n  76  hit 57.9% ask 0.59 | paper -0.024 (H1 -0.043 H2 -0.004, w/o top3 -0.086) | LONDON-EXEC -0.155/$1, total $-70.9 [p05 -130.7, p95 -13.1]
  240-295 s R0 first call          n  25* hit 68.0% ask 0.82 | paper -0.130 (H1 -0.290 H2 +0.017, w/o top3 -0.244) | LONDON-EXEC -0.215/$1, total $-31.8 [p05 -56.4, p95 -7.0]
  240-295 s R1 lane-p breakeven    n   3* hit 33.3% ask 0.06 | paper -0.271 (H1 -1.000 H2 +0.093, w/o top3 +nan) | LONDON-EXEC -0.417/$1, total $-8.3 [p05 -21.3, p95 +9.6]
  all       R0 first call          n 830  hit 76.6% ask 0.79 | paper -0.024 (H1 -0.012 H2 -0.037, w/o top3 -0.030) | LONDON-EXEC -0.109/$1, total $-518.0 [p05 -644.7, p95 -399.5]
  all       R1 lane-p breakeven    n  79  hit 57.0% ask 0.59 | paper -0.033 (H1 -0.067 H2 +0.000, w/o top3 -0.094) | LONDON-EXEC -0.157/$1, total $-75.2 [p05 -140.4, p95 -10.8]

REVERSAL: 11836 calls with a past-only quote <= 2s old
  0-240 s   R0 first call          n 211  hit 73.0% ask 0.64 | paper +0.315 (H1 +0.154 H2 +0.474, w/o top3 +0.197) | LONDON-EXEC +0.155/$1, total $+191.8 [p05 +37.8, p95 +341.2]
  0-240 s   R1 lane-p breakeven    n 174  hit 75.3% ask 0.60 | paper +0.430 (H1 +0.264 H2 +0.595, w/o top3 +0.288) | LONDON-EXEC +0.262/$1, total $+266.6 [p05 +129.8, p95 +407.7]
  240-295 s R0 first call          n  76  hit 61.8% ask 0.64 | paper +0.647 (H1 +0.004 H2 +1.291, w/o top3 +0.030) | LONDON-EXEC +0.314/$1, total $+143.5 [p05 -48.7, p95 +432.9]
  240-295 s R1 lane-p breakeven    n  54* hit 53.7% ask 0.46 | paper +0.892 (H1 +1.686 H2 +0.098, w/o top3 +0.022) | LONDON-EXEC +0.439/$1, total $+145.6 [p05 -63.6, p95 +376.4]
  all       R0 first call          n 255  hit 70.2% ask 0.63 | paper +0.384 (H1 +0.180 H2 +0.586, w/o top3 +0.242) | LONDON-EXEC +0.194/$1, total $+290.5 [p05 +66.7, p95 +524.8]
  all       R1 lane-p breakeven    n 209  hit 70.3% ask 0.59 | paper +0.493 (H1 +0.275 H2 +0.709, w/o top3 +0.321) | LONDON-EXEC +0.278/$1, total $+343.5 [p05 +130.5, p95 +561.7]
== past-only quote age <= 5 s

MAIN: 60231 calls with a past-only quote <= 5s old
  0-240 s   R0 first call          n 870  hit 77.0% ask 0.78 | paper -0.016 (H1 +0.000 H2 -0.032, w/o top3 -0.022) | LONDON-EXEC -0.100/$1, total $-498.0 [p05 -631.6, p95 -362.2]
  0-240 s   R1 lane-p breakeven    n  95  hit 55.8% ask 0.60 | paper -0.084 (H1 -0.170 H2 +0.001, w/o top3 -0.137) | LONDON-EXEC -0.205/$1, total $-118.3 [p05 -179.2, p95 -57.9]
  240-295 s R0 first call          n  27* hit 70.4% ask 0.81 | paper -0.115 (H1 -0.256 H2 +0.017, w/o top3 -0.200) | LONDON-EXEC -0.205/$1, total $-32.5 [p05 -57.1, p95 -8.1]
  240-295 s R1 lane-p breakeven    n   3* hit 33.3% ask 0.06 | paper -0.271 (H1 -1.000 H2 +0.093, w/o top3 +nan) | LONDON-EXEC -0.417/$1, total $-8.3 [p05 -21.3, p95 +9.6]
  all       R0 first call          n 873  hit 77.0% ask 0.78 | paper -0.017 (H1 +0.000 H2 -0.034, w/o top3 -0.022) | LONDON-EXEC -0.100/$1, total $-502.3 [p05 -635.1, p95 -372.7]
  all       R1 lane-p breakeven    n  98  hit 55.1% ask 0.60 | paper -0.090 (H1 -0.169 H2 -0.010, w/o top3 -0.142) | LONDON-EXEC -0.204/$1, total $-121.6 [p05 -185.6, p95 -55.6]

REVERSAL: 20144 calls with a past-only quote <= 5s old
  0-240 s   R0 first call          n 217  hit 72.8% ask 0.57 | paper +0.796 (H1 +0.559 H2 +1.031, w/o top3 +0.565) | LONDON-EXEC +0.523/$1, total $+667.5 [p05 +377.6, p95 +1030.8]
  0-240 s   R1 lane-p breakeven    n 193  hit 75.1% ask 0.55 | paper +0.937 (H1 +0.691 H2 +1.180, w/o top3 +0.679) | LONDON-EXEC +0.633/$1, total $+718.5 [p05 +434.5, p95 +1094.7]
  240-295 s R0 first call          n  90  hit 62.2% ask 0.56 | paper +1.120 (H1 +1.089 H2 +1.150, w/o top3 +0.349) | LONDON-EXEC +0.618/$1, total $+335.1 [p05 +18.0, p95 +703.7]
  240-295 s R1 lane-p breakeven    n  71  hit 59.2% ask 0.45 | paper +1.435 (H1 +1.414 H2 +1.456, w/o top3 +0.463) | LONDON-EXEC +0.819/$1, total $+355.0 [p05 +42.6, p95 +772.5]
  all       R0 first call          n 265  hit 69.8% ask 0.56 | paper +0.911 (H1 +0.552 H2 +1.267, w/o top3 +0.623) | LONDON-EXEC +0.561/$1, total $+880.3 [p05 +484.8, p95 +1383.0]
  all       R1 lane-p breakeven    n 236  hit 70.8% ask 0.54 | paper +1.050 (H1 +0.700 H2 +1.399, w/o top3 +0.728) | LONDON-EXEC +0.687/$1, total $+961.2 [p05 +564.1, p95 +1498.5]
== past-only quote age <= 0 s
MAIN: 11765 calls with a past-only quote <= 0s old
  0-240 s   R0 first call          n 737  hit 77.7% ask 0.79 | paper -0.017 (H1 -0.005 H2 -0.028, w/o top3 -0.023) | LONDON-EXEC -0.097/$1, total $-407.9 [p05 -532.5, p95 -292.8]
  0-240 s   R1 lane-p breakeven    n  55* hit 56.4% ask 0.59 | paper -0.039 (H1 +0.026 H2 -0.102, w/o top3 -0.125) | LONDON-EXEC -0.167/$1, total $-55.7 [p05 -104.3, p95 -5.3]
  240-295 s R0 first call          n  18* hit 77.8% ask 0.82 | paper +0.008 (H1 -0.187 H2 +0.202, w/o top3 -0.131) | LONDON-EXEC -0.073/$1, total $-7.6 [p05 -26.7, p95 +12.2]
  240-295 s R1 lane-p breakeven    n   2* hit 50.0% ask 0.25 | paper +0.093 (H1 -1.000 H2 +1.187, w/o top3 +nan) | LONDON-EXEC -0.116/$1, total $-1.4 [p05 -10.7, p95 +12.1]
  all       R0 first call          n 739  hit 77.8% ask 0.79 | paper -0.016 (H1 -0.005 H2 -0.028, w/o top3 -0.022) | LONDON-EXEC -0.098/$1, total $-416.4 [p05 -529.3, p95 -293.5]
  all       R1 lane-p breakeven    n  57* hit 56.1% ask 0.59 | paper -0.035 (H1 -0.011 H2 -0.058, w/o top3 -0.118) | LONDON-EXEC -0.162/$1, total $-56.3 [p05 -105.2, p95 -5.6]
REVERSAL: 3890 calls with a past-only quote <= 0s old
  0-240 s   R0 first call          n 201  hit 75.1% ask 0.69 | paper +0.091 (H1 +0.127 H2 +0.055, w/o top3 +0.066) | LONDON-EXEC -0.011/$1, total $-12.8 [p05 -83.3, p95 +57.8]
  0-240 s   R1 lane-p breakeven    n 149  hit 77.9% ask 0.64 | paper +0.170 (H1 +0.239 H2 +0.102, w/o top3 +0.138) | LONDON-EXEC +0.065/$1, total $+56.5 [p05 -7.1, p95 +122.0]
  240-295 s R0 first call          n  59* hit 61.0% ask 0.64 | paper -0.003 (H1 -0.130 H2 +0.120, w/o top3 -0.212) | LONDON-EXEC -0.154/$1, total $-54.8 [p05 -121.2, p95 +20.3]
  240-295 s R1 lane-p breakeven    n  39* hit 46.2% ask 0.45 | paper -0.054 (H1 -0.241 H2 +0.124, w/o top3 -0.384) | LONDON-EXEC -0.229/$1, total $-56.3 [p05 -123.1, p95 +15.7]
  all       R0 first call          n 239  hit 71.1% ask 0.68 | paper +0.073 (H1 +0.061 H2 +0.085, w/o top3 +0.020) | LONDON-EXEC -0.039/$1, total $-54.8 [p05 -172.2, p95 +62.2]
  all       R1 lane-p breakeven    n 176  hit 71.6% ask 0.62 | paper +0.140 (H1 +0.187 H2 +0.092, w/o top3 +0.068) | LONDON-EXEC +0.018/$1, total $+18.4 [p05 -71.6, p95 +106.9]
== past-only quote age <= 1 s
MAIN: 23601 calls with a past-only quote <= 1s old
  0-240 s   R0 first call          n 788  hit 77.3% ask 0.79 | paper -0.021 (H1 -0.009 H2 -0.033, w/o top3 -0.027) | LONDON-EXEC -0.102/$1, total $-459.6 [p05 -568.8, p95 -337.6]
  0-240 s   R1 lane-p breakeven    n  63  hit 52.4% ask 0.59 | paper -0.112 (H1 -0.106 H2 -0.118, w/o top3 -0.190) | LONDON-EXEC -0.231/$1, total $-88.6 [p05 -136.2, p95 -42.0]
  240-295 s R0 first call          n  22* hit 72.7% ask 0.82 | paper -0.072 (H1 -0.233 H2 +0.088, w/o top3 -0.195) | LONDON-EXEC -0.164/$1, total $-21.2 [p05 -43.4, p95 +3.1]
  240-295 s R1 lane-p breakeven    n   3* hit 33.3% ask 0.06 | paper -0.271 (H1 -1.000 H2 +0.093, w/o top3 +nan) | LONDON-EXEC -0.417/$1, total $-8.3 [p05 -21.3, p95 +9.6]
  all       R0 first call          n 791  hit 77.2% ask 0.79 | paper -0.022 (H1 -0.009 H2 -0.035, w/o top3 -0.028) | LONDON-EXEC -0.105/$1, total $-477.4 [p05 -598.1, p95 -362.6]
  all       R1 lane-p breakeven    n  66  hit 51.5% ask 0.58 | paper -0.119 (H1 -0.104 H2 -0.135, w/o top3 -0.195) | LONDON-EXEC -0.243/$1, total $-98.1 [p05 -154.9, p95 -37.5]
REVERSAL: 7842 calls with a past-only quote <= 1s old
  0-240 s   R0 first call          n 208  hit 73.1% ask 0.67 | paper +0.177 (H1 +0.108 H2 +0.245, w/o top3 +0.085) | LONDON-EXEC +0.052/$1, total $+63.2 [p05 -55.5, p95 +190.8]
  0-240 s   R1 lane-p breakeven    n 163  hit 76.1% ask 0.63 | paper +0.289 (H1 +0.202 H2 +0.375, w/o top3 +0.175) | LONDON-EXEC +0.151/$1, total $+143.7 [p05 +33.8, p95 +257.3]
  240-295 s R0 first call          n  71  hit 60.6% ask 0.62 | paper +0.425 (H1 +0.004 H2 +0.834, w/o top3 -0.079) | LONDON-EXEC +0.142/$1, total $+60.8 [p05 -80.0, p95 +292.6]
  240-295 s R1 lane-p breakeven    n  49* hit 49.0% ask 0.45 | paper +0.582 (H1 +1.123 H2 +0.063, w/o top3 -0.152) | LONDON-EXEC +0.201/$1, total $+61.6 [p05 -89.5, p95 +317.3]
  all       R0 first call          n 250  hit 70.0% ask 0.66 | paper +0.194 (H1 +0.111 H2 +0.277, w/o top3 +0.109) | LONDON-EXEC +0.044/$1, total $+65.1 [p05 -79.9, p95 +214.5]
  all       R1 lane-p breakeven    n 196  hit 70.4% ask 0.61 | paper +0.288 (H1 +0.219 H2 +0.357, w/o top3 +0.181) | LONDON-EXEC +0.123/$1, total $+142.7 [p05 +3.5, p95 +282.7]
```
