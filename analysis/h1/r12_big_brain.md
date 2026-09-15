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
