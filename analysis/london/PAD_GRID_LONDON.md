# Never-filled money + slippage-cap grid, London EF since go-live (V spec 09-26 02:32). READ-ONLY backtest.
(Computed on the London box 09-26 02:35; box has no git creds, V committed the pasted text verbatim.)

Grading: Polymarket resolution (gamma), fee 0.07*p*(1-p) per share at the assumed fill price, stake = each candle's planned budget.
Cap today = signal ask + 1 tick (pad 1), so anything 'reachable at pad 1' was missed by timing, not by the cap.
Book truth available: best ask per second (tape1s) and top-of-book ask/size at each attempt; NO archived depth, so 'size at +k' is unknown.
Halves split at the median EF candle by time.

## ALL: EF candles 259, filled 155, never-filled 104 (graded 104, would-have-won 65)
  (1) if every never-filled had filled at signal ask +1c: +297.06
  (1) if every never-filled had filled at signal ask +2c: +269.83
  (1) if every never-filled had filled at signal ask +3c: +244.20
  (2) filled candles whose attempt-1 top-of-book size < planned shares (could walk the book under a wider cap): 49/155
  never-filled with a best-ask observation in the 3 s after refusal: 104/104
  (3) pad 1 (current): reachable 22/104, would win 12, PnL +11.62 -> net +11.62 INSUFFICIENT
  (3) pad 2: reachable 22/104, would win 12, PnL +11.62 -> net +11.62 INSUFFICIENT
  (3) pad 3: reachable 24/104, would win 12, PnL -3.38 -> net -3.38 INSUFFICIENT
  (3) pad 4: reachable 29/104, would win 15, PnL +3.45 -> net +3.45 INSUFFICIENT
## H1: EF candles 131, filled 79, never-filled 52 (graded 52, would-have-won 34) INSUFFICIENT
  (1) +1c +66.44 / +2c +59.78 / +3c +53.41; (2) thin 17/79
  (3) pad1 13/52 win 8 +26.28; pad2 13/52 win 8 +26.28; pad3 14/52 win 8 +21.28; pad4 17/52 win 10 +26.24
## H2: EF candles 128, filled 76, never-filled 52 (graded 52, would-have-won 31) INSUFFICIENT
  (1) +1c +230.62 / +2c +210.05 / +3c +190.79; (2) thin 32/76
  (3) pad1 9/52 win 4 -14.66; pad2 9/52 win 4 -14.66; pad3 10/52 win 4 -24.66; pad4 12/52 win 5 -22.79

## V's read
No cap lever. The never-filled candles' asks did not come back within 4 ticks in the 3 s after refusal for 75/104 of
them; widening the cap beyond pad 1 adds 0/2/7 candles for ~0/-15/-8. The money "left on the table" (+244..+297) is at
prices that no longer existed. Closes the slippage-cap idea; the only fill lever was speed, and NC-5 closed that.
