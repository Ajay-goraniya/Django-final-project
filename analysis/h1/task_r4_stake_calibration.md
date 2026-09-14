# Task R-4 — dynamic staking: is there anything to size on?

User: *"what if the staking is dynamic? less capital in losing trades, more in winning ones... it
needs to be very sure."* V's brief, 09-14 21:5x. Script `analysis/h1/task_r4_stake_calibration.py`.

Sizing can only work if something known **at fire time** predicts the win. Buckets were fixed
before any outcome was read; the whole grid is below; cells under 60 graded fires are marked and
not read. Grading on Polymarket's own oracle, `venues.outcome` — provenance **0/912** against the
lanes' own recorded `actual` (independent files).

**Answer: no. Nothing separates the win rate consistently, and the one thing that separates the
money is the price paid, not the accuracy.**

## The sets

| set | n graded | what it is |
|---|---|---|
| A — v10 poly long4 | 777 | **PAPER**, fills at the quoted ask — an upper bound |
| B — v12 lane + weekend | 766 | **PAPER**, slippage 0.0 by construction (V's own caveat) |
| C — live fills (`r3_submissions.csv`) | 78 | the only real fills; carries no `p` and no EV |

## 1. Does the win rate separate?

Win-rate spread across the four readable buckets:

| feature | set A | set B |
|---|---|---|
| model `p` | **20.9 pp** | 9.1 pp |
| EV at fire | 2.7 pp | 5.0 pp |
| sec into candle | 7.3 pp | 6.7 pp |
| ask paid | 15.6 pp | 4.3 pp |

`p` is the one that looks like a sizing signal on set A, and it is monotone there:
42.4% → 51.0% → 58.1% → 63.2%. **It does not replicate.** On set B the same buckets read
51.7% → 57.9% → **48.8%** → 57.8% — non-monotone, and the third bucket is below a coin. A
confidence measure that orders one paper set and not the other is not something to put money on.

Set C, the only set with real fills, is **unreadable everywhere**: cells of n = 36/19/16/7 by
second and 18/19/19/22 by ask. Marked insufficient, not read.

## 2. EV separates the money — so what is it actually selecting?

Pooled paper sets, n=1,543, EV quartile cuts 0.167 / 0.251 / 0.302:

| EV bucket | n | win% | median ask | median `p` | per $1 |
|---|---|---|---|---|---|
| EV Q1 | 385 | 51.9% | 0.500 | 0.602 | +0.004 |
| EV Q2 | 357 | 52.1% | 0.490 | 0.623 | +0.009 |
| EV Q3 | 414 | 52.7% | 0.450 | 0.594 | +0.117 |
| EV Q4 | 387 | **55.0%** | **0.380** | **0.544** | **+0.352** |

Read the columns against each other. From Q1 to Q4 the win rate moves 3 points, **the model's own
confidence `p` falls** (0.602 → 0.544), and the ask drops 12 cents. High EV does not mean the model
is surer and more often right — **it means the quote was cheap.** EV = p/ask − 1 is dominated by
its denominator.

Holding price roughly fixed (inside each ask quartile, split at that bucket's EV median):

| ask bucket | EV half | n | win% | median ask | median `p` |
|---|---|---|---|---|---|
| Q1 | low / high | 139 / 189 | 48.9% / 47.1% | 0.390 / 0.350 | 0.510 / 0.510 |
| Q2 | low / high | 206 / 212 | 48.1% / 51.9% | 0.440 / 0.420 | 0.540 / 0.569 |
| Q3 | low / high | 164 / 173 | 52.4% / 59.5% | 0.480 / 0.480 | 0.590 / 0.627 |
| Q4 | low / high | 228 / 232 | 57.0% / 56.9% | 0.560 / 0.530 | 0.678 / 0.678 |

The EV-high half is cheaper in every quartile, and the win-rate change is **−1.8 / +3.8 / +7.1 /
−0.1 pp — it flips sign.** No consistent accuracy gain survives holding the price fixed.

## 3. The walk-forward test V asked for

Bucket per-$1 estimated on the **first half only**, applied to the second half; same trades, same
total capital.

| set / feature | train | test | flat | dynamic | delta |
|---|---|---|---|---|---|
| A v10 / p | 388 | 389 | +0.077 | +0.061 | −0.016 |
| A v10 / EV | 388 | 389 | +0.077 | +0.188 | **+0.111** |
| A v10 / sec | 388 | 389 | +0.077 | +0.084 | +0.007 |
| B v12 / p | 383 | 383 | +0.148 | +0.215 | +0.067 |
| B v12 / EV | 383 | 383 | +0.148 | +0.278 | **+0.130** |
| B v12 / sec | 383 | 383 | +0.148 | +0.135 | −0.013 |
| C live / sec | 39 | 39 | +0.014 | +0.418 | +0.404 — **n=39, insufficient, do not read** |

Only EV beats flat on both paper sets — and §2 says what EV-weighting actually does: it moves
capital onto the cheapest quotes.

## 4. The verification gate, run honestly — including what it passes

`verify.py` on "size up on the high-EV quartile" (+0.352/fire, n=387):

| check | result |
|---|---|
| sample size | PASS — all four cells ≥ 60 |
| both halves | PASS — +0.253 / +0.449 |
| sweep shape | PASS — monotone [0.004, 0.009, 0.117, 0.352] |
| cost sensitivity | PASS — survives to +5c (+0.199) |
| beats the null | PASS — +0.352 vs +0.282 for "just buy the cheapest ask quartile" |
| **quote age** | **FAIL** — ffill, max age **10.0 s** (median 14 ms, p90 433 ms) |

**VERDICT: NOT A FINDING.** And the failing check is the right one: Task 20's artifact is exactly
"an EV filter conditioning on cheapness turns unbiased quote noise into one-directional profit",
and §2 is that mechanism caught in the act.

Three further reasons this does not become a stake rule, independent of the gate:

1. It beats the dumb null — *buy the cheapest quartile of asks* — by only **+0.070**. Nearly the
   whole "EV edge" is available without any model at all.
2. It is measured on **paper fills at the quoted ask**. R-3 measured what that quote is worth live:
   the filled book earned **+0.004 per $1 at the price actually paid** against **+0.038 at its own
   quote**.
3. R-3 also found **105 of 108 rejects were FAK-killed because the resting size was gone**. The
   high-EV bucket *is* the cheap-ask bucket — the orders the live book least often fills. Sizing up
   on it means sizing up on the trades you are least likely to get.

## Verdict

**The buckets do not separate the win rate, so there is nothing to size on — that closes it.**
`p` orders set A and not set B. EV orders the money but not the accuracy, and it fails the
quote-age gate. The only set with real fills cannot test any of it at n=78.

No stake modifier is proposed, and the standing rule ("no gates, stake modifiers or threshold
sweeps on a score already known to be weak") is the reason this task ends here rather than in a
sizing curve.

What would reopen it: a live-fill sample large enough to put 60+ trades in each bucket, priced at
`avg_fill_price`, not at a quote. At the current fill rate that is weeks, not days.
