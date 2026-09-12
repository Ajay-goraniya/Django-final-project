# v11 notes - WHAT MATTERS MOST (revised 2026-09-09 13:25 UTC)

Live evidence: four parallel runs of the same v10 model, 2026-09-08 17:21 -> 09-09 13:00 UTC (~20 h),
Predict.fun (pnl + accuracy modes) and Polymarket (pnl + accuracy), $10 flat, plus a both-venue book
collector (5-s samples, 257 candles). All numbers are EF-only, quoted asks, no slippage.

## A. The five findings that decide PnL (ranked)
1. VENUE > MODEL. Same weights, same candles: Polymarket pnl +212 (58%) vs Predict.fun pnl +69 (56%).
   Polymarket's book forecasts better (leader right 2:1 on all 1,663 disagreement samples; leader
   converts 76% vs 71%) and sells the model's side cheaper on the leader side (median -0.06, mean -0.074).
   -> v11: Polymarket websocket as the model's ONLY signal input; Predict.fun for everything else.
2. EXECUTE ON PREDICT.FUN CORRECTLY: fee is 2% of notional (cost = ask*1.02), not 7% of payout; require
   size at the ask >= stake (2-17 shares seen behind "cheap" prices). Retro on the recorded 19 h through
   the real v11 code: v10-as-run +186 (110 tr) -> v11 +241 (118 tr, 63%).
3. LIVE CALIBRATION FAILED OUT OF SAMPLE (15:00 UTC pre-launch check, 128 v11 trades): fitted on the
   first 1/2 or 2/3 of the day it LOST on the rest (+193 -> +160 and +71 -> +57); the fires it refuses
   (p<0.56, cheap asks) were net winners later. In-sample gain shrank from +91 to +9 with more data.
   -> ships OFF (Trade Controls toggle, table still displayed); refresh with day 2+ before trusting.
   EV THRESHOLD SCALE 0.75 holds out of sample (both splits, 5 of 6 four-hour blocks): the v10 per-vol
   thresholds were fitted for Polymarket at 7% fee; with Predict.fun's 2% fee they are too strict.
   Full-span retro: x1.0 +286 (128 tr) | x0.75 +403 (167 tr, 66%) | x0.5 +469 (monotonic -> the
   threshold itself is miscalibrated for this venue; 0.75 is the conservative default, dial stays).
   SIZE RULE: top-of-book size refused 7 fills the executor's ladder walk would have made (+80 in retro);
   v11 now counts shares within 2c of the best ask.
4. MODES ARE REGIME-COMPLEMENTARY on Predict.fun: pnl mode earned in active hours (evening, London/US),
   accuracy mode earned in calm hours (01:00-08:00 +75, 83%) and lost in active hours. Dead tape has ~zero
   edge for pnl mode (00:30-02:00: 2/9 -51 pooled). Time of day is NOT a gate (one night, 1-in-8 chance);
   activity (rv60, book) is the signal. Hand rules tested and REJECTED: fixed high-vol EV threshold
   (removed 3 losses/5 wins), previous-candle trend filter (7/8), fixed p band (kills all cheap entries).
5. LEADER-CONVERSION WINDOW (12 candles, fired or not): gates the accuracy lane (85% -> 89-90%, PnL
   150 -> 137) and must NOT gate the pnl lane (removes 24 wins / 10 losses). Implemented that way.

## B. Bugs found live and fixed (all in Build 11)
- Candle-open fire priced from the previous market's 0.01 loser side (engine lane + now the executor too).
- Dust-ask fire on a one-sided book near close (no fire outside 15-240 s, none on one-sided quotes).
- Binance perp "NA" prints at price 0 -> basis -10000 -> p pinned 0.99 (dropped).
- Per-tick feature pass starved the phone engine thread (2 decisions/s).
- Feeds silently dead after a network-route change (proxy port) for 25 min -> feed-age watchdog + relaunch loop.

## C. Still open for v12 (need day 2+ of paired-book data)
- Regime-dependent floor / activity-driven frequency for the pnl lane (with Predict.fun execution the
  low-vol cell was +121 in the retro, so no floor is justified by one day; EV scale is a dial in Trade Controls).
- Venue-specific timing windows; payoff-sized stakes for accuracy mode; retrain the core on both venues'
  prices + gap (collector has 257 candles; not enough yet). Wire-or-remove the idle Build36 learner (disconnected now).
- Staking: hybrid ~= fixed 10%; drawdown brakes and quarter-Kelly cut return without cutting the capped-stake
  drawdown. Keep hybrid; Kelly sizing only once calibration is trusted.

## D. Two-book rule (design law for v11+)
Predict.fun: market discovery, candle id, current market, book state, size, fee, fills, settlement, orders.
Polymarket: model input only, keyed to Predict.fun's candle; stale/one-sided/other-candle -> fall back to
Predict.fun's own quote; every price in EV/size/order is Predict.fun's ask.

---
# Running log (chronological, live-data findings only)
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

## 07:26 UTC check-in (backup 07:26) - five healthy, feeds live, 13 GB free
- Predict pnl 36/67 +17.3; Predict acc 74/89 +64.1 (83%); Poly pnl 51/90 +142.0; Poly acc 48/63 -2.9. Last hour pooled 3/7 -9 (London open still quiet on BTC).
- Retro on 157 fires: none 87/157 +159 | p>=0.56 69/110 +174 | ask>0.45 65/102 +169. Calibration: 0.62-0.70 39/58 +147; 0.70+ 16/23 +34; 0.50-0.56 18/47 -15; 0.56-0.62 14/29 -6. The below-0.62 bins have been net negative for 10 hours now (32/76 -21).
- Venue gap -0.079; Polymarket right on disagreement 893:412 over 191 candles (2.17:1).
- No bugs, no restarts.

## 07:58 UTC check-in (backup 07:59) - five healthy, feeds live, 13 GB free
- Predict pnl 37/69 +14.9; Predict acc 78/93 +74.7 (84%); Poly pnl 53/95 +132.4; Poly acc 50/67 -18.9. Last hour pooled 6/12 -1.
- Retro on 164 fires: none 90/164 +147 | p>=0.56 +158 | ask>0.45 +153. Calibration: 0.62-0.70 40/60 +144; 0.70+ 17/24 +40; 0.50-0.56 19/49 -11; 0.56-0.62 14/31 -26.
- Overnight summary (01:00-08:00): Predict.fun accuracy mode +75 over the night is the only run with a steady positive slope; pnl modes and Polymarket accuracy have been flat since ~23:30. Frequency: pnl modes ~2-3 fires/h overnight vs ~7/h in the evening.
- Venue gap -0.078; Polymarket right on disagreement 949:426 over 197 candles.
- No bugs, no restarts.

## 08:30 UTC check-in (backup 08:30) - five healthy, feeds live, 13 GB free
- Predict pnl 40/72 +43.8; Predict acc 83/100 +68.7 (83%); Poly pnl 53/96 +122.4; Poly acc 53/72 -29.7. Last hour pooled 6/10 +17. London morning: Predict.fun pnl climbing (high-vol cell now 10/19 +18.5, was negative all night).
- Retro on 168 fires: none 93/168 +166 | p>=0.56 74/119 +177 | ask>0.45 69/109 +169. Calibration: 0.62-0.70 41/61 +153; 0.70+ 18/25 +48; 0.50-0.62 34/82 -35.
- 15-hour tally, all venues/modes: Polymarket pnl +122 (96 fires), Predict acc +69 (100), Predict pnl +44 (72), Polymarket acc -30 (72). Same model; venue x mode decides the sign.
- Venue gap -0.078; Polymarket right on disagreement 990:436 over 204 candles (2.27:1).
- No bugs, no restarts.

## 09:02 UTC check-in (backup 09:03) - five healthy, feeds live, 13 GB free
- Predict pnl 40/73 +33.8; Predict acc 86/106 +48.2 (81%); Poly pnl 54/97 +136.9; Poly acc 55/77 -55.9. Last hour pooled 3/5 +16.
- Accuracy modes diverging by venue again: Polymarket accuracy -56 (4 straight losses at 0.77-0.88 asks); Predict.fun accuracy gave back 20 on the same candles. In active London tape the leader converts under its price on both venues; accuracy mode needs the rolling-conversion switch-off (item already in notes).
- Retro on 170 fires: none 94/170 +171 | p>=0.56 +167 | ask>0.45 +159 (filters neutral to slightly negative in active hours). Calibration: 0.62-0.70 41/62 +143; 0.70+ 18/25 +48; 0.56-0.62 15/33 -24; 0.50-0.56 20/50 +4.
- Venue gap -0.077; Polymarket right on disagreement 1000:447 over 210 candles.
- No bugs, no restarts.

## 09:34 UTC check-in (backup 09:35) - five healthy, feeds live, 13 GB free
- Predict pnl 40/73 +33.8 (no fire this half hour); Predict acc 92/113 +54.2 (81%); Poly pnl 55/98 +147.8 (new high); Poly acc 59/82 -55.3. Last hour pooled 2/3 +15.
- Poly high-vol cell now 17/28 +79: the London-morning activity is being captured on Polymarket but not fired on Predict.fun (Predict pnl idle: its asks on the model's side sit 3-6c above the EV line).
- Retro on 171 fires: none 95/171 +182 | p>=0.56 +178 | ask>0.45 +170. Calibration unchanged (0.62-0.70 41/62 +143).
- Venue gap -0.077; Polymarket right on disagreement 1006:460 over 216 candles.
- No bugs, no restarts.

## 10:08 UTC check-in (backup 10:08) - five healthy, feeds live, 13 GB free
- Predict pnl 43/77 +53.3; Predict acc 96/117 +69.8 (82%); Poly pnl 56/101 +140.7; Poly acc 64/87 -41.4. Last hour pooled 5/8 +23.
- Retro on 178 fires: none 99/178 +194 | p>=0.56 +197 | ask>0.45 +190. Calibration: 0.62-0.70 43/65 +152; 0.70+ 18/25 +48; below 0.62 38/88 -6 (flat; was -35 at 08:30 - London hours favour the cheap fires again).
- All-lanes on Predict.fun (10:05): pnl engine MAIN 107/150 -106, REV 32/51 +102, EF 43/77 +47 -> +43 total; accuracy engine MAIN 83/117 -80, REV 25/39 +87, EF 96/117 +68 -> +74 total. MAIN wins 71% and loses ~100 on both (buys the leader at ~0.75); REVERSAL is the best lane per fire (+2/fire from cheap contrarian entries).
- Venue gap -0.076; Polymarket right on disagreement 1034:469 over 223 candles.
- No bugs, no restarts.

## Refinement of the rolling-conversion switch (user request, 10:20 UTC 2026-09-09)
- Do NOT window on the lane's own fires (20 fires = 3-24 h at night's fire rates - would stop late and re-arm late). Window on CANDLES: every 5-min candle has a book leader and an outcome, so measure leader-conversion-vs-price over the last 12 candles (1 h) on every candle, fired or not. Switch off when it is under break-even, back on when above; same rule both ways, no cool-down timer. Combine with rv60 (reacts in minutes) so the lane is quiet in dead tape and live in active tape within an hour of the change.

## 10:40 UTC check-in (backup 10:40) - five healthy, feeds live, 13 GB free
- Predict pnl 44/78 +61.9; Predict acc 99/122 +55.6 (81%); Poly pnl 57/102 +155.9 (new high); Poly acc 65/89 -50.0. Last hour pooled 5/7 +37.
- Pnl modes waking with London/pre-US activity: Predict pnl +29 since 08:00 (mid-vol cell 6/11 +18). Accuracy modes giving back (Predict acc -14 since 08:00, Poly acc -10): the day/night mirror between the two modes holds a second time.
- Retro on 180 fires: none 101/180 +218 | p>=0.56 +206 | ask>0.45 +198 (filters cost money in active tape). Calibration: 0.62-0.70 44/66 +161; 0.70+ 18/25 +48; 0.50-0.56 22/54 +12; 0.56-0.62 17/35 -2.
- Venue gap -0.076; Polymarket right on disagreement 1041:478 over 229 candles.
- No bugs, no restarts.

## 11:19 UTC check-in (backup 11:19) - five healthy, feeds live, 13 GB free
- Predict pnl 44/78 +61.9 (idle since 10:05); Predict acc 104/128 +63.0 (81%); Poly pnl 59/105 +163.0 (new high); Poly acc 68/94 -58.2. Last hour pooled 4/5 +31.
- Poly pnl mid-vol cell 15/26 +64, high-vol 17/29 +69: the pre-US window (10:00-11:30) is paying on Polymarket; Predict.fun pnl has not fired in 75 min - its ask on the model's side keeps landing 3-6c above the EV line (the contrarian side is dearer on Predict.fun).
- Retro on 183 fires: none 103/183 +225 | p>=0.56 +223 | ask>0.45 +215. Calibration: 0.62-0.70 46/68 +178 (core), 0.70+ 18/25 +48, below 0.62 39/90 flat.
- Venue gap -0.075; Polymarket right on disagreement 1059:497 over 237 candles.
- No bugs, no restarts.

## 11:50 UTC check-in (backup 11:51) - five healthy, feeds live, 13 GB free
- Predict pnl 45/80 +60.5; Predict acc 109/135 +57.2 (81%); Poly pnl 60/107 +163.1; Poly acc 71/97 -51.0. Last hour pooled 3/5 +7 (lull before the US open).
- Retro on 187 fires: none 105/187 +224 | p>=0.56 +232 | ask>0.45 +234. Calibration: 0.62-0.70 48/70 +197; 0.70+ 18/25 +48; 0.50-0.62 39/92 -20.
- Venue gap -0.075; Polymarket right on disagreement 1075:512 over 243 candles.
- No bugs, no restarts.

## 12:25 UTC check-in (backup 12:25) - five healthy, feeds live, 13 GB free
- Predict pnl 47/82 +80.3; Predict acc 114/141 +64.9 (81%); Poly pnl 63/110 +203.1 (crossed +200); Poly acc 75/103 -57.6. Last hour pooled 6/8 +48 - pre-US window active on both venues.
- Second active window of the run (10:00-12:30) is paying like the first evening one: Poly pnl +40 in 2.5 h, Predict pnl +19. Both pnl runs are now positive in every vol cell (Predict low/mid/high +15/+35/+29; Poly +30/+80/+93).
- Retro on 192 fires: none 110/192 +283 | p>=0.56 +276 | ask>0.45 +254 - in active tape the unfiltered model is best; every constant filter costs. Calibration: 0.62-0.70 50/72 +216; 0.70+ 18/25 +48; 0.50-0.62 42/95 +20 (turned positive again).
- Venue gap -0.074; Polymarket right on disagreement 1090:547 over 251 candles (2:1).
- No bugs, no restarts.

## 12:57 UTC check-in (backup 12:57) - five healthy, feeds live, 13 GB free
- Predict pnl 48/85 +69.3; Predict acc 117/146 +55.2 (80%); Poly pnl 64/111 +211.7; Poly acc 78/107 -57.9. Last hour pooled 4/6 +20.
- Retro on 196 fires: none 112/196 +281 | p>=0.56 +283 | ask>0.45 +261. Calibration: 0.62-0.70 52/75 +224; 0.70+ 18/25 +48; 0.50-0.62 42/96 +10.
- Build 11 (v11) built and live-smoke-tested on port 8793 (scratch DB): first fire end-to-end with Polymarket signal (89% of decisions), Predict.fun ask 0.34 / 152 shares, 2% fee, current market. Retro through the real decide_v11 on the recorded 19 h: v10-as-run +186 (110 tr) -> v11 pnl +241 (118 tr, 63%) -> v11 pnl + live calibration (refuse if calibrated p<0.5) +332 (97 tr, 69%); accuracy mode 97 tr 85% +140. Calibration table is in-sample; retro uses 15-s/5-s samples.
- Venue gap -0.074; Polymarket right on disagreement 1108:555 over 257 candles.
- No bugs, no restarts on the five v10 processes.

## 13:15 UTC - leader-conversion window (item 13) retro-tested and implemented in Build 11
- Per candle (fired or not): Polymarket leader at >=60 s, its Predict.fun ask*1.02 as break-even, graded at settlement, window = last 12 settled candles. 254 candles: leader converts 73% vs mean break-even 65%; window ON 65% of candles.
- pnl lane (contrarian fires): switch REMOVES 24 wins / 10 losses -> +340 -> +225. Wrong signal for that lane: contrarian fires win exactly when the leader under-converts. NOT gated.
- accuracy lane (leader fires): 100 tr 85% +150 -> 63 tr 89% +137 (W=12); W=24 67 tr 90% +137. Gated by default (V11_CONV_GATE=accuracy; all/off available).
- Regime floor / activity-driven frequency for the pnl lane: with Predict.fun execution + 2% fee the low-vol cell is +121 (52 tr 67%) in the retro, so no floor is justified by this data; left as env dials (V11_THR_SCALE) rather than a rule. Needs day 2.

## 13:29 UTC check-in (backup 13:30) - five healthy, feeds live, 13 GB free
- Predict pnl 50/87 +93.8; Predict acc 123/153 +61.9 (80%); Poly pnl 65/114 +201.8; Poly acc 81/112 -68.1. Last hour pooled 4/7 +14. US open ahead.
- Retro on 201 fires: none 115/201 +296 | p>=0.56 +291 | ask>0.45 +269. Calibration: 0.62-0.70 53/77 +221; 0.70+ 18/25 +48; 0.50-0.62 44/99 +27.
- Build 11 smoke (scratch): signal source Polymarket 796 / Predict.fun fallback 339 decisions (30% fallback, up from 11% earlier) - watch: fallback should only happen at rollover; check PolyBook freshness/ladder coverage before launch. 1 fire so far (13:05 UP @0.42 lost). Conversion window filling (3 candles).
- Venue gap -0.074; Polymarket right on disagreement 1154:585 over 263 candles.
- No bugs, no restarts on the v10 processes.

## 14:03 UTC check-in (backup 14:03) - five healthy, feeds live, 13 GB free
- Predict pnl 53/90 +127.1 (new high); Predict acc 126/159 +28.8; Poly pnl 67/119 +200.3; Poly acc 85/119 -86.3. Last hour pooled 8/11 +67 (US open: pnl lanes on, accuracy lanes off - third time the mirror shows).
- Retro on 209 fires: none 120/209 +327 | p>=0.56 +319 | ask>0.45 +266. Calibration: 0.62-0.70 53/78 +211; 0.56-0.62 23/43 +53; 0.70+ 19/26 +55; 0.50-0.56 25/62 +8.
- Build 11 smoke (scratch, pnl): 6 fires since 13:05, 5/6 wins, all with Polymarket signal, Predict.fun asks 0.42-0.51. Fallback to Predict.fun quote happens at candle ends when Polymarket has one side empty (harmless: one-sided quotes never fire anyway). Conversion window filling (6 candles, leader 83% vs break-even 74%).
- Venue gap -0.074 (median -0.05); Polymarket right on disagreement 1188:590 over 270 candles.
- No bugs, no restarts on the v10 processes.

## 14:34 UTC check-in (backup 14:35) - five healthy, feeds live, 13 GB free
- Predict pnl 55/93 +146.9 (new high); Predict acc 130/166 +25.3; Poly pnl 68/122 +202.0; Poly acc 89/125 -92.9. Last hour pooled 6/12 +25.
- Predict.fun pnl has caught most of the day's US-session move (high-vol cell 19/31 +99 - its best cell now), while Polymarket pnl is flat since 12:30: in the fast US tape the Predict.fun book is lagging Polymarket by enough that the same fires get cheaper fills there. Cumulative gap unchanged (-0.075) but it is where and when it shows that pays.
- Retro on 215 fires: none 123/215 +349 | p>=0.56 +314 | ask>0.45 +256: in active tape every constant filter costs (fourth time).
- Build 11 smoke (scratch, pnl): 11 fires, 7/11, all on Polymarket signal; window 10 candles, leader 80% vs 74% break-even.
- No bugs, no restarts on the v10 processes.

## 14:39 UTC - second container restart / proxy-port change (43519 -> 38961)
- All six processes (v10 x4, collector, Build 11 smoke) went to "reconnecting"; detected within ~1 min (harness notice), relaunched via proxy_restart.sh at 14:41 on the SAME databases; feeds live again by 14:42. Histories intact (Predict pnl 94 fires, Poly pnl 124, Predict acc 167, Poly acc 127). ~90 s gap.
- Confirms the feed-age watchdog in Build 11 (exit 3 -> relaunch) is the right ops fix; the v10 processes lack it and depend on the check-in.

## 15:00-15:15 UTC - pre-launch data review of Build 11 (changes made before the 16:30 launch)
- Replay check: v10-as-run replay +222.7 (125 tr) vs live Polymarket pnl +224.8 (124 fires): the retro reproduces live.
- Calibration table fails out of sample (see A.3) -> default OFF, toggle added to Trade Controls (tested: POST on/off, invalid value rejected, persisted in meta, survives relaunch).
- EV threshold scale default 1.0 -> 0.75 (out-of-sample +193 -> +262 and +71 -> +130; extra 39 trades 74%, p~0.68, ask~0.56, spread over all three vol regimes).
- Size check now uses shares within 2c of the best ask from the Predict.fun ladder (executor walks the ladder anyway); min notional stays $10.
- Evidence persistence verified: every fire stores ef_v11_signal/ask/size/p/ev/threshold/sec/rv60 in ef_predictions.features (all 15 smoke fires on the Polymarket signal).
- Candle boundary measured at 1 Hz: Predict.fun market switches in <=2 s, Polymarket signal for the new epoch ready at +2 s; the 19% "predict" fallback count was the post-restart warm-up, not a live gap.
- Smoke relaunched 15:04 on the patched build (scratch DB kept): thr 0.75, calibration off, signal polymarket, no errors.
- 15:08 UTC: Polymarket signal dropped to the Predict.fun fallback twice mid-candle (5 s and 2 s) with the socket alive (age <50 ms): a one-sided/empty ladder moment, not staleness. Build 11 now holds the last complete Polymarket quote of the same candle for up to 10 s ("polymarket-held" in signal counts) before falling back, so a fire never switches venue features for a blink. Smoke relaunched 15:13 on that build.
- Pre-launch tests passed: fresh --reset launch from the launch file set (22 tables, no errors), executor path with master OFF records EF fires as SHADOW with break-even = ask*1.02 (2% notional fee confirmed in Build36's own numbers), report/backup/check-in tooling extended for the 8794 database (report section verified on the smoke DB).

## 15:14 UTC check-in (backup 15:13) - five v10 processes healthy, feeds live, 13 GB free
- Predict pnl 58/97 +178.2 (new high); Predict acc 134/171 +18.6; Poly pnl 73/127 +243.9 (new high); Poly acc 92/129 -92.1. Last hour pooled 8/12 +68.
- Both pnl runs are earning the London/US afternoon again: Predict.fun high-vol cell 22/35 +130, Polymarket high-vol 26/45 +125 - the active-hours pattern (A.4) holds for a second afternoon.
- Retro on 224 fires: none 130/224 +422 | p>=0.56 +338 | ask>0.45 +264 (constant filters still cost).
- Build 11 smoke: 15 fires 8/7 (+18.8 at 2% fee), all on the Polymarket signal; relaunched 15:13 on the held-quote build, warming.
- No bugs, no restarts on the v10 processes. Collector single instance, no duplicate samples.

## 15:45 UTC check-in (backup 15:45) - five v10 processes healthy, feeds live, 13 GB free
- Predict pnl 60/102 +165.9; Predict acc 141/178 +48.8; Poly pnl 74/130 +262.6; Poly acc 98/135 -68.3. Last hour pooled 8/14 +44.
- High-vol cell still carries both pnl runs (Predict.fun 24/40 +118, Polymarket 28/48 +144). Retro on 232 fires: none +428 | p>=0.56 +349 | ask>0.45 +262.
- Build 11 smoke (held-quote build since 15:13): 19 fires 10/9; 1 Hz sampling over 10 min shows the Polymarket signal is complete for the first 3 min of every candle and one-sided (loser side has no asks) in the last 2 min: 0 fallbacks at 60-180 s, ~50% at 180-240 s, ~50% after 240 s. The fallback to the Predict.fun quote therefore only happens when the market is already decided; the proven Polymarket runner refuses one-sided quotes instead of switching venue.
- 15:47: Build 11 changed accordingly - a fresh but one-sided Polymarket quote now refuses the fire ("polymarket-onesided" in signal counts) instead of falling back to the Predict.fun quote; fallback is reserved for a stale/missing Polymarket feed. Smoke relaunched 15:47 on that build.

## 16:16 UTC check-in (backup 16:16) - five v10 processes healthy, feeds live, 13 GB free
- Predict pnl 60/105 +135.9 (three straight losses 15:50-16:10); Predict acc 146/184 +57.6; Poly pnl 78/136 +260.5; Poly acc 103/141 -59.9. Last hour pooled 4/14 -62: both venues lost the same candles (a chop hour after the 15:00 run-up), no venue or timing pattern in the 14.
- Retro on 241 fires: none +396 | p>=0.56 +337 | ask>0.45 +250.
- Build 11 smoke: 24 fires 13/11; signal counts since 15:47: polymarket 999, held 18, one-sided refusals 55, Predict.fun fallback 0 -> the one-sided rule and the 10-s hold cover every gap; no venue switch happened. Polymarket socket reconnects 14 in 30 min (rotation + the 15-s silence rule), each bridged by the hold, no signal loss.
- No bugs, no restarts on the v10 processes.

## 16:30 UTC - Build 11 (v11) LAUNCHED in the container, port 8794, own database, master OFF
- File set shipped to the user as v11_launch_20260909_1630.tar.gz (build11 1,437,627 B md5 98edaff9; v10 module 18,307; v11 module 15,661; model 8,803; calibration 611; run_v11.sh 712).
- Final retro on all recorded data (09-08 17:31 -> 09-09 16:22, 139 fires, 267 candles): v10-as-run replay = live; v11 launch settings (thr 0.75, calibration off) in-sample +422 on 163 trades (65%); calibration still adds only +18 in-sample and loses out of sample -> off.
- Launch settings: mode pnl, EV scale 0.75, calibration off, min size $10 within 2c of ask, conversion gate accuracy lane, Polymarket signal with 10-s hold and one-sided refusal. All four v10 runs, the collector and the smoke keep running untouched.
- 16:30:40: feeds live (spot, perp, Predict.fun book websocket), Polymarket signal live, warming up.

## 16:51 UTC check-in (backup 16:51) - six model processes + collector healthy, 13 GB free
- Predict pnl 60/108 +105.9 (five straight losses since 15:50: 16:00 chop); Predict acc 151/191 +66.1; Poly pnl 79/139 +288.1; Poly acc 108/146 -43.8. Last hour pooled 4/11 -13.
- Build 11 (8794, 21 min): 3 fires, 0/2 (16:40 UP ask 0.41, 16:45 UP ask 0.37 - cheap-ask entries in the chop, both lost; 16:45 also lost on Predict.fun v10), 16:50 open. Signal since launch: polymarket 969, held 36, one-sided refusals 296 (last 2 min of candles), Predict.fun fallback 0. No relaunch, no errors in b11.log.
- Binance spot websocket (stream.binance.com) resets by peer intermittently on every engine; the engine drops to REST fallback and comes back on data-stream.binance.vision within minutes (seen on 8794 at 16:50 -> live by 16:52; Predict.fun pnl engine 8789 on rest-fallback at 16:52, watching). Not a v11 issue.
- Retro on 247 fires: none +394 | p>=0.56 +307 | ask>0.45 +220.

## 17:22 UTC check-in (backup 17:22) - all processes healthy, 13 GB free
- Predict pnl 61/111 +91.1; Predict acc 155/196 +66.3; Poly pnl 80/142 +277.8; Poly acc 112/152 -50.7. Last hour pooled 3/10 -33: the 16:00-17:20 chop is the worst stretch of the run on every venue.
- Build 11 (52 min): 9 fires, 2/8, -38.5. It fired on 9 of 10 candles (v10 runs 4-5 of 10): with thr x0.75 the cheap-ask entries at p 0.53-0.63 all went through and 5 of 6 lost in the chop; the two p>=0.68 fires split 1/1. Same-candle view: 16:50 v11 DOWN won where both v10 UP lost; 17:05 v11 DOWN (p 0.73) lost where both v10 UP won (different fire times -> different p). Too early to judge; frequency effect of the 0.75 scale is visible and is what the dial is for.
- Signal since launch: polymarket 1483, held 36, one-sided 296, Predict.fun fallback 0; 12 socket reconnects, all bridged. Spot feeds back to live on all engines (REST fallback episodes resolved themselves). No errors, no relaunch.
- Retro on 253 fires: none +369 | p>=0.56 +282 | ask>0.45 +195 (constant filters still lose overall even after this chop hour).

## 17:53 UTC check-in (backup 17:53) - all processes healthy, 13 GB free
- Predict pnl 63/113 +106.3; Predict acc 160/202 +61.9; Poly pnl 82/143 +283.5; Poly acc 116/156 -38.7. Last hour pooled 5/7 +16 (chop easing).
- Build 11 (83 min): 15 fires, 7/14, -4.6. Five straight wins 17:25-17:45 (asks 0.42-0.70) after the 2/8 open; on 17:30-17:40 it fired three DOWN winners on candles where neither v10 run fired (cheap asks 0.42-0.50 with p 0.54-0.63 clear the 0.75-scaled threshold). By p: <0.62 3/7, >=0.62 4/7. Still a small sample.
- Signal: polymarket 1842, held 37, one-sided 296, fallback 0; 19 socket reconnects, all bridged. Spot live on all engines. No errors, no relaunch.
- Retro on 256 fires: none +390 | p>=0.56 +302 | ask>0.45 +215.

## 18:24 UTC check-in (backup 18:24) - all processes healthy, 13 GB free
- Predict pnl 64/117 +88.6 (day high was +185.8 at 15:49: -97 since); Predict acc 163/208 +42.6; Poly pnl 82/147 +260.5 (-38 from its 15:49 high... high was +298 at 16:31); Poly acc 120/162 -45.6. Last hour pooled 3/9 -34.
- Second evening is the opposite of the first: 16:00-18:20 UTC today is the worst stretch of the run on both venues (Predict.fun 4/10 -27, Polymarket 3/9 -38 since 16:30), while yesterday's same hours were the best. Confirms A.4: time of day is not a gate; the tape is (today's US afternoon = range chop, low follow-through).
- Retro on 264 fires: none +349 | p>=0.56 +262 | ask>0.45 +172 - constant filters still lose overall.

## 18:56 UTC check-in (backup 18:56) - all processes healthy, 13 GB free
- Predict pnl 65/121 +67.5; Predict acc 169/215 +64.8; Poly pnl 82/150 +230.5; Poly acc 123/166 -48.2. Last hour pooled 1/13 -111: the single worst hour of the run on both venues (17:55-18:55 UTC).
- Since 16:30 the pnl runs are 5/14 -48 (Predict.fun) and 3/12 -68 (Polymarket); the accuracy runs are +9 / +11 in the same two hours (78% / 82%). The mode complementarity (A.4) held for a second day, the other way round: accuracy mode earns the chop, pnl mode earns the trend.
- Retro on 271 fires: none +298 | p>=0.56 +241 | ask>0.45 +151.

## 19:28 UTC check-in (backup 19:28) - all processes healthy, 13 GB free
- Predict pnl 66/122 +80.9; Predict acc 173/221 +57.2; Poly pnl 82/150 +230.5 (4 fires ungraded); Poly acc 124/167 -43.4 (4 ungraded). Last hour pooled 1/4 -17 (few fires: the engines stopped finding EV in the 19:00 tape).
- Polymarket resolution lag: every 5-min market from 18:55 UTC onward is still unresolved on Gamma at 19:30 (closed=false, prices 0.9995/0.0005, UMA status none) while 18:45 resolved normally. The two Polymarket runners grade only on resolution, so their PnL lags until Polymarket's resolver catches up; the grade loop retries every 20 s, nothing lost. Also found: Gamma returns 403 to Python's default user agent (all our processes send their own UA, unaffected).
- Retro on 272 fires: none +311 | p>=0.56 +241 | ask>0.45 +151.

## 20:00 UTC check-in (backup 20:00) - all processes healthy, 13 GB free
- Predict pnl 67/123 +95.4; Predict acc 177/225 +72.1; Poly pnl 82/151 +220.5 (7 ungraded); Poly acc 126/169 -36.9 (7 ungraded). Last hour pooled 2/3 +18 (few fires).
- Polymarket resolution still stalled: no 5-min market since 18:45 UTC has resolved by 20:00 (75 min). Both Polymarket runners' PnL and any "since 16:30" comparison against them are incomplete until it clears; the grade loop keeps retrying.
- Retro on 274 fires: none +316 | p>=0.56 +231 | ask>0.45 +141.

## 20:31 UTC check-in (backup 20:31) - all processes healthy, 13 GB free
- Predict pnl 68/124 +105.1; Predict acc 182/230 +89.3; Poly pnl 84/156 +230.7 (5 ungraded); Poly acc 131/175 -28.1 (7 ungraded). Last hour pooled 5/7 +34.
- Polymarket resolution resumed ~20:20 (18:55-19:30 markets graded); the runners are catching up.
- Ask bands, whole run: Polymarket pnl earns in 0.30-0.60 (81/147 +258), Predict.fun pnl in 0.30-0.50 (31/57 +124) and loses in 0.50-0.60 (28/55 -43); no pnl run has bought under 0.30 except 3 Polymarket fires (0/3). Cheap tail is thin and the model rarely disagrees with the book by that much.
- Retro on 280 fires: none +336 | p>=0.56 +251 | ask>0.45 +171.

## 20:43 UTC - accuracy-mode runs retired (user decision: CPU), databases kept and backed up
- Final Predict.fun accuracy (21:10 09-08 -> 20:43 09-09, 23.5 h): 184/232 = 79%, +94.5 at $10. Final Polymarket accuracy (22:15 -> 20:43, 22.5 h): 133/177 = 75%, -35.8 at $10 (6 fires ungraded at stop). Both databases in learner/live_backup (predict_acc, poly_acc).
- Lesson they leave: accuracy mode is regime-complementary to pnl mode (earns calm/chop, loses trends), and on Polymarket the leader's price is too rich for a 75% hit rate to pay. Still the candidate lane for an auto-switch once a detector exists.
- Build 11 smoke on 8793 (scratch) stopped at the same time; Build 11 on 8794 continues. Running now: Predict.fun pnl 8789, Polymarket pnl 8788, collector, Build 11 8794.

## 21:21 UTC check-in (backup 21:21) - Predict.fun pnl, Polymarket pnl, collector, v11 healthy, 13 GB free
- Predict pnl 70/129 +93.0; Poly pnl 89/162 +259.8 (3 ungraded). Last hour pooled 6/9 +37 (tape improving after 20:30).
- Retro on 291 fires: none +353 | p>=0.56 +245 | ask>0.45 +175.

## 21:52 UTC check-in (backup 21:52) - Predict.fun pnl, Polymarket pnl, collector, v11 healthy, 13 GB free
- Predict pnl 71/130 +100.0; Poly pnl 91/165 +271.3 (2 ungraded). Last hour pooled 4/7 +17.
- Retro on 295 fires: none +371 | p>=0.56 +273 | ask>0.45 +191.

## 22:25 UTC check-in (backup 22:25) - Predict.fun pnl, Polymarket pnl, collector, v11 twin healthy, 13 GB free
- Predict pnl 72/133 +95.2; Poly pnl 91/166 +261.3 (5 ungraded). Last hour pooled 2/6 -18.
- Retro on 299 fires: none +356 | p>=0.56 +253 | ask>0.45 +171.

## 22:56 UTC check-in (backup 22:56) - all container processes healthy, 13 GB free
- Predict pnl 74/136 +98.4; Poly pnl 94/170 +284.5 (5 ungraded). Last hour pooled 6/10 +22. Retro on 306 fires: none +383 | p>=0.56 +265 | ask>0.45 +183.

## 23:27 UTC check-in (backup 23:27) - all container processes healthy, 13 GB free
- Predict pnl 76/139 +118.1; Poly pnl 96/175 +271.6 (2 ungraded). Last hour pooled 7/11 +10. Retro on 314 fires: none +390 | p>=0.56 +292 | ask>0.45 +220.

## 23:50 UTC - input bug found in the Build 10/11 engine's v10 lane (applies to the Predict.fun pnl engine on 8789)
- The engine feeds raw Binance perp @trade prints into the v10 feature state; the runner and the training data aggregate them like aggTrade (same timestamp/side/price -> one print). Raw prints run ~2.6x the aggTrade count, so perp_n15 is inflated (coef 0.0464 per 752 prints: ~+0.02 logit typical, larger in busy tape). Fixed in build 11.1; the 8789 run keeps the old input so its history stays one series. Part of the Predict.fun-vs-Polymarket gap is therefore an input difference, not only the book.

## 23:58 UTC check-in (backup 23:58) - container healthy (7 processes incl. 4 v11 test twins), 13 GB free
- Predict pnl 79/143 +100.4; Poly pnl 96/178 +258.4 (3 ungraded). Last hour pooled 5/11 -20. Retro on 321 fires: none +359 | p>=0.56 +279 | ask>0.45 +207.

## 00:30 UTC check-in (backup 00:30) - container healthy (7 processes), 13 GB free
- Predict pnl 80/146 +119.5; Poly pnl 97/179 +248.4 (6 ungraded). Last hour pooled 3/10 -34 (00:00 dead tape again, as on 09-09 01:00).
- Container spot feed: the Build36 core prefers stream.binance.com:9443, which resets from this network; each reset means a REST-fallback stretch of sparse spot trades before it lands on data-stream.binance.vision. That is a container-network artefact (Tokyo sits on stream.binance.com:443, stable) and degrades the v10-lane features on the container engines during fallbacks.

## 01:02 UTC check-in (backup 01:02) - container healthy (7 processes), 13 GB free
- Predict pnl 82/149 +136.1; Poly pnl 103/186 +283.2 (3 ungraded). Last hour pooled 8/10 +83 (00:30-01:00 trend burst after the dead 00:00 hour).

## 01:35 UTC check-in (backup 01:35) - container healthy (7 processes), 13 GB free
- Predict pnl 84/151 +150.9 (day high); Poly pnl 103/190 +243.2. Last hour pooled 4/10 -19.

## 02:07 UTC check-in (backup 02:07) - container healthy (7 processes), 13 GB free
- Predict pnl 84/152 +140.9; Poly pnl 103/191 +253.2 (both graded through). Last hour pooled 3/5 +5 (quiet tape, few fires).

## 02:40 UTC check-in (backup 02:40) - container healthy (7 processes), 13 GB free
- Predict pnl 84/154 +120.9; Poly pnl 105/194 +268.7 (2 ungraded). Last hour pooled 3/7 -4 (02:00-02:40 chop: Predict.fun v10 0/2, Tokyo 3/4).

## 03:13 UTC check-in (backup 03:13) - container healthy (7 processes), 13 GB free
- Predict pnl 84/154 +120.9 (no fires since 02:10); Poly pnl 106/200 +225.7. Last hour pooled 2/9 -47: Polymarket v10 1/5 in the 02:40-03:10 chop, its worst hour of the night.

## 03:45 UTC check-in (backup 03:45) - container feed outage 03:38-03:47, fixed; 13 GB free
- Predict pnl 85/157 +109.5; Poly pnl 106/203 +195.8. Last hour pooled 1/9 -71 (03:00 hour was a loser for both v10 runs; Polymarket v10 is 14/22 in the fair window).
- The session harness restarted at 03:38 and the container's outbound proxy moved to a new port; every container process kept the old one -> spot/perp/depth "Connection refused" for ~9 min (about two candles of paper data lost on the v10 runs and the twins). proxy_restart.sh relaunched all seven on the same databases at 03:46; feeds live within 60 s, masters OFF. Tokyo has its own network and was untouched (63/63 filled through the window).

## 04:18 UTC check-in (backup 04:18) - container healthy (7 processes, relaunched 03:46), 13 GB free
- Predict pnl 85/160 +79.5; Poly pnl 107/205 +185.8. Last hour pooled 1/9 -71. In the fair window since 21:55 both v10 paper runs are now negative (Predict 14/16 -20.5, Poly 14/24 -92.8); the 03:00-04:00 stretch was against both.

## 04:51 UTC check-in - container MACHINE REBOOTED ~04:42-04:50 (uptime 1 min at 04:52), all seven processes relaunched 04:52 on the same DBs; 13 GB free
- Predict pnl 85/162 +69.5 (1 ungraded); Poly pnl 108/207 +192.8. Last hour pooled 2/8 -43. Fair window since 21:55: Predict 14/17 -30.5, Poly 16/24 -75.7.
- Second outage of the night: this time the VM itself rebooted (not just the harness); processes were gone, disk intact, proxy port changed again. restart_all.sh brought all seven back within 20 s, feeds live at once, masters OFF. Roughly 9 min of paper data lost (one to two candles). Tokyo untouched (73/73 fills).

## 05:24 UTC check-in - container VM rebooted AGAIN (uptime 0 min at 05:23), all seven relaunched 05:24; 13 GB free
- Predict pnl 85/162 +59.5; Poly pnl 108/207 +192.8 (no new fires while down). Fair window since 21:55: Predict 14/18 -40.5, Poly 16/24 -75.7.
- Root cause of the reboots: the session container is reclaimed when the session is idle ~30 min and re-provisioned on the next wake (disk persists, processes do not). It did not happen before 03:38 because a background crash-detector task was running the whole night and counted as activity; the harness restart at 03:38 killed it, and the replacements I armed timed out after 30 min -> reboots at 04:50 and 05:23 exactly at the next wake. Fix: a background bash keepalive (60-s process check, exits only on a crash) started 05:25; if the container still reboots at 05:55 the keepalive theory is wrong and the paper runs need another home.

## 05:55 UTC check-in (backup 05:55) - container healthy, uptime 32 min: the keepalive held through the idle gap (no reclaim); 13 GB free
- Predict pnl 85/162 +59.5 (no fires 05:25-05:55); Poly pnl 108/208 +192.8 (1 open). Last hour pooled 0/0: dead tape for both v10 runs from 05:00.
- Reclaim theory confirmed: with the background keepalive bash task running, the container survived a full 30-min idle gap for the first time since 03:38. Keep the keepalive alive across every check-in (it exits only on a crash, which is the wake we want).

## 06:27 UTC check-in (backup 06:27) - container healthy, uptime 64 min (keepalive holding), 13 GB free
- Predict pnl 88/165 +81.8; Poly pnl 110/210 +208.5 (1 open). Last hour pooled 5/5 +38: the 06:00 hour woke up (Predict 3/0, Poly 2/0). Fair window since 21:55: Predict 17/18 -18.3, Poly 18/24 -60.0.

## 06:59 UTC check-in (backup 06:59) - container healthy, uptime 96 min (keepalive holding), 13 GB free
- Predict pnl 90/167 +91.8 (1 ungraded); Poly pnl 113/215 +221.0 (2 open). Last hour pooled 6/8 +46. Fair window since 21:55: Predict 18/18 -8.2, Poly 20/26 -47.6 - both v10 runs recovering in the 06:00-07:00 wake-up while v11 live lost.

## 07:31 UTC check-in (backup 07:31) - container healthy, uptime 2 h 8 min, 13 GB free
- Predict pnl 91/168 +86.6; Poly pnl 114/215 +226.1. Last hour pooled 3/7 -10. Fair window since 21:55: Predict 19/19 -13.4, Poly 21/27 -42.4.

## 08:05 UTC check-in (backup 08:05) - container healthy, uptime 2 h 42 min, 13 GB free
- Predict pnl 91/169 +76.6; Poly pnl 114/217 +226.1 (2 open). Last hour pooled 1/2 -5 (quiet 07:00-08:00 tape). Fair window since 21:55: Predict 19/20 -23.4, Poly 21/27 -42.4.

## 08:40 UTC check-in (backup 08:39) - container healthy, uptime 3 h 15 min, 13 GB free
- Predict pnl 91/171 +73.9; Poly pnl 114/219 +208.0. Last hour pooled 2/7 -31. Fair window since 21:55: Predict 20/21 -26.1, Poly 22/30 -60.6.

## 09:12 UTC check-in (backup 09:12) - container healthy, uptime 3 h 49 min, 13 GB free
- Predict pnl 94/174 +103.4; Poly pnl 115/223 +205.0 (2 open). Last hour pooled 6/9 +26. Fair window since 21:55: Predict 23/21 +3.4 (back above zero), Poly 23/31 -63.6.

## 09:43 UTC check-in (backup 09:43) - container healthy, uptime 4 h 20 min, 13 GB free
- Predict pnl 96/176 +120.1; Poly pnl 118/226 +226.1. Last hour pooled 9/12 +64 (the 09:00 hour was a winner for every run). Fair window since 21:55: Predict 25/21 +20.0, Poly 26/33 -42.4.

## 10:15 UTC check-in (backup 10:15) - container healthy, uptime 4 h 51 min, 13 GB free
- Predict pnl 97/179 +111.0; Poly pnl 121/232 +193.2 (1 open). Last hour pooled 6/13 -6 (09:45-10:15 was a losing patch for everything). Fair window since 21:55: Predict 26/23 +11.0, Poly 27/37 -75.4.
- SHADOW LANES retro (41 h, b10.sqlite3 trades table, kinds MAIN/REVERSAL scored but never sent): MAIN 345 fires, directional 72% but mean buy 0.75 at median 94 s -> shadow PnL -20.8 at $1 (both halves negative). REVERSAL 110 fires, directional 69%, mean buy 0.55 at median 192 s -> +43.6 at $1 (halves +12.6 / +31.1; positive in 17 of 22 UTC hours). Twins agree (A 26/5 +22.3, C 20/5 +19.6); Tokyo's own shadow since 21:55: 27/6 +22.7. Overlap with EF: of 50 shared candles, 23 opposite-side, REVERSAL right 15 vs EF 8. Recommendation sent to the user: REVERSAL live at the ladder stake, MAIN stays off; awaiting the user's OK.

## 10:48 UTC check-in (backup 10:48) - container healthy, uptime 5 h 25 min, 13 GB free; variant D retired 10:50
- Predict pnl 98/183 +99.9 (1 open); Poly pnl 125/236 +207.0 (2 open). Last hour pooled 5/13 -29: the 09:45-10:45 tape lost for every run on both venues.

## 11:19 UTC check-in (backup 11:19) - container healthy (6 processes), uptime 5 h 56 min, 13 GB free
- Predict pnl 98/186 +59.9; Poly pnl 126/240 +193.5 (1 open). Last hour pooled 2/12 -60: the 10:15-11:15 hour is the worst of the whole record for both v10 paper runs. Fair window since 21:55: Predict 27/29 -40.1, Poly 30/42 -75.1.

## 11:53 UTC check-in (backup 11:53) - container healthy (6 processes), uptime 6 h 30 min, 13 GB free
- Predict pnl 99/188 +56.9; Poly pnl 128/244 +217.7. Last hour pooled 6/11 +18 (tape steadier from 11:00). Fair window since 21:55: Predict 28/30 -43.1, Poly 34/43 -50.9.
- 12:20 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 28/34 -83.1@$10; v10 Polymarket paper 34/47 -90.9@$10; v11 live 80/70 -7.50 real. Tokyo EF+REVERSAL paused at capital floor (see NOTES_v12 12:20). 6 local processes up.
- 12:58 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 31/36 -75.0@$10; v10 Polymarket paper 37/51 -99.0@$10; v11 live 83/72 -7.03 real. 6 local processes up. H1 Task 6/7 merged (see NOTES_v12 12:58).
- 13:28 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 36/36 -27.4@$10; v10 Polymarket paper 41/52 -62.1@$10; v11 live 86/74 -6.26 real (EF), realised -9.26. Trend guard live on Tokyo since 13:14. 6 local processes up.
- 13:57 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 37/39 -47.3@$10; v10 Polymarket paper 46/53 -12.5@$10; v11 live 89/78 -6.69 real (EF), realised -8.69, equity 17.54. 7 local processes (twin TE added). Guard status: unproven, kept pending H1's kline sweep.
- 14:41 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 39/40 -36.3@$10; v10 Polymarket paper 48/56 -17.9@$10; v11 live 94/79 -3.27 real (EF), realised -5.27, equity 19.68. Guard off since 14:25. Build 11.2 (REVERSAL entry cap) awaiting deploy. 7 processes.
- 15:26 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 42/41 -16.4@$10; v10 Polymarket paper 53/58 +10.7@$10; v11 live 99/80 -0.05 real (EF), realised -2.05, equity 22.57. Build 11.2, EF + REVERSAL(cap 0.60) on. 7 processes.
- 15:57 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 43/41 -1.2@$10; v10 Polymarket paper 55/58 +32.4@$10; v11 live 100/83 -1.82 real (EF), realised -3.82, equity 20.79. First capped REVERSAL fire 15:46 (quote 0.61, would have won). 7 processes.
- 16:35 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 43/42 -11.2@$10; v10 Polymarket paper 58/61 +39.9@$10; v11 live 101/86 -4.00 real (EF), realised -5.78, equity 18.84. REVERSAL cap leak found (16:02 fill at 0.81) and fixed in build 11.3. 7 processes.
- 16:59 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 43/42 -11.2@$10; v10 Polymarket paper 59/63 +37.2@$10; v11 live 104/87 -1.70 real (EF), realised -3.47, equity 22.16. Build 11.2; 11.3 awaiting deploy. 7 processes.
- 17:31 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 45/43 +1.3@$10; v10 Polymarket paper 59/65 +17.2@$10; v11 live 108/88 +2.67 real (EF), realised +1.43, wallet 21.25. Build 11.2; 11.3 awaiting deploy (second cap leak 17:27). 7 processes.
- 18:02 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 45/44 -8.7@$10; v10 Polymarket paper 64/67 +57.6@$10; v11 live 108/92 -1.26 real (EF), realised -2.51, wallet 21.11. Build 11.2; 11.3 awaiting deploy. 7 processes.
- 18:33 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 45/45 -18.7@$10; v10 Polymarket paper 64/69 +37.6@$10; v11 live 112/94 +0.50 real (EF), realised -0.75, wallet 22.87. Local twins relaunched on the current proxy at 18:35 after a 14-min feed outage; 7 processes live.
- 19:04 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 45/45 -18.7@$10; v10 Polymarket paper 64/71 +17.6@$10; v11 live 113/96 -0.44 real (EF), realised -1.69, wallet 22.76. Build 11.2; 11.3 awaiting deploy. 7 processes.
- 19:35 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 45/47 -38.7@$10; v10 Polymarket paper 66/71 +40.0@$10; v11 live 116/100 -3.21 real (EF), realised -5.34, wallet 18.75. Build 11.2 (no deploy per the user). 7 processes.
- 20:30 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 46/49 -51.1@$10; v10 Polymarket paper 67/74 +20.1@$10; v11 live 122/100 +2.15 real (EF), realised -0.97, wallet 23.49. VM rebooted 20:18, all relaunched; EF2 forward shadow running. 8 processes.
- 20:51 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 46/50 -61.1@$10; v10 Polymarket paper 67/76 +0.1@$10; v11 live 123/105 -1.89 real (EF), realised -5.01, wallet 19.45. Build 11.2; EF2 shadow 0/4 so far. 8 processes.
- 21:25 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 50/51 -38.4@$10; v10 Polymarket paper 72/76 +71.2@$10; v11 live 126/108 -1.90 real (EF), realised -4.21, wallet 20.24. REVERSAL cap removed (skipped group profitable). 8 processes.
- 21:55 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 51/51 -31.4@$10; v10 Polymarket paper 77/77 +114.7@$10; v11 live 128/111 -3.30 real (EF), realised -5.30, wallet 18.16. EF2 shadow cap 0.60: 10 graded +0.126/fire. 8 processes.
- 22:25 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 53/52 -17.2@$10; v10 Polymarket paper 79/79 +115.1@$10; v11 live 132/112 +0.29 real (EF), realised +0.40, wallet 23.86. REVERSAL 9/2 live since 14:47. EF2 shadow cap 0.60: 12 graded +0.363/fire. 8 processes.
- 22:54 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 56/52 +3.7@$10; v10 Polymarket paper 81/82 +102.9@$10; v11 live 135/112 +3.30 real (EF), realised +5.25, wallet 30.71. REVERSAL 12/2 live since 14:47. EF2 shadow cap 0.60: 13 graded +0.586/fire. Ladder: stake -> $2 at 22:58. 8 processes.
- 23:26 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 59/53 +40.6@$10; v10 Polymarket paper 85/83 +162.4@$10; v11 live 139/113 +8.73 real (EF), realised +12.13, wallet 37.58. REVERSAL 14/2 live since 14:47. $2 phase 5/1 +6.88. EF2 shadow cap 0.60: 15 graded +0.686/fire. H1 Task 12a refuted + retracted. 8 processes.
- 23:57 UTC check-in: fair states since 21:55 - v10 Predict.fun paper 61/55 +48.7@$10; v10 Polymarket paper 87/85 +165.3@$10; v11 live 141/115 +9.17 real (EF), realised +11.26, wallet 34.71. REVERSAL 15/3 live since 14:47. $2 phase 8/4 +6.01. EF2 shadow cap 0.60: 18 graded +0.616/fire. 8 processes.
- 00:27 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 62/56 +46.3@$10; v10 Polymarket paper 90/86 +196.6@$10; v11 live 143/118 +6.50 real (EF), realised +9.46, wallet 32.91. REVERSAL 16/3 live since 14:47. $2 phase 11/7 +4.21. EF2 shadow cap 0.60: 22 graded +0.520/fire. 8 processes.
- 00:57 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 63/58 +36.3@$10; v10 Polymarket paper 91/87 +198.9@$10; v11 live 145/120 +6.93 real (EF), realised +9.88, wallet 33.34. REVERSAL 16/3 live since 14:47. $2 phase 13/9 +4.63. EF2 shadow cap 0.60: 24 graded +0.393/fire. 8 processes.
- 01:28 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 64/59 +40.9@$10; v10 Polymarket paper 92/88 +206.2@$10; v11 live 147/122 +5.38 real (EF), realised +8.34, wallet 31.79. REVERSAL 16/3 live since 14:47. $2 phase 15/11 +3.09. EF2 shadow cap 0.60: 26 graded +0.286/fire. 8 processes.
- 01:59 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 65/59 +48.5@$10; v10 Polymarket paper 94/89 +234.7@$10; v11 live 152/123 +11.15 real (EF), realised +14.79, wallet 38.24, equity 40.87. REVERSAL 17/3 live since 14:47. $2 phase 21/12 +9.53. Ladder -> $3 pending. EF2 shadow cap 0.60: 28 graded +0.361/fire. 8 processes.
- 02:31 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 66/59 +56.7@$10; v10 Polymarket paper 96/90 +256.4@$10; v11 live 155/125 +10.73 real (EF), realised +12.77, wallet 33.83, equity 35.23. REVERSAL 18/4 live since 14:47. $3 phase 1/3 -7.60, back to $2. EF2 shadow cap 0.60: 32 graded +0.319/fire. 9 processes.
- 03:01 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 66/59 +56.7@$10; v10 Polymarket paper 96/91 +246.4@$10; v11 live 158/126 +14.23 real (EF), realised +16.27, wallet 39.33. REVERSAL 18/4 live since 14:47. $2 phase 28/16 +11.02. EF2 shadow cap 0.60: 34 graded +0.349/fire; 11.2 live shadow 0 fires yet. 10 processes.
- 03:32 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 66/60 +46.7@$10; v10 Polymarket paper 97/93 +237.3@$10; v11 live 159/129 +11.01 real (EF), realised +13.05, wallet 36.11. REVERSAL 18/4 live since 14:47. $2 phase 29/19 +7.80. EF2 shadow cap 0.60: 37 graded +0.240/fire (2nd half negative); 11.2 live shadow 0 fires (stale-quote artifact suspected). 10 processes.
- 04:05 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 66/60 +46.7@$10; v10 Polymarket paper 98/96 +216.2@$10; v11 live 162/132 +11.26 real (EF), realised +13.29, wallet 31.90. REVERSAL 18/4 live since 14:47. $2 phase 32/22 +8.04. EF2 shadow cap 0.60: 41 graded +0.161 (2nd half -4.71); 11.2 live shadow 1/1. 10 processes.
- 04:35 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 67/60 +55.7@$10; v10 Polymarket paper 100/97 +224.6@$10; v11 live 165/134 +10.43 real (EF), realised +13.60, wallet 34.67. REVERSAL 19/4 live since 14:47. $2 phase 36/24 +8.35. EF2 shadow cap 0.60: 43 graded +0.107 (2nd half -5.71); 11.2 live shadow 1/1. 10 processes.
- 05:10 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 69/61 +68.2@$10; v10 Polymarket paper 104/99 +233.4@$10; v11 live 169/137 +11.24 real (EF), realised +14.42, wallet 35.48. REVERSAL 19/4 live since 14:47. $2 phase 40/27 +9.16. EF2 shadow cap 0.60: 46 graded +0.141 (2nd half -3.95). 10 processes.
- 05:42 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 69/61 +68.2@$10; v10 Polymarket paper 107/100 +261.0@$10; v11 live 171/141 +5.85 real (EF), realised +9.15, wallet 30.21. REVERSAL 20/4 live since 14:47. $2 phase 43/31 +3.89. EF2 shadow cap 0.60: 49 graded +0.071 (2nd half -5.95). 10 processes.
- 06:15 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 71/62 +76.1@$10; v10 Polymarket paper 109/105 +226.5@$10; v11 live 178/141 +19.82 real (EF), realised +24.53, wallet 47.60. REVERSAL 23/4 live since 14:47. $2 phase 53/31 +19.28; ladder -> $3. EF2 shadow cap 0.60: 53 graded +0.140. 11 processes.
- 06:46 UTC 09-11 check-in: Tokyo restarted ~06:29 (safe startup, master OFF), re-armed 06:47. fair states since 21:55 - v10 Predict.fun paper 72/63 +75.8@$10; v10 Polymarket paper 111/106 +228.6@$10; v11 live 179/142 +19.19 real (EF), realised +25.40, wallet 48.46. REVERSAL 24/4 live since 14:47. $3 phase 2/1. EF2 shadow cap 0.60: 55 graded +0.099. 11 processes.
- 07:18 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 73/64 +78.1@$10; v10 Polymarket paper 111/108 +208.6@$10; v11 live 181/145 +16.49 real (EF), realised +22.70, wallet 42.76. REVERSAL 24/4 live since 14:47. $3 phase 4/4. EF2 shadow cap 0.60: 57 graded +0.060 (2nd half -6.68). 11 processes.
- 07:49 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 75/66 +71.7@$10; v10 Polymarket paper 113/108 +238.4@$10; v11 live 184/147 +18.39 real (EF), realised +21.60, wallet 41.66. REVERSAL 24/5 live since 14:47. $3 phase ~6/6. EF2 shadow cap 0.60: 60 graded +0.040 (2nd half -7.60); 11.2 live shadow 1/4. 11 processes.
- 08:21 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 76/67 +79.8@$10; v10 Polymarket paper 114/109 +236.9@$10; v11 live 187/149 +21.56 real (EF), realised +28.28, wallet 48.34, equity 50.94. REVERSAL 28/5 live since 14:47. Ladder -> $4 pending. J REFUTED at 102 graded (2nd half negative at every cap). 11 processes.
- 08:52 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 76/67 +79.8@$10; v10 Polymarket paper 115/111 +223.7@$10; v11 live 188/154 +5.59 real (EF), realised +14.17, wallet 33.23. REVERSAL 29/5 live since 14:47. $4 phase 1/2 -6.14 -> back to $2; ladder step-ups now need two consecutive check-ins above the rung. 11 processes.
- 09:23 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 77/68 +80.7@$10; v10 Polymarket paper 118/111 +253.5@$10; v11 live 192/156 +9.51 real (EF), realised +18.09, wallet 39.16. REVERSAL 29/5 live since 14:47. $2 stays (39.35 < 40). Twins restarted 09:17 after the proxy change. 11 processes.
- 09:54 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 78/69 +80.0@$10; v10 Polymarket paper 118/113 +233.5@$10; v11 live 193/159 +4.80 real (EF), realised +14.07, wallet 33.23. REVERSAL 30/5 live since 14:47. $2 stays. 11.2 forward ledger 22 fires -0.238. 11 processes.
- 10:26 UTC 09-11 check-in: fair states since 21:55 - v10 Predict.fun paper 80/71 +83.5@$10; v10 Polymarket paper 122/115 +254.4@$10; v11 live 194/163 -0.84 real (EF), realised +7.43, wallet 28.49. REVERSAL 31/6 live since 14:47. $2 stays (equity 30.56, step to $1 if < 30). 11.2 forward ledger 23 fires -0.271. 11 processes.
- 10:56 UTC 09-11 check-in: Predict.fun paper 82/72 +90.6@$10; Polymarket paper 122/116 +244.4@$10; v11 live 197/165 +0.73 real (EF), realised +9.26, wallet 30.33, equity 32.33. REVERSAL 32/6. $2 stays; 10:41 sighting at 43.15 void. 11 processes.
- 11:26 UTC 09-11 check-in: Predict.fun paper 82/74 +70.6@$10; Polymarket paper 124/119 +239.4@$10; v11 live 200/168 +2.33 real (EF), realised +7.39, wallet 30.45, equity 30.45. $1 step-down landed at 11:21; 11:26 is the first sighting back above 30. REVERSAL 33/8. 11 processes.
- 11:56 UTC 09-11 check-in: Predict.fun paper 85/74 +99.0@$10; Polymarket paper 127/121 +246.6@$10; v11 live 202/171 +1.22 real (EF), realised +6.28, wallet 28.34, equity 28.97. Stake $1. REVERSAL 33/8. H1 forward ledger 29 fires 10 hits. 11 processes.
- 12:27 UTC 09-11 check-in: Predict.fun paper 87/76 +94.0@$10; Polymarket paper 131/122 +286.6@$10; v11 live 203/175 -1.64 real (EF), realised +2.02, wallet 24.08, equity 24.27. Stake $1 (floor). REVERSAL 34/10, per $1 +0.071. Drawdown from the +28.28 high; twins also gave back, so market-wide. No rule changed. H1 ledger 30 fires.
- 12:42 UTC 09-11: BOTH LANES PAUSED by user decision after the day gave back +28.28 to +0.02. EF and REVERSAL manual_enabled=false, verified MANUALLY OFF. Master stays ON, no positions taken. Equity 22.10, one position left open to settle. Paper runs, twins, loggers and shadows all continue. Do not re-arm without the user.
- 12:56 UTC 09-11 check-in: lanes PAUSED (no live fires). Paper runs, twins and both 1 Hz loggers continue. Both check-in triggers rewritten to carry the pause and forbid re-arming a lane after a restart.
- 13:26 UTC 09-11 check-in: lanes still paused. H1 Task 21 corrected my 1.5c (crossing is only +0.26c; usable prior +0.5c) and confirmed 13.9% venue disagreement on traded candles. Patched the Polymarket paper runner to log book_age_ms and restarted it (430 rows preserved) - unblocks certifying the paper quote age.
- 14:00 UTC 09-11: v12 Polymarket lane running in PAPER on port 8790 (mode=pnl, $10/fire, db v12_poly_weekend.sqlite3). Tests pass. Fixed the run doc defaulting to accuracy mode; flagged the unverified polymarket-client package on the live path. No credentials used. 12 processes.
- 13:56 UTC 09-11 check-in: lanes paused. v12 Polymarket lane fired its first paper trade 13:55:56 (quote age 60 ms, PAPER_FILLED). v10 runner has 5 certified-quote-age fires. 12 processes.
- 14:05 UTC 09-11: user instruction via H1 - 2-hour cadence until Sunday night, cut processes. Stopped twin B, twin TE and ef2_shadow (all refuted); 9 processes left, loggers protected. H1 Task 24: retracted my "204 candles never offered" claim (the book was there, the filter declined the price); headline is +0.123/fire not +0.187; quote_age still FAILS. New: the Polymarket edge is a SIDE SKEW - UP 3.33c cheaper, DOWN 2.62c dearer.
- 14:11 UTC 09-11: added the v12 Polymarket paper-execution lane as a 4th row in fair.py, and added its DB to the ci.sh snapshot list (learner/live_backup/v12_poly_lane.sqlite3.gz). Dropped the two stopped twins from the snapshot list. It now appears in every states report.
- 14:15 UTC 09-11: user ruled the handed-over v12 execution build OBSERVATION ONLY - keeps running in paper, code barred from the real v12 (no dashboard/controls). learner/v12_polymarket/DO_NOT_MERGE.md written. The Polymarket executor is to be built inside build11 as a venue backend behind the existing dashboard and controls.
- 14:21 UTC 09-11: rewrote fair.py per the user - the window now OPENS WITH THE NEWEST RUN (max of each run's first record) so every run is judged on the same candles. Currently that is the v12 lane, 13:55 UTC. Old behaviour kept as fair_since_tokyo.py, and fair.py takes an epoch-ms or "tokyo" argument to override.
- 14:25 UTC 09-11: user clarified the saving is on MY responses, not on model processes. Restarted twin B 8795, twin TE 8798 and ef2_shadow.py (12 processes, twins relaunched from v11/launch which is their required cwd); restored them to the ci.sh snapshot list. Check-in cadence set to 1 HOUR, next 15:25 UTC.
- 14:38 UTC 09-11 safety net: healthy, lanes paused, 12 processes. Safety net moved from 2h to 4h (cron 38 */4) since the main check-in is now hourly and re-arms itself - saves turns without losing the recovery path.
- 14:40 UTC 09-11: the pause had reverted - master OFF "safe startup" with no restart (uptime 8.1 h) and all three kinds back to manual_enabled TRUE. Re-posted false for EF/REVERSAL/MAIN, verified SIGNAL OFF on all three. Pause is now double-locked. Cause unknown; check manual_enabled every check-in, not just master.
- 14:45 UTC 09-11: answered why the two Polymarket runs diverge - same side on 11 of 12 shared candles; the whole ~17-point gap is one candle (37000) where v10 fired DOWN at 104 s and won while v12 fired UP at 66 s and lost. Cause is timing jitter between two independent processes, and it exposes that the model's SIDE is unstable in the decision second.
- 15:10 UTC 09-11: user granted re-arm authority ("whenever you think it's profit time turn the wanted signals"). Pre-committed the criterion in NOTES_v12 BEFORE using it: REVERSAL re-arms when the Predict.fun paper last-20 is net positive at TWO consecutive hourly checks; EF additionally needs its own live last-20 positive; MAIN stays off; stake $1 per the ladder; existing kill rules apply; symmetric re-pause. Reading at 15:10: Predict.fun last-20 +0.010/$1 (first sighting), last-40 -0.022; Polymarket last-20 -0.308. NOT re-armed.
- 16:12 UTC 09-11 check-in: RE-ARM RULE FIRED (Predict.fun paper last-20 +0.129 after +0.010 at 15:10 = two consecutive). REVERSAL re-armed LIVE at $1, master ON, verified ACTIVE/effective True. EF stays OFF - its own live last-14 is -0.443 per $1, so its extra condition failed. MAIN off. Kill rules and symmetric re-pause both live. Fair table since 15:04: PF paper 4/3 +19.5, Poly paper 6/3 +35.8, v12 lane 6/3 +38.8, Tokyo 0/0. 12 processes.
- 16:39 UTC 09-11 safety net: healthy. Rewrote the safety-net prompt - it still said "all lanes paused, do not re-arm", which would have fought the 16:12 re-arm. It now carries the live state (REVERSAL ACTIVE at $1, EF/MAIN off), the pre-committed rule including the symmetric re-pause, and the restart-restore sequence.
- 17:12 UTC 09-11 check-in: SYMMETRIC RE-PAUSE fired - Predict.fun paper last-20 went -0.038 (from +0.129 at 16:12), so REVERSAL is OFF again after ~1 h live. Verified all three kinds MANUALLY OFF, master ON, stake $1. The live hour was 2W/1L +0.07 real, equity 22.15. Rule NOT changed mid-flight; flagged the hourly-oscillation risk to review only if it repeats without net progress. Fair since 15:04: PF paper 6/8 -10.1, Poly paper 11/6 +47.8, v12 lane 11/5 +61.2, Tokyo 2/1 +0.7. 12 processes.
- 18:10 UTC 09-11: answered whether the v12 lane is beating the v10 paper run - NO. Same side on 25 of 27 shared candles and within 1.5 points there; the whole ~50-point gap is 2 opposite-side candles that v12 won. At 14:45 the same jitter put v12 17 points BEHIND. Median decision second identical (62 s). Confirms the model side is unstable in the decision second; entry timing must be pinned in the executor.
- 18:12 UTC 09-11 check-in: PF paper last-20 +0.022 (first sighting again after the 17:12 reset), last-40 +0.077; Poly paper last-20 -0.042. Lanes stay OFF; arms at 19:12 if positive again. Tokyo master ON, all kinds MANUALLY OFF, equity 22.15. 12 processes.
- 19:12 UTC 09-11 check-in: rule fired on the 2nd consecutive sighting (18:12 +0.022, 19:12 +0.002) - REVERSAL LIVE again at $1, verified ACTIVE, EF/MAIN off, equity 22.15. Flagged that +0.002 is a hair above zero and the criterion has no dead zone; pre-committed the review condition (4+ flips by Sunday with cumulative real PnL < +1.00 = refuted, redesign with a dead zone). Fair since 15:04: PF 13/13 +29.8, Poly 20/17 +38.2, v12 21/14 +98.6, Tokyo 2/1 +0.7.
- 19:40 UTC 09-11: USER OVERRIDE - EF armed as a monitored run despite failing rule condition 2 (its live last-20 was -0.443 per $1). Verified EF ACTIVE, REVERSAL ACTIVE, MAIN off, master ON, stake $1, equity 22.15. EF runs under the same kill rule as REVERSAL (cumulative < -3.0 over 20 fills, or avg slip > 3c); symmetric paper re-pause now applies to both lanes; EF live last-20 reported hourly.
- 20:12 UTC 09-11 check-in: KILL RULE FIRED, BOTH LANES OFF. REVERSAL last-20 cumulative -3.76 (< -3.00, literal trigger); EF killed too at -2.71 over 6 fills = -0.452/fill, 3x the rule's implied rate (judgement, flagged). Equity 22.15 -> 16.53 in ~30 min, wallet 16.44, one position left open. The paper trigger said HOLD (+0.014) while the live account lost 5.6 - third strike against the criterion. Verified all three kinds MANUALLY OFF.
- 21:00 UTC 09-11: H1 Task 21b - the CERTIFIABLE Polymarket paper number (quote age known, n=61) is -0.062 per $1, both halves negative; fresh-quote trades -0.141 (n=48) vs stale-quote trades +0.232 (n=13). The Task 20 mechanism, reproducing. +0.187/+0.123 must not be sized on; go/no-go needs ~150 certifiable rows. Smoke test staged but launch blocked by the session permission classifier - user asked to change the mode.
- 21:10 UTC 09-11: LIVE Polymarket smoke test launched on port 8791 ($4/order, 2-fill stop watcher) after the user switched permission mode off Auto. SecureClient initialised at startup, account not closed-only. Paper lane on 8790 continues. Measures fill quality, not edge.
- 21:12 UTC 09-11 check-in: PF paper last-20 -0.253 -> trigger NEGATIVE. All three Tokyo kinds found MANUALLY OFF again, not by me (someone posted false after the 21:52 REVERSAL fill; engine has no audit field). EF since 20:46 re-arm 0/2 -1.96, last-9 -0.630/$1; REVERSAL 1/0 +0.54. Equity 15.02. Leaving lanes OFF - rule, EF rate and equity all agree. Smoke lane 8791 warming. 13 processes.
- 21:30 UTC 09-11: live smoke - 2 signals fired (21:21 UP 0.52 ev 0.1579; 21:27 DOWN 0.44 ev 0.2566), BOTH SKIPPED with ev_failed_at_cap, zero orders sent. Cause: the model threshold is dynamic and sits just under the achieved EV, so a 1-tick pad always fails the recheck. Restarted with --pad-ticks 0 so orders can reach the book. Paper runs therefore count trades the live executor would decline.
- 21:46 UTC 09-11: FIRST REAL POLYMARKET ORDER SUBMITTED (DOWN 0.49, pad 0, EV-at-cap passed, latency 986 ms) and REJECTED - "Trading restricted in your region" (geoblock). No fill, no position, no money moved. Lane self-disabled on the ambiguous-submit guard; process stopped. Egress IP is US (Columbus OH, Google LLC) so the block is on this container, not necessarily the user. Auth, SDK, pad-0 fix and the safety guard all verified working; fill quality still unmeasured.
- 22:00 UTC 09-11: live Polymarket execution CLOSED. User is an Indian national resident in the UK; the UK is close-only on both frontend and API, and residence governs. Declined the Tokyo-server routing as circumvention. Polymarket continues as a research venue only; Predict.fun stays the live venue. Smoke lane stopped, its 3-row DB kept as the record.
- 22:12 UTC 09-11 check-in: PF paper last-20 -0.051, lanes stay OFF. 4 flips today with cumulative real PnL about -1.35 -> the re-arm criterion is REFUTED under its own 19:12 review condition; no automatic re-arm until a dead-zone redesign is pre-committed. Tokyo equity 15.02, 6x 502 before answering. Worker restart mid-check; all 12 processes survived; keepalive recreated.
- 22:30 UTC 09-11: Polymarket live PARKED (not closed). Support per the user: VPS and account holder must both be in non-restricted areas. Tonight both were restricted (container Ohio, user UK). Reopens when the user is in a permitted jurisdiction, executor on Tokyo only.
- 23:20 UTC 09-11: lost ~1 h of Polymarket paper data - both runners kept running with dead websockets after the 22:12 restart (feeds 57 min stale) and twins B/TE were dead, but my keepalive only counted processes so nothing alerted. My error. Recovered all 12 processes, feeds fresh. Health watch now checks feed age and logger row age, not just process count.
- 23:15 UTC 09-11 check-in: recovery verified - both Polymarket runners now 0.2 s feed age (was 3450 s), 12 processes, both paper runs firing again. PF paper last-20 -0.051, trigger NEGATIVE, lanes stay off (criterion refuted regardless). Tokyo equity 15.02, all kinds off, nothing open.
- 23:20 UTC 09-11: user asked to stop Polymarket live trading - verified nothing was live (only --execution paper on 8790, 0 attempt rows; smoke lane stopped 21:50). Added locks: poly.env and both launchers renamed .DISABLED. Confirmed in writing that the paper lane is paper-only by construction (fire() branches on execution before lane_enabled is consulted). Data collection untouched, 12 processes.
- 00:20 UTC 09-12 check-in: trigger -0.071, lanes off, equity 15.02, 12 processes. Overnight Predict.fun paper (+15.5) has overtaken Polymarket paper (-17.8) over the shared window for the first time. Also: no "l2 full.zip" exists here; the raw L2 data (3.5 GB Binance depth + 1.3 GB Polymarket) and the pre-split deliver/ archives are all GITIGNORED and exist only in this container.
- 01:20 UTC 09-12 check-in: trigger POSITIVE (+0.134 last-20, +0.015 last-40) but NOT arming - the criterion was refuted at 22:12 and must be redesigned with a dead zone before it is used again. Lanes stay off, equity 15.02, 12 processes, 12 G free. Polymarket paper recovered -21.3 -> +4.3, so the previous hour's cross-venue reading was noise.
- 01:40 UTC 09-12: received the Polymarket v12 checkpoint zip. Checksums all OK, its 32 tests pass here, model_v10.json and btc_model_v10.py byte-identical to ours. Ships the old dashboard/controls (the 14:15 objection, now addressed) plus an audit script and baseline DB. Headline +0.118 per $1 on 412 settled - but its trades table has NO quote-age column, so it is uncertifiable, same class as our retracted +0.123; certifiable rows read -0.066. Copied to learner/v12_checkpoint/, not launched.
- 02:20 UTC 09-12 check-in: trigger +0.418 last-20 (best ever) and +0.082 last-40 - would arm under the old rule, NOT arming because the criterion is refuted pending a written redesign. Equity 15.02, lanes off, 12 processes. Predict.fun paper +55.9 vs Polymarket paper -1.9 on the shared window, third hour running.
- 03:20 UTC 09-12 check-in: trigger +0.148 last-20, +0.092 last-40 - third consecutive positive hour, still not arming (criterion refuted, replacement unwritten). Equity 15.02, lanes off, 12 processes. Flagged for Sunday: the two Polymarket runners are now 109 points apart on the same venue and window, far beyond the measured timing jitter.
- 04:20 UTC Sat 09-12: fair PF 33/33 +42.9 | Poly 45/48 -3.8 | v12 lane 47/43 +107.3 | Tokyo live 5/10 -7.06 real. Trigger positive 4th hour (+0.137 last-20, +0.033 last-40); HELD, criterion refuted 22:12 and its replacement is not written yet. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 05:20 UTC Sat 09-12: fair PF 37/36 +49.1 | Poly 47/51 -11.8 | v12 lane 49/46 +99.3 | Tokyo live 5/10 -7.06 real. Trigger positive 5th hour (+0.118 last-20, +0.164 last-40, its best); HELD, criterion refuted 22:12 and unreplaced. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 06:20 UTC Sat 09-12: fair PF 40/38 +53.9 | Poly 50/54 -1.6 | v12 lane 51/48 +110.4 | Tokyo live 5/10 -7.06 real. TRIGGER FLIPPED NEGATIVE -0.140 last-20 (last-40 still +0.142) after five positive hours - out-of-sample confirmation of the 22:12 refutation; no lane was armed so nothing was exposed. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 07:20 UTC Sat 09-12: fair PF 44/38 +94.7 | Poly 54/55 +25.3 | v12 lane 55/49 +137.3 | Tokyo live 5/10 -7.06 real. Trigger flipped back to +0.264 last-20 one hour after -0.140, while last-40 sat still at +0.143 - the 20-fire window is measuring coin flips, not an edge. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 08:20 UTC Sat 09-12: fair PF 46/40 +100.8 | Poly 59/56 +67.0 | v12 lane 60/51 +175.6 | Tokyo live 5/10 -7.06 real. Best Polymarket hour of the run, both runners 5W/1L; all three paper runs positive over the fair window for the first time. Trigger +0.290 last-20, +0.213 last-40, still held. Runner gap 108.6, first move off the 111-112 band. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 09:20 UTC Sat 09-12: fair PF 49/44 +95.4 | Poly 62/59 +68.8 | v12 lane 63/54 +180.7 | Tokyo live 5/10 -7.06 real. Flat hour, all three paper runs still positive. Trigger +0.231 last-20, +0.174 last-40, third positive reading, still held. Runner gap back to 111.9 so the 108.6 at 08:20 looks like the outlier. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 10:20 UTC Sat 09-12: fair PF 52/46 +118.6 | Poly 68/62 +116.9 | v12 lane 70/56 +240.8 | Tokyo live 5/10 -7.06 real. Biggest hour of the run on all three paper lanes. Trigger +0.324 last-20 (highest yet) but last-40 fell to +0.092; still held. Runner gap widened to 123.9, breaking the 111-112 band. Master ON, all kinds false, equity 15.02, 12 procs, 12 G free.
- 11:00 UTC Sat 09-12: H1 closed Task 17.2 - ledger row M (11.2 direction model as the EF probability) REFUTED on the forward test as well as the replay. 104 fires, 48.1% hit, -0.040/fire, halves -0.214/+0.134; verify.py fails halves and beats-the-null. Sixth candidate to die at the recorded-to-honest-to-live ladder. The direction signal itself still stands; the monetisation does not.
- 11:30 UTC Sat 09-12: session container restarted. All 12 model processes survived (launched detached); only my watcher shells died. Verified by row age not pid: book1s and poly1s writing 1s-old rows, venue_collect 3s, all five ports 200. No Polymarket book data lost. Watcher replaced with learner/tools/watch_live.py, which checks produced rows and not process counts.
- 11:20 UTC Sat 09-12: fair PF 53/49 +97.7 | Poly 68/64 +96.9 | v12 lane 70/58 +220.8 | Tokyo live 5/10 -7.06 real. Give-back hour, all three lost about 20. Trigger fell to +0.015 last-20 on 9W/11L, positive only because the winners were cheap; last-40 +0.139. Still held. Runner gap unchanged at 123.9. Master ON, all kinds false, equity 15.02, 13 procs incl. watcher, 12 G free.
- 12:20 UTC Sat 09-12 INCIDENT: the 11:30 container restart changed the proxy port (43733 -> 41463) and build10, the v10 runner and the v12 lane ran with dead websockets for 72 min while still answering HTTP. Recovery task had been killed mid-run, so only the build11 twins came back. Confirmed via feed_age_s ~4326 s and /proc/<pid>/environ, recovered on the same databases via restart_all.sh plus a new restart_v12_lane.sh. Polymarket order-book tape NOT lost. Watcher missed it because it probed ports and logger rows, not engine feed ages; watch_live.py now reads feed_age_s on 8788/8790 with a 180 s limit across all seven ports. Fair PF 53/49 +97.7 | Poly 69/64 +114.1 | v12 lane 71/58 +238.1 | Tokyo live 5/10 -7.06 real, unaffected.
- 13:00 UTC Sat 09-12: H1 CORRECTION to Task 21b. The certifiable Polymarket number is +0.022 per $1 at n=148 (halves -0.058/+0.102), NOT the -0.062 reported at n=61. The fresh-vs-stale split is retracted too: fresh +0.015 n=130 vs stale +0.078 n=18, ordering collapsed, no stale-quote effect in that window. Corrected in NOTES_v12. What survives: uncertifiable +0.120 n=430 vs certifiable +0.022 n=148 is still a five-fold gap, so still do not size on +0.187 - but the honest number is FLAT, not negative. Side skew not yet visible in the certifiable set (DOWN n=93 +0.019, UP n=55 under the bar).
- 13:20 UTC Sat 09-12: fair PF 56/51 +103.5 | Poly 70/67 +100.7 | v12 lane 73/61 +225.3 | Tokyo live 5/10 -7.06 real. Post-incident recovery holding, all feeds 0 s and 6 new graded fires across the two venues. Trigger turned negative at -0.038 last-20 (last-40 +0.137); lanes already off. Master ON, all kinds false, equity 15.02, 13 procs, 12 G free.
- 14:20 UTC Sat 09-12 (ran 14:40): fair PF 59/55 +89.5 | Poly 75/69 +135.6 | v12 lane 78/63 +260.2 | Tokyo live 5/10 -7.06 real. Trigger -0.059 last-20 at 10W/10L, last-40 +0.089; not arming. Master ON, all kinds false, equity 15.02, 13 procs, 12 G free. Separately delivered v12.2 to the user: MAIN/REVERSAL ported from Build 11 and working under Trade Controls, all money figures taken from the Polymarket API, feed staleness measured by event lag not arrival, pending reserve verified against venue open orders. 82 tests pass.
- 15:00 UTC Sat 09-12: H1 reports the weekend cell of the REFUTED 11.2 test passes every verify.py check (n=62, +0.073/fire, halves +0.025/+0.121, beats null). NOT shipped and NOT a ledger candidate: one Saturday only, halves are morning-vs-afternoon of the same day, it would be a gate on a score that just failed its own test, and there is no mechanism. Honest claim is 'the weekend cell passes', not 'weekend beats weekday' - the weekday cell is n=57 and not read. Needs 100+ fires across two separate weekends, halves split by weekend, before it is actionable. Row M stays REFUTED.
