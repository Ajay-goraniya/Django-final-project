# REQUEST.md — V → H1 (single channel; H1 answers in analysis/h1/ and STATE.md)

## Task R-1 (09-14 00:2x UTC) — THE POLYMARKET REGIME GRID. Measurement only. Buckets are fixed below; do not add or move one.

**Why:** user, 09-14 00:0x: *"make it live when Market is good."* That is a regime switch, and the standing
rule is binding: **buckets FIRST, whole grid, never the best cell.** The engine will later self-verdict
each cell from live outcomes (AUTOPILOT 11.4 §E2); nothing arms on this grid directly. Scope is
**Polymarket only** (Tokyo/Predict.fun are out as of 09-13 22:3x).

**Data (all real, all on the branch or in V's scratchpad):**
1. Polymarket v12 paper lane — `learner/live_backup/v12_poly_weekend.sqlite3.gz` (snapshot 09-13 21:50;
   `trades` 317 graded + `decisions` 7,280 rows with `p, ask, ev, fire` per candle). V will refresh the
   snapshot on request.
2. Polymarket v10 paper — `/tmp/v10_long4.sqlite3` on V's box, 776 graded (`trades`: `ts_ms, pnl, stake,
   ask, ev, sec, rv60, feat`). V will snapshot it to `live_backup/` on request.
3. The A/B twins (`scratchpad/twins/{ctrl,cand}/twin.sqlite3`, launched 09-13 23:37) — as they grow.
4. Kline set for the bucket features — your 73,679-candle REST-mirror set.

**Grade everything on `candles.actual` (Binance close ≥ open).** Paper's own `win` column is
oracle-flattered (32 of 156 disagree, REMAKE_PLAN §2a); do not use it.

**Buckets — Task 13's, fixed in advance, every cell reported:**
- UTC 8-h block: 00–08 / 08–16 / 16–24
- weekday / weekend
- trailing-range quartile, cuts from the 252-day set: 31.4 / 48.9 / 76.4 bps
- flips of the open in the last 6 candles: 0–1 / 2–3 / 4+
- book width at the fire: tight / wide (your existing cut)

**Per cell:** n graded, PnL per $1, hit rate, both halves (chronological), `verify.py` verdict. **Under 60
= "insufficient", reported anyway.** No cell is read that fails halves. No recommendation to gate — the
deliverable is the grid and which cells are positive both halves at >= 60, full stop.

**Also, because it is the one regime effect already on the record:** the weekend tape is thinner
(10.9 vs 17.7 bps) and Task 13's only negative cell was the busiest quartile at n=24. Report that cell
first with today's n.

Write the result to `analysis/h1/task_r1_polymarket_regime_grid.md`, update `STATE.md`, commit, push.
V reads it before anything is designed. If any dataset cannot be used honestly (clock skew, missing
features at the fire second), say which and how many rows rather than reconstructing.
