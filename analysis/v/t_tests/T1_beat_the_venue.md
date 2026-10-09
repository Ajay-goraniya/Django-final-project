# T1 — can a direction model on the correct ruler beat the venue price? **NO.** 2026-09-21 (V)

Setup: 2,049 candles 09-08 → 09-16, 10 offsets each (15…240 s) = 19,214 rows. Features measured from the TWAP60
settlement line (T0): move_line, ref_gap, ret5/15/30/60, rv60, range, pos_in_range, taker imbalance 15/60 s,
prev1/prev2, sec_left, hod, mv_x_sec; model B adds p_venue, lv, lv_x_sec. L2 logistic (C=0.3), standardized,
**walk-forward by day**: fit on all prior days (≥3), test the next day; 12,962 test rows over 09-11 → 09-16.
Label `venues.outcome`. Fee 1.67% of shares. Venue quote = `venues.q` at that second (≤10 s old; a stale cheap
quote can only flatter the model, so the result below is an upper bound).

| forecaster | Brier | direction acc |
|---|---|---|
| venue price alone | **0.1671** | **0.7480** |
| model, BTC features on the settlement line | 0.1773 | 0.7372 |
| model, BTC + venue price | 0.1680 | 0.7453 |

Discordant candles only (model B vs venue), McNemar per offset: model right/venue wrong vs venue right/model wrong —
15 s 61/71 p=.43; 30 s 37/57 **p=.049 (venue wins)**; 45 s 48/51; 60 s 34/49 p=.12; 90 s 25/23; 120 s 19/21;
150 s 17/16; 180 s 25/22; 210 s 12/7; 240 s 11/7. No offset favours the model.

Trading, one trade per candle, buy side when p·(1−fee) − ask > margin, per $1 after fee, H1|H2:
| margin | model B n / hit / per$1 / halves | BTC-only | venue p alone |
|---|---|---|---|
| 0.00 | 1376 / 55% / −0.047 / −0.057|−0.037 | 1384 / 46% / −0.031 / −0.073|+0.011 | 301 / 30% / +0.079 / +0.409|−0.162 |
| 0.02 | 1139 / 56% / −0.045 / −0.032|−0.059 | 1378 / 46% / −0.010 | 46* |
| 0.05 | 476 / 55% / +0.000 / −0.018|+0.022 | 1322 / 43% / −0.044 | 11* |
| 0.08 | 145 / 48% / +0.030 / −0.079|+0.168 | 1158 / 39% / −0.052 | 5* |
| 0.12 | 57* / 49% / +0.350 | 871 / 36% / −0.069 | 2* |
Nulls: shuffled predictions within offset −0.078 (p95 −0.052) — the model carries information; cheapest side ≤0.45 −0.103.
Model B at ask 0.40: hit 34% (n=38), breakeven 40.7%. Venue-alone calibration (T1 baseline): cheap side at 0.40 wins 34–38% in every second bin.

verify gates: grading ✓ (own venue oracle) · sample ✓ (main cells ≥60) · **halves ✗** (no cell positive in both) · permutation ✓ · **null: beats dumb nulls, does not beat zero** · costs: fee only, no slippage (would worsen) · quote_age: ≤10 s tolerance (flatters). **Verdict: FAIL.**

## What this means
- Fixing the ruler removes the 11.6% label noise (T0) but does not create a forecast the venue does not already have.
  R-13 said this for the live v10 on Binance features; it holds on the settlement line too. Direction is not the lever.
- Paper's +0.24/$1 (Mumbai 8795, 527 fills) is not contradicted: it is filled at the quoted ask with no adverse
  selection. Live filled 41% at the touch and paid +1c (R-18/R-3), and lost. T1 says the quote, not the call, is the edge
  in paper, and the quote does not survive contact with the book.
- Caveats that could reopen T1, none expected to flip it: perp/depth/OFI features absent offline (v10 had them and still
  matched the venue, R-13); 3–8 training days; logistic only (R-12 showed history and bigger models did not help).

## Plan consequence: §5, not §3
No new direction model. Work goes to (a) price-paid vs settlement probability by second (T2 on the correct ruler, live
fills as the check), (b) execution: what fills and at what price, (c) venue fee/fill structure. Owner decides.
Scripts: scratchpad `t0/t1_build.py`, `t0/t1_walk.py`. Token budget T0+T1: ~90k.
