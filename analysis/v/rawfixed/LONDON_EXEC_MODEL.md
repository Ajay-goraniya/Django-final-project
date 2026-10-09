# London EF execution model (London box, 09-26 03:54, read-only). Used to re-score Zurich RAW vs FIXED as if on London.
263 EF candles since go-live, 155 filled, graded on Polymarket resolution. Price bucket = attempt-1 signal ask; sec = fire second.

(a) P(candle filled) filled/n | 0-60 | 60-120 | 120-180 | 180-240 | all
<.35    | 4/9  | 13/14 | 10/17 | 3/5  | 30/45
.35-.45 | 8/15 | 24/35 | 16/29 | 13/23 | 61/102
.45-.55 | 9/16 | 13/25 | 12/18 | 10/16 | 44/75
.55-.65 | 3/4  | 4/9   | 5/12  | 3/7  | 15/32
>.65    | 2/2  | 0/3   | 3/3   | 0/1  | 5/9

(b) adverse selection, P(fill | would win) vs P(fill | would lose):
<.35 16/27 59% vs 14/18 78% | .35-.45 33/53 62% vs 28/49 57% | .45-.55 20/39 51% vs 24/36 67% |
.55-.65 8/22 36% vs 7/10 70% | >.65 2/5 vs 3/4 | ALL 79/146 54% vs 76/117 65%  -> winners fill LESS.

(c) filled: fill minus signal ask, cents p10/p50/p90, attempt-1 share:
<.35 n30 0/+4/+10 a1 13/30 | .35-.45 n61 0/+4/+15 a1 42/61 | .45-.55 n44 -1/+2/+11 a1 31/44 |
.55-.65 n15 -9/0/+7 a1 13/15 | >.65 n5 -28/-1/+6 a1 4/5 | ALL n155 -1/+2/+11 a1 103/155

(d) fee per share 0.07*p*(1-p). RAW rule on London's own candles: computable for 166/263, raw also fires 148/166.
Cells mostly n<60: use the ALL rows as the model, per-bucket only as shape.
