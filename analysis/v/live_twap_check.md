# The settlement line on LIVE money (V, 09-16 10:0x)
Companion to R-22 (2,132 venue-graded candles, 7.7 days: close>=open agrees with the venue 87.05%, TWAP60-vs-TWAP60
96.67%, +9.62 points, positive 9/9 days). This is the same question asked of the 83 live Zurich fills.

| measure on the 83 live fills | value |
|---|---|
| engine's `close >= open` agrees with the venue outcome | 67 / 83 = **80.7%** |
| our side scored by the VENUE (what we are paid on) | 38 wins = **45.8%** |
| our side scored by BINANCE close | 50 wins = **60.2%** |

Two things follow.
1. **A Binance-graded scoreboard overstates us by 14.4 points on the candles we actually traded.** Live PnL is not
   affected - `results.actual` is the venue's own answer and money is booked on it - but any display, replay or
   analysis that reads `candles.actual` is reading the wrong line, and on our own fills it is wrong 19.3% of the
   time rather than the 12.95% base rate.
2. **Our fires concentrate where the two lines disagree.** Base disagreement is 12.95% of all candles; on the
   candles EV chose to trade it is 19.3%. That is R-16's near-tie bleed seen from the other side: a cheap ask is
   most often a candle that is close to the line, and a candle close to the line is exactly where the Binance close
   and the 60 s TWAP part company.
Nothing to change in the engine from this: the retrain on the TWAP line already failed (R-16 retrain, the book
prices the rule), and grading is already correct where it matters. It is a warning about which column to read.
