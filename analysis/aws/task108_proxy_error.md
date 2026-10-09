# Task 108 - how wrong is the Binance TWAP60 proxy for the Chainlink settlement line?
Measured by Mumbai on its own box (the ref_stream file cannot be pushed: no git credentials there), window
2026-09-16 01:44-09:29 UTC, 7.80 h, 26,993 seconds carrying both series. V commits the numbers verbatim.

1. LEVEL. |chainlink - binance spot| n=26,993: median 8.4 bps, p90 9.3, max 18.6.
   |chainlink - TWAP60(binance)| n=26,952: median 8.3, p90 10.8, max 18.4.
   Binance is ABOVE Chainlink in 100.0% of seconds on both measures - a persistent BTC/USDT-vs-USD-aggregate
   basis, not noise.
2. DIRECTION, per candle, TWAP60(close) vs TWAP60(open), epochs fully covered and present in venues.outcome, n=72:
   (proxy,chainlink) = (UP,UP) 39, (DOWN,DOWN) 32, (UP,DOWN) 1, (DOWN,UP) 0.
   chainlink vs venue 72/72; proxy vs venue 71/72; proxy vs chainlink 71/72. The single discordant candle has
   chainlink right and the proxy wrong. n=72 supports the agreement rate; the DISAGREEMENT rate is INSUFFICIENT -
   one flip is not a probability.
3. COVERAGE. 89 epochs in the window had a venue outcome; 15 touched one of the logger's 30 gaps and were dropped
   (a gap at the open or close second breaks the TWAP); 74 clean, 72 with all four TWAPs computable at >=45 of 60 s.
4. VERDICT. Safe for DIRECTION, not for LEVEL. The 8.4 bps basis is one-sided, so it cancels in close-minus-open;
   what can flip a call is the error in the MOVE - median 0.22 bps, p90 0.68, max 1.02 - against a typical candle
   move of 5.4 bps (p10 1.1). Error budget ~1 bps against a ~5 bps signal: comfortable in the middle, marginal on
   the smallest tenth of candles, which is exactly where the one observed flip sits. Do not substitute the proxy
   for the settlement LEVEL.
