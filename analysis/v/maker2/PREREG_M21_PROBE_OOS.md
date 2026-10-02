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

AMENDMENT 10-02 10:4x (before any OOS read; Zurich ack c914a35, armed at 78/200 candles, evaluator refuses to run early):
- In-sample random-subset null: P1 p=0.016, P2 p=0.074, P3 p=0.053. P2/P3 were never significant in sample, so an OOS
  FAIL on them means "was never there", not "reversed". P1 is the only prediction with in-sample support.
- P4 came from the ex-17:00 table; with the 09-30 17:00 candle in, 15 winners touched 0.10. One such candle fails P4 alone.
- Null permutes the bucket label only, never the outcome. Group sizes kept.

## P5-P7 appended by Zurich, 10-02 11:0x UTC, from PROBE_EXIT_GRID.txt (in-sample exploratory)
Owner 10:5x asked for all exit combinations and for stricter rules that allow compounding. The grid
(45 stop x take-profit x trailing cells, exits priced at a PROVEN bid print with no queue or size,
i.e. an upper bound) says the answer is "no exit rule, better entries". Frozen before any OOS fill:
 P5 HOLD BEATS EVERY EXIT CELL. On fills after 10-02 10:27, pnl/$ of hold-to-settlement >= pnl/$ of
    every one of the 45 cells. In sample: 45 of 45 cells lost to hold (best L0.10/U0.95 +0.1123 vs
    hold +0.1232); ex-17:00, 2 of 45 beat it (L0.20 +0.26, L0.10 +7.81 in dollars), both deep stops
    with no take-profit. FAIL if any cell beats hold by more than 0 on the OOS fills.
 P6 CANCELLING ON A BID DIP LOSES MONEY. The fills a 1-tick cancel would have removed have POSITIVE
    pnl/$ out of sample. In sample: 10 fills removed, 9W/1L, +7.63 (+0.2642/$). Same sign at 2 and 3
    ticks. FAIL if the removed fills are net negative.
 P7 MAX ADVERSE EXCURSION SEPARATES, AND THE BANDS STAY ALMOST DISJOINT: median max drop below entry
    is SMALLER for winners than losers, and the winners' p75 stays below the losers' p25. In sample
    winners median 0.21 / max 0.62, losers median 0.64 / min 0.57. This is a post-hoc descriptor,
    NOT a proposed gate - section 3 of the file explains why acting on it is just the deep stop.
Gates for P5-P7: direction holds out of sample, n >= 60 on the better side where a split applies,
both OOS halves same sign, random-subset null p < 0.05 where a two-group gap is being tested.
NOT A PREDICTION, recorded as context: compounding a fixed fraction from $30 on HOLD gave $36 (5%),
$39 (10%), $35 (20%) over all fills, against $49 / $76 / $144 on the sec 60-120 subset, which is the
only subset that never tripped the -10 day stop. That subset is P1 itself, so the figure measures the
same selection twice and is hindsight, not an expectation. No staking change is proposed, and Kelly
or any dynamic staking still needs the owner's two separate confirmations.
