# MAIN / REVERSAL new EV logic - window 1 (09-07..09-16 replay), V 09-27
Script `analysis/v/model/lane_ev_replay.py` (real LaneEngine, full call stream, one trade per candle, fee 0.07p(1-p),
venues.outcome, flip priced at the opposite ask). Paper fills at the quoted ask: an UPPER bound. Zurich runs window 2 (09-23+).

## Verdict
- **Calibrated EV (R2) does not help either lane**; the venue-only null (R3) is as good or better. Nothing new ships.
- **MAIN R1 (its own lane-p breakeven) +0.186/$1 is NOT usable**: the money is after 240 s, which London's order engine
  refuses. Inside 0-240 s: n108, +0.032, w/o top 3 -0.024, H1 negative. MAIN stays dead.
- **REVERSAL as it is (R0/R1) is strong on paper inside 0-240 s**: R1 n182, 73.6% hit, +0.388/$1, H1 +0.207 H2 +0.569,
  w/o top 3 +0.252. Zurich's live SHADOW REV reads only +0.064 on 77, so the open question is execution, not the signal.

## 0-240 s (London-tradeable)
MAIN R0 n867 77.0% -0.017 (H1 -0.003 H2 -0.031) w/o top3 -0.022 | MAIN R1 n108 59.3% +0.032 (-0.027 | +0.090) w/o top3 -0.024
REV  R0 n213 72.3% +0.303 (+0.132 | +0.472) w/o top3 +0.186 | REV  R1 n182 73.6% +0.388 (+0.207 | +0.569) w/o top3 +0.252

## Full grid, whole window (0-300 s)
```

MAIN: 60591 calls on 1195 candles, 9 days
  R0 first call, ask<=0.90           n  893  hit 77.6% ask 0.78 per$1 +0.001  H1 +0.016 H2 -0.015  neg days 4/9  +2c -0.024  perm p 0.04
  R1 lane p breakeven (live)         n  134  hit 65.7% ask 0.57 per$1 +0.186  H1 +0.127 H2 +0.245  neg days 3/9  +2c +0.143  perm p 0.01
  R2 calibrated lane+venue ev>=0.00  n  286  hit 79.4% ask 0.84 per$1 -0.042  H1 -0.028 H2 -0.057  neg days 4/6  +2c -0.064  perm p 0.57
  R2 calibrated lane+venue ev>=0.03  n   71  hit 76.1% ask 0.81 per$1 -0.001  H1 +0.094 H2 -0.094  neg days 2/5  +2c -0.027  perm p 0.37
  R2 calibrated lane+venue ev>=0.05  n   20* hit 70.0% ask 0.66 per$1 +0.110  H1 +0.167 H2 +0.054  neg days 3/4  +2c +0.075  perm p 0.34
  R2 calibrated lane+venue ev>=0.10  n    8* hit 87.5% ask 0.56 per$1 +0.545  H1 +0.664 H2 +0.426  neg days 1/2  +2c +0.492  perm p 0.05
  R2 calibrated lane+venue ev>=0.15  n    1* hit 100.0% ask 0.42 per$1 +1.288  H1 +nan H2 +1.288  neg days 0/1  +2c +1.187  perm p 0.51
  R3 venue-only (null) ev>=0.00      n  260  hit 81.2% ask 0.85 per$1 -0.032  H1 -0.022 H2 -0.042  neg days 5/6  +2c -0.054  perm p 0.68
  R3 venue-only (null) ev>=0.03      n   22* hit 72.7% ask 0.65 per$1 +0.141  H1 -0.281 H2 +0.563  neg days 1/2  +2c +0.106  perm p 0.25
  R3 venue-only (null) ev>=0.05      n   14* hit 71.4% ask 0.56 per$1 +0.219  H1 -0.307 H2 +0.744  neg days 1/2  +2c +0.178  perm p 0.18
  R3 venue-only (null) ev>=0.10      n    6* hit 100.0% ask 0.56 per$1 +0.817  H1 +0.733 H2 +0.901  neg days 0/1  +2c +0.753  perm p 0.04
  R3 venue-only (null) ev>=0.15      none
  R0 on the same walk-forward days   n  599  hit 78.1% ask 0.79 per$1 +0.002  H1 +0.038 H2 -0.034  neg days 2/6  +2c -0.023  perm p 0.08

REVERSAL: 20194 calls on 271 candles, 9 days
  R0 first call, ask<=0.90           n  259  hit 69.1% ask 0.62 per$1 +0.362  H1 +0.170 H2 +0.552  neg days 2/9  +2c +0.273  perm p 0.00
  R1 lane p breakeven (live)         n  219  hit 68.5% ask 0.59 per$1 +0.444  H1 +0.242 H2 +0.645  neg days 2/9  +2c +0.342  perm p 0.00
  R2 calibrated lane+venue ev>=0.00  n  140  hit 69.3% ask 0.65 per$1 +0.181  H1 +0.119 H2 +0.243  neg days 2/6  +2c +0.128  perm p 0.02
  R2 calibrated lane+venue ev>=0.03  n  105  hit 63.8% ask 0.61 per$1 +0.212  H1 +0.058 H2 +0.362  neg days 2/6  +2c +0.150  perm p 0.05
  R2 calibrated lane+venue ev>=0.05  n   86  hit 66.3% ask 0.59 per$1 +0.299  H1 +0.133 H2 +0.465  neg days 2/6  +2c +0.229  perm p 0.00
  R2 calibrated lane+venue ev>=0.10  n   39* hit 51.3% ask 0.48 per$1 +0.207  H1 -0.025 H2 +0.427  neg days 3/6  +2c +0.135  perm p 0.25
  R2 calibrated lane+venue ev>=0.15  n   17* hit 47.1% ask 0.37 per$1 +0.029  H1 +0.490 H2 -0.381  neg days 1/6  +2c -0.018  perm p 0.25
  R3 venue-only (null) ev>=0.00      n  140  hit 69.3% ask 0.65 per$1 +0.126  H1 +0.123 H2 +0.129  neg days 2/6  +2c +0.084  perm p 0.02
  R3 venue-only (null) ev>=0.03      n  102  hit 63.7% ask 0.61 per$1 +0.090  H1 +0.109 H2 +0.071  neg days 2/6  +2c +0.052  perm p 0.18
  R3 venue-only (null) ev>=0.05      n   82  hit 67.1% ask 0.61 per$1 +0.122  H1 +0.085 H2 +0.159  neg days 2/6  +2c +0.083  perm p 0.04
  R3 venue-only (null) ev>=0.10      n   26* hit 65.4% ask 0.56 per$1 +0.303  H1 -0.110 H2 +0.716  neg days 1/6  +2c +0.248  perm p 0.14
  R3 venue-only (null) ev>=0.15      n    9* hit 66.7% ask 0.48 per$1 +0.399  H1 -0.020 H2 +0.734  neg days 1/4  +2c +0.338  perm p 0.16
  R0 on the same walk-forward days   n  170  hit 68.2% ask 0.62 per$1 +0.473  H1 +0.619 H2 +0.328  neg days 1/6  +2c +0.360  perm p 0.00
```
