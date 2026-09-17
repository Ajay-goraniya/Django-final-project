# v12_2 engine audit: dead code, overlapping logic, leftovers, config dials

Scope: `learner/v12_2/{btc_model_v12_polymarket.py, poly_core.py, poly_live.py, poly_feeds.py, poly_lanes.py, poly_dashboard.py, btc_model_v10.py, btc_model_v10_runner.py}` at HEAD c01c455 (build string 12.8.11, poly_core.py:397). Tests = `test_v122.py, test_polymarket.py, test_lanes.py, poly_selftest.py, audit_paper.py`.
Method: every `def`/`class` in the 8 modules (244 total) was counted for `name(` and `.name` references across the 8 modules with definition lines excluded (script output kept in the session scratchpad), then every zero/low-count hit was hand-checked with `grep -n` because same-named methods (`grade`, `main`, `positions`, `decide_loop`) collide. **Nothing was modified.** Line numbers are from HEAD c01c455. "UNSURE" is used where I could not prove it from the code alone.

Read-first verdict: the engine has very little dead *function* code. What it has is (a) one whole standalone runner path that the live engine bypasses, (b) several observation-only subsystems that still run queries every 1-5 s, and (c) two places where the live order path takes the same decision from two different settings (quote age: CLI vs meta; depth check: gate vs executor).

---

## 1. Dead code

### 1a. Never called from any of the 8 modules

| name | file:line | size (lines) | proof (modules) | tests |
|---|---|---|---|---|
| `BookCache.clear` | poly_core.py:116 | 1 | `grep -n '\.clear()'` in modules: only the def itself; the word "clear()" at poly_core.py:120 is inside `prune`'s docstring. `self.books.clear()` never appears in v12/dashboard. | test_polymarket.py:42,44 (2 calls) - test-only |
| `PaperBroker.account_snapshot` | poly_core.py:843 | 1 | `grep -n 'account_snapshot('`: callers at btc_model_v12_polymarket.py:424 and :732 are both inside `if self.a.live:` (lines 423, 722), so the broker is `LiveBroker`; poly_live.py:226 is `LiveBroker.venue_truth` calling its own. | 0 calls in tests. **Dead everywhere.** |
| `Journal.live_reserve` branch `venue_verified=False` | poly_core.py:726-727 | 2 | all 3 callers (btc_model_v12_polymarket.py:259, :362, :466) pass no argument. | test_v122.py:244 only |
| `Dashboard.feed_state` fallback `if h is None:` | poly_dashboard.py:84-87 | 4 | `PolyRunner.__init__` always sets `self.health` (btc_model_v12_polymarket.py:40); no code deletes it. Only reader of `r.age` is in this branch (poly_dashboard.py:85). | test_v122.py:1835 sets `r.health` to a namespace, so the branch is not exercised there either. |
| `Dashboard` getattr/hasattr fallbacks: `hasattr(self.r,'ev_setting')` :162, `hasattr(self.r,'pad_ticks')` :163, `hasattr(self.r,'m')` :164, `getattr(self.r,'EV_MODES',...)` :166 and :324, `getattr(self.r,'CALIBRATION_DEFAULT',...)` :308-309 | poly_dashboard.py | 6 fallback literals | `PolyRunner` defines all five (btc_model_v12_polymarket.py:629, 675, 24, 628, 175). The fallback literals duplicate the runner's constants (see 2.9). | tests construct `PolyRunner` (test_v122.py:449,557,575; test_polymarket.py:565) - fallbacks unexercised |
| `PolyRunner.age` dict | btc_model_v12_polymarket.py:38 (writes :78, :81, :709) | write-only state | only reader is the dead branch poly_dashboard.py:85 (`grep -n 'r\.age\|\.age\['`). `FeedHealth.arrival` (poly_feeds.py:110) is what is actually read. | test_v122.py:1835 assigns `r.age={}` - not a read |
| `PolyRunner.msgs` dict | btc_model_v12_polymarket.py:38 (writes :117, :710) | write-only state | no reader in modules (`grep -n '\.msgs\b'`: the reads at poly_feeds.py:121,168 are `FeedHealth.msgs`, a different dict). | poly_selftest.py has 1 `.msgs` hit - UNSURE whether it is `r.msgs` or `health.msgs` |
| `Executor.fire` local `seq` | poly_core.py:883 (`seq=-1`), :900 (`seq=q['seq']`) | 2 assignments | never read after assignment; the `latest['seq']!=seq` compare was removed in 12.8.7 (comment :944-951). `plan['seq']` (:345) is only journaled. | - |
| `poly_lanes.Model.version` | poly_lanes.py:188 | attribute | written from a `version` kwarg that no caller passes (`LaneEngine.__init__` :215 passes `weights` only); never read (`grep -n '\.version' poly_lanes.py` = 1 hit, the write). | poly_selftest.py:1 hit, UNSURE |
| `model_weights` meta row (promised by poly_lanes.py:35-36 docstring) | - | - | `grep -n model_weights` over non-test modules: the docstring only. Nothing loads drifted weights; `LaneEngine()` is constructed with no weights (btc_model_v12_polymarket.py:48). | - |
| `ARRIVAL_LIMITS['venue']` / env `FEED_MAX_ARRIVAL_VENUE_S` | poly_feeds.py:86 | 1 | `stale()` is only ever called with `('spot','perp','depth')` (btc_model_v12_polymarket.py:148, poly_dashboard.py:89) or `('spot','depth')` (:318). The venue arrival/lag written at btc_model_v12_polymarket.py:82 is displayed (snapshot) but never enforced; venue freshness is enforced by `BookCache.quote` max_age instead. | - |

### 1b. Reachable only when `btc_model_v10_runner.py` is run standalone (the Polymarket engine never enters them)

`PolyRunner(Runner)` does **not** call `super().__init__` (`grep -n 'super().__init__'` over modules = 0 hits) and overrides `resolve_market` (:56), `venue` (:85), `decide_loop` (:235), `grade_loop` (:570), `main` (:721). From the runner it uses only `Runner.on_spot` (:127 via super), `Runner.on_perp` (passed at :740), `Runner.on_depth` (:131 via super), `http_json`, and the constants `GAMMA/CLOB/POLY_WS/US`. No test imports `btc_model_v10_runner` (grep = 0).

| name | btc_model_v10_runner.py:line | size | only caller |
|---|---|---|---|
| `Store` (+ `trade`, `decision`, `ungraded`, `grade`, `stats`) | 46-95 | 50 | `Runner.__init__`:103 |
| `Runner.__init__` | 99-112 | 14 | `Runner(a)` at :362 (`__main__`) only |
| `Runner.ws` | 115-125 | 11 | `Runner.main`:345-347 |
| `Runner.resolve_market` | 152-170 | 19 | overridden; `Runner.venue`:225 only |
| `Runner._publish_venue` | 172-188 | 17 | `Runner._apply_ws`:215 |
| `Runner._apply_ws` | 190-215 | 26 | `Runner.venue`:255 |
| `Runner.venue` | 217-260 | 44 | overridden; `Runner.main`:348 |
| `Runner.decide_loop` | 263-300 | 38 | overridden; `Runner.main`:348 |
| `Runner.grade_loop` | 302-323 | 22 | overridden; `Runner.main`:348 |
| `Runner.serve` (+ class `H`) | 326-339 | 14 | `Runner.main`:342 |
| `Runner.main` | 341-348 | 8 | `__main__`:362 |
| module `FEE`, `cost` | 34-35 | 2 | `Runner.grade_loop`:318 only |

Net: 265 of the runner's 364 lines are outside the live path. This is not "dead" in the repo sense (the file is a working standalone paper runner) but it is dead weight *inside the live process*: `class Runner` is imported solely for three `on_*` handlers and four constants.

### 1c. Reachable only via CLI/test switches

| name | file:line | size | reached by |
|---|---|---|---|
| `btc_model_v10._selftest` | btc_model_v10.py:287-320 | 34 | `--selftest` (:324-325); poly_selftest.py references it |
| `Model.decide(conf_floor=, ev_floor=)` | btc_model_v10.py:230-231, 265-266 | params | v12 passes only `mode`, `ev_threshold` (btc_model_v12_polymarket.py:157-159); model-file floors are used instead |
| `PaperBroker.post` `else: self.pending[oid]=f` and `PaperBroker.reconcile`'s `pending.pop` | poly_core.py:838, 841 | 2 | only when `db is None`; `PolyRunner` always passes `self.db` (:33). Tests build `PaperBroker(self.books)` without db (test_polymarket.py:83,346,370,458). |
| `Executor.require_depth` default `True` in `getattr(broker,'all_or_nothing',True)` | poly_core.py:853 | - | both brokers define `all_or_nothing=False` (poly_core.py:827, poly_live.py:19) so the executor never runs the depth block - but see 2.2: the EV gate does. |
| never-overridden parameters: `FeedHealth.stale(max_arrival, max_lag)` :145, `limit_for(override)` :141, `run_stream(event_key, urls)` :176, `rest_json(timeout, hosts)` :93, `LiveBroker.positions(status)` :148, `LiveBroker.account_pnl(interval)` :197, `Journal.conditions_awaiting_venue(limit)` :589, `Journal.rolling(windows)` :615, `Journal.mark_venue_open(now)` :673, `FeatureState.on_depth(is_crossed)` btc_model_v10.py:97 | - | defaults only from every module call site (grep each name; no keyword passed) |

### 1d. Checked and NOT dead (listed because they look dead by name)

`Journal.halt_check` (called btc_model_v12_polymarket.py:579 and poly_core.py:1048), `_wipeout_check` (:431), `_main_oneshot_check` (:567), `_sample_ambient_age` (:432), `_flush_wait_census` (:433), `_count_wait` (:77), `Journal.rolling` (poly_dashboard.py:527), `Journal.kill_window` (poly_core.py:631, :808), `slippage_band`/`SLIPPAGE_BANDS` (poly_core.py:265, reachable via `ev_settings.slippage_mode='band'`), `Model.decide` accuracy branch (btc_model_v10.py:264-275, reachable via `ev_settings.mode='accuracy'` at btc_model_v12_polymarket.py:158), `PolyRunner.on_kline` (passed at :740), `Journal.set_many` (poly_dashboard.py:271, :371), `LiveBroker.metadata/cash/redeem/claim_state` (live housekeeping/claim loops). All of poly_lanes is reached every decide pass through `lane_loop` (:275 -> :320 `self.lanes.evaluate`).

---

## 2. Overlapping / duplicate logic

Legend for "status": LIVE = on the real order path; OBS = observation-only (writes a row / dashboard field, changes no decision); DEAD = unreachable.

### 2.1 Quote-age: two settings, both on the live path

| control | value | read at | what it decides | status |
|---|---|---|---|---|
| CLI `--quote-age-ms` (default 750, bounds 0<x<=2000 at :762) | `self.a.quote_age_ms` | btc_model_v12_polymarket.py:75 `publish()` | whether the model gets a venue quote at all; the "Waiting for fresh UP and DOWN books" refusal (:147); the `ask` the model decides on (`st.on_venue_quote` :80 -> `_ask_up/_ask_dn` btc_model_v10.py:190) | **LIVE** |
| same | | :34 `Executor(...,a.quote_age_ms/1000,...)` | initial `Executor.age` | overwritten every pass by :664 -> effectively DEAD |
| same | | :669 | fallback inside `quote_age_s()` when meta value missing/invalid | LIVE fallback |
| same | | poly_dashboard.py:483 | book panel | OBS |
| meta `ev_settings.quote_age_ms` (set poly_dashboard.py:333-341, bounds 0<qa<=2000) via `quote_age_s()` :665-670 (clamp 1 ms..2.0 s) | | :225 `_gate_on_padded_ev`; :347 lane ask capture; :664 -> `Executor.age` used at poly_core.py:896 and :952 | EV gate quote, executor's submit quote and pre-submit re-read | **LIVE** |
| `BookCache.quote` default `max_age=.75` (poly_core.py:186) | | poly_core.py:833 `PaperBroker.post` calls `quote(token)` with no age | paper fill price | paper-only |

Finding: the live path uses **both** sources at once. `publish()` never reads the meta value, contrary to the comment at poly_dashboard.py:334-338 ("It gates publish(), the EV gate and the executor at once"). If meta > CLI, `publish()` still refuses at the CLI limit; if meta < CLI, the model can decide on a quote the executor then treats as stale and waits on until DEADLINE (poly_core.py:895-899). Which one binds is the smaller of the two; today (meta unknown from code) mark **UNSURE** which value the live box has in meta - check `SELECT v FROM meta WHERE k='ev_settings'` on the live DB, and compare with the launch flag.

### 2.2 decide_now()/publish() vs the executor's own quote read (and the depth check)

Per fire attempt the same quote/EV question is asked repeatedly:

| step | quote() call | age used | EV judged at | code |
|---|---|---|---|---|
| decide_now -> publish | 2 (UP, DOWN) | CLI | model: raw ask, `ev >= threshold(f)` (btc_model_v10.py:262-280) using `m.fee` from model_v10.json (0.07) | btc_model_v12_polymarket.py:75, 157 |
| decide_now -> _gate_on_padded_ev | 1 | meta | `order_plan`: ask + `EV_REFERENCE_PAD`(1 tick), venue `terms` rate/exp, **`require_depth` defaulted True** | :225-229, poly_core.py:294-298, 314-321 |
| Executor.fire first read | 1 (loop until fresh) | meta | - | poly_core.py:896 |
| reassess() = decide_now again | 3 | CLI + meta | model + gate again | :273 lambda, poly_core.py:910 |
| order_plan(q) | - | - | EV again, `require_depth=False` | poly_core.py:921 |
| latest read | 1 | meta | - | :952 |
| reassess() again | 3 | CLI + meta | model + gate again | :955 |
| order_plan(latest) | - | - | EV again, `require_depth=False` | :957 |

So the initial `decide_now` costs 3 quote() reads and 2 EV judgements, and then **each `fire()` attempt costs 8 more quote() reads and 6 more EV judgements** (11 reads / 8 judgements for a one-attempt fire). The arithmetic agrees (model's `ps*(1/cost-1)-(1-ps)` == `p/cost-1`, and `order_plan`'s `max(px+f, px/(1-f/px))` equals the model's `q/(1-fee(1-q))` when `rate==0.07` and `exponent==1`), **but the fee sources differ**: the model pre-filter uses `model_v10.json fee_rate=0.07`; the gate and executor use the venue's `fee_info.rate/exponent` fetched at poly_live.py:46. UNSURE whether the live venue rate is 0.07/exp 1 today; if not, the pre-filter and the gate disagree by construction.

**Real second decision point:** `_gate_on_padded_ev` calls `order_plan(q,terms,stake,d,pad,band=...)` **without `require_depth`** (btc_model_v12_polymarket.py:229), so the depth block poly_core.py:314-321 ("book too thin at cap") runs in the gate, while both executor calls pass `require_depth=False` (poly_core.py:921, :957; `all_or_nothing=False` on both brokers). The comment at poly_core.py:301-313 says the check "is off for both live and paper" and "could never bind" - it is off in the executor and **on in the gate**. With a $3 stake against ~$98 at the touch it will rarely bind, but it is a live refusal path the executor would not have taken. No grid was run here; this is a code-path statement only.

The gate also uses `pad_ticks()` for the cap (btc_model_v12_polymarket.py:227) while EV is judged at the fixed 1-tick reference in both places, so pad affects only `ev_gate_cap` and the "no executable ask at cap" branch (:300).

### 2.3 Halt / kill machinery after 12.8.8

| piece | file:line | size | called from / cadence | writes | status |
|---|---|---|---|---|---|
| `Journal.halt_check` | poly_core.py:757-823 | 67 | `grade_loop` btc_model_v12_polymarket.py:579 (20 s) **and** `Executor.reconcile` poly_core.py:1048 (1 s from `reconcile_loop` :564-569, plus 2x at startup :729) | one `KILL_CONDITION` diagnostics row per rule per episode (:822); never `halt` | **OBS** - but it runs 2 SQL queries (:780, `kill_window` :745) every second |
| `Journal.rolling()['kill']` | poly_core.py:652-669 | 18 | `Dashboard.snapshot` :527 on every `/api/state` (0.5 s cache) | dashboard field | OBS; duplicates halt_check's ALL and per-kind rules from the same `kill_window()` rows; halt_check additionally computes SLIPPAGE (:807) which rolling does not show |
| meta `halt` | set poly_core.py:1011 (order-id mismatch) ; cleared poly_dashboard.py:298 | - | read at `Executor.fire` :882 (blocks `reserve`), `allowed()` poly_dashboard.py:76, `apply` :254 (refuses arming master), display :239, :288-289, :527 | - | **LIVE** integrity stop. Checked twice per fire (allowed() at :257/:352, then :882). |
| meta `halt_cleared_at` | set poly_dashboard.py:297 | - | read `kill_window` :744, `halt_check` :779 | - | only shifts the OBS windows now |
| `_wipeout_check` | btc_model_v12_polymarket.py:439-485 | 54 | `housekeeping` :431 every 5 s, live only | one `LOW_BALANCE` row per episode (:478) | OBS; calls `live_reserve()` (3-row reserve query) every 5 s |
| `_main_oneshot_check` | btc_model_v12_polymarket.py:535-563 | 29 | `reconcile_loop` :567 every 1 s | **`db.set('main_enabled',False)`** :562 | **LIVE - NOT monitor-only.** Disarms MAIN after >=1 FILLED MAIN order since the last `control_write` arming row. While `main_enabled` is True it runs a `LIKE '%control_write%'` scan of `diagnostics` (:553) every second. |
| `Dashboard.allowed()` | poly_dashboard.py:74-76 | 3 | EF: :257 and inside the reassess lambda :273 (2x per attempt); lanes: :352, :373 | - | LIVE; six gates in one expression: `master`, per-kind flag, `halt`, `daily()` tp/sl (:59-64), `banned()` rules (:65-73), `sx_enabled`/`sx_until` |

### 2.4 reserve / live_reserve vs venue_state

| quantity | computed where | cadence | used by | status |
|---|---|---|---|---|
| `self.cash` | `housekeeping` :424-426 (`LiveBroker.account_snapshot` -> `get_balance_allowance`) | 5 s | fire eligibility :257/:269 and :353/:363; `_wipeout_check` :466; dashboard fallback :504 | LIVE |
| `self.cash` again | `venue_truth_loop` :695 (`venue_truth` -> same `cash()` call) | 20 s | same field, same source, second writer; both set `cash_at` | LIVE (redundant writer) |
| `self.cash` at startup | `main` :734 | once | | LIVE |
| `Journal.live_reserve()` = `reserve_detail()['effective']` | poly_core.py:698-728 | per call | :259 (every decide pass when EF wants to fire), :362 (every lane decision), :466 (5 s) | LIVE: `stake <= cash - reserve` is the fire check |
| `Dashboard.reserve_detail()` | poly_dashboard.py:509 | per snapshot | display | OBS (same query again) |
| `venue_state` (dict from `venue_truth`) | :694 | 20 s | `Dashboard.equity()` :118-120 -> `update_stake()` :125 -> `next_stake` (sizing); snapshot display :491-527 | LIVE for **sizing** only |
| `mark_venue_open` | :700 -> poly_core.py:673-697 | 20 s | `reserve_detail` phantom test :714; `LiveBroker.reconcile` ABSENT_PROOF poly_live.py:132-135 | LIVE |

Two bankroll definitions coexist on the live path: **sizing** uses `cash + open_value` from `venue_state` (equity, 20 s old), **firing** uses `cash - local reserve` (5 s old). Three "order is absent from venue" standards: `Journal.ABSENT_GRACE_S=5 / ABSENT_CONFIRMATIONS=2` (poly_core.py:671-672, reserve), `LiveBroker` 404 path `age>=2.0 and misses>=2` (poly_live.py:139), `LiveBroker.ABSENT_PROOF=3 / 60 s` (poly_live.py:10, unreadable get_order). Each is applied to a different question, so none is dead, but they are three thresholds nobody has gridded together.

### 2.5 "Age" definitions

| name | computed at | meaning | consumer | status |
|---|---|---|---|---|
| `age_ms` | `BookCache.quote` poly_core.py:203-205: `max(mono, min(wall_corrected, mono+max_age))` | book staleness | gate at :206 on **every** quote() call; journaled as `plan.age_ms` :345, `timing.book_age_ms` :900, `pre_submit_book_age_ms` :959; dashboard :485, :415 | **LIVE** (the only enforced venue-freshness number) |
| `snapshot_age_s` | quote :211; recomputed with the same formula in `housekeeping` :410 | seconds since last full `book` event | `timing.snapshot_age_s` :909; `feed_counters` row :412 | OBS (12.3.2 gate removed, comment poly_core.py:901-908) |
| `block_detail` age | quote :198-208 | age at the refusal | `_count_wait` :500 -> `WAIT_CENSUS` row :509 | OBS |
| `AMBIENT_AGE` | `_sample_ambient_age` :511-534 | raw `now - arrival`, unfiltered | diagnostics row :533 | OBS |
| `PolyRunner.age['venue']` | :81 `time.time() - age_ms/1000` (a timestamp, not an age); `age[spot/perp/depth]` :709 arrival wall time | | reader is dead (poly_dashboard.py:85) | DEAD |
| `FeedHealth.arrival_age` / `event_lag` | poly_feeds.py:132-139 vs `ARRIVAL_LIMITS` (:82-87) and `MAX_EVENT_LAG_S` 2.5 (:88) | socket liveness vs data freshness | `stale()` at btc_model_v12_polymarket.py:148 (decide), :318 (lanes), poly_dashboard.py:89 | **LIVE** for spot/perp/depth; 'venue' entries written (:82) but never checked |
| `cash_at` age < 15 s | :257, :353 | balance readiness | fire eligibility; dashboard :221, :482, :518 | LIVE |
| `terms_age` > 30 s | :416 | refetch tick/min/fee | housekeeping | LIVE |
| `timing.quote_wait_ms`==`quote_read_ms` (:900); `submit_ms`==`response_ms`==`network_roundtrip_ms` (:966, :974) | | one number under 2 and 3 names | journal/dashboard | OBS (duplicate columns) |

### 2.6 Diagnostics writers (17 sites) and readers (3)

| file:line | tag | epoch col | when |
|---|---|---|---|
| btc_model_v12_polymarket.py:249 | `reason=decide_loop_error` | 0 | exception in decide loop |
| :266 | `reason=no_terms, kind=EF` | ep | EF fire blocked on terms |
| :277 | (bare EF decision dict incl. `features`) | ep | every 15 s |
| :350 | lane decision dict + `lane`, `ask_up`, `ask_dn` | ep | every lane decision (on or off) |
| :358 | `reason=no_terms, kind=<lane>` | ep | lane blocked on terms |
| :412 | `reason=feed_counters` | ep | every 5 s |
| :478 | `kind=LOW_BALANCE` | 0 | once per low-balance episode |
| :509 | `kind=WAIT_CENSUS` | ep | every 60 s |
| :533 | `kind=AMBIENT_AGE` | ep | every 5 s |
| poly_core.py:465 | `reason=control_write` | 0 | audited meta write |
| :519 | `reason=candle_rearmed` | ep | release() re-arm |
| :822 | `kind=KILL_CONDITION` | 0 | once per rule per episode |
| :931 | `reason=order_plan_refused` | ep | EV/plan refusal in executor |
| :940 | `reason=prepare_failed` | ep | sign failure |
| :1027 | (bare `error_info` dict, no tag) | ep | reconcile raised |
| :1038 | `kind=RECONCILE_STUCK` | ep | reconcile returned error |
| poly_dashboard.py:299 | `reason=halt_cleared` | 0 | operator clear |

Readers: `lane_loop` :381 (`ORDER BY ts DESC LIMIT 1 WHERE epoch=?`, **any tag** - a `feed_counters`, `AMBIENT_AGE`, `WAIT_CENSUS` or 15-s EF decision row written with the same `ep` between the lane's fire and the read will be what `skip_reason` prints; OBS-level mis-report, no decision depends on it), `_main_oneshot_check` :553 (`control_write` rows; **LIVE**, see 2.3), `housekeeping` :434 (7-day purge). Tags are split between `reason=` and `kind=` keys and between epoch=0 and epoch=ep; offline consumers have to handle both.

### 2.7 Attempt caps: three of them

| cap | value | scope | code |
|---|---|---|---|
| `Executor.max_attempts` | CLI `--max-attempts` 4 | per `fire()` call (retry after retryable reject) | poly_core.py:884, RETRYABLE :1001-1008 |
| `Journal.MAX_ATTEMPTS_PER_CANDLE` | 4 | per (epoch, kind): after 4 `NO_ORDER_SENT` releases the signals row is kept and `reserve()` fails silently | poly_core.py:496, 507-521, 882 |
| `LaneEngine.MAIN_MAX_ATTEMPTS` | 6 | per lane per candle, counted by `confirm(placed=False)` | poly_lanes.py:427, 442, 449, 455, 492 |

For a lane the journal's 4 binds first; the lane keeps counting to 6 on a reserve that can no longer be taken, then sets `main_block` (:456). Not a fault, but two counters describe one thing.

### 2.8 Two settings-synchronisation paths for the executor dials

`Executor.__init__` (poly_core.py:850-862) takes `age`/`pad` from the CLI and hardcodes `band=False`; `_sync_executor_dials` (btc_model_v12_polymarket.py:648-664) overwrites all three from meta on every decide pass (:256) and every lane decision (:355). The constructor values are therefore only in force between process start and the first decide pass. `budget_s`, `post_timeout_s`, `max_attempts` have **no** meta path - CLI only, restart to change.

### 2.9 Duplicated constants / literals

| what | copies |
|---|---|
| `US = 1_000_000` | btc_model_v10.py:55, btc_model_v10_runner.py:29 (v12 imports the runner's, :5) |
| `EV_MODES` | btc_model_v12_polymarket.py:628; poly_dashboard.py:166 and :324 fallback literals |
| `CALIBRATION_DEFAULT` | btc_model_v12_polymarket.py:175; poly_dashboard.py:309 fallback literal |
| cost/break-even formula | btc_model_v10.py:218 (`Model.cost`), btc_model_v10_runner.py:35 (`cost` lambda, standalone only), poly_core.py:296-297 (`order_plan`) |
| `tick_size=0.01` hardcoded | poly_dashboard.py:167 (`ev_controls`) while the venue moves between 0.01 and 0.001 intra-candle (poly_core.py:155-164) - display only |
| readiness `cash_at < 15` | btc_model_v12_polymarket.py:257, :353; poly_dashboard.py:221, :518 (`age<15`) |
| `signals`/`orders`/`fills` PnL-per-lane formula | poly_dashboard.py:201-206 (`pnl_by_kind`), :405-407 (`orders`), :446-447 (`history`); `Journal.grade` :546-553 sums across lanes |

---

## 3. Leftovers (Predict.fun / Tokyo / build 36 / paper-only / standalone)

### 3a. Keyword census (code + comments, `grep -n -i -c`)

| keyword | hits | code lines (not comment/docstring) |
|---|---|---|
| `predict` | v12:1, poly_core:2, poly_lanes:3, poly_dashboard:2 | 0 - all comments/docstrings/status text (poly_dashboard.py:231 is a UI status string) |
| `tokyo` | poly_core:1, poly_lanes:1 | 0 |
| `build 36` | v12:2, poly_core:6, poly_dashboard:2 | 0 (btc_model_v12_polymarket.py:757 is a trailing comment on `--max-attempts`) |
| `isMinAmountOut` | poly_core:2 | 0 (poly_core.py:216, :224 comments) |
| `build 11` | poly_lanes:23, poly_dashboard:3 | provenance comments on the lane port |
| `PaperBroker` | v12:2 (:7 import, :33 construct), poly_core:1 (class) | |

There is **no** Predict.fun / Tokyo *code* path in the live engine; what remains is the build-36 execution-survivability policy ported as `SLIPPAGE_BANDS` / `slippage_band` / band mode in `order_plan` (poly_core.py:234-244, 260-266, 324-343), which is **live-selectable** via `ev_settings.slippage_mode='band'` (poly_dashboard.py:342-344; default `'ticks'` at btc_model_v12_polymarket.py:673). Not a leftover - a dial.

### 3b. MAIN / REVERSAL lanes - can they fire?

| lane | evaluated | can execute when | observed default |
|---|---|---|---|
| MAIN | every decide pass (`lane_loop` :275 -> `evaluate` :320 -> `_try_main` poly_lanes.py:451-479) regardless of any toggle; every decision written to diagnostics :350 | `allowed('MAIN')` :352 = `master AND main_enabled AND not halt AND not daily-halted AND not banned AND not sx` (poly_dashboard.py:76) + cash fresh :353 + terms :357 + `stake <= cash - reserve` :363 | `main_enabled` seeded **False** (poly_dashboard.py:53); `_main_oneshot_check` turns it back off after one fill (:562) |
| REVERSAL | same pass, `_watch_reversal` :482-516 | as MAIN with `reversal_enabled`, **and** `self.current_main` must be a *placed* MAIN this candle (poly_lanes.py:490) and phase 30-285 s (:496) | seeded False (:53). Given the one-shot rule, REVERSAL is reachable only inside the single candle in which MAIN fills. |

So both lanes are **live-capable, off by default**, and cost one diagnostics INSERT per lane decision plus two quote() reads (:344-349) whether on or off. `lane_loop` is 93 lines (:303-395); poly_lanes is 553 lines; `lane_card`/`pnl_by_kind`/`orders(kind)`/`history` lane columns in the dashboard serve them.

### 3c. Paper-only code (never entered with `--live`)

| code | file:line | gate |
|---|---|---|
| `PaperBroker` | poly_core.py:825-843 (19) | `if a.live else PaperBroker(...)` btc_model_v12_polymarket.py:33 |
| paper terms via public CLOB + `m.fee` | :418-421 | `else` of `if self.a.live` :417 |
| paper cash from `--capital` + local pnl | :427-429 | `else` of :423 |
| `claim_status='PAPER'` | :605-606 | `not self.a.live` |
| `Dashboard.equity` local basis | poly_dashboard.py:117 | `not self.r.a.live` |
| `master` seeded True | poly_dashboard.py:53 `not r.a.live` | |
| `--capital` (only readers :429, :762, poly_dashboard.py:117) | | unused on live |
| `--mode` (choices `['pnl']`) | btc_model_v12_polymarket.py:751 | **never read** by `PolyRunner`/dashboard/core (`grep -n 'a\.mode'` hits only the standalone runner) - vestigial flag |
| `financial_is_shadow` fields | poly_dashboard.py:415, 454, 477 | display |

### 3d. Pre-Polymarket dashboard machinery still in the gate chain (live-reachable, not dead)

Daily take-profit/stop-loss (`daily()` :59-64, meta `tp`/`sl`), ban-window `rules` (`banned()` :65-73), state-X 2-loss pause (`sx_*`, :136-137, :361), streak/ladder/percent stake modes (`update_stake` :123-150). All are consulted by `allowed()` on every EF and lane decision. `/events` returns a 404 stub (:564); `/api/weights` reports synthetic `drift=0` (:563); `Journal.__init__` accepts 46 historical build strings (poly_core.py:400).

---

## 4. Config dials

### 4a. CLI (`args()` btc_model_v12_polymarket.py:746-768)

| flag | default | bounds | read at | meta override? |
|---|---|---|---|---|
| `--live` | off | | 13 sites in v12, 13 in poly_dashboard | no |
| `--host` / `--port` | 127.0.0.1 / 8787 | password required if host not loopback (poly_dashboard.py:44) | :738; poly_dashboard.py:44, :593 | no |
| `--model` | model_v10.json | must exist :767 | :24, :26 | no |
| `--db` | polymarket_v12_paper.sqlite3 | | :28-32 | no |
| `--capital` | 50 | >0 finite :762 | :429 (paper), poly_dashboard.py:117 (paper) | no; unused live |
| `--mode` | pnl | choices `['pnl']` | **never read** | - |
| `--ev` | None | finite :763 | :640, :642 (seeds `ev_setting()` when meta has no mode/value) | yes: `ev_settings.mode/value` |
| `--quote-age-ms` | 750 | 0<x<=2000 :762 | :34 (overwritten), **:75 publish (LIVE, no override)**, :669 fallback, poly_dashboard.py:483 | partial: `ev_settings.quote_age_ms` reaches :225, :347, :664 only |
| `--pad-ticks` | 1 | >=0 :762 | :34 (overwritten), :677/:679 fallback | yes: `ev_settings.pad_ticks` (:676-680, clamp 0..5) |
| `--execution-budget-ms` | 2000 | 300..240000 :764 | :35 -> poly_core.py:861, :883 | no |
| `--post-timeout-ms` | 1200 | 100..budget :765 | :36 -> :861, :962 | no |
| `--max-attempts` | 4 | 1..10 :766 | :37 -> :862, :884 | no |

### 4b. Meta keys (`db.get`) - every read site, with the default used at that site

| key | read (file:line -> default) | written | seeded at start |
|---|---|---|---|
| `master` | poly_dashboard.py:76 -> False; :239 -> None | v12:53 (False, live start), poly_dashboard.py:53 seed, `set_many` :255-271 | `not a.live` |
| `main_enabled` / `reversal_enabled` / `ef_enabled` | poly_dashboard.py:76 -> **True**; :232 -> **True**; v12:551 (`main_enabled`) -> None | seed :53 (**False/False/True**), `/api/controls/signal` :277, v12:562 (one-shot off) | yes. Read-default True vs seed False differ; seed wins unless the row is deleted (UNSURE only in that case) |
| `halt` | poly_core.py:882; poly_dashboard.py:76, :239, :254, :288-289, :527 -> None | poly_core.py:1011 (set), poly_dashboard.py:298 (clear) | no |
| `halt_cleared_at` | poly_core.py:744, :779 -> -1.0 | poly_dashboard.py:297 | no |
| `calibration` {enabled False, cut .80, to .784} | v12:177 (merged over `CALIBRATION_DEFAULT`); poly_dashboard.py:310 (merged over the duplicate literal :309) | poly_dashboard.py:319 (bounds :316-318) | no (defaults inline) |
| `ev_settings.mode` | v12:636-640 -> `'fixed'` if `--ev` else `'regime'`; poly_dashboard.py:161/:325 | :351 | no |
| `ev_settings.value` | v12:642 -> `--ev` | :332 (bounds 0..5) | |
| `ev_settings.quote_age_ms` | v12:667 -> `--quote-age-ms`, clamp 1..2000 ms | :341 (0<qa<=2000) | |
| `ev_settings.slippage_mode` | v12:673 -> `'ticks'` | :344 | |
| `ev_settings.pad_ticks` | v12:677 -> `--pad-ticks`, clamp 0..5; poly_dashboard.py:163 fallback -> 1 (dead) | :348 (0..5) | |
| `stake_settings` {mode ladder, fixed 1, percent 10, current 1, win 3, loss 2, min 1, max 50} | poly_dashboard.py:125 -> `DEFAULT_STAKE`; :245 -> None | seed :53; apply :267/:271 (bounds :258-266) | yes |
| `next_stake` | v12:227, :258, :362, :465 -> `1.`; poly_dashboard.py:125, :245, :518 -> `1` | `update_stake` :150 (every 5 s via v12:430 and after apply :272); apply :267 | via update_stake |
| `streak` / `streak_cursor` / `rung` / `sx_losses` / `sx_until` | poly_dashboard.py:126, :141, :222, :243, :76 -> [0,0]/0/[0,0]/0/0 | :137-146, :267, :361 | no |
| `sx_enabled` | poly_dashboard.py:76, :136, :139, :243 -> None | :361; seed :53 False | yes |
| `tp` / `sl` | poly_dashboard.py:62 -> 0 | `set_many` :371; seed :53 (0) | yes |
| `rules` | poly_dashboard.py:67, :377, :378 -> []; :245 -> None | :377-378; seed :53 [] | yes |
| `build` / `lane` / `model_hash` | poly_core.py:397-402; `build` at poly_dashboard.py:535 | poly_core.py:402 | yes |

### 4c. Environment variables

| var | read at | default / effect |
|---|---|---|
| `DASHBOARD_PASSWORD` | poly_dashboard.py:43 (redacted poly_core.py:20) | '' ; >=12 chars required off-loopback :44 |
| `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_WALLET_ADDRESS`, `RELAYER_API_KEY`, `RELAYER_API_KEY_ADDRESS` | poly_live.py:38-42 | required for `--live` |
| `BINANCE_REST_HOSTS`, `BINANCE_WS_SPOT/PERP/DEPTH/CHART` | poly_feeds.py:39-63 | host lists |
| `FEED_MAX_ARRIVAL_AGE_S` 6, `_SPOT_S` 6, `_PERP_S` 6, `_DEPTH_S` 2, `_VENUE_S` 5 (**never enforced**, 1a), `FEED_MAX_EVENT_LAG_S` 2.5, `FEED_STALL_RECONNECT_S` 8 | poly_feeds.py:81-90 | gates in `stale()` / `run_stream` |

### 4d. Model file (`model_v10.json`, read btc_model_v10.py:196-208)

`fee_rate` 0.07 (used by `Model.decide` cost :262, paper terms v12:421, dashboard break-even poly_dashboard.py:486), `ev_threshold_default` 0.25, `regime.thresholds` low .15 / mid .25 / high .25 with `rv60_edges` [.1668, .3653] (used by `threshold()` :221-228 for EF and, via v12:368, as the lane EV bar), `accuracy_mode` floors, `mode_default` pnl.

### 4e. Read in two places with different defaults / sources (the flag list)

1. **Quote age** - CLI value at `publish()` (:75) vs meta value at gate/executor (:225, :664); plus `quote()`'s own `.75` (poly_core.py:186) and `Executor.__init__` `.75` (:850). Live path straddles the first two. (2.1)
2. **Fee** - `model_v10.json fee_rate` in `Model.decide` vs venue `fee_info.rate/exponent` in `order_plan` (poly_live.py:46 -> `terms`). (2.2)
3. **Depth check** - on in `_gate_on_padded_ev` (default `require_depth=True`), off in the executor. (2.2)
4. **Per-kind lane flags** - read default True (poly_dashboard.py:76, :232) vs seed False (:53).
5. **`next_stake`** - `1.` vs `1` (same value; harmless).
6. **`EV_MODES` / `CALIBRATION_DEFAULT`** - runner constant vs dashboard fallback literal (same values; fallback dead).
7. **Bankroll** - `venue_state` cash+open_value for sizing vs `self.cash - live_reserve()` for firing. (2.4)
8. **Absence proof** - 5 s/2, 2 s/2, 60 s/3 across Journal and LiveBroker. (2.4)
9. **Attempt caps** - 4 (executor) / 4 (journal per candle) / 6 (lane). (2.7)
10. **`tick_size=0.01`** literal in `ev_controls` vs live venue tick. Display only.

---

## Counts

- Defs/classes inventoried: 244. Fully dead functions in the 8 modules: **2** (`BookCache.clear`, `PaperBroker.account_snapshot`; the first is test-only, the second is dead everywhere). Dead branches/state: 8 (1a). Standalone-only runner code: 12 functions/classes, ~265 lines (1b). CLI/test-only: 4 + 10 never-overridden parameters (1c).
- Overlap items: 9 (2.1-2.9); of these **3 are real second decision points on the live path** (quote-age CLI vs meta; depth check in gate vs executor; `_main_oneshot_check` disarming MAIN), 1 is a live redundancy (two writers of `self.cash`), the rest are OBS or duplicate computation.
- Leftovers: 0 Predict.fun/Tokyo/build-36 *code* paths; 1 vestigial flag (`--mode`); MAIN/REVERSAL are live-capable and off by default (3b); paper-only paths listed in 3c.
- Config dials: 13 CLI flags (3 of which are overwritten by meta each pass, 1 never read), 20 meta keys, 12 env vars, 1 model file; 10 flagged double-reads (4e).
