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

### 1a. CORRECTION, 22:10 — the decision path is IDENTICAL. The gap is fill rate.

The table above stands, but its one-sentence reading was wrong and I am replacing it before it misleads
anyone. Read line by line against both files, the **decision** — whether a candle is worth firing — is
the same in paper and live:

| component | paper (Sep 11) | live (12.8.4) | same? |
|---|---|---|---|
| model | `btc_model_v10.py`, `m.decide(...)` | same file, same call | **yes** |
| EV formula | `p·(1/c−1) − (1−p)` | `p/c − 1` | **algebraically identical** |
| fee model | `q/(1−0.07(1−q))` | `rate·(px(1−px))^exp`, r=0.07 e=1 | **numerically identical to 4 dp across 0.30–0.90** |
| threshold | `--ev` not given → model's per-vol table | `mode=regime` → model's per-vol table | **yes** |
| price EV is judged at | `ask + pad_ticks(1)·tick` | `ask + EV_REFERENCE_PAD(1)·tick` | **yes** |
| EV inside the decision? | yes (`execute_live` re-judges per attempt) | **yes** — `_gate_on_padded_ev` runs inside `decide_now` before `fire` is claimed (12.4.0) | **yes** |

**So "EV should be within the signal logic" is already how live works**, and paper and live should agree on
side and `p` on every shared candle — Task 76 must confirm that number, and if it is not ~100% something
above is wrong.

**The post-decision gates that differ, each measured:**

| gate | live | paper | cost, measured |
|---|---|---|---|
| quote-age clamp | **2.0 s** hard max (`quote_age_s`) | 5.0 s | books aged 2–5 s are **0.24%** of 139,418 logged seconds — negligible |
| venue minimum (5 shares) | refuses `amount/cap < 5` → **at $3, every ask > 0.59** | `min_retry_usdc=0.10` only | **10 of 318 paper fires (3%)**, and those ten ran +0.272/$1 |
| `require_depth` | **OFF** (`all_or_nothing=False`) | none | not a difference |
| `no_terms` gap | skip while terms refetch (≤5 s) | none | unmeasured — Task 76 counts it |

**And the one that is not a gate at all — paper's fill model:**

```python
if self.a.execution=="paper":
    mark_execution(state="PAPER_FILLED", attempts=1, avg_fill_price=q.price, slippage=0.0, reason="paper_at_ws_ask")
```

**Paper fills every fire, instantly, at the websocket ask, with zero slippage, 100% of the time.**
Live, lifetime: **82 orders → 38 fills, 40 rejected — a 49% reject rate.** Half of live's decisions never
become trades, and (Task 73) the half that do are the ones on quieter books.

**The corrected one-sentence diagnosis:** paper and live make the same decision on the same candle; paper
then books a fill at the quote every time, and live gets one about half the time. **The +457 is a 100%-fill
number. The remake target is fill rate, not the signal.** Task 76's job is now to price the unfilled half:
what did paper earn on the candles where live decided the same thing and then got rejected?

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

### 2a. RESULT, 22:25 — the number is in, and it names the target

**Row 0: same model, same decision.** On 114 candles both fired: side agreement **97.4%**, |Δp| median
**0.0000** (p90 0.055), EV median 0.173 on both. Across 2,705 time-matched decision rows: side 93.7%,
|Δp| median 0.0013. §1a confirmed. (AWS's first Row 0 run paired a mid-candle paper row with an end-of-
candle live row — 73% / 0.16 — caught and voided by AWS itself before reporting.)

**The grid, 333 shared candles, 156 paper fires, everything graded on `candles.actual`:**

| paper fired → live did | n | paper $/1 on those | reading |
|---|---|---|---|
| **filled** | **29** | won 15 / lost 15 | live's actual trades — 19% of paper's fires |
| **skipped: EV at padded price** | **56** | 32 won +0.524, 24 lost −0.506 → **net ≈ +0.08** | the gate refused a break-even set. **It is working.** |
| **REJECTED by venue** | **31** | 16 won ≈+0.99, 15 lost −0.50 → **net ≈ +0.25** | **the money. This is the fill-rate target.** |
| no signal | 42 | ~26 are quote/timing at the decision second, 9 "warming up" | mostly timing, not logic |

**Every cell is under 60 and is marked insufficient.** But the shape is decisive: **of 156 paper fires
live filled 29**, and the bucket with the money is not the EV gate (net +0.08 — it is correctly declining
coin-flips) but **the 31 venue rejects at ≈+0.25/$1 on paper**. That is the unfilled half, priced.

**Two corrections to the user's own framing, in their favour to know:**
1. **The EV gate is not the problem.** The 56 it refused were break-even on paper. Leave it.
2. **Paper's headline is oracle-flattered.** Paper's `trades.win` disagrees with `candles.actual` on
   **32 of 156** fires — it grades on its own resolution. On the honest oracle, paper on shared candles
   is **88W/68L = 56.4%**, not what its table shows. Live filled on the same candles: 15W/15L, n=30,
   too small to read. So "beat the paper" means beat **56%** on `candles.actual`, not the table.

**Step 2 is therefore the fill-rate fix and nothing else.** The 42 "no signal" are decision-second timing
— paper decided at second *s*, live at *s+11* (p90) and the quote had moved — and that is the same
mechanism as the rejects viewed from the other side: **live is slower to the quote than paper's
bookkeeping is.** One target.

## 3. The remake — sequenced so every change is rechecked before the next

The user: *"after every change everything should be rechecked, its effects, and all the other things
those are affected by it."* Binding on every step.

| step | when | what | recheck |
|---|---|---|---|
| **0** | tonight | decision diff (§2) | it IS the check |
| **1** | tonight | this plan on the branch | — |
| **2** | Monday | **build the fill-rate fix** (per §1a the decision path needs no change). Candidates, in the order the evidence ranks them: (i) the `seq`-unchanged submit gate at `poly_core.py:928` that selects quiet books (AWS's reading, Task 75 — resolve gate-vs-feed with the `age_ms` instrumentation first); (ii) re-judge EV **per attempt at the live quote** the way paper's `execute_live` does, instead of `continue`-ing on any tick; (iii) the 2 s clamp → 5 s to match paper (0.24%, cheap, do it). **Not** a threshold on `age_ms`. **Not** touching the signal or EV. | every test that asserted the old behaviour is **inverted, not deleted**; every touched path's downstream (journal, kill rules, dashboard rows, audit, `rolling()`) re-run; 3 suites + checksums; each new test shown to **fail against the old file** |
| **3** | Monday, all day | run it as a **paper twin beside live** on Monday's wide tape — same candles, both journals | it must **beat live AND match paper** on shared candles, whole grid, both halves. Under 60 graded = insufficient, not read. `verify.py` on the result. |
| **4** | Tuesday | deploy if step 3 passes. **Not before.** | post-deploy: confirm it comes back with the user's flags, not safe-startup surprises |
| **5** | after 4 | wire the adaptive layer (11.4 autopilot §E2: regime cells self-verdicted from live outcomes) | same standard: twin first, then live |
| **MAIN/REV** | after 5 | rebuild from the Build 11 source **only if** a paper twin of them earns. Paper wins without them. **Not a precondition for beating paper.** | twin, 60+ graded, both halves |

### 3a. Step 2, candidate (ii) — DESIGNED 09-13 23:5x. The paper-parity attempt loop. Not built.

Read side by side (`scratchpad/v12/engine/...:477-520` vs `learner/v12_2/poly_core.py:875-990`), the two
attempt loops differ in exactly three places, and together they are the fill-rate mechanism:

| step | paper | live (12.8.4) | effect |
|---|---|---|---|
| before each attempt | take the **current** fresh quote | `while …: if q and q['seq']!=seq: break` (`:880`) — **wait for the book to TICK** since the last attempt | on a quiet book the retry waits out the 2 s budget → **DEADLINE** |
| after signing | n/a — sign+post is one call | `if not latest or latest['seq']!=seq: continue` (`:928`) — **abandon the signed order if the book ticked during the ~10 ms sign**, go back to waiting for another tick | a moving book cannot be posted against |
| after a retryable reject | `sleep 75 ms`, loop | `continue` straight into the tick-wait | second shot only if the book happens to tick |

**Live does retry** (`RETRYABLE` substring path, `:983`) — the 12.4.8 fix is real. **But every retry
waits for a tick inside a 2.0 s budget**, so 82 orders produced 4 second attempts and 10 DEADLINEs.
Paper gets three shots at the current book inside a second. **That is the 31 rejects.** It is consistent
with AWS's "gate selects quiet books" reading (the tick-wait literally selects a just-ticked book, then
abandons on the next tick) and needs no slow feed.

**The change — three edits in `Executor.fire`, nothing else:**

```
:880   if q and q['seq']!=seq: break          →   if q: break
:928   if not latest or latest['seq']!=seq: continue   →   if not latest: continue
:983   continue   (after RETRYABLE)           →   await asyncio.sleep(0.075); continue
```

- `:880`: attempt 1 already breaks immediately (`seq=-1`); this makes attempts ≥2 do the same. The
  freshness filter `self.age` still applies — a stale book still waits.
- `:928`: the guard that matters is already there and stays — `order_plan(latest, …)` at `:932` re-checks
  EV and depth on the moved book and releases `EV_CHANGED` if it fails. The signed order's cap is from `q`;
  if the ask moved up past it the FAK rejects cheaply, if down it fills better. Exactly paper's behaviour.
- `:983`: paper's `retry_delay_ms=75`. Four attempts × (~140 ms RTT + 10 ms sign + 75 ms) ≈ 0.9 s fits the
  2.0 s budget; the budget is a launch flag if Monday says otherwise.

`seq` stays recorded in `timing` for the diff. **The signal, EV, threshold, reference price, band cap,
kill rules and audit are untouched.**

**Tests (rule: inverted not deleted; each new one shown failing against 12.8.6's files):**
1. NEW `test_retry_on_a_book_that_did_not_move`: broker rejects once with `fak_not_filled` and does NOT
   move the book → **2 orders**. Old code: 1 order then DEADLINE/EXHAUSTED. **Fails on old.**
2. NEW `test_a_tick_during_signing_does_not_abandon_the_order`: `prepare()` mock applies a snapshot with
   the same ask → order posts. Old code: 0 orders. **Fails on old.**
3. NEW `test_a_tick_during_signing_that_breaks_ev_still_releases`: snapshot during `prepare()` with an ask
   that fails EV → `EV_CHANGED`, 0 orders. Pins that the `:932` guard is doing the work now.
4. KEPT `test_retry_only_on_fresh_quote` — still passes (the book moved; the retry uses it).
5. KEPT `test_model_changed_before_post_abandons` — SIGNAL_CHANGED untouched.
6. NEW `test_retry_waits_75ms`: two attempts ≥ 70 ms apart.

**Downstream rechecked after the change (§7 row 7 list, written now so it cannot be skipped later):**
`timing['quote_wait_ms']` no longer means "waited for a tick" — dashboard latency panel reads it;
`_sample()` stats; `candle_attempts`; DEADLINE rate (should fall); attempt histogram (should widen);
Task 73's submit-time `age_ms` distribution (will shift — that is the point, and 12.8.6's `AMBIENT_AGE`
is the control); per-fill paid−ask (may rise slightly; band cap bounds it; **measure on the twin**).

**What qualifies it (step 3, Monday, paper twin beside live, same candles):** fill rate up from 49%;
DEADLINEs down; **PnL/$1 on filled ≥ live's AND the twin's decided-and-filled set ≥ 56.4% on
`candles.actual`**; both halves; ≥60 graded or "insufficient". `verify.py` by H1. If paid−ask rises
more than the fill-rate gain is worth, the twin says so and it does not ship.

**Frozen while this runs:** no further execution-mechanism builds. **12.8.5 (master-arming audit) and
12.8.6 (halt flip-flop fix + ambient book-age sampling) are built, tested and HELD**; both ship at the
next natural restart. 12.8.6's sampling is what resolves the gate-vs-feed question (Task 75) - it needs a
few hours of live data after it is deployed, which makes the step-4 restart the earliest that question can
be answered, and the answer ranks the step-2 candidates.

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

## 5a. SCOPE — Polymarket only (user, 09-13 22:3x)

*"tokyo server is no longer our thing, nothing related to predict for now on, for now polymarket is the
only thing we should be focusing and that's where the goal applying."* So: the Tokyo v11 engine, the
Predict.fun venue, the Predict.fun re-arm rule and the Tokyo wallet question are **out of scope**. The
re-arm criterion was met at 22:22 (Predict.fun paper +0.140 then +0.478 on the verified source) and was
**deliberately not acted on** — the wallet read 0.00 for eight hours — and is now retired with it. The
fair table's Polymarket paper (v10) and Polymarket v12 lane rows are the comparators; the Predict.fun and
Tokyo rows are reported verbatim and not read. Nothing in this plan depended on Predict.fun: the model is
v10 on Binance features, `candles.actual` is Binance close≥open, and every step above targets the
Polymarket engine on the AWS box.

## 6. Roles

- **V (this session):** owns the plan, the build, the tests, the twin, and every claim in this file.
  *"as the main session, a head session you are responsible for all that."* Accepted.
- **AWS Mumbai:** the live journal, the decision diff, deploys, and post-deploy verification. Given
  measurement and deployment work only — no more speculative tasks.
- **H1:** `verify.py` on the twin result at step 3.
- **The user:** the step-4 go, and every control write on the live engine.

## 7. Deploy procedure — binding from 12.8.5/12.8.6 onward (user, 09-13 23:1x: "not only byte identical but it needs to be proper code")

Byte-identity proves the box has what the branch says. It does not prove the code is right. **A deploy is
not done until every row below is written into `learner/DEPLOYED.md` by the AWS session, with the
evidence, and committed to the branch.** V verifies the commit; nothing is taken on report.

| # | check | proves | evidence AWS commits |
|---|---|---|---|
| 1 | `git rev-parse` of the deployed commit + `sha256sum` of every deployable file **in the running process's cwd** (`/proc/<pid>/cwd`), beside the branch's hashes at that commit | the box has exactly what was reviewed | the hash table, every row |
| 2 | **all three test suites run ON THE BOX**, against the deployed files, with the box's Python and deps | the code works where it runs, not only where it was written | `Ran N tests … OK` × 3, with N |
| 3 | **each new test run against the PREVIOUS build's files** (the `polymarket_v12_backup_*` dir kept on every swap) and shown to **fail** | the test tests the change, not itself | the FAIL/ERROR lines |
| 4 | post-restart state read from `meta` and the venue: build, master, halt, lane flags, stake, cash | the restart came back as intended; no safe-startup surprise | the state table |
| 5 | **the behavioural effect observed in the live journal**, not inferred — e.g. 12.8.2's MAIN row visible; 12.8.3's `LOW_BALANCE` row with `acted:false`; 12.8.4's `clear-halt` audit row carrying `do_POST`; 12.8.5's first `master False→True` row; 12.8.6's one halt row per episode + `AMBIENT_AGE` rows arriving every ~5 s | the change does what it was built to do, in production | the journal rows, quoted |
| 6 | **AWS reads the diff and states disagreement** — anything it thinks is wrong, unclear, or untested, in writing, before the deploy goes live | a second reader on the box, not an echo | its objections, or "none, and here is what I checked" |
| 7 | **downstream rechecked**: every path the change touches (journal, kill rules, dashboard rows, audit, `rolling()`, the reconcile loop) exercised once after restart | the user's rule — "after every change everything should be rechecked, its effects, and all the other things affected" | one line per path with what was seen |

**Rows 1–3 and 6 happen BEFORE the restart. Rows 4, 5, 7 after.** A row that cannot be checked is
written as "cannot check, because …", never skipped.

**Push path (found 23:2x on the first use):** the AWS box has **no git credentials** — `git push` fails
there. So "committed by AWS" means: AWS commits locally and sends the section **verbatim**; V commits it
to the branch **unedited**, with a provenance line naming AWS's local commit. Every future section arrives
the same way until the box has a push path — **a deploy key on the user's server is the user's decision**,
raised and not made. Two rows AWS structurally cannot do from the box: exercising the dashboard endpoints
(401 without `DASHBOARD_PASSWORD`, which it correctly will not use) — evidence for those is the user's own
audited clicks, and the row says so. **V does not mark a build deployed until
`DEPLOYED.md` for it is on the branch and V has read every row.** Deploys stay AWS's job; verifying the
deploy is now a document, not a message.

