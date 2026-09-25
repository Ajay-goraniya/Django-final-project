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

---

# 13.0.4 — per-second decision logging (09-24 12:20 UTC), logging only

Owner-approved, V-relayed. **No model, profile, EV, stake or flag change.** Confirmed to V before the
restart, with the pre-checks already done.

| row | result |
|---|---|
| stage 6885af4 | 41 files, SHA256SUMS **39/39 OK** == `git show` |
| suites | all nine, **477 tests, OK** |
| disk | `/dev/root` 30G, **21G available**, 32% used. 4 days at ~150 MB/day ~= 600 MB, ~35x headroom |
| clean point | 12:20:03, sec_into_candle 3 |
| start | pid **166436**, 12:20:05, same argv, same live4 db, 5/5 creds |
| `decide_log` | set **true** 12:20:30 via `Journal.set` |
| unchanged | master false, raw_v10_live25, ev 0.25, calibration off, stake 5, halt null |

## 10-minute measurement
2,360 rows over 9.9 min = **238 rows/min** (target ~240). **0 fire rows.**
`decide_log_features` **44** entries; the latest row's `feats` array is 44 long, so they line up.
`/api/state` error field is **empty**. Engine alive, 117 tape rows/120 s.

**`feats` non-null is 2.3% over the whole window, and that number is misleading on its own.** The
null rows are not a defect:

| reason | rows |
|---|---|
| "Warming up: 10 minutes of spot / 60 seconds of perpetual trades" | 1,641 |
| "Waiting for fresh UP and DOWN books" | 665 |

All 2,306 null-`feats` rows also have `p` NULL — the model never produced a call on those passes, so
there were no features to store. Measured from the first feats-carrying row instead, the steady state
is **1,054 rows over 4.5 min = 234/min, feats non-null 63.5%**, the remainder being the book-wait
rows. Usable rows for the early-fire study run at roughly 150/min.

## Third fix to the same line in my deploy helper
It printed `SHA256SUMS 39/38 OK` on this deploy: the denominator was `len(names)-2` after I replaced
the original hardcoded `/30`. Both numbers now come from the hash lines actually checked, so the line
cannot drift again. The verification itself was never wrong — 39 files verified against 39 hashes,
all matching `git show` — only the denominator printed next to it.

---

# 13.1.0 event-driven decide — SHADOW test (09-24)

Owner-approved via V. London and Mumbai untouched.

## Step 1 — build verified
stage 54f8ef0: 41 files, **SHA256SUMS 39/39 OK** == `git show`; `sha256sum -c SHA256SUMS.txt` clean
(0 non-OK lines); all nine suites **482 tests, OK**. Build string reads `13.1.0`.

## Step 2 — poll-mode baseline, measured BEFORE the restart
`analysis/zurich/decide_mode_metrics.py`. V asked for the 13.0.4 window; that is only **8 EF orders**
since 12:20:05, too thin to be a baseline, so the table below is the whole poll-mode raw arm since
01:36:04 on 09-23 (13.0.0 + 13.0.4, `decide_mode` was poll throughout and only logging changed).
Both are reported so nobody has to guess which window a number came from.

| metric | 13.0.4 only (n=8) | whole poll arm (n=166) |
|---|---|---|
| `book_age_ms` at fire p50 / p90 | 40.9 / 52.0 | **39.9 / 131.7** |
| `decision_ms` p50 / p90 | 2.08 / 2.24 | **2.08 / 3.25** |
| signal-ask -> fill, ticks p50 / p90 / mean | +0.00 / +0.00 / -0.00 | **+0.00 / +0.50 / +0.09** |
| partial fills | 0 | **12 of 166 (7.2%)** |
| refusals | 0 | **0** |
| decide passes | — | **3.76/s** (decide_log, 0.25 s cadence) |

**Two things about this baseline that limit the test, both structural, neither a reason not to run it.**

1. **Refusals cannot move.** Every order here is a `PaperBroker` fill that completes in-process —
   404 of 404 orders in this journal are `FILLED`, reason `venue-confirmed fill`, zero refusals ever.
   The refusal symptom that motivated 13.1.0 (London's refused attempt-1 orders priced on older books)
   is a *live-venue* phenomenon the shadow lane structurally cannot reproduce. Expect 0 before and 0
   after, and do not read that as "event mode fixed refusals".
2. **`passes/s` will not show the speed-up.** 13.1.0 throttles `decide_log` to one row per 250 ms in
   event mode (`btc_model_v12_polymarket.py:641`, fires exempt), precisely so the journal rate holds.
   So decide_log reads ~4/s in *both* modes by design. The fast passes are not journalled anywhere, so
   passes/s is not directly measurable from the DB; CPU% is the available proxy, and `book_age_ms` at
   fire is the outcome that actually answers "did EF see it sooner".

## Step 3-4 — 13.1.0 up, event mode on, 10-minute check

Clean 14:20:00 (sec 0), stopped pid 166436, deployed **39/39 == git show 54f8ef0**, started pid
**167283** 14:20:01 on the same argv and same live4 db. `decide_mode` set **event** at 14:20:27.
Unchanged: master false, raw_v10_live25, ev 0.25, calibration off, stake 5, `decide_log` true, halt null.

| 10-min check | value |
|---|---|
| decide_log rate | 3.82/s (poll was 3.76/s) |
| inter-row gaps | p10 250 ms, p50 267, p90 270, min **250** |
| `decide_loop_error` rows | **0** |
| `/api/state` error | **empty** |
| engine | alive, 118 tape rows/120 s |
| EF orders since the switch | 0 |

**The gap distribution proves the measurement limit rather than the speed-up.** The minimum gap is
exactly 250 ms and the p10 is 250 ms, which is the `_decide_log` throttle binding on essentially every
row. So 3.82/s is the *logging* rate in both modes by construction and says nothing about how often
the fast pass ran. Reporting it as "passes/s" would be reporting the throttle.

### A measurement bug of my own, caught before it was reported
The first event-mode CPU sample returned **0.0% over 300 s**. That was not the engine. `cpu5.py`
selected its pid with `pgrep -f pm_paper_zurich/.venv/bin/python`, and this session's own bash wrapper
carries that path in its command line, so it sampled a dormant shell (pid 166834). The poll baseline
of **28.7%** was unaffected — it did resolve to the real engine (166436) — but the event figure would
have been a fabrication. `cpu5.py` now selects the pid by matching `/proc/<pid>/cmdline[0]` against the
venv interpreter **and** requiring the engine script in argv, so no shell can match. Same root cause as
the phantom "duplicate engine" pids on 09-23: a pgrep pattern that matches the observer.

### CPU correction: 60.2%, not 50.9%
I sent V **50.9%** for event mode. That came from a **120 s** sample taken while the proper **300 s**
run was still going, and the poll baseline it was being compared against was 300 s — not like for like.
The matched 300 s figure on the same engine pid (167283) is **60.2%**.

| mode | window | CPU |
|---|---|---|
| poll (13.0.4, pid 166436) | 300 s | 28.7% |
| event (13.1.0, pid 167283) | 300 s | **60.2%** |

So event mode costs **2.1x** the CPU, not the 1.8x I reported. The direction and the conclusion are
unchanged — the fast passes are real and the box has the headroom — but the ratio I gave V was wrong
because I compared a 2-minute window against a 5-minute one.


## 13.1.1 (a881350) verified and staged, waiting on the 10-order report

484 tests OK, `sha256sum -c` clean (0 non-OK lines), 39/39 == `git show`. Not deployed yet — V's
order is the 10-EF-order report on 13.1.0 first, and that is at **2 of 10** at 14:47.

**Both changes in this build came out of measurement problems I reported rather than from a fault in
the engine**, which is worth recording because it is the useful half of the event-mode test so far:

| 13.1.1 change | the report it came from |
|---|---|
| `decide_min_gap_ms` live dial, default **50 ms** (was a hardcoded 20 ms floor) | my CPU correction: 20 ms cost **2.1x** poll, and the code comment now cites "Zurich 09-24" |
| `decide_log` keeps only a candle's **first** fire row | my finding that event mode logged **117 fire rows for one candle and one order** because fires are exempt from the 250 ms throttle |

So the 13.1.0 shadow run has not yet said anything about whether EF sees prices sooner — n is 2 —
but it has already paid for itself by exposing a 2x CPU cost and a logging artifact that would have
made fire counts look 6x higher across the mode switch.

## 13.1.1 deployed at 50 ms (09-24 15:15:03) — the 20 ms arm closes at n=2

Owner: "Switch to 50ms now", which replaced the after-10-orders gate. Clean 15:15:01, stopped pid
167283, **39/39 == git show a881350**, `sha256sum -c` clean, 484 suites OK, started pid **168424**.
Unchanged: master false, raw_v10_live25, ev 0.25, calibration off, stake 5, `decide_log` true,
`decide_mode` event, halt null.

**`decide_min_gap_ms` is left UNSET in meta on purpose.** V asked for "default 50", and
`decide_min_gap_s()` reads `db.get('decide_min_gap_ms', DECIDE_MIN_GAP_S*1000)` with
`DECIDE_MIN_GAP_S=.05` in the deployed file. So the effective gap is 50 ms via the code default and
the meta key reads `None` — that is correct, not a missed write. Setting it explicitly would only
pin the value against a future default change, which nobody asked for.

### The 20 ms arm, closed
| | 20 ms event | poll |
|---|---|---|
| EF orders | **2** | 167 |
| book_age_ms p50 / p90 | 56.4 / 91.6 | 39.9 / 131.7 |
| CPU | 41.1% (120 s), 60.2% and 51.4% (300 s), 21.3% (90 s) | 28.7% (300 s) |

The two book_age values were 21.2 and 91.6 ms. **n=2 is not a comparison** and the 20 ms arm never
produced one. Its only durable results are the two measurement findings — 2.1x CPU and the
117-fire-rows artifact — and 13.1.1 fixes both, so closing it early cost little.

## 10 orders at 50 ms — and the 13.1.1 "first fire only" change does NOT do what it says

| metric | 50 ms (n=10) | 20 ms (n=2) | poll (n=167) |
|---|---|---|---|
| `book_age_ms` p50 / p90 | **48.8 / 288.4** | 56.4 / 91.6 | **39.9 / 131.7** |
| `decision_ms` p50 / p90 | 2.00 / 2.24 | 1.74 / 2.94 | 2.08 / 3.25 |
| signal-ask -> fill, ticks | p50 +0.00, mean +0.06 | +0.00 | p50 +0.00, mean +0.08 |
| partial / refusals | 0 / 0 | 0 / 0 | 12 / 0 |
| CPU (300 s) | 39.1% | 60.2% | 28.7% |

**On this sample event mode is not beating poll on the metric it exists to improve.** p50 48.8 vs
39.9 and p90 **288.4 vs 131.7**. n=10 against n=167, so this is not a verdict — but it is the wrong
direction, and the p90 is more than double. The 60-order report is the one to judge on.

### The defect: `_decide_log`'s first-fire guard does not limit a candle to one fire row
Deployed code:
```python
first_fire = bool(d.get('fire')) and self.__dict__.get('_dlog_fire_ep') != ep
if not first_fire and t_ms - self.__dict__.get('_dlog_last',-10**12) < 250: return
```
The comment above it reads *"13.1.1: only the first"*. What the code actually does is guarantee the
**first** fire row is never dropped by the throttle. Every **later** fire pass in the same candle has
`first_fire=False` and therefore falls through to the ordinary 250 ms throttle, which lets it log at
4/s for as long as the signal holds.

Measured on the deployed build, 11 candles since 15:15:03: **591 fire rows across 11 epochs**, per
candle 101, 29, 133, 1, 5, 183, 88, 6, 1, 29, 15. On the busiest (epoch 1790268300, 183 rows) the gaps
between consecutive fire rows are **min 252 ms, p50 254, p90 260** over a 90.7 s run — that is the
250 ms throttle, not a once-per-candle rule.

So the artifact I reported on 13.1.0 (117 rows for one candle) is **not fixed**; it is now 183. The
guard changed which row is guaranteed present, not how many are written. Anyone who resumes counting
fires from `decide_log` because 13.1.1 "fixed it" will still see a 6-15x inflation. `count(distinct
epoch)` remains the only honest fire count.

## Ask-drift after the fire (V's metric) — and a +8-tick artifact it nearly produced

V, 09-24: book_age is the wrong test for "sooner", because firing right after a Binance tick means
firing *before* Polymarket re-quotes, so the book is older by construction. The discriminating test is
whether the ask **rises after** we fire. `analysis/zurich/ask_drift.py`, read-only.

**Measured against `signal_quote`, as briefed, the answer looks spectacular and is wrong.**

| baseline | POLL (n=162) | EVENT @50 ms (n=16) |
|---|---|---|
| vs `signal_quote`, +1s | **+7.90** ticks, 76.5% rose | +5.25, 68.8% |
| vs `signal_quote`, +2s | +7.81, 74.1% | +5.75, 68.8% |
| **vs tape's own ask at the fire second, +1s** | **+0.67**, 37.0% | +0.50, 37.5% |
| **vs tape, +2s** | +0.57, 45.7% | +1.00, 50.0% |

`signal_quote` is the **executor's** read; `up_ask`/`dn_ask` in `tape1s` are a **1 Hz snapshot taken on
the full pass**. They are different measurement sources. At the fire second itself the median gap
between them is already **0.050 = 5 ticks** (checked directly: same-side ask closer than the opposite
side in 148 of 201 orders, median same-side gap 0.050 vs opposite 0.150). So most of the "+7.9 tick
rise" is that constant offset, not market movement.

Taking both ends from the tape cancels the offset, and the real drift is **under one tick**. A +7.9
tick rise would have meant EF reliably buys 8 ticks ahead of an 8-tick move — an enormous edge, and
entirely an artifact of mixing two price sources.

**On the honest baseline the two arms are indistinguishable**: +0.67 vs +0.50 ticks at +1s, 37.0% vs
37.5% rose. n=16 against n=162 anyway.

**Time from the newest spot trade to fire is NOT journaled.** `since_tick_change_s` and
`last_tick_change` are non-null in **0 of 231** EF orders, and the aggTrade `E` field is consumed by
`on_depth` without being stored per order. That metric cannot be produced from this journal without a
code change; I am not proposing one.

---

# 13.1.2 + the poll/event A/B (09-24 19:30:02)

Deploy: clean 19:30:00, stopped pid 168424, **39/39 == git show 327de5f**, `sha256sum -c` clean,
**485 suites OK**, started pid **169816**. Settings all unchanged: master false, raw_v10_live25,
ev 0.25, calibration off, stake 5, `decide_log` true, `decide_mode` event, `decide_min_gap_ms` unset
so the 50 ms code default applies.

## Design note: arm membership comes from the order, not from my flip clock
13.1.2 journals `feed_timing.decide_mode` on every fired EF decision. `analysis/zurich/ab_decide_mode.py`
splits the arms on **that field**, not on the flip timestamps. A flip that lands late, or a flip I fail
to make, therefore cannot mis-assign an order — it only changes how many land in each arm. Orders whose
decision predates 13.1.2 carry no `feed_timing` and are **excluded and counted**, never guessed at.
The flip log (`out/ab_flips.jsonl`) is kept because V asked for it, not because the analysis needs it.

Flipper: `out/ab_flip.py 60 16` — 60 min period, 16 h cap, `Journal.set` only, no restart. First arm
EVENT from 19:30:02, so the first flip to POLL is due 20:30.

**The 13.1.1 60-order watcher was stopped.** That arm measured a single fixed mode on a build the A/B
supersedes; leaving it running would have sent a stale report against a cutoff that no longer describes
what the engine is doing.

## A/B interim (09-25 ~08:4x): the direct speed metric, and which one actually measures it

13 flips logged, arms split from each order's own `feed_timing.decide_mode`. POLL n=23, EVENT n=27
distinct epochs. 0 orders excluded for missing `feed_timing`.

| at fire | POLL (n=23) | EVENT (n=27) |
|---|---|---|
| `newest_rx_age_ms` p50 / p90 | 14.8 / 20.2 | **14.8** / 23.0 |
| `spot_rx_age_ms` p50 / p90 | **95.9** / 371.1 | **62.2** / 337.6 |
| `spot_exch_age_ms` p50 / p90 | 211.0 / 485.7 | 174.8 / 449.9 |
| `book_age_ms` p50 / p90 | 23.7 / 111.1 | 35.1 / 126.8 |

**V's prediction is right, but it describes `spot_rx_age_ms`, not `newest_rx_age_ms`.** Poll's spot
age sits mid-range of the predicted 0-250 band (p50 95.9) and event's lands in the predicted 0-50
neighbourhood (p50 62.2) — a 1.5x improvement in the right direction, and the earlier 10-per-arm cut
had it at 116.4 vs 43.8, 2.7x.

**`newest_rx_age_ms` cannot show the difference and should be dropped from the comparison.** It is
`min()` over four continuously-streaming feeds (spot, perp, depth, venue). With four independent
streams, *something* has always just arrived, so the minimum is ~15 ms whatever the decide cadence.
It measures feed density, not decide latency. Both arms read p50 14.8 — identical to one decimal,
which is the giveaway.

`book_age_ms` is *worse* in event (35.1 vs 23.7 p50), exactly as V predicted it would be: firing
sooner means firing before Polymarket re-quotes, so the book we price against is older.

**CPU caveat:** my sampler reads the process, not the arm, so a 300 s CPU sample lands in whichever
mode happens to be active. The 26.1% at the interim is a single-mode window, not a per-arm figure. A
per-arm CPU number needs the sample pinned inside one flip period; I will do that for the final.

## A/B FINAL — poll vs event at 30+ per arm (09-25 12:5x)

Same build 13.1.2, same market, same settings throughout. Arms split on each order's own
`feed_timing.decide_mode`; **0 orders excluded**. 15 flips in the first 16 h, flipper extended 3 h to
land the gate (reported to V rather than done quietly).

| at fire | POLL (n=33) | EVENT (n=30) | direction |
|---|---|---|---|
| `spot_rx_age_ms` p50 | **116.4** | **51.7** | event **2.3x fresher** |
| `spot_rx_age_ms` p90 | 433.0 | 337.6 | event better |
| `spot_exch_age_ms` p50 / p90 | 229.4 / 546.2 | 174.8 / 449.9 | event better |
| `newest_rx_age_ms` p50 | 15.7 | 14.8 | **no difference** |
| `book_age_ms` p50 / p90 | 26.4 / 111.1 | 35.2 / 126.8 | event worse, as predicted |

**The result: event mode does what it was built to do.** The spot feed at the moment EF fires is
2.3x fresher (116 ms -> 52 ms p50), and V's predicted bands hold almost exactly — poll mid-range of
0-250, event inside 0-50 at the p50.

`newest_rx_age_ms` never discriminated at any cut (15.7 vs 14.8 here, 14.8 vs 14.8 at the interim).
It is `min()` over four continuously-streaming feeds, so it measures feed density, not decide latency.

`book_age_ms` is worse under event and that is the *expected* consequence, not a regression: firing
sooner means firing before Polymarket re-quotes.

### Per-arm CPU, pinned inside single flip periods
The earlier CPU numbers were whole-process samples that landed in whichever mode happened to be
active, which is not a per-arm figure. `out/cpu_arm.py` reads `decide_mode` before and after and
**discards the sample if the mode changed mid-window**, so each number belongs to one arm.

| arm | window | CPU |
|---|---|---|
| EVENT | 300 s, 12:52-12:57 | **44.6%** |
| POLL | 300 s, 13:34-13:39 | **29.2%** |

Both samples passed the mode-unchanged check. **Event costs 1.53x poll** on the same build, same
settings, matched window length — and that is the honest per-arm figure. Every earlier CPU number in
this file was a whole-process sample that happened to land in one mode or straddle a flip; those
should be read as indicative only, and this pair as the result.

## The scheduled "24 h EVENT" job fired — and its label is wrong. Do not use it.

The job armed on 09-24 for step 5 of the 13.1.0 brief fired on time at 14:20 and printed
`13.1.0 EVENT, 24 h since 14:20:27 — EF orders 103, book_age p50 41.3 / p90 150.1`.

**That window is not an event-mode window.** Composition of its 103 orders:

| | |
|---|---|
| journalled `decide_mode` = event | **34** |
| journalled `decide_mode` = poll | **40** |
| no `feed_timing` (pre-13.1.2, mode not recorded) | **29** |
| builds spanned | 13.1.0 -> 13.1.1 -> 13.1.2 |
| gap dial | 20 ms until 15:15, 50 ms after |

The A/B flipping ran inside it for 18.8 of its 24 hours, so the line is a blend of both arms across
three builds and two gap settings. Read as an event-mode result it would say event and poll are
identical on `book_age` (41.3 vs 40.1) — which is only true because half the "event" sample is poll.

The clean answer already exists and I sent it 30 minutes earlier: the A/B at 30+ per arm, same build,
same settings, arms taken from each order's own journalled mode. **That is the result; this job's
output is superseded and should be discarded.**

I let this fire rather than cancelling it because the schedule was V's instruction, but the label it
carries is stale — a job armed before the experiment design changed under it.

## A/B closed — final engine state (09-25 14:32)

Flipper finished, 17 flips logged over 19 h. Engine is left on **`decide_mode = poll`**, which is
simply where the last flip put it, not a decision I made. Everything else as it has been all along:
13.1.2, pid 169816, master **false**, SHADOW, raw_v10_live25, ev 0.25, calibration off, stake 5,
`decide_log` true, `decide_min_gap_ms` unset (50 ms code default), halt null.

**Nobody has said which mode to settle on, so I have not chosen one.** The evidence for that decision
is in hand — event is 2.3x fresher on spot feed age at fire for 1.53x the CPU, and neither arm shows
any money effect that shadow can measure — but picking the standing mode is V's or the owner's call,
not mine. It stays on poll until someone says otherwise, and poll is the pre-experiment default, so
leaving it there is the conservative end.
