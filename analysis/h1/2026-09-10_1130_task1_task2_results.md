# H1 results for V — Task 1 and Task 2 (11:30 UTC 09-10)

Data: `learner/live_backup/*.sqlite3.gz` as committed at `ef5ae2d`. PnL is stated **at $1** with V's
fee model (win = shares*0.98 - 1 where shares = 1/quote; loss = -1). Reproduce with
`analysis/h1/reversal_profile.py` and `analysis/h1/gates.py`.

**Two corrections to my 3dc5c69 note first — both were small-sample artefacts, and both reverse.**
That note used `build11` (twin A, 31 REVERSAL fires). On `predict_pnl`'s 110 fires:

1. **RETRACTED: "REVERSAL went live into its weakest window."** I flagged 08:00-10:59 as 3/6 -1.64.
   Over 110 fires that window is **11/16 (69%), +2.03** — the run average exactly. There is no
   08-10 weakness. **Do not change the kill rule on my account.** My apologies for the noise.
2. **RETRACTED: hour-of-day as a variant candidate.** See Task 2(a) — the runs disagree with each
   other hour by hour. It is not a real effect.

The book-depth measurement in that note stands (it is a measurement, not an inference), and the
quote-bucket direction not only stands but strengthens.

---

# Task 1 — independent check of the REVERSAL finding

## Your headline numbers reproduce, to the decimal

| | V | H1 | |
|---|---|---|---|
| REVERSAL fires | 110 | **110** | ✅ |
| directional | 69% | **69%** | ✅ |
| mean quote | 0.55 | **0.551** | ✅ |
| median fire | 192 s | **193 s** | ✅ |
| PnL @$1 | +43.6 | **+43.62** | ✅ |
| both halves positive | yes | **+12.57 / +31.05** | ✅ |
| MAIN | 345 fires, 72%, q 0.75, -20.8 | **362 graded, 74%, 0.750, -19.22** | ✅ (count differs, story identical) |

**Confirmed.** MAIN is right three times in four and still loses, because it pays 0.75. That is the
whole finding and the data carries it.

## (i) By quote bucket — the dominant effect, stronger than I first reported

| quote | n | W/L | hit | PnL | per fire |
|---|---|---|---|---|---|
| **< 0.45** | 20 | 17/3 | **85%** | **+36.72** | **+1.836** |
| 0.45-0.60 | 48 | 32/16 | 67% | +9.46 | +0.197 |
| **> 0.60** | 42 | 27/15 | 64% | **-2.56** | **-0.061** |

**84% of REVERSAL's PnL comes from 18% of its fires**, and the expensive bucket is a net loser over
42 fires. Note >0.60 still wins 64% of the time — it is priced wrong, not predicted wrong. Same
disease as MAIN, inside REVERSAL.

**Entry cap test** (skip fires quoted above X):

| cap | kept | hit | PnL | removed | removed record | h1 | h2 |
|---|---|---|---|---|---|---|---|
| none | 110 | 69% | +43.62 | 0 | — | +12.57 | +31.05 |
| **0.60** | **68** | **72%** | **+46.18** | 42 | 27/15, -2.56 | **+14.73** | **+31.45** |
| 0.55 | 42 | 79% | +45.62 | 68 | 43/25, -2.00 | +14.74 | +30.88 |
| 0.50 | 28 | 82% | +41.16 | 82 | 53/29, +2.46 | +13.71 | +27.45 |

A **0.60 cap** passes your decision rule on all three clauses: ahead on PnL, ahead on hit rate,
sign holds on both halves. The PnL gain is only +2.56 and I would not sell it on that. The argument
is **38% fewer fires for slightly better PnL** — less capital at risk, fewer thin-book orders at
190 s, and the removed tail is the one that behaves like MAIN. It degrades gracefully either side
of 0.60, so it is not a knife-edge fit.

## (ii) By seconds into candle — your late fires are the good ones

| bucket | n | W/L | hit | PnL | per fire |
|---|---|---|---|---|---|
| < 120 s | 24 | 17/7 | 71% | +9.41 | +0.392 |
| **120-180 s** | 21 | 11/10 | **52%** | **-2.30** | **-0.109** |
| 180-240 s | 36 | 26/10 | 72% | **+19.70** | +0.547 |
| >= 240 s | 29 | 22/7 | **76%** | **+16.81** | **+0.580** |

**83% of the PnL is in fires at 180 s or later.** Your open caveat — "it fires at ~190 s, book depth
then is unmeasured" — resolves in the lane's favour on edge: the late window is where it earns, and
the latest fires are the best. The depth caveat is still real for sizing (median book 30, p25 15.6),
but the answer is cap the stake, not move the lane earlier.

## (iii) REVERSAL against EF on the same candle — **no, not net positive**

| relationship | n | REVERSAL | EF on those candles | **net** |
|---|---|---|---|---|
| **opposes EF** | 23 | 15/8, +4.50 | 8/15, **-8.29** | **-3.79** |
| agrees with EF | 27 | 17/10, +9.92 | 17/10, +8.07 | **+17.99** |
| no EF fire | 60 | 44/16 (73%), **+29.21** | — | +29.21 |

Direct answer to your question: **when the lanes disagree, the pair loses money.** REVERSAL wins its
side, but the EF fire it contradicts loses more. Two further things fall out:

- **67% of REVERSAL's total PnL comes from the 60 candles EF never fired on.** Its value is largely
  additive coverage, not a better opinion on candles EF already has.
- Agreement is the strongest signal on the board: +17.99 over 27 candles, both lanes 63%.

Worth considering as variant E: **suppress the EF fire when REVERSAL later opposes it** — though
note the causality problem, EF fires at ~20 s and REVERSAL at ~190 s, so EF cannot wait for it.
The implementable version is the reverse: let a REVERSAL fire that opposes an open EF position
close or hedge it rather than sit against it.

---

# Task 2 — time-of-day and gates

## (a) Hour-of-day: **negative result. It is not a real effect.**

Pooled 542 fires across the three runs, per UTC hour, the runs **disagree with each other**:

| hour | predict_pnl | build11 twin A | poly_pnl runner |
|---|---|---|---|
| 03 | +0.60 | **+3.31** | **-4.95** |
| 09 | **+6.86** | **-3.28** | +1.89 |
| 04 | -6.66 | -1.92 | **+0.21** |
| 16 | **-5.00** | — | **+2.65** |

And your two suspect windows, split by day (predict_pnl, the only run covering two passes):

- **04:00-06:00** — 09-09: 8/6, **+1.22**. 09-10: 4/6, **-2.70**. Does not repeat.
- **09:00-11:00** — 09-09: 6/2, **+3.68**. 09-10: 6/4, **+1.73**. **Both days positive** — the
  09:45-11:00 pain you logged this morning was that morning, not that hour.

**Conclusion: the losing stretches are one-offs, not hour-of-day.** Do not build an hours gate, and
strike the idea from my earlier note. Two days is thin, but the *disagreement between simultaneous
runs on the same hours* is the strong part of this: a real time-of-day effect would show up in all
three, and it does not.

## (b) Realised-volatility gate: **the best result in this report**

`poly_pnl` records `rv60` at fire time. Baseline: 235 fires, 121/114 (51%), **+19.70**, and it is
**h1 +22.03 / h2 -2.33** — negative in its own second half.

| gate | kept | hit | PnL | removed | removed record | **h1** | **h2** |
|---|---|---|---|---|---|---|---|
| none | 235 | 51% | +19.70 | 0 | — | +22.03 | **-2.33** |
| rv60 >= 0.2 | 136 | 54% | +26.42 | 99 | 48/51, -6.72 | +16.27 | **+10.15** |
| **rv60 >= 0.3** | **103** | **57%** | **+28.44** | 132 | 62/70, **-8.74** | **+16.03** | **+12.40** |
| rv60 >= 0.4 | 70 | 57% | +19.08 | 165 | 81/84, +0.62 | +10.79 | +8.29 |
| rv60 >= 0.5 | 49 | 55% | +11.23 | 186 | 94/92, +8.47 | +4.16 | +7.07 |

**rv60 >= 0.3: +28.44 vs +19.70, hit 57% vs 51%, and it turns a run that was negative in its second
half into positive in both** (+16.03 / +12.40). The 132 removed fires are 62/70 — a coin flip that
pays fees. The improvement rises to 0.3 and falls away after, so the signal is "low volatility is
bad", not one lucky threshold; 0.2 and 0.3 both work, which is what a real effect looks like.

Gating high volatility instead does the opposite — `rv60 <= 1.0` keeps +11.07 and pushes h2 to
-8.89. Do not do that.

This is the strongest variant candidate I have found and it is testable in shadow at zero risk.
`rv60` is already computed and stored at fire time in the runner, so the gate is a comparison, not
new plumbing. **Recommend it as variant E over anything currently in the ledger.**

## (c) Ask-price gates on EF: weak, one worth noting

| gate | kept | hit | PnL | removed | h1 | h2 |
|---|---|---|---|---|---|---|
| baseline | 235 | 51% | +19.70 | 0 | +22.03 | -2.33 |
| skip ask < 0.40 | 170 | 56% | +15.95 | 65 (26/39, +3.75) | +21.68 | -5.73 |
| **skip ask < 0.45** | 121 | **63%** | +20.86 | 114 (45/69, -1.16) | +16.26 | **+4.60** |
| skip ask > 0.60 | 230 | 51% | +18.40 | 5 | +21.30 | -2.90 |

| ask bucket | n | W/L | hit | PnL | per fire |
|---|---|---|---|---|---|
| < 0.40 | 65 | 26/39 | 40% | +3.75 | +0.058 |
| 0.40-0.60 | 165 | 91/74 | 55% | +14.65 | +0.089 |
| > 0.60 | 5 | 4/1 | 80% | +1.30 | +0.261 |

- **"Skip ask < 0.40": not supported.** Those fires hit only 40% but are still net positive (+3.75)
  — cheap enough that the win rate does not need to be high. Removing them costs money.
- **"Skip ask > 0.60": untestable here** — the runner made only 5 such fires. Note this is the
  opposite of REVERSAL, where >0.60 was 42 fires and negative. The lanes need separate rules; do not
  carry the REVERSAL cap across to EF.
- `ask >= 0.45` is the only ask gate that fixes the halves sign, and it does it by cutting 114 of
  235 fires for +1.16 of PnL. **rv60 >= 0.3 achieves more, on more fires, and makes mechanical
  sense. Prefer it.**

---

## What I would put in the ledger

1. **Variant E: `rv60 >= 0.3` gate on EF.** Strongest evidence here; both halves positive; free to
   shadow-test.
2. **REVERSAL entry cap at 0.60.** Modest PnL gain, but 38% fewer fires and it removes the
   MAIN-shaped tail. Also reduces exposure to the thin 190 s book.
3. **REVERSAL/EF opposition handling.** Do not let a REVERSAL fire sit against an open EF position;
   the pair is -3.79 over 23 candles.

## Sample sizes and caveats

110 REVERSAL fires over 41 h; 542 EF fires pooled over three runs and ~41 h; the REVERSAL quote
buckets are 20/48/42 and the seconds buckets 24/21/36/29. Two days of tape, one regime, $1 shadow,
no slippage modelled beyond the 2% fee — Tokyo's real fills average +0.41c worse than quote, which
would shave every number above slightly and hurt the cheap-entry buckets most in relative terms.
The hour-of-day negative and the rv60 positive are the two results I would act on; everything else
here is a hypothesis with a sample size attached.
