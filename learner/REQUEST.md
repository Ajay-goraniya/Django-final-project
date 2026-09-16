# REQUEST.md — V → H1 (single channel; H1 answers in analysis/h1/ and STATE.md)

## Task R-1 (09-14 00:2x UTC) — THE POLYMARKET REGIME GRID. Measurement only. Buckets are fixed below; do not add or move one.

**Why:** user, 09-14 00:0x: *"make it live when Market is good."* That is a regime switch, and the standing
rule is binding: **buckets FIRST, whole grid, never the best cell.** The engine will later self-verdict
each cell from live outcomes (AUTOPILOT 11.4 §E2); nothing arms on this grid directly. Scope is
**Polymarket only** (Tokyo/Predict.fun are out as of 09-13 22:3x).

**Data (all real, all on the branch or in V's scratchpad):**
1. Polymarket v12 paper lane — `learner/live_backup/v12_poly_weekend.sqlite3.gz` (snapshot 09-13 21:50;
   `trades` 317 graded + `decisions` 7,280 rows with `p, ask, ev, fire` per candle). V will refresh the
   snapshot on request.
2. Polymarket v10 paper — `/tmp/v10_long4.sqlite3` on V's box, 776 graded (`trades`: `ts_ms, pnl, stake,
   ask, ev, sec, rv60, feat`). V will snapshot it to `live_backup/` on request.
3. The A/B twins (`scratchpad/twins/{ctrl,cand}/twin.sqlite3`, launched 09-13 23:37) — as they grow.
4. Kline set for the bucket features — your 73,679-candle REST-mirror set.

**Grade everything on `candles.actual` (Binance close ≥ open).** Paper's own `win` column is
oracle-flattered (32 of 156 disagree, REMAKE_PLAN §2a); do not use it.

**Buckets — Task 13's, fixed in advance, every cell reported:**
- UTC 8-h block: 00–08 / 08–16 / 16–24
- weekday / weekend
- trailing-range quartile, cuts from the 252-day set: 31.4 / 48.9 / 76.4 bps
- flips of the open in the last 6 candles: 0–1 / 2–3 / 4+
- book width at the fire: tight / wide (your existing cut)

**Per cell:** n graded, PnL per $1, hit rate, both halves (chronological), `verify.py` verdict. **Under 60
= "insufficient", reported anyway.** No cell is read that fails halves. No recommendation to gate — the
deliverable is the grid and which cells are positive both halves at >= 60, full stop.

**Also, because it is the one regime effect already on the record:** the weekend tape is thinner
(10.9 vs 17.7 bps) and Task 13's only negative cell was the busiest quartile at n=24. Report that cell
first with today's n.

Write the result to `analysis/h1/task_r1_polymarket_regime_grid.md`, update `STATE.md`, commit, push.
V reads it before anything is designed. If any dataset cannot be used honestly (clock skew, missing
features at the fire second), say which and how many rows rather than reconstructing.


## Task R-2 (09-14 00:5x UTC) — R-1 accepted in full, my grading instruction retracted. The same grid on the v10 set.

**§1 of R-1 is accepted and I have retracted the instruction in `REMAKE_PLAN.md` §2a.** You were right
not to follow it: Polymarket pays on its own oracle, the lane's `actual` is that oracle 303/303, and
grading on `candles.actual` would have inflated every cell by ~90%. My error, recorded as mine.

**§6's ask is done:** `learner/live_backup/v10_poly_long4.sqlite3.gz` (commit `24d28a7`) is the v10
Polymarket paper runner's journal from V's box (`btc_model_v10_runner.py --port 8788 --db
/tmp/v10_long4.sqlite3 --mode pnl`, pid 901), taken with sqlite3's online backup API at 00:4x UTC.
Tables: `trades` (778 rows, 777 graded; cols `candle_epoch, ts_ms, mode, side, p, ask, ev, sec, rv60,
stake, actual, win, pnl, graded_ms`), `decisions` (16,805; has `feat`), `meta`.

**Do first, before any cell:** the same provenance table as R-1 §1 for this file — `trades.actual` vs
`venues.outcome` vs `candles.actual`, n and disagreements. I do **not** know which oracle the v10 runner
graded on; do not assume. If it is Binance, re-grade on `venues.outcome` before anything else and say so.

**Then the R-1 grid, unchanged buckets, on the 777**, Polymarket's oracle, ≥60 or "insufficient",
both halves, `verify.py`, whole grid, never the best cell. Two things R-1 could not do that this set can:
(a) a **second, separate window for the weekend cell** — report the two weekend windows side by side,
not pooled; (b) a readable n on **Q4 busiest** and on **weekday**. Zero-slippage caveat stands and goes
at the top again.

Output: `analysis/h1/task_r2_v10_polymarket_regime_grid.md`. Measurement only; no design.


## Standing rule (user, 09-14 01:2x) - short messages

Cross-session messages <= ~15 lines: the verdict, the numbers, the file path. The full write-up lives in
`analysis/h1/`, never in the message. Applies to R-2 and everything after.

## Task R-3 (09-14 13:4x UTC) — PAY-UP GRID on the real rejects. User: "what if we use our predict slippage? filled 100%... even 45/90$ is good"

Question: for every live REJECTED submission (archive era 37 + reset era ~34+; AWS has the rows with `pre_submit_quote`,
signed cap, ts; ask AWS by Routine `session_0128m2knBcqiTyAVoh7h994A` for a CSV of reject rows, no secrets), what
did the ask do in the next 0.35 s / 1 s / 2 s (`live_backup/polybook.sqlite3.gz`, `book1s`/`poly1s` 1-Hz logs, whichever
covers the timestamps — state which), and what is the per-$1 outcome (Polymarket oracle, `venues.outcome`) had we
paid ask+1, +2, +3, +5 ticks. WHOLE GRID, every pad, fills-that-would-have-happened vs not, n per cell, both halves,
`verify.py`. Also the same grid on the FILLED rows (what paying more would have cost on trades we already got).
Report the grid, no recommendation. Under 60 per cell = insufficient. Output `analysis/h1/task_r3_payup_grid.md`.
<= 15 lines in the message; the doc carries the rest.

**R-3 addendum (user, 14:1x):** report explicitly, first table: win rate and per-$1 of the REJECTED set vs the FILLED
set (as decided, at paper price) — if the rejected ones lose more, paying up loses money; that is the decision. Then
the pad grid. User's intent if the answer is good: raise the pad on the FIRST order so it fills without a retry.

## Task R-4 (09-14 21:5x) — DYNAMIC STAKING: is there anything to size on? Calibration grid, whole grid.

User: *"what if the staking is dynamic? less capital in losing trades, more in winning ones... it needs to be very
sure."* Sizing can only work if something known AT FIRE TIME predicts the win. Candidates, each its own grid:
model `p` (buckets 0.50-0.55/0.55-0.60/0.60-0.65/0.65+ and the mirror for DOWN), EV = p/ask−1 (quartiles of the
data, state the cuts), `sec` into candle (0-60/60-120/120-180/180-240), and ask price (quartiles). Sets: v10 777
(`live_backup/v10_poly_long4.sqlite3.gz`), v12 lane (`v12_poly_weekend`/`v12_poly_lane`), live fills (H1's
`r3_submissions.csv` + outcomes). Polymarket oracle. Per cell: n, win%, per-$1, both halves, `verify.py`; <60 =
insufficient. Then the one number that decides: per-$1 of a stake proportional to the bucket's edge vs flat stake,
on the SAME trades, walk-forward (bucket edges estimated on the first half, applied to the second). If the buckets
do not separate win rate, say so - that closes it. Output `analysis/h1/task_r4_stake_calibration.md`; <=15 lines back.

## R-5 (V, 09-15 02:2x) - dynamic staking as a trained brain, standing task. Replies ≤6 lines; the work goes in files.
R-4 said "nothing to size on" from fixed buckets. The user's direction is the same as for EF: not a gate, a trained
model. Build: walk-forward model of PnL per $1 at fire time (inputs known at fire: p, EV, ask, sec, regime features,
lane), trained on the first half, sized on the second, Polymarket lanes graded on venues.outcome, paper + live pooled
but reported separately. Sizing rule = fractional Kelly on the model's edge, capped at the user's max. Ship only if
verify.py passes on the second half and the sized PnL beats fixed-3 on the same trades (paired()).
Standing: re-run at every +100 graded live fires on Zurich (journal polymarket_v12_live_zurich_2.sqlite3 snapshots in
learner/live_backup when V pushes them), append one line per run to analysis/h1/r5_ledger.md. Report only a change of
verdict. Until it passes: stake stays fixed 3.0.

## R-6 (V, 09-15 02:3x) - calibrated p inside the EV rule, walk-forward. Not a gate: the brain's p corrected by its own record.
R-5 run 2: p overconfident in every bin. Test: fit calibration (Platt and isotonic, report both) on the first half of
graded fires (paper and live separately, Polymarket lanes on venues.outcome), apply to the second half INSIDE the
existing EV rule (same threshold, same cost model), and report on the second half: fires kept / dropped / added vs the
raw p, PnL per $1 and total, paired() on the discordant candles, halves(), permutation() of the calibrated p, and the
same for a rolling refit every 200 fires. Whole grid, no best cell. Ship condition: sized PnL on the same candles beats
raw in both halves with verify.py passing. Reply ≤6 lines, file on the branch.

## R-7 (V, 09-15 19:1x) - futures positioning as a "when is the model cold" signal. Rain-or-sun rules, whole grid.
Not in the model today: Binance USDT-perp 5-min open-interest change, global long/short account ratio, top-trader
long/short position ratio, taker buy/sell volume ratio (fapi /futures/data/* endpoints, period=5m; if fapi is
geo-blocked from the container say so and use data-api.binance.vision or ask AWS to fetch a csv). Join to every graded
Polymarket fire (paper sets + live journals incl. learner/live_backup/zurich_*.sqlite3.gz) at fire time, causal only
(the last completed 5-min bar). Buckets FIXED before looking: terciles of each series over the sample. Report per
bucket: n, win%, per-$1, both halves; verify.py on any cell that looks alive. Also the trivial null: last-3-results
of the model itself (hot/cold streak) as a bucket. Reply ≤6 lines, file on the branch.

## R-8 (V, 09-15 19:1x) - taker buy/sell ratio as a FEATURE: parity, retrain walk-forward, ship test. Not a gate.
R-7 found sum_taker_long_short_vol_ratio (previous completed 5-min bar) orders accuracy 58.5/56.6/50.7 by tercile.
The daily archive lags a day, so live cannot read it; the engine already consumes the perp trade stream (taker side
per trade). (a) PARITY: rebuild the same ratio from our own logged perp trades (whatever tape we have: engine
diagnostics, book1s/poly1s, or the Binance daily aggTrades/trades zips for the same days) = taker buy vol / taker sell
vol over each completed 5-min bar; report correlation and tercile agreement with the archive series on 09-08..09-14.
If our tape cannot reproduce it, say so - then it is not a live feature. (b) RETRAIN: v10's own trainer (learner/
train*.py, same features + this one, same lgbm/logit), walk-forward by day over the available labelled days (train
on days < d, test on d), frozen model as the control on the same days; report per-day and pooled: logloss, hit%,
PnL per $1 under the SAME EV rule, paired() on the discordant fires, halves(), permutation(); whole grid, no best
cell. (c) Ship condition: beats frozen on pooled PnL per $1 AND in both halves AND verify.py passes; then V builds
12.10 (feature computed in-engine from the perp deque, model file swap, §7, twins first). Reply ≤6 lines, file on
the branch.

## R-9 (V, 09-15 19:2x) - STANDING: the cold-regime brain. User: "keep working on it, don't stop after a few tests fail."
Goal unchanged: a trained brain that knows when its move is wrong (no gates, no hand thresholds). Program, in order,
each attempt through verify.py, whole grid, paired() on discordant candles, both halves, ledger analysis/h1/r9_ledger.md:
1. STACKED BRAIN: second-stage model on top of frozen v10: inputs p, EV, ask, sec, rv60, taker ratio (R-7), last-3/
   last-10 outcomes (causal), hour-of-day, regime features; target = fire wins; walk-forward by day; output replaces p
   in the SAME EV rule. Try logit and lightgbm (pip install lightgbm). Compare to frozen on the same candles.
2. MORE DATA: extend labelled paper days backward as far as the logged tapes + venues.outcome allow; rebuild R-7/R-8
   on the larger set; report how the taker ordering behaves outside the 09-08..09-14 week.
3. RE-RUN R-8 at every +2 days of live fills (Zurich snapshots in learner/live_backup) and at every new week of
   labelled data. One ledger line per run; message V only on a verdict change.
4. Anything else you find that predicts the model's own accuracy: log it in the ledger with n, halves, permutation.
Stake and gates untouched throughout. Kelly stays out (two user confirmations rule).

## R-10 (V, 09-15 20:3x) - the model's own ACCURACY mode, replayed. User wants a safer/less dangerous mode.
btc_model_v10.decide(mode="accuracy"): fire iff p_side >= conf_floor AND EV >= ev_floor; model_v10.json has fixed
0.85/0.02 and regime_floors (low 0.80/0.02, mid 0.75/0.05, high 0.80/0.08 by rv60 edges). Replay BOTH variants over
the same tick streams as R-6 (paper sets + live journals, Polymarket oracle), same cost model: fires/day, hit%, per-$1,
total, positive days / days, halves, permutation, paired() vs the pnl rule on shared candles, verify.py. Also the
grid of conf_floor {0.70,0.75,0.80,0.85,0.90} x ev_floor {0.02,0.05,0.08} - whole grid, no best cell - so the user
sees the frequency/accuracy trade-off. Reply ≤6 lines, file on the branch.

## R-11 (09-15 23:0x) - trend x volatility regime grid. Today 13-22 UTC: 36 res 13W -0.131/$1 during a -2.8% BTC selloff
with rv60 med 0.75 (vs +0.717/$1 on 29 res before 13:00). rv60 alone is not a losing bucket (every bucket positive in
poly_pnl 1005 / v10_long4 777). Define FIRST, then grid ALL cells on the largest Polymarket-oracle sample plus today's
Zurich rows: ret60 tercile (down/flat/up) x rv60 (<0.35 / 0.35-0.75 / >0.75) x side (UP/DOWN). Per cell n, hit, pnl/$1,
halves, >=60 or "insufficient". Full grid, never the best cell. Question: is "selling into a selloff at high vol" a
cell that loses every day (rain or sun) or is today variance. verify.py gates. Report ≤8 lines in analysis/h1/, one
verdict line to NOTES.

## R-12 (09-15 23:1x, USER ORDER) - retrain the brain on ALL known BTC regimes. Priority over R-9 and R-11.
User: "train it on a bigger scale... trained in almost all the regimes known... train it and test it, no excuse or no
cheating." v10 today = 8 days (08-29..09-06), frozen; today's selloff is out of sample.
Data: data.binance.vision (monthly zips; api.binance.com geo-blocked, data-api.binance.vision works - fetch_rest_klines.py):
spot BTCUSDT aggTrades (2017-08+), futures BTCUSDT aggTrades + bookTicker (2019-09+ / 2020+), spot 1s klines where
aggTrades are too big. State the data footprint before pulling (disk is a fixed per-session allowance).
Regimes - DEFINE FIRST, then grid ALL, never the best cell: era (2020-21 bull, 2022 crash incl. LUNA/FTX, 2023 chop,
2024 ETF/halving, 2025, 2026), trend (ret60 tercile), vol (rv60 <0.35/0.35-0.75/>0.75), hour-of-day, weekend.
Model: same feature set + interface as btc_model_v10 (model json drop-in, FeatureState unchanged) so it can run as a
twin without engine changes; the venue-implied features do not exist historically - train the microstructure part on
the full history, fit the venue combination + isotonic on the logged Polymarket window only, report both stages.
Test (this is the deliverable, not the training): strict walk-forward (train <= T, test > T, no overlap); on the
labelled Polymarket rows graded on venues.outcome, PAIRED vs frozen v10 (discordant only, McNemar), halves, permutation
of predictions, costs, null; plus today's 13-22 UTC Zurich rows. Every regime cell: n, hit, pnl/$1, >=60 or
"insufficient". verify.py verdict() must pass. No in-sample numbers in the report. Retrain on the 8 days with the
new pipeline must reproduce v10 within noise (pipeline check) before the big run.
Deliver: analysis/h1/r12_big_brain.md (<=15 lines + grid file), model json under analysis/h1/, one verdict line to
NOTES. Ships as a PAPER twin first (Mumbai, V arranges); nothing live without the user.
R-12 addendum (V, 22:5x): plan approved. On the 9 unbuildable features: serve them zeroed too (a feature mask in the
json, applied in FeatureState output) so train == serve and there is no skew to measure; the venue stage on the logged
window may use all 30. Report both (masked vs unmasked serve) if cheap, masked is the default.
R-12 addendum 2 (user, 09-15 23:2x): "hoping to run it live sooner." Paper twin: Mumbai first (Task via AWS_TASKS);
ONLY if Mumbai cannot run it, H1 runs the twin inside its own container and keeps checking it. Walk through any
other issue yourself; do not stop. V's session is near its usage limit - H1 self-drives R-12 end to end (data ->
train -> walk-forward -> paired test -> twin -> 4-h ledger), commits every stage to analysis/h1/r12_big_brain.md,
and posts a one-line verdict trigger to V only at: test verdict, twin running, or a blocker V must clear.
R-12 step 2 (V, 23:5x) - user order stands ("if not achievable then make changes but train on all regimes"). Stage 1
shows linear-on-18 + venue = frozen v10. Change the model, keep the data and the test: (a) gradient boosting (lightgbm)
on the 4.75M-row store with explicit regime inputs (rv60, ret60, range_bps, hour, weekend, era) so regimes are learned,
not gated; walk-forward BY YEAR (train <= Y-1, test Y) reporting OOS logloss/AUC per year vs the stage-1 logistic -
if GBM does not beat logistic on Binance direction across years, say so: regimes carry no extra 5-min direction
info and that closes the question honestly. (b) if it does beat: venue stage as before, then the paired test vs
frozen v10 on the Polymarket rows, verify.py, and only then a twin. (c) Also report the per-regime OOS grid of the
stage-1 model itself (era x vol x trend, n/hit/logloss) - that is the "all regimes" deliverable the user asked for,
whatever ships. ≤15 lines in r12_big_brain.md, one verdict poke to V.

## R-14 (09-16 00:1x) - the edge is execution. R-13 accepted (V confirmed on the 70 live fills: 63 disagree with the venue
side, 48% right, still +12.9 at median ask 0.43). R-12 step 2: deliver only the per-regime OOS grid (cheap), skip the
GBM unless already running. Then R-14, on the Zurich live journals + polybook/book1s logs, real data only:
(1) For every fill and every FAK reject since 09-15 02:06: ask paid vs venue mid at signal, vs mid 1 s / 5 s / 60 s
later, vs outcome. Where does the cheap ask come from (book lag vs Binance move, one-sided book, size pulled)?
(2) Reject anatomy: 105/108 FAK killed for size - grid order size vs displayed size at signal, fill probability and
pnl/$1 per bucket; what size would have filled and at what pnl.
(3) Fire-second grid (15-240 s) x ask bucket: fill rate, pnl/$1, halves. Full grid, never the best cell.
(4) From (1)-(3) propose at most two concrete execution changes (e.g. size <= displayed, limit-with-TTL vs FAK, a
different fire window) with their gridded pnl/$1 vs current, verify.py, paired where same candles. No gates on the
score; these are execution rules. <=15 lines in analysis/h1/task_r14_execution_edge.md, one verdict poke to V.

## R-15 (09-16 00:5x, USER ORDER) - SIGNAL ONLY. User: "the issue is the signal that fails to predict correctly, not the
execution." Execution threads (R-14, geography, dashboard) are parked. Goal: information the venue price does not have,
trained at scale on the 9-year store, tested walk-forward, then paired vs frozen v10 on the live window. Two sources,
both computable live from data the engine already has or can poll:
(a) higher-timeframe state from the same 1s klines: 5m/15m/1h/4h returns, vol ratios (rv60 / rv15m / rv1h), distance
from 1h/4h VWAP and range, same-direction candle streak length, time since last reversal. The refuted "trend guard"
was an on/off rule; this is learned features, different method.
(b) taker buy/sell ratio and open-interest change from data.binance.vision futures metrics (5-min bars, R-7 found
58.5/56.6/50.7 by tercile 7/7 days on one week); available for years - add to the store at the prev-completed bar.
Method: GBM walk-forward BY YEAR, OOS logloss/AUC per year: stage-1 (18) vs +(a) vs +(b) vs +(a)+(b). Then venue stage
on the logged window, paired vs frozen v10 (discordant, McNemar), halves, permutation of predictions, verify.py.
Specific question the user sees: runs of 7-9 same-side losses in one trend; report whether the (a) features cut the
loss-run frequency OOS (max run length per day, pnl in trend windows), full grid. Ship as PAPER twin if it passes.
≤15 lines in analysis/h1/task_r15_signal.md, one verdict poke to V. Do not stop; if a source is missing, substitute
and say so.

## R-16 (09-16 01:4x, from the user's review; V verified the lead) - SETTLEMENT REFERENCE. On 76 live fills: 12 lost
where Binance direction said win (venue settled the other way), 2 the reverse; afternoon 9 vs 0; disagreement 18% vs
~10% base. Do, real data only: (1) get the venue's price-to-beat per candle (Polymarket market metadata / description
at open, or the Chainlink BTC/USD reference the market resolves on - polybook/venues logs may carry it; if not, say
what is needed and V will add it to the logger). (2) On the labelled lanes (poly_pnl 1005, v10_long4 777, v12 lane 568,
Zurich live) grid: sign(move from Binance open) vs sign(price - price_to_beat) agree/disagree x fills/rejects x
outcome; is the loss concentration reproducible (halves, per day)? (3) If yes: feature = distance and movement relative
to the settlement reference (not a substitution into existing weights), retrain chronologically with the venue stage,
paired vs frozen v10, verify.py; report loss-run change. ≤15 lines analysis/h1/task_r16_settlement_ref.md, verdict poke.
R-16 addendum (reviewer via user, 01:4x; reviewer reproduced the 76-fill table exactly: Binance 45/76 vs venue 35/76):
(1) entry-time only - the reference distance must be computable before the order, no future information; (2) training
labels verified against venue outcomes; (3) chronological evaluation on real executable quotes reporting PnL, drawdown,
frequency. Also flagged from r12 reports: 17,449 synthetic-book vs 4,117 real-book training rows, real-book coverage
concentrated on two days - confirm and state what that does to the venue-stage evidence. Mumbai Task 98 starts
recording the reference stream now (Chainlink BTC/USD + price-to-beat, source and arrival timestamps).

## R-17 (09-16 02:3x) - retrain on EXECUTABLE QUOTES only. From your own addendum: v10 was fitted with p_venue 81%
trade prints and 5/8 days with no book at all, yet p_venue carries its largest coefficient. We now have many days of
logged REAL book (v12 lanes, poly_pnl/book_age_ms, the Zurich journals, polybook 1 s snapshots). Do: (1) count the
usable executable-quote rows per day across every logged source - state n before anything else; if under ~60 graded
fires per day-bucket say "insufficient" and stop there. (2) Rebuild the training table from book rows only (p_venue
from the actual UP/DOWN touch at the fire second, quote age recorded), same 30 features, labels on venues.outcome
(and the TWAP rule where the venue is Predict.fun). (3) Retrain the same recipe chronologically, walk-forward by day;
paired vs frozen v10 on held-out days (discordant, McNemar), halves, permutation, costs, null; PnL/drawdown/frequency
on executable quotes only. (4) Report the p_venue coefficient and calibration of the retrained arm vs v10. Ship = paper
twin on Mumbai with the json (engine 12.11.1 loads any feature list). <=15 lines analysis/h1/task_r17_book_only.md.

## R-18 (09-16 03:0x) - THE GOAL PROGRAM: stop paying the ask. Owner V, priority 1, everything else pauses.
User's goal restated: accuracy AND PnL (PnL first) AND adaptive frequency AND no evening where almost every trade loses.
What tonight established (do not re-derive): the direction forecast equals the venue price (R-13, six negatives:
R-6/8/9/12/16/17); loss runs are at chance (R-15); our money comes from buying BELOW fair, and R-14 showed the orders
that would have won are exactly the ones the venue KILLS - fills pay mid+0.5c and win 51%, the 26 killed orders priced
under the ask would have won 65% (+0.170/$1). We have only ever sent FAK taker orders at the touch. The untested
structural lever is to REST the order under fair instead of chasing it.
(1) FILL SIMULATOR on the logged book tape (polybook 1 s snapshots + book1s + the live journals). For each candle and
each fire second, simulate a limit buy resting at cap = ask - k ticks (k = 0..5) with a TTL (cancel at T-30 s, T-60 s,
end of candle): filled iff the book's ask trades at/through cap while the order rests, size = displayed at that price.
Grade on venues.outcome. Report the FULL grid k x TTL x fire-second: fill rate, hit%, pnl/$1, n, halves, per day.
Never the best cell. Compare against the actual FAK arm on the same candles (paired, McNemar).
(2) ADVERSE SELECTION is the thing that kills this idea: a resting order fills when the market moves against it.
Measure it directly - for each simulated fill, the venue outcome vs the outcome of the same candle when we did NOT
fill. If pnl/$1 at k>=1 is not positive after that, say so and the idea dies there.
(3) FILL MODEL, only if (1) survives: P(fill | cap, displayed size, sec, rv60, spread) fitted on real orders (190+
live and growing, plus every paper arm). Expected value per attempt = p_win x payoff x P(fill) - cost. Frequency then
adapts by itself: quiet thin candles price themselves out, and no threshold is hand-set. verify.py on every cell.
(4) Deliverable: analysis/h1/task_r18_resting.md (<=15 lines + the grid file), and if it survives, a PAPER lane on
Mumbai that posts resting orders beside the live FAK engine so the two are comparable on the same candles.
Constraints unchanged: real data only, >=60 graded per cell or "insufficient", halves, paired, permutation, costs,
null. Nothing live without the user. This is not a gate on the score - it is how the order is placed.

## R-18a (09-16 03:1x, USER'S IDEA, run it FIRST - it is cheaper than the resting grid and uses data we already have)
User: "maybe adjusting one tick, two ticks may help? or maybe EV mode?" They are right that the tick is the live knob.
FACT from the running journal (V, 400 live orders): the cap is ask_at_decide + pad, pad=1 tick today. Outcomes by
cap-minus-ask: +1 -> 46 FILLED / 32 REJECTED, +2 -> 4 FILLED / 2 REJECTED, and 21 rejects sit at cap <= ask (the ask
moved up between decide and submit, so our cap was already stale). So both directions are live: pay one more tick and
more of those 53 rejects become fills, at a worse price.
Do, on real rows (Zurich journals + every paper lane + the book logs), full grid, never the best cell:
(1) For pad in {-2,-1,0,+1,+2,+3,+4}: counterfactual fill (would the ask at submit have been <= cap, and was there
size), realized price, pnl/$1 graded on venues.outcome, n per cell, halves, per day. Paired against the actual +1 arm
on the same candles (McNemar on discordant).
(2) Split by what moved: rejects where the ask ROSE after decide vs rejects where size vanished at our price. A pad
only helps the first kind; report the split so the ceiling of this lever is known.
(3) Interaction with fire-second and rv60 (the pad that pays may differ at 30 s vs 240 s, in fast vs quiet markets) -
report the grid, and if a single pad is not best everywhere, that is the adaptive-frequency answer the user wants:
pad chosen by a fitted rule on (sec, rv60, spread, displayed size), not a hand-set number.
(4) EV MODE: do not re-run R-10 (accuracy mode 86.4% hit but +0.001/$1, regime floors -0.040/$1 worst, pnl rule
+0.131 best). Instead answer the one open question: with the best pad from (1), does the EV threshold sweep move at
all? Full sweep, both arms, PnL not accuracy.
Deliverable analysis/h1/task_r18a_pad_grid.md <=12 lines + grid file. verify.py. Then the resting simulator (R-18).
