# Findings for the next version (running log, 2026-09-08)

## Bugs found live (fixed in code, already shipped)
- Candle-open fires priced from the previous market's 0.01 loser side (engine). Fix: quote only the current candle's market. Executor has the same hole (NOT fixed, engine-side).
- Dust-ask fires when the book is one-sided (runner 18:44). Fix: no fire if venue quote incomplete; decide only 15-240 s.
- Binance perp @trade "NA" prints with p=0 -> basis_bps -10000 -> p pinned 0.99. Fix: drop non-positive prices.
- Per-tick feature pass starved the phone engine thread. Fix: 2 decisions/s.

## Model / learner (not applied, for v11)
- Confidence floor in pnl mode: p=0.51 fires ran 1/6 live; p=0.68 fires 6/7. Cheap asks inflate EV of ignorant fires.
- Fee per venue: Predict.fun = 2% of notional (cost = ask*1.02), model assumes 7% of payout.
- Signal from Polymarket book (leader wins 78% vs Predict.fun 74%; on disagreement 142:59), execute on Predict.fun (leader 6-8c cheaper, gap widens with confidence and in the last minute).
- Both venues' prices + their gap as features. Polymarket websocket (free) for the signal.
- High-vol regime is where the model is weakest live (3/8) while it dominates tonight's mix; training week was balanced.
- Timing: Predict.fun early fires (15-60 s) 2/6 tonight; watch.
- Retrain on today's recorded data (Predict.fun book + Polymarket ws book + Binance) as a new regime day; validate day-out.

## 19:43 UTC check-in
- Engine (Predict.fun) EF 4/10, -26; runner (Polymarket) 7/13, +11. Engine's last 5 fires all DOWN and all lost (BTC grinding up; model chasing intra-candle dips in a high-vol uptrend).
- High-vol regime: engine 1/4, runner 4/8. Training week balanced; tonight ~55% of fires are high-vol. -> regime-specific EV threshold should be higher in high vol, or a trend filter (prev1/prev2 sign vs fire side).
- Claimed p vs realized (pooled, n=23): p<=0.55 -> 1/7; p 0.59-0.63 -> 4/6; p 0.68 -> 6/8. Confidence floor ~0.58 in pnl mode would have removed 7 fires, 6 of them losses.
- Venue: Predict.fun fires priced higher (median 0.52 vs 0.46) AND lose more on the same candles -> the cheaper Polymarket entry is doing part of the work.
- Timing: Predict.fun early-window fires 2/6 vs Polymarket 5/7. Same seconds, different book -> Predict.fun's early book is less informative.

## 20:14 UTC check-in
- Engine 5/11, -18.7; runner 10/17, +39.0. Runner outperforming on the same candles: cheaper entries (median 0.46 vs 0.52) and better early-window book (7/10 vs 2/6).
- Pooled calibration n=28: p<=0.55 -> 2/9; p 0.59-0.63 -> 5/7; p>=0.68 -> 7/12 (the 0.70/0.73 fires 1/3). Floor ~0.58 still the cleanest single change.
- High vol: engine 1/4, runner 5/10. Mid vol runner 3/4. Regime mix still high-heavy vs balanced training.
- Venue gap stable: -0.078 mean, leaders agree 88%, Polymarket right on disagreement 205:98 (2:1). Signal-from-Polymarket idea keeps strengthening.
- No bugs; r3 window guard visibly working ("outside decision window" at 285 s).

## 20:46 UTC check-in
- Engine 5/11, -18.7 (no fire in the last 40 min; Predict.fun asks 0.56-0.59 on the model's side keep EV under threshold). Runner 12/19, +53.3, four straight wins.
- Runner high-vol now 6/11, mid 4/5. Engine high-vol still 1/4. Predict.fun's book in high vol is where the two venues diverge most.
- Calibration n=30: p<=0.55 -> 2/9; 0.59-0.63 -> 5/7; >=0.68 -> 9/14. Floor 0.58 keeps holding.
- Frequency: runner 20 fires in 3.25 h (~6/h, ~150/day pace, above the 62/day backtest pace) - tonight's high vol makes cheap contrarian asks common. Engine 11 fires (~3.4/h). Regime-adaptive frequency should tighten in high vol, not loosen.
- Venue gap unchanged (-0.077); Polymarket leader right 215:100 on disagreement.

## Regime timeline (17:30-21:30 UTC, 30-min windows)
- 18:00-18:30 calm uptrend (rv60 0.19, +29 bps): EF 7/8 across both venues.
- 19:00-20:00 high-vol chop (rv60 0.39, ~45% of samples in the high tercile, net flat): Predict.fun EF 0/3, Polymarket EF 5/8 (cheap entries carried it).
- 21:00+ calm again (rv60 0.18).
- The regime flips are visible in rv60 alone, ~10 min ahead of the drawdown. The learner's job in v11: regime detection on rv60 (+ range_bps) driving (a) the EV threshold up in high vol, (b) a trend filter, (c) frequency down. Fixed thresholds per tercile (v10) are not enough because the terciles were fitted on a calmer week.
- Note: Build 10 still runs the Build36 EFLearner on settlements, but it no longer influences fires (v10 decides). Its adaptation is dead weight in this build; either wire it to adjust v10's thresholds online or remove it.

## 21:17 UTC check-in
- Engine pnl 6/15, -30.7; runner 14/24, +42.7; accuracy-mode engine warming (live from ~21:21).
- Calibration n=39: p<=0.55 -> 3/12 (25%); p 0.59 -> 1/4; p>=0.62 -> 15/23 (65%). Floor ~0.60 is now cleaner than 0.58.
- Engine mid-window fires (60-180 s) 2/6, -21: on Predict.fun the mid-candle contrarian fires are the worst bucket.
- Polymarket leader right 287:108 on disagreement (2.7:1) over 69 candles; gap -0.082.

## Retro test of the loss filters on tonight's 39 graded fires (both venues)
- baseline 20/39, +12.0
- confidence floor p>=0.60: 16/23, +64.0 (removed 12 losses, 4 wins)  <- the only one that clearly works
- high-vol EV>=0.30: 15/31, -4.1 (removed 3 losses, 5 wins)  <- as a simple rule it HURTS; the high-vol problem is on Predict.fun only, Polymarket high-vol fires were 8/13
- trend filter (no fade of prev candle): 12/24, -16.1 (removed 7 losses, 8 wins)  <- does not work as a simple rule; drop it
- floor + high-vol: 12/18, +39.2 (worse than floor alone)
Conclusion: regime handling must be venue-aware and learned, not a hand rule; the confidence floor is the one hand rule justified by tonight.
