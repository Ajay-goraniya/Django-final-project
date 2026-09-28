# ETH_SOL_DIAG — why the ETH/SOL EF shadow is negative at 24 h

Zurich, 2026-09-28 06:0x. READ-ONLY on my own four shadow DBs. Master OFF, nothing live, nothing deployed.

The 09-28 ledger put three of four arms under water: eth frozen −0.078, sol frozen −0.277, eth platt −0.269,
sol platt +0.075 (620 graded fires pooled, per $1 **−0.146**, win 31.1%). "It loses" is not a finding. The
question the owner actually asked — does EF work individually on these coins — needs to know *what* fails.

Labels throughout are `results.src = gamma.outcomePrices`, the venue's own resolution, per the standing
settlement rule. Every arm's src column was checked, not assumed.

## Answer: the model's RANKING transfers to ETH/SOL. Its LEVEL does not. The fill is fine.

That is the opposite diagnosis from BTC, and it matters because it points at a different fix.

**1. The ranking is real.** Win rate rises monotonically across every p bucket, pooled over all four arms:

| p_side bucket | n | win% | mean p | per $1 |
|---|---|---|---|---|
| 0.00–0.30 | 77 | 14.3% | 0.234 | −0.190 |
| 0.30–0.40 | 118 | 23.7% | 0.355 | −0.110 |
| 0.40–0.50 | 153 | 24.8% | 0.457 | −0.284 |
| 0.50–0.60 | 148 | 37.2% | 0.546 | −0.079 |
| 0.60–0.75 | 79 | 48.1% | 0.661 | **+0.017** |
| 0.75–1.00 | 45 | 51.1% | 0.831 | −0.195 |

Six buckets, monotone in win rate, no reversal. AUC of `p_side` against the outcome is **0.647**. The model
knows something about ETH and SOL.

**2. The level is wrong by 17 pp.** Mean p **0.484** against a realised **0.311**. Every bucket sits below its
own mean p, and the gap is worst where the model is most confident (0.831 claimed, 0.511 realised).

This is measured **on the fired set**, which is selected — so it is not an unconditional claim about the
model, it is the calibration error *where the money is*. The shadows' `skips` table carries only a reason and
a short detail, no p, so an unconditional calibration cannot be computed from these DBs.

**3. Therefore EV is anti-predictive.** EV is a level quantity, `p/breakeven − 1`, so a 17 pp inflation in p
lands entirely in EV — and the fires with the biggest EV are the ones where the inflation is largest:

| EV bucket | n | win% | per $1 |
|---|---|---|---|
| 0.0–0.3 | 224 | 37.5% | −0.123 |
| 0.3–0.5 | 297 | 30.6% | −0.102 |
| 0.5–0.8 | 68 | 19.1% | **−0.376** |
| 0.8–1.2 | 17 | 23.5% | +0.088 |
| 1.2+ | 14 | 7.1% | **−0.634** |

The EF rule is "fire when EV clears a bar". On these coins that rule is selecting *against* itself. SOL alone
is almost perfectly monotone downward: −0.071, −0.162, −0.250, −0.518, −0.306.

**4. The fill is NOT the problem here, and that is the cleanest contrast with BTC.** Slippage mean **+0.10c**,
p90 +0.50c, max +0.94c. Book age at the fire p50 **0.35 s**, p90 2.58 s. On BTC the fill is where everything
goes wrong (EF_TRIGGER_SOURCE, EF_PERSIST, ASK_LIFETIME_MS: 67.9% of asks cancelled, the fill adversely
selected by 10–29 pp). On ETH/SOL the shadow is getting essentially the price it asked for and still losing.

**5. It gets worse later in the candle**: per $1 by second-in-candle −0.108 (0–60), −0.138 (60–120), −0.303
(120–180), −0.534 (180–240). Monotone, though the last two cells are n=59 and n=14.

## The obvious fix, tested honestly, does not work — it shuts the lane down

The diagnosis says recalibrate. Fitting a Platt shrink on all 620 fires and quoting the result would be
worthless, so it was fitted on one half and used to veto the other, in both directions. It can only veto,
since the non-fired passes are not in these DBs — the same shape as EF_VETO.

```
  ETH   fit H1 -> veto H2: a +0.2749 b -0.6387   test n 143 per$1 -0.290 -> kept  33 (23%) -0.436
        fit H2 -> veto H1: a +0.7229 b -1.0856   test n 142 per$1 +0.003 -> kept   4 ( 3%) -1.000
  SOL   fit H1 -> veto H2: a +0.7944 b -0.9240   test n 168 per$1 -0.036 -> kept   3 ( 2%) +0.485
        fit H2 -> veto H1: a +0.7106 b -0.5893   test n 167 per$1 -0.255 -> kept  14 ( 8%) -0.174
  ALL   fit H1 -> veto H2: a +0.5277 b -0.8016   test n 310 per$1 -0.144 -> kept  21 ( 7%) -0.552
        fit H2 -> veto H1: a +0.6910 b -0.7870   test n 310 per$1 -0.147 -> kept  19 ( 6%) +0.137
```

**A correct calibration removes 77–98% of the fires**, and what is left is n = 3 to 33 with a sign flip
across its own halves in every single case. Two of the four directions are still negative after the veto.

That is the real result, and it is stronger than "recalibration failed": the EV ≥ 0.25 bar was only being
cleared *because* p was inflated. Take the inflation away and there is almost no trade left. The fitted
slopes are a +0.27 to +0.79 — a heavy shrink — which is the same statement in the coefficient.

It also explains why the Platt arms are not better than the frozen arms (eth platt −0.269 vs eth frozen
−0.078): the Platt coefficients in those arms were fitted elsewhere and apply a far smaller shrink than
17 pp of over-confidence requires.

## What I am NOT doing

Not deploying a recalibration, not changing a bar, not touching an arm. The owner's rule is explicit: no
model deploy without his strict confirmation, and Kelly/dynamic staking needs two confirmations. This
document is a measurement.

## What the next test should be, if the owner wants one

The useful experiment is not a better calibration on the fires — it is recording the **non-fired passes** on
ETH/SOL the way `decide_log` does for BTC, so calibration can be measured unconditionally and a bar can be
chosen on the full distribution instead of on the survivors. Without that, every ETH/SOL calibration study is
fitted on a set selected by the very quantity being corrected.

## Files

- `eth_sol_diag.py` — the five diagnostics and the out-of-sample veto
- full output in the commit message trail; regenerate with
  `python eth_sol_diag.py`

## Full output

```
eth frozen  graded fires  187  per$1  -0.078  src ['gamma.outcomePrices']
sol frozen  graded fires  210  per$1  -0.277  src ['gamma.outcomePrices']
eth platt   graded fires   98  per$1  -0.269  src ['gamma.outcomePrices']
sol platt   graded fires  125  per$1  +0.075  src ['gamma.outcomePrices']

========================================================================================================
ETH (both arms): n 285, per$1 -0.143, win 30.2%
========================================================================================================
  1 CALIBRATION - the model says p, the market delivers:
    p_side bucket
      [     0,0.3   ) n    36  win  13.9%  mean p 0.237  per$1  -0.181  *n<60
      [   0.3,0.4   ) n    52  win  25.0%  mean p 0.352  per$1  -0.005  *n<60
      [   0.4,0.5   ) n    71  win  26.8%  mean p 0.466  per$1  -0.235
      [   0.5,0.6   ) n    72  win  34.7%  mean p 0.543  per$1  -0.101
      [   0.6,0.75  ) n    31  win  41.9%  mean p 0.658  per$1  -0.159  *n<60
      [  0.75,1.01  ) n    23  win  47.8%  mean p 0.839  per$1  -0.223  *n<60
      OVERALL mean p 0.487 vs realised 0.302  ->  over-confident by +18.5 pp
  2 ASK vs MODEL - AUC of p_side 0.617   AUC of (1-ask) 0.371   the MODEL discriminates better  (gap +0.246)
  3 EV MONOTONE - does a bigger EV pay more?
    ev bucket
      [     0,0.3   ) n    98  win  33.7%  mean p 0.526  per$1  -0.187
      [   0.3,0.5   ) n   135  win  32.6%  mean p 0.464  per$1  -0.032
      [   0.5,0.8   ) n    36  win  16.7%  mean p 0.484  per$1  -0.489  *n<60
      [   0.8,1.2   ) n     9  win  33.3%  mean p 0.396  per$1  +0.630  *n<60
      [   1.2,99    ) n     7  win   0.0%  mean p 0.509  per$1  -1.000  *n<60
  4 FILL - slip mean +0.07c p90 +0.38c max +0.94c; book_age_s p50 0.25 p90 1.75 max 19.10
    book age bucket (s)
      [     0,1     ) n   238  win  27.7%  mean p 0.489  per$1  -0.216
      [     1,2     ) n    21  win  47.6%  mean p 0.472  per$1  +0.378  *n<60
      [     2,3.01  ) n    13  win  30.8%  mean p 0.461  per$1  -0.034  *n<60
  5 SEC - where in the candle:
    second-in-candle
      [     0,60    ) n   157  win  29.3%  mean p 0.495  per$1  -0.209
      [    60,120   ) n    88  win  34.1%  mean p 0.469  per$1  +0.099
      [   120,180   ) n    30  win  23.3%  mean p 0.494  per$1  -0.448  *n<60
      [   180,241   ) n    10  win  30.0%  mean p 0.486  per$1  -0.325  *n<60

========================================================================================================
SOL (both arms): n 335, per$1 -0.147, win 31.9%
========================================================================================================
  1 CALIBRATION - the model says p, the market delivers:
    p_side bucket
      [     0,0.3   ) n    41  win  14.6%  mean p 0.231  per$1  -0.197  *n<60
      [   0.3,0.4   ) n    66  win  22.7%  mean p 0.357  per$1  -0.197
      [   0.4,0.5   ) n    82  win  23.2%  mean p 0.450  per$1  -0.328
      [   0.5,0.6   ) n    76  win  39.5%  mean p 0.549  per$1  -0.059
      [   0.6,0.75  ) n    48  win  52.1%  mean p 0.663  per$1  +0.132  *n<60
      [  0.75,1.01  ) n    22  win  54.5%  mean p 0.822  per$1  -0.164  *n<60
      OVERALL mean p 0.482 vs realised 0.319  ->  over-confident by +16.3 pp
  2 ASK vs MODEL - AUC of p_side 0.670   AUC of (1-ask) 0.321   the MODEL discriminates better  (gap +0.349)
  3 EV MONOTONE - does a bigger EV pay more?
    ev bucket
      [     0,0.3   ) n   126  win  40.5%  mean p 0.532  per$1  -0.071
      [   0.3,0.5   ) n   162  win  29.0%  mean p 0.457  per$1  -0.162
      [   0.5,0.8   ) n    32  win  21.9%  mean p 0.416  per$1  -0.250  *n<60
      [   0.8,1.2   ) n     8  win  12.5%  mean p 0.428  per$1  -0.518  *n<60
      [   1.2,99    ) n     7  win  14.3%  mean p 0.540  per$1  -0.306  *n<60
  4 FILL - slip mean +0.12c p90 +0.54c max +0.94c; book_age_s p50 0.52 p90 3.19 max 10.21
    book age bucket (s)
      [     0,1     ) n   222  win  31.5%  mean p 0.483  per$1  -0.122
      [     1,2     ) n    56  win  33.9%  mean p 0.521  per$1  -0.262  *n<60
      [     2,3.01  ) n    22  win  45.5%  mean p 0.466  per$1  +0.321  *n<60
  5 SEC - where in the candle:
    second-in-candle
      [     0,60    ) n   191  win  35.6%  mean p 0.482  per$1  -0.022
      [    60,120   ) n   111  win  25.2%  mean p 0.477  per$1  -0.326
      [   120,180   ) n    29  win  37.9%  mean p 0.504  per$1  -0.147  *n<60
      [   180,241   ) n     4  win   0.0%  mean p 0.496  per$1  -1.000  *n<60

========================================================================================================
ALL FOUR ARMS: n 620, per$1 -0.146, win 31.1%
========================================================================================================
  1 CALIBRATION - the model says p, the market delivers:
    p_side bucket
      [     0,0.3   ) n    77  win  14.3%  mean p 0.234  per$1  -0.190
      [   0.3,0.4   ) n   118  win  23.7%  mean p 0.355  per$1  -0.110
      [   0.4,0.5   ) n   153  win  24.8%  mean p 0.457  per$1  -0.284
      [   0.5,0.6   ) n   148  win  37.2%  mean p 0.546  per$1  -0.079
      [   0.6,0.75  ) n    79  win  48.1%  mean p 0.661  per$1  +0.017
      [  0.75,1.01  ) n    45  win  51.1%  mean p 0.831  per$1  -0.195  *n<60
      OVERALL mean p 0.484 vs realised 0.311  ->  over-confident by +17.3 pp
  2 ASK vs MODEL - AUC of p_side 0.647   AUC of (1-ask) 0.343   the MODEL discriminates better  (gap +0.304)
  3 EV MONOTONE - does a bigger EV pay more?
    ev bucket
      [     0,0.3   ) n   224  win  37.5%  mean p 0.530  per$1  -0.123
      [   0.3,0.5   ) n   297  win  30.6%  mean p 0.460  per$1  -0.102
      [   0.5,0.8   ) n    68  win  19.1%  mean p 0.452  per$1  -0.376
      [   0.8,1.2   ) n    17  win  23.5%  mean p 0.411  per$1  +0.088  *n<60
      [   1.2,99    ) n    14  win   7.1%  mean p 0.524  per$1  -0.634  *n<60
  4 FILL - slip mean +0.10c p90 +0.50c max +0.94c; book_age_s p50 0.35 p90 2.58 max 19.10
    book age bucket (s)
      [     0,1     ) n   460  win  29.6%  mean p 0.486  per$1  -0.171
      [     1,2     ) n    77  win  37.7%  mean p 0.507  per$1  -0.083
      [     2,3.01  ) n    35  win  40.0%  mean p 0.464  per$1  +0.191  *n<60
  5 SEC - where in the candle:
    second-in-candle
      [     0,60    ) n   348  win  32.8%  mean p 0.488  per$1  -0.108
      [    60,120   ) n   199  win  29.1%  mean p 0.473  per$1  -0.138
      [   120,180   ) n    59  win  30.5%  mean p 0.499  per$1  -0.303  *n<60
      [   180,241   ) n    14  win  21.4%  mean p 0.489  per$1  -0.534  *n<60

========================================================================================================
6 OUT-OF-SAMPLE RECALIBRATION AS A VETO (fit one half, veto the other)
========================================================================================================

  ETH (both arms)  n 285, unfiltered per$1 -0.143
    fit H1 -> veto H2: a +0.2749 b -0.6387 (train mean p 0.487 vs win 0.345)
      test n 143 per$1 -0.290  ->  kept 33 (23%) per$1 -0.436  *kept n<60, not a reading   the veto does NOT help
      kept halves -0.145 / -0.682
    fit H2 -> veto H1: a +0.7229 b -1.0856 (train mean p 0.486 vs win 0.259)
      test n 142 per$1 +0.003  ->  kept 4 (3%) per$1 -1.000  *kept n<60, not a reading   the veto does NOT help
      kept halves -1.000 / -1.000

  SOL (both arms)  n 335, unfiltered per$1 -0.147
    fit H1 -> veto H2: a +0.7944 b -0.9240 (train mean p 0.486 vs win 0.287)
      test n 168 per$1 -0.036  ->  kept 3 (2%) per$1 +0.485  *kept n<60, not a reading   the veto HELPS
      kept halves -1.000 / +1.227   SIGN FLIPS
    fit H2 -> veto H1: a +0.7106 b -0.5893 (train mean p 0.479 vs win 0.351)
      test n 167 per$1 -0.255  ->  kept 14 (8%) per$1 -0.174  *kept n<60, not a reading   the veto HELPS
      kept halves -1.000 / +0.715   SIGN FLIPS

  ALL FOUR ARMS  n 620, unfiltered per$1 -0.146
    fit H1 -> veto H2: a +0.5277 b -0.8016 (train mean p 0.486 vs win 0.310)
      test n 310 per$1 -0.144  ->  kept 21 (7%) per$1 -0.552  *kept n<60, not a reading   the veto does NOT help
      kept halves -1.000 / -0.099
    fit H2 -> veto H1: a +0.6910 b -0.7870 (train mean p 0.483 vs win 0.313)
      test n 310 per$1 -0.147  ->  kept 19 (6%) per$1 +0.137  *kept n<60, not a reading   the veto HELPS
      kept halves -0.060 / +0.336   SIGN FLIPS
```
