# Task R-9 item 1 — stacked second-stage brain on frozen v10

V, 09-15 19:2x, standing program. User: *"keep working on it, don't stop after a few tests fail."*
Script `analysis/h1/task_r9_stacked_brain.py`. Ledger `analysis/h1/r9_ledger.md`.

**Verdict: neither arm ships. But the most useful thing in this run is a bug I caught in my own
first version, and it generalises beyond R-9 — see §1.**

## 1. The leak I caught, and why it matters to anyone using streak features

The first version printed **83.8% hit rate and +414 PnL** for the lightgbm arm. That is not a good
result, it is a tell. The cause:

`last3` / `last10` were accumulated **per tick**. A candle is evaluated many times (one tick per
second in the decision window), and every tick of a candle carries the same label. So the second
and later ticks of a candle saw a "previous result" that was **their own candle's outcome**. The
target leaked into its own feature.

Fixed: streaks now accumulate **per candle**, and only over candles **strictly earlier** than the
current one. The 83.8% becomes 54.7%.

**This is worth flagging to anyone else building on this repo:** `build11` has a `streak_events`
table, and any feature derived from recent outcomes has exactly this failure mode whenever the
decision loop evaluates a candle more than once. Per-tick history is not causal history.

## 2. Design

Frozen v10 keeps the **direction**; the stack only refines the **confidence**:

- stage 1 — frozen v10 → `p_up` → side, and `ps` = its confidence in that side
- stage 2 — trained on *"did this fire actually win?"* from `ps`, `ev`, `ask`, `sec`, `rv60`,
  taker ratio (R-7), causal `last3` / `last10`, hour-of-day sin/cos, and the rv60 regime bucket
- the EV rule is **unchanged**: `ps2` replaces `ps`, same cost model, same regime thresholds, one
  fire per candle at the first qualifying tick

Walk-forward by day (train on days < d, test on d), both arms V asked for. 32,062 evaluated ticks,
1,693 candles, 8 days; 26,034 ticks scored across 5 tested days. Graded on `venues.outcome`.
Paper at the quoted ask, so per-$1 is an upper bound (R-3: live +0.004 vs +0.038 quoted).

## 3. Result

| arm | Brier | fires | hit% | per $1 | total |
|---|---|---|---|---|---|
| frozen v10 | **0.1631** | 758 | 52.6% | +0.131 | **+99.56** |
| stack logit | 0.1635 | 67 | 52.2% | +0.284 | +19.04 |
| stack lgbm | 0.1668 | 698 | 54.7% | +0.131 | +91.52 |

**Neither stack improves the Brier score** — both are marginally worse than the frozen model they
sit on top of. lgbm buys a better hit rate (54.7% vs 52.6%) by firing less, lands on an *identical*
per-$1, and ends below frozen on total. logit fires 67 times out of 758 candidates: the same
"decline the book" shape as R-5 and R-6.

Per day, whole grid, nothing dropped (per $1) — frozen / logit / lgbm:
09-10 +0.127 / +0.115 / +0.082 · 09-11 −0.000 / +0.084 / −0.061 · 09-12 +0.153 / +0.194 / +0.218 ·
09-13 +0.126 / +0.329 / +0.113 · 09-14 +0.264 / +0.589 / +0.364.

## 4. Verification

**stack logit** — sample PASS (n=67), halves PASS (+0.130/+0.183), permutation PASS (p=0.000),
**paired FAIL** (65 shared candles, only **7 discordant**, 2 vs 5, p=0.453 — no power at all),
**null FAIL** (+19.04 vs frozen's +99.56). → **NOT A FINDING.**

**stack lgbm** — sample PASS, **halves FAIL** (−0.029 / +0.057, sign flips), **paired FAIL**
(545 shared, 58 discordant, **29 vs 29, p=1.000** — a perfect null), permutation PASS,
**null FAIL** (+91.52 vs +99.56). → **NOT A FINDING.**

The lgbm paired result is the cleanest statement available: on the candles where the stack and the
frozen model disagree, they split exactly 29–29. The stack is not adding a signal; it is
reshuffling.

## 5. Where this leaves the program

Item 1 is done and negative. The standing program continues — item 2 (extend labelled data
backward) is the next one, and it is also the one most likely to change an answer: every negative
result so far has been fought on 5–8 days of labelled data, and R-8 already showed a retrain
handicapped by exactly that.

Stake and gates untouched. Kelly stays out (two-confirmation rule).

Token budget: R-9 item 1, ~45k.
