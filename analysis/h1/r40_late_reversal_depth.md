# Late REVERSAL 240–285 s — **the bucket is one lottery ticket, and my depth sources cannot be trusted**

`r40_late_reversal_depth.py`. REVERSAL fires from my own full-span replay
(`replay_lanes_1s.py`, 09-08 → 09-16, 1 Hz `venues.q`): **475 fires, 419 early (<240 s), 56 late.**

| bucket | n | hit | per $1 | total | ask med |
|---|---|---|---|---|---|
| late 240–285 s | 56 | 32.1% | **+1.7244** | **+96.56** | 0.115 |
| early < 240 s | 419 | 66.3% | +0.2759 | +115.58 | — |

This reproduces V's shape (n=56 in the 53–65 range, ~half of REVERSAL's replay profit).

## The answer, and it needs no depth data at all

| | profit carried | share of the bucket |
|---|---|---|
| **top 1 fire** | **+97.33** | **100.8%** |
| top 2 | +116.00 | 120.1% |
| top 3 | +123.19 | 127.6% |

**A single fire at ask 0.010 carries more than the entire bucket. The other 55 fires net −$0.77.**

REVERSAL total with the late bucket +212.15 (n=475); without it +115.58 (n=419). The "extra half of
REVERSAL's profit" is one 1-cent ticket that came in — not a bucket, not an edge, and not something
a deadline is costing you in any repeatable sense.

For scale: a $3 stake at ask 0.010 needs **300 shares**. Neither of my book loggers shows anything
like that at the touch on that fire (b1: 15.3 shares; polybook: 2,543 — see below for why that
disagreement matters).

Also note the winners' asks: median winning ask is **0.630**, i.e. most late winners pay 1.6×. The
+1.72 per-$1 is not "cheap asks win late" — it is that one 0.010 fire.

## WITHDRAWN (09-22 23:4x) — the owner was right; see the correction at the end of this file

**The "two different measurements / unreliable" claim below is withdrawn.** Re-matched on the same
market key and wall clock, the disagreement is dominated by a *persistent per-candle offset*, which
is the signature of market/window misalignment — exactly what the owner said — not of either logger
being wrong. Numbers in the correction section. The rest of this section is left as written, marked
wrong, because the reasoning is what I would otherwise repeat.

## ~~Why I will not give a depth verdict: my two book sources disagree fundamentally~~ (WRONG)

I hold `book1s.b1` and `polybook.pb`, two independent 1 Hz Polymarket loggers, both with
`ask_up/size_up/ask_dn/size_dn`. On **40,000 matched (epoch, sec) rows**:

| field | b1 median | pb median | identical | discrepancy |
|---|---|---|---|---|
| `ask_up` | 0.4700 | 0.4400 | **6.9%** | mean \|diff\| **0.1098** |
| `size_up` | 151.0 | 333.6 | 0.1% | pb/b1 ratio p5–p95 **0.14× … 62.6×** |

An 11-cent mean disagreement on a probability, and sizes differing by up to 62×, is not two honest
observers 0.4 s apart — it is two different measurements. On the 38 late fires I could match in
both, they **disagree on dust / not-dust for 16**.

So: **I cannot tell you whether the late asks are fillable.** Any dust verdict I produced would rest
on a source I have just shown to be unreliable. What I ran before noticing it, for the record and
not as a finding: requiring two-sided + ≥5 shares + ≥$5 at the touch (b1) left 31 of 56, at
+0.3996/$1 and total **+12.39** — while the 9 rejected carried **+90.43**. That is *consistent* with
the dust story, but it rests on b1 alone and b1 is one of the two sources that disagree.

## verify.py on what survives — fails regardless

`late, passes b1 depth test`: n=31, +0.3996/fire.

- **sample size FAIL** — 31, under the 60 bar (and the unfiltered bucket is 56, also under).
- both halves PASS — but +0.823 → +0.003, collapsing.
- **cost sensitivity FAIL** — +0c +0.400, +2c +0.162, **+5c −0.040**: dies once you pay realistically.
- beats the null PASS — +0.400 vs +0.276 for REVERSAL before 240 s.

**VERDICT: not a finding**, on sample size and costs, before the depth question is even reached.

## What this says about the 240 s deadline

**The deadline is not costing measurable profit.** The late bucket's entire apparent value is one
fire; strip it and the remaining 55 are flat-to-negative. Whatever the executor's guard is doing, on
this sample it is not standing between the engine and half of REVERSAL's edge.

**What I would need to answer the depth question properly:** one book source that is reconciled
against the venue's own fills. The disagreement above is worth more attention than the late bucket —
if `book1s` and `polybook` really are 11 cents apart on the ask, then **every** book-derived feature
in this repo inherits that, not just this one test.

## Limits

1. Replay fires at the quoted 1 Hz ask, zero slippage — upper bound, as always.
2. `book1s` starts 09-11 02:01, so it covers all 56 late fires but only part of the replay span.
3. Top-of-book size only; no ladder exists in any file I hold, so "≥5 shares at or under ask+0.01"
   could only be tested as "≥5 shares AT the touch" — a weaker condition, and an upper bound on
   fillability even if the source were trustworthy.


---

# CORRECTION — the book logs differ by ALIGNMENT, not by reliability

Owner (09-22 23:4x): *"Because one is per candle up and down and second one is as per twap 60."*
Correct, and my r40 point 2 was wrong to call either source unreliable.

## Re-matched properly, then decomposed

`b1` carries a `book_candle` column distinct from `epoch` (they differ on **10.9%** of rows) and
`pb` carries a `status` column with **88,901 `no market` rows** — I used neither in r40. Redone with
both, plus wall-clock matching `|Δt| ≤ 500 ms` and freshness in both files:

| alignment | n | corr | exact | mean \|diff\| | ≤1c |
|---|---|---|---|---|---|
| `epoch=epoch` (r40's join) | 60000 | 0.832 | 7.3% | 0.1058 | 17.4% |
| + `pb` live websocket only | 60000 | — | 7.3% | 0.1061 | 17.4% |
| `book_candle=epoch`, live | 60000 | — | 7.3% | 0.1049 | 17.4% |
| both fresh (b1 ≤2000 ms, pb ≤2 s) | 60000 | 0.854 | 6.7% | 0.0995 | 16.4% |
| both fresh, sec 30–240 | 60000 | **0.889** | 4.5% | 0.0934 | 13.1% |

**Re-keying does not close the gap — but the decomposition explains it.** On 1,178 candles with ≥30
paired seconds each:

| component | value | meaning |
|---|---|---|
| sd of the per-candle **mean** offset | **0.1172** | a near-constant offset *within* a candle that varies *between* candles |
| median **within-candle** sd | **0.0617** | second-to-second observation noise |

**The persistent per-candle component is ~2× the tick noise.** Two honest observers of the *same*
book would disagree mostly second-to-second; two logs keyed to *different* markets or windows
disagree by a per-candle constant. The data has the second shape. Correlation 0.83–0.89 confirms
they track the same underlying series — so neither file is broken, they are indexed differently.

Agreement also rises sharply late in the candle (≤1c: 13.5% at 120–240 s, 26.2% at 240–285 s,
**58.0%** at 285–301 s), consistent with two windows converging as they come to refer to the same
resolution.

## What this does and does not change

- **Withdrawn:** "every book-derived feature in the repo inherits an 11-cent error." Not supported.
  The offset is an indexing difference between two *logs*, and says nothing about what the *engine*
  read at fire time.
- **Unchanged:** the late-REVERSAL verdict above. It rests on the PnL distribution — one 0.010 fire
  carrying 100.8% of the bucket — and never used book depth at all.
- **Still open:** I cannot do the dust/depth test until someone states which file keys to which
  market. Given the 2× median size ratio, the choice decides a 5-share threshold. That is a mapping
  question for whoever wrote the loggers, not a data-quality problem.
