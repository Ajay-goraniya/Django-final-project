# EF bucket grid - spec (V, 09-26 02:4x). READ-ONLY. Rain-or-sun rule: buckets fixed HERE, every cell reported.
Owner asks whether fire time, entry price, move size or clock time separate EF's winners from its losers.
Trades: EF fills only, graded on venues.outcome, fees in. London = real fills since go-live; Zurich = EF shadow.
Buckets (fixed before looking):
- fire second into candle: [0,60) [60,120) [120,180) [180,240) [240,300)
- entry price (fill): <0.35, 0.35-0.45, 0.45-0.55, 0.55-0.65, >0.65
- |BTC move open->fire| bps: <3, 3-6, 6-10, >10
- UTC hour block: 00-06, 06-12, 12-18, 18-24
- side: UP, DOWN
Per cell: n, win%, break-even win% at the cell's mean entry (incl. fee), per$1, first-half/second-half per$1 by time.
n<60 = INSUFFICIENT, printed but not read. No cell is "the finding" unless its sign holds in both halves AND on both
venues AND n>=60 on each. Report the whole grid.

## RESULT 09-26 02:4x - NO CELL CLEARS on both venues. Nothing ships, nothing to gate.
- London (155 real fills): no cell n>=60 negative both halves; only UTC 12-18 positive both halves (n74, halves 31/43).
- Zurich (772 shadow fills, grading cross-check 84/84 agree): positive both halves with all sub-cells >=60 = fire second
  [0,60), UTC 06-12, side UP. Negative both halves: none. Zurich's h1 is a losing period and h2 wins in 15/15 cells,
  so "both halves" there collapses to "positive in h1" (the halves() trap).
- Cross-venue: London's UTC 12-18 is not a Zurich survivor; Zurich's UTC 06-12 is NEGATIVE on London (n30). Dead.
  Same sign on both venues but London n<60: fire second [0,60) (Lon n20 +0.246) and side UP (Lon n52 +0.085). Neither
  is a knob EF can turn (fire time is when the move comes), and neither has the sample. Re-read at ~300 London fills.
- Files: analysis/london/EF_BUCKET_GRID_LONDON.md, analysis/zurich/EF_BUCKET_GRID_ZURICH.md.
