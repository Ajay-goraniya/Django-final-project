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
