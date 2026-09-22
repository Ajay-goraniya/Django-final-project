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
