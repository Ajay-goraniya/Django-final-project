# v12 notes - live findings from the Build 11 (v11) run (started 2026-09-09 16:30 UTC)

Scope: what the v11 build (Polymarket signal, Predict.fun execution, 2% fee, EV scale 0.75, calibration off,
10-s signal hold, one-sided refusal) does live, versus the four v10 runs on the same candles. Live data only.
Old-version findings keep going to NOTES_v11.md.

## Baseline at launch (retro on 09-08 17:31 -> 09-09 16:22, 139 recorded fires)
- v10-as-run replay = live (+223 vs +225). v11 launch settings in-sample +422 on 163 trades (65%).
- Calibration table lost out of sample on both time splits -> shipped OFF. EV scale 0.75 held out of sample.

## Running log
### 16:30-18:00 UTC (first 90 min): 8/16, -5.0 at $10
- Same window: Predict.fun pnl v10 4/8 -7.3, Polymarket pnl v10 3/6 -7.6 -> v11 is not worse, it fires ~2x as often (16 of 17 candles vs 6-8) so the chop shows faster.
- The 8 fires that also pass the strict (x1.0) threshold: 3/8 -18; the 8 extra fires from x0.75: 5/8 +13.
- By confidence p<0.62 3/7, p>=0.62 5/9 (the losing streak 16:40-17:20 included p 0.73 and 0.63 fires). Timing: 13 of 16 fires inside 60 s (7/13), 60-180 s 1/3.
- Signal quality: every fire on the Polymarket signal; one-sided refusals only in the last 2 min of candles; 0 venue fallbacks; ~1 socket reconnect per candle (rotation) bridged by the 10-s hold. No errors, no relaunch.
- Verdict pending: needs 60-80 fires against the Polymarket v10 run before judging the v11 layer.

### 18:24 UTC (114 min): 9/20, -22.7 at $10
- Same window v10: Predict.fun pnl 4/10 -27.3, Polymarket pnl 3/9 -37.6, Predict.fun accuracy 15/21. v11 is losing less than either v10 pnl run on the same tape, with 2x the fires.
- Strict-threshold fires 3/9 -27.8 vs x0.75 extras 6/11 +5.1 (second check-in in a row the "extra" fires are the better half). p<0.62 4/9 -2.1, p>=0.62 5/11 -20.7. Timing <60 s 8/17, 60-180 s 1/3. Regime low 2/4, mid 4/10 -16, high 3/6.
- 18:05 and 18:15: all three (v11, both v10) fired UP and lost - same-signal losses, the model, not the layer. 18:00: v11 DOWN won where Polymarket v10 UP lost.
- Signal: polymarket 2011, held 37, one-sided 296, fallback 0; 27 reconnects bridged. No errors, no relaunch.

## Market-change detector test (18:50 UTC, all 296 pnl fires of the three pnl runs, 25 h)
- Hourly hit rate swings 24%-73% on every run; losing hours today 16:00 (29%), 18:00 (24%), and 01:00 (25%) yesterday. The change is real and visible after the fact.
- Trailing 12-candle Polymarket leader conversion (at 60 s) does NOT separate it: the worst hours had 54-61% conversion, but so did 21:00 and 23:00 yesterday, which were the best (69%). By band, pooled: conv<=55% 15/25 +43 | 55-70% 59/117 +15 | >70% 85/154 +229. A gate at 55% would have cost the Polymarket v10 run $67 (+240 -> +173) and given v11 +20. Not a gate; the >70% band is where the money is, the middle band is flat.
- rv60 median does not separate either (16:00 chop 0.38 vs 17:00 win hour 0.31; 15:00 0.93 was 50%).
- Conclusion for v12: no single trailing statistic found yet that flags the losing hours before they happen; still a frequency dial, not a switch. Keep collecting; test a two-signal rule (conversion + book-gap width) once day 2 is complete.

### 18:56 UTC (146 min): 12/27, -30.7 at $10
- Same window v10: Predict.fun pnl 5/14 -48.4, Polymarket pnl 3/12 -67.6 -> v11 still loses least of the three pnl runs on this tape, at 2x the fires.
- This half hour the extras stopped carrying: strict-thr 5/13 -22.7, x0.75 extras 7/14 -8.0. p>=0.62 8/18 -28.6 is where the losses sit (18:30, 18:45, 18:50 all UP at p 0.62-0.68 and lost; 18:45 all three runs UP and wrong). p<0.62 4/9 -2.1. Regime: low 2/5, mid 6/14, high 4/8 - flat everywhere.
- Signal: polymarket 2378, held 37, one-sided 296, fallback 0; 34 reconnects bridged. No errors, no relaunch.

### 19:28 UTC (178 min): 17/33, +3.7 at $10 - back above zero
- 19:00-19:20: 4/5 (19:00 DOWN 0.54 W with both v10 runs DOWN; 19:10/19:15/19:20 UP at 0.46-0.54 W where neither v10 pnl run fired, and the Polymarket runner fired DOWN on 19:15 and 19:20 - opposite side, ungraded yet). Same window v10 since 16:30: Predict.fun pnl 6/15 -35, Polymarket pnl 3/12 -68; v11 +4 on the same tape.
- Breakdown: strict-thr 8/16 +2.3 | extras 9/17 +1.5; p<0.62 6/12 +8.8 | p>=0.62 11/21 -5.1; <60 s 16/28 +36.8 | 60-180 s 1/5 -33.1 (all five mid-candle fires but one lost - watch); regime low 4/7 +11, mid 6/14 -11, high 7/12 +4.
- Signal: polymarket 2653, held 37, one-sided 296, fallback 0; 41 reconnects bridged. v11 grades from Predict.fun/Binance settlement, so it is not affected by the Polymarket resolution lag. No errors, no relaunch.

### 20:00 UTC (211 min): 19/39, -23.3 at $10
- 19:30-19:55: 2/5 (two DOWN wins at p 0.73/0.80, three cheap-ask losses at p 0.59-0.62). Same window since 16:30: Predict.fun v10 7/16 -20; Polymarket v10 3/13 -78 but with 7 fires ungraded (resolution stall), so that comparison is incomplete.
- Breakdown: strict 9/19 -11 | extras 10/20 -12 (even now); p<0.62 6/15 -21 | p>=0.62 13/24 -2; <60 s 17/32 +13 | 60-180 s 2/7 -37 (the mid-candle fires keep losing: 7 fires, 2 wins); regime mid 6/17 -41 is the sink, low 4/7 +11, high 9/15 +7.
- Signal: polymarket 3534, held 55, one-sided 462, fallback 0; 48 reconnects bridged. No errors, no relaunch.

## What the losing tape looks like (20:10 UTC, Binance 5-min candles 16:00-20:00 vs the winning windows)
- By candle statistics it is NOT distinguishable: median range 10.4 bps, body 5.3 bps, direction flips 44%, 25% of candles closing within 3 bps of open - the same as yesterday 17-21 (11.3 / 6.1 / 50% / 31%) and today 05-09 (10.0 / 5.8 / 46% / 29%). Volatility, wicks and flip rate do not flag it.
- What differs is direction persistence: a slow grind from 78,870 to 78,230 (-80 bps in 4 h) in small steps; 30 of 49 candles closed DOWN, 16:35-19:00 was 18 DOWN of 25. The model's early-candle signal buys the intra-candle dip: 11 of v11's 20 losses were UP fires in that grind (16:40, 16:45, 17:00, 17:15, 17:55, 18:05, 18:15, 18:30, 18:45, 18:50, 19:35). Same failure as the Sep 8 19:43 note (engine's DOWN fires in an uptrend), opposite direction.
- Hit rate by candle size, all 314 pnl fires: |close-open| <3 bps 44% (coin-flip closes), 3-6 bps 56%, 6-12 bps 55%, >12 bps 74%. v11 in this window lost even on the decisive candles (6/14 on >6 bps), i.e. wrong side, not noise.
- For v12: the previous-candle trend filter was rejected on Sep 8 data (7/8 removed were wins). Re-test it on the full 27 h now that a second, opposite grind exists; the answer decides whether a slow-trend guard belongs in the decision layer.

## Slow-trend guard re-test (20:20 UTC, 320 live pnl fires of the 3 runs, real Binance candles) - CANDIDATE, not shipped
- Candle-majority rules (>=67-75% of the last 6/12/24 candles one way) touch almost nothing (12-20 fires) - the grinds here are made of small mixed candles, not runs of one colour.
- Cumulative-move rule "no fire against the last 12 candles' net move when it exceeds 20 bps": all 171/320 +282 -> kept 133/236 +348, removed 38/84 -66. Positive on both halves (+4 / +62), on all three runs (Predict.fun +17, Polymarket +28, v11 +20), and it catches the 17:35-21:35 block today (removed 4/15 -71). But it COSTS in the reversal-rich winning blocks (09-08 17:35 removed 4/6 +16, 21:35 5/8 +32, 09-09 09:35 9/13 +61) and it is parameter-sensitive: window 6c +241 | 9c +464 | 12c +348 | 18c +345; threshold 15 bps +419 | 20 +348 | 30 +278. That spread is the signature of a rule fitted to one day.
- Decision: keep it as the v12 candidate, re-run at each check-in as data grows; ship only if the 9-18 candle / 15-25 bps region stays positive on a third day and the removed set stays net negative. Do not tune to the maximum.

### 20:31 UTC (242 min): 21/45, -45.6 at $10 - run low
- 20:00-20:25: 2/6. 20:00 all three runs DOWN and right; 20:05 v11 DOWN lost where Polymarket v10 UP won; 20:10/20:25 v11 UP lost where Polymarket v10 fired DOWN (ungraded). Same window since 16:30: Predict.fun v10 8/17 -11, Polymarket v10 6/18 -67 (5 ungraded).
- Breakdown: strict 10/23 -32 | extras 11/22 -14; p<0.62 7/19 -42 | p>=0.62 14/26 -4; <60 s 19/37 +1 | 60-180 s 2/8 -47; regime low 5/8 +21 | mid 7/22 -73 | high 9/15 +7. The mid-vol regime holds the whole loss.
- Trend-guard re-test on 325 fires: 12c/20bps kept 135/239 +356 vs +290 as run; parameter spread unchanged (9c +462, 6c +239; 15 bps +427, 30 bps +296). Still candidate-only.
- Signal: polymarket 4201, held 55, one-sided 462, fallback 0; 57 reconnects bridged. No errors, no relaunch.

## 20:53 UTC - Build 11 on 8794 switched to LIVE execution (user decision)
- Same process/database as the paper run (history kept, paper fires stay SHADOW rows). Credentials in a root-only file next to launch.sh (never in the repo). Auth: JWT obtained, account verified, BUY approvals present, wallet 25.58 USDT at start.
- Settings: master ON, EF only (MAIN and REVERSAL manually off), stake fixed $1.00 (min 1, max 50), v11 mode pnl, EV scale 0.75, calibration off, min size $10 within 2c of ask, slippage cap 100 bps, 3 retries.
- Purpose: measure real fill VWAP vs quoted ask, fill rate, rejections; the money is a rounding error.

## 21:02 UTC - v11 database RESET for a clean live run (user decision); paper history kept
- Paper run 16:30-21:00 saved as learner/live_backup/v11_paper_1630-2100.sqlite3.gz (final 22/49, -67 at $10, vs Predict.fun v10 8/19 and Polymarket v10 6/21 on the same candles).
- Fresh database, relaunched with credentials; re-applied: fixed $1 stake, EF only, master ON at 21:03; v11 mode pnl, EV scale 0.75, calibration off. Counters for v11 start here. Name: v11 (version 11).

## 21:11 UTC - FIRST LIVE ORDER REJECTED: Predict.fun geo-block from the container
- 21:10:53 EF DOWN, candle 21:10, quoted 0.63, stake $1, signed and submitted in 406 ms; Predict.fun answered HTTP 403 "This operation is not available in your jurisdiction". Auth, approvals and the read-only API all work from here; only order placement is refused. The container's egress is in the US (Ohio), where Predict.fun does not accept orders. Not a code bug.
- Master switched OFF at 21:11 to stop a 403 loop; v11 on 8794 continues as a paper run on the reset database (fires still recorded, executor in SHADOW).
- Consequence: real orders must be sent from a jurisdiction Predict.fun serves (the user's phone in the UK). The container keeps signal, paper grading and notes.

### 21:21 UTC (19 min since reset, paper, master OFF): 1/2, -4.4 at $10
- 21:10 DOWN 0.63 won (the order Predict.fun refused with the jurisdiction 403); 21:15 UP 0.48 lost with Predict.fun v10. Signal since reset: polymarket 1112, held 37, one-sided 114, fallback 0. No new failed attempts; executor idle in SHADOW.
- Trend-guard candidate on 342 fires (archived paper fires included): 12c/20bps kept 142/255 +333 vs 182/342 +281 as run, removed 40/87 -51; 15 bps +385, 30 bps +287; 9c +453, 6c +216 - still parameter-sensitive. Not shipping.

### 21:52 UTC (50 min since reset, paper, master OFF): 3/5, +0.8 at $10
- p>=0.62 3/3 +20.8, p<0.62 0/2 -20.0. Same window: Predict.fun v10 1/3 -13, Polymarket v10 3/4 +30. 21:40 v11 UP won with Predict.fun v10 where Polymarket v10 DOWN lost.
- Signal since reset: polymarket 2325, held 102, one-sided 540, fallback 0. No new failed attempts. Trend guard on 349 fires: 12c/20bps +356 vs +305 as run, removed 40/87 -51; 9c +476, 6c +240 - unchanged verdict.
- Execution move: v11 deployed on the user's AWS Tokyo server (ap-northeast-1) via learner/aws_setup.sh as a systemd service with HTTPS dashboard (Caddy, basic auth); master OFF until reachable from here; security-group rules for 80/443 being added.

### 22:25 UTC - v11 LIVE on Tokyo, 30 min: 4 orders, 4 filled, 0 failed; 2/4 settled, realized +0.06 at $1
- Fills: 21:55 UP quoted 0.42 filled 0.42 (won, +1.38); 22:05 lost; 22:15 DOWN 0.43 filled 0.43 (lost); 22:20 UP quoted 0.55 filled 0.57 (2c slip, open). Mean delay 138 ms, all accepted first attempt. Fill quality so far: 3 of 4 at the quote, worst +2c.
- Wallet 25.58 -> 23.91 with one $1 position open (equity 25.62). Capital truth shows "unexplained -1.73" = the open position's shares; verify it clears at settlement, else a ledger bug.
- Paper twin (container) 5/10 -8.1: p>=0.62 4/5 +18.6, p<0.62 1/5 -26.7; extras 3/7 -20 vs strict 2/3 +12 this window. Same candles: 21:40 v11 UP won where Polymarket v10 DOWN lost; 22:00 v11 UP lost where Predict.fun v10 DOWN won; 22:15 both DOWN lost.
- Trend guard on 358 fires: 12c/20bps +335 vs +281 as run, removed 41/89 -54; 9c +445, 6c +216 - unchanged verdict.

## Slow-trend guard: implemented as a dial, shipped OFF (22:45 UTC)
- User's idea: an identifier of how the candles moved over the last 30-40 min. Tested as "no fire against the net move of the last N closed candles beyond X bps" on the realised fires of the three pnl runs (359 fires): 30 min windows LOSE (+186..+267 vs +296 as run: they remove winners); 40-60 min / 15-25 bps all gain (+335..+459), positive on both halves and on every run, 5 of 8 four-hour blocks.
- BUT replayed through v11's own decision path (runner decision log every 15 s, Predict.fun book, launch settings) the same guard HURTS: no guard 143/220 +532, 45 min/20 bps 112/176 +421, 40 min +411, 60 min +435, 30 min +422; the 44 fires it removes won 31 (70%). v11's early cheap against-lean entries are winners in that replay while the v10 runs' later against-lean fires were losers. Two fire sets, opposite verdicts -> not robust.
- Shipped in v11.1 as Trade Controls fields (trend guard candles / bps, 0 = off) with default OFF; evidence in code comments; retro script v11/retro_trend.py. Re-test when a third day exists; the deciding test is the v11 path, not the v10 fires.

### 22:56 UTC - v11 LIVE Tokyo, 61 min: 11 orders, 11 filled, 0 failed; 6/4 settled (60%), realized +1.44 at $1, wallet 25.58 -> 26.02, 1 open
- Fill quality: 9 of 11 at the quote, one +2c, one -1c; mean delay 194 ms, all accepted on the first attempt (72-92 ms server accept). Capital truth "unexplained" cleared to 0.0 once the 22:20 position settled - not a ledger bug, just an open position in flight.
- Paper twin (container, restarted 22:31 for v11.1, guard off) 7/14 -14.9 over the same window while Tokyo is 6/4: different machines fire at slightly different ticks and asks (twin 22:15 DOWN 0.43 L, 22:25 UP 0.54 L; Tokyo's fills at 21:55/22:20/22:40 won). Same-candle vs v10: 22:00 and 22:25 v11 UP lost where both v10 runs DOWN won; 22:40 all DOWN won.
- Twin breakdown since reset: p>=0.62 5/7 +11, p<0.62 2/7 -26; high-vol 0/4 -40. Trend guard on 369 fires unchanged (+366 vs +301 on realised fires; fails on the v11 replay) - dial stays off.
- 23:24 UTC: daily stop-loss set on Tokyo at $5 (day resets 12:00 BST); the engine halts new orders for the day when realized daily PnL <= -5. Take-profit off. Overnight max loss is therefore bounded at ~$5 plus one open position.

### 23:27 UTC - v11 LIVE Tokyo, 92 min: 16 orders, 16 filled, 0 failed; 7/8 settled (47%), realized -1.64 at $1, wallet 22.94 (+1 open), daily stop-loss $5 not hit
- First fill that needed retries: 23:25 candle, quoted 0.50, filled 0.53 on attempt 3 (+3c, inside the 9% tolerance band); mean delay rose to 311 ms because of it. Others at the quote. Fill quality over 16: mean about +0.3c, worst +3c.
- Same window since 21:55: Predict.fun v10 6/9 +18.1, Polymarket v10 5/10 +0.4, v11 live 7/15 -1.64 (about -16 at $10). Same-candle: 22:55 and 23:10 v11 UP lost where Predict.fun v10 DOWN won; 22:40 and 23:05 all right.
- Paper twin (container): 8/19 -45.7 since reset; extras 5/14 -57 vs strict 3/5 +11; first-minute fires 6/15 -42; low-vol 4/11 -40. The twin is doing worse than Tokyo on the same tape (different fire ticks). EV-scale review point is 60 settled live fires (at 15 now).
- Trend guard on 382 fires unchanged (+348 vs +277 realised-fire basis; fails the v11 replay) - off.
- 23:31 UTC: daily stop-loss removed at the user's request (stop_loss 0); no daily limits on the live run.

## 23:50 UTC - fire timing + a model-input discrepancy found (user's question: "average fire time")
- Fire timing: v11 twin median 23 s into the candle (48% of fires in the first 20 s), v10 runs median 63-68 s. v11's first-40-s fires this evening: 22/50 -79 (44%); its 40-60 s fires 5/7 +26. In the same window the v10 runs fired early far less often (11 of 33, 11 of 37).
- Replay through decide_v11 over 27 h says a later earliest-fire second HURTS (15 s +568, 30 s +510, 45 s +402, 60 s +345) in every regime window - so the early fires themselves are not the problem in replay, but the replay does not reproduce the twin: on the same evening the replay gives 30/49 +93 and the actual twin 31/69 -104.
- Root of the mismatch: same model, same candle, nearly the same second, the twin's p_up differs from the runner's by 0.085 on average and picks the opposite side 18 of 69 times. Venue mapping, depth and spot paths are identical; one confirmed difference: the engine fed RAW perp @trade prints into the feature state while the runner and training aggregate them like aggTrade (measured 2.58x more prints; perp_n15 coef 0.0464 per 752 prints -> +0.02 logit typical, more in busy tape). Fixed in build 11.1-perp-agg-fix (aggregation in the engine's on_trade), and every v11 fire now stores its full feature dict so pcmp.py can pin any remaining differing feature against the runner's log.
- Consequence: the Predict.fun v10 paper engine (build 10) has had the same raw-print input since 17:21 09-08; part of "venue > model" may be this. Not changed mid-run (comparison continuity); v10 notes updated.
- Tokyo runs the original v11 (raw prints). The fix reaches Tokyo only when the user pulls and restarts; recommended in the morning once pcmp.py confirms the twin now matches the runner.

### 23:58 UTC - v11 LIVE Tokyo, 2.1 h: 21 orders, 21 filled, 0 failed; 13/8 (62%), realized +2.78 at $1, wallet 25.58 -> 28.36, no open
- Fair window since 21:55: v11 live 13/8 +27.8@$10 | Predict.fun v10 7/6 +0.4 | Polymarket v10 6/8 -22.9. v11 leads both v10 runs on the same candles; 5 of its last 6 won. Fill quality: 19 of 21 at the quote, worst +3c (one 3-attempt fill), mean delay 352 ms.
- Test twins A-D all up, no fires yet since the 23:34/23:50 launches (A past warm-up; ledger unchanged). pcmp input-match: no A fires with feature dicts yet.
- Trend guard on 394 realised fires: +376 vs +272 (removed 45/101 -104) - the realised-fire view keeps favouring it; the v11-replay view does not; twin B answers it live.

### 00:30 UTC - v11 LIVE Tokyo, 2.6 h: 27 orders, 27 filled, 0 failed; 15/12 (56%), realized +1.04 at $1, wallet 26.62
- Fair window since 21:55: v11 live 15/12 +10.4@$10 | Predict.fun v10 9/7 +19.5 | Polymarket v10 6/8 -22.9 (4 ungraded). Tokyo gave back $1.74 in the 00:00 dead tape (2/4 last half hour); fills 25 of 27 at the quote, mean delay 294 ms, zero rejections.
- INPUT FIX CONFIRMED on the twin (build 11.1-perp-agg-fix): twin-vs-runner mean |dp_up| 0.085 -> 0.043 over 6 matched fires (same side 5/6); the residual sits in the fast features (move_bps, imb20, lv) at 3-7 s offsets, and the one fire matched within 3.7 s agreed to 0.004. Recommend the Tokyo update in the morning.
- Twins after ~40 min: A 2/4 +3.0 (median fire 24 s) | B guard 1/5 -26.7 (27 s) | C thr 1.0 2/4 +3.4 (56 s, 1 open) | D auto 2/7 -25.3 (50 s). Far too early; C fires later as designed.

### 01:02 UTC - v11 LIVE Tokyo, 3.1 h: 33 orders, 33 filled, 0 failed; 19/13 (59%), realized +2.48 at $1, wallet 27.06, 1 open
- Fair window since 21:55: v11 live 19/13 +24.8@$10 | Predict.fun v10 11/8 +36.1 | Polymarket v10 10/9 +14.6 (3 ungraded). 00:30-01:00 was a burst hour (v10 pooled 8/10 +83); Tokyo 4/1 in it. Fills 30 of 33 at the quote, worst +3c, mean delay 312 ms, zero rejections.
- Twins (restarted 00:33 on the stable spot host, DBs kept; ~70 min of data): A 4/7 +3.8 (median fire 18 s) | B guard 2/7 -33.0 | C thr 1.0 5/8 +18.0 (median 56 s) | D auto 4/10 -23.3. pcmp A-vs-runner: 10 matches, same side 9/10, mean |dp| 0.038 (was 0.085 before the input fix); residual in lv/imb20/move at 3-8 s offsets.

### 01:35 UTC - v11 LIVE Tokyo, 3.7 h: 39 orders, 39 filled, 0 failed; 24/15 (62%), realized +4.09 at $1, wallet 27.79 (+1 open), equity 29.66
- Fair window since 21:55: v11 live 24/15 +40.9@$10 | Predict.fun v10 13/8 +50.9 | Polymarket v10 10/13 -25.4. Tokyo 5/2 in the last half hour. Fills 36 of 39 at the quote, worst +3c, mean delay 315 ms, zero rejections. Capital truth "unexplained -1.89" = the open position again (clears at settlement each time).
- Twins after 62 min on the stable spot host: A 9/14 +23.5 (median fire 16 s) | B guard 7/14 -12.6 | C thr 1.0 9/14 +31.8 (median 19 s now - the 1.0 threshold did not delay fires this hour) | D auto 9/17 +6.1. pcmp A-vs-runner: 16 matches, same side 14/16, mean |dp| 0.047 (residual in lv/imb20/move at 3-8 s offsets).

### 02:07 UTC - v11 LIVE Tokyo, 4.2 h: 44 orders, 44 filled, 0 failed; 27/16 (63%), realized +5.69 at $1, wallet 30.27 (+1 open), equity 30.6
- Fair window since 21:55: v11 live 27/16 +56.9@$10 | Predict.fun v10 13/9 +40.9 | Polymarket v10 11/13 -15.3. Tokyo 3/1 in the last half hour; v11 now leads both v10 paper runs on the same candles in real money. Fills: mean delay 289 ms, last fill at the quote; 6 of 44 orders needed a retry (13.6% first-attempt failure, all filled inside the slippage band, none lost); capital truth unexplained 0.0, no unredeemed positions.
- Twins (95 min on the stable spot host): A 12/18 +39.3 (median fire 16 s) | B guard 10/18 +3.7 | C thr 1.0 12/18 +49.4 (median 19 s) | D auto 12/21 +21.9 (37 s). Ranking unchanged: C > A > D > B. pcmp A-vs-runner: 21 matches, same side 18/21, mean |dp| 0.057 (residual in lv/imb20/move_bps at 3-8 s offsets - a timing residual, not an input bug; the 0.4 s match agreed to 0.09 on lv only).
- Verdicts still pending: 18 graded per variant, rule needs >= 100 (~6 more hours at this fire rate).

### 02:40 UTC - v11 LIVE Tokyo, 4.8 h: 51 orders, 51 filled, 0 failed; 30/20 (60%), realized +4.40 at $1, wallet 26.98, equity 30.0 (2 open + one $2 payout awaiting redemption)
- Fair window since 21:55: v11 live 30/20 +44.0@$10 | Predict.fun v10 13/11 +20.9 | Polymarket v10 13/14 +0.2 (2 ungraded). Tokyo 3/4 in the last half hour (gave back $1.29 from the 02:07 high of +5.69); still ahead of both v10 paper runs on the same candles. Fills: last at the quote, mean delay 260 ms, 6 of 51 needed a retry (11.8%), none failed; unexplained 0.0.
- Unredeemed: one EF UP win (02:35-02:40 UTC candle, 2.0 shares, $2 payout) listed right after settlement; check it auto-redeems by the next check-in, else a redemption bug.
- Twins (128 min): A 15/25 +27.0 (median fire 15 s) | B guard 13/24 +0.8 | C thr 1.0 15/25 +36.4 (19 s) | D auto 15/28 +9.6 (20 s). Order C > A > D > B unchanged for the third check-in; all four gave back in the 02:00-02:40 chop (A -12, C -13). pcmp A-vs-runner: 26 matches, same side 23/26, mean |dp| 0.058 (lv, imb20, move_bps at 3-8 s offsets).

### 03:13 UTC - v11 LIVE Tokyo, 5.3 h: 56 orders, 56 filled, 0 failed; 33/22 (60%), realized +4.92 at $1, wallet 29.50, equity 30.6 (1 open)
- Fair window since 21:55: v11 live 33/22 +49.2@$10 | Predict.fun v10 13/11 +20.9 | Polymarket v10 14/19 -42.8. Tokyo 3/2 in the last half hour while Polymarket v10 went 1/5 on the same tape; v11 is +28 ahead of the better v10 run and +92 ahead of the worse one at $10 equivalent.
- The 02:35 unredeemed $2 payout redeemed by itself (unredeemed list empty, unexplained 0.0) - not a bug. Fills: last at the quote, mean delay 243 ms, 6 of 56 needed a retry (10.7%), zero failures.
- Twins (160 min): A 18/30 +30.6 (median fire 16 s) | B guard 16/28 +19.4 | C thr 1.0 17/29 +36.0 (20 s) | D auto 17/33 -0.4 (22 s). C still ahead of A on PnL with the same hit rate (4th check-in); B recovered +19 this half hour (3/3) but stays behind A; D lowest hit rate and the only one negative. pcmp A-vs-runner: 30 matches, same side 26/30, mean |dp| 0.061 (lv, imb20, move_bps at 3-8 s offsets).

### 03:47 UTC - v11 LIVE Tokyo, 5.9 h: 63 orders, 63 filled, 0 failed; 38/24 (61%), realized +6.59 at $1 (session high), wallet 31.17 (+1 open), equity 32.1
- Fair window since 21:55: v11 live 38/24 +65.9@$10 | Predict.fun v10 14/13 +9.5 | Polymarket v10 14/22 -72.8. The 03:00 hour hurt both v10 runs (pooled 1/9) while Tokyo went 5/2 in it. Fills: last at +1c, mean delay 240 ms, 6 of 63 needed a retry (9.5%), zero failures, unexplained 0.0, the earlier unredeemed $2 auto-redeemed.
- Container outage: harness restart at 03:38 changed the proxy port; all paper processes lost feeds for ~9 min (two candles); relaunched 03:46 on the same DBs. Twins lose ~2 candles of comparability vs Tokyo for that window.
- Twins before the outage (~35 graded each): A 22/35 +51.9 | B guard 16/31 -10.6 | C thr 1.0 20/34 +35.9 | D auto 20/38 +3.5. First flip: A moved ahead of C (C had led at every earlier check-in) - the C lead was never more than +10 and is inside noise at this sample. pcmp A-vs-runner: 35 matches, same side 30/35, mean |dp| 0.065 (lv/move_bps/imb20 at 3-8 s offsets).

### 04:18 UTC - v11 LIVE Tokyo, 6.4 h: 67 orders, 67 filled, 0 failed; 39/27 (59%), realized +5.00 at $1, wallet 29.58 (+1 open), equity 31.2
- Fair window since 21:55: v11 live 39/27 +50.0@$10 | Predict.fun v10 14/16 -20.5 | Polymarket v10 14/24 -92.8. Tokyo 1/3 in the last half hour (gave back 1.59 from the +6.59 high); still the only positive run over the window. Fills: last at the quote, mean delay 231 ms, 6 of 67 retried (9%), zero failures, unexplained 0.0, nothing unredeemed.
- Twins (~40 graded each, after the 03:46 relaunch): A 25/40 +53.6 | B guard 18/35 -10.5 | C thr 1.0 22/38 +35.4 | D auto 23/43 +5.7. A leads for the second check-in; B and D still negative or flat on hit rate. pcmp A-vs-runner: 40 matches, same side 34/40, mean |dp| 0.065.
- EV-scale review point (60 settled live fires) reached: Tokyo 39/27 at thr 0.75; the paper C twin at thr 1.0 is behind A on the same tape (+35 vs +54) so there is no number supporting a Tokyo change. No change.

### 04:52 UTC - v11 LIVE Tokyo, 6.95 h: 73 orders, 73 filled, 0 failed; 41/31 (57%), realized +2.43 at $1, wallet 27.01 (+1 open), equity 27.6
- Fair window since 21:55: v11 live 41/31 +24.3@$10 | Predict.fun v10 14/17 -30.5 | Polymarket v10 16/24 -75.7. Tokyo 2/4 in the last half hour and 3/7 over the last hour: the 04:00 hour is the worst of the night for it (gave back 4.16 from the +6.59 high at 03:47). Still the only positive run in the window. Fills: last at the quote, mean delay 220 ms, 6 of 73 retried (8%), zero failures, unexplained 0.0, nothing unredeemed.
- Container VM rebooted ~04:42-04:50; all seven paper processes relaunched 04:52 on the same DBs (second outage tonight; the first at 03:38 was a proxy-port change). Twins lose another ~2 candles of comparability.
- Twins (~44 graded each): A 26/44 +30.5 | B guard 19/39 -33.6 | C thr 1.0 23/42 +12.3 | D auto 25/48 -21.2. Everyone lost in the 04:00 hour (A -23, C -23, B -23, D -27); ranking A > C > D > B unchanged. pcmp A-vs-runner: 44 matches, same side 38/44, mean |dp| 0.062.
- Stake policy check: 73 fills, hit 57% >= 54%, slippage fine, but the step to $2 needs >= 100 fills - not yet.

### 05:24 UTC - v11 LIVE Tokyo, 7.5 h: 78 orders, 78 filled, 0 failed; 43/34 (56%), realized +0.72 at $1, wallet 25.30 (+1 open), equity 26.0
- Fair window since 21:55: v11 live 43/34 +7.2@$10 | Predict.fun v10 14/18 -40.5 | Polymarket v10 16/24 -75.7. Tokyo 2/3 in the last half hour, 4/10 since the 03:47 high (+6.59 -> +0.72); the 04:00-05:20 stretch is the night's drawdown the user expected. Fills: last at the quote, mean delay 225 ms, 7 of 78 retried (9%), zero failures, unexplained 0.0, nothing unredeemed. No settings change: no stop-loss by instruction, EV dial has no supporting number (C twin still behind A).
- Container VM reclaimed again before this wake (second time in 33 min); all seven paper processes relaunched 05:24 on the same DBs. Cause and fix in NOTES_v11 05:24 (idle reclaim; background keepalive started). Twins missed ~30 of the last 60 minutes.
- Twins (no new fires since 04:52; grading only): A 27/45 +40.6 | B guard 20/40 -23.6 | C thr 1.0 24/43 +21.1 | D auto 25/49 -31.2. pcmp unchanged: 44 matches, same side 38/44, mean |dp| 0.062.

### 05:55 UTC - v11 LIVE Tokyo, 8.0 h: 85 orders, 85 filled, 0 failed; 46/38 (55%), realized -0.31 at $1, wallet 25.27 (1 open), equity 26.3
- Fair window since 21:55: v11 live 46/38 -3.1@$10 | Predict.fun v10 14/18 -40.5 | Polymarket v10 16/24 -75.7 (1 open). Tokyo 3/4 in the last half hour; 7/14 since the 03:47 high of +6.59, now 31c under water on the night. Wallet 25.27 vs 25.58 at launch. The two v10 paper runs did not fire at all 05:00-05:55 (dead tape) while v11 kept firing early cheap entries and lost 4 of 7 - the 04:00-06:00 lull is where v11's early-fire profile bleeds.
- Execution: 85/85 filled, mean delay 216 ms, 8 of 85 retried (9%). Worst fill of the run at 05:55: quoted 0.45, filled 0.49 (+4c, one attempt, inside the 9% band for that price). A mid-flight snapshot briefly showed failed=1 / fill_price None; it cleared to 0 once confirmed - not a failure. Unexplained 0.0, nothing unredeemed.
- Twins (~49 graded): A 29/49 +37.5 | B guard 23/44 -5.4 | C thr 1.0 26/47 +16.7 | D auto 26/53 -54.3. B recovered +18 this half hour (3/4) while A lost (2/4); D lost -23 (1/4, auto mode fired 4 in the lull). Ranking A > C > B > D. pcmp A-vs-runner: 48 matches, same side 39/48, mean |dp| 0.069 (lv, imb20, move_bps).
- Stake policy: 85 fills, 55% hit (>= 54%), slippage mean about +0.4c. The $2 step needs 100 fills AND the hit rate to still be >= 54% at that point; at the current slide it may not be.

### 06:27 UTC - v11 LIVE Tokyo, 8.5 h: 89 orders, 89 filled, 0 failed; 49/39 (56%), realized +1.23 at $1, wallet 25.82 (+1 open), equity 27.1
- Fair window since 21:55: v11 live 49/39 +12.3@$10 | Predict.fun v10 17/18 -18.3 | Polymarket v10 18/24 -60.0. Tokyo 3/1 in the last half hour, back above water (+1.23 from -0.31). Both v10 runs went 5/0 in the 06:00 wake-up hour. Fills: last +2c, mean delay 208 ms, 7 of 89 retried (8%), zero failures, unexplained 0.0, nothing unredeemed.
- Twins (~53 graded): A 32/53 +53.6 | B guard 27/48 +24.0 | C thr 1.0 29/51 +37.5 | D auto 29/57 -42.6. All up this half hour except D; B is 4/4 over the last hour (+29) and back positive. Ranking A > C > B > D. pcmp A-vs-runner: 53 matches, same side 44/53, mean |dp| 0.069 (lv, imb20, move_bps).
- Stake policy: 89 fills, hit 56%, mean slippage about +0.4c; the $2 step is checked at 100 fills (about 1 h away at this rate).

### 06:59 UTC - v11 LIVE Tokyo, 9.1 h: 94 orders, 94 filled, 0 failed; 50/43 (54%), realized -1.54 at $1, wallet 23.70 (+1 open), equity 24.3
- Fair window since 21:55: v11 live 50/43 -15.4@$10 | Predict.fun v10 18/18 -8.2 | Polymarket v10 20/26 -47.6. Tokyo 1/4 in the last half hour (+1.23 -> -1.54); over the night it has now dropped behind the Predict.fun v10 paper run on the same candles for the first time, still ahead of Polymarket v10. Net since launch: -1.88 on the wallet (25.58 -> 23.70, one $1 position open). Since the 03:47 high: 12/24.
- Execution: 94/94 filled, mean delay 201 ms, 7 retried (7%), last fill +3c, unexplained 0.65 = the open position (clears at settlement). No failures.
- STAKE STEP at 100 fills (next ~30 min): the authorized rule is hit >= 54% and slippage <= 2c -> fixed $2. Hit rate is exactly 54% and falling, and realized PnL is negative on the night; stepping stake up while the run is losing is not "doing better" in the user's words, so the step will NOT be taken unless realized PnL is positive at the 100-fill check. Report either way.
- Twins (~58 graded): A 33/58 +25.8 | B guard 27/50 +4.0 | C thr 1.0 30/56 +10.8 | D auto 30/62 -69.3. All four lost this half hour (A -28, B -20, C -27, D -27): the 06:30-07:00 tape was against every v11 setting while both v10 runs won (Predict 1/0, Poly 2/2). Ranking A > C > B > D. pcmp A-vs-runner: 58 matches, same side 49/58, mean |dp| 0.068.

### 07:31 UTC - v11 LIVE Tokyo, 9.6 h: 100 orders, 100 filled, 0 failed; 55/44 (56%), realized +0.78 at $1, wallet 24.09 (2 open), equity 26.7
- Fair window since 21:55: v11 live 55/44 +7.8@$10 | Predict.fun v10 19/19 -13.4 | Polymarket v10 21/27 -42.4. Tokyo 5/1 in the last half hour (-1.54 -> +0.78), back ahead of both v10 paper runs on the same candles.
- 100-FILL STAKE CHECK (numbers from /api/orders?kind=EF, all 100 fills): hit 55/99 = 56% (rule >= 54%: pass); mean fill-vs-quote +0.55c, 67 at or better than quote, 17 worse than 2c, worst +5c (rule <= 2c mean: pass); realized +0.78 (positive: pass). BUT split in halves: first 50 fills +3.40, last 50 fills 26/50 (52%) and -2.62. The edge has not held into the morning session. DECISION: NOT stepping to $2 yet. Stepping stake into a losing second half is not "doing better"; re-check every 30 min and step to $2 when the last 50 fills are >= 54% with positive realized PnL over them. User can override.
- Execution: mean delay 194 ms, 7 of 100 retried (7%), last fill +4c, unexplained -1.27 = two open positions in flight (clears at settlement), nothing unredeemed.
- Twins (~64 graded): A 38/64 +48.3 | B guard 32/56 +26.5 | C thr 1.0 34/61 +29.5 | D auto 35/68 -46.0. All four won this half hour (A +23, B +23, C +19, D +23). Ranking A > C > B > D. pcmp A-vs-runner: 64 matches, same side 54/64, mean |dp| 0.066.

### 08:05 UTC - v11 LIVE Tokyo, 10.2 h: 105 orders, 105 filled, 0 failed; 58/47 (55%), realized +0.26 at $1, wallet 26.49, no open
- Fair window since 21:55: v11 live 58/47 +2.6@$10 | Predict.fun v10 19/20 -23.4 | Polymarket v10 21/27 -42.4 (2 open). Tokyo 3/3 in the last half hour (peaked +1.63 at 07:37, now +0.26). Still the only run above zero on the window, by a hair.
- Stake check (every 30 min): all 105 fills 55%, mean slip +0.55c; LAST 50 fills 25/50 and -4.66 -> stake stays $1 (rule: last 50 >= 54% with positive PnL).
- Execution: mean delay 189 ms, 7 of 105 retried (6.7%), last fill at the quote, zero failures. Capital truth "unexplained 0.65" with NO open position and nothing unredeemed - first time it shows with nothing in flight; if it does not clear by 08:37 it is a ledger discrepancy to root-cause (65c = one just-settled winner's payout not yet reflected in the wallet read is the likely benign cause).
- Twins (~70 graded): A 41/70 +46.8 | B guard 33/60 +9.8 | C thr 1.0 36/66 +17.3 | D auto 37/73 -56.6. Quiet half hour (A 3/6 -2, B 1/4 -17, C 2/5 -12, D 2/5 -11). Ranking A > C > B > D. pcmp A-vs-runner: 70 matches, same side 59/70, mean |dp| 0.066.

## 08:30 UTC - TOKYO UPDATED to build 11.1-perp-agg-fix (user pulled + restarted); settings re-armed 08:31
- Raw-input phase closed: 21:55 09-09 -> 08:30 09-10, 108 orders / 108 filled / 0 failed, 59/48 (55%), realized +0.26 at $1, mean fill +0.55c, worst +5c, mean delay 188 ms. Same window as the fixed-input twin A (since 23:45): Tokyo raw 48/41 real -2.01 (-20.1@$10) vs twin A 42/72 +47.2@$10 paper - the reason for the update.
- Re-armed from here and verified: master ON, EF ACTIVE, MAIN/REVERSAL manually off, stake fixed $1 (max 20), pnl mode, thr 0.75, trend guard 0 (off), no daily limits. Ledger continuity: same DB, W/L and realized carry on; the 11.1 phase is measured from 08:30 for the fair comparison (twin A vs Tokyo on identical inputs from now on).
- Open item carried over: capital truth "unexplained +0.65" (wallet 65c above the ledger, in the user's favour) - root-cause at the next check-in.

### 08:40 UTC - v11 LIVE Tokyo on 11.1 for 10 min: no order yet on the new build; raw phase closed at 110 fills, 61/49 (55%), +0.69 real, wallet 26.92
- Fair window since 21:55: v11 live 61/49 +6.9@$10 | Predict.fun v10 20/21 -26.1 | Polymarket v10 22/30 -60.6. The last two raw-phase fills (08:20, 08:25 UTC) both won.
- Stake check: last 50 fills 25/50, -4.69 -> stake stays $1.
- Ledger +0.65 root-cause (once): all 110 fills are graded; stakes 109.45 out, pnl +0.69 in, so the ledger expects 26.27 and the wallet reads 26.92. The gap has been exactly +0.65 since 08:05 and does not move with settlements, so it is not an open position or an unredeemed payout. The remaining candidate is one of the 7 retried orders whose first attempt executed (partially) at the venue while the ledger logged it as failed - extra shares that paid out. It is in the user's favour and static; treated as a known constant, re-reported only if it changes. Note: the /api/orders "utc" column is BST (UTC+1), not UTC; ts_ms is the truth.
- Twins (~76 graded): A 44/76 +43.5 | B guard 37/65 +35.6 | C thr 1.0 41/71 +60.3 | D auto 40/78 -45.2. C ahead of A again (+17) with the same hit rate (58%); B closed to within 8 of A. pcmp A-vs-runner: 76 matches, same side 64/76, mean |dp| 0.067.
- Routine housekeeping: the 08:37 check-in fired late (08:38) and the prompt's phase boundary constant was wrong (08:20 instead of 08:30); corrected to ts_ms >= 1789029000000.

# LIVE TEST LEDGER (every candidate runs as a paper twin beside the baseline; outcomes revised here at check-ins)
Rule (user, 23:45 UTC 09-09): nothing goes into notes as a finding unless it is run and measured over time; entries are rewritten from outcomes, not kept as ideas.
| id | start (UTC) | variant | hypothesis | verdict so far |
|---|---|---|---|---|
| A | 09-09 23:45 | v11.1 baseline: thr 0.75, guard off, perp-print aggregation fixed (port 8794) | control; its p should now match the runner's (pcmp) | 08:40: 44/76 +43.5 (76 fires); pcmp |dp| 0.067, same side 64/76 -> input fix confirmed |
| B | 09-09 23:50 | A + slow-trend guard 9 candles / 20 bps (port 8795) | fewer against-lean losses; realised-fire retro +459 vs +296, v11 replay -111 -> undecided | 08:40: 37/65 +35.6 (65 fires) - behind A by 8, hit rate 57% vs 58% |
| C | 09-09 23:50 | A + EV scale 1.0 (port 8796) | v10-like frequency; fewer early cheap fires, higher hit rate, lower PnL per retro | 08:40: 41/71 +60.3 (71 fires) - ahead of A by 17, same hit rate 58%; lead has flipped 3 times - undecided |
| D | 09-09 23:50 | A + auto mode (accuracy lane in low vol) (port 8797) | earns in calm/chop hours where pnl mode bleeds | 08:40: 40/78 -45.2 (78 fires) - behind A by 89, hit rate 51% - heading to FAIL |
| Tokyo | 09-09 21:55 | v11 live, $1: raw-input build until 08:30 09-10, then 11.1-perp-agg-fix | execution quality + live edge; from 08:30 the live test of the input fix | raw phase final: 108 fills 0 failed, 59/48 (55%), +0.26 real; 11.1 phase starts 08:30 (measure vs twin A from here) |
Decision rule: a variant replaces the baseline setting only when, over the same candles, it is ahead on PnL at $10 AND not behind on hit rate after >= 100 graded fires, and the sign holds on both halves of its own run.
