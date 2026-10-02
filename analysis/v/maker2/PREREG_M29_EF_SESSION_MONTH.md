# M29 - does London's EF make money in 13-24 UTC and lose in 00-13 UTC, over a MONTH? (V, 10-02 15:4x, frozen before any run)

Owner 15:4x: "let it run maker at the moment ... but also check our EF finding on a bigger scale ... test it on a month".
The finding: London's REAL fixed-stake EF fills 09-23..10-01 13:07: 13-24 UTC +151.26 (183 fills) vs all hours -84.10 (366)
(analysis/london/EF_FIXED_13_24_PNL.html). It was found by looking at those days, so it must be tested on days it never saw.

STEP 0 - FIDELITY FIRST (CLAUDE.md: verify against the running artifact). Replay London's EF decision code (the 13.2.1 brain that
made those fills, not a re-derivation) over 09-23..10-01 and match London's 366 real fills (analysis/london/M17_FILLS.csv):
same candle + same side on >= 80% of them. If it cannot, STOP and report - no month numbers from a harness that disagrees.
STEP 1 - THE MONTH: every day with data, target 09-01..09-22 (never seen) + 10-02 onward as it arrives. Inputs: Binance 1 s
(data-api.binance.vision), Polymarket public tape for prices, real 1 Hz books where they exist (09-08..16, 09-24..), venue
resolution (gamma) as the label. Entry = next print/ask after the decision + 1c, fee 0.07p(1-p), the fixed stake.
PREDICTION: per $1, 13-24 UTC > 00-13 UTC, AND 13-24 > 0, on the unseen days (09-01..09-22), in both halves of them.
REPORT: per day x session (Asia 00-07, Europe 07-13, US 13-20, Late 20-24), per $1, n, both halves, days positive in 13-24
vs 00-13. Real-book days and tape-priced days reported separately AND together. n<60 flagged. Whole grid, no best cell.
PASS -> V proposes EF 13-24 to the owner as the alternative to the maker lane (his yes in London's terminal).
FAIL -> the session effect is retracted; the 13-24 curve was those days, not the clock.

AMENDMENT 10-02 16:1x (before any run; Zurich stopped correctly at step 0, 16:04):
- THE BRAIN: London's fixed EF fills were NOT poly_ef (the 12.22.0 reversal lane). They are profile 'fixed15' =
  ef_engine 'v10' + Platt (a 1.0677, b -0.3208) + fixed EV bar 0.15 (learner/v12_2/poly_dashboard.py:314), first qualifying pass
  per candle - the FIXED arm of Zurich's own raw_vs_fixed_london_exec.py. v10 = learner/live_backup model, trained 08-29..09-06
  (v10_features_8days.parquet), so every day from 09-08 is out of sample for the MODEL as well.
- THE DATA: no Polymarket ask history exists anywhere for 09-01..09-07. The unseen window that CAN be run on venue asks is
  09-08..09-22 (~15 days): (a) Zurich's own EF decide rows 09-15..09-22 (p_raw + ask at each pass, as used in raw_vs_fixed);
  (b) learner/live_backup book1s/polybook/venues (1 Hz asks, 09-08..09-16) with v10 recomputed from Binance 1 s.
  Not a full month: stated, not hidden. Days 09-23..10-01 remain the fidelity window only, never pooled with the test.
- Prediction, pass rule and report unchanged.

RESULT (Zurich M29_EF_MONTH.txt eaf0f52/c07b234, 10-02 16:36): STEP 0 fidelity 94.6% PASS. STEP 1(A) 09-14..09-22, engine's own
journalled rows, zero reconstruction: FIXED taker 13-24 -0.0947/$ (n94) vs 00-13 +0.0598 (n76); RAW 13-24 -0.1608 (n116) vs
00-13 +0.0841 (n90). Both legs of the prediction FAIL and the sign INVERTS; 13-24 halves -0.18/+0.11; 3/7 days positive.
VERDICT: the EF 13-24 session effect is RETRACTED - the +151 curve (09-23..10-01) was those days, not the clock.
Exploratory (post-freeze): raw is worse than fixed; the ask-touch maker fill is worse than taker (fill 41-46%, adverse:
fixed 85W/85L as taker vs 22W/48L on the filled subset). STEP 1(B) 09-08..16 NOT run (V, 16:3x): (A) is decisive with zero
reconstruction error; (B) would add recompute error to a test that already failed.
