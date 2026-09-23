# REVERSAL by seconds-into-candle (V, 09-23 23:2x) - owner: "test Reversal ... only trades before 200 seconds"
Polymarket: lanes_twap60 replay (8 days, 459 graded REVERSAL, settlement-line open, exact fee 0.07p(1-p), graded venues.outcome).
Predict.fun: Mumbai 8796 paper, 43 graded (recorded pnl/spent) - every cell n<60, insufficient.

| Polymarket bucket | n | right | per$1 | w/o top3 | H1 | H2 |
|---|---|---|---|---|---|---|
| <200 s | 323 | 64.4% | +0.144 | +0.063 | +0.116 | +0.173 |
| <240 s | 394 | 67.8% | +0.215 | +0.144 | +0.113 | +0.318 |
| all | 459 | 65.1% | +0.435 | +0.173 | +0.113 | +0.756 |
| 0-60 | 36* | 66.7% | +0.098 | -0.016 | | |
| 60-120 | 123 | 62.6% | +0.077 | +0.001 | +0.080 | +0.074 |
| 120-180 | 119 | 65.5% | +0.202 | +0.014 | +0.040 | +0.362 |
| 180-200 | 45* | 64.4% | +0.213 | -0.056 | | |
| 200-240 | 71 | 83.1% | +0.538 | +0.304 | +0.355 | +0.716 |
| 240-300 | 65 | 49.2% | +1.769 | -0.034 | | (one 0.010 ticket) |

Live executor already refuses REVERSAL orders after 240 s, so "<240" is what London would trade. The 200-240 s bucket is the
strongest cell; a <200 cut removes it. Gates (permutation / null) NOT run: this is a grid, not a finding.

## Gates (analysis/v/model/rev_verify.py -> analysis/h1/verify.py), same replay, exact fee
| window | n | per$1 | w/o top3 | halves | permutation p | +5c | beats cheap-side null | losing days |
|---|---|---|---|---|---|---|---|---|
| 0-240 s | 394 | +0.215 | +0.144 | +0.113/+0.318 | 0.001 PASS | +0.086 | +0.215 vs +0.114 PASS | 1/9 |
| 0-200 s | 323 | +0.144 | +0.063 | +0.116/+0.173 | 0.042 FAIL | +0.027 | +0.144 vs +0.145 FAIL | 3/9 |
| 200-240 s | 71 | +0.538 | +0.304 | +0.355/+0.716 | 0.000 PASS | +0.354 | +0.538 vs -0.028 PASS | 1/9 |
Grading: replay actual == venues.outcome 394/394. 0-240 and 200-240 pass every gate; 0-200 fails two.
Limits: replay prices every call at the 1 Hz tape ask with a guaranteed fill (live FAK refusals ~40-60% of first tries);
no depth features; quote_age not gated. Zurich live shadow REVERSAL is far weaker so far: 32 fires +0.034 (21:30).
