# Task R-2 — the regime grid on the v10 Polymarket set (777 graded)
H1, 2026-09-14 01:05 UTC. V's task (`learner/REQUEST.md` R-2). Push access verified first. Buckets
unchanged from R-1. **Measurement only; no design.** Script `task_r2_v10_polymarket_regime_grid.py`.

## 1. Provenance, run before any cell — V asked and did not assume; here is the answer

| comparison | n | disagree |
|---|---|---|
| `v10 trades.actual` vs `venues.outcome` (Polymarket) | 776 | **0 — 0.0%** |
| `v10 trades.actual` vs `candles.actual` (Binance) | 776 | 127 — 16.4% |

**The v10 runner also grades on Polymarket's own oracle, exactly.** No re-grade was needed. Same
answer as the v12 lane, now on an independent file and 2.5× the sample.

## 2. The caveat that governs every number below

**This is a paper runner filling at the quoted ask.** No slippage, no queue, no partial fills, no
adverse selection at the touch. Everything here is an **upper bound**. It is not comparable with a
live fill, and the gap is not small — the same runner's own quote-age split is in §3.

Excluded: 17 rows with no kline features (outside my candle set) and 1 with no oracle label. 759 used.

## 3. The split V did not ask for, and the one I would read first

The set spans 09-08 → 09-14 and `book_age_ms` only exists from 09-11 13:28, so half of it cannot have
its entry price certified at all. That is the Task 20/21b distortion, and it is present here:

| rows | n | per $1 | halves |
|---|---|---|---|
| all graded | 776 | +0.100 | +0.124 / +0.076 |
| **quote age UNKNOWN** (pre-13:28) | 430 | **+0.120** | +0.105 / +0.135 |
| **quote age KNOWN** | 346 | **+0.075** | +0.055 / +0.095 |
| **of those, fresh ≤1 s** | **316** | **+0.058** | **+0.054 / +0.062** |
| of those, stale >1 s | 30 | +0.255 | insufficient, not read |

**+0.058 on the 316 rows that are both certifiable and fresh, both halves positive and within half a
cent of each other.** That is the honest per-$1 for this runner, and it reproduces Task 21b's +0.055
(n=280) on a different slice. The uncertifiable rows are worth about twice as much, which is the same
direction the artifact has always pointed.

## 4. Q4 busiest — the cell V asked for first, now readable

| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| **Q4 busiest** | **89** | **+0.088** | 49.4% | **+0.283 / −0.103** | **halves FAIL** |

**Task 13's "only negative cell" is not negative here.** At a readable n it is positive overall and
fails on halves instead. So the prior record's one regime effect does not reproduce: it is neither
confirmed nor cleanly refuted — it is unstable, which is a different and less useful thing than the
"busiest quartile is bad" story it has been carrying.

## 5. The whole grid, Polymarket's oracle, 759 rows

**Pooled: n=759, +0.102, hit 52.2%, halves +0.132 / +0.072 — `verify.py` passes.**

### Trailing-12 SPAN quartile (31.4 / 48.9 / 76.4 bps)
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| Q1 calm | 325 | +0.110 | 53.2% | +0.106 / +0.115 | halves pass, positive |
| Q2 | 196 | +0.096 | 51.5% | −0.051 / +0.244 | **halves FAIL** |
| Q3 | 149 | +0.097 | 52.3% | +0.096 / +0.098 | halves pass, positive |
| Q4 busiest | 89 | +0.088 | 49.4% | +0.283 / −0.103 | **halves FAIL** |

### UTC 8-hour block
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| 00–08 | 219 | +0.090 | 51.6% | +0.007 / +0.172 | halves pass, positive |
| 08–16 | 240 | +0.128 | 52.5% | +0.200 / +0.056 | halves pass, positive |
| 16–24 | 300 | +0.089 | 52.3% | +0.181 / −0.004 | **halves FAIL** |

### Weekday / weekend — both readable now
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| weekday | 511 | +0.086 | 51.3% | +0.066 / +0.105 | halves pass, positive |
| weekend | 248 | +0.134 | 54.0% | +0.183 / +0.085 | halves pass, positive |

**R-1's weekday cell failed halves at n=74. At n=511 it passes.** That failure was a small-sample
artifact, and this is the clean correction of it.

### The weekend by day — and why this is still not what V asked for
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| 09-12 Sat | 148 | +0.124 | 53.4% | +0.162 / +0.086 | halves pass, positive |
| 09-13 Sun | 100 | +0.148 | 55.0% | +0.118 / +0.179 | halves pass, positive |

V asked for **a second, separate weekend window**. This set does not contain one: 09-12 and 09-13 are
the two days of **the same weekend**. Reporting them separately is better than early/late halves of
one day, but it is not an independent replication and must not be read as one. **The second weekend
arrives 09-19.**

### Every UTC day, for the record
| day | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| 09-08 Tue | 46 | +0.282 | 63.0% | +0.145 / +0.420 | insufficient, not read |
| 09-09 Wed | 136 | +0.078 | 50.7% | +0.076 / +0.079 | halves pass, positive |
| 09-10 Thu | 159 | +0.127 | 51.6% | −0.050 / +0.302 | **halves FAIL** |
| 09-11 Fri | 170 | **+0.000** | 48.2% | +0.089 / −0.089 | **halves FAIL** |
| 09-12 Sat | 148 | +0.124 | 53.4% | +0.162 / +0.086 | halves pass, positive |
| 09-13 Sun | 100 | +0.148 | 55.0% | +0.118 / +0.179 | halves pass, positive |

**Friday is exactly zero on n=170.** That is the single most informative row in this report: a full
readable day at 0.000 per $1 while the pooled number is +0.102.

### Flips of the open in the last 6 candles
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| 0–1 | 10 | −0.406 | 30.0% | −0.152 / −0.660 | insufficient, not read |
| 2–3 | 97 | +0.092 | 50.5% | −0.022 / +0.203 | **halves FAIL** |
| 4+ | 652 | +0.111 | 52.8% | +0.114 / +0.107 | halves pass, positive |

### Book width at the fire, median cut 0.0100 (stated, not tuned)
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| tight | 685 | +0.096 | 52.4% | +0.112 / +0.080 | halves pass, positive |
| wide | 73 | +0.169 | 50.7% | +0.332 / +0.010 | halves pass, positive |

## 6. What the grid says

**Cells positive in both halves at n ≥ 60:** Q1 calm (325), Q3 (149), 00–08 (219), 08–16 (240),
weekday (511), weekend (248), Sat (148), Sun (100), Wed (136), flips 4+ (652), tight (685), wide (73).

**Cells that FAIL halves at a readable n:** Q2 (196), Q4 busiest (89), 16–24 (300), flips 2–3 (97),
Thu (159), Fri (170).

**Still no cell separates, and now there is a better reason to believe that.** Every readable positive
cell lies between **+0.078 and +0.148** — a 7-cent band around the +0.102 pooled number, on a sample
2.5× R-1's. The cells that differ do not differ by being *worse in a regime*; they differ by being
**unstable across their own halves**, which is what noise looks like, not what a regime looks like.
The one genuinely large spread is between certifiable and uncertifiable quotes (§3), which is a
measurement artifact, not a market state.

**On the literal question — "make it live when Market is good":** this grid does not identify a
"good market" cell. It identifies a runner that is mildly positive nearly everywhere on paper at zero
slippage, worth about **+0.058 once the entry price is certifiable**, with one full readable day
(Friday, n=170) at exactly zero. Nothing here supports switching on a regime, and the honest next
measurement is the second weekend on 09-19 plus more certifiable-quote rows — not another slice of
this one.
