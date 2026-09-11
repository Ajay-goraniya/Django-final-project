# H1 STATE — single source of truth for the check-in loop
Last updated: 2026-09-11 02:47 UTC. Update this file at the end of every check.

## VERIFICATION IS NOW A GATE, NOT A HABIT (user 00:30: "verification is the most important part")
`analysis/h1/verify.py` — a `Finding` runs grading provenance / sample size / both halves /
permutation control / sweep monotonicity / cost sensitivity / beats-the-null, and `verdict()` is
True only if nothing FAILED. **Run it before reporting anything, including to V.**
Self-tested on the two real 09-10 cases: it REJECTS the cross-venue claim I got wrong and ACCEPTS
the distance premise. In that rejection **every other check passes and only `grading()` fires** —
the reason the checks run as a set and grading runs first.
Its `permutation()` permutes the model's PREDICTIONS, never the labels: shuffling labels destroys
the market's calibration too, so longshots "win" at the base rate and it prints a fake profit.

## FIXED 00:22 — the protocol now lives in repo-root `CLAUDE.md` (commit cfa8e77)
Every Claude session in this repo loads it automatically, so the three failures below cannot repeat
by anyone simply not knowing. It carries: push-access dry run BEFORE any analysis, read this file's
CLOSED table first, the working channels, the user's binding rules, the method rules, the venues
grading trap, and the Tokyo/secrets/file-ownership boundaries.
**Messaging V is now rationed** (user: "don't just talk talk talk with V"). The branch is the
channel. V gets a Routine ONLY for a finding/negative result that changes V's next move, a
retraction, a blocker or anything touching live trading, or a direct question in REQUEST.md —
batched into one message. No status pings, ever.
**Task lifecycle:** every REQUEST.md item is marked IN PROGRESS (with time) / DONE (with deliverable
path) / BLOCKED (with what would unblock it). Never silently unworked, never re-run when DONE.

## ROOT CAUSE OF THE STRANDED SESSION — found 00:40, fixed
The user sent the session URL. It was titled **"V -> H1 message channel"**, `origin:
force_run_trigger`, `routine:agent-minted`, **no git sources in its context**. V's poke through
`trig_01PX7ZvtkKWUnZ9SzxGuPzn9` **minted a new session instead of waking H1**, and a minted session
inherits no repo — hence the push denial. It burned 82k tokens on undeliverable work.
**Fixed:** that session is ARCHIVED (nothing lost; its one new claim was already re-derived and
pushed at 00:10). The poke trigger is KEPT — V needs it — but rewritten to open with an identity
test (`git push --dry-run` on the branch). Orphan -> reply once quoting V's content verbatim, then
STOP: no clone, no analysis, no asking the user for access. H1 -> proceed normally.
A future mis-mint now costs one message instead of hours, and V's content is not lost either way.

## OPERATIONAL ISSUES — known failure modes for any session on this task (user, 00:05)
A THIRD session was given the same `H1_BRIEF.md` retro tasks and hit all three of these. The user
relayed its output and said *"be aware of those comman issues."*
1. **`SendMessage` does not work in any direction** — by name, alias or full session ID. The working
   channels are (a) git commits on the branch and (b) one-shot Routines via `create_trigger` with
   `persistent_session_id`. Do not burn turns retrying SendMessage.
2. **A new session may have NO PUSH ACCESS** to `Ajay-goraniya/django-final-project` and will only
   discover it at `git push`. Its work is then stranded. **Check push access BEFORE doing hours of
   analysis**, and if it is missing, hand results to a session that has it (H1 does) rather than
   asking the user to change permissions.
3. **Duplicated work.** That session independently re-derived "no EF gate passes both-halves
   validation" — already closed here AND banned by the user. **Read `analysis/h1/STATE.md` first**;
   the CLOSED table exists exactly to stop this.

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

## Task 15 (V, 23:55) — part 2 DONE 00:05, part 1 UNBLOCKED, part 3 next
- **THE KLINE BLOCKER IS GONE.** `data.binance.vision` never published 2026-09-10 (404 all night).
  `api.binance.com` is **geo-blocked from this container**, but **`data-api.binance.vision` serves
  the same `/api/v3/klines` and is not blocked.** Fetched 09-10 00:00-23:55 = **86,101 rows of 1s
  closes** -> `scratchpad/klines/rest_2026-09-10.json`. Fetcher: `analysis/h1/fetch_rest_klines.py`
  (1000-row pages, retry with backoff). **Use this route whenever the daily zip lags.**
- **Part 2 DONE — the distance premise is REAL, and it is the market, not a regime.**
  P(close on the side price is already on) rises monotonically with |price(S)-open| in EVERY row, at
  every second, in BOTH halves, in ALL FOUR regime quartiles. At S=30: 0.526 / 0.593 / 0.639 / 0.698
  / 0.748 / 0.817 across the buckets. **Tokyo's 33 fills reproduce on 72,576 candles** (<1bps 51% vs
  0.53; 1-2.5 61% vs 0.58-0.63). One of the cleanest regularities in any H1 study.
- **Correction to the brief's premise:** V asked whether the <1bps bucket is really ~50% late. **No —
  0.614 at t=237**, 0.670 at 270, 0.772 at 290, both halves agreeing.
- **I could NOT explain away Task 14's 0.494 and did not pretend to.** My candidate explanation (that
  14 buckets on final |close-open| and 15 on observable |price(S)-open|) was TESTED and is WRONG:
  both conditionings give ~0.60 on the same 72k candles (0.614 vs 0.595). Two live candidates remain:
  (a) Task 14 measured the VENUE's implied favourite, not the Binance price leader — if those diverge
  in near-zero candles that ties straight to 14's two-oracle result; (b) noise, n=77, SE ~5.7pp, so
  0.494 vs 0.595 is ~1.8 SE. **Separable now that 09-10 klines are in** — compare the venue's implied
  favourite against the Binance leader at t=237 on the same candles. QUEUED.
- Deliverable: `task15_distance_premise.md`. Repro: `task15_distance_premise.py`.

## EF vs REVERSAL opposite sides, 00:10 (rescued from the stranded third session)
Its one non-duplicate claim, re-derived by H1 rather than taken on trust: **it replicates, exact
numbers, sign holds on all four sources.** When the two lanes oppose on the same candle the COMBINED
position loses in every source (−0.220 / −0.354 / −0.329 / −0.516 per $1); when they agree it is
strongly positive (+0.641 to +1.521). The engine is trading against itself on ~40% of the candles
where both fire.
- **NOT two independent signals:** REVERSAL fires *because* it thinks the move reverses, so
  "REVERSAL opposes EF" and "EF is wrong" are largely the same event counted twice.
- **NOT a finding yet:** every cell is under 60 (28/22/17/7) and the three twins share candles, so
  they are one twin family plus a thin slice of real fills, not four independent samples.
- **No rule proposed** — a disagreement gate is banned, and unimplementable anyway since REVERSAL
  fires after EF, so at EF's fire second the disagreement does not exist yet.
- Note: `2026-09-11_0010_ef_rev_conflict.md`. Repro: `ef_rev_conflict.py`.

## Task 15 part 1 + part 3 DONE 00:52 (part 2 done 00:05) — Task 15 COMPLETE except 11.2
- **Part 1 DONE.** Kline set extended through 09-10 via the REST mirror: **72,863 candles**
  (`append_day.py` + `fetch_rest_klines.py`). The daily zip never published; blocker permanently
  removed.
- **Part 3 DONE — and the answer is the opposite of the question's premise. The current model does
  NOT avoid the sub-1bps coin flips; it PREFERS them.** 82% of EF fires land under 2.5 bps:
  `<1` 47% of fires vs 41% of candles (**1.15x over**), `1-2.5` 35% vs 27% (**1.27x over**),
  `5-10` 2% vs 10% (**0.20x**, one fifth the base rate) — and 5-10 bps is where part 2 showed
  direction is MOST predictable (~0.70 vs ~0.53). Counting fact, label-independent, holds both
  halves (88% / 75% under 2.5 bps). **There is no avoidance to inherit.**
- **NOT ESTABLISHED, and I am not claiming it:** whether EF has skill inside the flat bucket. First
  pass said +5.0pp over "follow the move" (n=120, both halves). **verify.py failed it on grading
  provenance and the failure was REAL** — see the caveat below. On the SETTLING labels it is
  **+3.3pp with halves +5.0/+1.7**, inside noise at n=120. Needs ~400+ flat-bucket fires.
- **NEW CAVEAT THAT TRAVELS TO MY OTHER WORK: Tokyo's venue-reported `actual` disagrees with my
  Binance-spot close on 2.18% of orders (7/321), and EVERY disagreement is in a candle under ~1 bps**
  (2.5% inside the `<1` EF bucket vs 1.5% outside). My Binance feed is not a perfect proxy for the
  venue's settlement, and the error sits exactly in the flattest bucket. It does NOT overturn part
  2's distance premise (0.53 -> 0.82 across buckets dwarfs 2.5%, ordering untouched) but **the `<1`
  cell is the least trustworthy number in all of my work** and must be read that way.
- **Marked, NOT read (n=40, under the bar):** the `2.5-5` cell has EF at 45.0% vs a 70.0% null,
  −25pp. If real it would mean the engine actively fights genuine moves. **Highest-value cell to
  revisit as fills accumulate.** REVERSAL n=20 throughout: insufficient.
- Deliverable: `task15_part3_fire_profile.md`. Repro: `task15_part3_fire_profile.py`.
- **STILL OPEN from Task 15: 11.2 itself** (train the direction model and compare its fire set to
  the above baseline). Now unblocked — full kline coverage exists.

## Task 16 DONE 01:32 — market-prior EF replay. Prior does NOT beat the model; one big null result.
648 eval candles, prior walk-forward from 72,207 EARLIER candles, engine grading, V's rule verbatim.
- **Answer to V: NO, and nothing is established either way.** Matched fire count: prior @0.20
  n=76 +0.137 vs model-p @0.30 n=79 +0.109 — a 0.028 gap on ~77 fires, noise.
- **verify.py REJECTED the prior rule on SWEEP SHAPE** (0.108/0.137/0.175/0.288/0.104 — peaks
  interior, collapses). Grading/sample/halves/null all PASS. In fairness the cells driving the shape
  (n=28, n=18) are under the bar, so: **insufficient evidence both ways, not refuted.**
- **Current EF fire set on the same candles: n=220, +0.049/fire, halves −0.01/+10.83.** All of its
  profit is in the second half — its own instability, worth V noting.
- **THE SOLID RESULT (n=638, both halves negative): the naive null — fire every candle at S=20 on
  the side price is already on — is RIGHT 59.2% OF THE TIME AND LOSES MONEY (−0.019/fire).** Median
  ask 0.58. **This is the constraint 11.2 must be built against: a model that is merely more often
  right cannot make money; it must be right WHERE THE ASK IS CHEAP relative to the truth.**
- Direction to test, NOT a result: at margin 0.25 the prior puts 18% of fires in the 5-10 bps band at
  +0.93/fire where current EF puts 1% — but that is ~7 fires, unreadable.
- Deliverable: `task16_market_prior_ef.md`. Repro: `task16_market_prior_ef.py`.

## Task 11.2 DONE 02:20 — THE DIRECTION MODEL PASSES EVERY CHECK. Shadow candidate, not a ship.
**First thing in this project to pass all seven `verify.py` checks.** Trained on 505,365 rows from
72,207 candles ALL ending before the venue window (walk-forward by construction); evaluated as PnL
at the recorded ask on 648 venue candles, engine grading.
- **GBM @ EV margin 0.15: n=89, 62.7% hit, +0.266/fire, halves +0.356/+0.177.**
  vs market prior +0.137 · vs current EF +0.049 · vs naive null −0.019. Beats all three.
- **Permutation control p=0.000** (real +0.263 vs permuted mean −0.043, 200 draws). Signal is real.
- **Seed-stable:** 5 seeds give +0.263/+0.246/+0.217/+0.299/+0.308, mean +0.266, **sd 0.034**, all
  positive, n 86-92.
- **Sweep monotone** (+0.266/+0.213/+0.210/+0.146/−0.045) — edge is BROAD AND SHALLOW: best when
  taking many modest disagreements with the venue, decays on rare extreme ones.
- **Real slippage, measured by re-paying the ask (not approximated): +0c +0.242, +3c +0.168,
  +5c +0.124, +10c +0.027** — still positive at 10 cents. At J's measured 2.5x recorded->live ratio,
  expect about **+0.10/fire**.
- **It reaches the informative band:** 5-10 bps = 9% of its fires (current EF: 1%), 10-25 = 6%
  (current EF: ~0%). Exactly the mechanism Task 15 part 3 predicted.
- **Two of my own errors corrected in the writeup:** (a) I first called it a sweep-shape FAIL — that
  was ONE seed; five-seed average is cleanly monotone. (b) I diagnosed miscalibration and TESTED it:
  wrong — the model is already well calibrated (0.285->0.279, 0.713->0.712) and isotonic changed
  little.
- **LIMITS: n=89, 648 candles, ~2.3 days, ONE regime, PAPER.** No rain-or-sun grid possible at this
  size. **Recommendation: forward shadow on the live book like J — verdict at >=100 graded, both
  halves. Do NOT deploy on a 648-candle replay.**
- Deliverable: `task11_2_direction_model.md`. Repro: `task11_2_direction_model.py`.

## Task 14/15 DISCREPANCY RESOLVED 02:00 — it was the window, not the venue
The queued check, run on 648 candles with full kline coverage. Candidate (a) "the venue favourite
diverges from the Binance leader in near-zero candles" vs (b) "noise at n=77".
- **(a) is REAL as a phenomenon but explains NOTHING.** At t=237 the two disagree on 40% of <1bps
  candles (agreement 60%) against 96-100% in every other bucket — the venue stops tracking the tape
  when the candle is flat, and re-converges as it closes (60% -> 79% -> 90% at 237/270/290).
  **BUT they perform IDENTICALLY there: 0.467 vs 0.467, gap +0.000.** Overall gap +0.000 at t=237,
  +0.012 at t=270 — the venue is if anything marginally better.
- **(b) IS the explanation.** On THIS window the <1bps bucket is a coin flip for BOTH measures
  (leader 0.467) against **0.614 on the 72,863-candle set**. Task 14's 49.4% needs no venue-specific
  story and none should go in the ledger.
- **The caveat that matters going forward:** this 648-candle venue window differs from the 252-day
  set by **15 percentage points** in that bucket. Every per-fire number measured on these candles,
  **including Task 11.2's +0.266**, inherits that uncertainty. It is precisely why 11.2 was proposed
  as a forward shadow rather than a ship.
- <1bps cells are n=58-60, right at the bar: "consistent with noise", not a measurement.
- Note: `2026-09-11_0200_venue_favourite_check.md`. Repro: `venue_favourite_check.py`.

## Task 17.1 DONE 02:35 (model FROZEN) · Task 18 DONE 02:45 — 11.2 does NOT transfer to Polymarket
- **17.1: model frozen and exported** to `analysis/h1/models/` (joblib + `ef11_2_predict.py` +
  README, 0.27 MB, sklearn 1.9.0). Artifact reproduces the replay EXACTLY (n=91, +0.263,
  halves +0.352/+0.177). Feature parity asserted. **The integrity check caught a wrong
  TRAINING_CUTOFF_MS** (I had used the venue quote table's first ts; the real cutoff is later,
  1788887700000) — fixed, so the forward test cannot silently include training candles.
- **18: 11.2 DOES NOT TRANSFER.** At Polymarket asks with the 7% taker fee, graded on POLYMARKET's
  own resolution (the settling source there): **negative at all six margins** (−0.007..−0.063), hit
  **36-45%, BELOW RANDOM**. Graded on engine actual the same fires give +0.27..+0.59.
  **Mechanism: 11.2 predicts the BINANCE CLOSE; Polymarket pays a Chainlink TWAP and the two differ
  on 10.5% of candles. The fire rule selects where the model disagrees with the Polymarket ask — and
  that ask is right about Polymarket's own resolution.** Staleness worsens it (+5c −0.157, +10c −0.256).
- **The CURRENT EF fire set DOES transfer:** +0.281/fire at Polymarket asks on POLY grading (n=69,
  halves +0.230/+0.330, monotone sweep), positive under BOTH gradings. Because EF's signal already
  IS Polymarket. On this window it does better at Polymarket prices than on Predict.fun (+0.049).
- **Platform reading: a model trained on Binance close is a PREDICT.FUN model.** For Polymarket it
  must be RETRAINED against Polymarket's resolution — a new artifact, not a redeploy.
- verify.py FAILED the EF-at-poly claim on grading provenance (two sources disagree 10.6%); honest
  resolution is that the claim is positive under BOTH gradings, so it does not change the conclusion.
- Deliverables: `task18_polymarket_transfer.md`, `models/README.md`. Repro: `task18_polymarket_transfer.py`.

## OPEN, in priority order
1. **Task 17.3** — the rain-or-sun regime grid for the 11.2 fire set on the 648 candles, plus the
   per-hour-of-day fire/PnL profile (weekend matters; Sat-Sun is the live test window).
2. **Task 17.2** — the daily forward ledger for the FROZEN model; verdict at >=100 forward fires.
3. **Task 19 (standing)** — `analysis/h1/POLYMARKET.md`: CLOB API, fees, TWAP resolution, history
   endpoints, eligibility, v10 poly run by hour/weekday.
4. **The 2.5-5 bps EF cell** (EF 45.0% vs a 70.0% null, n=40) — revisit once fills pass 60. The one
   remaining queued check; the venue-favourite check is DONE (above).
2. If nothing else is open: extend the venue window as V's snapshots grow, and re-run 11.2's replay
   on the larger set — the 15pp window-vs-long-run gap above is the main uncertainty in that result.
2. **The venue-favourite vs Binance-leader check** at t=237 in the <1bps bucket — settles the one
   thing Task 15 could not (see above).

3. **Task 12b/c/d** — ONLY as a timing model for the later entry and REVERSAL. **Not over the
   venue's own quote path** (12a killed that). Base rates as a live dashboard number still stands.
4. **Tasks 9 (MAIN cap) and 10 (regime scaling)** — LAST, both price/threshold studies.
- Task 14 DONE 23:55. Open gap it leaves: REVERSAL's <1bps cell (n=15) — revisit when the twins have
  more REVERSAL fires, since that is the one cell that could change the "EF problem, not REVERSAL"
  reading.
- **Do NOT** start a third-entry or continuous "add while the market disagrees" rule without a steer.

## Pending on the clock — RESOLVED 00:05
The daily zip never published; the REST mirror `data-api.binance.vision` supplied 09-10 instead
(86,101 rows). Still to do on it: rebuild `paths.npz` with 09-10 appended, replay J against Tokyo's
live fills on full coverage, and run Task 11.2.

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
