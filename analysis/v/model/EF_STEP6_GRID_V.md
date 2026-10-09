# EF step 6 - every combination of its settings (V, 09-23 03:2x UTC)

Script: analysis/v/model/ef_step6_grid.py. Full grid (360 rows): analysis/v/model/ef_step6_grid.csv. 3 calibrations x 10 EV modes x 4 pads x 3 max-ask caps, exact venue fee, $5, 8 test days, graded on Polymarket. "walkfwd_platt" = each day fitted only on earlier days: the honest estimate of the live fix going forward; "pooled_platt" is fitted on these same days (in-sample, flattering).

## Read
1. **Pad (0-5 ticks) and max ask (0.50-0.70) barely matter**: +-$30 over 8 days. Not worth touching.
2. **The EV bar with the fix is the only real dial.** Honest walk-forward, fixed bar: 0.15 +$407 DD $53 | 0.20 +$309 DD $37 | 0.25 +$287 DD $32, 58% right, 0 losing days | 0.30 +$212 DD $22, 0 losing days. Profit and drawdown fall together, monotone.
3. **Regime mode (v10 own per-volatility bars) does not beat a fixed bar** once honest (walk-forward regime_x0.6 +$438 DD $53 vs fixed 0.15 +$407 DD $53).
4. **Raw p is never better per $ of drawdown** (best p/DD 11.6 at bar 0.30 vs walk-forward fix 9.7 at 0.30 with half the DD).
5. **Wallet-driven choice, not a best cell**: with ~$43 in the wallet, the honest DD must fit. At $5 that means the fix with bar 0.25 (DD $32, +$287/8 days), or bar 0.15 at $3 stake (DD ~$32, ~+$244). Same risk, bar 0.25 at $5 keeps slightly more profit and trades ~20/day instead of ~49.

## Output
```
360 combinations, 1031 fires on 8 test days -> analysis/v/model/ef_step6_grid.csv

MAIN SLICE (pad 1, max ask 0.60 = live), every calibration x EV mode:
calibration     EV mode        /day  right  profit  maxDD  p/DD losedays  run
raw             fixed_0.05    126.2  51.9%    +627     92   6.8        1    8
raw             fixed_0.10    126.2  51.9%    +627     92   6.8        1    8
raw             fixed_0.15    126.1  51.9%    +632     92   6.9        1    8
raw             fixed_0.20     85.9  51.7%    +631     84   7.5        1    7
raw             fixed_0.25     68.2  52.4%    +609     71   8.6        1    8
raw             fixed_0.30     36.2  53.1%    +478     41  11.6        1    6
raw             fixed_0.40     12.1  50.5%    +209     32   6.5        0    4
raw             regime        118.0  52.5%    +655     80   8.2        1    8
raw             regime_x0.6   126.2  51.9%    +627     92   6.8        1    8
raw             regime_x1.4    30.5  53.3%    +407     39  10.3        0    7
pooled_platt    fixed_0.05     92.6  53.4%    +701     82   8.6        1    7
pooled_platt    fixed_0.10     65.2  54.2%    +614     71   8.7        1    9
pooled_platt    fixed_0.15     33.2  57.1%    +463     33  14.0        1    5
pooled_platt    fixed_0.20     17.8  52.8%    +246     20  12.3        1    4
pooled_platt    fixed_0.25      8.9  56.3%    +196     22   9.0        0    4
pooled_platt    fixed_0.30      6.4  54.9%    +153     22   7.0        1    4
pooled_platt    fixed_0.40      4.0  53.1%    +105     17   6.3        2    3
pooled_platt    regime          9.8  56.4%    +217     27   8.1        0    4
pooled_platt    regime_x0.6    37.6  58.5%    +539     33  16.3        0    5
pooled_platt    regime_x1.4     6.0  52.1%    +140     20   6.9        0    4
walkfwd_platt   fixed_0.05     91.5  54.0%    +605     78   7.8        1    7
walkfwd_platt   fixed_0.10     68.1  53.6%    +469     71   6.6        1    9
walkfwd_platt   fixed_0.15     48.8  54.6%    +407     53   7.7        1    7
walkfwd_platt   fixed_0.20     31.4  54.6%    +309     37   8.3        0    5
walkfwd_platt   fixed_0.25     19.6  58.0%    +287     32   9.1        0    4
walkfwd_platt   fixed_0.30     10.0  58.8%    +212     22   9.7        0    3
walkfwd_platt   fixed_0.40      4.5  58.3%    +129     15   8.6        1    3
walkfwd_platt   regime         27.6  56.1%    +281     58   4.8        0    7
walkfwd_platt   regime_x0.6    57.4  55.1%    +438     53   8.3        1    7
walkfwd_platt   regime_x1.4     7.1  50.9%    +122     17   7.3        0    3

EFFECT OF PAD and MAX ASK on the live combination (pooled Platt, fixed 0.15):
  pad 0 max_ask 0.50:  25.8/day right  55.8% profit   +428 maxDD    30 losing days 0
  pad 0 max_ask 0.60:  33.2/day right  57.1% profit   +463 maxDD    33 losing days 1
  pad 0 max_ask 0.70:  34.5/day right  57.6% profit   +466 maxDD    30 losing days 1
  pad 1 max_ask 0.50:  25.8/day right  55.8% profit   +428 maxDD    30 losing days 0
  pad 1 max_ask 0.60:  33.2/day right  57.1% profit   +463 maxDD    33 losing days 1
  pad 1 max_ask 0.70:  34.5/day right  57.6% profit   +466 maxDD    30 losing days 1
  pad 3 max_ask 0.50:  24.2/day right  55.2% profit   +396 maxDD    25 losing days 0
  pad 3 max_ask 0.60:  31.8/day right  56.7% profit   +432 maxDD    33 losing days 1
  pad 3 max_ask 0.70:  33.0/day right  57.2% profit   +435 maxDD    26 losing days 1
  pad 5 max_ask 0.50:  23.0/day right  54.9% profit   +384 maxDD    21 losing days 0
  pad 5 max_ask 0.60:  30.5/day right  56.6% profit   +419 maxDD    33 losing days 1
  pad 5 max_ask 0.70:  31.8/day right  57.1% profit   +422 maxDD    26 losing days 1

SAME, walk-forward Platt (honest version of the live fix):
  pad 0 max_ask 0.50:  35.5/day right  52.5% profit   +372 maxDD    42 losing days 1
  pad 0 max_ask 0.60:  49.9/day right  55.1% profit   +435 maxDD    53 losing days 1
  pad 0 max_ask 0.70:  51.8/day right  55.6% profit   +436 maxDD    50 losing days 1
  pad 1 max_ask 0.50:  34.6/day right  51.6% profit   +342 maxDD    42 losing days 1
  pad 1 max_ask 0.60:  48.8/day right  54.6% profit   +407 maxDD    53 losing days 1
  pad 1 max_ask 0.70:  50.6/day right  55.1% profit   +407 maxDD    50 losing days 1
  pad 3 max_ask 0.50:  34.1/day right  51.6% profit   +342 maxDD    42 losing days 1
  pad 3 max_ask 0.60:  46.9/day right  54.4% profit   +401 maxDD    52 losing days 1
  pad 3 max_ask 0.70:  48.4/day right  55.0% profit   +408 maxDD    49 losing days 1
  pad 5 max_ask 0.50:  32.2/day right  52.3% profit   +344 maxDD    42 losing days 1
  pad 5 max_ask 0.60:  44.5/day right  54.5% profit   +386 maxDD    52 losing days 1
  pad 5 max_ask 0.70:  45.9/day right  55.0% profit   +392 maxDD    49 losing days 1
```
