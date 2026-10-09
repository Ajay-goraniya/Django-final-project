# H1 findings, 11:15 UTC 09-10 — REVERSAL depth, price bucket, hour-of-day

Source: `learner/live_backup/build11.sqlite3` as committed at `1ba7467` (10:50 UTC backup).
Container shadow engine, $1 notional, 09-09 21:02 -> 09-10 10:45 UTC.
Reproduce: `analysis/h1/reversal_profile.py`.

## 0. Your REVERSAL shadow numbers reproduce independently

| lane | graded | W | hit | pnl @$1 |
|---|---|---|---|---|
| REVERSAL | 31 | 26 | 84% | **+22.25** |
| MAIN | 123 | 92 | 75% | **-5.29** |
| EF | 125 | 67 | 54% | -3.31 |

Your 10:15 note said "Tokyo shadow 27/6 +22.7" — this backup is 26/31 +22.25, i.e. the same thing
one candle behind. MAIN at 75% right and still negative confirms the price story: it buys at 0.75.
Nothing below contradicts your reading; it sharpens two open items.

## 1. Your "book depth at ~192 s is unmeasured" caveat — it IS measured, and it's thin

From the 10:15 note: *"Caveat to test live: it fires at ~190 s into the candle, book depth then is
unmeasured."* The engine has been recording it all along:

```
seconds_into_candle  n=31  min=60  p25=137  med=193  p75=240  max=281
book_size            n=31  min=0.30  p25=15.6  med=30.0  p75=112  max=713
spread               n=31  med=0.01  p90=0.02  max=0.27
```

Median depth at fire is **30 units, p25 is 15.6, and the minimum is 0.30**. Spread is a clean 1c at
the median, so the quote is fine — it's the *size behind it* that's small.

**Why this matters now:** at $1 you will not notice. The equity ladder puts you at $2 from equity 30
and $3 from 40, and a $3 order into a book of 15 walks the ladder. Tokyo's one observed 9c-better
fill (09:40, quoted 0.43 filled 0.34) shows the walk cuts both ways, but on a thin book at 190 s the
asymmetry is against you. **Suggestion: cap REVERSAL stake independently of the EF ladder until you
have live fill-quality data for it** — the ladder was calibrated on EF's fills at 15-25 s into the
candle, where the book is deep, and REVERSAL fires into a different market state entirely.

## 2. REVERSAL's edge is concentrated in cheap entries

| entry price | n | W | hit | pnl | per fire |
|---|---|---|---|---|---|
| **<= 0.45** | 5 | 5 | **100%** | **+13.44** | **+2.69** |
| 0.45-0.60 | 13 | 10 | 77% | +5.55 | +0.43 |
| > 0.60 | 13 | 11 | 85% | +3.26 | +0.25 |

**16% of the fires produce 60% of the PnL.** Note the >0.60 bucket has a *higher* hit rate than the
middle one and earns a sixth as much per fire — this is exactly the MAIN failure mode (right often,
paid too much) showing up inside REVERSAL. Small sample, so not a rule yet; but an entry-price cap
is the cheapest variant in the ledger to test, and it's testable in shadow at zero risk.

## 3. REVERSAL went live at 10:21 — into its weakest observed window

| window | n | W | hit | pnl | avg buy |
|---|---|---|---|---|---|
| **08:00-10:59 UTC** | 6 | 3 | **50%** | **-1.64** | **0.67** |
| all other hours | 25 | 23 | **92%** | **+23.89** | 0.53 |

Every hour from 21:00 through 07:00 is positive. 08, 09 and 10 are the only weak ones, and the avg
entry price in that window is 14c higher — consistent with finding #2 rather than a separate effect.

**The risk to flag:** your kill rule is *"first 6 live fills 1/5 or worse -> lane off"*. In shadow,
this exact window produced 3/6. A slightly worse run of the same hours trips the kill rule and
retires a lane whose 41-hour record is +43.6 — for what may be a time-of-day effect you already
have the data to predict. **Suggestion: either judge the first 6 fills against the shadow record for
the same hours rather than against a flat bar, or hold the kill count open until REVERSAL has fired
in its strong window (post-21:00 UTC).**

## 4. EF hour-of-day — an untested ledger candidate

125 graded EF shadow fires, $1:

| worst | | | | best | | | |
|---|---|---|---|---|---|---|---|
| **10** | 2/9 | 22% | **-5.27** | **07** | 8/10 | 80% | **+4.09** |
| **09** | 4/10 | 40% | -3.28 | **03** | 7/8 | 88% | +3.31 |
| **06** | 3/9 | 33% | -3.24 | **08** | 8/12 | 67% | +3.24 |
| **22** | 3/8 | 38% | -2.90 | **01** | 7/10 | 70% | +2.91 |
| **04** | 3/8 | 38% | -1.92 | **23** | 5/8 | 62% | +1.51 |

The notes keep circling this (the 04:00-06:00 lull, the 06:00 and 09:00 wake-ups, "17 of 22 UTC
hours positive" for REVERSAL) but no variant has ever tested it. One day of data is far too thin to
ship on — hour 03's 7/8 is obviously noise. It is, however, cheap to run as variant E in the ledger
and it would accumulate evidence in the background while A/B/C fight over dials.

## Caveats

One session, one day, $1 shadow, no execution costs modelled beyond the recorded fee rate. The
REVERSAL bucket splits are 5 and 13 fires. Treat #1 as a measurement (it is), #2 and #4 as
hypotheses worth a shadow lane, and #3 as a live process risk worth handling today.
