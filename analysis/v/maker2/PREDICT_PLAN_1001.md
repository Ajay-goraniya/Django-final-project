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

## OWNER 10-01 ~20:1x, relayed by V: "Don't make it live, just paper on Zurich."
**PREDICT.FUN IS PAPER ONLY ON ZURICH.** No orders, no trading key, no live lane. A read-only quote
credential is the ONLY Predict secret that may ever be placed on this box, and it exists solely to
read the book. P3 ("a small live Predict lane") is therefore NOT on Zurich's table at all; if it ever
happens it is the owner's decision and his choice of box, and the Tokyo host remains off-limits to
sessions regardless.
Logged by Zurich 10-01 19:5x. Zurich holds no Predict credential of any kind as of this entry, and
every Predict data path answers HTTP 401 from here (see analysis/zurich/predict/P1_STATUS.txt).

### The paper lane V specified, to run once a READ-ONLY key is in Zurich's environment
Every **C_fixed15** fire (London's model), priced at **Predict's own best ask on that side** at
`fire_ts + 236 ms`; shares = `$5 / ask` **capped by the displayed ask size**; fee **2% of shares on
winners only**; graded on **Binance close >= open** (`candles.actual`), which is Predict's own
settlement rule and NOT Polymarket's resolution. The same fire is ALSO priced at the Polymarket ask
so the two venues can be compared on identical fires - that comparison column is the point of the
exercise, since R-31b showed Polymarket prices cannot stand in for Predict's.
Implemented ready-to-run at analysis/zurich/predict/predict_paper.py. It is NOT validated against
real Predict quotes, because there are none yet; it will be the moment the collector has data.
