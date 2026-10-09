# Morning report 09-28 (V) - what the night found. Details and files are in NC.md NC-13..15.

## 1. EF on Polymarket: no fix makes it profitable, and now we know exactly why
- The BTC 5m market has Polymarket's **taker-order delay ON** (`itode: true`). Our order is held ~50-250 ms; makers cancel inside
  the hold. Speed cannot win this; it is the venue's design.
- The fills we get are **adversely selected**: filled trades win 44%, the ones that do not fill would have won 55% (Zurich, 5 days).
  Raising the fill rate raises it on the losers.
- Tested tonight and CLOSED (numbers in NC-13..15): Predict.fun-style wide caps, EV-bounded chase + retries, waiting for the price to
  hold (persistence), last-minute TWAP lock-in (the market beats exact TWAP math even on the real Chainlink feed), regime switches.
- Two drafts are on the branch, OFF, not deployed: a delay-brain VETO (helps Raw on Zurich, fails on Fixed and on London's real fills)
  and FRESH-BOOK SEND. Zurich's trigger-source test (785k passes) then showed every extra fill on this book is a losing fill, so NEITHER is recommended.

## 2. The 5m/15m TWAP pair: real, but too small (retracted at 05:5x)
The 15m market and its last 5m candle settle on the same Chainlink TWAP, so the right pair pays $1 or $2, never $0. That holds.
But the "under $1" frequency was overstated twice:
- Zurich's books had a stale 15m quote (recorder bug, fixed). With fresh books: **5 of 105** windows, 1-9 seconds each, 1-4c profit.
- My public-trade check mixed prices up to 3 s apart. Buying both legs in the same second at what takers really paid: **1 of 87** windows (09-27).
Zurich's millisecond probe: when it is under $1 it lasts ~43 ms, shorter than our order takes to arrive, on ~10 shares.
So it is a few cents a few times a day. Not a profit engine at our size. The paper bot and code stay on the branch; no live test proposed.

## 3. Also closed overnight
- EF on ETH and SOL (Zurich, 24 h, 4 arms): 3 of 4 negative, the 4th is noise. No.

## 4. Honest answer
No profitable version was found tonight. Every EF fix makes more fills, and on this venue the extra fills are the losing ones.
EF on London: keep or pause is your call; nothing is changed.
