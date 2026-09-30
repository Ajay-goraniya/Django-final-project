# M5 STRICT passive FAV, calm only (owner 09-30 ~10:00: "test it strictly, no leakage, fill rate + slippage, $10 stake, $100 account")
Written BEFORE running. Differences from M2 (which chose its price from a real fill = hindsight on price):
1. DECIDE before the fill. At the first second s in [60,180] where the favourite's last traded price (tape, ts-2.2 s, both tokens
   mapped by the mint mirror) is in [0.61,0.81], we post a bid b = that price - 0.01 (one tick under), 1 s later (latency).
   With the real 1 Hz book (09-11..16 only) a second run posts at the book's actual best bid instead.
2. FILL only if the tape TRADES THROUGH our level after the post: a print on our side strictly below b (or on the other token strictly
   above 1-b) before 180 s. Queue position cannot matter then (the whole level was consumed). A looser "touch" fill (>= 14 shares at
   <= b) is reported next to it. Unfilled bids are cancelled at 180 s. Fill rate = fills / posts.
3. SLIPPAGE: a maker pays its bid; a second column pays b + 0.01 on every fill as a cost stress.
4. CALM without leakage: (a) the fixed 0.304 cut (Zurich fitted it on 09-22/23 - those days are marked in-sample for the cut);
   (b) a CAUSAL cut = the 45th percentile of all candle vols over the previous 3 days (first 3 days skipped).
5. $100 start, fixed $10 per fill, stop if equity < $10. Rebates NOT counted. Labels = gamma (the venue's own resolution).
6. Periods reported separately: 09-26..28 = the set M2 was designed on (in-sample); everything else = out-of-sample.
Output: per-day table, total, max drawdown ($ and % of peak), longest losing run, days positive, fill rate, equity chart.
No threshold, band or window is changed after the first run. Whatever it shows is the result.
