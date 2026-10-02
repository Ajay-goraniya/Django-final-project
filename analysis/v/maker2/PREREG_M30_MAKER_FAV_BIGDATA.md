# M30 PREREG (V, 10-02 21:3x) - owner: "test our London's maker test on it, the one live currently, also fav mid and calm and fav all"
Same idea as M29: every day with a real recorded book, rules FROZEN, nothing tuned. Runs on Zurich (has the data).

DATA: all days with real 1 Hz top of book + trade prints: 09-11..09-16 (book1s/polybook backup) AND Zurich's own recorded
book+tape 09-22 19:30..now. Grade every trade on the VENUE's resolution (Polymarket outcome), never Binance close.

ARMS (frozen, no parameter changes):
 MAKER   = London 13.3.1 rule exactly (maker_probe Quoter.decide): calm vol<0.304, sec 60-120, fav = best BID in [0.60,0.80],
           post-only BUY at bid, cancel only on >=2 bps adverse 1 s / outside 60-120 / candle end, 1 fill/candle, 3 posts, hold.
 FAV     = calm (vol<0.304) taker, as the Zurich shadow (S.* constants, real ask at decision +500 ms, fee 0.07p(1-p)).
 FAV_mid = 0.304<=vol<0.466, same taker rule.     FAV_all = every vol, same taker rule.
MAKER FILL MODEL: report BOTH (a) print strictly through our bid (pessimistic) and (b) print at/through bid (optimistic).
FIDELITY GATE FIRST: on candles where the REAL maker traded (Zurich probe 88 candles, London fills since 15:04), the
simulator must reproduce real fill/no-fill on >=85% - report the number; below that, MAKER results are marked UNRELIABLE.

REPORT (file analysis/zurich/M30_MAKER_FAV_BIGDATA.txt): per arm - n, W/L, $ at $10/trade, per $1, maxDD; PER-DAY table
(owner wants every day positive: count green days / total days, worst day); two time halves; verify.py (sample, halves,
costs +1c, null = buy the favourite at the same second without the vol rule). n<60 = INSUFFICIENT. Full grid, no best cell.
PASS for an arm = positive overall at +1c costs AND same sign both halves AND >=70% green days.
