# M21 - maker probe: which part of the rule carries it? Judged on LIVE fills only, out of sample. (V, 10-02 10:4x UTC)

Why: M20 (20-day sim) says the probe rule has no edge; Zurich A (PROBE_FILLS_ANATOMY.txt) shows the public tape
cannot resolve our 3 s order lifetimes, so NO sim fill model is validated. The only validator is the probe's own fills.
Zurich C read 97 live fills IN-SAMPLE. These are now predictions, frozen before any further fill is read.

In-sample (97 fills, 76W/21L, to 10-02 10:27 UTC):  sec 60-120 +0.206/$ (n78) vs 120-180 -0.162 (n19);
price 0.60-0.70 +0.22 (n60) vs 0.70-0.80 +0.01 (n37); M19 fair-minus-price <=0 +0.20 vs >0 -0.11 (M19's "bargain" loses);
DOWN +0.25 (n61) vs UP -0.06 (n36) - regime, NO claim.

PREDICTIONS on fills AFTER 10-02 10:27 UTC, evaluated at 200 distinct graded candles (~4-5 days):
 P1 pnl/$ (sec 60-120) > pnl/$ (sec 120-180)
 P2 pnl/$ (price 0.60-0.70) > pnl/$ (0.70-0.80)
 P3 pnl/$ (fair-minus-price <= 0) > pnl/$ (fair-minus-price > 0)   [k=1.4 fair, same code as the paper shadow]
 P4 stop at bid 0.10: winners stopped stays 0  (cheap check; fails on the first winner that touches 0.10)
 Side: reported, no prediction.
PASS for P1-P3: holds out of sample, better level n >= 60, both OOS halves same sign, random-subset null p < 0.05.
If pass -> propose that rule change to the owner (Yes/No). If fail -> probe stays as is. No change without his confirmation.
No cell is read before the 200-candle mark. Zurich reports the whole grid, never the best cell.
