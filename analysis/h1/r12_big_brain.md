# R-12 — big-regime retrain. Reply 1: data plan, footprint, ETA

1. **Plan:** spot 1s klines, monthly zips, **2017-08 → 2026-09 (110 months)**, streamed one month at a
   time (download → extract features → delete). Futures **1m** klines (1.9 MB/mo) for the perp block.
   Measured, not estimated: 7.2 s/month to fetch+unzip, 1.4 s to parse 2.59M rows.
2. **Footprint: ~10 GB transferred, peak disk < 1 GB** (24 GB free now), derived store ~120 MB
   (float32, ~700k candles × 21 features). **ETA ~45-60 min** to extract, ~1-2 h to train + walk-forward.
3. **Constraint that changes the design — 9 of v10's 30 features cannot be rebuilt historically.**
   Exact from 1s klines: the 16 price-path features **plus `spot_imb15`/`spot_imb60`** (1s klines carry
   taker-buy base volume) = **18**. Approximated at 1-min from futures klines: `basis_bps`, `ofi60`,
   `perp_n15` = **3**. **Unavailable at any sane cost: `ofi5`, `ofi15` (need per-trade perp — 69 GB of
   aggTrades), and `spread_bps`/`imb5`/`imb20`/`micro_bps` (need L2 depth; bookTicker is 6.7 GB/mo AND
   top-of-book only, so imb5/imb20 are impossible regardless)**, plus the 3 venue features the brief
   already excludes.
4. **This is safe to do and here is why:** `FeatureState` itself zero-fills exactly those when the feed
   is absent (`spread, imb5, imb20, micro = (0,0,0,0) if not self.depth`; ofi/perp return 0.0 on an empty
   deque). So the historical stage trains on the 18+3 that exist, the 9 carry **zero coefficients**, and
   the json stays a drop-in. **The risk I will measure and report: train/serve skew** — a model fitted
   with those 9 at zero, then served where they are populated, is not the same model.
5. **Order:** pipeline check first (retrain the 8 days with the new pipeline, must reproduce frozen v10
   within noise) → then the big run. No in-sample numbers in the final report.

## Progress — stage 1 (data) running, stage A (parity) running

**Plan approved 22:49 with the addendum "serve the 9 unbuildable zeroed too, feature mask in json,
so train == serve". Taken, and extended by three — stated here rather than silently:**
`basis_bps`, `ofi60`, `perp_n15` are **masked as well, not approximated.** Reply 1 said they would
come from futures 1m klines. A 1m bar is minute-aligned rather than trailing, and `perp_n15` is a
15-second count a 1m bar cannot express at all — so feeding them at train time while serve computes
the precise value is exactly the skew the addendum exists to remove. **Mask is 12; 18 features are
built.** Futures 1s klines do not exist (404), so there is no cheaper honest route.

Built (18, exactly as `FeatureState` computes them): the 16 price-path features **plus
`spot_imb15`/`spot_imb60`** — 1s klines carry taker-buy base volume, so taker sell = volume − taker
buy, the same quantity the engine accumulates from the trade stream.

- **stage 1 extraction:** running, ~8.8 s/month measured, 110 months, ~43k rows/month
  (8,637 candles × 5 sampled decision seconds in the 15–240 s window). Streams one month at a time
  and deletes the raw, so peak disk stays under 1 GB. Script `analysis/h1/r12_extract.py`.
- **stage A parity — the check that decides whether any of this is worth reading:** V asked for
  "retrain the 8 days, must reproduce v10 within noise". **That is not literally runnable** — v10
  was built from 2026-08-29..09-06 with all 30 features and no 30-feature vectors exist for those
  days on this branch (logged `feat` starts 09-08). The substitute is stronger for what can
  actually be wrong: recompute my kline-derived features **at the engine's own decision seconds**
  over the logged window and compare value-by-value against the `feat` it recorded at that instant.
  Verify against the running artifact, not a re-derivation. Script `analysis/h1/r12_parity.py`.

## Stage A — extractor parity: **PASSES**, after a silent corruption caught first

**A bug had to be fixed before this could be run, and it would have poisoned everything downstream.**
Binance **changed the timestamp unit partway through the archive** — older monthly 1s-kline files
stamp `open_time` in milliseconds, newer ones in microseconds. Reading a microsecond stamp as ms
does not raise: it puts the candle loop's start a thousand-fold too high, so it runs ~288k times per
day over a ~700 MB index array and **emits nonsense**. One day of 2026-09-12 built **863,982 rows
where 864 were expected**. Caught because the row count was implausible, not because a check fired.
The unit is now detected per file from magnitude. None of the 67 months already extracted were
affected — the format change falls later in the range — so no completed work was lost.

Parity, 24,805 of 25,317 logged ticks joined across 2026-09-08..09-14
(09-15's daily file is not published yet — the documented one-day lag):

| feature | median \|diff\| | feature | median \|diff\| |
|---|---|---|---|
| ret5 / ret15 / ret30 / ret60 | **~5e-07 bps** | move_bps | 0.0013 bps |
| range_bps, pos_in_range, dist_hi, dist_lo | **~1e-06** | rv60 | 0.0014 |
| hod_sin / hod_cos | 2.4e-07 | prev1_bps / prev2_bps | 0.0013 |
| **spot_imb15 / spot_imb60** | **0.0025 / 0.00057** | mv_x_sec | 0.0049 |
| `sec_left` | 0.458 — see below | | |

**The extractor reproduces the engine's own logged numbers.** `sec_left` is the one large value and
it is **not an error**: mine is an integer second by construction, the engine computes
`(now_us − candle_open_us)/1e6` with sub-second precision, so the difference is uniform in [0,1)
and its median *must* be ~0.5. Observed 0.458. Every other feature agrees to 1e-3 bps or better at
the median; the p90/max columns are the same 1s-grid-vs-tick-tape residual R-8 and Task 25 already
measured.

Stage 1 extraction: 71 of 110 months done, ~10 s/month.
