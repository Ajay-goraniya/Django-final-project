# Task R-1 — the Polymarket regime grid. Measurement only.
H1, 2026-09-14 00:45 UTC. V's task (`learner/REQUEST.md`, 09-14 00:2x). Script
`task_r1_polymarket_regime_grid.py`. Push access verified before starting. **No recommendation to
gate. Nothing below is a design.**

---

## 1. I did not follow one instruction in the brief, and this is why

**The brief says: "Grade everything on `candles.actual` (Binance close ≥ open). Paper's own `win`
column is oracle-flattered." For a Polymarket lane that is backwards, and it is the 09-10 error
pointed the other way.**

Polymarket settles on its own oracle, not on Binance close ≥ open. Checked, on the committed files:

| comparison | n | disagree |
|---|---|---|
| lane `actual` vs `venues.outcome` (Polymarket's resolution) | 303 | **0 — 0.0%** |
| lane `actual` vs `candles.actual` (Binance) | 303 | **61 — 20.1%** |
| `venues.outcome` vs `candles.actual`, whole overlap | 1,452 | 199 — 13.7% |

The lane is already graded on Polymarket's own oracle — exactly, 303 of 303. It is not
oracle-flattered; it is oracle-**correct** for the venue that pays it. And the direction of the error
matters: the same 304 trades read

- **+0.132 per $1 on Polymarket's oracle** (what the venue actually pays), and
- **+0.249 per $1 on `candles.actual`** — nearly double.

So following the brief would have *inflated* the grid by ~90% and every cell with it. `verify.py`'s
`grading()` check exists for precisely this, and it passes here only because I grade on the settling
source: provenance 0/303 against an independent file.

Everything below is on **Polymarket's oracle**. If V wants the Binance-graded version for comparison,
set `ORACLE = 'BINANCE'` in the script — but it should not be used to decide anything.

## 2. Two limits that apply to every cell, before any of it is read

1. **Zero slippage by construction.** This lane fills at the quoted ask with `slippage` exactly 0.0 on
   every row — V's own note of 09-12, recorded in STATE.md. **Every number here is an upper bound** and
   none of it is comparable like-for-like with a live fill. The honest per-$1 on the *v10* lane's
   quote-age-certifiable rows was +0.055 (Task 21b, n=280); that is the closer analogue.
2. **The sample is one weekend.** 230 of 304 trades are weekend. So the block and quartile rows are
   mostly re-slices of a single contiguous stretch, and their halves are early-vs-late within it. That
   is the structure that failed on 09-12: the 11.2 weekend cell passed all four checks at n=62 and was
   worth −0.001 by n=104.

## 3. The cell V asked for first — Task 13's only negative cell

| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| **Q4 busiest range quartile** | **35** | **−0.066** | 45.7% | −0.286 / +0.141 | **INSUFFICIENT (n<60), not read** |

Task 13 had it negative at n=24; it is still negative at n=35, and still under the bar. **Marked, not
read.** It is the only directional agreement with the prior record, and 35 fires cannot establish it.

## 4. The whole grid

**Pooled:** n=304, **+0.132**, hit 53.6%, halves +0.128 / +0.137 — `verify.py` passes (grading,
sample, halves).

### Trailing-12-candle SPAN quartile (V's cuts 31.4 / 48.9 / 76.4 bps)
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| Q1 calm | 215 | +0.132 | 54.0% | +0.195 / +0.069 | halves pass, positive |
| Q2 | 35 | +0.251 | 57.1% | +0.095 / +0.398 | insufficient, not read |
| Q3 | 19 | +0.287 | 57.9% | +0.573 / +0.030 | insufficient, not read |
| Q4 busiest | 35 | −0.066 | 45.7% | −0.286 / +0.141 | insufficient, not read |

**A note on the cuts, because two different cut sets are in circulation and conflating them would be
an error.** V's 31.4 / 48.9 / 76.4 are the quartiles of the trailing-12-candle **span** (max−min over
the last 12 candles); on my 73,703-candle set those quartiles are 31.1 / 48.6 / 76.0 — a match. My own
Task 17.3 used 8.6 / 13.0 / 19.8, which are the quartiles of the trailing-12 **mean of per-candle
range** (mine: 8.5 / 12.9 / 19.7). Both are right for their own feature. I used V's, as instructed,
with the span definition they belong to.

### UTC 8-hour block
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| 00–08 | 80 | +0.258 | 58.8% | +0.120 / +0.396 | halves pass, positive |
| 08–16 | 89 | +0.138 | 53.9% | +0.065 / +0.209 | halves pass, positive |
| 16–24 | 135 | +0.054 | 50.4% | +0.105 / +0.005 | halves pass, positive |

### Weekday / weekend
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| weekday | 74 | +0.016 | 47.3% | +0.071 / −0.038 | **halves FAIL** |
| weekend | 230 | +0.170 | 55.7% | +0.231 / +0.109 | halves pass, positive |

### Flips of the open in the last 6 candles
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| 0–1 | 9 | −0.102 | 44.4% | +0.060 / −0.232 | insufficient, not read |
| 2–3 | 69 | +0.047 | 50.7% | +0.022 / +0.072 | halves pass, positive |
| 4+ | 226 | +0.168 | 54.9% | +0.144 / +0.192 | halves pass, positive |

### Book width at the fire (`_ask_up` + `_ask_dn` − 1, from the lane's own feature blob)
| cell | n | per $1 | hit | halves | verdict |
|---|---|---|---|---|---|
| tight (≤ 0.0100) | 262 | +0.129 | 53.8% | +0.110 / +0.149 | halves pass, positive |
| wide (> 0.0100) | 42 | +0.152 | 52.4% | +0.204 / +0.099 | insufficient, not read |

No prior H1 cut existed for Polymarket book width. **I cut at the median (0.0100) and am stating that
rather than choosing a cut that separates the cells** — a tuned cut would be the banned threshold
sweep. The two cells are within 2c of each other, so on this sample width does not separate anything.

## 5. The answer to the literal question

**Cells positive in both halves at n ≥ 60, full stop:** Q1 calm (215), 00–08 (80), 08–16 (89), 16–24
(135), weekend (230), flips 2–3 (69), flips 4+ (226), tight book (262).

**Cells that fail:** weekday (74) fails halves. Q4 busiest, Q2, Q3, flips 0–1 and wide book are all
under 60 and not read.

**What that list actually says:** every readable cell is positive, which means **no cell separates**.
Eight of eight readable cells pass in the same direction, the pooled number is +0.132, and the spread
across the readable cells (+0.054 to +0.258) is within what one weekend's noise produces. A grid where
everything passes is not evidence for a regime switch — it is evidence that this sample cannot find
one. There is no "market is good" cell here, because there is no "market is bad" cell to contrast it
with at a readable n.

## 6. What cannot be used honestly, and what would fix it
- **The v10 Polymarket paper (776 graded, `/tmp/v10_long4.sqlite3`) is NOT on the branch.** It is the
  one dataset large enough to break the single-weekend problem and to give the Q4 cell a readable n.
  **Please snapshot it to `learner/live_backup/`.** I did not reconstruct it.
- The twins launched 09-13 23:37 have ~1 h of history; nothing to read.
- No rows were dropped from the v12 lane: all 304 had an oracle label, kline features and a feature
  blob. One row is ungraded (`actual` null) and is excluded from the 303 grading comparison.

**Next measurement that would move this forward:** the same grid on the v10 776-trade set, and a
second separate window for the weekend cell. Until one of those exists, the grid is measurement of a
single weekend and nothing should be designed from it.
