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
