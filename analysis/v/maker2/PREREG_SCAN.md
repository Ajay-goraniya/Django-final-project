# M7 - calibration scan with a sealed test half (V, 09-30 12:3x, owner /goal: "a model I can trust that gives profit"). Written BEFORE running.
Data: public Polymarket tape + Binance 1 s, 5,584 BTC 5m candles 09-11..09-30, labels = gamma (venue resolution).
Decision points s in {30,60,90,120,150,180,210,240,270} s; both sides of every candle. Price = last traded price of that side at s (tape,
ts - 2.2 s, mint mirror). COST = price + 0.01 (ask proxy) + 0.01 slippage + taker fee 0.07 c(1-c). $ per $1 = win/cost - 1.
Cells = s x side-price bucket (0.05 wide, 0.05..0.95) x momentum of that side's price over the last 30 s (down <-0.02 / flat / up >+0.02)
x Binance vol regime at the open (calm <0.304 / mid / high >=0.466) x Binance agreement (sign of the Binance move since the open vs the side:
agrees / disagrees / |move|<2 bps). One trade per candle per cell.
TRAIN = 09-11..09-20. A cell is SELECTED only if on TRAIN: n >= 100, $/1 >= +0.03, both train halves > 0.
TEST = 09-21..09-30, untouched until the selection is written to disk. Report: number of cells scanned, number selected, the selected
cells' pooled test $/1, per-day test $, and a null: the same selection rule applied with TRAIN labels shuffled across candles within
(s, price bucket) 200 times -> how often a random selection does as well on test. A model is only "trusted" if the pooled test result is
positive after costs, >= 60% of test days positive, and beats >= 95% of the null draws.

## M7b (written before running): the same scan on ETH 5m (Binance ETHUSDT) and BTC 15m (L=900). Only changes: decision points L/10..9L/10,
momentum look-back L/10, and the vol regime = terciles of that market's trailing 5-min vol computed on TRAIN days only (the BTC 0.304/0.466
cuts are in BTC units). Same train/test split, same selection bar, same null, same "trusted" bar.
