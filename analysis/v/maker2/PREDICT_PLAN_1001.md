# Predict.fun - owner 10-01 ~20:0x: "start working with predict, it settles on up/down not TWAP" (V)
FACTS FIRST
- We already traded Predict.fun for real on Tokyo 09-09 22:57 .. 09-11 21:52 (learner/live_backup/tokyo_orders.json):
  442 real fills, EF n389 win 52.7% pnl -9.31 (-0.017/$1), REVERSAL n53 +1.27. Halves -5.34 / -2.70. Roughly break-even, old EF build.
- R-31 (h1): Predict fee 2% of shares on WINNERS only, fill 99.5%; cheaper than Polymarket by ~1.5% of stake. Not a fix by itself.
- R-31b: Predict's prices differ systematically from Polymarket's (+10c at cheap asks, -10c at rich asks) - Predict prices the
  Binance-close rule. So Polymarket prices CANNOT be used to price Predict trades.
- NEW (V, 10-01): London's 364 real fixed15 fires 09-23..10-01: win 48.1% on Polymarket's resolution vs 66.2% on Binance
  close>=open (the Predict rule); the two rules agree on only 79.1% of these candles. EF's direction fits Predict's rule far better.
  THE PnL OF THAT IS UNKNOWN: Predict's ask at the fire already reflects the Binance move. Pricing it at Polymarket asks
  (+1514) is the cross-venue grading error CLAUDE.md bans - NOT a result.
PLAN (needs no money, no model change)
P1. Zurich: read-only Predict.fun quote collector (best ask both sides, 1 s) for BTC 5m, plus EF's fire stream (Zurich shadow
    and London's real fires). 48 h.
P2. Price every EF fire at Predict's OWN ask at fire time (+delay ~236 ms measured on Tokyo), 2% share fee on winners,
    graded on Binance close>=open (candles.actual). Train/test halves, null (random side at same asks), full grid by ask bucket.
P3. Only if P2 passes: a small live Predict lane = owner's decision (and Tokyo host is off-limits to sessions - owner chooses the box).
