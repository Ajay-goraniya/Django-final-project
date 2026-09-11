# H1 STATE — single source of truth for the check-in loop
Last updated: 2026-09-11 20:50 UTC. Update this file at the end of every check.

## VERIFICATION IS NOW A GATE, NOT A HABIT (user 00:30: "verification is the most important part")
`analysis/h1/verify.py` — a `Finding` runs grading provenance / sample size / both halves /
permutation control / sweep monotonicity / cost sensitivity / beats-the-null, and `verdict()` is
True only if nothing FAILED. **Run it before reporting anything, including to V.**
Self-tested on the two real 09-10 cases: it REJECTS the cross-venue claim I got wrong and ACCEPTS
the distance premise. In that rejection **every other check passes and only `grading()` fires** —
the reason the checks run as a set and grading runs first.
Its `permutation()` permutes the model's PREDICTIONS, never the labels: shuffling labels destroys
the market's calibration too, so longshots "win" at the base rate and it prints a fake profit.

## Task 21b DONE 20:50 — the certifiable Polymarket number is NEGATIVE
`analysis/h1/task21b_certifiable.md` + `.py`. Run the moment the certifiable count crossed 60 (62 at
20:45; 7 at 14:47, 26 at 16:46, 46 at 18:46).
- **Certifiable rows (quote age known, median 15 ms): −0.062 per $1, n=61, hit 45.9%, halves
  −0.013 / −0.108.** `verify.py` PASSES (quote age, sample, halves) — a readable number, and negative.
- Uncertifiable rows (before 13:28): +0.120, n=430.
- **Caveat stated first:** not like-for-like. The certifiable rows are ONE ~7-hour evening window; the
  +0.120 spans days. The drop is NOT proven to be quote age, and n=61 in one window is not rain-or-sun.
- **No time confound here:** inside the certifiable window, fresh (≤1 s) n=48 → **−0.141**; stale
  (>1 s) n=13 → **+0.232**. Both under the 60 bar so NEITHER IS READ, but the ordering is the Task 20
  mechanism exactly — the trades that paid a stale quote are the profitable ones. 21% of the
  "certifiable" rows are themselves over a second old (p90 3.6 s, max 9.3 s).
- By side: UP n=27 +0.032, DOWN n=34 −0.136 — both under the bar, not read, so Task 24's side-skew
  question stays open.
- **Consequence:** Task 24's "+0.187 passes everything but quote age" — this is that check closing,
  and it goes the wrong way. Not a refutation yet (one evening, n=61, real confound), but the +0.187
  must not be sized on. The next step is another day of `book_age_ms` rows, not more analysis of the
  old ones. Fifth candidate to shrink at the recorded→honest step; the evidence-ladder rule held.

## Task 25 QUEUED 18:46, NOT started (V, REQUEST.md 18:20) — deliberately deferred
V asks me to **independently reproduce a v12 lane decision**: take logged fires, rebuild the feature
vector from raw inputs (1 Hz polybook + Binance klines), run the frozen v10 model, and check p, side
and EV against the lane's `feat` column. If they reproduce, the decision path is verified end to end
for the first time; if not, that is bigger than anything in the PnL tables.
**Not started on purpose.** V marked it "NOT urgent, Sunday+ is fine" and the user is low on limit
until the Sunday reset. It is the right next task once the limit allows — start here.
V's own process audit (18:20): the lane's `quote_ask` vs poly1s.py, 22 of 40 within a tick, 18 differ
by up to 9c but the book moves >=2c in 20.1% of seconds, so that is two honest observers ~0.4 s apart,
not fabrication. Signed lean −1.25c at −1.36 se — not significant, same direction as the stale-quote
artifact, re-run at n>=100.
**Noted for my own numbers:** that lane fills at the quoted ask with slippage exactly 0.0 on all 40
trades **by construction**, so its PnL is an upper bound and must never be compared like-for-like
against a live fill. This does not affect Tasks 21/23/24, none of which used that lane.

## 14:47 — REQUEST.md 249 lines: a standing constraint, not a task. Task 21b still short of n.
- V/user (14:15): `btc_model_v12_polymarket.py` is **OBSERVATION ONLY** — it keeps running in paper
  but its code does not enter the real v12 build (no dashboard, no control endpoints, so it cannot be
  operated). See `learner/v12_polymarket/DO_NOT_MERGE.md`. The Polymarket executor will be a venue
  backend inside build11 behind the existing dashboard, /api/controls, lanes, ladder and kill rules.
  **Nothing in Tasks 21/23/24 assumed that file is the executor**, so no re-basing is needed.
- Its observation DB (`learner/live_backup/v12_poly_lane.sqlite3.gz`) is the only run recording
  `quote_age_ms`, `avg_fill_price` and `slippage` per trade — exactly what Task 21b needs — but it
  holds **3 trades** (23 decisions). **Far below the 60 bar; not read.**
- V's v10 runner `book_age_ms` (live from 13:28) is the other route to the same answer; check the
  certifiable row count each time and run Task 21b only at n >= 60, UP and DOWN separately.
  **Count at 18:46: 46** (7 at 14:47, 26 at 16:46) — n=60 lands around 20:00-20:45 UTC.

## 13:55 — USAGE SAVER IN FORCE UNTIL SUNDAY NIGHT (user: "I'm running low")
User, 13:55: *"stop as much process as you can till sundays limit reset, I'm running low now every
checks in every 2 hours till sundays night."* Done:
- **H1 check is now 2-hourly** (`43 */2 * * *`) and the **off-hour self-arm is gone** — the prompt now
  says DO NOT call send_later. One armed off-hour leg deleted. **Do not restore the 30-min cadence.**
- **v11 safety net set to 2-hourly** (`37 */2 * * *`).
- **V's own 30-min check-in could NOT be changed by me** — `update_trigger` refuses to edit the prompt
  of a routine firing into another session, and that trigger re-arms itself from its own prompt. V was
  asked to re-arm it 120 min out each time. If the 30-min cadence reappears, that is why.
- One queued H1→V message deleted and its content folded into the cadence message, saving a turn.
- Each check-in is now: pull, ledger, one line, stop. No exploratory work unless REQUEST.md grew.
- Only two sessions exist (H1, V). "Astra" is a directory V made, not a running session — nothing to
  close. The 5-hour window resets ~17:30 UTC today; the weekly reset is what the user is waiting on.
- **Not cut, deliberately:** the 1 Hz loggers. Polymarket has no historical order-book data, so
  anything not captured live is gone forever. Those stay running whatever the token cost.

## Task 24 DONE 13:58 — checked V's "the venue IS the finding, stop testing and build" (5f96d1e)
`analysis/h1/task24_poly_venue_check.md` + `.py`. Unrequested; run because the conclusion is to build
a live executor. **The core claim mostly survives and fails exactly one check.**
- Gate: grading PASS (poly labels match the poly `outcome` table 429/429 — right settling source),
  sample PASS (429; UP 189 / DOWN 240), halves PASS (+0.099/+0.147), costs PASS (+2c still +0.072),
  null PASS (vs −0.276). **quote_age FAIL** — 23 of 427 asks match the collector at the same second.
  My per-fire on all 429 is **+0.123, not V's +0.187** — reconcile before either is quoted onward.
- **A haircut does NOT fix the quote-age problem.** Task 20: the honest rule REMOVES fires (55 of 97,
  worth +0.290 each), it does not merely shift prices. Only an at-or-after re-run answers it, which
  V's new `book_age_ms` (from 13:28) now permits — hours away at ~2 fires/hour.
- **"204 candles Predict.fun's book never offered at all" is NOT supported.** The collector has a
  Predict.fun quote on **429 of 429** poly-fired candles, and on 100% of the only-poly candles. The
  extra candles are ones where Predict.fun's book WAS there and the filter declined the price. That
  makes the claim a *pricing* difference, not an *availability* one — i.e. it is not independent of
  the open quote-age question, which the availability framing makes it look.
- **Strict vs broad:** V picked the broad 225-candle cell over the matched n=80 (level: +0.3078 vs
  +0.3027) because "the broad one is the one with the money in it". n=80 is over the bar, so the
  strict read is the defensible one, and the broad split needs `paired()` to count at all.
- **I was WRONG about one thing, and it favours V.** I expected Polymarket's cheaper UP to be fair
  value for a different settlement rule. It is not: on the same 808 candles Predict.fun settles UP
  48.6% and Polymarket 48.5%, −0.1 pp. So the price gap is real, not compensation.
- **NEW: the venue edge is a SIDE SKEW, not a flat edge.** 1 Hz matched, n=43,552, both halves stable:
  poly UP ask **−3.33c ± 0.12**, poly DOWN ask **+2.62c ± 0.12**. Paper mix 44% UP / 56% DOWN, earning
  +0.162 UP vs +0.092 DOWN — consistent. An executor is harvesting a side skew and its advantage will
  move with the model's side mix. Report the at-or-after re-run UP/DOWN separately.
- My recommendation: build the executor AND close the check in parallel; they do not block each other.
  Do not switch real money on the current number.

## Task 23 (was 22; V took that number) DONE 13:40 — the user's delay question, answered: the delay is nearly free
`analysis/h1/task23_delay_cost.md` + `task23_delay_cost.py`. User asked (13:55) whether to read the
Polymarket book ~300 ms after the signal, matching Predict.fun's order delay. Right correction; done.
- Measured on both 1 Hz loggers: a **cheap print** (≥2c below that candle's median) moves back by
  **+0.16c ± 0.02 (Polymarket, n=19,492)** and **+0.22c ± 0.02 (Predict.fun, n=30,995)** one second
  later. Monotone in lag (1/2/3/5/10 s), both halves agree at every lag, and the **rich**-print
  mirror is symmetric negative — mean-reverting quote noise, not drift. Unconditional move +0.00c.
- **Tokyo's real lag is 236 ms** (delay_ms median 85 + book age median 151, 427 real fills), so the
  delay costs **~0.04c**. Essentially free. Not where the money went.
- **Where it went: the 5-s collector.** Same measurement at 5 s = **0.88c (poly) / 1.25c (pred)**,
  20–25× the real-latency figure. Task 20's artifact, re-derived independently on a huge sample.
  The fix is the at-or-after rule, not a 300 ms offset.
- Coherence: real Predict.fun crossing is +0.46c (Task 21); delay explains ~0.05c, so ~0.4c is
  genuine spread/queue. Shaving milliseconds off the order path buys almost nothing.
- **One point for Polymarket:** its book is ~30% quieter at every lag. **LIMIT: `polybook` spans 7
  hours of one weekday (from 06:03 today) — NOT rain-or-sun.** Do not promote past "one window".
- Still unverified: +0.187. Only 48 of 427 poly paper trades fall in the book window — under the 60
  bar, not read. Needs the `book_age_ms` column asked of V in Task 21.
- verify.py: sample / halves / sweep PASS on both venues; grading N/A (no outcome label involved).

## Task 21 DONE 13:40 — `analysis/h1/task21_venue_disagreement_and_crossing.md` (V asked 12:55)
- **21a: both numbers are right.** Full overlap **11.21% ± 1.11 (n=803)**; the candles the Polymarket
  paper FIRED on **13.85% ± 1.67 (n=426)**; not-fired 8.22% ± 1.41. V's 14.2% is the fired subset.
  **Not a keying bug** — a one-candle shift reads 45–50%, and the three engine DBs give 0 conflicting
  labels. Mechanism: the venues can only disagree when the move is near zero (29.9% in the smallest
  move quartile vs 1.0% in the largest), and the paper fires more on small-move candles. Ordering
  holds in both halves; ~2.6 se. **Quote 13.9% for traded candles, 11.2% for population statements.**
- **21b: NO — the 1.5c is not a crossing prior.** Matched EF fills: total gap +1.18c ± 0.81c, of
  which crossing (fill − Tokyo's own 151 ms-old quote) is only **+0.26c ± 0.18c**; the rest is a
  quote-timing difference between two feeds. Full live-fill set: **EF +0.46c ± 0.09c (n=380, halves
  +0.46/+0.47)**, all kinds +0.28c ± 0.10c. Proof the quantity is not execution cost: the same
  decomposition on REVERSAL gives +15.4c. **Usable prior = +0.5c ± 0.1c**, at $1–$4 stakes only.
- **The real blocker for the Polymarket go/no-go:** only **23 of 427** poly paper asks equal the
  collector's same-second value, and `poly_pnl.trades` has no `book_age_ms`, so the paper's quote age
  cannot be certified. +0.187 carries the same exposure Task 20 found. Unblock = V logs `book_age_ms`
  on each poly paper trade; then I re-run it under the at-or-after rule.
- `verify.py` run on the crossing number: grading / quote age / sample / halves all PASS. Also
  confirms `candles.actual` == Tokyo `financial_result` on 383/383.

## Task 21 was IN PROGRESS from 13:20 (V, REQUEST.md 12:55) — two numbers, no sweep
21a: re-measure venue settlement disagreement on the full overlap; V gets 31/218 = 14.2%, the record
says 10.4%; V suspects its own candle keying. 21b: is the 1.5c live-vs-paper entry gap on Predict.fun
usable as the prior for what crossing will cost on Polymarket? One number with an error bar.
Deliverable: `analysis/h1/task21_venue_disagreement_and_crossing.md`.

## 12:42 — BOTH LIVE LANES PAUSED BY THE USER. My work is unaffected; do not re-arm.
V's commit 62d64bb: after the drawdown (EF −21.20 of the −28 giveback since the 08:21 high, equity
22.27 at the $1 floor) the user's call was to PAUSE BOTH LANES. EF, REVERSAL and MAIN all read
MANUALLY OFF; **master stays ON**, so the engine keeps quoting, grading and logging but takes no
positions. The standing "if master is OFF, re-arm" rule does NOT apply — only the user reverses this.
**What it means for H1:** nothing stops. The forward ledger replays the frozen model against the
venue *collector*, not against live fills, and the collector, both 1 Hz book loggers, the four twins
and both shadows all keep running. The ledger keeps accruing at the same rate through the pause;
the only thing that stops is live PnL. No reason to change the 100-fire bar or the ETA.

## NEW 11:46 — a third session ("Astra") exists, with `analysis/astra/` as its channel
V created it (commits e49c93e, ac3e922). `analysis/astra/BRIEF.md` points it at this file first and
makes `analysis/h1/verify.py` its gate; `analysis/astra/REQUEST.md` is where V and H1 write tasks to
it and it writes answers/blockers back. Nothing addressed to H1 there yet. **H1 still writes only
under `analysis/h1/`** — if I need something from Astra it goes in `analysis/astra/REQUEST.md`, and
that is the one file outside `analysis/h1/` I may append to, never NOTES_v11/v12.
The BRIEF carries my evidence ladder as its standing prior, so a fresh session starts from the
honest baseline instead of re-deriving the retracted +0.266.

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
| **Task 11.2's +0.266/fire (Task 20)** | **STALE-QUOTE ARTIFACT, RETRACTED 03:55.** Replay read a fresh path at S but paid an ask up to 5 s old. Honest rules: NEXT −0.077, STRICT +0.018 at margin 0.15. 55 of 97 fires vanish and were worth +0.290/fire. The SIGNAL stands (accuracy-based work unaffected); monetising it at these quotes does not |
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

## Task 17.3 DONE 03:05 — the 11.2 SIGNAL is rain-or-sun stable; its PnL grid is unreadable
- **A (the literal ask): CANNOT BE ANSWERED at 91 fires. 1 of 9 cells reaches the 60-fire bar — and
  that cell is "weekday", i.e. the whole sample. THE WEEKEND CELL IS EMPTY: all 91 fires are
  weekday, because the venue window 09-08..09-10 is Tue-Thu. The +0.266 headline is a WEEKDAY-ONLY
  number, and Sat-Sun is the planned live test window — the forward test will be the first weekend
  evidence for the fire set that has ever existed.**
  Per-hour cells are n=1..11 and swing −1.000..+0.980 — textbook noise. Reported in full, marked,
  NOT read. Needs the Task 17.2 forward test. Any regime switch drawn from this would be fitting
  noise, i.e. the banned thing.
- **B (the answerable version): THE DIRECTION SIGNAL IS REGIME-STABLE.** Diagnostic model (trained
  on the first 80% of pre-cutoff candles — **NOT the frozen artifact, which is never retrained**),
  evaluated on **14,442 held-out candles**, every cell far above the bar:
  S=20 accuracy 0.572-0.588 across all nine cells · S=60 0.634-0.649 · S=120 0.712-0.729.
  **Spread 1.5-1.7pp. Flat. No regime switch warranted.**
- **The user's weekend concern, answered: NO weekend decay.** Weekend BEATS weekday at S=20
  (0.588 vs 0.576), equal at S=60 (0.645 vs 0.643), marginally under at S=120 (0.714 vs 0.719), on
  4,032 weekend candles. Reassuring for the Sat-Sun live window.
- **ACCURACY, NOT PnL** — stated throughout. A stable signal can still be unprofitable where the
  venue prices it correctly; Task 16's null (59.2% accurate, loses money) is the standing reminder.
  PnL-by-regime remains unanswered and only the forward test can settle it.
- Deliverable: `task17_3_regime_grid.md`. Repro: `task17_3_regime_grid.py`.

## Task 17.2 LIVE — forward ledger at 51 of 100 fires (20:50). STILL NOT READABLE.
`task17_forward.py` + `task17_forward_11_2.md` + `task17_forward_state.json` (append-only; each run
processes only candles newer than the last recorded, so reruns are idempotent and history cannot be
silently restated). Frozen artifact only, never refitted. Forward = strictly after epoch 1789078800.
- **51 forward fires: 22 hits (43.1%), −0.198/fire, −10.11 total.** First half −0.330, second half
  −0.072. Baseline is the honest-rule replay (+0.018/fire ~ 0.00).
- Against the honest-rule 51.5%, 22-or-fewer hits in 51 has probability **0.1457** — it has walked
  0.0054 → 0.0393 → 0.0630 → 0.0492 → 0.0347 → 0.0539 → 0.0583 → 0.0668 → 0.0744 → 0.1330 → 0.1457
  as the hit rate climbs back toward the baseline. **The clearest demonstration yet that the early
  p-values were noise**; refusing to read them was right in both directions.
- **NOT READABLE. n=51 is below the 60 bar, let alone 100.** Recorded so the trend is visible
  from the start rather than discovered at fire 100. **No conclusion drawn, and none should be.**
- Accrual 2.25 fires/hour; the 100-fire verdict lands about Sat 12 Sep ~18:50 UTC.
- Not messaging V: V's instruction is to report only when the verdict changes or at 100 fires, and
  V merges the branch anyway. V independently started its own 11.2 live shadow (e9676dc).
- Kline set extended through 09-11 20:35 (73,103 candles) via the REST mirror.
- `book1s.sqlite3` has appeared (1 Hz price + both asks/sizes/ages) but holds only 13 epochs so far;
  the 5-s venue table stays primary until it accumulates.

## Task 20 DONE 03:55 — MY BIGGEST RETRACTION. The 11.2 PnL was a stale-quote artifact.
V's charge was right. The replay read the price path at second S but paid an ask forward-filled from
a collector sample **up to 5 s earlier** (median age 1 s, p90 3 s).
- **margin 0.15: ORIGINAL +0.207 · NEXT −0.077 · STRICT +0.018.** ORIGINAL positive at every margin,
  NEXT negative at every margin, STRICT ~zero drifting negative.
- **55 of 97 fires VANISH under STRICT and they were worth +0.290/fire** — the profit WAS the fires
  that never existed.
- **MECHANISM, and it is not the obvious one: the stale quote is UNBIASED** (NEXT−ORIGINAL mean
  −0.0005, median 0.000) **but differs >5c on 17.3% of samples, and the EV filter SELECTS the
  randomly cheap ones.** An unbiased measurement error becomes one-directional profit the moment you
  condition on it. **This is why it passed permutation, seeds, halves, sweep and cost: all of those
  test the SIGNAL; none test whether the PRICE WAS REAL.** The cost row added a haircut to a
  fictional ask.
- **Task 17.2's 1-of-8 forward start is no longer a surprise — it was the first honest measurement**
  and it agrees with STRICT/NEXT, not with the replay.
- **SURVIVES:** Task 15's distance premise (no quotes involved), Task 17.3's regime stability
  (accuracy-based), Task 16's naive null (a negative, flattered if anything), Task 18's negative.
- **STANDING RULE: the collector `q` table is 5-s data — "quote age unknown, up to 5 s" in every
  study. Never pair a fresh observation with an earlier quote. `verify.py` now has `quote_age()`,
  which FAILS a finding whose quote can predate the decision.** `book1s.sqlite3` (1 Hz + age_ms) is
  the right source as it accumulates.
- Deliverable: `task20_stale_quote.md`. Repro: `task20_stale_quote.py`.

## Task 20 item 3 DONE 04:25 — CANDIDATE J IS **NOT** A STALE-QUOTE ARTIFACT
J selects on cheapness (ask <= cap) so it had to be re-run. It survives.
- **cap 0.60: ORIGINAL +0.230 (n=151) -> NEXT +0.195 (n=147).** All caps stay clearly positive
  (+0.207/+0.209/+0.195/+0.160/+0.142/+0.109). Halves positive under NEXT (+0.184/+0.205).
- **Only 11-17 fires vanish out of 118-255, and they are mostly LOSERS** (−0.356/−0.057/−0.181/
  −0.173/−0.282 per fire). **Compare 11.2: 55 of 97 vanished and were worth +0.290.** Opposite sign,
  an order of magnitude fewer.
- **WHY THE SAME-LOOKING RULE DIFFERS — keep this:** exposure to quote noise scales with how tightly
  the rule optimises AGAINST the quote. 11.2's EV filter compares p directly to the ask (maximally
  exposed); J's cap only excludes expensive entries and takes direction from EF (barely exposed).
- **verify.py: 5 PASS (incl. the new quote_age), 2 FAIL — and I am overriding one.** Sweep "fail" is
  a **+0.002** blip between caps 0.50 and 0.55; effectively monotone, not an overfit signature.
  Cost fail is REAL on recorded quotes (+5c +0.020, +10c −0.101) but is **answered by better
  evidence: V's replay on Tokyo's REAL FILLS gave +0.153/fire on 128 fills**, which already embeds
  true slippage and sits between my +0c and +5c rows.
- **J's case does not depend on the 5-s table at all.** Its live forward shadow still decides it.
- Deliverable: `task20b_candidate_j.md`. Repro: `task20b_candidate_j.py`.

## Task 20 continued 05:00 — Task 16 prior ALSO an artifact; Task 18's EF-at-poly WEAKENS (correction)
- **Task 16's prior: positive at every margin under the stale quote, NEGATIVE at every margin under
  the honest one** (+0.111/+0.087/+0.094/+0.169/+0.243 -> −0.042/−0.064/−0.166/−0.245/−0.308).
  My "insufficient both ways" was TOO GENEROUS to the prior; honestly priced it LOSES at every
  margin. Task 16's naive-null headline is untouched and reinforced.
- **Task 18's EF-at-Polymarket: CORRECTION TO WHAT I REPORTED.** I said +0.281/fire and "passes both
  halves". Honest rule: **+0.223 at margin 0.10 (n=67, 62.7% hit) — the only margin clearing the
  bar — and its halves are −1.22/+16.14, so it FAILS both-halves.** Still positive, but suggestive
  rather than established, and it should NOT carry a platform decision on its own.
  The Predict.fun side of that comparison (+0.049) is UNAFFECTED — it used `ef_v11_ask`, the ask the
  engine itself recorded at fire time, not a collector sample.
- **Task 18's two structural conclusions stand:** 11.2 does not transfer (a negative, only flattered
  by the artifact), and a Binance-close model is a Predict.fun model (a resolution-source argument).
- **THE PATTERN ACROSS ALL FOUR RE-RUNS — the cleanest statement of the lesson:**
  11.2 (EV filter) +0.207 -> +0.018 · Task 16 prior (EV filter) +0.087 -> −0.064 ·
  Task 18 EF@poly (EV filter) +0.361 -> +0.182 halves fail · **J (loose cap) +0.230 -> +0.195
  SURVIVES.** Every EV-filter rule was inflated; the one rule that only excludes expensive entries
  was not.
- **Forward ledger CORRECTED and REBUILT** at 04:50: it was using the stale rule too. The 8 fires
  recorded under it were DISCARDED, not carried forward — a mixed history is worse than none. Under
  the honest rule it now has 2 fires, 0 hits (p=0.235 under the honest-rule 51.5%, i.e. nothing).
  Its stated baseline is now +0.018, not the retracted +0.266.
- Deliverable: `task20c_rerun_16_18.md`. Repro: `task20c_rerun_16_18.py`.

## Task 19 STARTED 05:30 — `POLYMARKET.md` created. Two data answers + a fee inconsistency.
- **(3) WE CANNOT GRADE POLYMARKET RESEARCH FROM KLINES.** Best of five pre-fixed TWAP candidates
  (`last30_mean >= open`) agrees with Polymarket's outcome on **91.4%**, against **89.5%** for just
  using the engine's actual — a 1.9pp gain, and **~9% of candles still mislabelled**, concentrated in
  flat candles (median |close-open| 1.47 bps vs 5.53 overall). **Any Polymarket study must grade on
  Polymarket's own outcome table**; a kline TWAP would reintroduce the Task 14 error elsewhere.
- **(6) THE v10 POLY RUN IS WEEKDAY-ONLY TOO: n=371, weekend n=0.** hit 52.8%, +0.133/$1, median ask
  0.45, median fire second 68. **Nothing we have measured on EITHER venue includes a weekend** —
  worth saying plainly before a weekend migration test. 00-08 UTC is near flat (+0.014, n=115) vs
  ~+0.19 in the active blocks: an observation, NOT a rule.
- **(2) FEE INCONSISTENCY BETWEEN TWO OFFICIAL SOURCES, unresolved.** Docs table says Crypto = 0.07;
  the Help Centre says fees "peak at 1.56% at 50%", which implies 0.0625 (0.07 gives 1.75%). We used
  0.07, the conservative side — if 0.0625 is right we are OVERSTATING Polymarket costs by ~11% of
  the fee, i.e. the error favours Polymarket. **V's gamma `takerBaseFee 1000` matches neither** (700
  / 625 on a 1e-4 scale); not guessing its units. Resolve against a real fill before migrating.
- Also confirmed: formula `shares x feeRate x p x (1-p)`, makers free, symmetric about 0.50, so per
  $1 staked the fee is `feeRate x (1 - ask)`.
- **(4) HARD CONSTRAINT FOUND: WE CANNOT BUILD A POLYMARKET ASK HISTORY.** The only historical
  endpoint is `/v2/prices-history`, which returns **midpoints only** — no historical book, bid, ask
  or trades endpoint exists. Retention: 1-min ~7 days, 5-min ~60 days, 30-min ~90 days. Combined
  with Task 20 (a replay must price at an ask taken at or AFTER the decision), **all Polymarket
  evidence must come from FORWARD collection** — our own 1 Hz logger or a live paper run. No
  shortcut through their API.
- **(5) Executor delta vs Predict.fun:** EIP-712 signing on Polygon chainId 137 (new component;
  deposit wallets need ERC-7739 wrapped signatures); order types GTC/GTD/FAK/FOK, and **GTD expires
  one minute BEFORE its stated expiry** — relevant for 5-min markets; `min_order_size` and
  `tick_size` are PER-TOKEN and must be read per market; websocket
  `wss://ws-subscriptions-clob.polymarket.com/ws/market` with `book`/`price_change`/
  `last_trade_price`/`tick_size_change`, **PING every 10 s**. Rate limits NOT documented — unknown.
- **THROUGHPUT CONSTRAINT FOR THE MIGRATION DECISION.** Daily RELAYER transaction limits:
  **Unverified 100/day · Verified 10,000/day · Partner unlimited.** The engine fires ~150/day, so an
  **UNVERIFIED relayer account is a HARD BLOCKER.** Deposit/Proxy/Safe wallets all route through the
  Relayer; an **EOA bypasses it** (direct on-chain, pays POL gas) but EOAs are "available for
  allowlisted traders". **So a Polymarket run needs account verification OR EOA allowlisting before
  it can operate at our fire rate** — a prerequisite, and both routes need someone outside this
  project. Per-second/per-minute API limits are only "Standard"/"Highest", never quantified publicly.
- Auth is two-step: L1 ERC-712 signature proving signer control -> L2 credentials (apiKey, secret,
  passphrase) derived from the CLOB.
- **ELIGIBILITY, as published (no interpretation, not legal advice):** tiered geoblock with two
  documented states — **"block completely"** (no new orders AND existing positions cannot be closed)
  and **"close-only"**. Named examples: Italy view-only, Germany prohibited (positions held to
  resolution), Singapore close-only. ToS: **US persons and certain other jurisdictions may not
  trade** on polymarket.com; US users go to polymarket.us, a separate regulated entity. Institutional
  onboarding is **non-US only, non-restricted jurisdictions**. The full restricted list is in the ToS
  and is NOT enumerated here — check the operating jurisdiction against it directly before migrating.
  **Operational note: a "block completely" state TRAPS open positions**, which on a 5-minute market
  is a settlement risk, not just an access one.
- **Forward-ledger efficiency note:** the ledger is gated on V's SNAPSHOT pushes (venues.sqlite3),
  not on my kline fetches. At 06:43 the klines advanced but the venue book had not, so 0 new fires.
  Don't spend a check fetching klines when `venues.sqlite3.gz` has not changed.
- **BLOCKED, not just pending — the three Task 19 gaps cannot be closed from here:**
  (1) the enumerated restricted-jurisdiction list — `polymarket.com/tos` serves a JS app shell to a
  fetcher, so the ToS text is unreachable; someone must read it in a browser.
  (2) quantified per-second API limits — described only as "Standard"/"Highest", not published.
  (3) the fee rate (docs 0.07 vs help-centre-implied 0.0625) — only a REAL FILL settles it, which is
  V's side. All three are recorded in POLYMARKET.md as open with what would unblock each.
- **Forward ledger at 10:47: 25 fires, 8 hits (32.0%), −0.330/fire, both halves negative**
  (−0.054 / −0.584). Accrual 2.07/h, ETA **Sat 12 Sep 22:50 UTC**.
  **p has now crossed 0.05 (0.0393 against the honest-rule 51.5%). THAT IS NOT THE VERDICT and I am
  not treating it as one.** n=25 is far below the 60 bar, let alone the pre-committed 100 with both
  halves. At 8 fires I called a p=0.005 start "not a verdict" and it swung back; the same discipline
  applies now that the direction happens to suit the prior. V not messaged; the rule is 100 fires or
  a verdict change, and neither has happened.
- **Nothing else is open.** Task 19's three gaps are BLOCKED with named unblockers; the 2.5-5 bps
  cell needs ~14 more fills; everything else is DONE or retracted. Per the user's "don't do
  unnecessary or unuseful work", checks with no new task and no new venue data should advance the
  ledger, say so in one line, and stop.
- (earlier) **VERDICT ETA, computed automatically in the ledger: accrual is 1.75 fires/hour (16 over
  9.2 h), so the 100-fire verdict lands about Sun 13 Sep 07:47 UTC.** Useful for planning: that is
  AFTER the Sat-Sun window, so **the verdict will arrive with weekend fires included** — which
  matters because neither the 11.2 replay nor the v10 poly run has a single weekend candle.
- (earlier) **Forward ledger at 07:50: 16 fires, 6 hits (37.5%), −0.179/fire** (p=0.192 vs 51.5%), halves
  −0.423/+0.065. Not readable, verdict unchanged, V not messaged.
- (earlier) **Forward ledger at 07:20: 15 fires, 6 hits (40.0%), −0.124/fire** (p=0.264 vs 51.5%), halves
  −0.340/+0.065. Not readable, verdict unchanged, V not messaged.
- (earlier) **Forward ledger at 06:18: 13 fires, 6 hits (46.2%), +0.010/fire** — it swung UP from −0.487 at 9
  fires and now sits essentially ON the honest replay's +0.018, not the retracted +0.266. Still NOT
  READABLE (n=13) and the verdict is unchanged, so V was not messaged. **The swing is a useful
  check on my own earlier framing: at 8 fires I flagged the start as improbable (p=0.005) while
  labelling it "not a verdict" — five fires later it reversed. The label was doing real work.**
- Deliverable: `POLYMARKET.md`. Repro: `task19_poly_research.py`.

## 07:25 — the EF flat-bucket edge, tested PROPERLY: still not established (p=0.341)
Tokyo fills grew 256 -> 320 EF, and the `<1 bps` bucket 120 -> 150, so I revisited it. Uses NO venue
quote, so Task 20 does not touch it. Venue-graded (settling source).
- **The edge STRENGTHENED to +5.3pp with both halves IDENTICAL (+5.3/+5.3).** That looks like a
  finding. **It is not.**
- **Exact McNemar: p = 0.341.** The two rules AGREE on 96 of 150 fires. Of the 54 discordant pairs,
  EF-only-right 31 vs move-only-right 23 — **the entire edge is 8 trades.** At this effect size it
  needs about **n=490** fires.
- **The identical halves were NOISE, not corroboration** — 54 discordant pairs split across halves
  is ~27 each. `halves()` tests whether the SIGN is stable; it cannot distinguish a stable signal
  from symmetric noise.
- **METHOD UPGRADE, keep this: for a rule-vs-rule comparison on shared candles, the raw edge AND the
  halves check both overstate the evidence. Use McNemar on the DISCORDANT pairs** — the ~64% of
  trades where both rules agree inflate n without adding power. A 150-trade sample was really a
  54-trade sample.
- **Second time today a number passed the standard checks and failed a sharper one** (first: Task
  20's quote rule). Same pattern both times: **the checks test the SHAPE of the result, not the
  thing the result actually depends on.**
- `2.5-5 bps` cell: n=46 (was 40), EF 47.8% vs a 71.7% null, holds its shape. Still under the bar,
  still not read.
- Note: `2026-09-11_0725_ef_flat_bucket_mcnemar.md`.
- **ENCODED IN THE HARNESS 08:00: `verify.py` now has `paired(mine_right, theirs_right)`** — exact
  McNemar on the discordant pairs, failing above p=0.05. Self-test 3 replays the real 07:25 numbers
  and rejects them. Also referenced from repo-root `CLAUDE.md`, so every session gets it.

## 08:55 — CANDIDATE J REFUTED BY V. THE PATTERN ACROSS ALL FIVE CANDIDATES IS NOW THE FINDING.
V refuted J at its pre-set 100-fire live verdict: 102 graded, positive overall (+0.07..+0.12/fire by
cap) but **second half NEGATIVE at every cap** (cap 0.60: +9.03/−1.25). It fails the both-halves
ship rule. That is the fifth candidate to die, and the fifth to die the same way.
**THE LADDER — every candidate, at every evidence level it reached:**
| candidate | wrong grading | stale quote | honest quote | real fills | live forward |
| 12a cross-venue | +0.44 | — | ~0.00 | — | — |
| 11.2 model | — | +0.207 | +0.018 | — | −0.179 (16, early) |
| 16 prior | — | +0.087 | −0.064 | — | — |
| 18 EF@poly | — | +0.361 | +0.182 (h1 neg) | — | — |
| **J** | — | **+0.408** | **+0.195** | **+0.153** | **+0.07..+0.12, h2 neg -> REFUTED** |
**NOT ONE CANDIDATE IMPROVED AT ANY STEP.** J climbed the whole ladder and halved at each rung.
**WORKING RULE: divide a recorded-quote per-fire number by at least 3 before treating it as an
expectation, and assume the BOTH-HALVES test is the binding constraint, not the level. A replay
number is a screening device for what to shadow, not an estimate of what you will earn.**
**The J case is the important one: honest quote, real fills, correct grading — nothing wrong with
the replay at all — and it STILL did not carry forward. Retrospective rigour does not substitute for
a forward test at a pre-committed n.**
**UNAFFECTED, because they never touch a venue quote:** the distance premise (72,863 candles) and
its regime stability (14,442 held-out). They are statements about the TAPE, not about tradeable
edge, and remain the only things here not walked back.
**Honest project summary: we understand the market better than we did, and we have not yet found
anything that makes money at prices we can prove existed.**
- Note: `2026-09-11_0855_evidence_ladder.md`.

## OPEN, in priority order
1. **Task 19 (standing)** — the daily forward ledger for the FROZEN model; verdict at >=100 forward fires.
2. **Task 17.2 continues automatically** — re-run `task17_forward.py` each check; report only when
   the verdict changes or at 100 forward fires.
3. **The 2.5-5 bps EF cell** (EF 45.0% vs a 70.0% null, n=40) — revisit once fills pass 60. The one
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
