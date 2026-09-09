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

## 21:48 UTC check-in
- pnl engine 9/19, -14.9 (three straight wins 21:30-21:40); runner 17/27, +74.8; accuracy-mode engine 4/5, +2.5 (asks 0.70-0.88, tiny payoff per win, as in backtest).
- Retro floor test, 46 pooled fires: none 26/46 +60 | p>=0.56 22/33 +78 | p>=0.60 20/28 +87 | p>=0.65 15/21 +56. Floor 0.60 still best: +45% PnL with 39% fewer fires. Frequency lever: floor 0.56 keeps 72% of fires at +30%.
- Calibration: p 0.51 bucket recovered to 4/10; p>=0.62 buckets 22/29 (76%).
- Polymarket early-window fires now 10/13 +62; Predict.fun early 3/7. The venue difference is concentrated in the first minute.
- Regime: high-vol on Polymarket 9/14 +53 - high vol is profitable THERE (cheap contrarian asks); on Predict.fun 3/7. Confirms: regime handling must be venue-aware.
- No bugs. Accuracy-mode engine behaving as designed.

## 22:19 UTC check-in
- Predict pnl 11/21 +1.0; Predict accuracy 7/8 +11.3; Poly pnl 19/30 +77.5; Poly accuracy warming (live 22:25).
- Retro on 51 pooled fires: none 30/51 +78 | p>=0.56 26/38 +97 | p>=0.60 23/32 +95 | p>=0.65 18/24 +75. Floor 0.56-0.60 both good; 0.56 keeps more fires for the same PnL -> frequency dial range 0.56-0.60.
- Per venue with floor 0.60: Polymarket 16/20 +94 (from 19/30 +77); Predict.fun 7/12 +2 (from 11/21 +1). The floor fixes accuracy on both, PnL only on Polymarket: Predict.fun's remaining problem is price, not selection.
- NEW: entry price split. ask<=0.45 fires 5/16 -27; ask>0.45 fires 25/35 +105. Tonight the cheap contrarian entries are the losers, opposite of the 8-day backtest where cheap entries were ~break-even and the edge came from disagreement. Candidate rule: min ask 0.45 (or equivalently p floor, they overlap). Needs more days before trusting; note the backtest had this regime under-represented.
- Polymarket early-window 11/14 +70 remains the single best bucket: Polymarket book + first minute + p>=0.6 is where the money is tonight.
- Venue gap -0.082; Polymarket right on disagreement 357:119 (3:1) over 81 candles.
- No bugs, 5 processes healthy.

## 22:51 UTC check-in
- Predict pnl 12/23 +2.3; Predict accuracy 11/13 +11.0; Poly pnl 21/33 +90.3; Poly accuracy 3/3 +8.2 (live since 22:25).
- Retro on 56 pooled fires: none 33/56 +93 | p>=0.56 28/42 +96 | p>=0.60 24/33 +104 | ask>0.45 26/36 +113 | p>=0.56 & ask>0.45 26/36 +113 (identical set to ask>0.45 alone).
- Calibration bins: p 0.50-0.56 5/14 -4 | 0.56-0.62 4/9 -8 | 0.62-0.70 21/28 +106 | 0.70+ 3/5 -2. ALL the profit is in the 0.62-0.70 band. Below it the model is guessing; above it the ask is too high for the hit rate. -> v11 pnl rule: p in [0.62, 0.70] band, or EV recomputed with realized calibration per band (the isotonic map is off live: claimed 0.68 realizes 0.75, claimed 0.51 realizes 0.36).
- Accuracy mode: both venues ~85-100% on 16 fires but +$19 total: consistent with backtest (small margin per win). Accuracy mode is the safe product; pnl mode with the 0.62-0.70 band is the money product.
- Polymarket early window 13/17 +82 (still the best bucket). Predict.fun early recovered to 5/10.
- Venue gap -0.084; Polymarket right on disagreement 384:150 over 87 candles.
- No bugs; 5 processes healthy.

## 23:23 UTC check-in (backup taken 23:23; pushed 23:20)
- Predict pnl 15/27 +13.9; Predict acc 15/18 +12.0; Poly pnl 25/39 +110.1; Poly acc 6/7 +6.4. Five processes healthy, 14 GB free.
- Retro on 66 pooled fires: none 40/66 +124 | p>=0.56 35/50 +148 | p>=0.60 28/38 +124 | ask>0.45 32/43 +153 | band 0.62-0.70 23/30 +123.
  -> The 0.56-0.62 bin recovered (7/12 +24); the only consistently negative bin is p<0.56 (5/16 -24). Best rules now: ask>0.45 (+23% PnL, 65% of fires kept) and p>=0.56 (+19%, 76% kept). These are the frequency dial candidates for v11: p floor 0.56 = high frequency, ask>0.45 = high PnL.
- Predict.fun pnl engine has recovered to +14 as vol dropped (low-vol fires 10/14 +37). Its problem is specifically mid-vol/high-vol (0/3, 5/10).
- Polymarket early window 15/21 +82: still the money bucket.
- Venue gap -0.083; Polymarket right on disagreement 454:189 over 94 candles.

## 23:55 UTC check-in (backup 23:55 local; last push 23:23)
- Predict pnl 17/30 +21.1; Predict acc 18/22 +10.2; Poly pnl 28/43 +140.2; Poly acc 9/11 +3.7. Five processes healthy, 14 GB free.
- Retro on 73 pooled fires: none 45/73 +161 | p>=0.56 37/53 +155 | p>=0.60 30/40 +141 | ask>0.45 34/46 +161. In the calm regime since ~21:00 the low-p / cheap-ask fires have started winning (p<0.56 bin now 8/20 +7, was 5/16 -24 at 23:23). So the filters' benefit is REGIME-SPECIFIC: they save money in high vol and cost fires in calm markets. -> v11: the floor / min-ask must be a function of regime (learner-set), not a constant. This is the concrete "adjustable frequency" mechanism: floor high in high vol, low in calm.
- Calibration bins: 0.62-0.70 still the core (25/32 +140).
- Frequency: Poly pnl 45 fires in 6.4 h (~7/h); Predict pnl 31 (~5/h); accuracy modes ~4-8/h.
- Venue gap -0.084; leaders agree 83%; Polymarket right on disagreement 519:222 over 100 candles.
- No bugs.

## 00:27 UTC check-in (2026-09-09; backup 00:28)
- Predict pnl 18/32 +24.5; Predict acc 22/26 +18.1; Poly pnl 29/45 +139.9; Poly acc 10/13 -3.8. Five processes healthy, 14 GB free.
- retro on 77 fires: none 47/77 +164 | p>=0.56 38/56 +144 | ask>0.45 35/49 +150
- calibration bins: p0.50-0.56 9/21 +20 | p0.56-0.62 8/14 +24 | p0.62-0.70 25/34 +120 | p0.70-1.00 5/8 +1
- last hour both venues: 3/6 +6  (quiet overnight market: fewer fires, mixed results)
- Polymarket accuracy mode slipped negative (10/13, -3.8): at asks ~0.8, 3 losses cost more than 10 wins earn. Accuracy mode needs >85% to pay at those prices; tonight it is 77-85%. -> for v11, accuracy mode's floors should be venue-specific and its stake rule should size by payoff, not flat.
- Predict.fun early-window fires back to 7/14 -1: first-minute Predict.fun book remains unreliable; mid-window on Predict.fun is 8/13 +22. -> venue-specific timing window (Polymarket early, Predict.fun mid).
- Venue gap -0.081; Polymarket right on disagreement 542:242 over 107 candles.

## 00:59 UTC check-in (backup 00:59)
- Predict pnl 19/33 +33.4; Predict acc 24/31 -7.2; Poly pnl 30/48 +135.8; Poly acc 13/18 -12.4. Five processes healthy, 14 GB free.
- BOTH accuracy modes are now negative despite 72-77% hit rates: at asks of ~0.80 the break-even is ~81%, and in this quiet market the leader is not converting at the 87% the backtest week showed. -> accuracy mode is structurally fragile: it buys the leader at the market's own price and needs the market to be UNDER-confident. v11 accuracy mode: require p_model - ask >= margin (e.g. 0.05) instead of a raw confidence floor, so it only takes the leader when the model sees more than the price does.
- Pnl modes hold: Poly +136 (62%), Predict +33 (58%).
- Retro on 81 fires: none 49/81 +169 | p>=0.56 +143 | ask>0.45 +149: constant filters keep losing value as the market stays calm (p<0.56 bin 10/23 +26). Regime-dependent floor confirmed as the right shape.
- Venue gap -0.082; Polymarket right on disagreement 560:245 over 113 candles.
- No bugs.

## 01:31 UTC check-in (backup 01:32)
- Predict pnl 19/36 +3.4; Predict acc 29/38 -12.9; Poly pnl 32/52 +139.9; Poly acc 16/23 -23.9. Five processes healthy, 14 GB free.
- Bad hour: 2/9 -46 across both venues (00:30-01:30 UTC, Asian-session drift; BTC low activity). Predict pnl gave back +30; Poly pnl flat.
- Accuracy modes now -13 / -24: 76% / 70% hit rates at ~0.80 asks. The 87% backtest number for accuracy mode was a daytime-regime number; overnight the leader converts ~75%. -> accuracy mode must (a) use a margin rule p_model - ask >= 0.05, (b) shut off (or drop to pnl mode) when the recent realized leader-conversion rate falls under break-even; a rolling 20-trade conversion rate is a cheap live signal for that.
- Calibration: p 0.62-0.70 27/36 +138 remains the only solidly profitable bin; p 0.70+ is 5/9 -9. High-confidence fires are NOT paying at the asks they get -> the isotonic map over-trusts the top; recalibrate on live data.
- Venue gap -0.079; Polymarket right on disagreement 592:269 over 120 candles.
- No bugs, no restarts.

## Correction (01:45 UTC): the 0.62-0.70 band is NOT a gate
- Every cheap entry (ask<=0.45) tonight has p<0.62 because p_venue/lv dominate the logit; a p band would remove all cheap entries. Cheap entries tonight: 14/35 -5 (break-even); mid-price agree-with-market fires: 28/37 +148. In the 8-day backtest cheap entries carried the edge. Regime, not rule.
- v11 change is model-side: (a) recalibrate p on cheap entries so BTC evidence is not swamped by the venue feature (separate calibration by ask bucket, or interaction terms venue x BTC features), (b) the regime-dependent floor decides how many cheap entries to take. Do NOT hard-gate on p band or ask level.

## Session split (17:21-01:40 UTC, EF pnl runs)
- US/EU-overlap (13-21): Poly 13/22 +43, Predict 6/13 -11.  Late US (21-01): Poly 17/27 +82, Predict 13/20 +44.  Asia (01-08): Poly 3/5 +15, Predict 0/5 -50 (early, few fires).
- Hourly pooled: 21:00 +46 and 23:00 +58 best; 01:00 -35 worst. The model's edge is largest in the late-US hours (moderate vol, active books) and weakest in the Asia drift (thin books, Predict.fun especially). Only one day - do not hard-code hours; use it as a prior and let the regime floor (rv60 + book depth/activity) handle it. Add hour-of-day is already a feature (hod_sin/cos) - but trained on one week; needs more days.


## Two-book rule for v11 (agreed with user, 02:00 UTC 2026-09-09)
- Predict.fun is THE platform: market discovery, candle id, current market, book state, empty-book handling, size at ask, fee (2% of notional), fills, settlement, hot orders. Polymarket is unavailable for trading in the user's region.
- Polymarket book (CLOB websocket, fresh, from a machine near their servers) is an INPUT only: it supplies the venue features (ask_up/ask_dn, implied probability, leader) to the model. It never selects the market, never sets the price used for EV/break-even/order, never drives the candle id.
- Keying: Polymarket quotes are attached to Predict.fun's candle id/market; if the Polymarket feed is stale, one-sided, or on a different candle, the lane falls back to Predict.fun's own quote for the features or waits. Engine keeps running on Predict.fun alone when Polymarket is down.
- Every price in EV, size check and order = Predict.fun ask. Require Predict.fun size at the ask >= stake before a fire counts (cheap price with 5 shares is not a trade).
- Purpose: get the Polymarket-signal PnL curve (+$130 tonight) executed on Predict.fun without book-mismatch bugs (the two bugs found live tonight were both book-mismatch: old-market ask at candle open, one-sided dust ask near close).

## 02:03 UTC check-in - INCIDENT and restart (2026-09-09)
- The container was restarted at ~01:42 UTC. Processes survived but the local egress proxy port changed (37271 -> 43519); all five kept retrying the dead port ("Connection refused"), so every feed (Binance spot/perp/depth, Predict.fun book, Polymarket ws) was down from ~01:42 to 02:07 UTC. No fires, no venue samples in that window. Databases intact.
- All five relaunched at 02:06 WITHOUT reset (new `restart_all.sh` relaunches only what is missing, never resets). Histories kept: Predict pnl 38 fires, Poly pnl 56, Predict acc 40, Poly acc 25. Feeds and both books live again by 02:07. ~25 min gap in the record.
- Ops lesson for the phone/VPS deployment: on network-path changes the engine's reconnect loop must re-resolve the proxy/route (or run without a proxy); a watchdog on "feed age > 120 s" should restart the process.
- States at 02:07: Predict pnl 19/38 -16.6; Predict acc 29/40 -32.9; Poly pnl 33/56 +120.3; Poly acc 16/25 -43.9 (the two pending Poly pnl trades settled as losses).
- Retro on 92 fires: none 52/92 +124 | p>=0.56 +123 | ask>0.45 +129. Calibration: p 0.62-0.70 28/37 +148; p 0.70+ 5/10 -19; below 0.62 roughly flat. Overnight (00:30-02:00) 2/9 -51 pooled.
- Staking check on tonight's Poly pnl sequence and the 8-day OOS trades: hybrid ~= fixed 10% (152 vs 150 tonight; 4109 vs 4248 on 8 days); drawdown brakes and quarter-Kelly reduce return without reducing the capped-stake drawdown (486 on 8 days is the $50-cap era, ~10 losses in a row). Danger zone is the first $50-100 (20% DD from a 2-loss start). Keep hybrid.

## 02:37 UTC check-in (backup 02:37) - all five healthy after the 02:06 relaunch, feeds live
- Predict pnl 21/40 -3.1; Predict acc 32/44 -33.1; Poly pnl 35/58 +132.8; Poly acc 18/28 -47.7. Last hour pooled 4/5 +16.
- Retro on 98 fires: none 56/98 +130 | p>=0.56 45/69 +139 | ask>0.45 42/62 +145 (filters back to slightly positive as the market thinned again). Calibration: p 0.62-0.70 28/38 +138; p 0.70+ 9/14 +7; below 0.62 11-8/46 -15.
- Venue gap -0.079; Polymarket right on disagreement 610:303 over 133 candles.
- No bugs, no restarts since 02:06, 14 GB free.

## 03:10 UTC check-in (backup 03:10) - five healthy, feeds live, 14 GB free
- Predict pnl 24/45 -0.4; Predict acc 38/50 -15.0; Poly pnl 37/62 +133.7; Poly acc 24/34 -32.0. Last hour pooled 9/13 +30 (quiet Asia, low vol: 29 of the last fires are low-regime; Predict low-vol 17/29 +12).
- Retro on 107 fires: none 61/107 +133 | p>=0.56 50/77 +152 | ask>0.45 47/70 +158. Calibration: p<0.56 11/30 -19 (the only losing bin); 0.56-0.62 10/20 +4; 0.62-0.70 30/42 +136; 0.70+ 10/15 +12 (top bin recovered).
- Venue gap -0.079; Polymarket right on disagreement 642:313 over 140 candles (2.05:1, stable all night).
- No bugs, no restarts.

## 03:41 UTC check-in (backup 03:41) - five healthy, feeds live, 14 GB free
- Predict pnl 27/50 +16.9; Predict acc 41/53 -7.0; Poly pnl 40/67 +154.2; Poly acc 28/38 -15.9. Last hour pooled 9/17 +25.
- Retro on 117 fires: none 67/117 +171 | p>=0.56 52/82 +138 | ask>0.45 49/75 +144. The cheap/low-p fires flipped positive again in the calm Asia hours (p<0.56 bin 15/35 +33; 0.56-0.62 10/22 -16). Filters cost money now. Same conclusion as before: floor must follow regime.
- Calibration: 0.62-0.70 31/44 +135; 0.70+ 11/16 +19.
- Predict low-vol 18/31 +8: still not converting at Polymarket's rate in the same regime (18/31 +46) - the entry price (venue) explains the whole difference tonight.
- Venue gap -0.078; Polymarket right on disagreement 698:326 over 146 candles.
- No bugs, no restarts.

## 04:12 UTC check-in (backup 04:12) - five healthy, feeds live, 14 GB free
- Predict pnl 27/51 +6.9; Predict acc 47/59 +8.3 (turned positive: 80%); Poly pnl 40/70 +124.2; Poly acc 30/41 -20.5. Last hour pooled 5/13 -15 (thin pre-London drift).
- Retro on 121 fires: none 67/121 +131 | p>=0.56 52/85 +108 | ask>0.45 49/78 +114. Calibration: 0.62-0.70 31/45 +125 (core), 0.50-0.56 15/36 +23, 0.56-0.62 10/23 -26, 0.70+ 11/17 +9.
- Low-vol regime is now the majority of fires for both venues (32-34 each) and is roughly break-even on both (Predict -2, Poly +16): in dead markets the edge is thin regardless of venue. The night's profit came from mid/high vol on Polymarket (+108 on 37 fires) - the edge scales with activity, and the frequency rule should follow the same signal (more in active markets, fewer in dead ones), the opposite of a naive "quiet = safe" prior.
- Venue gap -0.077; Polymarket right on disagreement 716:332 over 152 candles.
- No bugs, no restarts.

## 04:45 UTC check-in (backup 04:45) - five healthy, feeds live, 14 GB free
- Predict pnl 30/57 -0.3; Predict acc 51/63 +21.2 (81%); Poly pnl 42/75 +117.7; Poly acc 32/45 -33.1. Last hour pooled 5/12 -24 (dead pre-London tape).
- Low-vol regime now 36-37 fires per venue and negative/flat on both (Predict -10, Poly +5): confirms 04:12 note - dead markets carry no edge for this model; all the night's profit is mid/high vol on Polymarket (+112 on 38).
- Retro on 132 fires: none 72/132 +117 | p>=0.56 +100 | ask>0.45 +105. Calibration: 0.62-0.70 33/50 +115; 0.56-0.62 10/24 -36 (worst bin now); 0.70+ 13/19 +21.
- Predict.fun accuracy mode is the only run improving through the quiet hours (+21): buying the leader on the cheaper venue when the market is calm and the leader converts ~81%.
- Venue gap -0.080; Polymarket right on disagreement 801:358 over 159 candles.
- No bugs, no restarts.

## 05:17 UTC check-in (backup 05:17) - five healthy, feeds live, 14 GB free
- Predict pnl 30/58 -10.3; Predict acc 55/68 +23.6 (81%); Poly pnl 44/79 +119.3; Poly acc 35/48 -25.9. Last hour pooled 5/12 -22 (still dead tape before London).
- Retro on 137 fires: none 74/137 +109 | p>=0.56 +97 | ask>0.45 +103. Calibration: 0.62-0.70 33/51 +105; 0.70+ 14/20 +28; 0.56-0.62 10/24 -36; 0.50-0.56 17/42 +12.
- Regime: every venue/regime cell is flat-to-negative since 03:00; the two profitable cells remain Poly mid-vol (12/20 +56) and Poly high-vol (13/22 +58), both earned before 01:00. The overnight edge on this model is ~zero on both venues; v11 frequency rule should be near-zero fires in the dead hours (rv60 < ~0.17 and thin books), not "fewer".
- Venue gap -0.079; Polymarket right on disagreement 814:372 over 165 candles.
- No bugs, no restarts.

## 05:49 UTC check-in (backup 05:50) - five healthy, feeds live, 14 GB free
- Predict pnl 34/62 +28.3; Predict acc 62/75 +49.2 (83%); Poly pnl 47/84 +127.0; Poly acc 40/54 -19.6. Last hour pooled 7/11 +26 (London pre-open activity picking up).
- Predict.fun accuracy mode is the overnight winner: +49 on 75 fires at 83%, all earned since ~01:00 in the quiet regime. In calm tape the Predict.fun leader is cheap (6-8c under Polymarket) AND converts at ~83%, above its ~78% break-even: exactly the "buy the leader where it is under-priced" case. Accuracy mode on Polymarket in the same hours: 74% at ~0.80 asks -> negative. Venue-specific floors for accuracy mode confirmed.
- Retro on 146 fires: none 81/146 +155 | p>=0.56 +153 | ask>0.45 +148. Calibration: 0.62-0.70 36/54 +133; 0.70+ 15/21 +36; 0.56-0.62 13/28 -16; 0.50-0.56 17/43 +2.
- Venue gap -0.079; Polymarket right on disagreement 823:383 over 171 candles.
- No bugs, no restarts.

## 06:23 UTC check-in (backup 06:23) - five healthy, feeds live, 14 GB free
- Predict pnl 34/63 +18.3; Predict acc 66/79 +60.4 (84%); Poly pnl 48/85 +134.0; Poly acc 43/57 -7.5. Last hour pooled 5/7 +22.
- Predict.fun accuracy mode keeps compounding in the calm regime (+60, 84%); Polymarket accuracy recovering toward zero. Pnl modes flat overnight (few fires, dead tape).
- Retro on 148 fires: none 82/148 +152 | p>=0.56 +151 | ask>0.45 +145 (filters neutral now). Calibration: 0.62-0.70 37/55 +140; 0.70+ 15/22 +26; 0.56-0.62 13/28 -16; 0.50-0.56 17/43 +2.
- Venue gap -0.078 (unchanged all night); Polymarket right on disagreement 839:395 over 178 candles.
- No bugs, no restarts.

## 06:54 UTC check-in (backup 06:54) - five healthy, feeds live, 14 GB free
- Predict pnl 35/65 +17.3; Predict acc 71/85 +64.0 (84%); Poly pnl 49/86 +141.3; Poly acc 46/60 +0.9 (back to break-even). Last hour pooled 2/4 -4 (quiet).
- All four runs non-negative for the first time since 21:00. Predict.fun accuracy mode: +64 on 85 fires; its fire rate in the quiet regime (~10/h) is higher than pnl mode (~2/h) - in dead tape the leader trade is the only one the model finds.
- Retro on 151 fires: none 84/151 +159 | p>=0.56 67/107 +167 | ask>0.45 63/99 +161. Calibration: 0.62-0.70 39/57 +157 (core); 0.70+ 15/22 +26; below 0.62 30/72 -24.
- Venue gap -0.079; Polymarket right on disagreement 863:395 over 184 candles.
- No bugs, no restarts.
