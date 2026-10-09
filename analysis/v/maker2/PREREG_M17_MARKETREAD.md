# M17 - London fixed15: can the MARKET READ at the fire tell a winning fire from a flat-candle loser? (V, 10-01 13:1x, BEFORE any data)
Owner 10-01: "how can flat candles be solved? if not, see the winning candles and how they can be identified and captured".
Already closed (do not redo): pre-open vol/activity (M13), pre-open flat model AUC 0.645 -> no P&L (M15), 7 single fire-time
features incl. distance-from-line, momentum 5/15 s, rv60, ask, sec, basis (M14). Spotting winners = spotting losers (same split).
NEW here: what the market did INSIDE the candle, from the open up to the fire second (strictly <= fire_ts, no look-ahead):
  F1 chop      = |Binance net move open->fire| / sum of |1 s moves| open->fire   (low = choppy = skip)
  F2 activity  = share of seconds open->fire with a Binance price change           (low = quiet = skip)
  F3 venue     = Polymarket prints in the candle up to the fire (count)            (low = quiet = skip)
  F4 agree     = our-side token price change over the 30 s before the fire          (against us = skip)
  F5 brain     = logistic on F1..F4 fitted on TRAIN only, scored on TEST           (lowest p(win) = skip)
DATA: London's real fixed15 EF fills 09-23..10-01 (per-fill fire_ts, side, ask, stake, pnl; venue resolution) + Binance 1 s + PM tape.
RULES: skip worst 10/20/30% of each feature, direction fixed above. 15 cells. Cut points set on TRAIN.
WALK-FORWARD: train 09-23..27, sealed test 09-28..10-01, read once.
PASS (all on the sealed test): $ lost cut >= 5%, PnL >= baseline, skipped fires net negative, train halves agree,
verify: sample (>= 60 skipped), paired, null (random skips of the same count, p < 0.05). Full grid reported, never the best cell.
Also reported (descriptive, not a rule): win% and $ by candle |move| tercile for fired vs all candles - are winners being missed?
NOTHING is deployed. A pass goes to the owner as a proposal needing his confirmation (no gates rule: owner asked for this test).
