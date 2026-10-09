# EF brain v2 - V walk-forward cross-check (09-23 01:4x UTC)

Script: analysis/v/model/ef_brain_v2.py. 1077 graded v10 EF paper fires 09-08..16, venues.outcome, rule fixed before: ev_cal>=0.15, ask<=0.60, $5, engine fee. Each test day fitted ONLY on earlier days (8 test days).

## Read
- No arm beats A (pooled Platt, the live method). B context-aware is worse (+363 vs +474, DD 66 vs 54). C self-adjusting N=400/800 ties A (+546/+488, same DD 53.6); N=100/200 double the drawdown. Nothing ships.
- **Frequency already falls in bad markets under A**: 22 fires/day on its 3 worst days vs 61 on its 3 best - without any gate.
- **CORRECTION to the owner-facing fixed15 numbers**: walk-forward (fitted on past days only) gives maxDD **$53.6 at $5** over 8 days, not the $33 of the in-sample pooled fit. The honest drawdown range for the live setting is $33-54 at $5.

## Output
```
1077 graded fires, 9 days; walk-forward on days 2..9 (each day fitted on the days before it)
A pooled Platt (live method)   n/day  49.9 right  55.1% per$1 +0.238 total  +474.0 maxDD  53.6 run  7 negdays 1/8
B context-aware                n/day  49.5 right  51.8% per$1 +0.183 total  +362.9 maxDD  66.2 run  8 negdays 2/8
C self-adjusting N=100         n/day  70.0 right  50.7% per$1 +0.196 total  +549.3 maxDD 106.1 run  8 negdays 1/8
C self-adjusting N=200         n/day  56.8 right  51.8% per$1 +0.211 total  +479.7 maxDD 110.6 run  8 negdays 1/8
C self-adjusting N=400         n/day  53.9 right  54.3% per$1 +0.254 total  +546.5 maxDD  53.6 run  7 negdays 1/8
C self-adjusting N=800         n/day  49.1 right  55.2% per$1 +0.249 total  +488.4 maxDD  53.6 run  7 negdays 1/8

fires/day on arm A's 3 worst days vs its 3 best days (the "low frequency in bad markets" question):
  A pooled Platt (live method)   worst-3  22.3/day (pnl  +50.0) | best-3  61.0/day
  B context-aware                worst-3  23.3/day (pnl  +76.4) | best-3  65.7/day
  C self-adjusting N=100         worst-3  54.3/day (pnl +135.2) | best-3  87.0/day
  C self-adjusting N=200         worst-3  43.7/day (pnl  +47.1) | best-3  56.7/day
  C self-adjusting N=400         worst-3  36.0/day (pnl +124.4) | best-3  59.0/day
  C self-adjusting N=800         worst-3  20.3/day (pnl  +64.4) | best-3  61.0/day
```
