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
