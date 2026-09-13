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
