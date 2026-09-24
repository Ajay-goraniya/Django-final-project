# DEPLOYED.md — per-build deploy evidence, written by the AWS session (REMAKE_PLAN §7)

> Provenance: authored on the AWS Mumbai box by the AWS session (its local commit 04b6560) and sent to V
> verbatim at 23:2x UTC 09-13 because the box has no git push credentials. Committed to the branch by V
> **unedited**. Any future edit to a build's section must come from the AWS session the same way.

## 12.8.4

Deployed 2026-09-13 19:32:05 UTC on the AWS Mumbai box, `/home/ubuntu/polymarket_v12`, PID 85116, launched with `venv/bin/python btc_model_v12_polymarket.py --live --mode pnl --capital 50`. Written retroactively on 2026-09-13 23:2x UTC (Task 77/§7). The previous build on the box was **12.8.2**, not 12.8.3 — the user stopped the 12.8.3 deploy ("stop, do not deploy 12.8.3 — deploy 12.8.4 instead"), so this deploy carried 12.8.3's change (wipeout guard → monitor-only, `LOW_BALANCE`) and 12.8.4's (clear-halt on the controls page) together. Rows 3, 5 and 7 cover both.

### Row 1 — commit and hashes in the running process's cwd (Task 78, 23:11 UTC)
Commit `6100822c59340dae8b9478cf69bf07303d5f5863`. `/proc/85116/cwd` = `/home/ubuntu/polymarket_v12`. References recomputed from `git show 6100822:learner/v12_2/<file>`.
| file | box sha256[:16] | 6100822 | |
|---|---|---|---|
| btc_model_v12_polymarket.py | ede93a39c77f2688 | ede93a39c77f2688 | OK |
| poly_core.py | d153ba5cf2383a70 | d153ba5cf2383a70 | OK |
| poly_dashboard.py | 82aed14848dc3514 | 82aed14848dc3514 | OK |
| poly_lanes.py | 89c5f058fa9c4484 | 89c5f058fa9c4484 | OK |
| poly_live.py | ea47eee28fe5b217 | ea47eee28fe5b217 | OK |
| poly_feeds.py | 85128b1cbac0f737 | 85128b1cbac0f737 | OK |
| controls_html.html | 6bbe96f76dc5b8bc | 6bbe96f76dc5b8bc | OK |
| dashboard_html.html | b62bff16f72450a0 | b62bff16f72450a0 | OK |
| data_html.html | fa485a443d1fbad4 | fa485a443d1fbad4 | OK |
Every `__pycache__/*.cpython-312.pyc` header (source mtime + size) matches its source on disk; last source mtime 19:30:56, process start 19:32:05. Held 12.8.5 (poly_dashboard f9c25d645cdcea3c) and 12.8.6 (poly_core 0852fb186a37988a, btc_model 2799eecb6baaf9c0) are **not** on the box. Tree diff vs the commit: `V12_2_CHANGES.md` on the box is the older 384-line version (documentation, not imported); `start_live.sh` exists on the box only (relaunch helper). Nothing missing, no local patches.

### Row 2 — all three suites on the box, deployed files, box venv (23:2x UTC)
```
test_polymarket   Ran 59 tests in 0.927s   OK
test_lanes        Ran 21 tests in 0.501s   OK
test_v122         Ran 145 tests in 23.334s OK
```
225 total. Each suite uses `tempfile` databases; the live journal was not opened.

### Row 3 — the new tests against the previous build's files, shown failing
Previous tree = `/home/ubuntu/polymarket_v12_backup_20260913_193204/tree.tar.gz` (taken 1 s before the swap). Its hashes: btc_model 2d224d683032007c, poly_core bcb31acb84a165f4, poly_dashboard 29f31b27e3e88475, controls_html d8718d1149383e7e — i.e. 12.8.2 (poly_core reads `'build','12.8.2'`; no `LOW_BALANCE` in btc_model). 12.8.4's `test_v122.py` copied in and run with the box venv:
```
TheHaltCanBeClearedFromTheControlsPage      Ran 8 tests   FAILED (failures=2, errors=1)
  ERROR test_the_page_is_told_the_halt_exists            KeyError: 'halt'
  FAIL  test_no_halt_reads_as_none_not_missing           'halt' not found in {...controls() dict...}
  FAIL  test_the_page_actually_carries_the_control       '/api/controls/clear-halt' not found in page
LowBalanceIsWatchedNeverActedOn (12.8.3)    Ran 9 tests   FAILED (failures=4, errors=1)
  FAIL  test_a_sustained_low_balance_no_longer_stops_anything
  FAIL  test_it_records_once_per_episode_not_every_five_seconds
  FAIL  test_it_still_records_what_it_saw
  FAIL  test_nothing_else_in_the_engine_halts_on_the_balance
  ERROR test_the_reading_carries_the_money_the_old_rule_could_not_see
```
The remaining 5 + 4 tests in those classes pass on the old tree: they pin behaviour that predates the change (arming under a halt fails, etc.).

### Row 4 — state after restart (read from `meta` and `venue_state`, 23:2x UTC)
| key | value |
|---|---|
| build | 12.8.4 |
| master | true (armed by the user after the restart; safe-start had forced it off) |
| halt | null |
| ef_enabled / main_enabled / reversal_enabled | true / false / false |
| next_stake | 3.0 (user: 1.0→5.0 at 20:22, 5.0→3.0 at 20:23, audited) |
| ev_settings | {"mode":"regime","pad_ticks":1,"slippage_mode":"band"} |
| venue cash / open_value / portfolio_value | 33.959 / 4.341 / 4.341 (venue_state 23:17 UTC) |
| venue realized_pnl (detail, since 23:00 window) | −26.83, fees −5.10, 40 trades, volume 140.20 |

### Row 5 — behavioural effect observed in the live journal
12.8.4, the clear-halt audit row, 19:32:58 UTC, 53 s after the restart, with the `do_POST` stack:
```
{"reason": "control_write", "key": "halt",
 "old": "Account wiped out: spendable 2.06 below stake 5.00 on 3 consecutive balance reads",
 "new": null,
 "stack": ["server.py:436 handle", "server.py:424 handle_one_request",
           "poly_dashboard.py:585 do_POST", "poly_dashboard.py:294 apply"]}
```
paired with `halt_cleared_at 1789315950.02 → 1789327978.28` at the same second, same stack.
12.8.3 (carried in this deploy), 20:21:53 UTC:
```
{"kind": "LOW_BALANCE", "spendable": 1.9149, "stake": 5.0, "open_value": 0.0,
 "equity": 1.9149, "reads": 3, "acted": false}
```
one row for the episode, `acted:false`, `halt` stayed null through it.

### Row 6 — AWS's reading of the diff (6100822 vs 6100822~1)
None. What I checked: `controls()` adds `halt=self.db.get('halt')` and nothing else; `apply` is unchanged (still refuses to arm master while halt is set — line 294 in the stack above is that path); `/api/controls/clear-halt` existed since 12.4.1 and the page now echoes `acknowledge` from state, which is the only way the exact-match check can pass; master is deliberately not armed by the clear; build string bumped in `poly_core.py`. Two things I would note, neither a defect in this diff: (a) arming master through `apply` is not audited in 12.8.4 — the 20:2x audit shows `next_stake` writes but no `master False→True` row for the user's arm; that is 12.8.5's fix, held; (b) `halt_check` writes the halt every reconcile pass while below −3 (2,035 audit rows on 09-13) — 12.8.6's fix, held.

### Row 7 — downstream rechecked after restart
- journal: 25 orders since restart (10 FILLED / 15 REJECTED), 9 results settled, 39 `candle_attempts` rows — the reconcile loop is grading and releasing normally.
- kill rules / `rolling()`: `kill_window()` counts from `halt_cleared_at` 19:32:58 — 9 results in the window, sum −2.9274 unit, engine rule needs 20; `halt` still null, consistent.
- audit: control writes since restart are all stacked through `do_POST` (clear-halt, halt_cleared_at, three next_stake writes) — the user's actions, nothing from the engine.
- controls page / `controls()` / `apply`: **cannot exercise from here** — every dashboard endpoint answers 401 without `DASHBOARD_PASSWORD`, which I will not use. Evidence is the user's own use: the clear at 19:32:58 (`apply` line 294) and the stake changes at 20:22–20:23 (`apply` line 270).
- dashboard rows: cannot (same 401). Not inferred.

## 12.8.8

Deployed 2026-09-14 00:54:14 UTC on the AWS Mumbai box, `/home/ubuntu/polymarket_v12`, PID **93377**
(was 85116), `venv/bin/python btc_model_v12_polymarket.py --live --mode pnl --capital 50`. Carries
**12.8.5 + 12.8.6 + 12.8.8** from commit `72dca5f`. **Not 12.8.7** — its four attempt-loop hunks are
reverted to 12.8.6's text at this commit and preserved in `learner/v12_2/held/12.8.7_attempt_loop.patch`;
`RETRY_DELAY_S`, `if q: break`, `if not latest: continue` and the 75 ms sleep are absent from the
deployed `poly_core.py`, and `AttemptLoopIsPaperParity` does not exist in either test module (grep: 0/0).
Deploy window: master was off since 23:55:41 by the user's own click; **the deploy did not arm it**.

### Row 1 — commit and hashes in the running process's cwd

Commit `72dca5f`. `/proc/93377/cwd` = `/home/ubuntu/polymarket_v12`, started 00:54:14 UTC.
`rm -rf __pycache__` ran between the file swap and the start (wrapper printed `pycache removed: True`).

| file | box sha256[:16] | 72dca5f | |
|---|---|---|---|
| btc_model_v12_polymarket.py | 2799eecb6baaf9c0 | 2799eecb6baaf9c0 | OK |
| poly_core.py | 5ae4e926ad655321 | 5ae4e926ad655321 | OK |
| poly_dashboard.py | aafe0d8ad9c7ebcd | aafe0d8ad9c7ebcd | OK |
| poly_lanes.py | 89c5f058fa9c4484 | 89c5f058fa9c4484 | OK |
| poly_live.py | ea47eee28fe5b217 | ea47eee28fe5b217 | OK |
| poly_feeds.py | 85128b1cbac0f737 | 85128b1cbac0f737 | OK |
| controls_html.html | 6bbe96f76dc5b8bc | 6bbe96f76dc5b8bc | OK |
| dashboard_html.html | b62bff16f72450a0 | b62bff16f72450a0 | OK |
| data_html.html | fa485a443d1fbad4 | fa485a443d1fbad4 | OK |

Every regenerated `__pycache__/*.cpython-312.pyc` header (source mtime + size) matches its source
(poly_core, poly_dashboard, poly_feeds, poly_lanes, poly_live, btc_model_v10, btc_model_v10_runner).
Tree diff vs the commit: the only file on the box that is not at `72dca5f` is `start_live.sh` (my
relaunch helper, never on the branch). `V12_2_CHANGES.md` and `SHA256SUMS.txt` were also swapped, so
the documentation drift noted under 12.8.4 is gone. Backup of the previous tree and an online sqlite
backup: `/home/ubuntu/polymarket_v12_backup_20260914_005414/`.

### Row 2 — all three suites, staged `72dca5f`, box venv, before the restart

```
test_polymarket   Ran 64 tests in 0.963s    OK
test_lanes        Ran 21 tests in 0.545s    OK
test_v122         Ran 157 tests in 26.228s  OK
```
242 total, matching Task 82a's expectation. `tempfile` databases throughout; the live journal was not
opened.

### Row 3 — the new tests against the previous build's files, shown failing

Previous tree = a fresh `tar` of the running 12.8.4 cwd taken before the swap (`'build','12.8.4'`
confirmed in its `poly_core.py`), `72dca5f`'s three test modules copied in, box venv:

```
test_v122.ArmingMasterIsAudited          Ran 7 tests   FAILED (failures=3, errors=1)
  ERROR test_the_row_names_the_caller_not_the_journal
  FAIL  test_arming_master_leaves_an_audit_row
  FAIL  test_disarming_is_still_audited
  FAIL  test_no_raw_meta_writes_are_left_in_the_dashboard
test_v122.AmbientBookAgeIsSampled        Ran 5 tests   FAILED (failures=1, errors=4)
  ERROR test_one_row_with_both_tokens_ages
  ERROR test_a_token_with_no_book_yet_is_null_not_an_error
  ERROR test_no_market_for_the_epoch_writes_nothing
  ERROR test_it_cannot_raise_into_housekeeping
  FAIL  test_housekeeping_calls_it
test_polymarket.PnLConditionsNeverHalt   Ran 5 tests   FAILED (failures=4)
  FAIL  test_both_conditions_true_and_the_engine_does_not_stop
  FAIL  test_each_condition_is_reported_once_per_episode_with_its_number
  FAIL  test_the_only_engine_halt_left_is_the_order_identity_stop
  FAIL  test_the_report_is_per_process_episode_and_a_recovery_re_arms_it
  (the display test passes on both, as expected)
the three inverted tests                 Ran 3 tests   FAILED (failures=3)
  FAIL  test_kill_rule_is_per_lane_not_blended
  FAIL  test_clearing_a_halt_actually_restarts_trading
  FAIL  test_what_the_rule_enforces_is_what_the_screen_shows
```

### Row 4 — state after restart (`meta` and `venue_state`, 00:55 UTC)

| key | value |
|---|---|
| build | 12.8.8 |
| lane | LIVE |
| **master** | **false — untouched by the deploy, and not armed by me** |
| halt | null |
| ef_enabled / main_enabled / reversal_enabled | true / false / false |
| next_stake | 3.0 |
| stake_settings | mode fixed, fixed_stake 3.0, min 1.0, max 50.0 |
| ev_settings | {"mode":"regime","pad_ticks":1,"slippage_mode":"band"} (not rewritten this deploy) |
| halt_cleared_at | 1789327978.281314 (19:32:58, unchanged) |
| venue cash / open_value / portfolio_value | 37.529 / 0.00 / 0.00 |
| open positions | none |

### Row 5 — behavioural effect observed in the live journal

**12.8.6 — `AMBIENT_AGE`.** 11 rows in the first ~10 minutes, one per housekeeping tick (~6 s), e.g.
```
00:55:17 ep=1789347300 {"kind": "AMBIENT_AGE", "age_up_ms": 18.6, "age_dn_ms": 18.6}
00:55:11 ep=1789347300 {"kind": "AMBIENT_AGE", "age_up_ms": 32.5, "age_dn_ms": 32.5}
00:55:05 ep=1789347300 {"kind": "AMBIENT_AGE", "age_up_ms": 24.3, "age_dn_ms": 24.3}
```
First reading of the number Task 75 needs: ambient book age is tens of milliseconds, well under the
88.0 ms filled / 174.8 ms rejected submit-time `age_ms`. Not enough rows to answer 75 yet; that is a
later report, not this one.

**12.8.8 — the PnL kill is out.** `KILL_CONDITION` rows: **0**, which is the correct result — the
`kill_window()` since `halt_cleared_at` holds **13** results and every condition needs 20. `halt` is
null. Verified directly against the deployed module on a copy of the journal (never the live file):
`inspect.getsource(Journal.halt_check)` contains **0** occurrences of `set('halt'` and 2 of
`KILL_CONDITION`; calling `halt_check()` on that copy left `halt` None and wrote no row. The only
`set('halt'` left in the deployed `poly_core.py` is line 985, the order-identity stop
("Order hash mismatch; reconcile before resuming"); `poly_dashboard.py`'s single occurrence is the
operator's clear-halt endpoint setting it to None.

**12.8.5 — arming audited.** No `control_write` row since the restart, and that is correct: safe-start
writes `master=False` over a value that was already False, and `_audit` only records when `old != v`.
The first row will be the user's next control action. **Cannot show a `master False→True` row yet** —
nobody has armed master since the deploy, and I will not.

### Row 6 — AWS's reading of `git diff 6100822 72dca5f -- learner/v12_2/` (stated before Row 1)

**One objection, raised before the deploy and acted on:** the first commit Task 82 named (`24d28a7`)
contained 12.8.7 — `git merge-base --is-ancestor 5dbb8fa 24d28a7` was true and `RETRY_DELAY_S` /
`if q: break` / `if not latest: continue` / the 75 ms sleep were in its `poly_core.py`. I held the
deploy and asked for a commit without it; `72dca5f` is that commit and I re-ran Rows 2, 3 and 6
against it. Nothing was deployed from `24d28a7`.

On the remainder, no objection. What I checked: `_audit` uses `extract_stack()[:-2]` so the recorded
frame is the caller of `set`/`set_many`, which is what `test_the_row_names_the_caller_not_the_journal`
pins; `set_many` keeps the single-transaction write and adds the audit the bare
`INSERT OR REPLACE` bypassed; `halt_check` still computes SLIPPAGE / ALL / per-lane and writes one
`KILL_CONDITION` per rule per episode with `_kill_reported` cleared when a condition recovers
(`_kill_reported` initialised at `poly_core.py:358`, per process, so a restart re-arms the report);
`_sample_ambient_age` reads `books.books[token]['arrival']` directly rather than through `quote()`,
so the 2 s staleness filter cannot hide the tail, and swallows every exception; `apply` calls
`set_many` in both branches. **One note, already accepted by V and deferred:** `set_many` audits
before the transaction commits, so a failed transaction would leave an audit row for a write that did
not land.

### Row 7 — downstream rechecked after restart

- **reconcile / grade / release:** 48 results, 0 filled orders without a result, 6 candle rows written
  since the restart. No orders or signals since the restart — correct, master is off.
- **decide path:** 83 decide rows and 58 `decide` diagnostics in the first ten minutes; the engine is
  evaluating every candle with master off, as designed. Also present: 223 `feed_counters`, 16
  "Waiting for fresh UP and DOWN books" (startup), 4 "outside decision window".
- **`rolling()` display unchanged:** called on a journal copy with the deployed module —
  `keys = ['all','by_kind','kill','mixed_epochs']`, and
  `kill = {'unit_return_sum': None, 'unit_return_limit': -3.0, 'results_until_armed': 7,
  'armed': False, 'by_kind': {'EF': {'n': 13, ...}}}`. The screen still shows the rule; the engine no
  longer acts on it.
- **audit:** zero `control_write` rows since the restart (see Row 5). Every earlier row is stacked
  through `do_POST`.
- **dashboard pages:** **cannot check** — `/`, `/controls` and `/api/state` all answer 401 without
  `DASHBOARD_PASSWORD`, which I will not use. The HTTP server is up and answering (401 is a served
  response, and the log line `Polymarket v12.1 LIVE (master OFF) http://0.0.0.0:8787` is from this
  process).
- **engine.log:** the only tracebacks are `ConnectionResetError` on the HTTP socket, all written
  before the restart line; nothing since.

## 12.8.9

> AWS-authored summary (cross-session message 11:3x UTC 09-14), committed unedited by V. The full seven-row
> write-up is on the box at the AWS session's scratchpad `DEPLOYED_12.8.9.md`; not pasted into chat (token rule).

12.8.9 LIVE from 7457816. PID 98942, started 11:31:56 UTC. MASTER IS OFF — safe-start forced it, I did not re-arm; the user must click it or the fill-rate measurement cannot start.
Row 6 (read first, no objection): the diff is exactly RETRY_DELAY_S=0.075, `if q: break`, `if not latest: continue`, the 75 ms sleep, plus the build string. order_plan(latest) re-check still releases EV_CHANGED. Note: signed cap comes from q, so a book that moves up between sign and submit now gives a cheap FAK reject instead of a wait — intended, matches paper.
Row 1: all nine hashes = 7457816 (poly_core 26800c7ec67b7213, test_polymarket 8869082f51571921 as you gave). __pycache__ removed pre-start, 0 pyc header mismatches. Backup /home/ubuntu/polymarket_v12_backup_20260914_113125/.
Row 2: 68 + 21 + 157 = 246, all OK.
Row 3 vs the running 12.8.8 tree: AttemptLoopIsPaperParity Ran 4, FAILED (failures=4) — the four you named.
Row 4: build 12.8.9, master false, halt null, ef true, main/rev false, stake 3.0, ev {regime, pad 1, band}; cash 54.09, open 0.00, no position.
Row 5: attempt-loop effect NOT observable yet — no submissions since master went off. AMBIENT_AGE flowing (7 rows/2 min), KILL_CONDITION still 0.
Row 7: 29 results and 67 orders (29F/37R/1U) carried across; decide path alive; one audit row since restart — safe-start master true→false, stacked to btc_model:52 __init__.
Final 12.8.8 numbers for the comparison baseline: 29 results, 16W/13L, +19.77, unit +6.900; fill rate 29/66 = 43.9% on that build.

## 12.8.10

Deployed 2026-09-14 23:16:04 UTC, `/home/ubuntu/polymarket_v12`, PID 109303 (was 108430), commit `771bc87`.
Observation only: `WAIT_CENSUS`. Stopped 23:15:34 with 0 open positions and 0 orders in flight.

### Row 6 — read before Row 1, no objection
`git diff 7457816 771bc87` on the two changed modules is: `BookCache.block_detail[t]=(reason,age)` set on each
refusal path in `quote()` (no_book/no_asks/no_bids/stale/crossed) and popped on success; `self._wait_census={}`
and `_wait_flushed` in the runner's `__init__`; `_count_wait(toks,quotes)` called from `publish()` on refusal and
an `ok` counter on success; `_flush_wait_census(ep)` from housekeeping writing one `WAIT_CENSUS` diagnostics row a
minute; `WAIT_BUCKETS` (<0.75 / 0.75-1 / 1-2 / 2-5 / 5+); build string 12.8.9 → 12.8.10. Nothing in the decision or
order path changes and both new methods swallow every exception.

### Row 1 — hashes in the running process's cwd
All nine files equal `git show 771bc87:learner/v12_2/<f>`: btc_model 177dfdf1ab6ea20f, poly_core d1b2e423776e2a2b,
poly_dashboard aafe0d8ad9c7ebcd, poly_lanes 89c5f058fa9c4484, poly_live ea47eee28fe5b217, poly_feeds 85128b1cbac0f737,
controls_html 6bbe96f76dc5b8bc, dashboard_html b62bff16f72450a0, data_html fa485a443d1fbad4.
`rm -rf __pycache__` ran before the start; every regenerated pyc header matches its source (0 mismatches).
cmdline: `venv/bin/python btc_model_v12_polymarket.py --live --mode pnl --capital 50 --host 0.0.0.0 --port 8787
--db polymarket_v12_live_8787.sqlite3 --quote-age-ms 2000`. Backup: /home/ubuntu/polymarket_v12_backup_20260914_231534/.

### Row 2 — three suites, staged 771bc87, box venv, before the restart
test_polymarket Ran 68 OK; test_lanes Ran 21 OK; test_v122 Ran 163 OK = 252.

### Row 3 — the new class against the running 12.8.9 tree
`test_v122.WaitCensusSaysWhichBookBlockedAndHowOld`: Ran 6, FAILED (failures=3, errors=2) —
ERROR test_housekeeping_writes_one_row_a_minute_and_resets, ERROR test_quote_leaves_the_reason_and_age_per_token,
FAIL test_ok_publishes_are_counted_too, FAIL test_publish_counts_side_reason_bucket,
FAIL test_stale_is_bucketed_by_the_age_quote_judged.

### Row 4 — state after restart
build 12.8.10, lane LIVE, master false (safe-start; not armed by the deploy), halt null, ef true, main/rev false,
stake 3.0, ev_settings {"mode":"regime","pad_ticks":1,"slippage_mode":"band","quote_age_ms":750.0} preserved.
Journal carried across: 135 orders / 54 fills / 54 results.
The user armed master at 23:17:13 (audit stack server.py → poly_dashboard do_POST → apply); I set it back to false at
23:47:5x on V's Zurich-cutover instruction (audit stack `<stdin>:10 <module>`, my write, flagged as such).

### Row 5 — behavioural effect, the census itself
65 `WAIT_CENSUS` rows covering 4,050 s (67.5 min), one a minute as designed. Summed:
publish() ok 1,495,108, blocked 324,908, no_market 1 → **17.9% of publishes blocked**.
By side: UP 162,428 / DOWN 162,480 — symmetric to 0.03%, so it is not one side's book.
By reason: no_bids 113,092, no_asks 113,092, stale 96,958, crossed 1,762, no_book 4.
By age bucket: <0.75 s 227,866 (70.1%), 2-5 s 92,532 (28.5%), 5+ s 4,426 (1.4%), 0.75-1 s 60, 1-2 s 20, n/a 4.
Top cells: UP:no_bids:<0.75 and DOWN:no_asks:<0.75 at 77,896 each (24.0%); UP/DOWN:stale:2-5 at 46,266 each (14.2%);
UP:no_asks:<0.75 and DOWN:no_bids:<0.75 at 35,168 each (10.8%).
**The answer to "why 34.7% waiting": 70% of blocked publishes are on a book younger than 0.75 s that has an empty
side — one-sided books, not staleness.** no_bids and no_asks are exactly equal (113,092 each), which is the signature
of the two tokens of a pair being complementary: when UP has no bids, DOWN has no asks. Only 28.5% is genuine
staleness, and it sits in the 2-5 s bucket, i.e. beyond the old 0.75 s bar and beyond the new 2 s one.

### Row 7 — downstream
Journal writing throughout; 56 results / 135+ orders carried; decide path alive; no KILL_CONDITION; no halt.
Dashboard not exercised (401 without DASHBOARD_PASSWORD). engine.log clean after the start line.

### Phase split (AWS, 00:2x, appended by V from AWS's follow-up message, not part of the section above)
Decision window 15-240 s: ok 1,214,100, blocked 152,223 = 11.1%; one-sided 87,590 = 57.5% of those blocks.
Tail: 33.9% blocked, one-sided 80.2%. The 60-120 s phase is the clean one (3.2% blocked).

## 12.8.11 (Zurich box, fresh journal) — written by the Zurich session

Deployed 2026-09-15 02:06:04 UTC on the Zurich box (eu-central-2), `/home/ubuntu/pm_paper_zurich`, PID 15581, argv `.venv/bin/python -u btc_model_v12_polymarket.py --live --mode pnl --capital 50 --host 0.0.0.0 --port 8787 --db polymarket_v12_live_zurich_2.sqlite3 --quote-age-ms 2000`. Previous: 12.8.9 (7457816) PID 8347, stopped 02:04:59 at a clean moment (0 SUBMITTING/PENDING, open_value 0, no signal, 275 s into the candle). Old journal `polymarket_v12_live_zurich.sqlite3` (2,084,864 B, 02:04) left untouched as the record; the stuck UNKNOWN ...64f7d150 stays in it. User chose "reset everything" -> fresh journal.

Row 6 (read first): `git diff 7457816 2cf8b6d -- poly_live.py poly_core.py` is exactly the Z-5 brief - `ABSENT_PROOF=3`, `ABSENT_PROOF_AGE_S=60`; `if fills:` hoisted above the get_order-error branch; that branch -> `verified_no_fill` when venue_absent>=3, age>=60 s, no trade, nothing unsettled, else unchanged; `Executor._stuck_reported=set()`; one `RECONCILE_STUCK` diagnostics row per (id, class, message[:40]); build 12.8.9 -> 12.8.11. Also carries 12.8.10 (Mumbai): `BookCache.block_detail` and `WAIT_CENSUS` counting in btc_model (+29, try/except, diagnostics only). Nothing in decide, fire or pricing. No objection.
Row 1: commit 2cf8b6d. SHA256SUMS 30/30 OK in the deploy dir; all 30 files byte-equal to `git show 2cf8b6d:learner/v12_2/<f>`. poly_live ce8c900c58d42faa, poly_core fcce9c829fcef04a, test_polymarket 19ea11ca9b33d244, btc_model_v12_polymarket 177dfdf1ab6ea20f. `rm -rf __pycache__` before start (verified none after the suites).
Row 2: three suites in the deploy dir, box venv (pytest): 71 + 21 + 163 = 255 passed.
Row 3: `LiveBrokerSimulationTests.test_unreadable_get_order_resolves_on_repeated_venue_absence`, `.test_unreadable_get_order_still_takes_a_confirmed_trade`, `Tests.test_stuck_reconcile_is_recorded_once_not_every_second` against the RUNNING 12.8.9 modules: 3 failed. Against staged 12.8.11: 3 passed.
Row 4 (state after restart, `meta` + `venue_state`, 02:07:44): build 12.8.11, lane LIVE, model_hash 1538782f…458c5 (same as old db). Safe-start wrote master None -> False 02:06:06. **Master True since 02:06:20 - armed by the USER on the dashboard (`poly_dashboard.py:591 do_POST`), not by this session.** stake_settings fixed 3.0 / next_stake 3.0 (user, do_POST 02:06:51). ev_settings {quote_age_ms: 750.0} (this session, Journal.set_many 02:06:57, audit old None). ef true, main/rev false, halt null. Venue cash 61.6186, open 0.0. Orders 0, results 0, signals 0.
   Caveat on record: 02:06:20-02:06:51 the engine was armed on ladder mode with next_stake alternating 1 <-> 5 (housekeeping ladder vs the user's edits); orders 0 at 02:06:49, so nothing fired in that window.
Row 5 (behavioural effect): NOT observable on the fresh journal - the patient (UNKNOWN ...64f7d150) is in the old db, and the new db has no UNKNOWN row. The 12.8.11 path is proven by Row 3 only. 12.8.10's census IS live: first `WAIT_CENSUS` row written within 100 s of start.
Row 7 (downstream, 100 s after start): AMBIENT_AGE flowing (19 rows, age_up/dn 41.0 ms); feed_counters applied 33,368, dropped_stale 0; venue_truth 5 rows (cash 61.6186); decide path alive (7 rows: 6 warm-up, 1 "Waiting for fresh UP and DOWN books"); candles seeded 287. Dashboard on 0.0.0.0:8787, HTTP Basic.

## 12.9.0 (Zurich box) — written by the Zurich session

Deployed 2026-09-15 17:31:16 UTC on the Zurich box, `/home/ubuntu/pm_paper_zurich`, PID 72358, same argv as 12.8.11 (`--live --mode pnl --capital 50 --host 0.0.0.0 --port 8787 --db polymarket_v12_live_zurich_2.sqlite3 --quote-age-ms 2000`), same journal. Previous 12.8.11 PID 15581 stopped 17:31:17 at a clean moment (17:31:12: 0 in flight, 0 ungraded fills, open_value 0, no signal, 72 s into the candle). User's go 17:2x (Z-6).

Row 6 (read first): `git diff 2cf8b6d 76d9eb6 -- learner/v12_2/` = plan_12_9.md items 1-7 exactly: (1) `Executor.POST_FLOOR_S=0.4`, BUDGET release + `NO_ORDER_SENT`; (2) `FeatureState._arrays()` cache keyed on `_rev`/lengths, `cache=False` reference path; (3) `poly_live.run_sync`/`sign_off_loop`, `TrackedClient._sign_order` signs + re-hashes in a thread, identity check unchanged; (4) `diagnostics_ts` index, `_due()` cadence 60 s monitors / 3600 s retention, `halt_check(every_s)`; (5) `publish()` on `quote_age_s()`, gate `require_depth=executor.require_depth`; (6) `exchange_latency_ms` from event_lag, page 1 s poll, "since last trade"; (7) `PaperBroker.account_snapshot`/`BookCache.clear` removed, `--mode` SUPPRESS, runner header. Nothing in decide, EV, pad, threshold or execution shape. No objection.
Row 1: commit 76d9eb6. Staged then deployed; SHA256SUMS 30/30 OK in the deploy dir, all 30 byte-equal to `git show 76d9eb6`. poly_core 052a27f42920f1d5, poly_live 9a610231994f204c, btc_model_v12_polymarket 63a6b8716bde387b, btc_model_v10 c1415a73b79ef34e, poly_dashboard 20d6cffc4a613971, test_v122 368d1226196f2bce. `__pycache__` removed before start.
Row 2: three suites on the staged tree, box venv (pytest): 71 + 21 + 188 = 280 passed.
Row 3: the 25 new 12.9.0 tests against the RUNNING 12.8.11 modules: 22 failed, 3 passed (`test_above_the_floor_still_posts`, `test_sdk_sign_order_awaits_nothing`, `test_main_oneshot_returns_at_once_when_main_is_off` - pins by design). Against staged: 25 passed.
Row 4 (state after restart, `meta`, 17:31:48): build 12.9.0, **master False** (safe-start audit 17:31:26 True -> False, `__init__`), halt null, stake_settings fixed 5.0 / next_stake 5.0, ev_settings {quote_age_ms: 750.0}, ef true, main/rev false - all carried over unchanged. `diagnostics_ts` index created. 0 orders since restart. Master stays OFF for the user to arm.
Row 5 (behavioural effect, user armed 17:34:11 via dashboard `apply`): first live order ...d4e1b885 at 17:51:37, REJECTED (venue "no orders found to match"), order-identity check passed, halt null, fire_to_submit_ms **41** (12.8.11 median 50), network_roundtrip 359, total 408, post_budget_left 1958 ms (floor 400 not reached, 0 BUDGET releases). One RECONCILE_STUCK row for it on its first reconcile pass: `get_order` UnexpectedResponseError "OpenOrder response did not match expected shape" (the Z-4 SDK error, now recorded once as designed); the order still went terminal. KILL_CONDITION x2 at 17:31:27 = the watch-only monitor re-reporting the pre-restart 20-result window (unit_sum -5.23 vs limit -3.0, acted=false). Second order ...f268d9f5 at 18:08:52, **FILLED** (venue MATCHED), identity check passed, halt null, fire_to_submit_ms **23**, network_roundtrip 247, total 276, post_budget_left 1977. No second RECONCILE_STUCK row. Watch complete: 2/2 terminal, 0 UNKNOWN, 0 halts, fire_to_submit 41 / 23 ms vs the 12.8.11 median 50.
Row 7 (downstream, 17:42-18:02): AMBIENT_AGE flowing (124 rows/10 min, p50 24.5 ms); feed_counters applied 362,945, dropped_stale 0; decide path alive (122 rows); venue_truth updating (cash 99.50, open 0); results grading (46 -> 48 across the restart). Dashboard 0.0.0.0:8787 Basic auth.

## 12.10.0 (Zurich box) — written by the Zurich session

Deployed 2026-09-16 01:56:16 UTC on the Zurich box, `/home/ubuntu/pm_paper_zurich`, PID 85741, same argv and same journal as 12.9.0 (`--live --mode pnl --capital 50 --host 0.0.0.0 --port 8787 --db polymarket_v12_live_zurich_2.sqlite3 --quote-age-ms 2000`). Previous 12.9.0 PID 72358 stopped 01:56:12 at a clean moment (01:56:08: 0 in flight, 0 ungraded fills, open_value 0, no signal, 68 s into the candle). Z-8, on the user's explicit "deploy".

**Deviation from the brief, on record:** Z-8 said master was OFF. It was not — the user turned it off 00:49:25 and back ON at 01:19:27 (`do_POST`/`apply`), and it traded after that (FILLED 01:26:17, REJECTED 01:46:35 / 01:47:31 x2). I held the deploy and reported (85a92e2); the user answered "deploy". Safe-start therefore disarmed an armed engine: master parked False at 01:56:24. **Not re-armed by me** — the 03:00 trigger or the user does that.

Row 6 (read first): `git diff 76d9eb6 64ed3bb -- learner/v12_2/` touches two non-test files. `btc_model_v10.py`: new `FeatureState._twap()` static method (time-weighted spot over a window) and three keys added to the `features()` dict — `ref_open_bps`, `ref_move_bps`, `ref_gap_bps` (R-16 settlement-reference proxy). `poly_core.py`: build string only. **Verified logging-only against the artifact, not the comment:** `FEATURES` is the same 30 names, and the model consumes `x = np.array([f[k] for k in FEATURES])` (btc_model_v10:264), so extra dict keys cannot reach the weights. `/api/state.feature_names` reads 30 after the restart. Decisions identical to 12.9.0. No objection.
Row 1: commit 64ed3bb. SHA256SUMS 30/30 OK in the deploy dir, all 30 byte-equal to `git show 64ed3bb:learner/v12_2/<f>`. poly_core 0d381a5a4983a6f5, btc_model_v10 06ce156192c65c73, test_polymarket f23277a5cb8cf253, test_v122 cfb2dab1f3b337dc; poly_live 9a610231994f204c and btc_model_v12_polymarket 63a6b8716bde387b unchanged from 12.9.0. `rm -rf __pycache__` before start.
Row 2: three suites on the staged tree, box venv (pytest): 71 + 21 + 190 = **282** passed.
Row 3: not applicable as a fail-on-old — the brief names no new-test list and the change is additive logging; the 12.10.0 suite delta is +2 tests over 12.9.0's 280, both in `test_v122.py`, passing on staged.
Row 4 (state after restart, `meta` + `/api/state`, 01:57): build **12.10.0**, master **false** (safe-start), halt null, next_stake 3.0, stake streak 5% — all carried over. `/api/state` exposes no build field (the brief expected one); the journal `meta.build` is the authority and reads 12.10.0. Venue cash 48.70, open 0.00. results n=77 W35/L42 −0.66 across the restart.
Row 5 (behavioural effect): first decision row after warm-up, **02:06:28**, carries the new keys — `ref_open_bps 0.97, ref_move_bps 3.01, ref_gap_bps 2.51`, alongside `move_bps 1.54`; 38 feature keys in the row vs 35 on 12.9.0. `fire` false (master off). No orders since the restart — master has not been armed.
Row 7 (downstream, 01:56-02:07): decide path alive and logging the new keys; feed counters and AMBIENT_AGE flowing; venue_truth updating (cash 48.70); grading unchanged (n=77 either side of the restart); halt null; 0 UNKNOWN.

## 12.11.0 (staged 09-16 02:2x UTC) - the settlement reference as a first-class feed
poly_feeds: `ref` stream = wss://ws-live-data.polymarket.com (public, no credentials), subscribe frame
topic crypto_prices_chainlink; run_stream gained `subscribe=`; ARRIVAL_LIMITS ref 5 s. Engine: `_ref_stream()` +
`ref_samples()` (loose parser; chainlink full_accuracy_value 1e18 fixed point per Task 100; any format change
degrades to ref_src=0, never an exception) -> FeatureState.on_ref_price. FeatureState: r_ts/r_px buffer, `_ref_twap`;
ref_open/ref_now come from the venue feed when it covers the window (ref_src=1) else the Binance proxy (ref_src=0).
NEW model flag `open_reference` ("first_trade" default = v10 as trained; "twap60" = every open-relative feature
measured from the settlement line); Model.decide copies it into the state so train == serve. With model_v10.json the
model vector is unchanged from 12.9.0 (parity smoke-tested). Tests 71+21+197 = 289 green; SHA256SUMS 30/30.
Deploy: paper first (Mumbai Task 99 -> 12.11.0); Zurich after Z-8 settles, master state untouched.

## 12.11.1 (09-16 02:0x UTC) - the feed IS the settlement quantity; json-owned feature list
Correction to 12.11.0: the venue feed publishes Chainlink's 60 s TWAP itself, so the line at the open is the feed's
value AT the open (`_ref_at`) and the line now is its latest value - not a TWAP of the feed (REF_IS_TWAP=0 env
restores averaging for a raw-price topic). Model json now owns its `features` list (FEATURES + EXTRA_FEATURES =
ref_open_bps/ref_move_bps/ref_gap_bps/ref_src allowed; every name checked at load). model_v10.json unchanged ->
decisions identical to 12.9.0. Tests 71+21+199 = 291; SHA256SUMS 30/30. Supersedes 12.11.0 for Task 99 / Z-8b.

## 12.11.2 (09-16 02:4x UTC) - fix: a blank frame is not a dead socket
Zurich found the ref stream dead at 591 reconnects (~35/min, zero data): the venue's RTDS sends an EMPTY frame as its
subscribe ack and run_stream's json.loads raised, which the reconnect handler treated as a broken connection. Now a
blank frame is skipped and a non-JSON frame is counted in health.skipped_frames instead of reconnecting; the stall
timer still force-reconnects a genuinely silent stream. No other behaviour changes; decisions unchanged
(model_v10.json, 30 features). Tests 71+21+200 = 292; SHA256SUMS 30/30.

## 12.11.3 (09-16 02:5x UTC) - dashboard top line says what the numbers are
User: the "1429 ms since last trade" line reads like a fault. It was trade SILENCE, added in 12.9.0 by V. Now the line
leads with the real feed lag (local receipt minus Binance event time, the number that says whether data is late) and
prints silence in seconds: "LIVE · lag 112 ms · quiet 1.4 s". Dashboard only; no engine behaviour, no decisions.
Tests 71+21+201 = 293; SHA256SUMS 30/30.

## 12.12.0 (09-16 03:3x UTC) - the owner's bankroll floor: EF off below it
USER ORDER: "ef off if bankroll goes below 30$ in central 2". New meta control `ef_cash_floor` (audited; absent =
no behaviour, so paper and every other box are unaffected until it is set). `PolyRunner._floor_check`, on the 60 s
monitor cadence: acts on EQUITY = spendable cash + venue_state.open_value (never bare cash - the 09-13 halt of a
solvent account is documented in _wipeout_check and this is built not to repeat it), does nothing when open_value is
unknown, and requires 6 reads AND >=360 s below the floor (longer than one settlement cycle) before it acts. It sets
`ef_enabled` false only: master, the other lanes and halt are untouched, and it never re-enables itself - that is the
owner's call from the dashboard. Writes one EF_FLOOR diagnostics row with equity, cash, open_value, reads, held_s.
Tests 71+21+206 = 298; SHA256SUMS 30/30. Deploy: Zurich sets ef_cash_floor=30 after the restart.

## 12.12.2 (09-16 08:4x UTC) - a disarmed live engine says so
09-16: the 12.12.1 deploy parked master OFF by safe-start (correct) and the re-arm waited on a permission prompt for
4 h 02 m. 962 decide rows, 4 fires the model wanted and could not send, and nothing anywhere reported it - the engine
was healthy, which is exactly why the silence held. `PolyRunner._master_watch` on the 60 s monitor cadence: when a
LIVE engine has master false for >300 s it writes a MASTER_OFF diagnostics row (off_s, fires_gated) and prints, then
repeats at most every 30 min; the dashboard controls payload gains `master_off_s`. Observation only - it never arms
anything, master stays the operator's. Paper engines and an armed engine are silent. Tests 71+21+210 = 302;
SHA256SUMS 30/30.

## 12.13.0 (09-16 10:3x UTC) - the R-23 arm: a json may decide on the venue price instead of the model
R-23 measured the EV rule with p = the venue's own price: 547 fires, +0.296/$1, +161.93, maxDD 13.45, against frozen
v10's 1,033 fires, +0.141/$1, +145.81, maxDD 14.09 - more money on half the fires at a lower drawdown, consistent
with R-13/R-18/R-19 (we are paid for a lagging book, not a forecast). New model-json field `p_source` ("model"
default, "venue"), read in Model.p_up; with "venue" the probability is the clipped p_venue and a candle without a
two-sided book returns NaN, which decide() now refuses explicitly ("no venue probability for this candle") instead of
guessing. `model_venue.json` is model_v10.json with that one field changed - same features, same coefficients,
byte-identical otherwise - so the two arms differ in exactly one thing. PAPER ONLY: no live engine loads it, and
model_v10.json is untouched. Tests 71+21+213 = 305; SHA256SUMS 31/31 (the new json is in the manifest).
CAVEAT that ships with it: R-23's halves are +0.493/+0.100 and the per-day edge decays +0.573 -> +0.077 across
09-09..09-15. That decay must be explained before this goes anywhere near live money.

## 12.13.1 (09-16 12:5x UTC) - the MAIN one-fill disarm becomes LIVE-ONLY, so REVERSAL can be tested on paper
USER: run the Predict/build11 REV signal on Polymarket with EF, master on, in paper. The port already exists -
`poly_lanes.py` is build11's MAIN + REVERSAL ported into v12 (pressure gauge, fair odds, volume ratio, 13-feature
model, constants copied with line provenance; 21 tests in test_lanes.py). The blocker was elsewhere: REVERSAL is a
HEDGE on an open MAIN by design (build11 `_watch_reversal`: no MAIN, nothing to hedge), and `_main_oneshot_check`
disarms MAIN after ONE filled order - a live instruction from 09-13 that, on a paper engine, ends the experiment at
the first fill and takes REVERSAL with it. It now returns immediately unless `a.live`. Live behaviour is unchanged
and pinned by a test; paper keeps MAIN armed. Tests 215+71+21 = 307; SHA256SUMS 31/31.

## 12.14.0 — REVERSAL watches the MAIN call, not the MAIN order (build11 parity)
The port had REVERSAL wait for a PLACED MAIN (`poly_lanes.py` old line 490, `if not self.current_main`). build11
does not: `btc_model_build11.py:17151` sets `current_main` when `store.add_prediction` succeeds — the prediction —
and `_record_trade` consults `controls.may_execute(kind)` only afterwards, at 16804, to decide whether an order
goes out. Consequence of the deviation: with MAIN's switch off, `current_main` was never set, so REVERSAL returned
None on every candle and **EF + REVERSAL without MAIN orders could not be expressed at all**. That is why Task 113
had to arm MAIN. Owner's 09-16 screenshot of the Tokyo v11 box: MAIN BLOCKED, EF BLOCKED, REVERSAL TRADING,
runtime 5d 4h — the configuration that earns there is the one this port could not run.
Change: `main = self.current_main or self.main_signal`; the flip test and the state detail read from that, and an
unplaced MAIN is named in the detail as "(call only - MAIN order not placed)" rather than passed off as a hedge.
`test_lanes.py` inverts `test_reversal_requires_a_real_main_position` on purpose and keeps a floor
(`test_no_main_call_no_reversal`): no MAIN **call**, still no REVERSAL.
Tests 215+71+23 = 309 OK (direct invocation, see the test-runner fix below); SHA256SUMS 31/31.

## Test-runner defect fixed in the same commit
`test_v122.py` carried `if __name__ == '__main__': unittest.main()` at line 1280 with 1190 lines after it, and
`test_polymarket.py` the same at 694 with 152 after. Run as `python3 test_v122.py` the body reaches that block
mid-file, runs the 106 tests defined so far and exits **printing OK** — silently skipping 109 tests, all of them
the recent 12.10–12.13 work. `python3 -m unittest test_v122` was unaffected, which is why two sessions counted
307 and 189 and both were right. Blocks moved to end of file; either invocation now runs the whole suite.

## 12.14.1 — seed the lane's closed-candle history at startup (every restart was blind for 2 h)
`LaneEngine.closed` is a deque fed only by `on_closed_candle`, which the engine calls only on a live `k['x']`
frame (`btc_model_v12_polymarket.py:177`). The very next line writes that candle to the `candles` table — so the
table keeps the history and the deque starts EMPTY on every restart. `volume_ratio()` (poly_lanes.py:316) and the
move median (306) both read `list(self.closed)[-24:]`, so for the first 24 closed candles — two hours — the median
is over whatever handful has arrived.
Measured by Mumbai on two running engines reading the byte-identical candle at 11:57:27: volume_ratio 1.4975 warm
vs 0.4672 cold, implied vol median 27.51 vs 88.19, the cold lane's figure being simply the largest of the four
candles it had seen. Under `GATED_VOL_MIN` 0.70 that makes `_aligned_direction` return None on every read — 0 MAIN
calls in 6 candles where warm siblings called 10 and 11 of 17 (p=0.003 at their rate). It inflates the other way
too: the 113 lane's "23 MAIN in 28 min" against a steady 7–9/hr was the same artifact with a small median.
**Not a Task 114 problem — every restart pays it, live deploys included**, and it is invisible because the lane
reports a volume_ratio throughout; it just does not mean anything.
Fix: `_seed_lane_history()` replays the last 64 journal candles oldest-first into the lane before the feeds start,
prints warm/COLD, and files a `LANE_SEED_COLD` diagnostics row when under 24 so a genuinely cold start is on the
record rather than inferred. Unreadable candles table degrades to the old behaviour instead of failing the engine.
Tests: `LaneSeed12141`, 6 cases, including one that fails if seeding changes no median. 215+71+23+6 -> 316 OK;
SHA256SUMS 31/31.
Credit: Mumbai found and measured it, and retracted its own "market state" reading to do so.

## 12.15.0 — two verified defects from the nine-way line-by-line audit. One of them made the live PnL the wrong sign.

### (a) `poly_live.py` — a venue fee rate of ZERO was accepted as "the venue charges nothing"
`if bps is not None and str(bps)!=''` tested present-and-non-empty, so a reported `fee_rate_bps` of 0.0 passed and
stamped `fees=0.0` with basis `VENUE_FEE_RATE_BPS` — an estimate of zero presented as a venue figure. Polymarket's
trade tape does not carry the fee; it books it at POSITION level as `entry_fees_usdc`.
**Verified by V directly against the live journal, not taken from the audit:**
- 84 of 84 fills: `fees=0.0`, `fee_rate_bps=0.0`, basis `VENUE_FEE_RATE_BPS`.
- 83 settled epochs: local `sum(pnl)` **+4.4866** against the venue's `sum(venue_pnl)` **−8.5073**.
- Difference **12.9939** = `sum(venue_fees)` **12.9947**. The entire reported profit was uncharged fees.
- `payout − spent − venue_fees == venue_pnl` on **83 of 83** rows: the venue charges once, on entry, on the right
  base. Only our copy was missing.
So the engine reported **+$4.49 where the account actually lost $8.51**, and every number derived from
`results.pnl` — the dashboard PnL curve, `return_on_stake`, `daily()` and therefore the tp/sl daily halt — was too
high by $0.09–$0.25 per trade. Wins/losses/accuracy are unaffected (no row's sign flips; 38W/45L on both bases).
Fix: a positive rate is the venue's, anything else falls back to the local estimate and says so in the basis.
The local estimate was never wrong — `fee(px,shares,0.07,1)` reproduces `venue_fees` to 1e-5 on all 83 rows.
**This was seen before and misread.** R-19 observed `fills.fees` zero on all 76 rows and concluded the fee constant
did not matter. It did; the zero was the bug, not the answer.

### (b) `poly_lanes.py` — REVERSAL was handed the probability of the side it was NOT buying
The probability was flipped twice: `p_up = fair if UP else 1-fair` (already the side's probability) and then
`p_side = p_up if UP else 1-p_up`. **Verified on the running module:** a DOWN reversal with `fair_p_up` 0.0100 was
handed **p=0.0100 when P(DOWN) was 0.9900**, and reported `probability_up=0.9900` when P(UP) was 0.0100 — both
fields exactly swapped. `_aligned_direction` only names DOWN when `fair_p_up <= 0.40`, so the p reaching the EV
gate was always ≤0.40 against a DOWN ask near 0.60: EV about −0.35. **DOWN REVERSAL COULD NEVER FIRE**, and it
failed as "price fails model EV", which reads as a pricing problem. MAIN flips once and was always correct, so this
was a deviation in that function, not a house convention. Four regression tests; they fail on the old module.

Also in this build: `_shadow_stale` instrumentation (12.15.0) logs the decision the lane WOULD have made when the
freshness bar blocks it, so Task 116's unanswerable 1,228 blocked rows become gradeable. Instrumentation only —
a test asserts the function body cannot reach the order path.
Tests 221 + 77 + 28 = 326 OK; SHA256SUMS 31/31 (now covers `poly_live.py`).

## 12.15.1 — the journal recorded inputs the decision never saw, on half of every fired row
`_decide_once` replaced `d['features']` — the vector the model decided on — with a fresh `features()` read taken
later, after `publish()`, `decide()`, `_calibrate()` and the padded-EV gate, immediately before `executor.fire`.
**Measured on the live journal:** the decision's own `rv60` disagrees with `features['rv60']` on **43 of 90 fired
diagnostics rows (48%)** and **37 of 88 signals rows**, max delta 0.444 — against **4,775 of 4,775 non-fired rows
agreeing exactly**. That 100%-versus-52% split is the overwrite's fingerprint: only the fire path re-read.
Consequences: half of every fired row was unreproducible, so any study that replayed the model on journal features
— R-11, R-13, R-12 stage A — graded fires against inputs they did not use. It also dropped `ts_ms` (the
`features()` dict has no such key), which is why every EF order records `signal_ts_ms` null while the lanes record
it, making EF invisible to any decision-to-submit latency study.
Fix: the decision keeps its own features; the later read is still taken and recorded beside it as
`submit_features`. Two regression tests. 328 tests OK, SHA256SUMS 31/31.

## 12.15.2 — six more from the nine-way audit. Two of them decide whether the engine trades at all.
1. **`accuracy` EV mode raised an uncaught `TypeError` and stopped everything.** `decide()` returned `threshold`
   as a **dict** in accuracy mode; `order_plan` does `math.isfinite(d['threshold'])`, which raises TypeError —
   not ValueError, so neither `_gate_on_padded_ev` (catches ValueError) nor `Executor.fire` (ValueError, KeyError)
   caught it. One click on "accuracy" in the EV dropdown and the raise escaped into `decide_loop`'s catch-all
   ~4x/second: EF never traded, and because it raised BEFORE `await self.lane_loop(ep)`, **MAIN and REVERSAL died
   with it** — showing nothing but "decide loop: TypeError". The EV bar in accuracy mode is the `ev_floor`
   (confidence is a separate test already applied), so `threshold` is now always a number and both floors are
   published beside it as `floors`.
2. **The owner's only automatic stop could be skipped silently.** `_floor_check`, `_wipeout_check` and
   `_master_watch` sat inside the housekeeping try-block that opens with up to four 8 s `metadata()` awaits and an
   8 s `account_snapshot()`. One timeout jumped to the handler and the floor was simply not evaluated, leaving one
   error string as evidence — while `venue_truth_loop` kept `cash` fresh so trading carried on. The monitors are
   local and read the journal; they now run outside that block, each guarded so one cannot take out the others.
3. **The floor could read a frozen equity.** `open_value` was `ORDER BY ts DESC LIMIT 1` with no age bound, and
   `venue_state` is written only by `venue_truth_loop` — whose handler leaves the old row in place while
   housekeeping keeps `cash` current. Positions settling into cash while venue-truth is down overstated equity and
   the floor never fires. A row older than `FLOOR_OPEN_VALUE_MAX_AGE_S` (90 s, three missed 20 s cycles) is now
   treated exactly as `None` already was: unknown, act on nothing, say so.
4. **One raise could disarm the engine for hours.** `asyncio.gather` had no `return_exceptions` and
   `reconcile_loop`, `grade_loop`, `chart_seed` and part of `venue()` were unguarded: any exception unwound
   `main()`, systemd restarted, and safe-start parked master OFF — the 09-16 four-hour silent disarm, reachable
   from a single bad frame. `_supervise` now journals `TASK_CRASH` and restarts the loop.
5. **Ladder staking ignored the operator's own `max_stake`.** `if s['mode']!='ladder'` exempted the mode that
   scales fastest with the bankroll, so a panel reading "Max stake $5" would still stake $20 at $210 equity.
   The bounds now apply to every mode.
6. **The MAIN one-shot counted bookkeeping, not shares.** `reconcile` writes the fill rows first and sets
   `status='FILLED'` only once the venue agrees the order is terminal, so a partial or slow-to-confirm MAIN left
   the check seeing zero; it runs once a minute while lane state resets every candle, so MAIN could re-arm and
   send a SECOND live order against "main off after 1 filled order, whatever happens". It now counts an order that
   is FILLED **or** has any fill against it.
Also: the 12.15.0 shadow rows were contaminating `_master_watch`'s "fires gated" count and could surface as a
lane's skip reason — both reads now exclude them. Tests 336 OK; SHA256SUMS 31/31.

## 12.15.3 — the rest of the audit. Everything actionable is now fixed or explicitly deferred with a reason.
1. **`reconcile` declared a verified NO_FILL faster than a real fill can appear.** The 404 branch terminalised at
   `age>=2.0 s` / 2 misses; on the live journal every one of 84 fills needed **6.7 s at the fastest** (p50 8.5 s,
   max 16.0 s) for the trade tape to confirm, and a MATCHED FAK 404s on `get_order` exactly like an unmatched one.
   A false NO_FILL abandons a real position — no fills row, no result, no PnL, never re-checked. Now uses the same
   `ABSENT_PROOF` / `ABSENT_PROOF_AGE_S` standard the sibling branch already used.
2. **The venue book socket had no blank/non-JSON frame guard** — the exact shape of the incident that produced 591
   reconnects and zero data, on the feed the money is priced against. Guarded and counted (`_venue_skipped`).
3. **`release()` could orphan a live order.** `reconcile` and `grade` both INNER JOIN orders to signals, so a
   deleted signals row means an order that can never be reconciled and an epoch that can never be graded. All 41
   orphans in the live journal are REJECTED, so nothing is stranded today — but that was incidental, not enforced.
   Re-arm now refuses while any order on the candle is SUBMITTING/UNKNOWN/PENDING/FILLED and records why.
4. **Lane decisions that never reached the executor froze the lane for the rest of the candle.** `evaluate()` sets
   `pending[kind]`; five returns in `lane_loop` left it set, so MAIN and REVERSAL went quiet with no row naming the
   cause — a 15-second gap in `account_snapshot` was enough. `_lane_drop` clears pending, journals `lane_dropped`,
   and lets the lane retry.
5. **Port fidelity, `MEDIAN_WINDOW = 23`.** build11 medians a 24-deque that CONTAINS the live candle, filtered on
   `closed` — 23 closed candles. This port kept closed candles separately, so `[-24:]` gave 24 and took the upper
   middle. Both the move median (fair odds) and the volume median were affected, both biased the same way, so the
   port was systematically tighter than build11 on BOTH lane gates on every candle.
6. **`MAIN_MAX_ATTEMPTS` 6 → 4**, to match `MAX_ATTEMPTS_PER_CANDLE`. Attempts 5 and 6 could never reach the venue:
   `fire()` returned at the reservation with no status write and the lane counted a silent no-op against its budget.
7. **A placed MAIN with no signal no longer becomes `{}`** — falsy but `is not None`, which three call sites read
   two different ways.
8. **FeedHealth measured freshness on the wall clock.** A negative lag was clamped to zero, so on any host whose
   clock sits behind the exchange the event-lag check — the module's entire stated purpose — was silently off
   (clock 3 s behind, feed 2 s late, reported 0.000 and LIVE). The skew is now subtracted rather than clamped away,
   and `arrival_age` uses `time.monotonic()` for real messages, so a backwards NTP step can no longer make a dead
   socket read fresh. BookCache already did this and documents the incident that taught it.
9. **`Model.__init__` never checked weight LENGTHS.** 30 names against 29 coefficients loads fine and numpy
   broadcasts instead of raising — every p from a shifted feature-to-weight mapping, invisibly.
10. **The dashboard named only MASTER.** `ef_enabled=False` — including after the bankroll floor fires — plus a
    daily stop, a ban rule and a state-X pause all rendered as "LIVE · MASTER ON". The status line now names every
    gate that can stop a lane, and the floor is in the payload at all.
11. **One browser timeout permanently doubled the dashboard poll rate** (callback fired by both the readystate
    handler and the timeout handler, and `pollState` re-arms in its callback). Fires once now.
12. **The control WRITE path had no generic exception handler** — a sqlite or attribute error returned an HTML
    traceback the page cannot parse, with no `note_error` trace, so a failed write could look like a success.

**Deferred, with the reason — not silently skipped:** build11's `adapt_ratio` fair-odds volatility multiplier is
genuinely missing from the port (`btc_model_build11.py:15976`, plus `_AdaptWindowStats` and ~260 lines of
supporting code). It changes what fires, its magnitude here is unmeasured, and the lanes that use it are paper-only
today. Porting it belongs in its own build with its own before/after, not bundled into a same-day live deploy.
Tests 350 OK; SHA256SUMS 31/31.

## 12.15.4 — the owner's second audit (15 items, run against 12.9.0), verified against 12.15.3 first
Four of the fifteen were already closed by 12.15.x and are recorded as such, not re-fixed: #2 REVERSAL double
flip (12.15.0), #5 lane `pending` latch (12.15.3 `_lane_drop`), #7 attempt caps 6 vs 4 (12.15.3), #8 ladder
ignoring min/max stake (12.15.2). The other eleven were real and open on the current tree. All fixed:

1. **Clock skew in BOTH directions** (`poly_core.BookCache`, `poly_feeds.FeedHealth`). Both only corrected a
   clock BEHIND the venue; a clock AHEAD added its skew to every age — >8 s ahead dropped every valid book event,
   ~3 s ahead failed the 0.75 s bar on data received milliseconds earlier. First attempt at this (running minimum
   seeded from the first packet) was WRONG and four existing tests caught it: a single genuinely-old first event
   would have read as skew. Final form is asymmetric on purpose: a negative delta is impossible without skew, so
   that side follows immediately as before; a positive floor is indistinguishable from transport lag on one
   packet, so it is adopted only from the minimum of a full 200-sample window. One packet, or the first packet,
   can never move it. Tests pin both properties.
2. **Four of the thirteen weighted MAIN features were hardcoded to 0.0** — `ofi_1s` (0.85), `ofi_5s` (0.60),
   `aggressive_cluster_bias` (0.25), `volume_profile_delta` (0.35): 2.05 of 8.75 anchor weight permanently silent,
   so the lane never ran the declared score. Ported from build11 exactly (`quote_ofi` :15730, `cluster_z` :15767,
   `RollingSignedMean` :4393, per-candle aggressive quote :15226/15624), fed from the depth and trade inputs the
   port already receives. **This changes MAIN's score on the paper lanes; expect its call pattern to move.**
3. **MAIN/REVERSAL could submit a signal the market had already reversed.** EF's `reassess` re-runs `decide_now`;
   the lanes handed the executor a lambda returning the ORIGINAL frozen dict, so a lane's p was held constant
   against a moving book across up to four attempts. `LaneEngine.still_valid()` recomputes and re-applies the same
   alignment test without touching `pending`; the lane reassess now releases `SIGNAL_CHANGED` like EF does.
4. **Filtered positions were stored as whole-account truth.** `venue_truth_loop` passed the settled-candle filter
   to its one call and stored the result as `venue_state`, so the live position vanished from `open_value` on any
   pass with candles awaiting PnL (measured: 49 of 5,417 reads, one run 272 s) — biasing the floor toward firing
   and sizing toward under-staking. Whole account first; the awaited conditions as a second, narrower read.
5. **A positions-API failure was converted to "zero positions"** (`or []` on a value that is `None` by design).
   `None` now survives to `account_positions`.
6. **Dashboard `positions()` grouped by epoch alone**, summing an EF-UP and a REVERSAL-DOWN on one candle into a
   single position with an arbitrary side. Grouped by (epoch, kind).
7. **The dashboard's "EF" signal could be MAIN or REVERSAL** — selected `WHERE epoch=?` without kind. Fixed.
8. **CSV export cross-contaminated lanes** — order/fill subqueries filtered on epoch only. Kind-matched, fills
   joined through their order.
9. **Direct on-chain claims (`tx:<hash>`) had no path out of REVIEW/SUBMITTING** — `claim_state` returned None for
   them. Now `TX_DIRECT`, resolved from the venue's own valuation (settled + valued at zero = collected).
10. **The banner printed "Polymarket v12.1"** on every build. Prints the journal's build.
11. **Persisted `model_weights` were never loaded** despite the docstring; `PolyRunner` always built `LaneEngine()`
    bare. Read once at construction.
Tests 365 OK; SHA256SUMS 31/31.

## 12.15.5 — the lanes get build 11's parameters, not EF's EV threshold
Owner: *"are you using same ev for reversal as well? because reversal is different thing and it has different
parameters."* Yes, we were. `lane_loop` handed every MAIN/REVERSAL decision `self.m.threshold(...)` — the v10 model's
0.15/0.25 regime EV table — and `order_plan` refused on it. **build11 applies no EV gate to either lane**
(`btc_model_build11.py:16804-16820`: `may_execute` is switches and halts; the only price control is REVERSAL's
optional max-entry cap `v11_rev_max_entry`, default 0 = off). So REVERSAL on Polymarket faced a rule it was never
designed to clear — two of its first four post-fix signals died to it. The order_plan auditor named this
separately this afternoon ("a lane trade's EV bar is EF's regime dial, not anything the lane chose") and I did
not act on it then. Acting now.
Change: lane decisions carry their own `threshold = LANE_EV_FLOOR = 0.0` — the fee-inclusive breakeven and nothing
more — and the engine no longer overrides it. The breakeven is the one thing kept, deliberately: build11's venue has
no fee model and this one does, and a lane buying a price it cannot beat even when right is a loss, not a strategy
difference. build11's REVERSAL entry cap is ported as meta `rev_max_entry` (default 0 = off) so the owner can match
Tokyo's value without a build. EF's dial is untouched. Tests +4 = 369; SHA256SUMS 31/31.
Expect REVERSAL (and MAIN, where armed) to place materially more orders on the paper lanes. That is the port
running its own rules for the first time, not a regression — and it is exactly the sample the EF+REV question needs.

## 12.16.0 — build 11's adapt_ratio ported to the lanes (owner: "i need my model to be adaptive")
The one adaptive piece Tokyo runs that the port never had (deferred since 12.14.0). `AdaptRatio` in `poly_lanes.py`
is build11:863-877 + :15805-15958 on one deque: one-second causal log returns from spot trades, winsorised robust
RMS over 180 s (fast) and 3600 s (slow), ratio clamped 0.30–6.0, identity inside 0.85–1.15, log-linear ramp to
full by 0.67/1.50, chain broken by any >5 s feed gap. `fair_odds` multiplies the 23-candle median move by it
(build11:15976, :16062): when the last minutes move faster than the last hour, fair_p_up stops over-stating how
decided the candle is, so MAIN waits and REVERSAL sees the swing earlier; in ordinary tape the number is exactly
12.15.5's. Feature `adapt_ratio` is logged on every lane decision so its engagement rate is auditable. **EF is
untouched** — a vol-scaled EF is R-28 for H1 to grid first (rule: threshold gridded before shipping). Tests +6 =
375; SHA256SUMS 31/31. Paper lanes first (8794 MAIN, 8796 EF+REV); Zurich stays 12.15.4, master off.

## 12.16.1 — adapt_ratio reaches the journal and /api/state
Mumbai, 8 post-restart lane rows: the field never left `poly_lanes` — set in the feature dict, absent from the
MAIN/REVERSAL decision dicts the engine journals and from `monitor()`. Now on both and on `lanes.adapt_ratio`.
Tests +2 = 377; SHA256SUMS 31/31.

## 12.17.0 — the venue becomes a seam: `--venue predict` (paper only)
Owner, 09-16 22:2x: *"we are moving to predict, not polymarket anymore ... i like the signal logics and
everything we have now it does so well in this, but when it comes to execution and fees predict is way cheaper,
with almost 98% fill rate."* Context: R-30b found the Polymarket live fee is **4.01% of stake, charged on
winners and losers alike**, against a gross edge of **−0.50% of stake** — the toll, not the signal, is what the
account has been losing to. So the signal moves venue and nothing else changes.

New `predict_venue.py` (+`test_predict_venue.py`, 26 tests) does market discovery and book translation only,
lifted from the engine that already trades there: `/v1/markets?marketVariant=CRYPTO_UP_DOWN` ranked to the exact
candle (build11:9843), `/v1/markets/{id}/orderbook` bootstrap (build11:9965), and `predictOrderbook/{id}` over
`wss://ws.predict.fun/ws` (build11:10262). It emits the **same `BookCache` event shape** Polymarket already
sends, so `poly_core`, `poly_lanes` and `btc_model_v10` are untouched — a test asserts none of the three imports
it. Engine gains `--venue {polymarket,predict}` and `venue_predict()`; `resolve_market` delegates.

**The one real difference, and it is not cosmetic.** Polymarket quotes two independent token books; Predict
quotes ONE YES-centric ladder whose NO side is the exact complement (build11:9440), so `ask_dn == 1 − bid_up`
by construction and the two sides can never both look cheap. `p_venue`/`lv` therefore come from a single ladder.
Six tests pin the complement, because a sign error there inverts every DOWN trade silently.

**Paper only, by construction, not by policy:** `LiveBroker` signs Polymarket orders, so there is no Predict
order path in this build and `--venue predict --live` is refused in `args()` with a test to prove it. The
adapter has no signing, order or wallet surface (asserted on the parsed AST).

Not yet proven: model_v10's `p_venue`/`lv` were trained on **Polymarket** prices. R-31b is measuring whether
Predict's price is the same forecast; if it is not, the venue input needs a re-fit before any of this is worth
running. Tests 377 → 403; SHA256SUMS 31 → 33.

## 12.17.0 PAPER (Zurich box) — written by the Zurich session

Started 2026-09-21 14:12:35 UTC on the Zurich box, `/home/ubuntu/pm_paper_zurich`, **PID 137569**, argv `.venv/bin/python -u btc_model_v12_polymarket.py --mode pnl --capital 50 --host 0.0.0.0 --port 8787 --db polymarket_v12_zurich_paper1.sqlite3 --quote-age-ms 2000` — **no `--live`**. Owner via V, 14:1x: "Run eu central on paper please, it's live with master off."

Predecessor: the LIVE process PID 104148 (12.17.0, db `polymarket_v12_live_zurich_3.sqlite3`, up since 09-16 23:35:01) stopped 14:12:34 at a clean point — open_value 0.00, 0 in-flight/UNKNOWN, 0 filled-ungraded. Its final state: 402 orders, 164 results, master false, ef true, rev false, **cash 1.65**. That journal is closed and untouched as the record.
Paper environment proven from the engine's own API, not inferred: `/api/state` lane **PAPER**, `book.environment` **paper**, `api_key_configured` **False**; meta.lane "PAPER"; banner `Polymarket v12.17.0 PAPER`. The child process was started with the four Polymarket/Relayer credentials **removed from its environment** — only `DASHBOARD_PASSWORD` was passed — so this process cannot reach the venue with credentials even in principle.
Flags set through the audited control path after start: EF true, REVERSAL true, MAIN false, master **true** (paper), stake `streak` fixed 5.0 / percent 5.0 / current 3.0 / min 3 / max 50, next_stake 3.0. `ef_cash_floor` left **unset** (paper, per the brief).
First decision row 14:12:35. `[LANE SEED] 0 closed candles from the journal; COLD - volume_ratio is noise until 24 more` — the fresh db carries no candle history, so MAIN/REVERSAL volume_ratio is noise for the first ~2 h; EF is unaffected.

## 12.18.0 (09-22 10:xx UTC) - MAIN and REVERSAL are priced by a maximum entry, not by EF's model-EV test

Why (from the running artifacts, not a reconstruction): MAIN was switched ON on the Zurich paper lane 09-22 01:49:42 UTC.
In its first 45 min it evaluated 135 times and produced 101 order plans; **86 were refused "price fails model EV"** (asks
0.60-0.98, median ~0.85, lane p ~0.75) and **15 "below venue minimum; stake not increased"** (5-share minimum x ask 0.85 =
$4.25 > the $3 stake). Nothing else blocked it. On Mumbai 8796 (6 days, MAIN off) the lane produced 2,881 MAIN signals
(3.9/candle, 87% "strong"), every one dropped at the permission gate - the signal is healthy. The owner's v11 export
(Predict.fun build11, 09-21) shows build11's MAIN firing with p(side) <= quote on 58 of 73 calls and landing 85%; priced on
Polymarket's own book at the same second those calls made +0.266/$1 (n=65, hit 86%, ask median 0.72; analysis/v/model/RESULT.md).
build11's own comment (17028): "the blend sets the recorded probability; it does not gate the fire". The v12 port sent the lane
through EF's `p/cost-1 >= threshold` in `order_plan`, which build11 never applies to a lane. That is why MAIN never traded.

Change: `poly_lanes.LANE_MAX_ASK = 0.90`; MAIN and REVERSAL decisions carry `price_rule='lane_cap', max_ask`; `poly_core.order_plan`
skips the model-EV test for `lane_cap` decisions and refuses only `ask > max_ask` ("above lane cap"). EF's path is untouched.
`d['min_topup']` (engine sets it on PAPER lanes only) lets `order_plan` raise a lane plan to the venue's 5-share minimum instead of
refusing; LIVE keeps "stake not increased" - the live stake stays the owner's. The 0.90 cap is an economics floor (fee cannot be
covered above it at the hit rates seen), to be gridded on paper, not tuned. Tests: +6 (`test_lane_cap.py`, run against
`order_plan` on Zurich's exact refused case ask 0.85 / p 0.75 / $3) = 409 green (6+36+71+270+26); SHA256SUMS 33 -> 34.
Not shipped by V: the sandbox refuses V engine-changing instructions to Zurich. Deploy = Zurich pulls, restarts the PAPER process
on the same db with 12.18.0, verifies `/api/state` build 12.18.0 and the first MAIN order row. Owner arms nothing; paper only.

### 12.18.0 PAPER deploy line (Zurich box) — written by the Zurich session

Restarted 2026-09-22 10:10:52 UTC, **PID 144073** (was 137569, stopped 10:10:47 at a clean point: 0 in-flight/PENDING/UNKNOWN, 3 s into the candle). Same argv, **same db** `polymarket_v12_zurich_paper1.sqlite3`, no `--live`, the four Polymarket/Relayer credentials again stripped from the child environment (only `DASHBOARD_PASSWORD` passed).
Verified: `sha256sum -c SHA256SUMS.txt` **34/34**, every file byte-equal to `git show 3eed7c3`. `python3 -m unittest test_lane_cap test_lanes -q` → **Ran 42, OK**. Full suites also green: 71 + 36 + 270 + 26 + 6.
`/api/state` after restart: build **12.18.0**, lane **PAPER**, `book.environment` paper, `api_key_configured` False, master **true**, MAIN **true**, REVERSAL **true**, EF **true**, halt null. `[LANE SEED] 64 closed candles from the journal; warm` — the same-db restart seeds warm, unlike the 09-21 fresh-db start which read COLD.
Baseline carried in the db at restart: 130 orders (EF 124, MAIN 2, REVERSAL 4). **The 2 MAIN and 4 REVERSAL orders all predate this deploy** (MAIN 09-22 03:05:24 and 04:01:55; REVERSAL 09-21 19:06 → 09-22 03:42), so any MAIN order after 10:10:52 is the first attributable to the LANE_MAX_ASK change.

 12.19.0 (09-22 12:xx UTC) - fast path: one decision per attempt, warm order transport, honest wire timing

Why (Zurich live journals, 674 orders, `analysis/v/exec/latency_breakdown.py`; plan `analysis/v/exec/EXEC_PLAN_2026-09-22.md`):
our side before the wire was 14-38 ms p50 on attempt 1 and the POST round trip 255 ms p50, of which ~180 ms is venue-side
(curl GET /time from Zurich: connect 1.8 ms, TLS 33 ms, first byte 75 ms). Inside our 14-38 ms: a SECOND full reassess()
(1.5-17 ms p50), the sign on a worker thread (9.8 ms p50 for ~0.5 ms of signing), ui.allowed()'s 6 SELECTs twice per attempt,
and two synchronous=FULL commits. Rejects 58% "no orders found to match with FAK" - the ask moved during the round trip; the
retry then slept a flat 75 ms before re-pricing. Owner, 09-22: "your first goal is to get the order accepted asap ... less
than 100ms ... try getting it filled in first try so we don't have to retry and even if we retry try getting it filled asap."

Change (all in `learner/v12_2`, EF/MAIN/REVERSAL alike; no pricing or EV rule touched):
- `Executor.fire`: the pre-post reassess() is replaced by `Executor.allowed(kind)` (the dashboard's control check, wired in
  the runner) + the existing `order_plan(latest)` EV re-check. One decision per attempt.
- `LiveBroker.sign_mode`: 'inline' when eth_keys runs on coincurve (sub-ms sign, no thread hop), else the 12.9.0 thread path.
  Same bytes, same journal hash.
- `Journal`: `journal_mode=WAL, synchronous=NORMAL` (order INSERT before the POST stays - it is the crash record; NORMAL
  loses only power-loss durability). `Journal.get` is a 2 s write-through cache; `set`/`set_many` refresh it.
- `Executor.RETRY_TICK_WAIT_S=0.1` replaces `RETRY_DELAY_S=0.075`: after a retryable reject, re-price as soon as the local
  book changes (seq), at most 100 ms later. `timing.retry_ticked` records which.
- `LiveBroker.keepalive()` = GET /time on the `secure_clob` transport (the one the POST uses) every 10 s from
  `keepalive_loop`; `keepalive_ms`/`keepalive_age_s`/`sign_mode` in `latency_stats()` -> dashboard `latency`.
- timing: `fire_to_wire_ms` (stamped as the POST leaves, after the order INSERT) and `db_order_ms`.
Not changed: POST_FLOOR_S 0.4, budget 2 s, pad 1 tick, max attempts 4, cap/EV rules - the pad grid runs on London LIVE later.
Tests: `test_fastpath.py` +10; `test_polymarket` retry tests rewritten for the tick wait (+1); `test_v122` oneshot pin
relaxed to "no diagnostics scan". Green: 72 + 270 + 36 + 6 + 26 + 10 = 420. SHA256SUMS 34 -> 35.
Rollout: Zurich PAPER first (same db; opening it switches the file to WAL - readers use `?mode=ro` with the -shm present, or
a byte copy), verify build 12.19.0 and `latency` in /api/state, then `latency_breakdown.py` after 1 h against the 12.18.0 hour.
London LIVE only after the owner's E-0 decisions.

### 12.19.0 PAPER deploy line (Zurich box) — written by the Zurich session

Restarted 2026-09-22 11:40:38 UTC, **PID 145293** (was 144073, stopped 11:40:26 at a clean point: 0 in-flight/PENDING/UNKNOWN, 9 s into the candle). Same argv, **same db** `polymarket_v12_zurich_paper1.sqlite3`, no `--live`, the four Polymarket/Relayer credentials again stripped from the child environment. Restart epoch **1790077238**.
Verified: `sha256sum -c SHA256SUMS.txt` **35/35**, every file byte-equal to `git show a2b3ace`. `python3 -m unittest test_fastpath test_polymarket -q` → **Ran 82, OK**.
`/api/state` after restart: build **12.19.0**, lane **PAPER**, master true, MAIN/REVERSAL/EF all true. `[LANE SEED] 64 closed candles from the journal; warm`. Banner `Polymarket v12.19.0 PAPER`.
WAL confirmed as the brief warned: `-wal` (387,312 B) and `-shm` (32,768 B) present alongside the db; all reads here used `?mode=ro`.

**`latency.sign_mode` / `latency.keepalive_ms` could NOT be verified on this run, and cannot be on a paper run.** Two independent reasons, both read from the deployed source:
1. `poly_core.latency_stats()` returns `{}` on its first line when `latency_samples` is empty (`if not S: return {}`). The `keepalive_ms` / `sign_mode` assignments are at poly_core.py:1188-1189, *after* that early return — so both keys are absent until at least one order attempt has been sampled. At the time of writing there are 0 orders since restart, and `/api/state.latency` is `{}`.
2. Both are read off the broker (`getattr(b,'sign_mode',None)`), and they are set in **`poly_live.LiveBroker.__init__`** (poly_live.py:52). `poly_core.PaperBroker` defines no `sign_mode` attribute at all, so even once orders exist this key will read `None` under `--mode pnl` without `--live`. `sign_mode` is chosen by `LiveBroker.pick_sign_mode()` — 'inline' when eth_keys runs the CoinCurve backend, else 'thread' — which is live-path-only logic.
Verdict: the deploy is correct and complete; the requested verification is not satisfiable in PAPER. It needs a live run, or the keys need to be surfaced independently of `latency_samples` and of the broker class.
 12.19.1 (09-22 11:5x UTC) - `latency_stats()` reports `sign_mode` / `keepalive_ms` / `keepalive_age_s` before any order exists
(Zurich, 11:43: the empty-samples early return hid them on the fresh 12.19.0 paper process; paper's broker has neither -> None).
No order-path change. Tests +1 (421), SHA256SUMS 35. Not deployed to Zurich paper (cosmetic); goes out with the London build.

 12.20.0 (09-22 12:xx UTC) - the settlement line as the venue settles it; MAIN/REVERSAL cards graded on their own fills

Why: owner, 09-22: "be sure about the settlement price when fire and everything else, simply clean dashboard no bugs in
accounting"; and 12:53 BST on the Zurich paper dashboard: "Why no shadow grading here??" (MAIN card 0 W / 0 L while MAIN
had been placing orders since 10:25).
1. Settlement line. T0 (analysis/v/t_tests/T0_ruler.md) proved the venue's reference feed is the INSTANT Chainlink price
   (corr 0.974 with Binance raw, residual 1.6 bps vs raw / 4.0 bps vs TWAP), while btc-updown-5m settles on that feed's
   60 s TWAP at close vs at the open. `btc_model_v10.FeatureState.REF_IS_TWAP` defaulted to 1 ("the feed IS the TWAP") so
   `ref_open`/`ref_now` were instant values. Default is now 0: the line is the TWAP of the feed over the window
   (Binance TWAP60 proxy when the feed does not cover it, ref_src=0). The v10 model does not read ref_* (model_v10.json
   lists FEATURES only), so EF's p is unchanged; the lanes judge on the Binance candle as before. New absolute fields in
   every features dict: `ref_open`, `ref_now`, `ref_inst` (+`ref_inst_ok`), `bn_line_open`, `bn_line_now` - so every EF
   fire's diagnostics row and every lane decision row (`ref_*` beside `ask_up/ask_dn`) carries the line it saw.
   Dashboard: "Settlement line · Chainlink TWAP60" card (`/api/state` `settlement`: line_open = price to beat, line_now,
   move_bps, source, chainlink_now, binance_last, basis_bps, locked_s = seconds of the closing window already known).
2. Lane cards. `poly_dashboard` built `metrics=dict(main={},reversal={},ef=metric,combined=metric)`: MAIN and REVERSAL were
   handed EMPTY dicts, EF was handed the whole-journal per-epoch metric. `Journal.lane_metrics()` grades each lane on its
   own fills (win = lane side == venue actual); the three cards now read from it, combined stays the per-epoch net.
Accounting audit (read-only, zurich_2 live journal 83 results vs venues.outcome): grading 61/61 match the venue oracle;
per-candle pnl arithmetic 83/83 exact; reserve and orphan checks pass. Faults found: fills.fees=0 on every fill in that
12.12.1-era journal (fixed in 12.15.0, not backfilled - that journal's local +4.49 is the venue's -8.51); 6 results rows
stuck in claim_status REVIEW with claim_id NULL (collected by auto-redeem; pending_payout excludes them; cosmetic).
Tests: `test_settlement.py` +6; RefFeed tests re-pinned to the TWAP reading (+ref_inst). Green: 72+10+6+6+36+26 + 270 = 426.
SHA256SUMS 35 -> 36. Rollout: Zurich PAPER (with 12.19.1), then London.

### 12.20.0 PAPER deploy line (Zurich box) — written by the Zurich session

Restarted 2026-09-22 12:01:09 UTC, **PID 145746** (was 145293, stopped 12:00:54 at a clean point: 0 in-flight/PENDING/UNKNOWN, 30 s into the candle). Same argv, **same db** `polymarket_v12_zurich_paper1.sqlite3`, no `--live`, credentials stripped from the child environment. Restart epoch **1790078469**.
Verified: `sha256sum -c SHA256SUMS.txt` **36/36**, every file byte-equal to `git show 230dadf`. `python3 -m unittest test_settlement test_fastpath -q` → **Ran 17, OK**.
`/api/state` after restart: build **12.20.0**, lane **PAPER**, master true, MAIN/REVERSAL/EF all true. `[LANE SEED] 64 closed candles from the journal; warm`.
`settlement` block present and populated: `line_open` 86016.01, `line_now` 86023.76056484699, `source` **"binance proxy"**; full key set `basis_bps, binance_last, bn_line_now, bn_line_open, chainlink_now, line_now, line_open, locked_s, move_bps, rule, source`.
`metrics.main` and `metrics.reversal` are no longer empty: **main** accuracy 0.875, wins 7, losses 1, real 0, shadow 8, basis LOCAL_FROM_FILLS, local_pnl +4.7213. **reversal** accuracy 0.25, wins 1, losses 3, real 0, shadow 4, basis LOCAL_FROM_FILLS, local_pnl −7.0669. `metrics` key set is now `combined, ef, main, reversal`.

**12.19.0 window, closed early by this deploy.** 12.19.0 ran 11:40:38 → 12:00:54, **20 minutes, not the planned 60** — this deploy ended it. `latency_breakdown --since 1790077238` was captured from a `backup()` snapshot before the restart so the data was not lost, but it is **n=3 and unreadable**: orders with timing 3, all FILLED, decision_ms p50 0.4, sign_ms p50 0.1, fire_to_submit_ms p50 0.7, submit_ms p50 0.1, total_attempt_ms p50 1.0, book_age_ms p50 14.0, signal.ts→order.ts p50 1 ms, by attempt {1: (3,3)}. Those sub-millisecond submit figures are the PaperBroker's in-process fill, not a venue round trip, so they are not comparable to the live journals' submit_ms p50 ≈ 255 ms. A real 12.19.0 latency read needs either a dedicated 60-minute soak without an intervening deploy, or a live run.
 12.21.0 (09-22 12:xx UTC) - master OFF = shadow paper, master ON = live, one process

Why: owner, 09-22 12:5x: "when master off it's paper and when master onn it's live, we don't have to set paper or live from
terminal or anything, if master off it's paper and if master onn it's live it's that simple bro". Until now a process was
paper OR live by the `--live` flag, and master OFF meant no orders at all - so a live box with master off produced nothing
to grade, and the "real N · shadow M" labels on the cards were fixed by the flag, never by what the money did.
Change:
- A process started with `--live` (credentials) carries BOTH brokers. `Executor.route()`: master OFF -> the paper broker,
  order lane 'PAPER' (shadow fills in the same journal); master ON -> the venue, lane 'LIVE'. `orders.lane` is new
  (additive); old rows read as the journal's lane. `reconcile` and `fill` use the broker of the order's lane.
- `Dashboard.allowed(kind)` no longer requires master: the lane switch, halt, daily limits, bans and the cash floor still
  stop both lanes. Master is the ROUTE. A process without credentials ignores master (label PAPER, all fills paper).
- `Journal.grade`: `results.pnl/payout` = the journal's own lane (LIVE on a live process), `results.shadow_pnl/shadow_payout`
  = the paper broker's fills on the same candle. `metrics()`, the pnl curve, sizing and the cash floor stay on the venue
  lane. `lane_metrics()` returns real/shadow blocks per lane; the cards read them (headline = venue fills when any).
- `reserve_detail` counts only the journal's lane (a shadow order never holds venue reserve). `_main_oneshot_check`
  counts LIVE MAIN fills only. `min_topup` is set per order from its lane (shadow may top up to 5 shares, live never).
- Header label: LIVE (creds + master ON) · SHADOW (creds, master OFF) · PAPER (no creds). Export rows' `financial_is_shadow`
  follow the order's lane.
Startup is unchanged: a live process still boots with master OFF, i.e. SHADOW, and the owner arms it from Trade Controls.
Tests: `test_master_lane.py` +10; two master-gate pins in `test_polymarket` re-pinned to routing. Green: 167 + 270 = 437.
SHA256SUMS 36 -> 37. Rollout: Zurich PAPER (no creds: behaviour identical, master ignored), then London with credentials.

### 12.21.0 PAPER deploy line (Zurich box) — written by the Zurich session

Restarted 2026-09-22 12:10:35 UTC, **PID 146085** (was 145746, stopped 12:10:20 at a clean point: 0 in-flight/PENDING/UNKNOWN, 2 s into the candle). Same argv, **same db** `polymarket_v12_zurich_paper1.sqlite3`, no `--live`, credentials stripped. Restart epoch **1790079035**.
Verified: `sha256sum -c SHA256SUMS.txt` **37/37**, every file byte-equal to `git show 0157856`. `python3 -m unittest test_master_lane test_polymarket -q` → **Ran 82, OK**.
`/api/state`: build **12.21.0**, lane label **PAPER**, MAIN/REVERSAL/EF all true. `metrics.ef` = accuracy 0.5164, wins 63, losses 59, **real 0**, **shadow 122**, basis LOCAL_FROM_FILLS, local_pnl +57.4738, real_pnl 0.0, shadow_pnl +57.4738 — real/shadow split behaving as specified on a no-credentials process.
`orders.lane`: column present. The 143 rows that predate this build read NULL (added by migration, not backfilled — correct, nothing was rewritten). **First new order after the restart carries it: 12:12:48, kind MAIN, FILLED, `lane='PAPER'`.**

**12.19.0 / 12.20.0 latency_breakdown, for the record — the window is unusable and will stay that way in paper.** Captured from a `backup()` snapshot at 12:0x before this restart.
`--since 1790077238` (12.19.0 restart, spans 12.19.0 + 12.20.0, 11:40:38 → 12:10:20, ~30 min): orders with timing **4**, all FILLED. decision_ms p50 0.4 / max 0.4; quote_wait_ms p50 0.0; sign_ms p50 0.1 / max 0.2; final_recheck_ms p50 0.1 / max 0.2; fire_to_submit_ms p50 0.7 / max 1.0; submit_ms p50 0.2 / max 0.2; total_attempt_ms p50 1.0 / max 1.2; book_age_ms p50 14.0 / max 51.1; pre_submit_book_age_ms p50 14.7 / max 51.7; signal.ts→order.ts p50 1 ms; by attempt {1: (4,4)}.
`--since 1790078469` (12.20.0 only, 12:01:09 → 12:10:20): **orders with timing 0** — no order fired in that 9-minute window, every stage reports `none`.
Why this cannot be fixed by waiting: `PaperBroker.post()` fills in-process against the local book, so `submit_ms` measures a function call, not a venue round trip — p50 **0.2 ms** here against **255 ms** on the live journals (`live_zurich_3`, n=402). Paper latency numbers are not comparable to live and should not be used to judge the 12.19.0 fast-path work. That needs a live run, or a separate harness that times the SDK call directly.
 12.21.1 (09-22 12:3x UTC) - a shadow order is not gated by the live wallet's cash

Owner, 12:3x, on the Zurich paper dashboard still reading PAPER: "Still not the one update?? The master off = paper and
master onn = live". The 12.21.0 routing was there; the Zurich process runs with the credentials stripped, so it can only be
PAPER. Starting it WITH credentials makes master OFF = SHADOW - but the runner's four cash checks ("cash unknown or stale",
"stake exceeds free cash", and the EF equivalents) read the venue balance, and the Zurich live wallet holds $1.65 < the $3
stake: every shadow order would have been dropped. `_routing_live()` (Executor.route()[1]=='LIVE') now guards all four; a
venue order is gated exactly as before. Tests +1 (438), SHA256SUMS 37.
Rollout on Zurich: a NEW process with the four credentials in its environment (`--live`), a NEW db (the paper journal's
identity is PAPER and the 09-21 live journal is closed), boots master OFF = SHADOW; the paper process stops. The owner arms
master from Trade Controls when they want the venue.

 12.21.2 (09-22 14:5x UTC) - the EF decide-stage gate prices a shadow order the way it will be placed

Zurich live4 (12.21.1, SHADOW, 13:16 -> 14:46): 372 decides, 0 fires. Not the cap, not EV (214 padded-EV reads, p50 +0.035,
161 > 0), not the floor (unset). `_gate_on_padded_ev` calls `order_plan` with the bare decision, so `min_topup` was absent
at the decide stage and next_stake 1.0 on the fresh journal died 8 times as "below venue minimum; stake not increased" -
before `Executor.fire` (which does set min_topup per lane since 12.21.0) ever saw it. The gate now passes
`min_topup = not self._routing_live()`: shadow may top up to the 5-share minimum, live never does. Tests +1 (439),
SHA256SUMS 37. Note for the owner: the fresh live4 journal reset next_stake to 1.0 (paper1 had 5.47); live stake is theirs.

 12.21.3 (09-22 15:0x UTC) - the page header follows the route, not the --live flag

Owner, 15:56 BST screenshot of Zurich live4 (12.21.2, master OFF): header "PnL · LIVE" - "Master off paper is not working
properly??". Master was OFF and every order routes to shadow; the header string is rendered server-side at page load from
`self.r.a.live` (poly_dashboard.py:599), the one place 12.21.0 missed. It now renders `lane_label()` (LIVE / SHADOW / PAPER)
and the dashboard JS updates `#buildStamp` from `/api/state` `lane` on every refresh, so arming or disarming master changes
the header without a reload. Tests +1 (440), SHA256SUMS 37. Nothing in the order path changed.

 12.21.4 (09-22 15:5x UTC) - the combined card's real/shadow split comes from the orders' lanes

Owner, 15:4x: "still not proper, recheck the code". Zurich's read-only audit of the deployed 12.21.3 on live4: the per-lane
cards were right (ef real 0 / shadow 3 / -6.95, main real 0 / shadow 1 / +0.71) but the COMBINED card read
"real 4 · shadow 0 · 0.00" - `poly_dashboard.py:559` classified real-vs-shadow by the --live flag, the same class of
defect as the header. `Journal.metrics_for(lane)` counts settled candles by the lane of their fills with that lane's pnl
column; the combined card uses it (headline = venue fills when any, else shadow). `_shadow()`'s no-lane fallback is the
route, not the flag. Zurich also verified: route()/fire() never touch self.broker with master OFF, grade() keeps shadow pnl
out of results.pnl (4 rows: pnl 0.00, shadow_pnl -6.24), live4 has exactly one master write, None -> False at boot.
Tests +1 (441), SHA256SUMS 37. Nothing in the order path changed.

 12.22.0 (09-22 16:xx UTC) - EF reversal lane (poly_ef) + ef_engine switch; the last three flag-based money labels

Owner, 16:0x: "You still did not work on ef right? It still follows your old goal?? ... Shame on you, do it" and "test test
test and improve, use the data that we hold". EF's goal (owner, 09-22): "wait for the reversal to happen ... catch that
reversal before anyone else does and fire ... buy cheap shares", settled the Polymarket way (TWAP60).
Change:
- `poly_ef.py`: build11's legacy EF decision structure (map: old-side exhaustion, control transfer, settlement feasibility,
  the real/fake reversal classifier, 12 gates at the EF_* anchors, the 250 ms confirm latch, one per candle), side
  contrarian to the move against the SETTLEMENT LINE (`ref_open`, TWAP60), sigma = build11's 120 s RMS of 1 s returns,
  flow scaled by the lane's own rolling RMS. Added for Polymarket: the price rule (ask <= EF_MAX_ASK 0.60 and settlement
  probability >= ask + 0.06 + fee). Not ported: perp lane, aged depth history, EFLearner, frequency controller.
- `poly_lanes.LaneEngine`: raw tick tape, `set_line()`, `_try_ef()` after MAIN/REVERSAL in `evaluate()`, `still_valid('EF')`,
  `confirm('EF')`, `ef_monitor()`; off unless `ef_enabled`.
- runner: `ef_engine` control ('v10' default | 'build11'); with build11 the v10 call is kept as a shadow reason and the
  lane fires EF through the same executor path (allowed('EF'), lane_cap price rule). Set via /api/controls/apply
  `system.ef_engine` (audited) - no UI button yet.
- Zurich audit fixes: claim_status PAPER unless a venue fill; shadow bankroll = capital + shadow pnl (equity());
  venue headline only when routing LIVE.
Stored-data test (analysis/v/model/EF_REVERSAL_RESULT.md, replay_lanes_1s.py over 2,460 candles 09-08..09-16 with the
venue tape): the lane as built -0.142/$1 (n130); the real-score grid is monotone (+0.05 -> +0.20) BUT fails permutation
(p 0.31-0.33), costs (+0.05 -> negative) and paired-vs-REVERSAL (negative on every candle REVERSAL does not trade). No edge
of its own on this data. The harness reproduces MAIN (-0.02) and REVERSAL (+0.46) as seen live.
Tests: test_ef.py +14, test_master_lane +2 = 457 green (187 + 270). SHA256SUMS 37 -> 39.
Rollout: Zurich SHADOW with ef_engine=build11 for a forward read with the full live features (depth, book) - the inputs the
stored data lacks. v10 EF stays the default everywhere else; nothing live.

 12.23.0 (09-22 19:xx UTC) - EF lane: the perp feed, the depth history and the 120 s memory; tape1s recorder

Owner, 19:0x: "Then port the perp feed and depth history too, test that."
- `poly_ef.DepthHistory`: aged top-20 snapshots (9 s), zone imbalances 1-5 / 6-10 / 11-20, replenishment against the
  0.8-1.8 s old snapshot (build11 side_change, matched levels + meaningful best shifts), event OFI against the 0.12-0.8 s
  old one, microprice. The runner's "depth" stream IS the perp depth20@100ms, so this is build11's perp book.
- `poly_ef.PerpMemory`: build11's one-second history (delta, price_eff, book zones, replenishment) over 120 s and
  `_memory_for_direction` verbatim (old aggression, futility, aggression/effectiveness decay, control/book handoff,
  exhaustion score, deep persistence; constants 1021-1039). Applied as build11 does: bounded shifts on exhaustion
  (+-0.06), persistence/transition/book (+-0.05), fake (-), real (+).
- `ef_metrics(..., micro)`: PERP is the microstructure source when >= 3 perp trades in 5 s and the newest <= 1.5 s old
  (flows, flow profile, paths from the perp tape; book_signed = 0.48 near + 0.24 deep + 0.12 replenishment + 0.10 OFI +
  0.06 microprice); spot stands in otherwise. Reports micro_source / memory_ready / book_age_ms in the EF monitor.
- runner: `on_perp` now forwards perp trades to the lane engine; `tape1s` table (one row per second: spot px/buy/sell,
  perp px/buy/sell, bid/ask depth 5 and 20, Chainlink ref, venue asks) written from decide_loop, 7-day retention - so the
  next replay has the inputs the stored klines lack. ~86k rows/day.
Tests: test_ef +4 (58), housekeeping delete count 2 -> 3. All suites green. SHA256SUMS 39.
Rollout: Zurich SHADOW (ef_engine=build11), then read the EF monitor for micro_source=PERP and memory_ready before
counting any fire; Mumbai paper the same build to grow the tape.

### London box (eu-west-2) - E-0a measured 09-22 21:03 UTC (written by V; the London session cannot push)
Session "London" session_01S5RwxZdQUWbVVn49A5TrgX. c6i.large, 2 vCPU, 3814 MB, Python 3.12.3, Ubuntu 24.04; AZ not readable
from the session sandbox. Repo at a2da255 (contains 12.23.0 e34549d). /home/ubuntu/pm_london = learner/v12_2, SHA256SUMS
39/39, 45 tests OK. deploy.env present (18 lines, never read by any session).
E-0a, `curl https://clob.polymarket.com/time` x10 from London: dns 0.0004, connect 0.0016-0.0044, TLS 0.026-0.044,
first byte 0.041-0.059 (p50 ~0.049). Zurich for comparison: connect 0.0018, TLS 0.033, first byte 0.075. So a warm GET
from London is ~15 ms vs ~40 ms from Zurich; the venue's own POST processing (~180 ms seen from Zurich) is the number the
SHADOW run's keepalive_ms and, later, live orders will show. Engine start (SHADOW, master OFF, dashboard 0.0.0.0:8787
behind DASHBOARD_PASSWORD) pending the London session's start at 21:0x.
**21:13 UTC - London box UNUSABLE for Polymarket.** Two boot exits: (1) 21:09 `poly_dashboard.py:45` DASHBOARD_PASSWORD 10 chars
(<12) - owner fixed to 16; (2) 21:13 `btc_model_v12_polymarket.py:1287` 'Venue geographic eligibility check did not pass':
`polymarket.com/api/geoblock` -> blocked:true, ip 13.40.72.11, country GB, region ENG. Polymarket blocks the UK. The check is a
hard eligibility gate and is NOT to be bypassed. Nothing ran, no orders, no dashboard. Zurich (CH, eu-central-2) stays the only
live-credentialed box. Owner to pick a permitted region near eu-west-2 (Ireland eu-west-1 or Frankfurt eu-central-1, ~10-15 ms
to London; France/Belgium are blocked) or ask Polymarket whether its whitelist covers the geoblock endpoint.
**21:26 UTC - owner pasted Polymarket's whitelist email (eu-west-2) to the London session; London proceeded.** Owner, 21:2x:
"london is geographically blocked but not our account specifically". 12.23.1 (4773b94) adds VENUE_GEO_WHITELIST=1: boot
proceeds on a geo-flagged box only with the flag, the geoblock answer is written to diagnostics (GEO_WHITELIST_OVERRIDE),
default stays a hard stop.
| 12.23.1 | 4773b94 | 2026-09-22 21:26 UTC | eu-west-2 (London) 13.40.72.11 | 39/39 == git show, suites 393 OK (London) | pid 2700, polymarket_v12_london_1.sqlite3, master OFF (SHADOW), 0.0.0.0:8787 (401 auth) | [GEO] blocked:true GB logged, flag set; no CLOB refusal at open/snapshot; keepalive_ms 16.2 (Zurich ~40); sign inline; ef flag false at start | written by V from the London session's report |
| 12.23.1 | 4773b94 | 2026-09-22 21:56 UTC | eu-west-2 (London) 13.40.72.11 | same files | **systemd pm-london active, pid 3547, master ON -> lane LIVE** | owner approved in the London session (21:5x). Audit 913 stake_settings fixed 3/3/3 (next_stake 3.0), 946 master false->true; cash 39.548; EF ON build11 (micro PERP, memory_ready), MAIN/REVERSAL OFF; Zurich stays master OFF (same wallet). First LIVE order to be reported once; ledgers 4-hourly from 01:30 UTC | written by V from the London session's report |
| 12.24.1 | d90c1c9 | 2026-09-22 22:40:40 UTC | eu-central-2 (Zurich) | 39/39 == git show, nine suites 463 OK | pid 152214, live4 db, master OFF (SHADOW) | calibration audited None -> {enabled, mode platt, a 1.0677, b -0.3208} (H1 EF_BRAIN.md D); ef_engine v10 (since 22:17:59, build11 out); ledger 01:30 UTC: EF fires removed by calibration + n/hit/per$1 | written by V from the Zurich session's report (analysis/zurich/z_12214_alive_audit.md d6a02da) |
| 12.24.3 | b7cb8bd | 2026-09-22 22:50 UTC | eu-west-2 (London) 13.40.72.11 | 39/39 == git show, suite 452 OK | systemd pm-london pid 5422, master ON -> LIVE | owner's in-terminal go; backup bak_12.23.1_*; meta unchanged across restart (master T, main F, reversal T, ef F, build11, stake 5); cash 47.145. Carries 12.23.2 (last-fill card every lane), 12.24.0/1 (Platt hook, OFF here), 12.24.2 (MAIN one-shot guard removed), 12.24.3 (master persists across boots). First LIVE fills: 1790115600 MAIN DOWN 11.43 sh @0.42 won; 1790116500 REVERSAL filled | written by V from the London session's report |
| 12.24.5 | 2b1c90d | 2026-09-22 23:42 UTC | eu-west-2 (London) | 39/39, suite 456 OK | systemd pm-london pid 6331, LIVE | owner go; meta unchanged (master T, main F, rev T, ef F, stake 5); first BLOCKED call recorded: 1790120700 MAIN UP p 0.8335 quote 0.98 sec 209. The restart lost the candle's REVERSAL (00:40:54 UP) on the card -> fixed in 12.24.6 (2c30404), not yet deployed | written by V from the London session's report |
| 12.24.8 | 08b7f8e | 2026-09-23 00:05:06 UTC | eu-west-2 (London) | 39/39, suite 463 OK | systemd pm-london pid 7286, LIVE | owner go; carries 12.24.6-12.24.8 (restart restore, settlement seed, transient drops, floor persistence, call grading, lane labels, master re-read before post, rev cap on retries, paper quote age); meta unchanged (master T, main F, rev T, ef F, stake 5); cash 44.62; '[REF] settlement line seeded from tape1s: 1180 s', line_open 86216.48 chainlink vs bn_line_open 86160.01 | written by V from the London session's report |
| 13.0.0 | 702ec24 | 2026-09-23 01:05:30 UTC | eu-central-2 (Zurich) | 39/39, 464 OK | pid 153702, SHADOW | profile raw_v10_live25 (calibration off, ev fixed 0.25), stake 5; ledger clock 01:05:55 | written by V from the Zurich session's report |
| 13.0.0 | 702ec24 | 2026-09-23 01:10 UTC | eu-west-2 (London) | 39/39, 464 OK | systemd pid 9146, LIVE | owner's order 01:0x 'keep raw on london', told the $84 paper DD exceeds the wallet; profile raw_v10_live25 (audit 6555-6557); reversal_enabled T->F at 01:09:44 from the dashboard; EF only live; cash 36.85 | written by V from the London session's report |
| 13.0.2 | accc8bd | 2026-09-23 11:40 UTC | eu-west-2 (London) | 39/39, 474 OK | systemd pid 48836, LIVE | owner go; fast path [fast] uvloop 0.22.1 / sign inline coincurve 21.0.0 / h2 4.4.1; keepalive 25.6 ms, book 23.0 ms; stake found on ladder since 02:40:08 (dashboard) -> fixed $5 on owner's order |
| 13.0.3 | 4953cd3 | 2026-09-23 12:45 UTC | eu-west-2 (London) | 39/39, 475 OK | systemd pid 51588, LIVE | owner go; REST book read after every FAK refusal; first EF on it 1790169000 filled att 2 via rest_changed (0.36, $4.78) |
| 13.0.3 | 4953cd3 | 2026-09-23 13:33:26 UTC | eu-west-2 (London) | - | pid 51588, LIVE | profile fixed15 -> raw_v10_live25 (owner, 13:3x: 'Do raw in london live and fixed in Zurich'); master ON, EF only, $5 fixed, no floor |
| 12.21.4 | 5ac70b2 | 2026-09-22 15:50:35 UTC | eu-central-2 (Zurich) | 37/37 == git show, test_master_lane 14 OK | pid 149446, live4 db, master OFF (SHADOW) | combined real 0 / shadow 5, shadow_pnl -7.352842941176469 == sum(results.shadow_pnl); :559 fixed | written by the Zurich session |
| 12.22.0 | 3357a90 | 2026-09-22 19:05:54 UTC | eu-central-2 (Zurich) | 39/39 == git show, test_ef+test_master_lane 30 OK | pid 150792, live4 db, master OFF (SHADOW) | ef_engine None->build11 audited 19:05:54; ef_monitor 'EF engine build11 (lane)', lanes.ef.enabled true, line_open 86449.27 | written by the Zurich session |
| 12.23.0 | e34549d | 2026-09-22 19:30:23 UTC | eu-central-2 (Zurich) | 39/39 == git show, test_ef+test_master_lane 34 OK | pid 151129, live4 db, master OFF (SHADOW) | micro_source PERP, memory_ready true, perp_ticks_32s 629->2021, depth_rows 83->89, tape1s 0.98 rows/s; ef_engine build11 carried in meta | written by the Zurich session |
| 12.24.1 | d90c1c9 | 2026-09-22 22:40:40 UTC | eu-central-2 (Zurich) | 39/39 == git show, all 9 suites 463 tests OK | pid 152214, live4 db, master OFF (SHADOW) | calibration None->platt a=1.0677 b=-0.3208 audited 22:40:40; ef_engine stays v10; fit lowers p below its 0.9913 fixed point, 0.55->0.4734 | written by the Zurich session |
| 13.0.0 | 702ec24 | 2026-09-23 01:05:30 UTC | eu-central-2 (Zurich) | 39/39 == git show, all nine suites 464 OK | pid 153702, live4 db, master OFF (SHADOW) | profile raw_v10_live25 applied 01:05:55: ef_profile None->raw_v10_live25, ev_settings 0.15->0.25, calibration enabled True->False; ef_engine already v10 (no row); stake fixed 5 untouched; '[REF] settlement line seeded from tape1s: 1184 s' | written by the Zurich session |
| 13.0.0 (profile switch) | 274b2df | 2026-09-23 13:33:37 UTC | eu-central-2 (Zurich) | no deploy, audited control writes only | pid 153702, live4 db, master OFF (SHADOW) | owner: "Do raw in london live and fixed in Zurich". ef_profile raw_v10_live25->fixed15, ev_settings 0.25->0.15, calibration enabled False->True; ef_engine v10 and stake 5 unchanged. CLOSED raw arm 01:36:04->13:33:37: n 50, right 58.0%, per$1 +0.328, pnl +79.21 at $5, maxDD 27.05, losing run 6 - closed 10 short of the 60-fire bar, not a reading | written by the Zurich session |
| 13.0.0 (profile switch) | 274b2df | 2026-09-23 14:07:23 UTC | eu-central-2 (Zurich) | no deploy, audited control writes only | pid 153702, live4 db, master OFF (SHADOW) | owner: "Changed my decision bro do fixed in live and raw in Zurich i don't wanna get much drawdowns". ef_profile fixed15->raw_v10_live25, ev_settings 0.15->0.25, calibration enabled True->False; ef_engine v10 and stake 5 unchanged. fixed15 window 13:33:37->14:07:23 (33 m 46 s): 5 EF orders, 5 fills, 4 graded - closed too small to read. Raw arm RESUMES as a stitched series, windows 01:36:04-13:33:37 and 14:07:23-open | written by the Zurich session |
| 13.0.4 | 6885af4 | 2026-09-24 12:20:05 UTC | eu-central-2 (Zurich) | 39/39 == git show, all nine suites 477 OK | pid 166436, live4 db, master OFF (SHADOW) | owner-approved per-second decision logging, LOGGING ONLY: no model/profile/EV/stake/flag change (raw_v10_live25, ev 0.25, calibration off, stake 5 all untouched). decide_log set true 12:20:30. 10 min: 2360 rows, 238/min, 0 fires, decide_log_features 44, feats len matches, error ''. feats non-null 2.3% over the whole window but 63.5% post-warm-up - the gap is 1641 warm-up rows + 665 'waiting for fresh UP and DOWN books', both p NULL by design. Disk 21G free vs ~600 MB for 4-day retention | written by the Zurich session |
| 13.1.0 | 54f8ef0 | 2026-09-24 14:20:01 UTC | eu-central-2 (Zurich) | 39/39 == git show, sha256sum -c clean, all nine suites 482 OK | pid 167283, live4 db, master OFF (SHADOW) | owner-approved SHADOW test of event-driven decide. decide_mode set 'event' 14:20:27; raw_v10_live25 / ev 0.25 / calibration off / stake 5 / decide_log true all unchanged. 10 min: decide_log 3.82/s (throttled by design, NOT the fast-pass rate), 0 decide_loop_error rows, error field '', engine alive. Revert is Journal.set('decide_mode','poll'), no restart. London and Mumbai untouched | written by the Zurich session |
| 13.1.1 | a881350 | 2026-09-24 15:15:03 UTC | eu-central-2 (Zurich) | 39/39 == git show, sha256sum -c clean, all nine suites 484 OK | pid 168424, live4 db, master OFF (SHADOW) | owner "switch to 50ms now", replacing the after-10-orders gate. decide_min_gap_ms left UNSET so the code default applies: DECIDE_MIN_GAP_S=.05 = 50 ms. decide_mode event, decide_log true, raw_v10_live25 / ev 0.25 / calibration off / stake 5 all unchanged. Closes the 20 ms arm at n=2 (book_age p50 56.4 / p90 91.6) - not a comparison. Both 13.1.1 changes came from Zurich 13.1.0 reports: the 50 ms dial from the 2.1x CPU finding, the first-fire-only decide_log from the 117-rows-per-candle artifact | written by the Zurich session |
| 13.1.2 | 327de5f | 2026-09-24 19:30:02 UTC | eu-central-2 (Zurich) | 39/39 == git show, sha256sum -c clean, all nine suites 485 OK | pid 169816, live4 db, master OFF (SHADOW) | owner "do on shadow Zurich whatever you want". Adds feed_timing on every fired EF decision ({spot,perp,depth,venue}_rx_age_ms, *_exch_age_ms, newest_rx_age_ms, decide_mode). A/B started 19:30:02 on the EVENT arm, decide_mode flipped every 60 min by Journal.set with no restart (out/ab_flip.py, flips logged to out/ab_flips.jsonl). All settings unchanged: raw_v10_live25, ev 0.25, calibration off, stake 5, decide_log true, decide_min_gap_ms unset = 50 ms code default. Arm membership is read from each order's OWN feed_timing.decide_mode, not from flip bookkeeping | written by the Zurich session |

