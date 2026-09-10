# H1 STATE — single source of truth for the check-in loop
Last updated: 2026-09-10 23:57 UTC. Update this file at the end of every check.

## Standing user rules (binding)
- **No gates.** No on/off gates, stake modifiers, or threshold sweeps on a score already known to be
  weak. The user: *"EF should know when to fire and it cannot be decided by a gate... give it a
  trained brain that knows that move is wrong and it will reverse."* Four such things failed on 09-10.
- **"Don't do unnecessary or unuseful work, go in a right direction not wrong."**
- **"Rain or sun"** (Task 13): a finding must work every day; if not, find WHEN and switch only then.
  A regime switch is itself a threshold — define buckets FIRST, test them all, report the full grid,
  never the best cell.
- The user talks to H1 directly. Answer properly but SHORT ("summarise it, I'm not reading all").
  Log every ask in `USER_ASKS.md`.

## Method (the expensive lessons of 09-10)
Full parameter sweep AND largest available sample before calling anything a finding, including my
own. Non-monotone sweep peaking at the chosen value = fitting to noise; smoothly monotone = real.
**Accuracy is not PnL.** Always test the obvious null against my own result. Real data only. Sample
sizes on every claim; under 60 graded fires in a bucket is "insufficient". Walk-forward only.
**Retract my own claims when data reverses them — five times on 09-10, the most useful thing I did.**
**GRADING (V, 23:15, after my 12a error): never grade a Predict.fun trade with the venues `outcome`
table — that is POLYMARKET's resolution and the two venues disagree on 10.5% of candles. Grade with
`candles.actual` from the engine DBs or Tokyo's `financial_result`.** Check what a label MEANS before
using it. Never touch Tokyo, V's containers or the DBs. Never handle secret values.

## CLOSED — do not resurrect
| item | verdict |
|---|---|
| Task 7 prescriptive half | on/off gate, stake modifier, entry-price interaction all failed |
| Task 8 | path features conditional on engine features — negative in all six configs |
| Task 11.1 confidence score | **OOS AUC 0.4746, below random.** Frequency dial runs backwards. **Retracts my "+33% per unit" claim** (real only for the v10 runner, 0.5644; does not transfer to v11 twins, 0.479/0.539). Never cite it again |
| trend guard | premise refuted on 20,308 candles; reverted on Tokyo 14:25 |
| hour-of-day / weekend decay | refuted on 252 days; my weekend claim withdrawn |
| **Task 12a — ANY direction model over the venue quote table** | **CLOSED, both channels, on correct labels.** Own quote path: flat (−0.02..+0.06), negative at +5c everywhere. Cross-venue spread: my positive claim was a GRADING ARTIFACT, retracted — see below. Do not queue 12b/c on either |

## LIVE CANDIDATE J — the one thing that works
Second EF entry at t≈120 s, **same side as the first fire**, only if that side's ask is still ≤0.60.
- Recorded quotes: **+0.408/fire**, 215 fires, both halves (+44.20/+43.49), cap sweep monotone,
  survives +10c slippage, liquidity median 129.
- **V's replay on Tokyo's REAL fills: +0.153/fire, both halves, 128 fills.** ~2.5× staleness haircut —
  **plan on the live number.**
- **Null rejected:** same candles, same 0.36 ask — EF's side 48%, opposite side 28%; "buy whatever is
  cheap late" LOSES (−0.053 all candles, −0.248 where EF stayed out). **EF's direction is the edge.**
- t=190 does not replicate; t=240 negative.
- V has a forward shadow on the live book since 20:24 (`ef2_shadow.py`), verdict at ≥100 graded.
- Task 13 grid: ON in both halves in 9 of 9 buckets with n≥30 → **ON unconditionally**. One watch
  cell: Q4 busiest trailing range (>76.4 bps) −0.233 on 24 fires — watch, do not switch; arm
  "EF2 off above 76.4 bps" only if still negative at 60+ fires.

## Task 13 results for the other findings (21:20)
- **EF ask floor 0.48 is NOT unconditional.** Skipped group is profitable in **Q4 range (+0.250, n=42,
  both halves)** and **flips 4+ (+0.296, n=56, both halves)**. Recommended: floor ON except when
  trailing 12-candle range > 76.4 bps or flips ≥ 4.
- **REVERSAL cap 0.60: the skipped group MAKES money** — 77% hit, +0.134/fire, both halves, n=108.
  **This reverses my Task 1 claim** that the >0.60 bucket was a loser. Cap is still right as a
  *capital* dial (kept +0.646 vs skipped +0.134 per fire) but costs +14.44 total PnL.
- **REVERSAL lane:** +0.429/fire, n=255, positive everywhere except a flat 08-16 block.
- **Fast tape is the one regime signal that has appeared twice, from opposite directions.**

## Task 13 table COMPLETE (22:25)
- **EV scale 1.0: RECONCILED — it was units.** V's "+59.2" was at $10; my +2.62 at $1 is the same
  quantity. V's own longer-window figure is +3.7 at $1. **Ledger row C corrected to UNDECIDED**, ~30
  decisions, ~+0.02/fire either way. Stays live: no harm, little gain. My flag was worth raising and
  the answer was mundane — check units before alleging a discrepancy next time.
- **Live confirmation of the EF-floor finding:** Tokyo's sub-0.48 fills since 14:25 ran **17 for
  +1.78**, i.e. the group the floor throws away made money on live fills, exactly as the Task 13 grid
  predicted for the current regime. V logged this independently.
- **EF2 (J) shadow on the live book:** 8 graded, 62% hit, +0.074/fire (cap 0.60: 5 graded, 60%,
  +0.105). Far too small to read; verdict at ≥100.

## Task 12a — RETRACTED and closed, 23:30 (my fifth retraction of 09-10)
Ran on `venues.sqlite3`: 640 candles, 54.7 h, walk-forward, 8 decision seconds, both halves.
- **I graded Predict.fun trades with POLYMARKET's outcome.** The `outcome` table is Polymarket's
  resolution; Predict.fun settles on the engine's source (Binance close >= open). **V caught it
  (afcdf4f).** I confirmed it independently: **66 of 627 common candles disagree, 10.5%.** V's
  decisive evidence, which I do not have: Tokyo's `financial_result` on 264 real fills agrees with
  the engine's `actual` on all 29 disputed candles traded.
- **Re-graded on the engine's actual, everything collapses.** Cross-venue spread by second:
  +0.050 / +0.093 / +0.102 / -0.020 / -0.094 / -0.008 / -0.130 (60/90/120/150/180/210/240) against
  +0.27..+0.44 on the bad labels. **Nothing survives a 5c haircut.** The least-dead cell (t=90,
  +0.093, n=219) is noise — **do not chase it**, that is banned threshold-hunting on a weak score.
- **My negative claim is restated too**: "own quote path dead 16/16" used the same bad labels.
  Correctly graded it is FLAT (-0.02..+0.06), negative in both halves at most seconds, negative
  everywhere at +5c. Same practical conclusion, now on correct labels.
- **Net: Task 12a is a negative result end to end. No direction model over the venue quote table
  works, on either channel.** That still closes the avenue, which was the useful part.
- **Structural fact kept (V's):** on ~10% of candles the Polymarket-favoured side at 240 s loses on
  Predict.fun (27 UP->DOWN, 27 DOWN->UP). Caps late-candle accuracy for any Polymarket-led rule at
  ~90% on this venue; part of why late EF/REVERSAL fills lose "sure things".
- Report: `2026-09-10_2310_task12a_direction_model.md` (retraction box at the top, original left
  intact as the record). Repro: `venue_regrade.py` (both gradings side by side).

## Task 14 DONE 23:55 — why the two venues resolve differently (V's task, description only)
641 common candles, 54.7 h, engine grading, buckets fixed in advance (|close-open| bps).
- **66/641 disagree (10.3%), and it is a NEAR-ZERO-CANDLE phenomenon.** Disputed rate 32.9% (<1bps)
  / 21.5% / 13.6% / 0.5% / 2.2% / 0% — monotone, holds in BOTH halves in every row. 94% of all
  disputes sit under 5 bps. Median |close-open| 1.41 bps disputed vs 5.44 overall.
- **Not uncertainty:** on disputed candles Polymarket prices ITS OWN winner at median 0.990 and
  >=0.90 on 94% of them. Two confident answers from two different oracles.
- **Tokyo EF losses concentrate there:** <1bps 39% hit −0.290/fire, 2.5–5 48% hit −0.085. Those are
  the ONLY negative cells; candles inside 5 bps are 50% of fills and **59% of gross losses**. Every
  bucket >=5 bps is profitable.
- **EF accuracy tracks the bucket (43/54/46/60/58 on 458 twin fires); REVERSAL's does not**
  (82/74/77, n=114, 80% overall). Near-zero looks like an EF problem, not a REVERSAL one — but
  REVERSAL's <1bps cell is n=15, too thin, so that is a GAP not a clearance.
- **The late ask is NOT fair in the near-zero bucket** (V's question 3): at t>=237 the favoured side
  costs 0.729 and wins 49.4%, gap **−0.236** on n=77. Fair-to-cheap in every other bucket
  (+0.008/+0.040/+0.056/+0.036/+0.015). Late fills in near-zero candles are systematically overpriced.
- **No rule proposed, per the brief.** An unprofitable bucket is a venue fact, not a gate.
- Limits: one regime, 54.7 h; 25+bps and both REVERSAL tails under the 60-fire bar; Tokyo REVERSAL
  n=18 cannot carry PnL (twin numbers are accuracy only).
- Deliverable: `task14_venue_disagreement.md`. Repro: `task14_disagreement.py`.

## OPEN, in priority order
1. **The 00:00 UTC kline job (below)** — everything else of substance is gated on it.
2. **Task 11.2** — retrain the forecaster on the ENGINE's own candles, walk-forward, versus the
   twins' own calls. (12a is DONE — see above. Gated on the kline job.)
3. **Task 12b/c/d** — ONLY as a timing model for the later entry and REVERSAL. **Not over the
   venue's own quote path** (12a killed that). Base rates as a live dashboard number still stands.
4. **Tasks 9 (MAIN cap) and 10 (regime scaling)** — LAST, both price/threshold studies.
- Task 14 DONE 23:55. Open gap it leaves: REVERSAL's <1bps cell (n=15) — revisit when the twins have
  more REVERSAL fires, since that is the one cell that could change the "EF problem, not REVERSAL"
  reading.
- **Do NOT** start a third-entry or continuous "add while the market disagrees" rule without a steer.

## Pending on the clock
**~00:00 UTC:** data.binance.vision publishes 2026-09-10. Pull it, rebuild `paths.npz`, then:
(a) replay J with **Tokyo's live fills** for the first time on full coverage;
(b) run **Task 11.2** — the retrained direction model — which needs 09-10 coverage to compare against
the twins' own calls on the same candles. Doing 11.2 before this only covers the 09-08/09-09 slice
and would have to be redone, so it waits. Check the 404 first; if not up, wait for the next leg
rather than looping.

## The constraint any new direction model must beat
Measured three ways on 09-10: the path does not beat the ask; path features added to engine features
make prediction worse; engine features alone carry no usable ranking on the v11 path. **A better
model over the same inputs will not work.** New information only. Of the four channels listed here,
**Task 12a has now tested two**: the venue's per-second quote path as a DIRECTION model is dead
(it is what made J work as a TIMING rule, but it does not call direction); cross-venue lead/lag is
the one that works, at ~6 cents. Untested: deeper book state than imb5/imb20, trade-flow aggression.

## Scratch assets
`scratchpad/build/paths.npz` — 252 days of Binance spot 1s klines, 72,576 five-minute candles
(2026-01-01..09-09), plus `feat.npz`. Builders: `analysis/h1/build_paths.py`, `tree.py`, `gates.py`,
`reversal_profile.py`.
