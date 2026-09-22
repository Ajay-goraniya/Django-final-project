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
