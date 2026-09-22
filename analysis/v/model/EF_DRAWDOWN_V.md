# EF drawdown: pause grid, clustering, buckets - V, 2026-09-22 23:0x UTC

Owner (22:5x): "profitable ef that has no drawdowns by tomorrow ... you can stop trading in drawdown period or when market is wrong for us ... but don's waste profit".
Script: analysis/v/model/ef_pause_grid.py. Data: poly_pnl.sqlite3 v10 EF paper fires 09-08 -> 09-16 (1077 graded on venues.outcome), fee 1.67%, $3 stake.
Grid and buckets defined in the script BEFORE any result; whole grid below, never a best cell. Calibrated = pooled Platt a=1.0677 b=-0.3208 (H1 EF_BRAIN.md D) with the fixed rule p' >= ask+0.06+fee, ask<=0.60.

## Read
1. Losses do NOT cluster: lag-1..5 autocorrelation of win is 0 (perm p 0.17-0.97), runs test z=-0.60 raw / +0.13 calibrated. So a pause rule removes fires at random.
2. The pause grid confirms it: every cell's total sits at or below its random-removal null, and no cell beats the null's p5 drawdown. "After L losses pause M min" and "pause while last-10 pnl < -X" do not reduce drawdown beyond what deleting the same number of fires at random does.
3. The only arm that cuts drawdown by more than random removal is the CALIBRATION: maxDD 53.0 -> 27.2, per$1 +0.154 -> +0.298, W 52.7% -> 56.0%, total +497 -> +335 (n 1077 -> 375), negative days 1/9 -> 1/9. Nothing has zero drawdown; a 56% bet at 0.43 cannot.
4. Buckets: no market-wrong regime. Raw and calibrated are positive in every rv60 tercile, hour block and ask bucket >= 0.30. The sec 120-180 cell (calibrated +0.645, DD 9.3, 0/9 negative days) sits in a NON-monotone sec sweep (0.22 / 0.27 / 0.65 / 0.15), so it is not a finding.

## Output (verbatim)
```
fires 1077 graded on venues.outcome, 09-08 -> 09-16, days 9

## base arms
raw v10 EF (all fires)                 n=1077 W= 52.7% per$1=+0.154 total=+497.09 maxDD= 53.01 run= 8 negdays=1/9 | +0.31 +0.10 +0.15 +0.02 +0.15 +0.16 +0.32 +0.33 -0.14
calibrated p (pooled a,b), same rule   n= 375 W= 56.0% per$1=+0.298 total=+335.03 maxDD= 27.18 run= 6 negdays=1/9 | +0.19 +0.28 +0.33 +0.20 +0.46 +0.43 +0.46 +0.21 -0.10

## clustering: do losses cluster? (lag autocorrelation of win, permutation p; runs test)
  raw         lag1: acf=+0.017 perm p=0.56
  raw         lag2: acf=-0.019 perm p=0.51
  raw         lag3: acf=+0.001 perm p=0.97
  raw         lag5: acf=-0.042 perm p=0.17
  raw         runs=528 expected=537.9 z=-0.60  (z<0 = losses/wins cluster)
  calibrated  lag1: acf=-0.010 perm p=0.81
  calibrated  lag2: acf=-0.105 perm p=0.06
  calibrated  lag3: acf=-0.021 perm p=0.69
  calibrated  lag5: acf=-0.005 perm p=0.94
  calibrated  runs=187 expected=185.8 z=+0.13  (z<0 = losses/wins cluster)

## pause grid on RAW (null = random removal of the same number of fires: mean total, mean maxDD, p5 maxDD)
  after 2 losses pause  15 min         n= 791 W= 53.1% per$1=+0.176 total=+418.17 maxDD= 64.69 run= 6 negdays=1/9 | +0.17 +0.16 +0.26 +0.02 +0.07 +0.22 +0.39 +0.30 -0.27
                                       null: total=+361.71 maxDD= 48.45 p5= 33.56
  after 2 losses pause  30 min         n= 576 W= 50.7% per$1=+0.126 total=+217.26 maxDD= 53.72 run= 8 negdays=3/9 | -0.05 +0.16 +0.09 -0.11 +0.07 +0.27 +0.34 +0.34 -0.57
                                       null: total=+267.84 maxDD= 44.13 p5= 29.42
  after 2 losses pause  60 min         n= 455 W= 53.4% per$1=+0.180 total=+245.43 maxDD= 32.21 run= 5 negdays=3/9 | +0.05 +0.17 +0.31 -0.03 +0.19 -0.01 +0.31 +0.39 -0.27
                                       null: total=+209.51 maxDD= 39.91 p5= 25.51
  after 2 losses pause 120 min         n= 255 W= 50.2% per$1=+0.127 total= +96.93 maxDD= 43.50 run= 8 negdays=2/9 | +0.34 +0.14 +0.19 +0.02 -0.46 +0.07 +0.41 +0.10 -0.44
                                       null: total=+124.12 maxDD= 32.24 p5= 20.04
  after 3 losses pause  15 min         n= 913 W= 51.6% per$1=+0.133 total=+363.27 maxDD= 61.14 run= 6 negdays=2/9 | +0.31 +0.09 +0.12 -0.06 +0.12 +0.14 +0.32 +0.33 -0.27
                                       null: total=+422.19 maxDD= 49.48 p5= 36.00
  after 3 losses pause  30 min         n= 767 W= 51.6% per$1=+0.135 total=+310.72 maxDD= 69.20 run= 7 negdays=3/9 | +0.31 +0.13 +0.08 -0.05 -0.04 +0.19 +0.34 +0.38 -0.44
                                       null: total=+351.98 maxDD= 47.55 p5= 32.66
  after 3 losses pause  60 min         n= 658 W= 52.1% per$1=+0.140 total=+276.41 maxDD= 51.07 run= 6 negdays=3/9 | +0.31 +0.14 +0.12 -0.02 -0.02 +0.10 +0.31 +0.36 -0.39
                                       null: total=+301.87 maxDD= 44.31 p5= 30.31
  after 3 losses pause 120 min         n= 477 W= 51.8% per$1=+0.147 total=+210.57 maxDD= 56.43 run= 9 negdays=2/9 | +0.31 +0.09 +0.22 +0.02 -0.10 +0.04 +0.18 +0.35 -0.16
                                       null: total=+223.52 maxDD= 40.77 p5= 26.08
  after 4 losses pause  15 min         n=1012 W= 52.4% per$1=+0.147 total=+445.42 maxDD= 58.04 run= 7 negdays=2/9 | +0.31 +0.12 +0.14 -0.02 +0.12 +0.18 +0.34 +0.33 -0.24
                                       null: total=+467.71 maxDD= 50.85 p5= 41.60
  after 4 losses pause  30 min         n= 902 W= 51.2% per$1=+0.125 total=+337.37 maxDD= 68.05 run= 9 negdays=3/9 | +0.31 +0.07 -0.04 -0.05 +0.12 +0.15 +0.36 +0.33 -0.17
                                       null: total=+418.13 maxDD= 49.09 p5= 37.26
  after 4 losses pause  60 min         n= 841 W= 52.7% per$1=+0.154 total=+389.49 maxDD= 55.50 run= 7 negdays=1/9 | +0.31 +0.06 +0.01 +0.02 +0.14 +0.23 +0.37 +0.33 -0.38
                                       null: total=+388.35 maxDD= 48.23 p5= 35.48
  after 4 losses pause 120 min         n= 629 W= 51.8% per$1=+0.136 total=+257.11 maxDD= 39.39 run= 8 negdays=2/9 | +0.31 +0.10 +0.00 -0.01 +0.14 +0.04 +0.34 +0.19 -0.19
                                       null: total=+296.09 maxDD= 45.09 p5= 30.78
  pause while last-10 pnl < -2 stakes  n=  57 W= 57.9% per$1=+0.219 total= +37.47 maxDD= 10.18 run= 3 negdays=1/2 | +0.31 -0.16
                                       null: total= +28.96 maxDD= 19.92 p5=  9.00
  pause while last-10 pnl < -3 stakes  n=  57 W= 57.9% per$1=+0.219 total= +37.47 maxDD= 10.18 run= 3 negdays=1/2 | +0.31 -0.16
                                       null: total= +25.00 maxDD= 20.14 p5=  9.06
  pause while last-10 pnl < -4 stakes  n= 149 W= 55.0% per$1=+0.187 total= +83.69 maxDD= 15.91 run= 4 negdays=0/2 | +0.31 +0.13
                                       null: total= +68.36 maxDD= 28.64 p5= 15.22

## pause grid on CALIBRATED (null = random removal of the same number of fires: mean total, mean maxDD, p5 maxDD)
  after 2 losses pause  15 min         n= 332 W= 55.4% per$1=+0.300 total=+299.10 maxDD= 24.22 run= 6 negdays=2/9 | -0.00 +0.22 +0.36 +0.24 +0.38 +0.49 +0.54 +0.11 -0.05
                                       null: total=+294.05 maxDD= 25.25 p5= 21.18
  after 2 losses pause  30 min         n= 285 W= 53.0% per$1=+0.253 total=+216.17 maxDD= 18.12 run= 5 negdays=2/9 | -0.11 +0.12 +0.29 +0.17 +0.45 +0.48 +0.43 +0.26 -0.21
                                       null: total=+254.27 maxDD= 24.08 p5= 18.18
  after 2 losses pause  60 min         n= 240 W= 51.7% per$1=+0.226 total=+162.42 maxDD= 21.55 run= 6 negdays=2/9 | -0.13 +0.19 +0.23 +0.17 +0.51 +0.41 +0.31 +0.14 -0.07
                                       null: total=+216.20 maxDD= 22.44 p5= 15.18
  after 2 losses pause 120 min         n= 156 W= 46.8% per$1=+0.073 total= +34.10 maxDD= 46.66 run= 9 negdays=3/9 | -0.29 +0.11 +0.18 +0.06 +0.17 +0.49 +0.20 -0.76 -1.00
                                       null: total=+140.60 maxDD= 19.89 p5= 12.64
  after 3 losses pause  15 min         n= 358 W= 55.9% per$1=+0.302 total=+324.02 maxDD= 24.18 run= 7 negdays=1/9 | +0.19 +0.28 +0.33 +0.24 +0.46 +0.41 +0.45 +0.21 -0.10
                                       null: total=+321.67 maxDD= 25.75 p5= 21.18
  after 3 losses pause  30 min         n= 350 W= 56.0% per$1=+0.300 total=+315.05 maxDD= 21.18 run= 6 negdays=1/9 | +0.19 +0.28 +0.30 +0.25 +0.46 +0.41 +0.47 +0.25 -0.26
                                       null: total=+313.53 maxDD= 25.25 p5= 21.18
  after 3 losses pause  60 min         n= 323 W= 55.4% per$1=+0.291 total=+282.05 maxDD= 25.03 run= 7 negdays=1/9 | +0.19 +0.28 +0.26 +0.30 +0.46 +0.43 +0.44 +0.19 -0.40
                                       null: total=+290.06 maxDD= 24.91 p5= 20.85
  after 3 losses pause 120 min         n= 287 W= 55.1% per$1=+0.284 total=+244.69 maxDD= 48.32 run= 8 negdays=2/9 | +0.19 +0.28 +0.33 +0.32 +0.46 +0.41 +0.48 -0.32 -1.00
                                       null: total=+255.30 maxDD= 24.09 p5= 18.18
  after 4 losses pause  15 min         n= 374 W= 56.1% per$1=+0.301 total=+338.03 maxDD= 24.18 run= 5 negdays=1/9 | +0.19 +0.28 +0.33 +0.20 +0.46 +0.43 +0.48 +0.21 -0.10
                                       null: total=+333.89 maxDD= 27.12 p5= 27.18
  after 4 losses pause  30 min         n= 370 W= 55.9% per$1=+0.295 total=+326.91 maxDD= 21.18 run= 5 negdays=1/9 | +0.19 +0.28 +0.33 +0.18 +0.46 +0.43 +0.51 +0.21 -0.26
                                       null: total=+331.04 maxDD= 26.95 p5= 24.18
  after 4 losses pause  60 min         n= 357 W= 55.7% per$1=+0.294 total=+314.91 maxDD= 22.20 run= 5 negdays=1/9 | +0.19 +0.28 +0.32 +0.16 +0.46 +0.43 +0.51 +0.14 -0.07
                                       null: total=+320.01 maxDD= 25.90 p5= 21.18
  after 4 losses pause 120 min         n= 334 W= 55.7% per$1=+0.294 total=+294.75 maxDD= 21.50 run= 6 negdays=1/9 | +0.19 +0.28 +0.28 +0.15 +0.46 +0.43 +0.55 +0.14 -0.20
                                       null: total=+300.77 maxDD= 25.14 p5= 20.69
  pause while last-10 pnl < -2 stakes  n=  61 W= 57.4% per$1=+0.264 total= +48.31 maxDD=  9.71 run= 2 negdays=0/2 | +0.19 +0.30
                                       null: total= +53.91 maxDD= 15.90 p5=  9.00
  pause while last-10 pnl < -3 stakes  n=  74 W= 55.4% per$1=+0.215 total= +47.72 maxDD= 12.35 run= 3 negdays=1/3 | +0.19 +0.28 -0.16
                                       null: total= +65.35 maxDD= 16.56 p5=  9.54
  pause while last-10 pnl < -4 stakes  n=  74 W= 55.4% per$1=+0.215 total= +47.72 maxDD= 12.35 run= 3 negdays=1/3 | +0.19 +0.28 -0.16
                                       null: total= +66.10 maxDD= 16.23 p5=  9.00

## market-wrong buckets (defined first; * = n<60)
-- RAW
  rv60 low<0.14                        n= 358 W= 53.4% per$1=+0.084 total= +90.63 maxDD= 40.44 run=10 negdays=3/9 | +0.36 -0.12 -0.10 +0.05 +0.02 +0.18 +0.14 +0.69 -0.17
  rv60 mid                             n= 360 W= 53.3% per$1=+0.180 total=+194.23 maxDD= 32.71 run= 8 negdays=1/9 | +0.03 +0.09 +0.13 +0.09 +0.46 +0.10 +0.37 +0.41 -0.01
  rv60 high>=0.41                      n= 359 W= 51.5% per$1=+0.197 total=+212.24 maxDD= 35.30 run= 7 negdays=2/9 | +0.69 +0.29 +0.28 -0.04 +0.48 +0.17 +0.38 +0.15 -0.23
  hour 00-06                           n= 250 W= 51.2% per$1=+0.123 total= +91.96 maxDD= 34.69 run= 8 negdays=2/8 | +0.01 -0.15 +0.20 +0.06 +0.18 +0.56 +0.64 -0.32
  hour 06-12                           n= 255 W= 53.3% per$1=+0.178 total=+136.01 maxDD= 28.00 run= 6 negdays=1/8 | +0.27 +0.02 +0.10 +0.40 +0.02 +0.15 +0.52 -0.04
  hour 12-18                           n= 276 W= 54.7% per$1=+0.184 total=+152.35 maxDD= 30.19 run= 4 negdays=2/9 | -1.00 +0.31 +0.28 -0.04 +0.21 +0.34 +0.30 +0.01 +0.57
  hour 18-24                           n= 296 W= 51.7% per$1=+0.132 total=+116.78 maxDD= 38.93 run= 8 negdays=3/8 | +0.37 -0.10 +0.32 -0.14 -0.01 +0.07 +0.37 +0.06
  ask <0.30*                           n=  19 W= 47.4% per$1=+0.828 total= +47.22 maxDD= 15.00 run= 5 negdays=2/7 | -1.00 -1.00 +0.46 +0.82 +1.26 +2.41 +2.39
  ask 0.30-0.40                        n= 250 W= 46.0% per$1=+0.240 total=+179.71 maxDD= 42.90 run=10 negdays=2/9 | +0.24 +0.25 +0.19 -0.14 +0.45 +0.57 +0.45 +0.43 -0.17
  ask 0.40-0.50                        n= 482 W= 50.8% per$1=+0.122 total=+175.76 maxDD= 41.05 run= 8 negdays=3/9 | +0.40 -0.01 +0.14 -0.01 +0.16 +0.19 +0.18 +0.41 -0.34
  ask 0.50-0.60                        n= 303 W= 60.1% per$1=+0.095 total= +86.12 maxDD= 45.57 run= 5 negdays=2/9 | +0.38 +0.20 +0.09 +0.16 -0.08 -0.09 +0.23 +0.03 +0.19
  sec 0-60                             n= 495 W= 53.7% per$1=+0.133 total=+197.58 maxDD= 57.35 run= 8 negdays=2/9 | +0.53 +0.13 +0.04 -0.16 +0.17 +0.21 +0.21 +0.51 -0.06
  sec 60-120                           n= 295 W= 51.9% per$1=+0.161 total=+142.63 maxDD= 41.01 run= 7 negdays=4/9 | -0.24 +0.12 -0.02 +0.37 +0.06 -0.03 +0.47 +0.25 -0.05
  sec 120-180                          n= 170 W= 54.1% per$1=+0.255 total=+130.06 maxDD= 22.58 run= 6 negdays=2/9 | +0.44 +0.10 +0.83 -0.04 +0.07 +0.40 +0.38 +0.25 -0.57
  sec 180-240                          n= 115 W= 49.6% per$1=+0.095 total= +32.83 maxDD= 16.49 run= 3 negdays=5/9 | +0.34 -0.05 +0.17 -0.01 +0.34 -0.09 +0.35 -0.12 -0.11
  sec 240+*                            n=   2 W=  0.0% per$1=-1.000 total=  -6.00 maxDD=  6.00 run= 2 negdays=1/1 | -1.00
-- CALIBRATED
  rv60 low<0.36                        n= 125 W= 55.2% per$1=+0.290 total=+108.80 maxDD= 17.92 run= 4 negdays=3/9 | -0.04 -0.07 +0.40 +0.37 +0.29 +0.64 +0.57 +0.15 -0.32
  rv60 mid                             n= 125 W= 58.4% per$1=+0.339 total=+127.10 maxDD= 14.74 run= 4 negdays=1/9 | +0.32 +0.45 +0.35 +0.39 +0.71 +0.36 +0.40 +0.38 -0.60
  rv60 high>=0.60                      n= 125 W= 54.4% per$1=+0.264 total= +99.13 maxDD= 23.69 run= 5 negdays=1/9 | +0.37 +0.57 +0.23 +0.01 +0.76 -1.00 +0.43 +0.14 +0.81
  hour 00-06                           n=  68 W= 60.3% per$1=+0.396 total= +80.69 maxDD=  9.00 run= 3 negdays=3/8 | +0.59 -0.05 +0.67 -0.02 +0.60 +0.54 +0.75 -0.10
  hour 06-12                           n=  69 W= 58.0% per$1=+0.406 total= +83.97 maxDD=  9.91 run= 3 negdays=2/8 | +0.23 +0.77 -0.07 +1.15 -0.22 +0.39 +0.49 +0.00
  hour 12-18                           n= 124 W= 54.0% per$1=+0.205 total= +76.33 maxDD= 20.79 run= 4 negdays=3/9 | -1.00 +0.37 +0.18 +0.12 +0.09 +0.93 +0.66 -0.16 -1.00
  hour 18-24                           n= 114 W= 54.4% per$1=+0.275 total= +94.03 maxDD= 27.18 run= 6 negdays=1/8 | +0.25 -0.01 +0.37 +0.09 +0.61 +0.38 +0.34 +0.02
  ask <0.30*                           n=  19 W= 47.4% per$1=+0.828 total= +47.22 maxDD= 15.00 run= 5 negdays=2/7 | -1.00 -1.00 +0.46 +0.82 +1.26 +2.41 +2.39
  ask 0.30-0.40                        n= 110 W= 50.9% per$1=+0.426 total=+140.54 maxDD= 25.03 run= 7 negdays=0/9 | +0.01 +0.46 +0.51 +0.18 +0.36 +0.83 +0.34 +0.89 +0.12
  ask 0.40-0.50                        n= 142 W= 57.0% per$1=+0.241 total=+102.56 maxDD= 24.88 run= 5 negdays=2/9 | +0.58 +0.25 +0.32 +0.27 +0.62 +0.28 +0.32 -0.07 -0.45
  ask 0.50-0.60                        n= 104 W= 61.5% per$1=+0.143 total= +44.71 maxDD= 24.56 run= 3 negdays=3/9 | +0.43 +0.32 +0.08 +0.12 -0.08 +0.26 +0.34 -0.16 -0.39
  sec 0-60                             n= 134 W= 56.0% per$1=+0.217 total= +87.20 maxDD= 25.80 run= 6 negdays=2/9 | +0.53 +0.80 +0.11 -0.12 +0.24 +0.57 +0.44 +0.30 -1.00
  sec 60-120                           n= 104 W= 54.8% per$1=+0.265 total= +82.57 maxDD= 23.55 run= 5 negdays=4/9 | -0.38 -0.20 +0.33 +0.72 -0.03 -0.43 +0.50 +0.17 +0.40
  sec 120-180                          n=  75 W= 65.3% per$1=+0.645 total=+145.10 maxDD=  9.33 run= 3 negdays=0/9 | +1.39 +0.45 +0.70 +0.74 +0.83 +0.65 +0.53 +0.62 +0.09
  sec 180-240                          n=  60 W= 48.3% per$1=+0.145 total= +26.15 maxDD= 20.30 run= 6 negdays=3/9 | +0.07 -0.03 +0.34 -0.09 +0.75 +0.64 +0.30 -1.00 +0.06
  sec 240+*                            n=   2 W=  0.0% per$1=-1.000 total=  -6.00 maxDD=  6.00 run= 2 negdays=1/1 | -1.00
```
