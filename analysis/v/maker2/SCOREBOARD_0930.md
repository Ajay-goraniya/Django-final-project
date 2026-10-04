# Owner /goal 09-30 "a model I can trust that gives profit" - every test run today, strict, pre-registered, unseen days
| # | idea | result |
|---|---|---|
| M3 | both-sides bids before the open (owner idea) | loses in all 20 cells |
| M5 | passive FAV calm, strict (decide first, trade-through, +1c, $100/$10) | -335 / -778 over 20 days; broke |
| M6 | taker FAV / FAV_mid / FAV_all, strict 20 days | +20 / -556 / -1428 at +1c; broke |
| M4 | regime switching (walk-forward) | worse than not switching |
| M7 | 3,008-cell sealed calibration scan, BTC 5m | test -0.09/$1, null p 0.60 |
| M7b | same, ETH 5m / BTC 15m | -0.088/$1 null p 0.89 / nothing passes train |
| M8 | copy wallets that kept winning (3 s late) | -0.098/$1, 0/10 test days |
| M9 | BTC 15m lags the 5m market | negative on train at every threshold |
| M10 | passive late buys of 0.90-0.97 favourites | broke in every cell |
Only untested structure: a maker that cancels within milliseconds (what winning makers do). Needs tiny real post-only orders to measure.
