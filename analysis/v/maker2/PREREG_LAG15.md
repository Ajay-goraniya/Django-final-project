# M9 - does the BTC 15m market lag the 5m market? (V, 09-30, owner /goal). Written BEFORE running.
In the last 5m sub-candle of a 15m candle E (seconds 630..870 of E), the 15m outcome = sign((close - open_{E+600}) + D), D = open_{E+600} - open_E.
The live 5m market prices P(close >= open_{E+600}) = u5. With X ~ N(mu, s^2), s = sigma * sqrt(900 - t) (sigma = Binance 1 s vol over
[E+300, E+600), bps), mu = s * Phi^-1(u5): FAIR 15m = Phi(Phi^-1(u5) + D / s). Gap = FAIR - u15 (last traded 15m price).
Trade: at the first checkpoint t in {630, 660, ..., 870} with |gap| >= g, buy the 15m side the gap favours at its last price + 0.01 ask
+ 0.01 slippage + fee 0.07 c(1-c); $10; one trade per 15m candle; label = the 15m market's own resolution (gamma).
TRAIN 09-11..20: choose g from {0.03, 0.05, 0.08, 0.12} = best train $/1 with n >= 60 and both halves > 0 (none -> FAIL).
TEST 09-21..30 sealed. NULL: 200 draws flipping each trade's side at random, the flipped side priced at ITS OWN price (1 - u15) + costs.
Trusted = test $ > 0, >= 6/10 test days positive, beats >= 95% of the null. D and sigma use Binance spot as the stand-in for Chainlink.
