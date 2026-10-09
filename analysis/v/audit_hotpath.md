# Hot-path audit, v12_2 live engine (build 12.8.11), 2026-09-15

Static trace of `learner/v12_2/` + three measurements run in this container against the modules
themselves (not the Tokyo box; CPU/disk differ, treat as order-of-magnitude):

| measurement | result | how |
|---|---|---|
| `FeatureState.features()` with 20-min buffers (48k spot, 72k perp rows) | **14.8 ms** per call; `Model.decide()` 15.2 ms | `btc_model_v10.py` itself, synthetic tape at 40 spot/s + 60 perp/s |
| one sqlite `INSERT`+commit under the Journal's PRAGMAs (`synchronous=FULL`, `journal_mode=DELETE`) | **1.05 ms** (ext4/virtio); `SELECT meta` 0.01 ms | same PRAGMAs as `poly_core.py:362` |
| EIP-712 `sign_typed_data` (installed eth_account) | **5.3 ms** | same call the SDK makes at `async_secure.py:3464` |

SDK = `polymarket-client 0.10.0` installed at `/usr/local/lib/python3.11/dist-packages/polymarket` (pinned by `poly_live.py:23`).

## 1. Chain trace

Files: `F`=poly_feeds.py, `R`=btc_model_v12_polymarket.py, `U`=btc_model_v10_runner.py, `M`=btc_model_v10.py, `C`=poly_core.py, `L`=poly_live.py, `N`=poly_lanes.py, `D`=poly_dashboard.py, `SDK`=polymarket package.

### (a) Binance message -> handler

| step | where | awaits / sleeps / locks / writes / HTTP / threads |
|---|---|---|
| 4 sockets, one per logical stream, raw `/ws/` URLs | `F:46-63`, gathered at `R:740` | none |
| connect | `F:191` `websockets.connect(ping_interval=15, ping_timeout=10, open_timeout=15, max_size=4MiB)` | await |
| receive | `F:196` `await asyncio.wait_for(w.recv(), 8.0)`; timeout -> `ConnectionError` -> reconnect | await |
| parse | `F:199` `json.loads`; `F:200-201` unwrap combined envelope | CPU only |
| event stamp | `F:202-206` first of `j['E']`, `j['T']` | |
| handler | `F:207` `handler(j)` (sync, on loop) | |
| health | `F:208` `health.note(name, stamp)` **after** handler -> `F:117-130` | dict writes |
| reconnect | `F:211-216` `reconnects+=1`, rotate host, `print`, `await asyncio.sleep(2)` fixed, no backoff | sleep 2 s |
| wrapper | `R:705-711` `age[name]=time.time()`, `msgs[name]+=1` | |

### (b) handler -> FeatureState

| stream | path | work |
|---|---|---|
| spot aggTrade | `R:126-129` -> `U:127-128` -> `M:82-87` (4 deque appends + `_trim` `M:74-80`); `N:248-252` (3 `RollingDelta.add`) | ~1 us measured |
| perp trade | `U:130-141` aggregates same `(T,m,p)` prints; emits the **previous** print only when a different key arrives -> `M:89-95` | last print held until next distinct trade |
| perp depth20@100ms | `R:130-136` -> `U:143-150` (two 20-level list comps + sums) -> `M:97-105` (replace tuple); `R:133-135` rebuilds the lists again for `N:254-255` | ~10 us, 10/s |
| kline_5m | `R:137-144`; on close `db.sql INSERT candles` `R:144` | **sqlite write on loop**, 1 per 5 min |
| venue book | `R:85-125`: `await wait_for(w.recv(),15)` `R:112`; text PING every 5 s `R:102-103`; `books.apply` `C:133-185`; `publish()` `R:117` -> `quote()` x2 `C:186-211` (each builds `sorted(asks.items())` `C:210`) -> `M:107-110`; `health.lag['venue']=book age` `R:82` | per venue msg |

No handler triggers a decision; all return to the loop.

### (c) decide loop

| step | where | cost / blocking |
|---|---|---|
| loop | `R:235-252`: `await _decide_once()` then `await asyncio.sleep(.25)` `R:252` | **timer-driven, period = 250 ms + work** |
| exception path | `R:249-250` `INSERT diagnostics` | write |
| `decide_now()` | `R:145-174` | |
| both books fresh | `R:147` `publish()` -> `quote()` x2 (age <= `quote_age_ms`, default 750 ms `R:752`, live dial <= 2 s `R:670`) | |
| Binance usable | `R:148` `health.stale(spot,perp,depth)` `F:145-161` (arrival 6/6/2 s, event lag 2.5 s) | |
| warm | `R:151` | |
| EV mode | `R:156` `ev_setting()` -> `db.get` `R:636` | SELECT |
| model | `R:157-159` `m.decide` `M:230-283` -> `features()` `M:244` + `p_up` `M:210-216` | **~15 ms** |
| features again | `R:160` `st.features()` a **second** time, only for `d['features']` (diagnostics/dashboard) | **~15 ms** |
| calibrate | `R:172` -> `calibration()` `db.get` `R:177` | SELECT |
| padded-EV gate | `R:173` -> `R:217-234`: `quote()`, `pad_ticks()` `db.get` `R:227`, `db.get next_stake` `R:227`, `slippage_mode()` `db.get` `R:229`, `order_plan` `C:247-345` | 3 SELECT |
| dials | `R:256` `_sync_executor_dials` -> 3 `db.get` `R:662-664` | 3 SELECT |
| permission | `R:257` `ui.allowed()` `D:74-76`: 5 `db.get` + `daily()` (SQL `D:61` + 2 `db.get`) + `banned()`; cash age < 15 s (`cash_at` from housekeeping `R:430` / venue truth `R:695`) | ~8 SELECT |
| stake / reserve | `R:258-259` `db.get next_stake`, `live_reserve()` -> `reserve_detail` correlated-subquery SELECT `C:705-719` | SELECT |
| no terms | `R:265-268` `INSERT diagnostics` | write (fire skipped) |
| features third time | `R:270` | **~15 ms** |
| fire | `R:273` `await executor.fire(..., reassess=lambda: decide_now())` | blocks loop up to budget |
| lanes | `R:275` `lane_loop` `R:303-395`: `health.stale`, `lanes.evaluate` `N:519-529` (`compute` `N:324-390`, `avg_move` O(300) `N:98-106`), `monitor` `N:531`; on a decision: `quote()` x2, **`INSERT diagnostics` `R:350` before permission check**, `allowed(kind)`, `db.get`, `live_reserve`, `features()` for threshold `R:368`, `executor.fire` `R:372`, `SELECT signals` `R:376`, `SELECT diagnostics` `R:381` | |
| decision log | `R:276-277` `INSERT diagnostics` with full decision json every 15 s (`_decide_last`) | write |

Baseline per tick with no fire: 2 x `features()` ~30 ms + ~17 SELECTs + lanes. At 4 Hz that is ~12% loop duty in feature builds alone, during which no websocket message is processed.

### (d) EV gate

| where | rule |
|---|---|
| `M:262` | `ev = ps*(1/cost(ask)-1) - (1-ps)`, `cost(q)=q/(1-fee*(1-q))` `M:218-219` |
| `M:221-228, 277-280` | threshold from `regime` rv60 terciles (or fixed via `ev_settings`) |
| `M:253-261` | window 15..240 s, both venue sides quoted, `0<ask<1` |
| `C:294-298` | re-judged at `ask + EV_REFERENCE_PAD(1) tick`: `p/cost-1 >= threshold` else `ValueError` |
| `C:314-321` | depth-at-cap check (`require_depth = broker.all_or_nothing` = False live `L:19`, so skipped) |
| `C:344` | venue minimum shares |

### (e) Executor.fire -> sign -> post  (`C:881-1015`, live broker `L`)

| # | where | what | await / write / HTTP |
|---|---|---|---|
| 1 | `C:882` | `db.get('halt')`; `db.reserve` **INSERT signals** (json.dumps(d) incl. ~30 features) | **WRITE 1** (commit+fsync) |
| 2 | `C:883` | `deadline = min(start+2.0 s, sec 240)` | |
| 3 | `C:895-899` | quote wait: poll `quote(token, age)` every `await asyncio.sleep(.005)` until fresh or deadline -> `release DEADLINE` (`C:497-521`: 5 statements, 1 txn + diagnostics) | sleeps |
| 4 | `C:910` | `reassess()` = full `decide_now()` (2 x `features()`) | **~30 ms CPU** |
| 5 | `C:916-920` | tick diagnostics into `timing` | |
| 6 | `C:921` | `order_plan`; refusal -> `release SKIPPED` + `INSERT diagnostics` `C:930-934` | writes on refusal |
| 7 | `C:937` | `await wait_for(broker.prepare, deadline-now)` -> `L:51` `create_market_order(max_price=cap, FAK)` -> `SDK async_secure.py:2457-2484` -> `market.py:130-166` (protected path because `max_price` set, `market.py:342-345`): `resolve_market` = cache, TTL 600 s `cache.py:29` (miss -> REST GET market); tick-grid validate `market.py:145`; **on `UserInputError` -> forced REST refetch `market.py:147`**; `_sign_order` `async_secure.py:3458-3474` sync secp256k1 on the loop; `TrackedClient` re-encodes + keccak for `journal_hash` `L:31-37` | ~6 ms CPU; HTTP only on cache miss / tick mismatch |
| 8 | `C:943` | deadline check -> `release DEADLINE` | |
| 9 | `C:952-953` | `latest = quote()`; **if None -> `continue`** (burns attempt n, discards signed order, no sleep; next iteration re-enters the 5 ms poll) | |
| 10 | `C:955` | `reassess()` again | **~30 ms CPU** |
| 11 | `C:957` | `order_plan(latest)` again -> `release EV_CHANGED` | |
| 12 | `C:960` | `db.order` **INSERT orders** (json.dumps(plan), json.dumps(timing)) | **WRITE 2** |
| 13 | `C:962` | `await wait_for(broker.post, min(1.2 s, max(.001, deadline-start)))` -> `L:56` `client.post_order` -> `SDK async_secure.py:3376-3383` -> httpx AsyncClient, HTTP/2, keepalive 30 s, connect 5 s/read 10 s (`clients/_transport.py:27-39`); cancellation at 1.2 s = ambiguous | **HTTP** |
| 14 | `C:966-972` / `C:975-982` / `C:983-1008` / `C:1009-1014` | `order_status` UPDATE + `status` UPDATE, `_sample` (list <= 500), `print` | 2 writes after post |
| 15 | `C:1007` | FAK unmatched -> `await asyncio.sleep(0.075)` -> next attempt (max 4, `R:757`) | |
| 16 | `C:1015` | `EXHAUSTED` | write |

Between the fire decision and the POST leaving: **2 sqlite commits + 5 `features()` builds (~74 ms) + sign (~6 ms) + 3 `order_plan` + quote reads**, all synchronous on the event-loop thread. `timing_json.decision_ms`, `final_recheck_ms`, `sign_ms`, `fire_to_submit_ms` in `orders` record exactly this on the live box - read those, not this estimate.

### (f) reconcile

| where | what |
|---|---|
| `R:564-569` | `reconcile_loop`: `await executor.reconcile()`, `_main_oneshot_check` (`SELECT ... diagnostics ... LIKE '%control_write%'` full scan `R:553-554`, only when `main_enabled`), `await asyncio.sleep(1)` |
| `C:1016-1048` | SELECT open orders `C:1017`; per row `await wait_for(broker.reconcile(r), 8)` `C:1022` -> `L:98-141`: paginated `list_account_trades` HTTP `L:79` + `get_order` HTTP `L:102`; `reconcile_touch` UPDATE `C:1030`; fills INSERT `C:1041`; terminal -> `order_status` + `status` UPDATE `C:1046`; **`halt_check()` every second regardless** `C:1048` -> ~4 SELECTs incl. 3-table `kill_window` join `C:745-756` |
| `R:681-704` | `venue_truth_loop` 20 s: 5 HTTP via gather `L:224-226`, `venue_snapshot` INSERT, `apply_venue_pnl` UPDATE per row, `mark_venue_open` UPDATE per open order `C:673-697` |
| `L:139` | no-fill proven after age >= 2 s and 2 misses; `L:133` unreadable get_order after 3 absences + 60 s |

### Other loops touching the same thread / DB

| loop | period | on-loop cost |
|---|---|---|
| `housekeeping` `R:400-437` | 5 s | `INSERT diagnostics feed_counters` `R:412`; terms via `broker.metadata` = 2 HTTP per token per 30 s `R:417` (`L:43-46`); `account_snapshot` = cash + open orders + positions HTTP every 5 s `R:424`; `update_stake` holds `db.lock` across ~8 statements `D:123-150`; `_sample_ambient_age` INSERT `R:432`; wait-census INSERT per 60 s `R:433`; **`DELETE FROM diagnostics WHERE ts<?` and `DELETE FROM candles` every 5 s `R:434-435` - `diagnostics` has no index on `ts` (`C:368`), full scan** |
| grade / claim | 20 s | REST via `to_thread` `R:574`; relayer HTTP |
| dashboard | HTTP thread (`ThreadingHTTPServer` `D:593`), browser polls `/api/state` every 250 ms (`dashboard_html.html` `setTimeout(pollState,250)`), snapshot cache 0.5 s `D:480` | ~25 SELECTs per rebuild incl. `rolling()`/`kill_window`, `reserve_detail`, `orders()`, `pnl()` x2; **same sqlite connection as the loop** (`check_same_thread=False` `C:360`), `Journal.lock` RLock held per statement `C:432`; `json.dumps(_json_safe(body))` under the GIL `D:549` |

## 2. Answers

**Q1 cadence.** Timer-driven: `decide_loop` sleeps 0.25 s after each pass (`R:252`), so the model runs at most ~4/s, period = 250 ms + pass time (~30 ms baseline, up to the 2 s execution budget + lane work when firing). Nothing in the Binance or venue handlers triggers a decision. Effective gates on each pass: both books fresh within `quote_age_ms` (`R:147`), Binance arrival/lag limits (`R:148`), warm-up (`R:151`), 15-240 s window (`M:253`), cash age < 15 s and `allowed()` (`R:257`). Paper runner is the same 0.25 s (`U:300`).

**Q2 writes before post.** EF path: **2 commits** - `signals` INSERT (`C:882` -> `C:486-490`) and `orders` INSERT (`C:960` -> `C:522-524`). Lane path adds the `diagnostics` INSERT at `R:350` (written before the permission check). Refusal branches add 1 txn of 5 statements (`release`, `C:497-521`) + a diagnostics row. All are synchronous `sqlite3` calls **on the event-loop thread** (`Journal.sql` `C:432`, no `to_thread`), each its own transaction with `synchronous=FULL` + `journal_mode=DELETE` (`C:362`) = journal create/fsync/db fsync/journal unlink per commit (1.05 ms here; cloud disk on the Tokyo box UNSURE, read `timing_json` to see). After the POST: 2 more UPDATEs.

**Q3 lag.** `FeedHealth.note` (`F:117-130`): `lag = time.time() - event_ms/1000` where `event_ms` is `j['E']` (Binance **event time, Binance's clock**; `T` only if `E` is absent), taken **after** `handler(j)` ran (`F:207-208`). So spot/perp/depth `lag` = local receipt time minus exchange event time = one-way network Binance->box + Binance publish delay + local clock offset (negative clamped to 0, kept as `clock_skew_s` `F:127-129`) + any time the message sat in the socket buffer behind loop work (a 30 ms decide tick or a sqlite DELETE scan shows up as lag). Last message only, no averaging. `stale()` blocks fires when it exceeds 2.5 s (`F:88, 158-160`). Venue `lag` is a different quantity: book age from `quote()` (`R:82`). Dashboard: JSON exposes `feed.event_lag_s` / `feed.arrival_age_s` (`D:88`, `F:163-173`); the HTML shows `feed.last_event_age_ms` = **spot arrival age** (`D:92`) as "N ms old", and `feed.exchange_latency_ms` (`dashboard_html.html:138`) which **no code sets** - that field is always `--`.

**Q4 Binance connections** (`F:46-63`, env-overridable `BINANCE_WS_*`):

| stream | primary host / path | fallback | notes |
|---|---|---|---|
| spot | `wss://data-stream.binance.vision/ws/btcusdt@aggTrade` | `stream.binance.com:9443` | aggTrade |
| perp | `wss://fstream.binance.com/ws/btcusdt@trade` | same host, combined `/stream?streams=` | raw trades, aggregated locally `U:130-141`; `X:NA` zero prints filtered `M:90-93` |
| depth | `wss://fstream.binance.com/ws/btcusdt@depth20@100ms` | combined | **perp** partial book, full 20-level snapshot every 100 ms; not a diff stream, so no sequence ids and no resync needed; none exists |
| chart | `wss://data-stream.binance.vision/ws/btcusdt@kline_5m` | `stream.binance.com:9443` | |

Four separate sockets, not a combined stream (combined only as fallback URL, unwrapped `F:200-201`). Ping/pong: library `ping_interval=15 s, ping_timeout=10 s` (`F:191`) plus an application stall rule: no frame in 8 s -> `ConnectionError` -> reconnect (`F:196-198`, `STALL_RECONNECT_S` `F:90`). Reconnect: any exception -> rotate to next host, fixed `sleep(2)`, no backoff, no cap (`F:211-216`).

**Q5 vs build 36** (`week_replay/scripts/btc_model_v9_3_build36.py`, Predict.fun):

| | build 36 | v12_2 |
|---|---|---|
| order type | value-denominated MARKET BUY, `isMinAmountOut=True` floor (`:598-625`, `:12255`), no price ceiling | FAK BUY with `max_price` cap = ask + pad ticks (or band %) (`C:259-273`, `L:51`) |
| tolerance | 5000/4118/3333/1667/909 bps by VWAP band (`:618-625`) | ticks (default 1, `R:752`) or band 100/70/50/20/10 % (`C:235-236`) |
| signing | **pre-signed "hot" order** built ahead of the signal, re-signed on book change with 200 ms floor (`:11037-11056`, `:652`) | signed **inside** the fire path after the signal (`C:937`) |
| attempts | 1 + 3 replacements, only on explicit terminal rejection; timeout = UNKNOWN reconciled by hash (`:643`, `:11188`) | 4 attempts (`R:757`), retry only on FAK-unmatched wording (`C:1001-1003`), 75 ms pause (`C:849`); timeout = UNKNOWN reconciled by id |
| budget | `TOO_LATE` under 3 s remaining (`:646`), status poll 2 s at 0.5 s (`:644-645`), HTTP timeout 6 s (`:577`) | 2 s total, 1.2 s post (`R:755-756`), reconcile 1 s (`R:569`) |
| threads | signing/posting on worker threads behind `submit_gate` (`:12550`) | everything on the asyncio loop |
| time spent | sign off the hot path; POST round trip only | quote wait + 2 x decide_now (~60 ms) + sign (~6 ms) + 2 commits + POST |

**Q6 observation-only code on the hot path** (calls/s x work):

| item | where | rate | est. cost |
|---|---|---|---|
| second `features()` for `d['features']` | `R:160` | 4/s | **~15 ms each = ~60 ms/s (6% loop)** - the largest |
| third `features()` on fire | `R:270` | per fire | ~15 ms |
| `health.note`, `msgs` counters (two copies) | `F:208`, `R:709-710` | ~110 msg/s | ~1 us each, negligible |
| `sorted(asks.items())` inside `quote()` | `C:210` | 2 per venue msg + 2 per tick + 2 per lane decision + dashboard | tens of us each, <1% |
| wait census / `block_detail` | `R:494-503`, `C:197-209` | per refusal | us |
| decision json row every 15 s | `R:276-277` | 1/15 s | 1 commit |
| lane decision row + ask lookup | `R:342-351` | per lane decision | 1 commit |
| `timing` dict, 2 `json.dumps`, `_sample`, 300-char `print` | `C:885-1013` | per attempt | << 1 ms vs the commit |
| feed_counters + ambient age rows | `R:412`, `R:432` | 2 per 5 s | 2 commits / 5 s |
| `DELETE diagnostics/candles` retention | `R:434-435` | 2 per 5 s | full scan of an unindexed table growing ~30k rows/day, 7-day keep; UNSURE size on the box |
| `halt_check` (watch-only since 12.8.8) | `C:1048` | 1/s | ~4 SELECTs incl. 3-table join |
| `_main_oneshot_check` LIKE scan | `R:553` | 1/s when MAIN armed | full diagnostics scan |
| dashboard snapshot | `D:480-528` | 2/s | ~25 SELECTs on the HTTP thread holding `Journal.lock` per statement + GIL for json |

## 3. Defects / suspicious (mark UNSURE where not proven)

1. **Sub-100 ms POST timeouts are possible.** `C:962` `wait_for(post, min(1.2, max(.001, deadline-start)))`: the deadline check at `C:943` runs before the second reassess (~30 ms) and `order_plan`; near the 2 s budget a request can be sent with a few-ms timeout, cancelled mid-flight, and land as UNKNOWN/PENDING (reserve held until reconcile proves absence, >= 2 s + 2 misses `L:139`). Proven from code; frequency UNSURE - check `orders` where `json_extract(timing_json,'$.fire_to_submit_ms') > 1900`.
2. **Dashboard latency field is dead.** `feed.exchange_latency_ms` is read by the page (`dashboard_html.html:138`) and set nowhere; the visible "N ms old" is spot **arrival** age, not data lag. The real `event_lag_s` is JSON-only.
3. **Feature builds dominate loop CPU.** `features()` rebuilds `np.fromiter` over the full 20-min deques every call (`M:118-119,137-138,148-150`), ~15 ms at 120k rows, and is called 2x per tick + 5x per fire attempt. This inflates `decision_ms`/`final_recheck_ms` and, because `health.note` runs after the handler, also inflates the measured Binance lag. Proven by measurement here; box numbers in `timing_json`.
4. **Two fsync'd commits sit between decision and POST** on the loop (`C:882`, `C:960`), plus per-tick DELETE scans and housekeeping writes on the same connection, with the dashboard thread contending for the same `RLock`. Per-commit cost on the Tokyo disk UNSURE.
5. `latest` None -> `continue` (`C:952-953`) consumes an attempt and discards a signed order without a sleep; the next iteration's 5 ms poll does the waiting. Attempt accounting off by one on a momentary stale book. Minor.
6. Lane decisions write `diagnostics` **before** `allowed(kind)` (`R:350-352`) - by design, but it is a commit on the loop each time a lane decides.
7. Perp aggregation (`U:133-141`) emits a print only when the next distinct key arrives, so the freshest perp trade is absent from `FeatureState` until then. Materiality UNSURE (60 trades/s typical, seconds in quiet tape).
8. SDK `prepare` can do a REST GET inside the budget if the cached tick size no longer matches the cap (`market.py:144-148`) - i.e. right after a `tick_size_change` the engine has not yet refetched terms for (`C:154-164`, housekeeping 5 s). Bounded by `wait_for(deadline)`; frequency UNSURE.
9. `poll` of `/api/state` every 250 ms with a 0.5 s cache means the HTTP thread rebuilds ~25 queries twice a second whenever a browser is open; each statement blocks the loop's `db.get` calls (~17 per tick). Magnitude UNSURE - depends on `results`/`fills`/`orders` sizes.

Not defects, checked: deadline arithmetic at `C:883` mixes monotonic and wall correctly; SDK HTTP retry is 429-only (`_internal/retry.py:33-44`), no silent re-POST on timeout; `prepare` makes no REST call on the warm path (metadata cache TTL 600 s, seeded by housekeeping's `fetch_current_market` `L:45`); httpx keepalive 30 s is kept warm by the 5 s `account_snapshot` (UNSURE the CLOB and data hosts share one pool).
