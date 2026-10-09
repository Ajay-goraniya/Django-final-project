# M8 - copy the wallets that keep winning (V, 09-30, owner /goal). Written BEFORE running.
Data: public tape with wallet ids, BTC 5m, 09-11..09-30, gamma labels.
TRAIN 09-11..20: per wallet, its BUY records held to settlement: $/1 = sum((win - p) s) / sum(p s). SMART = wallets with >= 200 BUY
records over >= 50 candles, $/1 >= +0.03, both train halves > 0 (by time).
TEST 09-21..30 (sealed; the SMART list is written to disk first): in each candle, the FIRST BUY by any SMART wallet. We act at its
data-api timestamp + 1 s (the api stamps ~2.2 s after the match, so we are ~3 s behind the wallet). We buy the SAME token at
(last print on that token at our action time) + 0.01 ask proxy + 0.01 slippage + taker fee 0.07 c(1-c); $10; one copy per candle; act only if <= 280 s.
Also: (a) the SMART wallets' own test $/1 (does skill persist at all?), (b) NULL = 200 random sets of the same size drawn from wallets
with >= 200 train BUYs, copied the same way. Trusted = pooled test copy PnL > 0, >= 6/10 test days positive, beats >= 95% of the null.
$100 account at $10 reported with the ruin point.
