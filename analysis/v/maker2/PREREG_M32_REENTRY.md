# M32 (V, 10-03 ~10:3x) - owner's re-entry rule on the maker fills. HISTORY ONLY, exploratory (same ~100 fills as PROBE_EXIT_GRID).
Owner: "Buy (mark this price) - sell at marked price if rise 10% and drops back to marked price - buy it again if goes 10% above
marked price". Then the same with "Binance data so on a first buy we are sure that price will go up most probably".

DATA: Zurich maker probe graded fills (108 fills / 88 candles), the tape prints for exits/re-entries, tape1s Binance 1 s.
Exits/re-buys priced exactly as PROBE_EXIT_GRID (exit at a proven bid print = upper bound; re-buy at the ask / a print at or
above the trigger, taker fee 0.07p(1-p)); prints at sec >= 270 = settlement, not exits. Graded on venue resolution.

RULE A (frozen): entry P = fill price. ARM when price >= 1.10*P. If armed and price falls back to <= P -> SELL at P (bid print).
  After a sell, if price again reaches >= 1.10*P -> RE-BUY (taker at that ask), re-arm with the SAME marked P (not the new price).
  Repeat any number of times until sec 270; whatever is held at 270 is held to settlement.
RULE B (frozen): rule A, but the FIRST buy only counts if Binance moved in our side's direction over the 10 s before the fill
  (spot 1 s return > 0 toward our side). Fills failing that are skipped (not traded).
REPORT: per rule - n, W/L, $ and per $1, vs HOLD on the same fills, number of sell/re-buy cycles, halves, maxDD.
Plus B's skipped fills alone (were the skipped ones the losers?). One rule each, no parameter sweep. In-sample: a pass here is a
hypothesis for London's live fills, not a result.
