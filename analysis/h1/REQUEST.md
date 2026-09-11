# REQUEST from V to H1 (11:21 UTC 09-10)

Read your 11:30 results - excellent, and the two retractions are exactly how this should work. Merged into NOTES_v12 (11:21 entry). Now on the branch for you:
- `learner/live_backup/twin_b_guard.sqlite3.gz`, `twin_c_thr1.sqlite3.gz`, `twin_d_auto.sqlite3.gz` (the variant twins; same schema as build11 = twin A; D retired at 10:50 as FAIL).
- `learner/live_backup/tokyo_orders.json` - Tokyo's real order record (EF, REVERSAL, MAIN lanes; order ids/hashes stripped). EF rows with filled=true are the 140 live fills; MAIN/REVERSAL rows are shadow (forbidden) except REVERSAL rows after ts_ms 1789035600000 which are live-armed. This file is refreshed by V at check-ins from now on.
- The channel: you are right, SendMessage fails both ways; V sends to you by a routine bound to your session (that is how the 11:14 message arrived), you answer by files under analysis/h1/. V pulls at every check-in.

## Task 3 (highest value): the rv60 gate on the v11 path
Your rv60 >= 0.3 result is on poly_pnl (the v10 runner). Tokyo and the twins are the v11 path, which fires at ~20 s not ~65 s. Test the same gate on the v11 fires: `build11` ef_predictions and the three twin DBs carry the full feature dict in features JSON (key `ef_v11_f`; V lists the volatility-like keys in NOTES_v12 11:21 - if none is rv60 itself, use the closest realised-vol proxy and say which). Same table as your Task 2(b): gate, kept, hit, PnL@$10, removed record, h1/h2, for A, B, C and for Tokyo's live EF fills (tokyo_orders.json has no features; match Tokyo fills to twin A fires by candle_id within 8 s to borrow the feature). If it holds on the v11 path with both halves positive, V ships it as a dial (v11 setting, default off) and runs it as variant E; if it does not, say so.

## Task 4: paired A/B/C adjudication at 100 graded
Your standing offer #1. Per-candle pairing of A vs B and A vs C (same candle_id): candles where both fired same side / opposite / only one fired; PnL@$10 on each subset; both halves. The verdict rule is "ahead on PnL AND not behind on hit rate at >= 100 graded, sign holding on both halves" - tell V whether B and C pass it on the paired view, not just the leaderboard.

## Task 5: trend-guard reconciliation (your offer #2)
Live B (guard 9c/20bps) vs the 27 h v11-path replay that said the guard hurts (-111). Re-run `learner/`'s retro_trend.py / oos.py logic on the backups if you can; otherwise explain the disagreement from the twin DBs (which fires B skipped relative to A, and how they did).

Deliver as `analysis/h1/2026-09-10_<hhmm>_task3_4_5.md`. Sample sizes on everything. Do not touch Tokyo or the DBs.


## Update 11:23 UTC from V - Task 3 already answered, and it is NEGATIVE
V ran the rv60 gate on the v11 path (ef_v11_f.rv60, PnL@$10): twin A base 60/51 -17.4 -> rv60>=0.3 keeps 24/24 -25.2 and removes 36/27 +7.8; twin C removes 29/21 +38.9; twin B keeps +11.1 / removes -8.1 (halves +15.0 / -3.9); Tokyo's 108 matched real fills show no separation (keep -4.08 / remove -2.07). The v10-runner result reverses on the v11 path. Task 3 is now: explain the disagreement - is the runner's rv60 the same quantity and scale as ef_v11_f.rv60 (compare distributions on the same candles)? does the effect depend on fire second (v10 ~65 s vs v11 ~20 s)? is there ANY vol gate that helps the v11 path on both halves? Tasks 4 and 5 unchanged.

## Task 6 (added 12:25 UTC 09-10): weekday-to-weekend decay, real data only
The user reports that many of their earlier models lose more as the week moves toward the weekend (Thu -> Sun).
Test it on the REAL historical set you used for Task 2 (v10 runner replay, the same graded fires):
- Hit rate and PnL@$10 by UTC day of week, for the baseline fires and for the EV-scale-1.0 setting if you can reproduce it.
- Same split for the Polymarket signal side (does the signal itself degrade, or only the fills/quotes?).
- Report n per bucket; a bucket under 60 graded fires is "insufficient", not a finding.
- If the effect is real, say which days are negative on both halves of the sample, and propose the cheapest guard (e.g. EF off on those days) with its retro PnL.
Live context: Tokyo EF and REVERSAL were paused at 12:20 UTC at the capital floor (equity 16.94, realised -8.52); EV scale 1.0 applied 12:18. Write results to analysis/h1/<date>_task6_dow.md and push; V merges at the next check-in.

## Task 7 (added 12:35 UTC 09-10, from the user, LONG-RUNNING): the intra-candle reversal "binary tree"
Why: EF fires in the first minute of the 5-min candle on the first reversal. It cannot see a second or third reversal
(up -> down -> up -> down -> close up) at minute 4 or 1 minute before close. Those multi-reversal candles are where the
fires die. The user wants a "candle brain": given the path so far inside the candle, the probability that the close
direction flips again before settlement. If that is accurate, it gates EF (do not fire / fire later / fire the other way).
This is not a one-shot task: gather data, build, test, iterate, keep going as data accumulates.

Data (REAL only, no synthetic, no resampling tricks):
- Historical BTCUSDT 1-second klines / aggTrades from Binance public data (data.binance.vision, monthly/daily zips) or
  Bybit equivalents, as many weeks as you can pull; the perp is what the engine watches. Store under scratch, not git.
- Live per-fire feature dicts: learner/live_backup/tokyo_orders.json (EF/REVERSAL/MAIN rows, ts_ms, quoted/fill, actual,
  correct) and the paper twins learner/live_backup/*.sqlite3.gz (ef_predictions: candle_id, features JSON with
  ef_v11_f = full feature dict incl. rv60, range_bps, lv, lv_x_sec, _ask_up/_ask_dn, actual, correct).
- The 5-min candle is settled on the open-to-close sign (Predict.fun BTC Up/Down 5-min, candle_id = open ms).

Build (the tree):
- For each historical candle, encode the path as the sequence of sign(price - open) sampled at fixed offsets
  (every 15 s or 30 s; also the "event" encoding: each crossing of the open). Node = the prefix at time t; leaf value =
  P(close > open | prefix) and P(at least one more crossing before close | prefix).
- Report, at t = 60 s (EF fire time) and t = 190 s (REVERSAL fire time): how well the prefix predicts the close, and how
  well it predicts "another reversal follows". Add features the engine already has (rv60, range_bps, lv, distance from
  open in bps, seconds since last crossing, number of crossings so far) and test whether a small model (logistic or a
  shallow tree, walk-forward only, never fit on the test half) beats the raw prefix table.
- Then the only thing that matters: replay the gate over the REAL EF fires (twins + Tokyo). Which fires would it block,
  which would it keep, PnL@$10 and hit rate with and without, on both halves of the sample and by UTC day/8-h block.
  A gate ships only if it is ahead on PnL and not behind on hit rate at >= 100 kept fires, sign holding on both halves.

Deliver: analysis/h1/<date>_task7_candle_tree.md (+ code under analysis/h1/), updated every time you have a new result.
State clearly what is a finding vs insufficient data. V merges at every check-in and can apply an engine-side gate on
Tokyo once you and V agree it holds. Tasks 3-6 stay open; Task 7 is the priority after Task 6.

### Task 7 correction (12:47 UTC, from the user): NO fixed time gate
Reversals happen at any second. The 60 s / 190 s offsets above were only the typical fire times of the lanes
(Tokyo real fires: EF 101/145 within the first 30 s, the rest spread to 240 s; REVERSAL fires 60-281 s, median 188 s).
So: evaluate the tree CONTINUOUSLY - at every second (or at every crossing of the open plus every 5 s), for every
t in 0..300: P(at least one more crossing before close | path up to t) and P(close > open | path up to t).
The gate is then read at the ACTUAL fire second of each real fire, whatever it was, and the replay over real fires
uses that value. Also report the time profile: at which t the tree becomes reliable (e.g. AUC by t), since a gate
that only works late in the candle is useless for EF, which fires early. Do not build anything keyed to a fixed offset.

## Task 8 (added 15:55 UTC 09-10): does the path add anything CONDITIONAL on the engine's own features?
Same fires as Task 7 (v10-runner 182 matched; add the v11 twins and Tokyo's fills once 09-10 klines exist).
For each fire the engine stored its feature dict (twin DBs: ef_predictions.features.ef_v11_f - imb5/imb20, ofi15/ofi60,
ret5/ret30/ret60, rv60, range_bps, lv, lv_x_sec, mv_x_sec, move_bps, basis_bps, _ask_up/_ask_dn ...; tokyo_orders.json
has fewer fields). Fit, walk-forward / out-of-sample, both halves:
  (a) engine features only -> P(correct) and P(flip before close);
  (b) engine features + path features (side, distance from open, crossings, seconds since last crossing, range so far).
Report AUC and log-loss for (a) vs (b), n per fit, and the same PnL-per-unit test as the stake modifier for (b) - (a).
If (b) does not beat (a) out of sample on both halves, say so and Task 7 is closed as descriptive; the effort then goes
to price/execution (ask deciles for EF: the 14:56 request), which is where every positive finding today has been.

## Task 9 (added 19:22 UTC 09-10, PRIORITY): MAIN lane - is there a price at which it pays?
MAIN is 72-74% right on its shadow record but buys at ~0.75 and loses (break-even ask at 74% with the 2% fee = 0.725).
Data: Tokyo /api/orders?kind=MAIN rows are in learner/live_backup/tokyo_orders.json (status F "manually OFF" with
quoted_price, candle_id, direction; grade them with the candles table in build11.sqlite3.gz or your klines); the b10
snapshots (learner/live_backup/predict_pnl.sqlite3.gz etc.) carry the older MAIN record. Full sweep of a MAIN max-entry
cap (0.50..0.80 by 0.05): kept n, hit, PnL at $1, both halves; plus by fire second. Answer: the cap value (if any) at
which MAIN is positive on both halves with >= 100 kept, or "no such price".

## Task 10: regime scaling premise (for AUTOPILOT_11.4.md section E)
On the 252-day klines: does scaling the EV threshold by realised range (last 12 candles vs trailing 24-h median) change
early-direction accuracy conditional on the ask proxy (|distance|)? I.e. at the same |distance| band, are low-range
regimes more or less accurate than high-range ones, both halves. Then on the fire data: PnL per fire by regime bucket.
Read learner/AUTOPILOT_11.4.md first; review sections C and D thresholds against the fire record and push comments.

## Task 11 (added 19:40 UTC 09-10, from the user, LONG-RUNNING, above Tasks 9/10): the SIGNAL itself
Today's gains were price/execution. The direction call is still 53-55% at ~0.5 asks at t=20 s and that is the ceiling of
the current forecaster. The user wants accuracy + PnL + adjustable frequency from the signal, and it must learn on its own.
Three lines of work, all REAL data, walk-forward, ship rule applies (paired both halves >= 100, full sweep, premise):
1. CONFIDENCE SCORE from the engine's own features (your Task 8 side finding: engine features beat flat staking +33%
   per unit out of sample). Build it as a model that outputs P(win) per fire from the stored feature dict, train on the
   twins' fires (learner/live_backup/twin_*.sqlite3.gz, ef_predictions.features.ef_v11_f + ask), walk-forward by time.
   Then: (a) FREQUENCY DIAL = fire only when P(win) is in the top X% (X = 100, 75, 50, 33): per-fire PnL, total PnL,
   hit rate, fires/hour, both halves - this is the adjustable-frequency knob the user asked for, if accuracy rises as X
   falls; (b) SIZING = stake proportional to P(win) - ask (edge), normalised to the same capital, vs flat.
2. RETRAIN THE FORECASTER on the 252-day 1-s kline set with the features that carried signal today (signed distance
   from open, crossings, seconds since last crossing, range so far, plus the v10 feature set where you can reconstruct
   it), target = close direction, read at t=20/40/60 s; report AUC/accuracy vs the current model's raw calls on the same
   candles (the twins' fires give you the current model's output to compare). If it beats it out of sample on both
   halves, that is v12's model.
3. SECOND, LATER EF ENTRY: at t=60-190 s accuracy is 65-80% (your Task 7 base rates). Test a second fire per candle when
   the model is confident AND the ask for that side is still <= 0.60 (the REVERSAL-style entry, but for EF's own side):
   per-fire PnL both halves on the recorded ask paths (venues.sqlite3.gz in learner/live_backup has the per-second
   Predict.fun asks per candle).
Deliver as analysis/h1/<date>_task11_*.md as results land; V verifies on the twins and puts winners into v12 as automatic
rules (nothing manual from here: see AUTOPILOT_11.4.md).

## Standing note (19:48 UTC 09-10): the user now talks to H1, not V
The user is low on usage and will put questions and instructions to H1 directly. H1: relay anything that changes the
plan or the live state to V through your routine message (as you do for results) and record the user's words in
analysis/h1/USER_ASKS.md (date, ask, what was done). V keeps the 30-min live check-ins, the ledger and the deploys; H1
answers the user from the ledger and the files, and asks V for any live number it does not have.

## Task 12 (standing, from the user): the binary candle tree stays a research line
The user's proposed architecture - a tree over the candle's intra-candle path - is NOT closed. What is settled: the
prefix TABLE has no information early (side only, no distance) and the on/off gate, stake modifier and conditional
value on the engine's features all failed. What stays open and must be researched, with results as they land:
  a. a real learned tree (gradient-boosted or shallow tree ensemble) on path features + engine features, walk-forward,
     as the direction model at t=20/40/60 (compare with the logistic and with the current forecaster: Task 11.2);
  b. the tree as the TIMING model for the later EF entry (Task 11.3) and for REVERSAL, where its AUC is 0.86;
  c. the tree as a "do not fire yet / fire now" state machine evaluated every second through the candle, scored on PnL
     through the recorded ask paths (venues.sqlite3.gz), not on accuracy;
  d. the base rates (P(another crossing) by t) as a live dashboard number so the user sees the candle brain working.
Report each part under the ship rule; if a part fails, say so and move to the next; never drop the line entirely.

## Task 13 (added 20:40 UTC 09-10, from the user, standing): "rain or sun" - when does each finding work, and can the engine tell in advance?
The user's rule: a finding must work every day; if it does not, identify WHEN it works and switch it on only then
(car in the rain, bike in the sun - we have both, we need to recognise the weather).
For EVERY finding that has passed or is close (EV scale 1.0; EF ask floor 0.48; REVERSAL cap 0.60; the t=120 second
entry J; REVERSAL itself; later the retrained model), on the real fire data (twins, Tokyo fills, v10 runner) and where
possible on the 252-day klines:
  1. PnL per fire and hit rate by UTC day, by 8-h block, by weekday/weekend, and by regime bucket defined IN ADVANCE from
     observable state at the fire second: trailing 12-candle realised range (quartiles from the 252-day set), crossings
     of the open in the last 6 candles, Polymarket book width/one-sidedness at fire time, time since the last state-X
     trigger. Both halves, n per cell. No regime that is defined after looking at the outcomes.
  2. For each finding: does it hold in ALL buckets (then it is unconditional), or only in some? If only some, the switch
     must be a regime the engine can read live (all of the above are), and the premise must hold on the 252-day set
     (accuracy by |distance| band within the regime, monotone) before it becomes a rule.
  3. Deliver a table "finding x regime -> ON/OFF" with the evidence, and a one-line rule per finding that the engine can
     evaluate at the fire second. V implements the switches in the autopilot as automatic rules (AUTOPILOT_11.4.md
     section E) and they ship in v12 only with both-halves support.
Guard against the trap of the day: a regime switch is itself a threshold; define the buckets first (quartiles, day
type), test them all, and report the full grid, not the best cell.

## Task 14 (V, 09-10 23:40 UTC): where and why the two venues resolve differently
Grounded in a measured fact: Polymarket's resolution and the engine's candles.actual (Binance close >= open, which Tokyo's real financial_result confirms is what Predict.fun pays on) disagree on ~10% of candles (66/637). Those are the candles where EF/REVERSAL lose "sure things" late. Grade everything on engine actual.
1. Characterise the disputed candles: |close - open| in bps at Binance close; the Polymarket UP price at 240 s and 290 s; whether Polymarket's own settle price differs (its oracle) - is the disagreement concentrated in near-zero candles (|close-open| < X bps)? Full distribution, buckets defined first, both halves of the 54.7 h.
2. For EF and REVERSAL fires on twins A/C and Tokyo's fills (learner/live_backup/tokyo_orders.json has actual, correct, pnl, seconds_into_candle): how much of the loss comes from candles that finish within Y bps of open? Report the loss share by |close-open| bucket. If a large share of losses sits in near-zero candles, that is a fact about the venue, not a gate to add - report it, do not propose a threshold.
3. If the data allows: does the Predict.fun ask late in the candle (t >= 240) already price the near-zero risk (ask vs realised win rate in the |close-open| < X bucket)? That tells whether REVERSAL's late fills are fairly priced.
Deliverable: analysis/h1/task14_venue_disagreement.md with the grids; STATE.md updated. No rule proposals; description only.

## Task 15 (V, 09-10 23:55 UTC): unblock the klines via REST, finish 11.2, and test the distance premise on the big set
1. data.binance.vision is still 404 for 2026-09-10. Use the REST endpoint instead: GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime=<ms>&endTime=<ms>&limit=1000 (also /api/v3/aggTrades?symbol=BTCUSDT&startTime=&endTime=&limit=1000 for the flow features, paging by fromId). Same data as the daily files. Fill the gap and run Task 11.2 as specified.
2. Premise test on the 252-day kline set for Task 14's fire-time fact: at decision second S (15, 20, 30, 45, 60, 90, 120), bucket |price(S) - open| in bps (<1, 1-2.5, 2.5-5, 5-10, 10-25, 25+) and report P(close on the same side as price(S)) per cell, with both halves and per-regime (Task 13 buckets). Tokyo's 250 fills say <1 bps at fire = 51% (coin flip) and 1-2.5 bps = 61%; find out whether that is the market or one regime. Full grid, no chosen cell. Also the same grid for the LATE seconds (237, 270, 290) since the Predict.fun ask overprices the favourite in the <1 bps bucket at t>=237 (Task 14 part 3): is P(same side) in that bucket really ~50% on 72k candles?
3. Feed the result into 11.2's evaluation: does the retrained model's fire set avoid the sub-1-bps coin flips on its own (share of fires with |move| < 1 bps, and their accuracy), or does it inherit the current model's 46%?
Deliverable: analysis/h1/task15_distance_premise.md + 11.2 results; STATE.md updated. Engine grading only. Description and model evaluation only; no gates.

## Task 16 (V, 09-11 01:05 UTC): market-prior EF replay - the baseline 11.2 must beat
Motivation: Task 15 part 3 (82% of fires under 2.5 bps; 0.20x base rate in the 5-10 band). The twins log only FIRED candidates, so this needs your data: venues.sqlite3 (Predict.fun asks + sizes every 5 s, 661+ candles) joined to the kline path (|price(S)-open| and the side price is on at S). Engine grading only (candles.actual from the snapshots; never the venues outcome table).
Rule under test (fully specified, nothing hand-tuned): at each decision second S in {15, 20, 30, 45, 60, 90, 120}: side = the side price is on at S; p = the Task 15 part 2 bucket prior P(same side | S, |price(S)-open| bucket) estimated on the kline set EXCLUDING the evaluation candles (walk-forward: prior from days before the venue window); ask = recorded raw Predict.fun ask for that side at S (skip if missing or size < $10 notional); fire iff p*(1/ask)*(1-0.02) - 1 >= 0.25 (the engine's own EV threshold at thr_scale 1.0); one fire per candle at the first S that clears. Report: fires, hit, PnL per $1 per fire, total, both halves, fire-distance profile (share per bucket), per Task 13 regime quartile if n allows.
Comparators on the SAME candle set: (a) the current EF fire set (twin C ef_predictions / ef_candidates, which carry ef_v11_p, ef_v11_ask, ef_v11_sec, ef_v11_f.move_bps for every fire) - PnL per $1 at the recorded ask; (b) the rule above with p replaced by the CURRENT model's p where a fire exists - i.e. does the prior alone beat the model at the model's own fire count? Match fire counts by tightening/loosening the EV margin symmetrically and report the full curve (margin 0.15, 0.20, 0.25, 0.30, 0.40), never one cell. Also the naive null: fire on every candle at S=20 on the current side at the recorded ask.
Then the question that matters for 11.2: at equal fire count, does the retrained model's fire set earn more per fire than the market prior? If the prior alone is as good as or better than the model, the v12 direction model is the prior plus whatever the model adds on top of it, and the engine's calibration should be conditioned on the distance bucket (a learned mapping - not a gate). Run verify.py on any positive claim. Deliverable analysis/h1/task16_market_prior_ef.md; STATE.md updated.

## V ack (09-11 01:40 UTC): Task 16 read and noted - agreed, insufficient both ways; the naive-null loss is the useful fact.
Carry it into 11.2: evaluate the retrained model as PnL at the recorded ask on the venue window (engine grading), never accuracy; report the fire-distance profile of its fire set next to the part-3 baseline; and the two open checks stay queued (venue favourite vs Binance leader at t=237; the 2.5-5 bps cell as fills accumulate). Nothing new assigned.

## Task 17 (V, 09-11 02:05 UTC): freeze 11.2 and run it forward
1. Freeze the model NOW: training cutoff = the venue window start you used (nothing after it, ever, for this artifact). Export under analysis/h1/models/: joblib of the HistGradientBoostingClassifier, a small predict module exposing feats_at(path, S, trail12) and trailing12 exactly as trained, SECS, the EV margin (0.15), FEE, and your sklearn version in a README. Keep the artifact under a few MB.
2. Forward test, daily: for each new UTC day, take the new candles from my pushed snapshots (learner/live_backup/venues.sqlite3.gz for 5-s asks now; learner/live_backup/book1s.sqlite3.gz once it appears - 1 Hz price + both asks/sizes/ages, table b1(ts_ms, epoch, sec, price, open, ask_up, size_up, age_up, ask_dn, size_dn, age_dn, book_candle)) and the engine candles from build11/twin_c_thr1 snapshots, run the FROZEN model with the same EV arithmetic, and append a cumulative forward ledger to analysis/h1/task17_forward_11_2.md: fires, hit, per-fire, total, both halves of the forward set only, fire-distance profile. Verdict at >= 100 forward fires with the sign on both halves and verify.py True. Report only when the verdict changes or at 100 fires.
3. While it accumulates: the Task 13 rain-or-sun grid for the 11.2 fire set on the 648 candles (all cells, marked insufficient where n < 60), and a per-hour-of-day fire and PnL profile (weekend behaviour matters to the user; Sat-Sun is the live test window).
No deploy of anything until the verdict. Engine grading only.

## Task 18 (V, 09-11 02:25 UTC): does 11.2 transfer to Polymarket? (user is weighing the platform)
Context: the v10 Polymarket paper run (351 fires, 56 h) is +0.148 per $1 fire after Polymarket's real crypto taker fee (fee = shares x 0.07 x p x (1-p), makers free; NOTES_v12 02:20 entry), graded on Polymarket's own resolution - about 3x Predict.fun live per fire at 150 fires/day. The user asks whether to add/switch venue.
1. Replay the FROZEN 11.2 model (Task 17 artifact) on the same 648+ venue-window candles but paying the recorded POLYMARKET ask (venues.sqlite3 q.poly_up / q.poly_dn, 5-s samples; book1s does not carry Polymarket yet) with the 7% formula, and - this is the one place it is correct - grade on the venues `outcome` table, because Polymarket pays on its own Chainlink 60-s TWAP resolution, not on Binance close. Report the same table as Task 16/11.2: n, hit, per-fire, total, halves, EV-margin curve 0.10-0.40, fire-distance profile; and the same replay graded on engine actual for contrast (to show how much of any gap is the resolution source).
2. Same replay for the current EF fire set (twin C ef_candidates, direction + second) at Polymarket asks, both gradings, so the three (v10 runner, current EF, 11.2) sit on one table at Polymarket prices.
3. Note the structural difference for the ledger: on Polymarket the signal IS the venue's own price (p_venue/lv features), so the recorded ask can be gone when the order lands; state the +5c/+10c haircut rows explicitly.
verify.py on any positive claim; engine grading is NOT the settling source here - say which grading each number uses in every table. Deliverable analysis/h1/task18_polymarket_transfer.md. After Task 17's freeze/export, before the regime grid.

## Task 19 (V, 09-11 02:30 UTC, standing): Polymarket migration research file
User (02:28): "we might move to Polymarket at least for a test run ... keep gathering important infos, improvements and changes in different notes, use H1 for this." Research only; nothing built before v12.
Keep analysis/h1/POLYMARKET.md current (V's summary is learner/NOTES_polymarket.md). Gather, with sources and dates: (1) CLOB API - auth flow (wallet-derived API creds), order types, tick/min size, rate limits, websocket channels, how fills and settlement/redemption surface, what the executor must do that the Predict.fun one does not; (2) fees on the 5-min BTC markets right now (docs say takers 7% x p x (1-p) per share, makers free; gamma shows takerBaseFee 1000 - resolve the discrepancy); (3) resolution mechanics: Chainlink 60-s TWAP - how close a 1-s-kline TWAP gets to it (agreement rate vs the outcome table on your candles), so research grading can be honest; (4) historical data endpoints (prices-history, trades) and how far back they go - can we build a Polymarket-ask history for replay beyond our collector? (5) geo/eligibility policy as published (no legal advice - just what the docs and ToS say); (6) the v10 Polymarket paper run by hour-of-day and by weekday from the runner DB snapshot (learner/live_backup/poly_pnl.sqlite3.gz) - the user's weekend concern. Update the file as things are learned; no message unless something changes the plan.

## V ack (09-11 02:58 UTC): Task 18 read - clear result, recorded (ledger row N, NOTES_polymarket). No change to Task 17/19 order.
