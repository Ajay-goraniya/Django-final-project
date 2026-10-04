# H1 — Task 7: which model, on 72k candles (answers the build question)

Task 7 asks to "test whether a small model (logistic or a shallow tree, walk-forward only, never fit
on the test half) beats the raw prefix table." Now answerable properly: **72,331 graded candles,
252 days, split mid-May — 36,193 train / 36,138 test, no refit on test.**

| t | AUC raw sign | AUC **prefix table** | AUC logistic | AUC shallow tree | acc sign | acc tree |
|---|---|---|---|---|---|---|
| 10 | 0.5611 | **0.5000** | 0.5887 | 0.5889 | 56.1% | 56.3% |
| 20 | 0.5832 | **0.5000** | 0.6176 | **0.6189** | 58.3% | 58.3% |
| 30 | 0.6015 | 0.6015 | 0.6410 | 0.6416 | 60.2% | 60.1% |
| 60 | 0.6467 | 0.6524 | 0.6987 | **0.7003** | 64.7% | 64.6% |
| 90 | 0.6857 | 0.6992 | 0.7470 | 0.7500 | 68.6% | 68.6% |
| 120 | 0.7150 | 0.7344 | 0.7826 | 0.7855 | 71.5% | 71.5% |
| 180 | 0.7832 | 0.8079 | 0.8578 | 0.8608 | 78.3% | 78.3% |
| 240 | 0.8445 | 0.8718 | 0.9176 | 0.9194 | 84.5% | 84.4% |

Prefix table = the literal path-prefix lookup from the task spec (sign at 30 s offsets, leaf =
P(close > open), cells under 30 training candles fall back to the base rate). Shallow tree =
gradient boosting, depth 3. Features: current side, signed distance from open, crossings so far,
seconds since last crossing, realised range, and the side/distance 15 s and 30 s earlier.

## Three answers

**1. The shallow tree does NOT beat logistic — use the logistic.** The gap is +0.001 to +0.003 AUC
at every t, which is nothing. Same predictions, more machinery, harder to ship inside the engine.
This is the direct answer to the build question.

**2. The raw prefix table is the WORST option early — and that is the user's proposed architecture.**
At t=10 and t=20 it is 0.5000, i.e. no information at all, because with only one or two 30 s offsets
available the prefix has almost no distinct states. It never beats the feature model at any t. The
"binary tree of path prefixes" throws away exactly what matters — **how far** price is from the open,
not just which side — and magnitude is what carries the early signal. Worth saying plainly to the
user: the tree-of-prefixes idea is sound as an intuition and the base rates from it are real, but as
an implementation a handful of continuous features beats it everywhere, and beats it most in the
early window EF actually fires in.

**3. Every model adds ranking, none changes the call.** Accuracy at the 0.5 threshold is identical
across sign, logistic and tree at every t (58.3% vs 58.3% at t=20; 84.5% vs 84.4% at t=240) while
AUC gains +0.035 at t=20 and +0.075 at t=240. Confirmed now on 3.5× the earlier data. **The output
is only usable as a confidence/sizing input, never as a direction flip.** That is also why the on/off
gate failed in pass 2 — thresholding a ranking signal at 0.5 discards the ranking.

## What this leaves for Task 7

The model is settled: logistic on those features, read at the actual fire second. What is not settled
is whether its confidence is worth anything in PnL, and pass 2 says the on/off form is not. The
remaining candidate is **confidence as a stake modifier** — size down low-confidence fires rather
than skipping them, which keeps the cheap winners the on/off gate destroyed. That needs the fire
data, still blocked until 09-10 klines publish.

## Caveats

Walk-forward on a single mid-May split; spot 1s klines; the prefix table is my reading of the spec
(30 s offsets) and a finer or event-based encoding would score better late, though it cannot fix the
t≤20 s degeneracy that matters most here. Feature set is fixed across t rather than tuned per t.
