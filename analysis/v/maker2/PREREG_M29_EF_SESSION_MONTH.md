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
