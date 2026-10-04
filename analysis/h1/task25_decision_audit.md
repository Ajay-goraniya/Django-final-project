# Task 25 — audit the PROCESS of the v12 Polymarket lane, not its PnL

V, 09-11 18:20: *"we keep grading PnL and never verify how the decision was actually produced."*
Script: `analysis/h1/task25_decision_audit.py`. Sample: **420 trades + 9,386 decisions** from
`v12_poly_lane.sqlite3` (2026-09-11 13:55 → 09-14 14:20).

Everything below runs the **engine's own module** (`learner/v12_checkpoint/btc_model_v10.py`) and
the **engine's own model file** (`model_v10.json`, md5 `b5088f150c916a7522ce9159d4ed5e58`, identical
to `learner/model_v10.json`). Nothing here re-implements the engine — that is the 09-12/13 failure
mode and this task is the one where it would hurt most.

## A. Model application — VERIFIED

Feed the lane's own recorded `feat` vector to the engine's own `Model.p_up`:

| table | n | max \|p error\| | median | side reproduced |
|---|---|---|---|---|
| trades | 420 | 4.75e-05 | 2.14e-05 | **420/420** |
| decisions | 9,386 | 6.63e-05 | 1.79e-05 | **9,386/9,386** |

The lane stores `p` to 4 decimals, so ~5e-05 **is** exact agreement. The model file on the branch
is the model that produced these probabilities, the feature order matches, the scaler and the
isotonic calibration are the ones that ran. **9,806 decisions, zero disagreements.**

## B. Feature construction from raw inputs — price block VERIFIED

Rebuilt from Binance 1 s klines by driving the engine's own `FeatureState`, on all 420 trades
(0 skipped). Absolute differences vs the recorded `feat`:

| feature | median | p90 | max |
|---|---|---|---|
| move_bps | 0.0013 | 1.02 | 10.6 |
| ret5 / ret15 / ret30 / ret60 | ~0.0010 | 0.77–0.86 | 6.1–11.3 |
| rv60 | 0.00056 | 0.072 | 0.48 |
| range_bps | 0.00071 | 0.59 | 6.06 |
| pos_in_range | 0 | 0.14 | 1.0 |
| dist_hi_bps / dist_lo_bps | ~0.0005 | 0.42–0.47 | 5.4–6.1 |
| prev1_bps / prev2_bps | 0.0014 | 1.01–1.11 | 5.1 / 80.4 |
| sec_left | 0.00046 | 0.0009 | 0.001 |
| hod_sin / hod_cos | 2.4e-07 | 4.5e-07 | 4.9e-07 |
| mv_x_sec | 0.00096 | 0.72 | 9.9 |

Units are bps, so a median of 0.001 bps is agreement to the last digit the engine stored. The p90
of ~1 bps and the tails are what a **1 s grid vs a per-trade tape** must produce: the engine saw
ticks, this rebuild sees one close per second. `sec_left` and the hour-of-day pair reproduce to
floating-point. The single `prev2_bps` outlier (80 bps) sits on a candle where `paths.npz`
forward-fills a gap; it is one row of 420 and is left in rather than dropped.

**No feature was fabricated, mis-timed, or carried from a different candle.**

## B2. What this audit CANNOT reach — measured, not asserted

My 1 Hz `polybook` ask vs the engine's own recorded `_ask_up`, same second: n=282, **median \|d\| =
0.0100 — exactly one tick**, p90 0.10, inside one tick on 59%. The lane's own `quote_age_ms` is a
median 19 ms.

R-3 §5 measured this book moving a **median +1.0c per second**. So a 1 Hz logger and a live reader
sampling under a second apart *must* disagree by about a tick. **A one-tick median disagreement is
this instrument's floor, not evidence about the engine.** The venue-derived features
(`p_venue`, `lv`, `lv_x_sec`) are therefore reported as **not auditable at 1 Hz** — neither passing
nor failing. This is the same conclusion V reached from the other side with `poly1s` (22 of 40
within a tick), reached here independently.

Eleven features are **not verified at all**, because H1 has none of the feeds they need:
`spot_imb15`, `spot_imb60` (spot trade size + aggressor flag), `ofi5`, `ofi15`, `ofi60`,
`perp_n15`, `basis_bps` (Binance perp tape), `spread_bps`, `imb5`, `imb20`, `micro_bps` (Binance
spot depth). Listed as unverified, not counted as passing.

## C. Decision arithmetic — VERIFIED

| check | result |
|---|---|
| recomputed EV vs recorded `signal_ev`, via the engine's own `Model.cost()` | n=420, max \|d\| **1.7e-04** |
| `quote_ask` equals the `feat` vector's own ask for the chosen side | **0/420 mismatches** |
| `sec` equals `int(300 - sec_left)` from the same vector | **0/420 mismatches** |

*(My first pass reported 206/420 `sec` mismatches. That was my error: the engine floors the value
and I compared against `round()`. Corrected before reporting — it is exactly the manufactured
discrepancy this project keeps paying for.)*

## Verification gate

`verify.py` run. This task makes **no PnL claim and touches no outcome label**, so `grading()`,
`halves()`, `permutation()`, `sweep()`, `costs()`, `null()` and `paired()` have nothing to act on —
there is no edge here that could be an artifact. The applicable gates, `sample()` (420 / 9,386,
both far past the bar) and `quote_age()` (at-or-after; parts A and C read the lane's own vector at
its own decision instant), both PASS. Stated rather than silently skipped.

## Verdict

**The v12 lane's decision path is verified end to end for the first time, on the half that can be
verified.** Given the recorded inputs, the recorded probability, side, EV and timing are exactly
what the frozen v10 model and the engine's own code produce — across 9,806 decisions, not a
handful. The price half of the feature vector independently reproduces from raw Binance klines.

The remaining gap is instrumentation, not suspicion: the venue block needs a logger faster than
1 Hz, and eleven microstructure features need the perp and depth feeds. **If V wants that half
closed, the cheapest route is a >1 Hz book capture on the AWS box; nothing on the branch can do it.**

Reminder V asked to carry: this lane fills at the quoted ask with slippage 0.0 by construction, so
its PnL is an **upper bound** and must never be compared like-for-like with a live fill.
