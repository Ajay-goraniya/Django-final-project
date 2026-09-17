# R-26 artifacts for the EV grid split

`y` **is `venues.outcome`** — verified at source, not assumed: `task_r8_taker_feature.oracle()` is
`select epoch,actual from outcome` against `venues.sqlite3`, and `lane_ticks` carries it through as
`actual`. Polymarket settles on that oracle, so it is the right label for these rows.

| file | what it is |
|---|---|
| `model_b_week1.json` | **arm (b)** — week-1-only fit, 30 features. Coefficients, scaler and intercept are **identical to `learner/v12_2/model_v10.json` at 0.000e+00**; the only difference is the isotonic (152 knots vs 116, `GroupKFold(4)` vs `(8)`). This is the arm worth $36. |
| `model_c_<day>.json` × 9 | **arm (c)** — one fit per test day, trained on week 1 + week-2 days *before* that day (22,720 → 56,773 rows). Walk-forward is the point; a single pooled (c) json would leak the test day into its own fit. |
| `week2_features.parquet` | 34,121 rows / 1,906 candles, 33 columns named to match `v10_features_8days.parquet` so V's harness loads it unchanged. `lv`, `mv_x_sec`, `lv_x_sec` are **omitted** because `ev_grid.py` derives them from `p_venue`/`move_bps`/`sec_left`. `ask_up`/`ask_dn` finite on 100.0% of rows. |
| `ev_grid_c.txt` | the full (c) grid — 12 thresholds × 5 slippage levels, per day, every cell. |

4.1 MB total. No tapes.

## My half of the split: the (c) grid, and V's shape question

Whole grid in `ev_grid_c.txt`. Total PnL, 0 cents: 0.05 **+171.80** (1498 fires) · 0.10 **+185.80**
(1115) · 0.15 **+192.63** (817) · 0.20 **+200.76** (603) · 0.25 **+161.50** (439) · 0.30 **+129.52**
(328), falling to +45.50 at 0.60 (64).

**The answer to the shape question: the curve is not flat, and the fire count swings twice as hard.**

| slippage | total PnL across 0.10–0.30 | spread | fire count | swing |
|---|---|---|---|---|
| +0c | +129.52 … +200.76 | 35% of max | 328 … 1115 | **71%** |
| +1c | +117.66 … +181.62 | 35% | same | 71% |
| +3c | +95.77 … +146.10 | 34% | same | 71% |
| +5c | +59.35 … +113.82 | 48% | same | 71% |

So the threshold *is* a lever on total — but **per $1 is monotone across the entire range** (+0.115 at
0.05 rising without a turning point to +0.711 at 0.60). There is no optimum, only a volume-for-price
trade, which is R-19's cheapness sort seen through the frequency dial. **The fragility reading is the
right one:** the total moves 35% while the fire count moves 71%, so most of what the threshold does is
change how many candles you are in, not how good they are.

**The sensitivity, sized.** R-26's calibrator difference — isotonic on 4 folds instead of 8, a median
|Δp| of 0.0077, identical coefficients — was worth **$36** across 1,033 fires. On this grid, moving the
threshold from 0.25 to 0.20 is worth **$39** and 164 fires. **An arbitrary fitting detail in the
calibrator is worth about as much as a five-point threshold move.** That is the fragility to design
out, and it is why I am not reading 0.20 off this table as a recommendation — a best cell chosen from
a twelve-row sweep, on a metric whose per-$1 curve never turns over, is exactly what the standing rule
forbids.

**Per day at 0 cents**, every day, never the best: at thr 0.20 the seven readable days are
+42.75 / +61.03 / +34.55 / +24.82 / +8.61 / +12.40 / +0.97 — all positive. At 0.25: +18.57 / +44.98 /
+40.07 / +19.46 / +8.55 / +14.64 / +2.41 — also all positive. 09-08 and 09-16 are insufficient at
every threshold and are not read.
