# M19 - fair-value two-sided maker (V, 10-02 00:0x, BEFORE running). Owner /goal: "find the edge, change the strategy".
Idea: price each side from Binance (distance from the opening line, time left, recent vol), rest a post-only BUY on BOTH
tokens at fair - m, refreshed every second; profit = takers selling to us below fair. Not a favourite bet (M5/M10 dead).
DATA: Polymarket BTC 5m public tape 09-23..10-01 (scratch m17/tp_*, venue up_won = settlement truth) + Binance 1 s closes.
FAIR: open line O = mean Binance close over [e, e+60) (proxy of opening TWAP60; before sec 60, running mean).
  p_up(t) = Phi( ln(S_t/O) / (k * sig * sqrt(tau)) ), sig = std of 1 s log returns over the previous 300 s, tau = 300 - t.
  k fitted on TRAIN only (grid 0.6..1.8, max likelihood vs venue outcome at sec 60..270).
QUOTES: bid_up = floor((p_up - m)*100)/100, bid_dn likewise on 1-p_up, using the PREVIOUS second's fair (1 s latency).
  Only when 0.05 <= bid <= 0.90, window sec 30..270. FILL = a print on that token STRICTLY below our bid in that second
  (trade-through, conservative). 5 shares, at most one fill per side per candle, hold to settlement, maker fee 0.
GRID (fixed): m in {0.02, 0.04, 0.06, 0.08, 0.10, 0.15}. Train 09-23..27, sealed test 09-28..10-01 (cell chosen on train).
PASS: test pnl/$ > 0 AND both test halves > 0 AND >= 60 test fills AND beats null (same fills, random side) AND
  calibration check (fair vs outcome, train vs test) reported. Full grid reported. Nothing deployed without owner yes.
