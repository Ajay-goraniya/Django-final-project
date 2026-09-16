# Brief for session H1 from V (written 11:12 UTC 2026-09-10; V = session_01SmMRZqqMru5UdaeAoJarkr, peer name django-final-project-b4)

The user asked V and H1 to communicate. V cannot open a channel to a cloud session from its container (SendMessage finds no reachable peer), but H1 can message V: SendMessage to "V" (or "django-final-project-b4") reaches this session, and V replies to the `from` address. Until then this file is the channel; V refreshes it when something changes.

## Live state 11:10 UTC 09-10
- Tokyo (AWS ap-northeast-1, systemd `v11`, build 11.1-perp-agg-fix since 08:30 UTC) trades Predict.fun BTC 5-min up/down with real money; Polymarket websocket is the signal. Lanes: EF active, REVERSAL active since 10:21 UTC (no live fire yet), MAIN off. Stake $1 on the user's equity ladder ($1 below equity 30, $2 at 30, $3 at 40, +1 per +10, cap 20). V's capital floor: EF pauses if equity < 18.
- Since launch 21:55 UTC 09-09: 137 orders / 137 filled / 0 failed, mean fill +0.41c vs quote, worst +5c, 177 ms; 73/63 (54%), realized -6.20, wallet 16.95, equity 20.1. Peak +6.59 at 03:47; 09:45-11:00 lost 2/13 for every v11 setting and for both v10 paper runs.
- Container (paper, master OFF): Predict.fun v10 engine 8789, Polymarket v10 runner 8788, venue collector, v11 twins A baseline 8794 / B trend guard 8795 / C EV scale 1.0 8796. D (auto mode) retired 10:50 as FAIL (54/102 -33.2 vs A +3.4).
- Findings: `learner/NOTES_v11.md` (v10 runs) and `learner/NOTES_v12.md` (v11 + live; LIVE TEST LEDGER at the end). DB snapshots of every container run: `learner/live_backup/*.sqlite3.gz`, refreshed at every 30-min check-in (build11 = twin A; predict_pnl = v10 engine, whose `trades` table holds MAIN/REVERSAL/EF shadow lanes; poly_pnl = runner; venues = collector). Secrets stay in V's container.

## Task 1 - independent check of the REVERSAL finding
From `predict_pnl.sqlite3.gz` table `trades` (kind, direction, actual, quoted_price, seconds_into_candle, ts_ms, correct, pnl): V found the shadow REVERSAL lane = 110 fires over 41 h, 69% directional, mean quote 0.55, median fire 192 s, +43.6 at $1 with a 2% fee (win pays shares*0.98 - 1, loss -1), positive on both halves; MAIN = 345 fires, 72% right, mean quote 0.75, -20.8. Confirm or refute with your own numbers. Add: REVERSAL PnL by UTC hour; by quote bucket (<0.45, 0.45-0.60, >0.60); by seconds_into_candle bucket; and whether REVERSAL fires that oppose an EF fire on the same candle are net positive after counting the EF loss.

## Task 2 - time-of-day / regime gate for EF, both-halves validated
Data: `build11.sqlite3.gz` ef_predictions (ts_ms, price, correct, features JSON with ef_v11_ask; PnL@$10 = 10*(1/(ef_v11_ask*1.02)-1) on wins, -10 on losses); `predict_pnl` trades kind='EF' (41 h); `poly_pnl` trades table.
(a) Per UTC hour: EF hit rate and PnL across the three runs. Are the 04:00-06:00 and 09:45-11:00 losing stretches hour-of-day effects or one-offs?
(b) A realised-volatility gate: skip EF when the last 6 closed 5-min candles' range is below X bps (candles from ef_predictions price/ts or from venues.sqlite3.gz). Give the gate, fires removed, W/L removed, PnL removed, on each half separately.
(c) Same for "skip when the ask at fire time is < 0.40" and "> 0.60".
User's rule: nothing goes into notes unless measured; report only what the data shows, with sample sizes. Send the result to V by SendMessage (tables fine). Do not touch Tokyo, the container processes, or the DBs; V merges your text into the notes.
