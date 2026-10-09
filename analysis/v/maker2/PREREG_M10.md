# M10 - passive buys of near-certain favourites late in the candle (V, 09-30, owner /goal). Written BEFORE running.
Why: on the public tape (M1b) maker BUY fills at 0.90-1.00 were +0.7%/$1 on $4.2M notional - the one large positive maker cell.
Test = the M5 strict harness unchanged except band [0.90, 0.97] and window 200..285 s (env PF_LO/PF_HI/PF_S0/PF_S1): decide first
(one tick under the last trade), trade-through fills, +1c slippage column, fixed and causal calm cuts AND all-vol (reported), $100/$10.
Trusted = positive on 09-11..30 in the strict (thru, +1c) cell, >= 60% of days positive, no ruin, worst drop < 30% of profit.
