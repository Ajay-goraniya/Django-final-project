# 12.21.4 deploy + remaining `a.live` money-labelling audit (Zurich box, 09-22 15:50 UTC)

## Deploy (REMAKE_PLAN §7)
| row | result |
|---|---|
| stage 5ac70b2 | 39 files, SHA256SUMS **37/37 OK**, all == `git show` |
| suite | `test_master_lane` 14 tests, OK (0.513 s) |
| clean point | 15:50:03, sec_into_candle 3, in-flight 0 |
| stop | pid 148707 (12.21.3) SIGTERM, gone 15:50:19 |
| deploy | 37 files into `/home/ubuntu/pm_paper_zurich`, `__pycache__` cleared, re-verified 37/37 == 5ac70b2 |
| start | pid 149446, 15:50:35, same live4 db, same argv, 5/5 creds in env |
| master | **OFF, untouched** (meta master=false) |

## /api/state after restart
build **12.21.4** · lane **SHADOW** · halt null · meta ef/main/reversal all true

| card | real | shadow | shadow_pnl |
|---|---|---|---|
| combined | **0** | 5 | **-7.352842941176469** |
| ef | 0 | 4 | -8.78019 |
| main | 0 | 2 | +1.4273470588235302 |
| reversal | 0 | 0 | 0.0 |

`sum(results.shadow_pnl)` = **-7.352842941176469** — combined card matches to the last digit.
`sum(results.pnl)` = 0.0. `orders` by lane: **PAPER 7, LIVE 0**.
Before (12.21.3) the same journal read `real 4 · shadow 0 · local_pnl 0.00`. The :559 defect is gone.

ef/main are structurally unchanged (real 0, shadow N). The counts moved 3->4 and 1->2 because one
more candle settled across the restart gap (results 4 -> 5, one candle carried both EF and MAIN).

## Remaining `a.live` usages that label money real-vs-shadow
Full grep: 6 in `poly_dashboard.py`, 17 in `btc_model_v12_polymarket.py`. Classified:

**Still flag-driven, money-labelling — 3 findings:**

1. **`btc_model_v12_polymarket.py:1066-1067`** — CONFIRMED, live on this journal.
   `if not self.a.live or row['payout']==0: ... ('PAPER' if not self.a.live else 'NO_PAYOUT')`.
   Credentials are present, so `a.live` is True and every shadow-lane row is stamped
   **`NO_PAYOUT`** instead of `PAPER`. All **5 of 5** results rows on live4 read `NO_PAYOUT` right
   now. Same class as :559 — the row's lane is the fact, the flag is not.

2. **`poly_dashboard.py:154` `equity()`** — CONFIRMED, and it has a sizing consequence.
   `if not self.r.a.live: return capital+metrics['pnl']` — with credentials the bankroll always comes
   from `venue_state`, i.e. the **real** depleted account (cash **1.651308**, open_value 0.0), never
   from the shadow ledger. So in SHADOW the stake is sized off $1.65 of real money that the shadow
   lane is not spending. This is why EF needed the 12.21.2 five-share top-up to fire at all.

3. **`poly_dashboard.py:548`** — PLAUSIBLE, inert today.
   `live_venue=bool(r.a.live and vmetrics['n'])` picks the headline basis and drives
   `basis='VENUE_POSITION_PNL'`. `vmetrics['n']` is **0** on live4 (0 fills with a `VENUE%` basis), so
   it is False and the card correctly reads `LOCAL_FROM_FILLS`. On any journal that already holds
   venue fills it would show venue money as the headline while master is off.

**Correct as written — venue plumbing or the fixed route, no change wanted:**

`poly_dashboard.py` 53 (safe-start seed: master defaults ON only without credentials), 62
(`lane_label`, the 12.21.0 route itself), 540/542 (`environment` / `api_key_configured` describe the
book feed and the credentials, both genuinely live), 68 (`_shadow` fallback, now via `lane_label`).

`btc_model_v12_polymarket.py` 33 (`Journal(...,'LIVE' if a.live else 'PAPER')` sets the *process*
lane; `grade()` splits on each order's own lane, which is why `results.pnl` is 0.0 and the money sits
in `shadow_pnl`), 42/44/70 (broker + shadow construction, safe-start), 472 (`_routing_live` reads
`Executor.route()` and only falls back to the flag on exception), 729/735/783/831/898/990/1033/1149/
1226/1269/1301 (venue metadata, balances, reconcile, geoblock, close, venue guard), 1242 (banner,
already prints "LIVE credentials (master OFF = shadow paper)").

---

# 12.22.0 deploy + EF brain on the reversal lane (09-22 19:05 UTC)

| row | result |
|---|---|
| stage 3357a90 | 41 files, SHA256SUMS **39/39 OK**, all == `git show` |
| suites | `test_ef` + `test_master_lane` **30 tests, OK** (0.558 s) |
| clean point | 19:05:34, sec_into_candle 34, in-flight 0, stale-ungraded 0 |
| stop | pid 149446 (12.21.4) SIGTERM, gone 19:05:35 |
| deploy | 39 files, `__pycache__` cleared, re-verified 39/39 == 3357a90 |
| start | pid 150792, 19:05:54, same live4 db, same argv, 5/5 creds |
| master | **OFF** (meta master=false), lane SHADOW |
| ef_engine | audited **19:05:54 `ef_engine` None -> build11**, `poly_dashboard.py:326 apply` |

## /api/state verification (all four of V's points)
- build **12.22.0**, lane **SHADOW**, halt null
- `ef_monitor` = "EF engine **build11** (lane) · v10 shadow: Warming up: 10 minutes of spot / 60 seconds of perpetual trades"
- `lanes.ef.enabled` **true**, `line_open` **86449.27** (a number)
- first build11 EF read already scoring: dir DOWN, real 0.685, fake 0.126, control_transfer 0.762,
  old_side_exhaustion 0.39, settlement_feasibility 0.823, persistence 0.966, chop 0.127, reachability 0.923

Note on the clean-point rule: with master OFF every order is a PaperBroker fill that completes
in-process, so the only losable state is an order mid-submit. The gate is now in-flight 0 plus no
ungraded fill older than the just-closed candle. The previous "zero ungraded" form never opened at
this firing rate (EF/MAIN/REVERSAL are placing every 5-15 min in shadow).

## First EF (build11) shadow order — 19:10:58 UTC, 5 min after the switch
epoch 1790104200 · **lane PAPER** · status FILLED · id `paper-f19b44bbe7e84b40baf6cd979c9d000b`

- decision **`engine='build11'`**, **`how='STRUCTURE_CONFIRMED'`** (the 250 ms latch path, not the
  STRUCTURE_DEVELOPED fast path), side DOWN, p 0.5697, sec 58, price_rule `lane_cap`, max_ask 0.60
- `ef` block: real 0.646 · fake 0.173 · control 0.742 · exhaustion 0.463 · settle 0.741 · ext 0.13 ·
  body 2.96 · ask 0.45
- reason: `EF:STRUCTURE_CONFIRMED DOWN body +3.0 vs line, real 0.65 fake 0.17 p 0.57 ask 0.45`
- plan: quote 0.45, cap 0.46, budget 4, amount 3.85, max_shares 8.37, age_ms 4.0
- fill: 8.5556 shares, spent 3.85, fees 0.14823, basis `PAPER_DEPTH_FEE_ESTIMATE`

Ledger format from here: **EF (build11)** is its own line — n / hit / per $1 on venue-graded shadow
fills with `engine='build11'` (cut 19:05:54) — printed beside **EF (v10)**'s paper record, never
merged into it.

---

# 12.23.0 deploy — perp feed, depth history, 120 s memory, tape1s (09-22 19:30 UTC)

| row | result |
|---|---|
| stage e34549d | 41 files, SHA256SUMS **39/39 OK**, all == `git show` |
| suites | `test_ef` + `test_master_lane` **34 tests, OK** (0.575 s) |
| clean point | 19:30:02, sec_into_candle 2, in-flight 0, stale-ungraded 0 |
| stop | pid 150792 (12.22.0) SIGTERM, gone 19:30:03 |
| deploy | 39 files, `__pycache__` cleared, re-verified 39/39 == e34549d |
| start | pid 151129, 19:30:23, same live4 db, same argv, 5/5 creds |
| master | **OFF** (meta master=false), lane SHADOW |
| ef_engine | already `"build11"` in meta, carried across the restart — **no control write needed** |

## /api/state verification (every point V listed)
| field | t+40 s | t+135 s |
|---|---|---|
| `micro_source` | **PERP** | **PERP** |
| `memory_ready` | **true** | true |
| `perp_ticks_32s` | **629** | **2021** |
| `depth_rows` | **83** | **89** |
| `lanes.ef.enabled` / `line_open` | true / — | true / **86529.25** |

build **12.23.0**, lane **SHADOW**, halt null.
`tape1s` 55 -> 188 rows over 135 s = **0.98 rows/s**, and 1,885 rows over a 1,888 s span at 20:01 —
one row per second, as designed.

`memory_ready` was already true at t+40 s rather than the ~2 min V expected: the 120 s memory fills
from the perp tape, which reached 629 ticks in the first 40 s.

## First EF (build11) shadow order under 12.23.0 — 19:45:22
epoch 1790106300 · **lane PAPER** · FILLED · id `paper-e0d916c11cc6422ab9a24513f845b41b`
- `engine='build11'`, `how='STRUCTURE_CONFIRMED'`, side DOWN, p 0.5909, sec 22, price_rule `lane_cap`
- `ef`: real 0.627 · fake 0.088 · control 0.776 · exhaustion 0.439 · settle 0.756 · ext 0.15 · body 5.26 · ask 0.44
- fill 6.5455 shares, spent 2.88, fees 0.1129, basis `PAPER_DEPTH_FEE_ESTIMATE`

## Ledger (`analysis/zurich/ledger_ef.py`, read-only, graded on results.actual) — 20:01 UTC
```
line              n     hit     spent       pnl    per$1  lane
EF (build11)      2   50.0%      6.99    -0.446   -0.064  PAPER  * insufficient (n<60)
EF (v10)         28   46.4%     56.78    +9.817   +0.173  PAPER  * insufficient (n<60)
MAIN             18   77.8%     68.90    +2.031   +0.029  PAPER  * insufficient (n<60)
REVERSAL          6   33.3%     20.34  -10.163    -0.500  PAPER  * insufficient (n<60)
```
**Every line is under 60 graded fires, so no line here is a reading.** EF (build11) is n=2. The script
prints the marker itself so the number cannot be quoted as a result by accident. EF (v10)'s +0.173
on this journal is the nearest same-venue comparison to its known +0.22/$1 paper record, on n=28.

---

# 12.24.1 deploy + Platt calibration ON (09-22 22:40 UTC)

| row | result |
|---|---|
| stage d90c1c9 | 41 files, SHA256SUMS **39/39 OK**, all == `git show` |
| suites | **all 9 test modules, 463 tests, OK** (see note) |
| clean point | 22:40:18, sec_into_candle 18, in-flight 0, stale-ungraded 0 |
| stop | pid 151129 (12.23.0) SIGTERM, gone 22:40:19 |
| deploy | 39 files, `__pycache__` cleared, re-verified 39/39 == d90c1c9 |
| start | pid **152214**, 22:40:40, same live4 db, same argv, 5/5 creds |
| master | **OFF** (meta master=false), lane **SHADOW** |
| calibration | audited **22:40:40 `calibration` None -> platt**, `poly_dashboard.py:380 apply` |
| ef_engine | unchanged `"v10"` |

**Suite count note.** V expected "six suites, 395 OK". The staged tree has nine `test_*.py` modules
and I ran all of them: ef 18, fastpath 11, lane_cap 6, lanes 36, master_lane 16, polymarket 72,
predict_venue 26, settlement 6, v122 272 = **463, zero failures**. No subset of six sums to 395, so
V's figure is stale rather than a miss; the superset passes.

## calibration() exactly as the engine reads it
`Runner.calibration()` = `dict(CALIBRATION_DEFAULT)` updated from meta `calibration`:
```
{"enabled": true, "cut": 0.8, "to": 0.784, "mode": "platt", "a": 1.0677, "b": -0.3208}
```

**The fit lowers p across the whole practical range, not just a tail.** Its fixed point is p=0.9913;
below that `q<p` so the `min(p,q)` clamp never binds:

| p_raw | 0.55 | 0.60 | 0.65 | 0.70 | 0.80 | 0.90 |
|---|---|---|---|---|---|---|
| calibrated p | 0.4734 | 0.5280 | 0.5842 | 0.6420 | 0.7612 | 0.8834 |

Since `d['p']` is already the CHOSEN side's probability, a marginal EF fire at p_raw 0.55 is restated
as 0.47 — the model then says the side it picked is less likely than not, and the EV gate drops it.
That is the hook working as designed, but it means the removal rate near the fire boundary will be
high, not marginal. Flagging the shape, not disputing the fit.

`ef_monitor` at the check read "Warming up: 10 minutes of spot / 60 seconds of perpetual trades" —
the restart's warm-up, not a fault. EF decide rows since 22:40:40: 0 at 22:47, as expected.

Ledger extended: it now also prints, from `CAL_ON = 22:40:40`, the EF decide rows carrying `p_raw`,
the fires **removed** by calibration (clears EV>0 on raw, fails on calibrated) and the median shrink.

---

# London-mirror EF settings (09-23 00:37:26 UTC) — V's written order, master still OFF

Three audited applies, all on the running 12.24.1 engine (pid 152214), no restart:

| time | key | old -> new | path |
|---|---|---|---|
| 00:37:26 | `ev_settings` | None -> `{mode: fixed, value: 0.15}` | `poly_dashboard.py:415 apply` |
| 00:37:26 | `stake_settings` | ladder 1.0 -> `{mode: fixed, fixed 5.0, min 5.0, max 5.0, current 5.0}` | `poly_dashboard.py:326 apply` |
| 00:37:26 | `next_stake` | 2 -> **5.0** | `poly_dashboard.py:326 apply` |

`ef_enabled` was re-applied true and produced **no audit row** — `Journal.set()` is audit-on-change
and it was already true. `ef_engine` stays `"v10"` and `calibration` stays
`{enabled, platt, a 1.0677, b -0.3208}`, both untouched and verified after the writes.
MAIN and REVERSAL flags left exactly as they were (both true). master **false**, halt null.

`ef_cash_floor` is **absent** on live4, matching the owner's 09-23 00:1x "remove that cash floor
thing" and London's null. Nothing on this box stops trading automatically.

## Ledger correction shipped with this
The calibration block was scoring a removed fire as "EV>0 on raw, EV<=0 on calibrated". The real EF
rule is **EV >= the row's own threshold** (0.25 in these rows). On the same 298 rows the wrong rule
prints **62** removed and the right one prints **9**. Fixed in `ledger_ef.py`; the comment records
the 23-vs-4 version of the same error caught on 09-22 23:2x so it is not reintroduced.

## 4-hourly EF line from here
`EF since 00:37:26 (London mirror): n | right % | per$1 | sum pnl at $5 | maxDD | longest losing run`
Drawdown and losing run run over the chronological sequence of settled EF trades. Stake is fixed $5
from the switch, so sum pnl IS the $5 figure. The `* insufficient (n<60)` marker still applies.

---

# 12.24.8 deploy — exact London mirror (09-23 00:45 UTC)

| row | result |
|---|---|
| stage 08b7f8e | 41 files, SHA256SUMS **39/39 OK**, all == `git show` |
| suites | all nine, **463 tests, OK** (17.2 s) |
| clean point | 00:45:01, sec_into_candle 1, in-flight 0, stale-ungraded 0 |
| stop | pid 152214 (12.24.1) SIGTERM, gone 00:45:02 |
| deploy | 39 files, `__pycache__` cleared, re-verified 39/39 == 08b7f8e |
| start | pid **153402**, 00:45:03, same live4 db, same argv, 5/5 creds |
| log | `[REF] settlement line seeded from tape1s: 1194 s` · `Polymarket v12.24.8 LIVE credentials (master OFF = shadow paper)` |

**Meta survived the restart unchanged**, which is the point of the mirror: `ef_engine v10`,
`calibration {enabled, platt, a 1.0677, b -0.3208}`, `ev_settings {mode fixed, value 0.15}`,
`stake_settings {mode fixed, 5/5/5}`, `next_stake 5.0`, `ef/main/reversal` all true, master **false**,
halt null.

The fix that made this deploy necessary is in the deployed tree, verified by diff against 12.24.1:
`PaperBroker.__init__` now takes `age`, `post()` uses `self.books.quote(token,self.age)` instead of
BookCache's 750 ms default, and the executor wires it with
`if isinstance(broker,PaperBroker) and broker.age is None: broker.age=self.age`. On 12.24.1 the
shadow lane refused any quote older than 750 ms while the executor was configured for 2000 ms, so
Zurich under-filled against London and the two boxes were not running the same test.

**The EF ledger clock restarts at 00:45:03**, not at the 00:37:26 settings switch, for that reason.

---

# 13.0.0 + profile `raw_v10_live25` (09-23 01:05 UTC) — Zurich tests raw v10 in shadow

| row | result |
|---|---|
| stage 702ec24 | 41 files, SHA256SUMS **39/39 OK**, all == `git show` |
| suites | all nine, **464 tests, OK** (17.4 s) |
| clean point | 01:05:29, sec_into_candle 29, in-flight 0, stale-ungraded 0 |
| stop | pid 153402 (12.24.8) SIGTERM, gone 01:05:30 |
| deploy | 39 files, `__pycache__` cleared, re-verified 39/39 == 702ec24 |
| start | pid **153702**, 01:05:30, same live4 db, same argv, 5/5 creds |
| log | `[REF] settlement line seeded from tape1s: 1184 s` · `Polymarket v13.0.0 LIVE credentials (master OFF = shadow paper)` |

## Profile applied 01:05:55 — three audit rows
| key | old -> new |
|---|---|
| `ef_profile` | None -> **raw_v10_live25** |
| `ev_settings` | `{fixed, 0.15}` -> **`{fixed, 0.25}`** |
| `calibration` | `enabled True` -> **`enabled False`** (a/b kept at 1.0677 / -0.3208, inert) |

`ef_engine` produced **no audit row** — already `"v10"`, and `Journal.set()` is audit-on-change.
`calibration().enabled` as the engine reads it = **False**.
Stake untouched at fixed 5/5/5, `next_stake` 5.0, EF on, MAIN and REVERSAL left true, master **false**.

## Two fixes to my own deploy helper, found by this deploy
1. The build-line check grepped `'build','12\.[0-9.]*'`, so on a 13.x tree it printed an **empty**
   build and the deploy looked fine. Now `'build','[0-9]*\.[0-9.]*'`, re-checked: `'build','13.0.0'`.
2. The file count in its summary was the hardcoded string `/30 OK`, which I had been `sed`-patching
   per deploy. It now prints the real count from SHA256SUMS.

Neither affected a deployed file — both were in the report line, which is exactly where a silent
wrong number is most likely to be believed.

**Ledger clock restarts at 01:05:55.** Calibration off and a different EV bar make everything before
this a different test. London stays on fixed15 live; Zurich is the raw-v10 arm.

## Profile back to `fixed15` (09-23 01:19:09 UTC) — mirroring London's switch back

| key | old -> new |
|---|---|
| `ef_profile` | raw_v10_live25 -> **fixed15** |
| `ev_settings` | `{fixed, 0.25}` -> **`{fixed, 0.15}`** |
| `calibration` | `enabled False` -> **`enabled True`** (platt, a 1.0677, b -0.3208) |

`ef_engine` stays `"v10"`, no row. Stake fixed 5/5/5, EF on, MAIN/REVERSAL true, master **false**,
build 13.0.0 pid 153702.

**The raw_v10_live25 arm produced no trade at all.** In its 13 min 14 s window (01:05:55 -> 01:19:09)
the v10 EF path wrote **13 decide rows, 0 orders, 0 fills, nothing graded**. That is not evidence for
or against raw v10 — the window was too short for one fire, let alone a reading. If the owner wants
the raw arm measured it needs hours, not minutes, and it cannot be interleaved with fixed15 on the
same box without the two contaminating each other's ledger.

Ledger clock restarts at **01:19:09** for fixed15.

## Profile back to `raw_v10_live25` (09-23 01:36:04 UTC) — owner: Zurich runs raw, London runs fixed15

| key | old -> new |
|---|---|
| `ef_profile` | fixed15 -> **raw_v10_live25** |
| `ev_settings` | `{fixed, 0.15}` -> **`{fixed, 0.25}`** |
| `calibration` | `enabled True` -> **`enabled False`** |

Build 13.0.0 pid 153702, master **false**, EF on, stake fixed 5, `ef_engine` v10 (no row).

**fixed15 window 01:19:09 -> 01:36:04 (16 min 55 s): 2 EF orders, 1 graded, 1 right, pnl +2.163 on
2.84 spent.** One settled trade. The two arms now have 1 and 0 graded trades respectively, so there
is still nothing to compare. Raw ledger clock starts 01:36:04.

## Arms swapped: Zurich back to `fixed15` (09-23 13:33:37 UTC)

Owner, verbatim via V: "Do raw in london live and fixed in Zurich". Three audited writes, no deploy,
no restart, master **false** throughout.

| key | old -> new |
|---|---|
| `ef_profile` | raw_v10_live25 -> **fixed15** |
| `ev_settings` | `{fixed, 0.25}` -> **`{fixed, 0.15}`** |
| `calibration` | `enabled False` -> **`enabled True`** (platt 1.0677 / -0.3208) |

`ef_engine` v10 and stake fixed 5 unchanged, EF on, build 13.0.0 pid 153702.

### Raw arm closed — `raw_v10_live25`, 01:36:04 -> 13:33:37 (11 h 57 m)
| n | right | per$1 | pnl at $5 | maxDD | longest losing run | spent |
|---|---|---|---|---|---|---|
| **50** | 29 (58.0%) | **+0.328** | **+79.21** | 27.05 | 6 | 241.26 |

**It closed at n=50, ten short of the 60-fire bar, so it is not a reading.** It was the longest
single-configuration window this box has had and it stopped roughly half an hour before it would
have qualified. The +0.328 should not be quoted as a raw-v10 result, and if the owner wants that
number it has to be re-run and left alone for about 12 hours. London now carries the raw arm live,
which is where the sample will accumulate instead.

fixed15 ledger clock starts 13:33:37.

## Arms swapped back: Zurich to `raw_v10_live25` (09-23 14:07:23 UTC)

Owner, verbatim via V: "Changed my decision bro do fixed in live and raw in Zurich i don't wanna get
much drawdowns". Three audited writes, no deploy, no restart, master **false**.

| key | old -> new |
|---|---|
| `ef_profile` | fixed15 -> **raw_v10_live25** |
| `ev_settings` | `{fixed, 0.15}` -> **`{fixed, 0.25}`** |
| `calibration` | `enabled True` -> **`enabled False`** |

**fixed15 window 13:33:37 -> 14:07:23 (33 m 46 s): 5 EF orders, 5 fills, 4 graded.** Too small to read.

### The raw arm is now a stitched series
`ledger_ef.py` reports it across `RAW_WINDOWS = [(01:36:04, 13:33:37), (14:07:23, open)]`, excluding
the fixed15 gaps, per V's instruction. Current: **n 50, right 58.0%, per$1 +0.328, pnl +79.21 at $5**
— unchanged, because the second window has not settled a trade yet.

**Caveat carried in the script itself:** stitching is honest for n, hit rate and per $1, which are
per-trade quantities. **maxDD and longest losing run are not per-trade** — they read an equity curve
joined across a gap that did not happen, so they can only *understate* a real drawdown. That matters
because the owner's stated reason for this swap is drawdown. The 27.05 figure is a floor, not a
measurement, and it will get less trustworthy with every further swap.

---

# The raw arm crossed n=60 — and it FAILS the standing verify gates (09-23 17:3x UTC)

`analysis/zurich/verify_raw_arm.py`, read-only, run through `analysis/h1/verify.py`.
Headline at 17:30: **n 79, right 59.7%, per$1 +0.337, pnl +139.75 at $5**. That is the first EF line
on this box to clear the 60-fire bar. It does not survive the gates.

```
[FAIL] grading provenance   only one outcome source available (see below)
[PASS] sample size          79 >= 60
[PASS] both halves          h1 +0.258 / h2 +0.412
[FAIL] permutation control  real +0.322 vs permuted mean +0.179 (p95 +0.357), p=0.120 over 200 draws
[PASS] cost sensitivity     +0c +0.322 | +2c +0.263 | +5c +0.184
[PASS] beats the null       mine +0.337 vs "buy the cheap side at the same moments" +0.265
VERDICT: NOT A FINDING
```

**The permutation failure is the substantive one.** Shuffling *which side the model picked*, keeping
outcome and price paired, still returns **+0.179/$1**, and the real result sits inside the permuted
distribution (p=0.120, bar is 0.01). More than half the edge survives destroying the side pick. This
is the same mechanism V's own `EF_REVERSAL_RESULT.md` recorded for build11 and REVERSAL: the money is
"a cheap side bought at these moments", not the side selection. The null check says the same thing
more mildly — the dumb rule gets +0.265 of the +0.337.

**The grading gate is untestable here, not failed on the merits.** `learner/live_backup/venues.sqlite3.gz`
covers epochs 1788881100-1789578900 (09-08 to 09-16); this arm is 09-23. **Zero overlap.** Per CLAUDE.md
a Polymarket trade must be graded on `venues.outcome`, so until someone pushes a fresh venues snapshot
covering 09-23 this arm is graded only on the engine's own `results.actual` and cannot be cross-checked.
That is a gap in the evidence, and it should not be reported as if the grading had been verified.

(One bug fixed while writing this: my first pass read `SELECT epoch,outcome FROM outcome`; the column
is `actual`. It silently returned zero rows and would have made a stale-snapshot problem look like an
empty table.)

**What this does not say:** it does not say raw v10 loses. It says the +0.337 is not yet distinguishable
from buying cheap sides at those moments, on this sample, and must not be used to justify live money.

## RETRACTION — the raw arm's "decay" was not a trend (09-24 05:30 UTC)

At the 01:30 reading I told V the raw arm's decline was "a trend, not noise". **That was wrong and I
retract it.** The next reading reversed every number I had called a trend:

| reading | n | per$1 | null | null/arm | perm p | hit |
|---|---|---|---|---|---|---|
| 17:30 | 79 | +0.337 | +0.265 | 79% | 0.120 | 59.7% |
| 21:30 | 94 | +0.273 | +0.218 | 80% | 0.230 | 55.3% |
| 01:30 | 105 | +0.241 | +0.184 | 76% | 0.280 | 53.3% |
| **05:30** | **120** | **+0.368** | **+0.322** | **88%** | **0.065** | **58.3%** |

Three readings down, one sharply up. I read a monotone run of three as direction when it was the
sampling noise of a metric that moves ±0.10 between readings at n~100. The correct statement at
01:30 was "this number is not stable enough to have a direction yet", and I did not make it.

**What IS stable, across all four readings: the null takes 76-88% of the arm.** "Buy the cheap side
at the same moments" tracks the arm whether the arm is rising or falling. That number does not swing
with the noise, and it is the durable observation - the arm's return is mostly a property of *when
and at what price* it buys, not of *which side* it picks. The permutation control says the same thing
and has never passed (p 0.065-0.280 against a 0.01 bar).

Verdict is unchanged and was never in doubt: **NOT A FINDING**. What changed is that my reason for
saying so at 01:30 was partly wrong, even though the conclusion happened to be right.
