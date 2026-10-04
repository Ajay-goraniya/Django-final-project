# Owner-supplied docs of 20 Sep 2026 — verified against the repo's own data, 21 Sep

Two PDFs: **(1) "EF Market-State Finding"** (a volume_ratio / ef_chop filter on Build11 data) and
**(2) "Adaptive EV + Low-Latency Execution Plan"** (an EV penalty on rv60/ret15/ret60/spot_imb60,
plus an executor-latency plan). Neither doc's source CSVs are in the repo; both were replayed
**verbatim, thresholds frozen**, on data the thresholds were never fit to. Scripts alongside this file.

## Verdict, numbers first

| | claim | replay on repo data | verify.py |
|---|---|---|---|
| Doc 1 filter | −$23.40 → +$41.70 on 1,150 rows | **+$955.81 → +$814.48** on 6,420 rows (8 journals): loses $141. Helps only where raw EF is losing (build11 +46.65, twin_c_thr1 +404), hurts where it is winning (predict_pnl **−634.51**, twin_b_guard −95). | **FAIL** halves (sign flips by journal), sweep (non-monotone, doc's 0.346 is not the peak — 0.45 is), null (loses to "trade everything" and to random p95) |
| Doc 2 EV veto | (no numbers given) | PAPER n=3,034: keeps 18.7%, per-$1 +0.118 → +0.425 but total **+$3,571 → +$2,411** — vetoed set still +$1,160. LIVE n=151: −39.84 → kept 64 at +35.77, vetoed 87 at −75.61. | **FAIL** null (throws away profit); halves "pass" only in that both halves consistently lose money |
| Doc 2 latency | ~300 ms, network- or code-dominated unknown | Live Zurich n=153: total p50 **323 ms** = network **247** + local fire-to-submit **37** + sign 7 + decide 7. Local is already at the doc's 15-30 ms target. | premise half-right, see below |

Both are **gates** (a state filter; an EV/stake modifier). Standing user rule (CLAUDE.md §4): *"No gates. No on/off
gates, stake modifiers, or threshold sweeps on a score already known to be weak."* Task 97's ofi15+pos_in_range
gate — same shape, same mechanism — was already ruled "does not ship" (R-25). Neither of these could ship even
if they had verified. They did not.

## Doc 1 — what is real in it, and what is not

**Real:** the high band is genuinely bad on independent data. `volume_ratio > 1.396`: n=1,359, 50.6% acc,
**−$285**. `ef_chop > 0.539`: n=1,472, 50.3%, **−$7.64** — a coin-flip slice, not a loser.
**Not real:** the low band `volume_ratio < 0.346` is **+$200.67** (n=1,893) — excluding it costs money. Two of the
three thresholds sweep monotone in the "looser is better" direction on unseen data (vol_hi 1.396→3.0: +814→+1216;
chop 0.539→0.8: +814→+1084). The filter is a **frequency cut**, not state selection: it shrinks losses on losing
journals and shrinks gains on winning ones. The doc's "cross-file check" is four cumulative snapshots of one
journal (211 ⊂ 706 ⊂ 1,056 ⊂ 1,150 rows) — the doc says so itself; that is one look, not four.
**Unverifiable from the branch:** the doc's "live" subset (431 rows, −17.42 → +30.84). Every build11-family row
in this repo is `filled=0`, `execution_mode='SHADOW'` (H1_AVAILABLE.md); Tokyo's real fills were never committed.
**Ruled out:** the Task 114 cold-start confound — first-2h rows have ordinary volume_ratio (median 0.37–1.0).

## Doc 2 — strategy half

- Constants are in-sample: activation 1.0450 vs this sample's median activity_stress **1.0687**; rv60 normaliser
  0.327 vs sample mean|rv60| 0.355. `flow_weakness` activation 0.9113 is below the sample median (2.79), so the
  penalty is >0 on **89% of live and 77% of paper fires** — it is not a "stressed conditions" veto, the threshold
  does all the cutting.
- It vetoes **80% of the HIGH-rv60 tercile, which is the best-paying bucket (+0.166/$1)**, and 74–91% of every
  tercile. R-27 (vol regime is not the lever), R-28/R-29 (adapt-style EV adjustments lose total money) stand.
- LIVE looks good in isolation (kept +35.77 both halves, improves all 3 days, beats random at pct 98) — but kept
  n=64, the sample is the one losing stretch, and it is the identical mechanism that "worked" for doc 1 on losing
  journals and failed on winning ones. On the readable sample (paper, n=3,034) it throws away $1,160.

## Doc 2 — latency half, premises checked against `orders.timing_json` (Zurich, 153 live fills)

| stage | p50 | p95 | p99 |
|---|---|---|---|
| fire_to_submit_ms (local) | 36.6 | 766.8 | 1146 |
| sign_ms | 7.1 | 18.2 | 29.0 |
| decision_ms | 6.6 | 85.6 | 115 |
| network_roundtrip_ms | **247.4** | 329.4 | 764 |
| total_attempt_ms | 323.4 | 1035 | 1470 |

- "~300 ms": confirmed. "Network- or code-dominated": already known — **network, 247 of 323 ms.**
- Local hot path is already at the doc's target (37 ms p50); hot signer and no-rebuild-on-fire shipped in 12.9.0.
  The whole local-optimisation section is worth ~20 ms.
- "Move to the lowest-RTT region, target 20–40 ms": Task 96 measured from Mumbai — TCP connect 1.7 ms, TTFB
  165 ms, *"the entire 165 ms is edge→origin→edge behind Cloudflare; the cost is the path to origin."* Region
  choice can take Zurich's 247 to Mumbai's ~165. It cannot reach 20–40 ms; the sub-100 ms milestone is not
  reachable on Polymarket's current path.
- The real tail (fire-to-submit p95 767 ms) is **quote-wait/retry**, not code — and R-21/Task 116 already showed
  the freshness bar, not latency, is what costs money.
- Requested telemetry (`fire_to_submit_ms`, `sign_ms`, `network_roundtrip_ms`, `book_age_ms`, `decision_ms`)
  **already exists** in `timing_json`. The only new item would be user-WS `submit_to_user_ws_event_ms`.
- No measurement in this repo links execution latency to PnL (R-18: price capture loses to the touch; Task 116:
  a 5 s-old book pays the same as a 250 ms one). The plan's premise that speed is worth building for is untested.

## Replay output (verbatim)

### Doc 1
```
=== per db: raw vs frozen filter ===
build11                raw n=1513 acc=51.8% pnl= -31.86 | filt n= 543 (35.9%) acc=54.5% pnl= +14.79 | delta= +46.65 | unmatched=0
predict_pnl            raw n= 896 acc=54.8% pnl=+853.07 | filt n= 345 (38.5%) acc=52.8% pnl=+218.56 | delta=-634.51 | unmatched=0
predict_acc            raw n= 232 acc=79.3% pnl= +82.32 | filt n= 127 (54.7%) acc=79.5% pnl= +46.00 | delta= -36.32 | unmatched=0
twin_b_guard           raw n=1248 acc=53.8% pnl=+192.33 | filt n= 478 (38.3%) acc=54.2% pnl= +96.90 | delta= -95.43 | unmatched=0
twin_c_thr1            raw n=1368 acc=51.0% pnl=-142.58 | filt n= 488 (35.7%) acc=54.5% pnl=+261.91 | delta=+404.49 | unmatched=0
twin_d_auto            raw n= 103 acc=52.4% pnl= -51.52 | filt n=  52 (50.5%) acc=57.7% pnl= +37.46 | delta= +88.99 | unmatched=0
twin_e_combo           raw n=1011 acc=52.3% pnl=+122.42 | filt n= 372 (36.8%) acc=54.0% pnl=+173.28 | delta= +50.86 | unmatched=0
v11_paper_1630-2100    raw n=  49 acc=44.9% pnl= -68.38 | filt n=  18 (36.7%) acc=44.4% pnl= -34.44 | delta= +33.94 | unmatched=0

=== pooled (correlated lanes, n inflated) ===
raw                                n= 6420 W=3433 acc= 53.5% pnl= +955.81
frozen filter                      n= 2423 W=1343 acc= 55.4% pnl= +814.48

=== halves (chronological, per db, filtered set pnl and delta-vs-raw) ===
build11                H1 raw  -15.96 filt  +15.76 (n=250) | H2 raw  -15.90 filt   -0.96 (n=293) | delta H1 +31.72 H2 +14.94
predict_pnl            H1 raw +238.91 filt   +2.52 (n=156) | H2 raw +614.16 filt +216.04 (n=189) | delta H1 -236.39 H2 -398.12
predict_acc            H1 raw  +59.88 filt  +29.48 (n=67) | H2 raw  +22.44 filt  +16.52 (n=60) | delta H1 -30.40 H2  -5.92
twin_b_guard           H1 raw +186.17 filt +101.66 (n=209) | H2 raw   +6.16 filt   -4.76 (n=269) | delta H1 -84.51 H2 -10.92
twin_c_thr1            H1 raw  -28.58 filt +289.76 (n=218) | H2 raw -113.99 filt  -27.85 (n=270) | delta H1 +318.34 H2 +86.15
twin_e_combo           H1 raw +300.68 filt +363.71 (n=160) | H2 raw -178.26 filt -190.43 (n=212) | delta H1 +63.04 H2 -12.18

=== sweep, one threshold at a time, others frozen (pooled) ===
vol_lo    0.15:+272.2/n3373  0.2:+378.9/n3175  0.25:+353.6/n2900  0.3:+500.5/n2643  0.346:+814.5/n2423  0.4:+1058.7/n2194  0.45:+1324.1/n2002  0.5:+1047.0/n1796  0.6:+927.7/n1496
vol_hi    1.0:+516.2/n1980  1.1:+645.1/n2096  1.2:+639.1/n2225  1.3:+752.2/n2330  1.396:+814.5/n2423  1.5:+858.0/n2540  1.7:+977.3/n2681  2.0:+1026.5/n2804  3.0:+1216.4/n3039
chop_max  0.35:+174.8/n955  0.4:+418.9/n1272  0.45:+371.0/n1653  0.5:+545.3/n2113  0.539:+814.5/n2423  0.6:+929.4/n2821  0.7:+1015.0/n3094  0.8:+1083.9/n3157  1.0:+1040.1/n3168

=== nulls at the SAME retention (pooled) ===
frozen filter (37.7% kept)         n= 2423 W=1343 acc= 55.4% pnl= +814.48
top-EV null, same retention        n= 1997 W= 913 acc= 45.7% pnl= -529.21
random-retention null (500 draws, k=2423): median +356.10  p5 -164.07  p95 +980.94  -> filter pnl +814.48 sits at pct 89

=== what the filter removes: volume_ratio bands (pooled raw) ===
vr in [0,0.346)                    n= 1893 W=1015 acc= 53.6% pnl= +200.67
vr in [0.346,1.396)                n= 3168 W=1730 acc= 54.6% pnl=+1040.14
vr in [1.396,99)                   n= 1359 W= 688 acc= 50.6% pnl= -285.01
chop in [0,0.539)                  n= 4948 W=2692 acc= 54.4% pnl= +963.45
chop in [0.539,99)                 n= 1472 W= 741 acc= 50.3% pnl=   -7.64

=== cold-start confound: rows in first 2h of each db, and their volume_ratio ===
build11                first-2h n= 17 pnl= -4.13 vr median=0.78 kept-by-filter=3
predict_pnl            first-2h n= 10 pnl=-24.99 vr median=0.56 kept-by-filter=4
predict_acc            first-2h n= 18 pnl=+10.69 vr median=1.00 kept-by-filter=9
twin_b_guard           first-2h n= 18 pnl= +2.98 vr median=0.50 kept-by-filter=7
twin_c_thr1            first-2h n= 19 pnl=+38.32 vr median=0.70 kept-by-filter=9
twin_d_auto            first-2h n= 20 pnl=+15.29 vr median=0.71 kept-by-filter=12
twin_e_combo           first-2h n= 16 pnl=+37.85 vr median=0.37 kept-by-filter=2
v11_paper_1630-2100    first-2h n= 25 pnl=-11.60 vr median=0.71 kept-by-filter=10
```
### Doc 2
```
rows with full features + ev + outcome: 3185  LIVE=151 PAPER=3034

=== doc constants vs this sample's statistics ===
rv60   doc normaliser 0.327249 | sample mean|x| 0.354698 std 0.396503 median 0.236509
ret15  doc normaliser 2.303539 | sample mean|x| 1.991126 std 2.559645 median 1.052599
ret60  doc normaliser 4.757087 | sample mean|x| 2.385459 std 2.992407 median 1.313531
flow_weakness  doc activation 0.9113 scale 5.7734 | sample median 2.7948 mean 6.5537 std 11.3306
activity_stress doc activation 1.0450 scale 1.6664 | sample median 1.0687 mean 1.5706 std 1.6748

=== doc 2 adaptive-EV veto, replayed at fire time ===
  LIVE   all fires              n=  151 W=  63 acc= 41.7% pnl=   -39.84 per$1=-0.0767
  LIVE   KEPT by adaptive EV    n=   64 W=  35 acc= 54.7% pnl=   +35.77 per$1=+0.1700
  LIVE   VETOED by adaptive EV  n=   87 W=  28 acc= 32.2% pnl=   -75.61 per$1=-0.2446
  LIVE   penalty>0 on 89.4% of fires; median penalty 0.1456, p90 0.5861
  PAPER  all fires              n= 3034 W=1642 acc= 54.1% pnl= +3571.29 per$1=+0.1177
  PAPER  KEPT by adaptive EV    n=  567 W= 319 acc= 56.3% pnl= +2411.19 per$1=+0.4253
  PAPER  VETOED by adaptive EV  n= 2467 W=1323 acc= 53.6% pnl= +1160.10 per$1=+0.0470
  PAPER  penalty>0 on 76.6% of fires; median penalty 0.0405, p90 0.2975

=== what it targets: HIGH-vol / large-move fires, pnl by rv60 tercile (PAPER, the readable sample) ===
  rv60 LOW  n=1011 acc=54.5% per$1=+0.0860  vetoed-by-doc2=916 (91%)
  rv60 MID  n=1011 acc=54.0% per$1=+0.1014  vetoed-by-doc2=745 (74%)
  rv60 HIGH n=1012 acc=53.9% per$1=+0.1658  vetoed-by-doc2=806 (80%)
```
### verify.py gates
```
==============================================================================
FINDING: Doc 1: 0.346<=volume_ratio<=1.396 AND ef_chop<=0.539   (+0.336/fire, n=2423)
==============================================================================
  [FAIL] sample size     under the 60 bar: {'twin_d_auto': 52, 'v11_paper': 18}
  [FAIL] both halves     h1 +46.650 / h2 -634.510  <- SIGN FLIPS, not a finding
  [FAIL] sweep shape     NON-monotone: [ 272.2  378.9  353.6  500.5  814.5 1058.7 1324.1 1047.   927.7]  <- peaks at an interior point, classic overfit
  [FAIL] beats the null  mine +814.480 vs trade everything (raw) +955.810
  [FAIL] beats the null  mine +814.480 vs random same-retention p95 +980.940
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: sample size, both halves, sweep shape, beats the null, beats the null


==============================================================================
FINDING: Doc 2: EV_adj = EV - penalty(flow_weakness, activity_stress)
==============================================================================
  [PASS] sample size     all 4 cells >= 60
  [PASS] both halves     h1 -522.240 / h2 -637.860
  [FAIL] beats the null  mine +2411.190 vs trade everything (PAPER raw) +3571.290
  [PASS] beats the null  mine +0.425 vs top-EV per$1 at same retention (PAPER) +0.357
------------------------------------------------------------------------------
  VERDICT: NOT A FINDING - failed: beats the null

```
*To rerun: gunzip each `learner/live_backup/*.sqlite3.gz` into `/tmp/livecheck/` and run the two scripts here;
doc 2 also needs `all_trades.csv` from the 09-17 export (regenerable from the same journals).*
