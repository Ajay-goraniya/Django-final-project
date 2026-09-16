# R-30 — BTC-side market state at the candle open → can EF be switched off in a bad state? **No bucket qualifies.**

Script `analysis/h1/r30_btc_state_switch.py`. 1,762 graded Polymarket fires on `venues.outcome` that
have a full, contiguous 24 h of prior BTC candles. State measured from **BTC only, strictly before
the candle opens** — no venue price, no book, nothing from the fire second.

## READ THIS FIRST — the premise does not match the record

The owner's ask is to identify "this Monday and Tuesday" and stop. In this dataset:

| day | weekday | n | per $1 | **total** |
|---|---|---|---|---|
| 09-14 | **Monday** | 291 | +0.281 | **+81.79** |
| 09-15 | **Tuesday** | 188 | +0.297 | **+55.84** |
| 09-16 | Wednesday | 185 | −0.081 | **−15.05** |

**Monday and Tuesday are the two best days in the entire record.** Wednesday is the only losing one.
Live Zurich agrees: 09-15 **+14.11** (n=72), 09-16 **−9.63** (n=11, snapshot ends 08:20).

A switch that turned EF off on Monday and Tuesday would have destroyed +137.63 of the +280.00 total.
Before any state work is acted on, someone has to say **which account lost on Mon/Tue**, because
neither the Polymarket lanes nor live Zurich did. Everything below still stands as the honest answer
to the question as posed — but it is answering it against one losing day, not two.

## Step 0 — the daily table

| day | n | W% | avg ask | per $1 | total |
|---|---|---|---|---|---|
| 09-08 | 46 | 63.0% | 0.454 | +0.282 | +12.99 |
| 09-09 | 136 | 50.7% | 0.451 | +0.078 | +10.58 |
| 09-10 | 159 | 51.6% | 0.441 | +0.127 | +20.27 |
| 09-12 | 442 | 55.0% | 0.467 | +0.162 | +71.41 |
| 09-13 | 315 | 54.3% | 0.469 | +0.134 | +42.16 |
| 09-14 | 291 | 57.4% | 0.442 | +0.281 | +81.79 |
| 09-15 | 188 | 60.1% | 0.455 | +0.297 | +55.84 |
| 09-16 | 185 | 42.7% | 0.444 | −0.081 | −15.05 |
| **ALL** | 1762 | 54.1% | 0.456 | +0.159 | **+280.00** |

Note the avg ask on the losing day (0.444) is the ordinary one. It did not buy differently.

## Step 1 — every feature, every bucket, terciles fixed on the full sample

| feature | LO | MID | HI |
|---|---|---|---|
| ret24 (24 h return %) | +0.116 (n=582) h +0.203/+0.029 | +0.137 (598) +0.110/+0.164 | **+0.224** (582) +0.205/+0.244, p=0.040 |
| rv24 (24 h realised vol) | +0.137 (581) +0.120/+0.155 | +0.175 (598) +0.107/+0.243 | +0.164 (583) +0.256/+0.072 |
| volratio (1 h / 24 h) | +0.173 (582) +0.152/+0.195 | +0.141 (598) +0.078/+0.204 | +0.163 (582) +0.148/+0.178 |
| rangeatr (24 h range/ATR) | +0.085 (582) +0.081/+0.088 | +0.143 (598) +0.120/+0.166 | **+0.249** (582) +0.207/+0.291, p=0.009 |
| autocorr (lag-1, 6 h) | +0.191 (582) +0.159/+0.223 | +0.142 (598) +0.197/+0.088 | +0.144 (582) +0.131/+0.156 |
| samedir (12-candle agreement) | +0.133 (432) +0.144/+0.122 | +0.170 (695) +0.119/+0.221 | +0.164 (635) +0.211/+0.118 |
| posrange (pos in 24 h range) | +0.136 (580) +0.106/+0.166 | +0.137 (600) +0.243/+0.032 | +0.204 (582) +0.135/+0.273 |

Full numbers including permutation p per cell in the script output.

## Step 2 — the switch

**No bucket is negative in both halves at n ≥ 60. All 21 cells are positive on the full sample, and
every one is positive in at least one half.** There is nothing to switch off, so steps 2 and 3 have
no candidate to simulate. Not "the switch is small" — the switch does not exist.

The two cells that stand out do so in the *opposite* direction: `rangeatr` HI (+0.249, p=0.009) and
`ret24` HI (+0.224, p=0.040). Those are "fire **more** here" cells, not "turn off" cells, and I am
not proposing them: 21 cells were tested, so p=0.009 is ≈0.19 after Bonferroni, and the owner's
standing rule forbids a gate built on a sweep like this.

## Step 3 — the losing day's state was not distinctive

| day | ret24 | rv24 | volratio | rangeatr | autocorr | samedir | posrange |
|---|---|---|---|---|---|---|---|
| 09-10 (+20) | −1.504 | 11.260 | 0.739 | 18.328 | +0.015 | 0.583 | 0.196 |
| 09-15 (+56) | −1.162 | 11.556 | 0.704 | 26.103 | −0.051 | 0.583 | 0.097 |
| **09-16 (−15)** | **−1.499** | **16.342** | 0.558 | 18.327 | −0.022 | 0.583 | 0.341 |

09-16's 24 h return (−1.499) is a near-copy of 09-10's (−1.504), which made +20.27. Its only
distinctive reading is the highest rv24 in the set — but the rv24 HI bucket is **+0.164 overall and
positive in both halves**, so high 24 h vol is not the marker. There is no state here that picks out
the bad day without also picking out good ones.

## Limits, stated

1. **One losing day.** Any "state that identifies bad days" fitted on n=1 day is fitted, full stop.
   The honest test needs more losing days, not more features.
2. `samedir` is discrete (12 candles → 13 values), so its terciles are uneven (432/695/635) and its
   median is 0.583 on *every* day — it carries almost no cross-day variation and should be read as
   the weakest of the seven.
3. 1,762 of 2,080 fires survive the 24 h contiguity requirement; 09-11 is absent from the record.
4. Paper fills at the quoted ask are an upper bound and are not comparable to live fills.
