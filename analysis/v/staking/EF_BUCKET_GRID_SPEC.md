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
