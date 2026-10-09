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

---

# R-30b LIVE — the owner is right, and the reason is the fee, not the regime

Script `analysis/h1/r30b_live.py`. **Snapshot is stale:** `learner/live_backup/zurich_2.sqlite3.gz`
is the 09-16 09:11 push (commit `e6b9927`). No newer Zurich gz and no per-day venue table has landed
on the branch, so live coverage ends **09-16 08:20 UTC** — today is only part-counted.

## The finding, and it is a correction of my own numbers

The live journal carries **two** PnL columns and they differ by the fee:

`pnl − venue_pnl − venue_fees == 0` on all 83 rows, max residual 1e-4. **`pnl` is GROSS.
`venue_pnl` is what the account actually received.** Everything I reported to the owner earlier
today came off `pnl`, which is why I said 09-15 was +14.11. **It was not. It lost.**

| | 88 settled live fires |
|---|---|
| gross (`pnl`) | **−1.69** |
| venue fees | **13.61** |
| **net (`venue_pnl`)** | **−15.30** |

Total staked 339.55, so **fees are 4.01% of stake** while the **gross edge is −0.50% of stake**.

**The fee is charged on losers too:** winners pay 3.92% of stake (n=39), losers 4.08% (n=49). The
paper model `per1()` charges 7% of *winnings* and **nothing on a loss**. So every paper per-$1 figure
in this repository — including every arm I graded in R-26 through R-29 — is measured against a cost
structure the live venue does not use. On live the cost is a flat ~4% of stake per fire, win or lose.

That is the whole gap between "paper says +0.159/$1" and "the account went 50 → 40".

## Step 1 — the LIVE daily table (venue_pnl)

| day | n | W% | venue_pnl | venue_fees | cumulative |
|---|---|---|---|---|---|
| 09-15 | 77 | 46.8% | **−4.33** | 12.27 | −4.33 |
| 09-16 | 11 | 27.3% | **−10.97** | 1.35 | **−15.30** |

**Losing days from the live table: 09-15 AND 09-16 — both of them.** The owner said he lost on both.
He did. My R-30 daily table said Mon/Tue were the two best days; that table was paper, and on the
paper fee model. Retracted for any live purpose.

## Step 2 — the seven state buckets on live fires (terciles frozen from R-30, not refitted)

88 of 88 live fires have a full 24 h of prior BTC candles. Four cells reach n≥60:

| feature.bucket | n | net/fire | net total | halves | share of live |
|---|---|---|---|---|---|
| ret24.LO | 71 | −0.5833 | −41.42 | **+0.285 / −1.428** | 81% |
| rangeatr.HI | 60 | −0.5074 | −30.44 | **+0.867 / −1.882** | 68% |
| samedir.MID | 60 | +0.0601 | +3.61 | **+1.743 / −1.622** | 68% |
| posrange.LO | 76 | −0.0118 | −0.90 | **+1.499 / −1.522** | 86% |

**All four flip sign between halves**, and each holds 68–86% of the entire live sample. A bucket
containing five sixths of the data is not a detector, it is the data — what these four are measuring
is that the second half (09-16) lost. Live spans ~30 h, so both halves sit inside one contiguous
window, which this repo already records as nearly worthless. The other 17 cells are under 60 and are
not read.

## Steps 3 and 4 — no switch, and no detector

**No bucket qualifies.** Where the two live losing days actually land, scored on the big paper
sample, all 14 checks:

| day | the bucket it sits in | paper n | paper per $1 |
|---|---|---|---|
| 09-15 | ret24.LO / rv24.MID / volratio.MID / rangeatr.HI / autocorr.HI / samedir.MID / posrange.LO | 580–1108 | +0.116 … +0.245, **all positive** |
| 09-16 | ret24.LO / rv24.HI / volratio.MID / rangeatr.MID / autocorr.HI / samedir.MID / posrange.MID | 583–1108 | +0.116 … +0.189, **all positive** |

**Every single bucket the losing days fall into is positive on the large sample.** That is the
answer to "can we identify this state and stop": **no detector exists** in these seven features.
Step 4 does not run — nothing qualified.

## What this changes

The regime question was the wrong question. At 4% of stake per fire charged win or lose, the engine
needs a gross edge above 4% of stake to break even; it is currently running at **−0.50%**. No state
switch, threshold, or model change in this repo addresses a flat per-fire cost — only firing less
often, firing larger, or a venue with a different fee schedule does.

**Recommended next measurement, not a change:** re-grade R-26…R-29 arms under the live fee model
(4% of stake per fire, both outcomes) instead of `per1()`, and report which, if any, is still
positive. I expect most are not. I am not proposing any live change off this file.

---

# R-30c — CORRECTION to R-30b. A fresh Zurich journal landed; the numbers got worse, and the *reason* changed.

`zurich_2.sqlite3.gz` was refreshed (hash `7916cff4…` → `e569b5ce…`), extending live coverage from
09-16 08:20 to **09-16 23:25**. Coverage is now read from the journal, not asserted — see the two
stale-literal fixes at the bottom.

## The live table, full days

| day | n | W% | venue_pnl | fees | staked | cumulative |
|---|---|---|---|---|---|---|
| 09-15 | 77 | 46.8% | −4.33 | 12.27 | 307.56 | −4.33 |
| **09-16** | **38** | **28.9%** | **−41.54** | 4.47 | 109.81 | **−45.87** |
| **total** | **115** | 40.9% | **−45.87** | 16.73 | 417.36 | |

09-16 was far worse than the part-day showed: **n=11 → 38 fires, −10.97 → −41.54**, win rate 28.9%.
Cumulative **−45.87** on 417.36 staked. This is the owner's 50 → 40, and then some.

## What I got wrong in R-30b, stated plainly

R-30b reported live **gross −0.50% of stake** and concluded *"the fee is the problem; the gross edge
is roughly flat"*. On the full two days:

| | R-30b (part day) | **R-30c (full)** |
|---|---|---|
| gross | −0.50% of stake | **−7.27%** |
| fees | 4.01% | 4.01% |
| net | −4.5% | **−10.99%** |

**Fees are now the smaller half of the loss.** Gross is −30.35 of the −45.87; fees are −16.73. The
correct statement is: *the engine's own calls lost the money, and the fee made a bad result worse* —
not the other way round.

**This also weakens the Predict.fun case further (R-31).** I wrote there that switching venue turns
a −4.5% loss into roughly −2.9%. Corrected: it turns **−10.99% into roughly −9.3%**. Predict is
still the better venue on fee and fill, but it recovers about a sixth of the hole, not a third.

## The regime answer is unchanged, and now on more data

No bucket qualifies. Six live cells now reach n≥60, but each holds **52–77% of the entire live
sample** (ret24 LO 89/115, rv24 HI 75/115, rangeatr HI 60/115, autocorr HI 65/115, samedir MID
74/115, posrange LO 78/115) — a bucket holding most of the data is the data, not a detector. Live
spans 47 h, so both halves sit in one contiguous window. And every bucket the two losing days land
in is still **positive on the big paper sample** (+0.116 … +0.245, n 580–1108). **No detector.**

## Two stale literals fixed in `r30b_live.py` — same bug, twice, in one file

1. The header asserted *"snapshot is 09-16 09:11, coverage ends 08:20"*. Hardcoded; false the moment
   a fresher gz arrived. Now derived from the journal's own first and last epoch.
2. Step 3 printed *"each is 68-86% of the sample (ret24 LO 71/88, posrange LO 76/88, …)"*. Also
   hardcoded, also stale. Now computed, which is how the cell list grew from four to six.

This is the third stale-literal of the day (`task17_forward.py` had one too). The pattern: a caveat
or count written as prose at the time of first writing, which keeps printing confidently after the
data moves. **Anything describing the data must be computed from the data.**
