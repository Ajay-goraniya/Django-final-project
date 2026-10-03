# M33 PREREG (V, 10-03 ~10:4x) - owner: "test on big scale". The Binance 10 s direction filter from M32, on every big dataset.
M32 (in-sample, 108 maker fills): holding only fills where Binance spot moved our way in the 10 s before entry gave +0.18/$ vs
+0.03/$ for the rest, half the drawdown, 2/3 green days. Maker fills cannot be simulated at scale (M30 gate failed), so the
big test is on TAKER entries at real asks, graded on venue resolution, same harnesses as M29/M30.

FILTER (frozen): at the decision second, spot BTCUSDT 1 s return over the prior W seconds is > 0 in OUR side's direction.
W = 10 is the hypothesis; W = 5 and 30 reported beside it (full grid, no best cell).
ARMS, each FILTERED vs UNFILTERED on identical candles (paired - only the candles the filter removes carry information):
 1. FAV calm, FAV_mid, FAV_all - M30 data (venues.q 09-08..16 + tape1s 09-22..now, ~19 days, real ask +500 ms, fee).
 2. EF fixed15 and RAW25 taker - M29 data (15 days), journalled/reconstructed p, same harness.
REPORT per arm x W: n kept / removed, $@10, per $1, maxDD, worst trade, per-trade std, green days, both halves; and the REMOVED
group alone (its per $1). PASS for the filter on an arm = kept beats unfiltered per $1 AND the removed group is negative or ~0
AND same sign both halves AND kept green days >= unfiltered. n < 60 = INSUFFICIENT. File: analysis/zurich/M33_BN_FILTER_BIG.txt.
