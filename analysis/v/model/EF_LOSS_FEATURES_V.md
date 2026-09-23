# Does any BTC/market feature predict EF losses? - V, 09-23 02:5x UTC

Owner: "there should be something ... volume, rsi, oi, buy sell or any other parameters". Script: analysis/v/model/ef_loss_features.py. 1077 graded v10 EF paper fires 09-08..16 (venues.outcome), 33 features: the 25 v10 fire-time features + BTC 1 s klines at the fire second (RSI14 1-min, 60 s volume vs 30-min median, taker-buy share 60 s/300 s, returns 5/15/60 min, 1-min ATR). All signed so + = with our side. OI/funding: not reachable from these containers, not tested.

## Read
- **(1) 33 features vs the residual (win - p_cal)**: only two survive Benjamini-Hochberg: p_venue (market price of our side, rho -0.33, q 0.04) and pos_in_range (q 0.04). RSI, volume, taker buy/sell, 5/15/60-min trend, ATR, order flow, book imbalance: **all q > 0.4 - nothing**.
- **(2) a trained brain (gradient boosting) on p_cal + BTC features, or + all features, walk-forward: WORSE** than the live method (+$345/+$361 vs +$474, per$1 +0.12 vs +0.24, more fires at lower accuracy).
- **(3) logit(p) + logit(p_venue), walk-forward**: +$519 vs +$474, same maxDD 53.6. Paired: 399 shared fires, the ENTIRE difference is 15 extra fires (9 wins, +$45.5) - under 60, **insufficient**. Candidate, not a finding.

## Output
```
1077 graded fires with klines, 9 days, 33 features (signed so + = with our side)

(1) Spearman(feature, win - p_cal), whole list, permutation p, BH-adjusted q:
  pos_in_range   rho -0.109  p 0.002  q 0.041
  p_venue        rho -0.327  p 0.002  q 0.041
  move_bps       rho -0.083  p 0.007  q 0.082
  basis_bps      rho +0.084  p 0.015  q 0.123
  dist_hi_bps    rho +0.058  p 0.065  q 0.428
  ret60          rho -0.050  p 0.095  q 0.521
  k_ret5m        rho -0.033  p 0.234  q 0.925
  ofi5           rho +0.036  p 0.272  q 0.925
  k_buy300       rho -0.031  p 0.319  q 0.925
  k_atr1m        rho -0.030  p 0.327  q 0.925
  sec_left       rho -0.024  p 0.357  q 0.925
  ret5           rho +0.026  p 0.404  q 0.925
  k_vol_ratio    rho +0.026  p 0.409  q 0.925
  dist_lo_bps    rho -0.024  p 0.426  q 0.925
  imb20          rho +0.022  p 0.491  q 0.925
  ofi15          rho +0.021  p 0.529  q 0.925
  imb5           rho +0.019  p 0.534  q 0.925
  micro_bps      rho +0.017  p 0.561  q 0.925
  ofi60          rho -0.018  p 0.589  q 0.925
  ret15          rho +0.016  p 0.608  q 0.925
  ret30          rho -0.011  p 0.681  q 0.925
  k_ret60m       rho +0.010  p 0.743  q 0.925
  prev1_bps      rho -0.010  p 0.746  q 0.925
  prev2_bps      rho +0.010  p 0.766  q 0.925
  spread_bps     rho -0.008  p 0.778  q 0.925
  spot_imb15     rho +0.008  p 0.783  q 0.925
  k_rsi14        rho +0.007  p 0.793  q 0.925
  rv60           rho +0.007  p 0.813  q 0.925
  k_ret15m       rho +0.007  p 0.813  q 0.925
  perp_n15       rho +0.006  p 0.848  q 0.926
  range_bps      rho -0.006  p 0.870  q 0.926
  spot_imb60     rho -0.002  p 0.945  q 0.975
  k_buy60        rho -0.001  p 0.990  q 0.990

(2) walk-forward by day, rule ev >= 0.15, ask <= 0.60, $5:
  A pooled Platt (live method)       n/day  49.9 right  55.1% per$1 +0.238 total  +474.0 maxDD  53.6 run  7 negdays 1/8
  brain: p_cal + BTC kline features  n/day  71.8 right  50.3% per$1 +0.120 total  +345.3 maxDD  58.4 run  7 negdays 1/8
  brain: p_cal + all features        n/day  72.6 right  50.4% per$1 +0.124 total  +360.7 maxDD  69.6 run  7 negdays 2/8

(3) logistic on logit(p) + the BH survivors, walk-forward, same rule:
  logit(p) + logit(p_venue)          n/day  51.8 right  55.3% per$1 +0.251 total  +519.4 maxDD  53.6 run  8 negdays 1/8
  logit(p) + pos_in_range            n/day  50.0 right  55.0% per$1 +0.237 total  +474.9 maxDD  53.6 run  7 negdays 1/8
  logit(p) + p_venue + pos_in_range  n/day  51.6 right  54.7% per$1 +0.240 total  +496.0 maxDD  53.6 run  7 negdays 1/8

paired (live vs logit(p)+logit(p_venue)): shared 399 | only live 0 | only p_venue arm 15 fires, 9 wins, +$45.5
```
