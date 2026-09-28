# Morning report 09-28 (V) - what the night found. Details and files are in NC.md NC-13..15.

## 1. EF on Polymarket: no fix makes it profitable, and now we know exactly why
- The BTC 5m market has Polymarket's **taker-order delay ON** (`itode: true`). Our order is held ~50-250 ms; makers cancel inside
  the hold. Speed cannot win this; it is the venue's design.
- The fills we get are **adversely selected**: filled trades win 44%, the ones that do not fill would have won 55% (Zurich, 5 days).
  Raising the fill rate raises it on the losers.
- Tested tonight and CLOSED (numbers in NC-13..15): Predict.fun-style wide caps, EV-bounded chase + retries, waiting for the price to
  hold (persistence), last-minute TWAP lock-in (the market beats exact TWAP math even on the real Chainlink feed), regime switches.
- Two drafts are on the branch, OFF, not deployed: a delay-brain VETO (helps Raw on Zurich, fails on Fixed and on London's real fills)
  and FRESH-BOOK SEND (London's real orders: fills on a book >=50 ms old lost ~$75 over 5 days, both halves; n53, under the 60 bar).

## 2. The new lead: the 5m/15m TWAP pair (model-free)
The 15m market and the last 5m candle inside it settle on the **same Chainlink TWAP at the same second**, only against different
lines. Buying the right side of each pays $1 or $2, **never $0**. When both asks plus fees cost under $1, the profit is locked in.
- Zurich books, 22.8 h: under $1 in **25 of 81** windows, median 4.4c per pair (up to 27c). 0 zero-payoffs in 725 checks.
- Public trade tape (independent): real buyers bought both legs within 3 s under $1 in **19/91 BTC** and **15/91 ETH** windows;
  pair payoff never 0 on either. SOL, XRP and DOGE have the same markets.
- **Every day for 7 days** (public trades 09-20..26): 13 to 36 BTC windows a day, 22.8% of all windows. One zero payoff in 763 windows,
  caused by lines only $2.33 apart on the Binance proxy; the bot now skips gaps under $5 and uses the real Chainlink feed.
- The one open risk is **both legs filling at once**. A ms probe of both books runs on Zurich until 06:45; the paper bot runs alongside.

## 3. What needs your decision
- A **live micro-test of the pair bot** on London: a separate process, the engine untouched, $5 per pair, one pair per 15m window,
  daily cap. Code: learner/v12_2/pair_bot.py (13 tests). It cannot go live without `--live --owner-confirmed`.
- EF on London: keep as is, or pause it while the pair is tested. Your call; nothing is changed.
