# REMAKE PLAN — live must run the logic that wins on paper

Written by V (head), 09-13 21:50 UTC, at the user's instruction: *"work with aws Mumbai and remake the
model... the paper model does very well, but the same model in live has different logics, that's not
acceptable."* Every claim below was checked against the running code or journal before it was written.

## 1. Diagnosis — the user's claims, verified one by one

| user's claim | verified? | evidence |
|---|---|---|
| **paper and live run different logic** | **YES, entirely** | paper = `scratchpad/v12/engine/btc_model_v12_polymarket.py`, one 34.7 KB file dated **Sep 11 13:40**. Live = 2,300 lines across 3 files. `diff` = **1,291 lines**. Paper has **zero** of: `_gate_on_padded_ev`, `EV_REFERENCE_PAD`, `slippage_band`, `candle_attempts`, `_calibrate`, `_wipeout_check`, `_main_oneshot_check`, `order_plan`, `kill_window`, `halt_cleared_at`. **Every mechanism added since Sep 11 exists in live only.** The +457 paper row in the fair table is the Sep 11 program. |
| **MAIN and REV not firing** | **YES** | MAIN: 1 fill all day (18:20:43), closed on 12 candles with 0 EV-admissible at any threshold. REV: 0. Live `poly_lanes.py` is *"Build 11 pressure engine ported"* with `GATED_ODDS 0.60/0.40`, `VOL_MIN 0.70`, `PRESSURE_FIRE 0.15`, `HOLD 12 s / 60 reads`, then the EV bar on top. **Paper has no MAIN/REV at all** — it is EF-only and wins anyway. |
| **EV refuses at minute 1, can't re-fire at minute 3** | **fixed in code, but the real point stands** | `poly_core.py:493 release()`: a SKIPPED signal deletes its row and can re-fire, bounded at `MAX_ATTEMPTS_PER_CANDLE=4`. The docstring says the consume-the-candle bug was real and was fixed. **But** the architecture is still *signal fires blind → separate gate refuses*. Paper's `decisions` table carries `p, ask, ev, fire` **on the same row** — **paper's EV is inside the decision, exactly as the user asked.** |
| **nothing is adaptive** | **YES for live** | live has calibration (inert), a stake ladder (user overrode to fixed), an EV "regime" mode. Nothing learns from outcomes. The adaptive layer that was designed — `btc_model_autopilot.py`, `AUTOPILOT_11.4.md` §E2 (regime cells as engine data, self-verdicted) — sits in the paper engine's directory and **was never wired into live.** |
| **execution noise, book/feed staleness, slippage, accounting** | **YES, and it is where today went** | 17+ builds on execution mechanisms, several retracted. Reject mechanism still open (gate-vs-feed). Accounting: MAIN was charged to EF until 12.8.2; master arming unaudited until 12.8.5. |

**The one-sentence diagnosis:** the model that wins is the Sep 11 program with EV inside the decision and
no post-signal gates; the model that trades real money is that program plus 1,291 lines of gates and
executor mechanisms, added one at a time, none of them tested against the paper baseline they diverged from.

## 2. The test that decides the remake — runs TONIGHT, it is a query not a build

**Decision diff on shared candles.** Both engines have watched the same Polymarket BTC 5-min candles since
Sep 11 13:40. Paper's journal (`learner/live_backup/v12_poly_weekend.sqlite3.gz`, snapshot 21:50, 317 graded,
**7,280 decision rows** with `p, ask, ev, fire` per candle) and live's journal on the AWS box.

Join on epoch. For every shared candle, four columns: **paper decided / live decided / what paper earned /
what live earned.** Then the grid, whole, every cell:

| paper | live | n | paper PnL/$1 | live PnL/$1 |
|---|---|---|---|---|
| fired, won | fired, won | | | |
| fired, won | **skipped on EV** | | | — |
| fired, won | rejected by venue | | | — |
| fired, lost | skipped / rejected | | | — |
| did not fire | fired | | — | |
| ... every combination ... | | | | |

**The cell that matters: paper fired & won, live skipped on EV.** That cell's paper PnL is the money the
gates cost. If it is large and positive, the remake is a **strip-back**: live's decision logic becomes
paper's decision logic, and live keeps only what paper lacks and needs — the real executor, retries,
reconcile, claim, journal, dashboard, audit. If it is small, the divergence is in execution (fills and
rejects), the gates are not the problem, and stripping them would add losses. **No design decision before
this number. It is real data on both sides, not a reconstruction.**

AWS runs it (Task 76). It is the highest-value thing that session can do, because it holds the live journal
and nothing else does.

## 3. The remake — sequenced so every change is rechecked before the next

The user: *"after every change everything should be rechecked, its effects, and all the other things
those are affected by it."* Binding on every step.

| step | when | what | recheck |
|---|---|---|---|
| **0** | tonight | decision diff (§2) | it IS the check |
| **1** | tonight | this plan on the branch | — |
| **2** | Monday | **build the strip-back** (or the execution fix, per §2). Decision path = paper's `decisions` logic verbatim: EV computed inside the fire decision, not gated after. Executor kept. Remove what paper lacks and the diff says costs money. | every test that asserted the old behaviour is **inverted, not deleted**; every touched path's downstream (journal, kill rules, dashboard rows, audit, `rolling()`) re-run; 3 suites + checksums; each new test shown to **fail against the old file** |
| **3** | Monday, all day | run it as a **paper twin beside live** on Monday's wide tape — same candles, both journals | it must **beat live AND match paper** on shared candles, whole grid, both halves. Under 60 graded = insufficient, not read. `verify.py` on the result. |
| **4** | Tuesday | deploy if step 3 passes. **Not before.** | post-deploy: confirm it comes back with the user's flags, not safe-startup surprises |
| **5** | after 4 | wire the adaptive layer (11.4 autopilot §E2: regime cells self-verdicted from live outcomes) | same standard: twin first, then live |
| **MAIN/REV** | after 5 | rebuild from the Build 11 source **only if** a paper twin of them earns. Paper wins without them. **Not a precondition for beating paper.** | twin, 60+ graded, both halves |

**Frozen while this runs:** no further execution-mechanism builds. 12.8.5 (audit) ships at the step-4
restart, not separately. The reject mechanism (gate vs feed) is instrumented at step 4, not before.

## 4. Monday — the honest statement

**No rebuild ships before Monday's open.** Step 2 cannot be built and rechecked in two hours, and shipping
an unchecked build into the first wide-tape day is the exact churn that burned 09-13. **The engine that
trades Monday is 12.8.4**, armed at $3 with the hand rule at −2.00. Monday is step 3's test day: the strip-
back runs as a twin beside it, on the same candles, and Monday's data is what qualifies it.

**Monday's own risk, already on the record:** the weekend tape ran 10.9 bps, weekday 17.7. Under the
gate-selects-quiet-books reading, a faster tape means more retries and DEADLINEs, fewer submissions;
under feed-slowness, more rejects. AWS is tracking submissions / retries / DEADLINEs per candle from the
open so both predictions get tested rather than argued.

## 5. What "adaptive" means here, so it is not another gate

Not a switch the user or the AI flips. Not a threshold sweep. Per `AUTOPILOT_11.4.md` §E2 and the standing
"rain or sun" rule: regime buckets defined **in advance** (UTC block, weekday/weekend, trailing-range
quartile, recent crossings, book width), every cell tracked from **live outcomes**, each cell self-verdicted
at 60+ graded both halves, and the engine's frequency in a cell follows that verdict. The buckets and the
bar are fixed now; the verdicts come from the data. That is the difference between a gate and a brain.

## 6. Roles

- **V (this session):** owns the plan, the build, the tests, the twin, and every claim in this file.
  *"as the main session, a head session you are responsible for all that."* Accepted.
- **AWS Mumbai:** the live journal, the decision diff, deploys, and post-deploy verification. Given
  measurement and deployment work only — no more speculative tasks.
- **H1:** `verify.py` on the twin result at step 3.
- **The user:** the step-4 go, and every control write on the live engine.
