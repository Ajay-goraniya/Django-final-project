# EF_TRIGGER_SOURCE - does an EF fire come from the BOOK moving or the MODEL moving?

Zurich, 2026-09-28. READ-ONLY on the research archive's `decide_log`, labels = the venue's own resolution
(gamma `outcomePrices`). Master is OFF; every number below is shadow with SIMULATED fills. Nothing live,
nothing deployed, no config touched.

V's brief: London's REAL fills show attempt-1 against a book less than 50 ms old reaching a **69% candle
fill**, against 31% per attempt overall. So classify each EF fire by what changed, and then test firing only
on the book-triggered passes.

## Answer up front

1. The classification works, and it splits the fires very unevenly: the book moving to us is a **minority**
   trigger. On raw25, 5% of fires are book-only-down, 0% book-only-up, 18% model-only, 15% both, and **62%
   are side flips** - the previous pass logged the *other* side, because a fire is usually the moment the
   engine switches to the side that just crossed the bar.
2. The fill-rate half of V's hypothesis is **confirmed, strongly**: book-triggered fires fill 82.4% vs 36.2%
   for model-triggered (raw25). A fire aimed at a book that just moved is a fire that lands.
3. The money half is **inverted**. The cell that fills best has no edge (BOOK-dn −0.007/$1) and the cell that
   fills worst has the edge (MODEL +0.234/$1, 57.1% win, both halves positive). The same inversion appears
   inside the side-flip class: FLIP-mv −0.002 vs FLIP-still +0.398.
4. So V's policy - **fire only on book-triggered passes** - is worse than doing nothing, on both profiles:
   raw25 +0.071 -> **−0.021**, fixed15 +0.061 -> **−0.158**. It also gives up 68 of 325 candles (raw25).
5. Its mirror - fire only on a book-STILL pass - reads +0.032 (raw25) and **+0.177** (fixed15, 163 fires, 86
   fills, H1 +0.324 / H2 +0.030). fixed15's mirror is the only cell in the grid that meets the standing
   precondition for verify.py, so it was run. **It is NOT A FINDING** - see the verdict below.
6. The reason is in the reversion column and it is the same mechanism as EF_VETO_V2 and EF_PERSIST: nothing
   here is about *stillness*, it is about which fires are *selected dips*. Book-still fires carry +5.8c of
   ask reversion (you often miss, and when you hit you hit a good price); book-moved fires carry +0.0c (you
   always hit, at a price that was real). Filtering on the trigger just re-sorts the same population by how
   adversely selected the fill is.

## Method

There is **no quote-age column** in Zurich's `decide_log` - the 44 feature keys contain no age of any kind -
so London's "<50 ms book" cut cannot be reproduced here. V's proxy is what is available: compare each pass
with the **previous pass in the same candle**, 257 ms earlier (row gap p5 253 / p50 257 / p95 276 ms, the
250 ms throttle).

OUR side's ask is read on **both** rows from `up_ask`/`dn_ask`, so a side change does not corrupt the ask
comparison. The logged `ask` equals the own-side book ask on **852,162 of 852,162** rows, which is what makes
this exact.

```
dask = own ask now - own ask on the previous pass          dp = p now - p on the previous pass
BOOK-dn / BOOK-up   |dask| >= 1 tick and |dp| <  0.01      (split by sign: a dip we chase is not the
MODEL               |dask| <  1 tick and |dp| >= 0.01       same event as the book leaving)
BOTH-dn / BOTH-up   |dask| >= 1 tick and |dp| >= 0.01
NEITHER             |dask| <  1 tick and |dp| <  0.01
FLIP-mv/FLIP-still  previous pass logged the OTHER side, so dp is not comparable; |dask| still is
FIRST               no previous pass, or no usable previous quote on our side
```

`p` is the RAW model p: `meta.ef_profile` is `raw_v10_live25` and `meta.calibration.enabled` is false (and
`p_raw` is NULL on all 1,240,440 live rows), so raw25 reads `p` directly and fixed15 applies the Platt
a=1.0677 b=-0.3208 to it. `dp` is deliberately NOT converted across a side flip: measured, p is not
symmetric across one (residual mean +0.0715, **0.0%** of flips within 0.02), because the flip is itself
selected on p having moved.

The fill simulator, the capital-weighted per-$1, the halves and the sign-flip permutation are **imported
from `ef_persist.py`**, not re-implemented, so these are the same numbers EF_PERSIST.md was built on: a FAK
at ask+1 tick fills iff our side's ask on the first same-candle row at >= t+250 ms is within a tick, and it
fills AT that later ask.

`revC` = mean(later ask − fire ask) in cents on our side; `dask` = mean signed ask change in cents.

## The full grid

5 days (09-24..09-28), 1,015 graded candles, 785,924 passes. All passes by class: BOOK-dn 34,192 (4.4%),
BOOK-up 49,047 (6.2%), MODEL 55,210 (7.0%), BOTH-dn 26,802 (3.4%), BOTH-up 35,868 (4.6%), NEITHER 576,014
(73.3%), FLIP-mv 4,134 (0.5%), FLIP-still 3,642 (0.5%), FIRST 1,015 (0.1%).

### (1) THE ACTUAL FIRE - the first qualifying pass of each candle, which is what the engine does

```
--- raw25 ---
  ALL fires                       325   137   42.2%   43.8%   +0.071    +96.3  +0.213  -0.069  0.202  -0.006    5  +6.02  +1.99   258
  --------------------------------------------------------------------------------------------------------------------------------------------------------------
  BOOK-dn                          17    14   82.4%   42.9%   -0.007     -1.0  +0.274  -0.288  0.502  -0.028    4  +0.06  -1.59   258  *n<60
  BOOK-up                           0      (no fills)
  MODEL                            58    21   36.2%   57.1%   +0.234    +49.0  +0.272  +0.201  0.154  +0.007    5  +6.29  +0.00   257  *n<60
  BOTH-dn                           7     3   42.9%   66.7%   +0.603    +18.0  +1.140  +0.336  0.152  +0.164    2  +6.29  -9.29   259  *n<60
  BOTH-up                          41    18   43.9%   22.2%   -0.556   -100.1  -0.574  -0.538  0.990  -0.063    4  +3.39  +2.10   263  *n<60
  NEITHER                           0      (no fills)
  FLIP-mv                         114    41   36.0%   39.0%   -0.002     -0.6  +0.315  -0.304  0.400  -0.043    5  +6.39  +5.68   259  *n<60
  FLIP-still                       86    38   44.2%   52.6%   +0.398   +151.0  +0.626  +0.170  0.042  +0.062    4  +7.92  +0.00   258  *n<60
  FIRST                             2     2  100.0%    0.0%   -1.000    -20.0  -1.000  -1.000  1.000  -0.173    2  -0.50   +nan   nan  *n<60

--- fixed15 ---
  ALL fires                       195    82   42.1%   43.9%   +0.061    +47.8  +0.190  -0.068  0.458  +0.046    5  +7.23  +1.89   259
  --------------------------------------------------------------------------------------------------------------------------------------------------------------
  BOOK-dn                          13    10   76.9%   20.0%   -0.523    -52.6  -0.432  -0.614  0.950  +0.018    5  +1.62  -1.69   259  *n<60
  BOOK-up                           0      (no fills)
  MODEL                            43    17   39.5%   58.8%   +0.202    +33.9  +0.318  +0.099  0.282  +0.041    4  +5.53  +0.00   255  *n<60
  BOTH-dn                           5     2   40.0%   50.0%   +0.067     +1.4  +1.140  -1.000  0.468  -0.119    1  +8.20 -11.40   265  *n<60
  BOTH-up                          42    16   38.1%   37.5%   -0.270    -43.5  +0.194  -0.731  0.846  +0.054    5  +3.52  +2.57   258  *n<60
  NEITHER                           0      (no fills)
  FLIP-mv                          44    20   45.5%   35.0%   -0.048     -9.5  +0.463  -0.561  0.520  -0.047    5  +8.57  +7.73   262  *n<60
  FLIP-still                       48    17   35.4%   58.8%   +0.696   +118.0  +0.918  +0.499  0.032  +0.149    4 +12.19  +0.00   259  *n<60
  FIRST                             0      (no fills)

```
**BOOK-up = 0 and NEITHER = 0 on both profiles, and that is a consistency check rather than a gap.** A pass
whose only change is the ask moving AWAY from us cannot be the first pass to cross an EV bar, and neither can
a pass where nothing moved by a tick or by 0.01. The classifier reproducing both zeros is evidence it is
measuring what it claims.

The two largest cells are the two ends of the inversion:

| cell | fires | fill% | win% of fills | per $1 | H1 / H2 | ask reversion |
|---|---|---|---|---|---|---|
| BOOK-dn (raw25) - we chase a dip | 17 | **82.4%** | 42.9% | −0.007 | +0.274 / −0.288 | **+0.06c** |
| MODEL (raw25) - book still, p moved | 58 | **36.2%** | 57.1% | **+0.234** | +0.272 / +0.201 | **+6.29c** |
| FLIP-mv (raw25) | 114 | 36.0% | 39.0% | −0.002 | +0.315 / −0.304 | +6.39c |
| FLIP-still (raw25) | 86 | 44.2% | 52.6% | **+0.398** | +0.626 / +0.170 | +7.92c |
| BOTH-up (raw25) - p chases a rising ask | 41 | 43.9% | **22.2%** | **−0.556** | −0.574 / −0.538 | +3.39c |

BOTH-up is the worst cell on the board and it is the engine chasing its own model into a market moving away
from it: p rose by more than the ask rose, so EV still cleared, and the trade won 22.2% of the time.

### (2) EVERY qualifying pass, not just the first per candle - the conditional edge by class

This is the control on section (1). If "the book was still" were a genuine property of a good trade, it
would show up here too. It does not - the whole population is negative and book-still is not the best cell.

```
--- raw25 ---
  ALL qualifying passes         13295 11327   85.2%   45.3%   -0.059  -6698.2  +0.090  -0.208  1.000  -0.031    5  +0.54  +0.24   255
  --------------------------------------------------------------------------------------------------------------------------------------------------------------
  BOOK-dn                         849   764   90.0%   42.3%   -0.108   -821.8  +0.037  -0.252  0.972  -0.045    5  -0.03  -1.48   257
  BOOK-up                         871   716   82.2%   44.3%   -0.106   -760.7  -0.048  -0.164  0.970  -0.035    5  +0.56  +1.54   257
  MODEL                          1192   882   74.0%   45.9%   -0.045   -394.5  -0.069  -0.021  0.616  -0.035    5  +1.25  +0.00   255
  BOTH-dn                         585   514   87.9%   37.2%   -0.156   -803.6  +0.136  -0.447  0.996  -0.038    5  -0.20  -2.74   259
  BOTH-up                        1118   744   66.5%   46.2%   -0.044   -331.7  +0.136  -0.224  0.676  -0.026    5  +1.56  +3.02   260
  NEITHER                        8166  7445   91.2%   46.2%   -0.052  -3869.1  +0.173  -0.276  0.950  -0.032    5  +0.15  +0.00   253
  FLIP-mv                         302   150   49.7%   41.3%   +0.083   +124.8  +0.391  -0.225  0.094  -0.014    5  +4.13  +4.48   259
  FLIP-still                      210   110   52.4%   43.6%   +0.163   +178.3  +0.587  -0.262  0.078  +0.011    5  +5.41  +0.00   257
  FIRST                             2     2  100.0%    0.0%   -1.000    -20.0  -1.000  -1.000  1.000  -0.173    2  -0.50   +nan   nan  *n<60

--- fixed15 ---
  ALL qualifying passes          9646  8132   84.3%   48.0%   -0.092  -7434.7  +0.047  -0.230  1.000  -0.029    5  +0.57  +0.25   254
  --------------------------------------------------------------------------------------------------------------------------------------------------------------
  BOOK-dn                         669   598   89.4%   47.3%   -0.117   -695.6  -0.083  -0.150  0.944  -0.049    5  +0.02  -1.54   258
  BOOK-up                         746   600   80.4%   51.7%   -0.083   -500.3  -0.041  -0.126  0.922  -0.025    5  +0.60  +1.63   257
  MODEL                           846   609   72.0%   48.4%   -0.053   -322.4  -0.051  -0.055  0.666  -0.036    5  +1.29  +0.00   255
  BOTH-dn                         368   307   83.4%   42.7%   -0.089   -274.5  +0.016  -0.193  0.916  -0.009    5  +0.10  -2.67   261
  BOTH-up                         878   570   64.9%   49.3%   -0.041   -240.4  +0.077  -0.160  0.748  -0.009    5  +1.61  +2.93   261
  NEITHER                        5937  5346   90.0%   47.9%   -0.105  -5601.7  +0.114  -0.324  1.000  -0.033    5  +0.20  +0.00    65
  FLIP-mv                         122    68   55.7%   39.7%   +0.106    +72.4  +0.311  -0.099  0.182  -0.006    5  +4.88  +5.11   263
  FLIP-still                       80    34   42.5%   47.1%   +0.377   +127.9  +0.847  -0.094  0.066  +0.087    5  +8.83  +0.00   258  *n<60
  FIRST                             0      (no fills)

```
All 13,295 raw25 qualifying passes fill at **85.2%** and pay **−0.059/$1**. The 325 first-qualifying fires
fill at 42.2% and pay +0.071. The engine's one-fire-per-candle rule is therefore picking the 2.4% of
qualifying passes that fill worst, and that is where all of its apparent edge is. Selection, again.

### (3) PER DAY

```
  (3) raw25: PER DAY, fires / fill% / per$1, book moved vs model-only
    day       fires            BOOK moved            model-only         no prev quote
    09-24        62         32 50% -0.104         30 33% +0.661                   0 -
    09-25       119         66 35% +0.257         52 52% +0.300         1 100% -1.000
    09-26        62         36 39% -0.078         26 35% -0.256                   0 -
    09-27        74         41 51% -0.451         33 36% +0.547                   0 -
    09-28         8          4 50% -1.000          3 33% +1.095         1 100% -1.000

  (3) fixed15: PER DAY, fires / fill% / per$1, book moved vs model-only
    day       fires            BOOK moved            model-only         no prev quote
    09-24        47         26 42% -0.019         21 33% +0.584                   0 -
    09-25        78         39 41% -0.068         39 41% +0.548                   0 -
    09-26        28         15 47% -0.192         13 15% +0.089                   0 -
    09-27        36         21 52% -0.424         15 53% +0.147                   0 -
    09-28         6         3 100% -1.000          3 33% +1.095                   0 -

```
Book-moved fires are negative on 4 of 5 days on raw25 and on **all 5** on fixed15. Model-only fires are
positive on 4 of 5 on raw25 and on **all 5** on fixed15. The direction is consistent day by day, which is
what made it worth taking to verify.py rather than dismissing.

### (4) THE POLICY V ASKED FOR, and its mirror

```
  (4) raw25: POLICY - fire only when the book moved, model-only passes wait for the next book change
  arm                           fires fills   fill%    win%    per$1   total$      H1      H2  permP   permM days   revC   dask    dt
  baseline: first qualifying      325   137   42.2%   43.8%   +0.071    +96.3  +0.213  -0.069  0.202  -0.006    5  +6.02  +1.99   258
  policy, FIRST waits             257   117   45.5%   41.9%   -0.021    -25.0  +0.203  -0.242  0.440  -0.036    5  +4.95  +3.63   259
  INVERSE: only book-still        270   150   55.6%   43.3%   +0.032    +46.7  +0.108  -0.044  0.320  -0.005    5  +4.73  +0.00   258
      paired on 99 candles filled in both (23 moved to a later pass): baseline -0.074 vs policy -0.076
      candles the policy gives up entirely: 68 of 325; waited on 78, wait p50 582 ms p90 109890 ms
  policy, FIRST counts as mv      258   118   45.7%   41.5%   -0.030    -35.0  +0.183  -0.242  0.448  -0.044    5  +4.93  +3.63   259
      paired on 100 candles filled in both (22 moved to a later pass): baseline -0.083 vs policy -0.085
      candles the policy gives up entirely: 67 of 325; waited on 77, wait p50 596 ms p90 110052 ms

  (4) fixed15: POLICY - fire only when the book moved, model-only passes wait for the next book change
  arm                           fires fills   fill%    win%    per$1   total$      H1      H2  permP   permM days   revC   dask    dt
  baseline: first qualifying      195    82   42.1%   43.9%   +0.061    +47.8  +0.190  -0.068  0.458  +0.046    5  +7.23  +1.89   259
  policy, FIRST waits             147    69   46.9%   37.7%   -0.158   -109.7  -0.028  -0.284  0.890  -0.017    5  +5.57  +3.65   260
  INVERSE: only book-still        163    86   52.8%   50.0%   +0.177   +149.8  +0.324  +0.030  0.128  +0.043    5  +5.79  +0.00   259
      paired on 56 candles filled in both (8 moved to a later pass): baseline -0.204 vs policy -0.234  *n<60
      candles the policy gives up entirely: 48 of 195; waited on 43, wait p50 1014 ms p90 61571 ms
  policy, FIRST counts as mv      147    69   46.9%   37.7%   -0.158   -109.7  -0.028  -0.284  0.890  -0.017    5  +5.57  +3.65   260
      paired on 56 candles filled in both (8 moved to a later pass): baseline -0.204 vs policy -0.234  *n<60
      candles the policy gives up entirely: 48 of 195; waited on 43, wait p50 1014 ms p90 61571 ms
```
"Fire only when the book moved, and let a model-only pass wait for the next book change" loses on both
profiles. Making the candle's first pass count as a book change (the lenient variant) changes nothing.

The paired lines are the important ones and they say the policy is not really a different *rule*, it is a
different *population*: on the candles both arms fill, baseline and policy are the same to three decimals
(raw25 −0.074 vs −0.076; fixed15 −0.204 vs −0.234) and **both are negative**. All of the baseline's +0.071
comes from the candles the policy discards. Waiting p50 is 582 ms but p90 is 110 s, i.e. the wait usually
runs to the end of the candle.

## verify.py on the one cell that qualified

Standing rule: run verify.py on any cell positive in both halves with n >= 60. Exactly one qualifies -
fixed15's mirror arm, fire only on a book-still pass, +0.177/$1 on 163 fires and 86 simulated fills, H1
+0.324 / H2 +0.030. (raw25's mirror is +0.032 with H2 negative; every per-class cell is under 60 fills.)

```
cell: fixed15, fire only when the book did not move - 163 fires, 86 sim fills, per$1 +0.1766, win 50.0%
  [info, not a gate] Binance-TWAP60 proxy vs the venue: 96.73% agreement over 2,232 epochs (MULTI_MARKET.md). The proxy is NOT used here; every label above is the venue resolution.
  sweep |dask| ticks 0/1/2/>=3 -> -0.097 (n=5989)  -0.045 (n=1166)  -0.110 (n=451)  -0.116 (n=526)
  sweep EV bar 0.10:+0.177(n=86)  0.15:+0.177(n=86)  0.20:+0.302(n=36)  0.25:+0.203(n=15)  0.30:+0.784(n=9)
  paired pool: 67 candles filled in both; 33 fire at a different pass
==============================================================================
FINDING: fixed15 EF fires only on a book-still pass (Zurich shadow, simulated fills)   (+0.177/fire, n=86)
==============================================================================
  [PASS] grading provenance   gamma_btc5 vs gamma_btc5b disagree on 0/140 (0.0%)
  [PASS] quote age            rule=at-or-after, max age 0.0s from decide_log own-side ask at >= t+250 ms
  [PASS] sample size          all 2 cells >= 60
  [FAIL] sample size          under the 60 bar: {'09-24': 22, '09-25': 32, '09-26': 10, '09-27': 19, '09-28': 3}
  [PASS] both halves          h1 +0.324 / h2 +0.030
  [FAIL] permutation control  real +0.177 vs permuted mean +0.319 (p95 +0.448), p=0.966 over 500 draws
  [FAIL] sweep shape          NON-monotone: [-0.097 -0.045 -0.11  -0.116]  <- peaks at an interior point, classic overfit
  [FAIL] sweep shape          NON-monotone: [0.177 0.177 0.302 0.203 0.784]
  [PASS] cost sensitivity     +0c:+0.177 +0c:+0.161 +1c:+0.147 +2c:+0.119
  [PASS] beats the null       mine +0.177 vs fixed15 unfiltered first qualifying pass +0.061
  [FAIL] paired test          n=67, agree on 66, discordant 1 (1 vs 0), edge +0.015, exact McNemar p=1.000
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, permutation control, sweep shape, sweep shape, paired test

```

**NOT A FINDING.** Three of the five failures are decisive and none of them depend on my choice of sweep:

- **Permutation p=0.966, and the permuted mean (+0.319) is HIGHER than the real result (+0.177).** Shuffling
  the model's p and re-applying the same fixed15 bar at each row's own ask does *better* than the real p.
  The edge is not in p; it is in the ask the bar happens to select. This is the same result as REV_BRAIN
  (31 live features AUC 0.431 against venue-ask-only 0.725) arriving by a different route.

  One caveat on how that control is built, because it is worth auditing. Once the trade set is fixed, per $1
  does not depend on p at all — so shuffling p inside a fixed set cannot move the number, and re-selection is
  the only permutation that carries any information. The price of that is unequal n: the real arm is all-true
  under its own bar by construction (86 of 86), while a shuffled p qualifies a smaller, differently composed
  subset. So the *distribution* of permuted values is not directly comparable in variance to the real one.
  What is not explained by that asymmetry is the direction and size: the permuted arms average +0.319, a
  higher return than the real selection, which says the bar evaluated against each row's own ask is doing the
  selecting and p is along for the ride. The paired McNemar (66 of 67 candles identical) and the non-monotone
  |dask| sweep reach the same conclusion without any permutation at all.
- **Paired: 67 candles filled in both arms, they agree on 66, one discordant pair, McNemar p=1.000.** The
  filter is not choosing better trades; 96 dropped candles are doing the work. This is precisely the trap
  `verify.paired` was written for after 09-11.
- **Sweep on |dask| is non-monotone: 0 ticks −0.097, 1 tick −0.045, 2 ticks −0.110, >=3 ticks −0.116.** If
  stillness caused the edge, 0 ticks would be the best bucket on the full qualifying population. It is not -
  1 tick is. So "book-still" is not a mechanism, it is a label that happens to correlate with the selection.
- Per-day samples are 22 / 32 / 10 / 19 / 3. The EV-bar sweep is also non-monotone (+0.177, +0.177, +0.302,
  +0.203, +0.784 on n = 86, 86, 36, 15, 9).

Cost sensitivity and the null pass, and the grading and quote-age gates pass cleanly (two independent gamma
pulls agree on 140/140 candles; the fill price is strictly at-or-after the decision). Those were never the
weak points.

## What this means

The trigger source is real and measurable, and it predicts the **fill** very well: 82% against 36%. It does
not predict the **money**, and the sign of its association with money is the opposite of the sign of its
association with fills. That is the definition of adverse selection, and it is now the fourth independent
measurement of the same thing on this box:

| study | measurement |
|---|---|
| EF_VETO_V2 | the same-source ask is +6.02c higher one row after a raw25 fire, against +0.43c market-wide |
| EF_PERSIST | requiring the dip to persist raises the fill rate and removes the edge |
| ASK_LIFETIME_MS | 67.9% of asks are cancelled, p50 live 6 ms, 10 ms adverse-only |
| EF_TRIGGER_SOURCE | the fires that land are the fires with no reversion, and they pay −0.007/$1 |

The practical read for London: **raising the fill rate is not an improvement by itself.** London's 69%
figure on a <50 ms book is a fill-rate figure, and on Zurich's data the population that fills like that pays
nothing. Before acting on it, London should split its own REAL fills the same way - by whether its own ask
moved on the pass it fired on - and check whether its 69% bucket is where its money actually is. Zurich
predicts it is not, and London has the one thing Zurich does not: real fills.

No deploy, no config change, master still OFF.

## Files

- `ef_trigger_source.py` - the classifier and the grid; imports the fill simulator from `ef_persist.py`
- `ef_trigger_verify.py` - verify.py on the one qualifying cell

## Export for London — `ef_trigger_source_spec.json`

The read above ends with "London should split its own real fills the same way", so here is the means to do it
without re-deriving anything: `ef_trigger_source_spec.json` carries the classification rule, the exact per-pass
columns it needs (`epoch`, `ts_ms`, `side`, `up_ask`, `dn_ask`, `p`), the thresholds, Zurich's per-class
reference numbers, and three consistency checks that should reproduce on any correct implementation
(BOOK-up = 0, NEITHER = 0, side flips ≈62% of fires).

Two things the spec says loudly, because a JSON file outlives the conversation that produced it:

- **`not_a_filter`.** It records the verdict and the four gates that failed. This is a measurement spec. The
  filter version of it must not be deployed anywhere, and nothing here is a deploy request.
- **The one thing only London can do.** Zurich has no quote-age column, so the class-by-book-age cross is not
  available here. London has it. The prediction to test is that its 69% bucket *is* the book-triggered
  population, which Zurich measures at −0.007/$1 against +0.234 for the 36%-fill model-triggered population.
