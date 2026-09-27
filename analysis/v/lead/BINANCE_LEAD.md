# Can we predict Binance's next 0.3-1 s from sub-second order flow? (stage 1, V/lead, 09-27)

**VERDICT: NO for the moves that matter. Stop here.**
1. WHEN a move comes is predictable (AUC 0.75-0.80 vs 0.58-0.67 momentum), but unsigned activity alone does as well (0.72-0.75): it is volatility timing, not direction.
2. WHICH WAY a >=5 bps move goes, 100 / 250 / 500 ms before it starts: direction AUC 0.54 / 0.55 / 0.51 (GBM), coin level. At an alarm budget of 3e-4 of 100 ms points (~11/h, ~1 per candle) only 2.3-2.8% of >=5 bps moves are flagged that early.
3. Small moves ARE directional: the sign of the >=2 bps move still to come AFTER a 300 ms landing is called at AUC 0.74 vs 0.60 momentum, all 7 days, halves pass. The source is perp/basis. But an alarm catches only +0.1-0.2 bps on average after landing (5 bps model at 11/h: right-way >=2 bps 19% vs wrong-way 16%).
4. Stage 2 (closing vs opening TWAP60): +0.1-0.2 bps = +1-3 pp of resolution probability on the line mid-candle, ~0 off it, and the same size as the Binance->Chainlink proxy error on the move (median 0.22 bps, Task 108). A real >=5 bps move would be worth +20-50 pp near the line, but that one is not predictable with lead.
5. Perp leads spot by 2 ms (1 ms xcorr peak, 8/8 days), median 5 ms on >=5 bps moves. That is useless against ~230 ms venue latency plus Tokyo->London transport.
verify.py: >=2 bps claim passes sample/halves/null, FAILS grading (Binance labels, not the settlement oracle); >=5 bps FAILS halves (-0.010 / +0.129).

**Data / method.** data.binance.vision aggTrades BTCUSDT spot + USD-M perp, 8 UTC days 2026-09-18..09-25 (incl. a weekend). 100 ms grid, 864k points/day.
Features strictly <= t (perp ms stamps moved to the END of their ms): spot & perp signed taker vol, counts, imbalance over 100/250/500/1000/3000 ms,
intensity acceleration, returns over the same windows, perp-spot basis change 100/250/500/1000 ms + vs 60 s mean, largest trade (size, signed) in 1 s,
same-side run length/qty, time since last trade (53 total). Price = last trade (spot tick 0.01 USD ~0.001 bps; no book data used).
Targets: max spot move over (t, t+H] >= X bps up / down, X = 2/5/10, H = 300/500/1000 ms. Walk-forward by day: train all days before, test the next
(7 test days). Models: LR (signed-log, standardised) and LightGBM (200 trees, 31 leaves); NULL = same model on the last 1 s spot return only;
extra null = GBM on UNSIGNED activity only. Negatives subsampled with weights; alarm thresholds fixed on TRAIN scores at a flag rate, realised test
rate shown. Episodes: a >= X bps move completed inside 1 s on a 10 ms grid; start = the last tick at the extreme.
Caveats: 8 days; last trade, not mid; exchange-engine timestamps (spot us, perp ms); our Binance->London transport latency is NOT measured here;
ablation is one walk-forward split (train 09-18..22, test 09-23..25). Scripts: build.py, model.py, analyze.py, direction.py, latency.py,
ablation.py, perp_lead.py, stage2.py, verify_lead.py (run order as listed; scratch data ~0.5 GB + scores 0.8 GB, not committed).

## 1. Perp vs spot lead
**Cross-correlation of spot vs perp log returns** (+lag = perp return EARLIER than the spot return it correlates with = perp leads)

| grid | per-day peak lag | pooled corr at lags -2 / -1 / 0 / +1 / +2 bins | sum of corr, perp-leads side vs spot-leads side |
|---|---|---|---|
| 10 ms | [0, 0, 0, 0, 0, 0, 0, 0] x10 ms | 0.069 / 0.125 / 0.349 / 0.177 / 0.073 | 0.80 vs 0.58 |
| 1 ms | [2, 2, 2, 2, 2, 2, 2, 2] ms | 0.019 / 0.026 / 0.050 / 0.061 / 0.087 (peak +2 ms: 0.087) | 0.72 vs 0.52 |

**Event timing**: each spot episode (>= X bps in 1 s); time each tape first completes X/2 from its own extreme; lead = spot time - perp time (+ = perp first). Placebo = spot run through the perp rule (what the rule manufactures by itself).

| X | n | perp: median ms [q25, q75] | perp first | perp first by >=100 ms | placebo: first by >=100 ms | per-day median (ms) |
|---|---|---|---|---|---|---|
| 2 bps | 16958 | 5.1 [-2.7, 123.0] | 0.67 | 0.28 | 0.07 | [5.7, 1.0, 2.2, 9.9, 3.1, 9.3, 4.7, 4.9] |
| 5 bps | 1721 | 5.2 [-3.9, 111.5] | 0.68 | 0.26 | 0.11 | [5.6, -3.3, 1.9, 13.8, 2.0, 5.4, 6.5, 2.8] |
| 10 bps | 179 | 15.6 [-4.7, 106.5] | 0.70 | 0.27 | 0.12 | [-3.5, 4.5, 28.3, 44.0, -15.3, 15.6, -9.9, 8.3] |

## 2. Walk-forward grids (AUC, precision/recall by alarm budget, lead time, alarm direction, per day)

### AUC (mean over 7 walk-forward test days; [min..max] across days); positives = test grid points

| target | pos(test) | LR full | LR null(mom 1s) | GBM full | GBM null(mom 1s) | GBM activity-only |
|---|---|---|---|---|---|---|
| up >=2bps in 300ms | 9335 | 0.789 [0.73..0.84] | 0.605 [0.54..0.64] | 0.800 [0.74..0.85] | 0.670 [0.58..0.73] | - |
| up >=2bps in 500ms | 18740 | 0.784 [0.73..0.83] | 0.602 [0.56..0.63] | 0.793 [0.73..0.83] | 0.658 [0.60..0.71] | - |
| up >=2bps in 1000ms | 47861 | 0.773 [0.72..0.80] | 0.593 [0.57..0.62] | 0.787 [0.73..0.82] | 0.645 [0.59..0.68] | 0.747 [0.69..0.80] |
| up >=5bps in 300ms | 638 | 0.724 [0.66..0.79] | 0.624 [0.50..0.70] | 0.748 [0.65..0.85] | 0.645 [0.55..0.77] | - |
| up >=5bps in 500ms | 1337 | 0.778 [0.67..0.86] | 0.612 [0.49..0.71] | 0.760 [0.63..0.86] | 0.667 [0.58..0.76] | 0.718 [0.59..0.85] |
| up >=5bps in 1000ms | 3544 | 0.783 [0.66..0.88] | 0.577 [0.53..0.64] | 0.767 [0.65..0.86] | 0.662 [0.56..0.78] | 0.746 [0.64..0.85] |
| up >=10bps in 300ms | 48 | 0.270 [0.01..0.56]* | 0.273 [0.00..0.49]* | 0.507 [0.16..1.00]* | 0.613 [0.42..1.00]* | - |
| up >=10bps in 500ms | 112 | 0.515 [0.36..0.67] | 0.510 [0.27..0.82] | 0.692 [0.32..0.96] | 0.763 [0.64..0.91] | - |
| up >=10bps in 1000ms | 357 | 0.446 [0.00..0.90] | 0.372 [0.00..0.70] | 0.821 [0.67..0.96] | 0.721 [0.52..0.97] | 0.823 [0.70..0.99] |
| dn >=2bps in 300ms | 10094 | 0.793 [0.71..0.85] | 0.604 [0.58..0.64] | 0.802 [0.73..0.85] | 0.658 [0.60..0.72] | - |
| dn >=2bps in 500ms | 19947 | 0.788 [0.71..0.83] | 0.600 [0.57..0.63] | 0.798 [0.72..0.84] | 0.649 [0.58..0.70] | - |
| dn >=2bps in 1000ms | 49810 | 0.778 [0.70..0.81] | 0.594 [0.57..0.61] | 0.791 [0.72..0.83] | 0.641 [0.59..0.68] | 0.747 [0.66..0.79] |
| dn >=5bps in 300ms | 659 | 0.688 [0.50..0.83] | 0.543 [0.36..0.68] | 0.736 [0.60..0.85] | 0.640 [0.49..0.78] | - |
| dn >=5bps in 500ms | 1407 | 0.761 [0.65..0.87] | 0.550 [0.38..0.67] | 0.748 [0.66..0.85] | 0.630 [0.50..0.79] | 0.732 [0.62..0.85] |
| dn >=5bps in 1000ms | 3829 | 0.764 [0.64..0.88] | 0.561 [0.50..0.60] | 0.744 [0.59..0.86] | 0.653 [0.58..0.77] | 0.748 [0.63..0.86] |
| dn >=10bps in 300ms | 53 | 0.609 [0.29..0.94]* | 0.354 [0.19..0.51]* | 0.649 [0.19..0.92]* | 0.665 [0.50..0.84]* | - |
| dn >=10bps in 500ms | 118 | 0.500 [0.19..0.90] | 0.580 [0.33..0.80] | 0.752 [0.45..0.92] | 0.733 [0.52..0.92] | - |
| dn >=10bps in 1000ms | 330 | 0.556 [0.09..0.90] | 0.442 [0.19..0.67] | 0.790 [0.60..0.97] | 0.658 [0.52..0.88] | 0.787 [0.57..0.97] |

`*` = under 60 positive test grid points: insufficient, do not read.

### Precision / recall by alarm budget (threshold fixed on TRAIN at that flag rate)

flag rate 1e-4 = 3.6 alarms/hour, 3e-4 = 11/h (~1 per 5-min candle), 1e-3 = 36/h, 3e-3 = 108/h, 1e-2 = 360/h. Precision = alarm followed by the move; recall = share of positive grid points alarmed.

**up >= 5 bps in 500 ms** (test positives 1337, base rate 0.00022)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 6.9e-05 / 0.156 / 0.049 | 1.8e-04 / 0.094 / 0.075 | 6.8e-04 / 0.041 / 0.126 | 2.4e-03 / 0.017 / 0.192 | 9.1e-03 / 0.008 / 0.319 |
| LR null(mom 1s) | 1.3e-04 / 0.093 / 0.055 | 3.0e-04 / 0.055 / 0.076 | 9.4e-04 / 0.025 / 0.106 | 2.9e-03 / 0.011 / 0.148 | 1.0e-02 / 0.005 / 0.214 |
| GBM full | 1.9e-05 / 0.168 / 0.014 | 1.6e-04 / 0.094 / 0.069 | 7.6e-04 / 0.041 / 0.141 | 2.6e-03 / 0.018 / 0.214 | 1.0e-02 / 0.007 / 0.325 |
| GBM null(mom 1s) | 1.6e-03 / 0.008 / 0.058 | 1.6e-03 / 0.008 / 0.058 | 1.6e-03 / 0.008 / 0.058 | 3.4e-03 / 0.012 / 0.191 | 1.2e-02 / 0.005 / 0.268 |
| GBM activity-only | 6.9e-05 / 0.149 / 0.046 | 2.2e-04 / 0.088 / 0.089 | 8.5e-04 / 0.042 / 0.164 | 2.9e-03 / 0.017 / 0.221 | 1.1e-02 / 0.006 / 0.315 |

**up >= 5 bps in 1000 ms** (test positives 3544, base rate 0.00059)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 1.0e-04 / 0.264 / 0.047 | 2.5e-04 / 0.186 / 0.079 | 8.0e-04 / 0.098 / 0.133 | 2.6e-03 / 0.046 / 0.205 | 9.8e-03 / 0.020 / 0.335 |
| LR null(mom 1s) | 1.3e-04 / 0.153 / 0.034 | 3.0e-04 / 0.095 / 0.049 | 9.4e-04 / 0.047 / 0.075 | 2.9e-03 / 0.022 / 0.110 | 1.0e-02 / 0.010 / 0.179 |
| GBM full | 1.3e-05 / 0.284 / 0.006 | 1.4e-04 / 0.170 / 0.041 | 7.0e-04 / 0.093 / 0.111 | 2.5e-03 / 0.048 / 0.203 | 9.8e-03 / 0.019 / 0.312 |
| GBM null(mom 1s) | 1.5e-03 / 0.022 / 0.055 | 1.5e-03 / 0.022 / 0.055 | 1.5e-03 / 0.022 / 0.055 | 3.1e-03 / 0.026 / 0.135 | 2.2e-02 / 0.006 / 0.214 |
| GBM activity-only | 6.3e-05 / 0.235 / 0.025 | 2.4e-04 / 0.188 / 0.078 | 8.4e-04 / 0.091 / 0.130 | 2.8e-03 / 0.043 / 0.204 | 1.1e-02 / 0.016 / 0.290 |

**up >= 2 bps in 1000 ms** (test positives 47861, base rate 0.00791)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 1.4e-04 / 0.505 / 0.009 | 3.2e-04 / 0.390 / 0.016 | 9.6e-04 / 0.302 / 0.037 | 2.9e-03 / 0.215 / 0.080 | 1.0e-02 / 0.135 / 0.178 |
| LR null(mom 1s) | 1.3e-04 / 0.376 / 0.006 | 3.0e-04 / 0.282 / 0.011 | 9.4e-04 / 0.184 / 0.022 | 2.9e-03 / 0.118 / 0.043 | 1.0e-02 / 0.071 / 0.092 |
| GBM full | 5.8e-05 / 0.509 / 0.004 | 1.8e-04 / 0.404 / 0.009 | 7.0e-04 / 0.333 / 0.029 | 2.5e-03 / 0.247 / 0.078 | 9.3e-03 / 0.153 / 0.181 |
| GBM null(mom 1s) | 1.1e-03 / 0.168 / 0.023 | 1.1e-03 / 0.168 / 0.023 | 1.4e-03 / 0.154 / 0.028 | 3.2e-03 / 0.120 / 0.049 | 2.3e-02 / 0.037 / 0.106 |
| GBM activity-only | 5.6e-05 / 0.440 / 0.003 | 2.0e-04 / 0.371 / 0.009 | 6.9e-04 / 0.308 / 0.027 | 2.2e-03 / 0.225 / 0.064 | 8.5e-03 / 0.140 / 0.151 |

**up >= 10 bps in 1000 ms** (test positives 357, base rate 0.00006)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 6.0e-05 / 0.019 / 0.020 | 1.9e-04 / 0.006 / 0.020 | 7.0e-04 / 0.002 / 0.028 | 2.3e-03 / 0.001 / 0.036 | 8.8e-03 / 0.000 / 0.070 |
| LR null(mom 1s) | 1.3e-04 / 0.057 / 0.120 | 3.0e-04 / 0.031 / 0.157 | 9.4e-04 / 0.013 / 0.213 | 2.9e-03 / 0.005 / 0.263 | 1.0e-02 / 0.002 / 0.317 |
| GBM full | 3.0e-05 / 0.000 / 0.000 | 1.6e-04 / 0.003 / 0.008 | 7.7e-04 / 0.004 / 0.056 | 2.7e-03 / 0.005 / 0.213 | 9.8e-03 / 0.002 / 0.353 |
| GBM null(mom 1s) | 1.7e-03 / 0.008 / 0.232 | 1.7e-03 / 0.008 / 0.232 | 1.7e-03 / 0.008 / 0.232 | 3.5e-03 / 0.004 / 0.249 | 1.1e-02 / 0.002 / 0.300 |
| GBM activity-only | 6.2e-05 / 0.003 / 0.003 | 2.1e-04 / 0.002 / 0.006 | 8.4e-04 / 0.003 / 0.042 | 2.8e-03 / 0.004 / 0.168 | 9.8e-03 / 0.002 / 0.406 |

**dn >= 5 bps in 500 ms** (test positives 1407, base rate 0.00023)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 1.1e-04 / 0.079 / 0.036 | 2.9e-04 / 0.052 / 0.066 | 9.7e-04 / 0.028 / 0.116 | 3.0e-03 / 0.015 / 0.189 | 1.1e-02 / 0.006 / 0.286 |
| LR null(mom 1s) | 9.6e-05 / 0.058 / 0.024 | 2.9e-04 / 0.029 / 0.036 | 9.6e-04 / 0.014 / 0.059 | 3.0e-03 / 0.008 / 0.109 | 1.1e-02 / 0.004 / 0.162 |
| GBM full | 1.8e-05 / 0.075 / 0.006 | 1.9e-04 / 0.065 / 0.052 | 8.8e-04 / 0.038 / 0.144 | 3.0e-03 / 0.017 / 0.211 | 1.1e-02 / 0.007 / 0.311 |
| GBM null(mom 1s) | 1.8e-03 / 0.012 / 0.093 | 1.8e-03 / 0.012 / 0.093 | 1.8e-03 / 0.012 / 0.093 | 3.6e-03 / 0.009 / 0.138 | 1.2e-02 / 0.004 / 0.193 |
| GBM activity-only | 5.0e-05 / 0.076 / 0.016 | 2.1e-04 / 0.062 / 0.055 | 8.8e-04 / 0.037 / 0.138 | 2.7e-03 / 0.016 / 0.190 | 9.5e-03 / 0.007 / 0.278 |

**dn >= 5 bps in 1000 ms** (test positives 3829, base rate 0.00063)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 1.3e-04 / 0.165 / 0.033 | 3.3e-04 / 0.121 / 0.062 | 9.7e-04 / 0.075 / 0.114 | 2.9e-03 / 0.042 / 0.189 | 1.0e-02 / 0.019 / 0.298 |
| LR null(mom 1s) | 1.1e-04 / 0.090 / 0.015 | 3.1e-04 / 0.053 / 0.026 | 9.8e-04 / 0.033 / 0.052 | 3.0e-03 / 0.019 / 0.091 | 1.1e-02 / 0.009 / 0.147 |
| GBM full | 1.0e-05 / 0.127 / 0.002 | 1.3e-04 / 0.114 / 0.024 | 7.6e-04 / 0.083 / 0.100 | 2.8e-03 / 0.045 / 0.196 | 1.1e-02 / 0.018 / 0.298 |
| GBM null(mom 1s) | 1.6e-03 / 0.025 / 0.065 | 1.6e-03 / 0.025 / 0.065 | 1.6e-03 / 0.025 / 0.065 | 3.3e-03 / 0.022 / 0.116 | 1.2e-02 / 0.011 / 0.198 |
| GBM activity-only | 4.1e-05 / 0.122 / 0.008 | 2.1e-04 / 0.114 / 0.037 | 8.2e-04 / 0.077 / 0.100 | 2.7e-03 / 0.042 / 0.179 | 9.3e-03 / 0.019 / 0.277 |

**dn >= 2 bps in 1000 ms** (test positives 49810, base rate 0.00824)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 1.9e-04 / 0.444 / 0.010 | 3.8e-04 / 0.382 / 0.018 | 1.1e-03 / 0.290 / 0.037 | 3.0e-03 / 0.206 / 0.076 | 1.0e-02 / 0.132 / 0.165 |
| LR null(mom 1s) | 1.1e-04 / 0.260 / 0.003 | 3.1e-04 / 0.211 / 0.008 | 9.8e-04 / 0.150 / 0.018 | 3.0e-03 / 0.107 / 0.039 | 1.1e-02 / 0.070 / 0.092 |
| GBM full | 7.8e-05 / 0.503 / 0.005 | 2.5e-04 / 0.434 / 0.013 | 9.2e-04 / 0.331 / 0.037 | 2.8e-03 / 0.238 / 0.081 | 1.0e-02 / 0.146 / 0.177 |
| GBM null(mom 1s) | 1.2e-03 / 0.146 / 0.021 | 1.2e-03 / 0.146 / 0.021 | 1.4e-03 / 0.138 / 0.024 | 3.8e-03 / 0.115 / 0.053 | 1.1e-02 / 0.077 / 0.106 |
| GBM activity-only | 9.7e-05 / 0.469 / 0.006 | 2.9e-04 / 0.391 / 0.014 | 8.6e-04 / 0.294 / 0.030 | 2.6e-03 / 0.206 / 0.065 | 8.9e-03 / 0.131 / 0.142 |

**dn >= 10 bps in 1000 ms** (test positives 330, base rate 0.00005)

| model | rate 0.0001: real rate / prec / recall | rate 0.0003: real rate / prec / recall | rate 0.001: real rate / prec / recall | rate 0.003: real rate / prec / recall | rate 0.01: real rate / prec / recall |
|---|---|---|---|---|---|
| LR full | 8.4e-05 / 0.006 / 0.009 | 2.6e-04 / 0.002 / 0.009 | 8.5e-04 / 0.001 / 0.015 | 2.6e-03 / 0.001 / 0.033 | 8.8e-03 / 0.000 / 0.079 |
| LR null(mom 1s) | 1.5e-04 / 0.023 / 0.061 | 3.4e-04 / 0.010 / 0.064 | 1.0e-03 / 0.005 / 0.085 | 3.1e-03 / 0.002 / 0.127 | 1.1e-02 / 0.001 / 0.173 |
| GBM full | 6.8e-05 / 0.000 / 0.000 | 2.5e-04 / 0.004 / 0.018 | 9.0e-04 / 0.005 / 0.076 | 3.0e-03 / 0.003 / 0.145 | 1.1e-02 / 0.002 / 0.336 |
| GBM null(mom 1s) | 1.9e-03 / 0.000 / 0.006 | 1.9e-03 / 0.000 / 0.006 | 1.9e-03 / 0.000 / 0.006 | 3.8e-03 / 0.001 / 0.055 | 1.1e-02 / 0.001 / 0.194 |
| GBM activity-only | 8.5e-05 / 0.000 / 0.000 | 2.8e-04 / 0.003 / 0.015 | 9.4e-04 / 0.003 / 0.052 | 3.0e-03 / 0.004 / 0.230 | 1.1e-02 / 0.002 / 0.397 |

### Lead time: share of spot episodes already flagged L ms BEFORE the move started

Model = same direction, same X, H = 1000 ms. Cell = flagged share / chance share (realised flag rate) ; n = episodes. Episodes pooled over the 7 test days, both directions.

**Episodes >= 2 bps inside 1 s**

| model | lead L | n | rate 0.0001 | rate 0.0003 | rate 0.001 | rate 0.003 | rate 0.01 | direction AUC at L (up-score minus down-score) |
|---|---|---|---|---|---|---|---|---|
| GBM full | 0 ms | 14403 | 0.005 / 0.0001 | 0.012 / 0.0002 | 0.030 / 0.0008 | 0.065 / 0.0027 | 0.152 / 0.0097 | 0.777 |
| GBM full | 100 ms | 14403 | 0.004 / 0.0001 | 0.009 / 0.0002 | 0.024 / 0.0008 | 0.056 / 0.0027 | 0.135 / 0.0097 | 0.726 |
| GBM full | 250 ms | 14403 | 0.004 / 0.0001 | 0.009 / 0.0002 | 0.023 / 0.0008 | 0.057 / 0.0027 | 0.130 / 0.0097 | 0.703 |
| GBM full | 500 ms | 14403 | 0.003 / 0.0001 | 0.008 / 0.0002 | 0.024 / 0.0008 | 0.055 / 0.0027 | 0.130 / 0.0097 | 0.680 |
| GBM null(mom 1s) | 0 ms | 14403 | 0.008 / 0.0011 | 0.008 / 0.0011 | 0.015 / 0.0014 | 0.047 / 0.0035 | 0.086 / 0.0169 | 0.523 |
| GBM null(mom 1s) | 100 ms | 14403 | 0.009 / 0.0011 | 0.009 / 0.0011 | 0.014 / 0.0014 | 0.042 / 0.0035 | 0.083 / 0.0169 | 0.539 |
| GBM null(mom 1s) | 250 ms | 14403 | 0.012 / 0.0011 | 0.012 / 0.0011 | 0.016 / 0.0014 | 0.042 / 0.0035 | 0.084 / 0.0169 | 0.556 |
| GBM null(mom 1s) | 500 ms | 14403 | 0.015 / 0.0011 | 0.015 / 0.0011 | 0.019 / 0.0014 | 0.043 / 0.0035 | 0.087 / 0.0169 | 0.573 |
| GBM activity-only | 0 ms | 14403 | 0.008 / 0.0001 | 0.018 / 0.0002 | 0.033 / 0.0008 | 0.064 / 0.0024 | 0.137 / 0.0087 | 0.517 |
| GBM activity-only | 100 ms | 14403 | 0.005 / 0.0001 | 0.014 / 0.0002 | 0.028 / 0.0008 | 0.060 / 0.0024 | 0.131 / 0.0087 | 0.523 |
| GBM activity-only | 250 ms | 14403 | 0.004 / 0.0001 | 0.013 / 0.0002 | 0.027 / 0.0008 | 0.060 / 0.0024 | 0.131 / 0.0087 | 0.516 |
| GBM activity-only | 500 ms | 14403 | 0.005 / 0.0001 | 0.013 / 0.0002 | 0.029 / 0.0008 | 0.060 / 0.0024 | 0.134 / 0.0087 | 0.513 |
| LR full | 0 ms | 14403 | 0.009 / 0.0002 | 0.015 / 0.0004 | 0.030 / 0.0010 | 0.063 / 0.0030 | 0.142 / 0.0103 | 0.765 |
| LR full | 100 ms | 14403 | 0.009 / 0.0002 | 0.014 / 0.0004 | 0.025 / 0.0010 | 0.052 / 0.0030 | 0.118 / 0.0103 | 0.715 |
| LR full | 250 ms | 14403 | 0.009 / 0.0002 | 0.016 / 0.0004 | 0.026 / 0.0010 | 0.052 / 0.0030 | 0.115 / 0.0103 | 0.698 |
| LR full | 500 ms | 14403 | 0.010 / 0.0002 | 0.015 / 0.0004 | 0.026 / 0.0010 | 0.051 / 0.0030 | 0.113 / 0.0103 | 0.676 |

**Episodes >= 5 bps inside 1 s**

| model | lead L | n | rate 0.0001 | rate 0.0003 | rate 0.001 | rate 0.003 | rate 0.01 | direction AUC at L (up-score minus down-score) |
|---|---|---|---|---|---|---|---|---|
| GBM full | 0 ms | 1362 | 0.003 / 0.0000 | 0.037 / 0.0001 | 0.104 / 0.0007 | 0.206 / 0.0026 | 0.333 / 0.0102 | 0.585 |
| GBM full | 100 ms | 1362 | 0.004 / 0.0000 | 0.028 / 0.0001 | 0.106 / 0.0007 | 0.202 / 0.0026 | 0.314 / 0.0102 | 0.539 |
| GBM full | 250 ms | 1362 | 0.002 / 0.0000 | 0.023 / 0.0001 | 0.109 / 0.0007 | 0.202 / 0.0026 | 0.316 / 0.0102 | 0.549 |
| GBM full | 500 ms | 1362 | 0.001 / 0.0000 | 0.023 / 0.0001 | 0.095 / 0.0007 | 0.182 / 0.0026 | 0.301 / 0.0102 | 0.511 |
| GBM null(mom 1s) | 0 ms | 1362 | 0.065 / 0.0016 | 0.065 / 0.0016 | 0.065 / 0.0016 | 0.151 / 0.0032 | 0.233 / 0.0169 | 0.476 |
| GBM null(mom 1s) | 100 ms | 1362 | 0.054 / 0.0016 | 0.054 / 0.0016 | 0.054 / 0.0016 | 0.127 / 0.0032 | 0.208 / 0.0169 | 0.486 |
| GBM null(mom 1s) | 250 ms | 1362 | 0.054 / 0.0016 | 0.054 / 0.0016 | 0.054 / 0.0016 | 0.128 / 0.0032 | 0.199 / 0.0169 | 0.494 |
| GBM null(mom 1s) | 500 ms | 1362 | 0.054 / 0.0016 | 0.054 / 0.0016 | 0.054 / 0.0016 | 0.130 / 0.0032 | 0.192 / 0.0169 | 0.508 |
| GBM activity-only | 0 ms | 1362 | 0.018 / 0.0001 | 0.054 / 0.0002 | 0.121 / 0.0008 | 0.218 / 0.0027 | 0.322 / 0.0101 | 0.480 |
| GBM activity-only | 100 ms | 1362 | 0.015 / 0.0001 | 0.052 / 0.0002 | 0.117 / 0.0008 | 0.209 / 0.0027 | 0.323 / 0.0101 | 0.485 |
| GBM activity-only | 250 ms | 1362 | 0.016 / 0.0001 | 0.056 / 0.0002 | 0.127 / 0.0008 | 0.216 / 0.0027 | 0.325 / 0.0101 | 0.486 |
| GBM activity-only | 500 ms | 1362 | 0.010 / 0.0001 | 0.047 / 0.0002 | 0.117 / 0.0008 | 0.206 / 0.0027 | 0.322 / 0.0101 | 0.484 |
| LR full | 0 ms | 1362 | 0.028 / 0.0001 | 0.065 / 0.0003 | 0.116 / 0.0009 | 0.210 / 0.0027 | 0.346 / 0.0099 | 0.576 |
| LR full | 100 ms | 1362 | 0.021 / 0.0001 | 0.054 / 0.0003 | 0.106 / 0.0009 | 0.186 / 0.0027 | 0.314 / 0.0099 | 0.519 |
| LR full | 250 ms | 1362 | 0.023 / 0.0001 | 0.066 / 0.0003 | 0.106 / 0.0009 | 0.175 / 0.0027 | 0.311 / 0.0099 | 0.536 |
| LR full | 500 ms | 1362 | 0.028 / 0.0001 | 0.059 / 0.0003 | 0.103 / 0.0009 | 0.167 / 0.0027 | 0.306 / 0.0099 | 0.510 |

**Episodes >= 10 bps inside 1 s**

| model | lead L | n | rate 0.0001 | rate 0.0003 | rate 0.001 | rate 0.003 | rate 0.01 | direction AUC at L (up-score minus down-score) |
|---|---|---|---|---|---|---|---|---|
| GBM full | 0 ms | 171 | 0.000 / 0.0000 | 0.006 / 0.0002 | 0.058 / 0.0008 | 0.187 / 0.0028 | 0.310 / 0.0103 | 0.466 |
| GBM full | 100 ms | 171 | 0.000 / 0.0000 | 0.018 / 0.0002 | 0.053 / 0.0008 | 0.181 / 0.0028 | 0.368 / 0.0103 | 0.457 |
| GBM full | 250 ms | 171 | 0.000 / 0.0000 | 0.018 / 0.0002 | 0.064 / 0.0008 | 0.152 / 0.0028 | 0.374 / 0.0103 | 0.466 |
| GBM full | 500 ms | 171 | 0.000 / 0.0000 | 0.012 / 0.0002 | 0.035 / 0.0008 | 0.152 / 0.0028 | 0.333 / 0.0103 | 0.423 |
| GBM null(mom 1s) | 0 ms | 171 | 0.135 / 0.0018 | 0.135 / 0.0018 | 0.135 / 0.0018 | 0.146 / 0.0036 | 0.269 / 0.0110 | 0.414 |
| GBM null(mom 1s) | 100 ms | 171 | 0.135 / 0.0018 | 0.135 / 0.0018 | 0.135 / 0.0018 | 0.158 / 0.0036 | 0.263 / 0.0110 | 0.453 |
| GBM null(mom 1s) | 250 ms | 171 | 0.158 / 0.0018 | 0.158 / 0.0018 | 0.158 / 0.0018 | 0.175 / 0.0036 | 0.281 / 0.0110 | 0.432 |
| GBM null(mom 1s) | 500 ms | 171 | 0.140 / 0.0018 | 0.140 / 0.0018 | 0.140 / 0.0018 | 0.152 / 0.0036 | 0.269 / 0.0110 | 0.414 |
| GBM activity-only | 0 ms | 171 | 0.006 / 0.0001 | 0.006 / 0.0002 | 0.029 / 0.0009 | 0.228 / 0.0029 | 0.468 / 0.0102 | 0.425 |
| GBM activity-only | 100 ms | 171 | 0.006 / 0.0001 | 0.012 / 0.0002 | 0.029 / 0.0009 | 0.158 / 0.0029 | 0.444 / 0.0102 | 0.388 |
| GBM activity-only | 250 ms | 171 | 0.006 / 0.0001 | 0.006 / 0.0002 | 0.023 / 0.0009 | 0.187 / 0.0029 | 0.480 / 0.0102 | 0.400 |
| GBM activity-only | 500 ms | 171 | 0.000 / 0.0001 | 0.006 / 0.0002 | 0.018 / 0.0009 | 0.146 / 0.0029 | 0.456 / 0.0102 | 0.389 |
| LR full | 0 ms | 171 | 0.018 / 0.0001 | 0.018 / 0.0002 | 0.035 / 0.0008 | 0.041 / 0.0025 | 0.082 / 0.0088 | 0.624 |
| LR full | 100 ms | 171 | 0.018 / 0.0001 | 0.018 / 0.0002 | 0.018 / 0.0008 | 0.058 / 0.0025 | 0.117 / 0.0088 | 0.527 |
| LR full | 250 ms | 171 | 0.029 / 0.0001 | 0.029 / 0.0002 | 0.053 / 0.0008 | 0.064 / 0.0025 | 0.088 / 0.0088 | 0.537 |
| LR full | 500 ms | 171 | 0.023 / 0.0001 | 0.029 / 0.0002 | 0.058 / 0.0008 | 0.070 / 0.0025 | 0.076 / 0.0088 | 0.508 |

### Direction of what follows an alarm (5 bps, H = 1000 ms): right-way move / wrong-way move / no move

| model | rate 0.0001 | rate 0.0003 | rate 0.001 | rate 0.003 | rate 0.01 |
|---|---|---|---|---|---|
| GBM full | 0.215 / 0.097 / 0.688 (n=144) | 0.143 / 0.100 / 0.757 (n=1643) | 0.088 / 0.067 / 0.845 (n=8823) | 0.046 / 0.035 / 0.918 (n=31800) | 0.018 / 0.014 / 0.968 (n=123728) |
| GBM null(mom 1s) | 0.023 / 0.019 / 0.957 (n=18872) | 0.023 / 0.019 / 0.957 (n=18872) | 0.023 / 0.019 / 0.957 (n=18872) | 0.024 / 0.024 / 0.952 (n=38435) | 0.007 / 0.007 / 0.986 (n=204994) |
| GBM activity-only | 0.191 / 0.193 / 0.616 (n=628) | 0.154 / 0.148 / 0.698 (n=2727) | 0.084 / 0.082 / 0.833 (n=10021) | 0.042 / 0.042 / 0.915 (n=33157) | 0.017 / 0.018 / 0.965 (n=122448) |
| LR full | 0.210 / 0.155 / 0.635 (n=1384) | 0.149 / 0.111 / 0.741 (n=3480) | 0.085 / 0.062 / 0.853 (n=10674) | 0.044 / 0.033 / 0.924 (n=33082) | 0.019 / 0.015 / 0.966 (n=120347) |

### Per test day (rain or sun): AUC GBM full vs GBM null, and test positives

| test day | up 5bps/500ms | up 5bps/1000ms | dn 5bps/500ms | dn 5bps/1000ms |
|---|---|---|---|---|
| 2026-09-19 | 0.695 vs 0.596 (n=77) | 0.737 vs 0.631 (n=178) | 0.664 vs 0.501 (n=67) | 0.592 vs 0.614 (n=177) |
| 2026-09-20 | 0.773 vs 0.601 (n=89) | 0.761 vs 0.581 (n=200) | 0.746 vs 0.582 (n=126) | 0.756 vs 0.604 (n=319) |
| 2026-09-21 | 0.863 vs 0.756 (n=709) | 0.859 vs 0.778 (n=1720) | 0.853 vs 0.787 (n=427) | 0.861 vs 0.771 (n=1318) |
| 2026-09-22 | 0.635 vs 0.578 (n=138) | 0.646 vs 0.556 (n=386) | 0.668 vs 0.579 (n=274) | 0.664 vs 0.575 (n=653) |
| 2026-09-23 | 0.745 vs 0.658 (n=148) | 0.784 vs 0.642 (n=420) | 0.828 vs 0.681 (n=208) | 0.837 vs 0.697 (n=542) |
| 2026-09-24 | 0.784 vs 0.746 (n=102) | 0.771 vs 0.733 (n=382) | 0.784 vs 0.736 (n=124) | 0.783 vs 0.708 (n=352) |
| 2026-09-25 | 0.827 vs 0.730 (n=74) | 0.815 vs 0.716 (n=258) | 0.695 vs 0.541 (n=181) | 0.717 vs 0.600 (n=468) |

## 3. Direction given that a move is coming, by how much has already printed (|last-1 s spot move|)

**>= 2 bps within 1 s, exactly one direction** - direction AUC by |last-1 s spot move| at t (n = grid points; `*` < 60)

| model | |r1s| 0-1 bps | |r1s| 1-2 bps | |r1s| 2-5 bps | |r1s| 5-inf bps |
|---|---|---|---|---|
| GBM full | 0.814 (n=73454) | 0.812 (n=12520) | 0.754 (n=9193) | 0.637 (n=1754) |
| GBM null(mom 1s) | 0.630 (n=73454) | 0.687 (n=12520) | 0.626 (n=9193) | 0.592 (n=1754) |
| GBM activity-only | 0.519 (n=73454) | 0.514 (n=12520) | 0.479 (n=9193) | 0.506 (n=1754) |
| LR full | 0.812 (n=73454) | 0.809 (n=12520) | 0.749 (n=9193) | 0.633 (n=1754) |

per test day, |r1s| < 1 bp bucket (before the move prints): GBM full: 0.77 0.79 0.80 0.83 0.83 0.84 0.81; GBM null(mom 1s): 0.60 0.61 0.63 0.63 0.63 0.65 0.64
(n per day [3698, 5571, 22584, 12081, 10851, 9951, 8718])

**>= 5 bps within 1 s, exactly one direction** - direction AUC by |last-1 s spot move| at t (n = grid points; `*` < 60)

| model | |r1s| 0-1 bps | |r1s| 1-2 bps | |r1s| 2-5 bps | |r1s| 5-inf bps |
|---|---|---|---|---|
| GBM full | 0.662 (n=4758) | 0.707 (n=948) | 0.661 (n=1080) | 0.540 (n=535) |
| GBM null(mom 1s) | 0.560 (n=4758) | 0.577 (n=948) | 0.569 (n=1080) | 0.481 (n=535) |
| GBM activity-only | 0.508 (n=4758) | 0.512 (n=948) | 0.424 (n=1080) | 0.474 (n=535) |
| LR full | 0.684 (n=4758) | 0.706 (n=948) | 0.666 (n=1080) | 0.584 (n=535) |

per test day, |r1s| < 1 bp bucket (before the move prints): GBM full: 0.52 0.65 0.65 0.68 0.72 0.65 0.72; GBM null(mom 1s): 0.65 0.54 0.55 0.47 0.58 0.62 0.55
(n per day [294, 409, 1472, 875, 665, 492, 551])

**>= 10 bps within 1 s, exactly one direction** - direction AUC by |last-1 s spot move| at t (n = grid points; `*` < 60)

| model | |r1s| 0-1 bps | |r1s| 1-2 bps | |r1s| 2-5 bps | |r1s| 5-inf bps |
|---|---|---|---|---|
| GBM full | 0.535 (n=341) | 0.478 (n=78) | 0.511 (n=140) | 0.556 (n=126) |
| GBM null(mom 1s) | 0.276 (n=341) | 0.415 (n=78) | 0.401 (n=140) | 0.638 (n=126) |
| GBM activity-only | 0.427 (n=341) | 0.471 (n=78) | 0.345 (n=140) | 0.623 (n=126) |
| LR full | 0.621 (n=341) | 0.436 (n=78) | 0.519 (n=140) | 0.387 (n=126) |

per test day, |r1s| < 1 bp bucket (before the move prints): GBM full: nan nan 0.70 0.22 0.92 0.58 0.80; GBM null(mom 1s): nan nan 0.37 0.18 0.86 0.56 0.55
(n per day [9, 12, 130, 54, 46, 45, 45])


## 4. Does the call survive our own latency? (order lands at t+300 / t+500 ms)

**Score from the >= 2 bps / 1 s models.** AUC for the sign of the move AFTER we land (t+L, t+1s], and of the move we miss (t, t+L]; n = grid points

| model | L=300: after, |mv|>=1 | L=300: after, |mv|>=2 | L=300: after, |mv|>=5 | L=500: after, |mv|>=1 | L=500: after, |mv|>=2 | L=500: after, |mv|>=5 | L=300: missed, |mv|>=2 |
|---|---|---|---|---|---|---|---|
| GBM full | 0.791 (n=236206) | 0.733 (n=56556) | 0.647 (n=3418) | 0.763 (n=165534) | 0.703 (n=36002) | 0.632 (n=2097) | 0.831 (n=18057) |
| GBM null(mom 1s) | 0.638 (n=236206) | 0.601 (n=56556) | 0.558 (n=3418) | 0.620 (n=165534) | 0.586 (n=36002) | 0.559 (n=2097) | 0.662 (n=18057) |
| GBM activity-only | 0.519 (n=236206) | 0.510 (n=56556) | 0.502 (n=3418) | 0.518 (n=165534) | 0.509 (n=36002) | 0.490 (n=2097) | 0.510 (n=18057) |
| LR full | 0.786 (n=236206) | 0.730 (n=56556) | 0.641 (n=3418) | 0.759 (n=165534) | 0.700 (n=36002) | 0.631 (n=2097) | 0.825 (n=18057) |

per test day, L=300, after-move |mv|>=2: GBM full: 0.74 0.73 0.70 0.77 0.73 0.77 0.75; GBM null(mom 1s): 0.57 0.59 0.59 0.62 0.60 0.63 0.63

**Score from the >= 5 bps / 1 s models.** AUC for the sign of the move AFTER we land (t+L, t+1s], and of the move we miss (t, t+L]; n = grid points

| model | L=300: after, |mv|>=1 | L=300: after, |mv|>=2 | L=300: after, |mv|>=5 | L=500: after, |mv|>=1 | L=500: after, |mv|>=2 | L=500: after, |mv|>=5 | L=300: missed, |mv|>=2 |
|---|---|---|---|---|---|---|---|
| GBM full | 0.679 (n=236206) | 0.645 (n=56556) | 0.598 (n=3418) | 0.658 (n=165534) | 0.625 (n=36002) | 0.591 (n=2097) | 0.735 (n=18057) |
| GBM null(mom 1s) | 0.589 (n=236206) | 0.567 (n=56556) | 0.526 (n=3418) | 0.577 (n=165534) | 0.554 (n=36002) | 0.512 (n=2097) | 0.610 (n=18057) |
| GBM activity-only | 0.495 (n=236206) | 0.494 (n=56556) | 0.497 (n=3418) | 0.495 (n=165534) | 0.497 (n=36002) | 0.494 (n=2097) | 0.489 (n=18057) |
| LR full | 0.730 (n=236206) | 0.680 (n=56556) | 0.625 (n=3418) | 0.706 (n=165534) | 0.656 (n=36002) | 0.623 (n=2097) | 0.767 (n=18057) |

per test day, L=300, after-move |mv|>=2: GBM full: 0.58 0.62 0.61 0.69 0.67 0.69 0.67; GBM null(mom 1s): 0.55 0.58 0.55 0.59 0.57 0.57 0.59

**Alarms of the one-sided models (threshold = train flag rate), signed in the alarm direction.** cell = mean move caught (t+300, t+1s] bps / right-way >=2 bps / wrong-way >=2 bps / mean move missed (t, t+300] bps (n alarms)

*>= 2 bps / 1 s models*

| model | rate 0.0001 | rate 0.0003 | rate 0.001 | rate 0.003 | rate 0.01 |
|---|---|---|---|---|---|
| GBM full | +0.19 / 0.226 / 0.203 / +0.60 (n=823) | +0.17 / 0.198 / 0.176 / +0.47 (n=2609) | +0.18 / 0.160 / 0.132 / +0.38 (n=9767) | +0.16 / 0.119 / 0.095 / +0.30 (n=32169) | +0.15 / 0.075 / 0.056 / +0.21 (n=116807) |
| GBM null(mom 1s) | +0.08 / 0.075 / 0.068 / +0.17 (n=13522) | +0.08 / 0.075 / 0.068 / +0.17 (n=13522) | +0.05 / 0.072 / 0.067 / +0.10 (n=17018) | +0.03 / 0.061 / 0.058 / +0.04 (n=42572) | +0.03 / 0.027 / 0.024 / +0.03 (n=204390) |
| GBM activity-only | +0.21 / 0.236 / 0.203 / +0.08 (n=928) | +0.00 / 0.193 / 0.202 / -0.04 (n=2964) | -0.01 / 0.164 / 0.169 / -0.00 (n=9359) | -0.00 / 0.122 / 0.124 / -0.00 (n=29392) | +0.00 / 0.076 / 0.076 / +0.00 (n=105656) |
| LR full | +0.05 / 0.225 / 0.216 / +0.36 (n=1957) | +0.06 / 0.185 / 0.177 / +0.38 (n=4234) | +0.14 / 0.139 / 0.115 / +0.37 (n=12167) | +0.17 / 0.098 / 0.076 / +0.32 (n=36240) | +0.16 / 0.063 / 0.045 / +0.23 (n=125041) |

*>= 5 bps / 1 s models*

| model | rate 0.0001 | rate 0.0003 | rate 0.001 | rate 0.003 | rate 0.01 |
|---|---|---|---|---|---|
| GBM full | +0.40 / 0.250 / 0.174 / +0.62 (n=144) | +0.10 / 0.194 / 0.161 / +0.30 (n=1643) | +0.12 / 0.155 / 0.133 / +0.23 (n=8823) | +0.11 / 0.109 / 0.092 / +0.17 (n=31800) | +0.09 / 0.065 / 0.053 / +0.12 (n=123728) |
| GBM null(mom 1s) | +0.02 / 0.061 / 0.060 / +0.06 (n=18872) | +0.02 / 0.061 / 0.060 / +0.06 (n=18872) | +0.02 / 0.061 / 0.060 / +0.06 (n=18872) | -0.00 / 0.064 / 0.064 / -0.00 (n=38435) | +0.03 / 0.027 / 0.024 / +0.03 (n=204994) |
| GBM activity-only | +0.22 / 0.239 / 0.202 / -0.14 (n=628) | -0.01 / 0.213 / 0.206 / -0.01 (n=2727) | -0.02 / 0.153 / 0.156 / +0.00 (n=10021) | -0.01 / 0.107 / 0.107 / -0.01 (n=33157) | -0.01 / 0.062 / 0.062 / -0.01 (n=122448) |
| LR full | +0.28 / 0.236 / 0.204 / +0.25 (n=1384) | +0.17 / 0.191 / 0.171 / +0.26 (n=3480) | +0.12 / 0.135 / 0.122 / +0.24 (n=10674) | +0.11 / 0.097 / 0.083 / +0.21 (n=33082) | +0.10 / 0.063 / 0.052 / +0.15 (n=120347) |


## 5. Where the direction skill comes from (ablation, one split) and what the top alarms catch

Top-|score| share uses the test-day score distribution (label-free); everything else is walk-forward.

| feature group | n features | dirAUC after landing (+300 ms), |mv|>=2 | same, |mv|>=5 |
|---|---|---|---|
| all | 53 | 0.750 (n=22318) | 0.671 (n=1122) |
| spot tape only | 24 | 0.696 (n=22318) | 0.615 (n=1122) |
| perp tape + basis only | 29 | 0.745 (n=22318) | 0.649 (n=1122) |
| basis change only | 5 | 0.726 (n=22318) | 0.640 (n=1122) |
| spot returns only | 5 | 0.672 (n=22318) | 0.592 (n=1122) |

corr(score, spot r1000 at t) = +0.301;  corr(score, perp-minus-spot 1 s: p_r1000 - s_r1000) = +0.323

| top-|score| share (alarms/hour) | n | mean signed move caught after +300 ms (bps) | right-way >= 2 bps | wrong-way >= 2 bps | mean signed move missed in first 300 ms (bps) |
|---|---|---|---|---|---|
| 0.0001 (4/h) | 260 | +0.28 | 0.019 | 0.000 | +0.62 |
| 0.0003 (11/h) | 778 | +0.24 | 0.018 | 0.001 | +0.62 |
| 0.001 (36/h) | 2592 | +0.25 | 0.021 | 0.002 | +0.52 |
| 0.003 (108/h) | 7776 | +0.23 | 0.021 | 0.004 | +0.42 |
| 0.01 (360/h) | 25919 | +0.21 | 0.019 | 0.004 | +0.31 |
| 0.03 (1080/h) | 77756 | +0.19 | 0.017 | 0.003 | +0.22 |

## 6. Stage 2: effect on the settlement quantity (closing TWAP60 vs opening TWAP60)

per-second spot vol (median of 8 days): 0.533 bps; per-day [0.608, 0.308, 0.37, 0.8, 0.546, 0.535, 0.53, 0.479]

### Persistence of the move (share of X still there h s after the episode start; mean / median)

| X | n | 1 s | 5 s | 30 s | 60 s |
|---|---|---|---|---|---|
| 5 bps | 1753 | 1.12 / 1.09 | 1.19 / 1.20 | 1.30 / 1.25 | 1.31 / 1.25 |
| 10 bps | 189 | 0.95 / 1.01 | 1.04 / 1.06 | 0.72 / 0.81 | 0.50 / 0.66 |

### Shift in P(the side the 5 bps move favours wins), probability points, by second of candle and margin

m = that side's projected margin vs the opening line before the move (bps; negative = it is losing).

| tau (s) | w | sig (bps) | m=-20 | m=-10 | m=-5 | m=0 | m=5 | m=10 | m=20 |
|---|---|---|---|---|---|---|---|---|---|
| 60 | 1.00 | 7.53 | +3.3 | +23.1 | +32.8 | +30.8 | +19.1 | +7.8 | +0.4 |
| 120 | 1.00 | 6.30 | +1.6 | +23.6 | +38.3 | +35.1 | +18.0 | +5.2 | +0.1 |
| 180 | 1.00 | 4.76 | +0.2 | +21.7 | +48.1 | +41.5 | +13.9 | +1.8 | +0.0 |
| 240 | 1.00 | 2.38 | +0.0 | +7.4 | +72.5 | +49.7 | +1.8 | +0.0 | +0.0 |
| 255 | 0.75 | 1.55 | +0.0 | +0.0 | +46.9 | +49.9 | +0.1 | +0.0 | +0.0 |
| 270 | 0.50 | 0.84 | +0.0 | +0.0 | +1.9 | +50.0 | +0.0 | +0.0 | +0.0 |
| 285 | 0.25 | 0.30 | +0.0 | +0.0 | +0.0 | +50.0 | +0.0 | +0.0 | +0.0 |
| 295 | 0.08 | 0.06 | +0.0 | +0.0 | +0.0 | +50.0 | +0.0 | +0.0 | +0.0 |

### Shift in P(predicted side wins), probability points, for the move the alarms actually CATCH after +300 ms

| tau (s) | sig (bps) | D=0.1 m=-5 | D=0.1 m=0 | D=0.1 m=5 | D=0.2 m=-5 | D=0.2 m=0 | D=0.2 m=5 | D=0.4 m=-5 | D=0.4 m=0 | D=0.4 m=5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 60 | 7.53 | +0.4 | +0.5 | +0.4 | +0.9 | +1.1 | +0.8 | +1.7 | +2.1 | +1.7 |
| 120 | 6.30 | +0.5 | +0.6 | +0.5 | +0.9 | +1.3 | +0.9 | +1.9 | +2.5 | +1.8 |
| 180 | 4.76 | +0.5 | +0.8 | +0.5 | +1.0 | +1.7 | +0.9 | +2.0 | +3.3 | +1.8 |
| 240 | 2.38 | +0.2 | +1.7 | +0.2 | +0.4 | +3.3 | +0.3 | +0.9 | +6.7 | +0.6 |
| 255 | 1.55 | +0.0 | +1.9 | +0.0 | +0.0 | +3.9 | +0.0 | +0.1 | +7.7 | +0.0 |
| 270 | 0.84 | +0.0 | +2.4 | +0.0 | +0.0 | +4.7 | +0.0 | +0.0 | +9.4 | +0.0 |
| 285 | 0.30 | +0.0 | +3.3 | +0.0 | +0.0 | +6.7 | +0.0 | +0.0 | +13.2 | +0.0 |
| 295 | 0.06 | +0.0 | +5.8 | +0.0 | +0.0 | +11.4 | +0.0 | +0.0 | +22.0 | +0.0 |

m = 0 cells late in the candle are knife-edge (sigma -> 0); they apply only to a price sitting exactly on the line.
Random-walk sigma from the measured 1 s vol is a lower bound (fat tails widen it, shrinking these shifts).

## 7. verify.py

```
==============================================================================
FINDING: order flow calls the sign of the >= 2 bps spot move left after +300 ms (models >= 2 bps / 1 s)
==============================================================================
  [FAIL] grading provenance  only one outcome source given - name the source the VENUE SETTLES ON and confirm it is not a different venue's oracle
  [PASS] sample size         all 7 cells >= 60
  [PASS] both halves         h1 +0.141 / h2 +0.136
  [PASS] beats the null      mine +0.741 vs momentum-1s GBM (AUC) +0.603
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: grading provenance

per-day AUC gain over momentum: [0.169, 0.139, 0.114, 0.147, 0.137, 0.135, 0.125] 

==============================================================================
FINDING: order flow calls the sign of the >= 5 bps spot move left after +300 ms (models >= 5 bps / 1 s)
==============================================================================
  [FAIL] grading provenance  only one outcome source given - name the source the VENUE SETTLES ON and confirm it is not a different venue's oracle
  [PASS] sample size         all 7 cells >= 60
  [FAIL] both halves         h1 -0.010 / h2 +0.129  <- SIGN FLIPS, not a finding
  [PASS] beats the null      mine +0.615 vs momentum-1s GBM (AUC) +0.546
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: grading provenance, both halves

per-day AUC gain over momentum: [-0.061, 0.018, 0.012, 0.26, 0.092, 0.022, 0.14] 

```

Token budget: not tracked in this sub-session.
