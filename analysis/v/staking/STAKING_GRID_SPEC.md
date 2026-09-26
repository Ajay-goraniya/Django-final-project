# Dynamic staking grid - spec (V, 09-26 01:xx). BACKTEST ONLY.
Owner asked for dynamic staking that beats fixed on profit AND drawdown. Live staking changes need the owner's
TWO separate confirmations (CLAUDE.md). Nothing here touches any engine.

## Why the earlier attempts died (do not repeat)
R-4/R-5/R-6 sized on the model's confidence p / EV. p is overconfident (0.65-0.70 bin delivers 56%) and after
correction beats the venue price by ~1% Brier - nothing to amplify. Rule: NO stake rule below reads p, EV or any
model score. Stakes may only depend on money state, entry price, or market state.

## Trades
EF only, same trades in every arm (paired, no arm may skip a trade: min stake 3, max 50 = engine limits).
- London: real live EF fills since first go-live, graded on venues.outcome, fee included.
- Zurich: EF shadow journal (paper fills at quoted ask - caveat: no refusal cost).

## Arms (all normalised to the SAME total capital deployed as baseline A, so none wins by betting more)
A fixed $ (current)
B bankroll %: stake = f x equity, f in {2,4,6,8,10,15}% (report un-normalised too - this one is meant to compound)
C fixed shares: stake = N x entry price
D fixed win target: stake proportional to entry/(1-entry) (equal win amount per trade)
E cheap-entry tilt: stake proportional to (1-entry)
F equity-curve de-risk: half stake while equity < its MA(k), k in {10,20,40} trades
G volatility scaled: stake proportional to 1/sigma(BTC 1h realised, known before the fire)

## Report (full grid, never the best cell)
Per arm: total PnL, maxDD, PnL/maxDD, first-half/second-half by time, worst day. Parameters for B/F picked on the
first half only, scored on the second. Mark anything under 60 trades INSUFFICIENT. An arm "wins" only if it beats A
on BOTH total PnL and maxDD on the second half, on BOTH London and Zurich.

## RESULT 09-26 01:1x - NOTHING SHIPS. Fixed $ stays.
- London (153 live EF fills, H2 n=77): no arm beats A on both H2 PnL and maxDD. E closest (more PnL, DD +1.2 worse);
  F MA20 less DD but less PnL; F MA40 and B lose PnL. File on the London box only (no git creds there).
- Zurich (765 shadow fills, H2 n=490, per $ deployed): only F de-risk MA(40) beats A on both - but the fit half was a
  straight EF loss, equal capital drifts inside H2, shadow has no refusal cost, EF edge never passed permutation.
  analysis/zurich/STAKING_GRID_ZURICH.md.
- F (half stake while equity < MA) is the only CANDIDATE: wins on Zurich, fails the both-venues rule on London.
  Re-run on London once it has ~300 live fills (about 3 more days). Live use needs the owner's two confirmations.
