# NC - New Changes (owner's list)

Findings the owner asked to record. Nothing here is deployed on London (eu-west-2) without the owner's
confirmation of that specific change (CLAUDE.md rule, 09-23).

## NC-1 - REVERSAL on Polymarket: trade only up to 240 s into the candle (09-23)

- **Why:** Polymarket settles on TWAP60 (average of the last 60 s vs the 60 s before the open), not on the plain
  candle close. A reversal that happens in the last minute only moves part of that average, so late REVERSAL
  bets stop paying. Predict.fun settles on the plain candle, so it is not affected the same way.
- **Result (8-day Polymarket replay, exact fee, graded on Polymarket's own outcome):**

  | window | trades | per $1 | w/o top 3 | all checks | losing days |
  |---|---|---|---|---|---|
  | 0-240 s | 394 | +0.215 | +0.144 | PASS (shuffle p=0.001, beats cheap-side null) | 1 of 9 |
  | 0-200 s | 323 | +0.144 | +0.063 | FAIL (shuffle, null) | 3 of 9 |
  | 200-240 s | 71 | +0.538 | +0.304 | PASS | 1 of 9 |
  | after 240 s | 65 | about -0.03 without one lucky 1c ticket | | | |

- **Meaning:** keep REVERSAL's trades up to 240 s; do not cut at 200 s (200-240 s is its best window);
  never trade it after 240 s. London's order engine already refuses orders after 240 s, so no code change is needed.
- **Limits:** the replay assumes every order fills (live, 40-60% of first tries are refused). Zurich's live
  shadow REVERSAL is weaker so far (32 trades, +0.034/$1) - confirm at 60 trades before any live use.
- **Status:** tested on replay, not deployed. REVERSAL stays OFF on London.
- **Full grid (every bucket, Polymarket replay, 459 graded REVERSAL):**

  | bucket | n | right | per $1 | w/o top 3 |
  |---|---|---|---|---|
  | 0-60 s | 36 (<60) | 66.7% | +0.098 | -0.016 |
  | 60-120 s | 123 | 62.6% | +0.077 | +0.001 |
  | 120-180 s | 119 | 65.5% | +0.202 | +0.014 |
  | 180-200 s | 45 (<60) | 64.4% | +0.213 | -0.056 |
  | 200-240 s | 71 | 83.1% | +0.538 | +0.304 |
  | 240-300 s | 65 | 49.2% | +1.769 (one 0.010 ticket) | -0.034 |

  0-240 s by day: 09-08 -0.153 | 09-09 +0.032 | 09-10 +0.176 | 09-11 +0.255 | 09-12 +0.846 | 09-13 +0.643 |
  09-14 +0.283 | 09-15 +0.067 | 09-16 +0.043. Costs: +1c +0.185, +2c +0.157, +5c +0.086.
  Predict.fun (Mumbai 8796): 43 trades, too few to compare.
- **Reproduce:** `python3 analysis/v/model/rev_verify.py --rows lanes_twap60.csv --venues venues.sqlite3 --lo 0 --hi 240`
