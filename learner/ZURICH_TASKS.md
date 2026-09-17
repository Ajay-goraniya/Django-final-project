# ZURICH_TASKS.md — V → Zurich (eu-central-2) session, `session_017UN5dZFsS3js7KA9WMFeDQ`. Same channel rules as AWS_TASKS.md.

Read first, in this order: `CLAUDE.md` (all rules, STRICT short-messages rule), `learner/HANDOVER_HEAD.md` (who is
who, channels), `learner/REMAKE_PLAN.md` (the plan), `learner/DEPLOYED.md` (what is live on Mumbai and how a deploy is
proven, §7), `learner/AWS_TASKS.md` Tasks 83-88 (the wire and book measurements this week). Polymarket only.
Boundaries: never touch the Mumbai box or its journal; never handle/print/commit secrets; no trading from Zurich
until V and the user say so in writing; messages to V <= 15 lines, numbers first; long output -> a file path.
Reply channel: one-shot Routine to V `session_01SmMRZqqMru5UdaeAoJarkr`. `SendMessage` does not work.

## Task Z-0 - identify yourself and the box
Region/AZ, instance type, public IP's `polymarket.com/api/geoblock` JSON (no secrets in it), Python version, whether
the repo is cloned on the box and at which commit, whether you can `git push` (dry-run) - say plainly if not.

## Task Z-1 - the wire from Zurich, same method as Mumbai's Task 83 and Task 87
1. `analysis/aws/task_83_wire.md` Block 2/3 repeated from Zurich: 50 warm GETs to `clob.polymarket.com/time`
   (handshake separately), TCP connect to both hosts, `cf-ray` colo code, `mtr -rwc 20` to both, IPv6 or not.
2. `analysis/aws/ws_gap_probe.py` for 600 s (run from `learner/v12_2` so the runner module imports; needs
   `websockets`): report maxgap p50/p90/p99/max, % seconds > 750 ms, maxlag p50/p90/max, ev/s, reconnects, with the
   exact UTC window. Mumbai's matched-window numbers to compare: maxgap p50 394 / p90 782 / max 3784, 10.7% > 750 ms;
   maxlag p50 89 / p90 250 / max 2074. Ohio: p50 399 / 792 / 3561, 11.3%; lag 60 / 173 / 1761.
3. The number that decides the region question: order-path round trip. You cannot post orders; measure the warm
   POST-shaped round trip you CAN make without credentials (e.g. an unauthenticated POST that returns 401 from
   `clob.polymarket.com`, 20 samples) and say what it is a proxy for.
Output: `analysis/zurich/task_z1_wire.md` if you can push, else <= 15 lines to V and V commits it.

## Task Z-2 (user, 22:5x) - deploy the model on Zurich, PAPER first. No keys yet.
Follow `learner/v12_2/DEPLOY_MUMBAI.md` on this box: venv, `pip install` the SDK/deps it names, copy `learner/v12_2/*`
from commit 7457816 (build 12.8.9) into your deploy dir, `sha256sum -c SHA256SUMS.txt` (30/30), `rm -rf __pycache__`,
run the three suites (expect 68 + 21 + 157 = 246 OK). Then start PAPER:
`python btc_model_v12_polymarket.py --mode pnl --capital 50 --db polymarket_v12_paper_zurich.sqlite3 --port 8787 --quote-age-ms 2000`
(no `--live`, no credentials). Seed via the controls page or Journal.set_many: ef on, main/rev off, stake fixed 3.0,
master on (paper). Report: hashes, suite counts, pid, first decide rows, AMBIENT_AGE, geoblock JSON. This is a
paper twin of Mumbai's live build on the Zurich path - it measures decisions/fills at 2 s quote age from here.
LIVE on Zurich: only after (a) the user's key transfer (never through chat) and (b) V's written go, because live on
two boxes with one wallet double-trades. `--live` runs the geoblock pre-check first; that result is the answer the
user wants.

## Z-4 - the stuck UNKNOWN order: facts before any fix. Read-only, no engine change, no restart.
Code read (V, poly_live.py reconcile + poly_core.py Executor.reconcile): a non-404 error from get_order returns
terminal=False every second forever; the venue_absent counter (mark_venue_open, from account open_order_ids) is
maintained but never used to resolve; and grade() skips the whole candle while an UNKNOWN row exists, and its budget
stays reserved (your "open 2.82"). So the loop is a real 12.8.x defect. Before I write the fix, the running facts:
(a) ONE reconcile diagnostics row for that order, compact: phase, class, message (first 200 chars), status code.
    Say which call fails: list_account_trades (phase 'reconcile') or get_order (phase 'reconcile_get_order').
(b) The orders row: id last 8 chars, epoch, ts, status, error (compact), reconcile_count, venue_absent, venue_live,
    venue_checked, plan.budget, plan.cap, plan.amount.
(c) Venue truth, plain reads with the deployed client (no writes): is the id in the account's open orders now; does
    list_account_trades(token, after=ts-120) show any taker trade with that taker_order_id; venue cash now vs engine
    cash.
(d) Did that epoch grade (results row present?) and what is candles/venue outcome for it.
Commit as analysis/zurich/z4_unknown_order.md, push, reply ≤8 lines with the hash. The fix (12.8.11) follows §7
only after these facts; nothing ships on a reconstruction.

## Z-5 - deploy 12.8.11 under §7 at the next clean moment. The stuck-UNKNOWN fix. Master stays OFF after restart.
Commit: the one this task lands in (git log -1 on learner/v12_2). Row 6 first: `git diff <running 12.8.9 commit> HEAD -- learner/v12_2/poly_live.py learner/v12_2/poly_core.py`
must be exactly: (1) poly_live.LiveBroker: ABSENT_PROOF=3, ABSENT_PROOF_AGE_S=60; in reconcile() the `if fills:` check
moves above the get_order-error branch, and that branch resolves verified_no_fill when venue_absent>=3, age>=60 s,
no trade and nothing unsettled - otherwise unchanged; (2) poly_core.Executor: `_stuck_reported=set()` in __init__,
and reconcile() writes ONE `RECONCILE_STUCK` diagnostics row per (order, class, message) when the broker returns a
non-terminal JSON reason; build 12.8.10 -> 12.8.11 (12.8.9 -> 12.8.11 on your box, nothing from 12.8.10's census
changes the order path; that build was Mumbai's). Nothing in decide, fire or pricing changes.
Fail-on-old (must FAIL on the running tree, PASS on staged): test_polymarket.LiveBrokerSimulationTests.
test_unreadable_get_order_resolves_on_repeated_venue_absence, .test_unreadable_get_order_still_takes_a_confirmed_trade,
test_polymarket.Tests.test_stuck_reconcile_is_recorded_once_not_every_second. Suites: 71 + 21 + 163 = 255.
SHA256SUMS 30/30. `rm -rf __pycache__`. Same argv as now (--quote-age-ms 2000); ev_settings preserved.
Clean moment = no open position and no order in flight (orders status not in SUBMITTING/PENDING; the UNKNOWN one is
the patient, it may stay). After restart: safe-start leaves master OFF - do NOT arm; the user arms on the dashboard
or tells V. Expected effect within ~3 reconcile ticks: order ...64f7d150 -> NO_FILL, reason "get_order unreadable
(UnexpectedResponseError); absent from account open orders Nx over Ns and no account trade"; reserve drops by 2.88;
epoch 1789432500 then grades on the next grade_loop pass (DOWN, unfilled winner, n stays). DEPLOYED.md `## 12.8.11`
section: commit it yourself (you can push now) - 7 rows, verbatim numbers, <=25 lines. Reply <=8 lines.

## Z-6 - deploy 12.9.0 under §7, user's go 17:2x. Same journal (polymarket_v12_live_zurich_2.sqlite3), same argv.
Commit 76d9eb6 (or later HEAD; build '12.9.0'). Row 6 first: `git diff 2cf8b6d HEAD -- learner/v12_2/` must be the 7
items of analysis/v/plan_12_9.md, nothing in decide/EV/pad/threshold: POST_FLOOR_S=0.4 BUDGET release; FeatureState
array cache (_rev); sign_off_loop in poly_live; diagnostics_ts index + 60 s/hourly housekeeping cadence; publish()
on quote_age_s() and gate require_depth=executor's; dashboard exchange_latency_ms + 1 s poll; PaperBroker.
account_snapshot/BookCache.clear removed, --mode hidden. Suites 71+21+188=280. Fail-on-old: 22 of the 25 new tests
must FAIL on the running 12.8.11 tree (3 pass by design: test_above_the_floor_still_posts,
test_sdk_sign_order_awaits_nothing, test_main_oneshot_returns_at_once_when_main_is_off). SHA256SUMS 30/30.
`rm -rf __pycache__`. Clean moment: no open position, no order SUBMITTING/PENDING. Restart; safe-start parks master
OFF - do not arm, the user does. ev_settings (quote_age 750, regime, pad 1, band) and stake_settings fixed 5.0 carry
over in the journal - verify they read back unchanged after start.
Then WATCH the first two live orders: order-identity check passed (no halt), status FILLED/REJECTED not UNKNOWN,
timing fire_to_submit_ms vs the 12.8.11 median 50 ms, and one RECONCILE_STUCK count. If halt='Order hash mismatch'
appears: stop, do not clear it, write hourly.md with the halt text; V decides. DEPLOYED.md `## 12.9.0` ≤25 lines,
7 rows, commit + push with plain git -C. Report via analysis/zurich/hourly.md (overwrite) - 4 lines.

## Z-7 - CLOB round-trip geography (read-only). Same as AWS Task 96 from Zurich: 20 curl timings each of
https://clob.polymarket.com/time and /book?token_id=<current token>; median/p90 connect + TTFB ms; traceroute -n -m 12
first/last 3 hops. Write analysis/zurich/z7_clob_rtt.md (≤6 lines), git -C add/commit/push. Live engine untouched.

## Z-8 - deploy 12.10.0 while master is OFF (user turned it off 00:49; ON is scheduled 03:00 UTC by trigger).
Logging-only build (DEPLOYED.md 12.10.0): decisions identical to 12.9.0. Same §7 procedure: stage learner/v12_2 at the
12.10.0 commit into a new deploy dir, `sha256sum -c SHA256SUMS.txt` 30/30, run the three suites (282), `rm -rf
__pycache__`, stop pid 72358 cleanly (master is off, 0 open positions - confirm), start on 8787 with the SAME journal
polymarket_v12_live_zurich_2.sqlite3 and the same argv; verify /api/state build 12.10.0, master false, and that the
next signals row's decision.features carries ref_open_bps/ref_move_bps/ref_gap_bps. Write analysis/zurich/hourly.md
(3 lines: old pid/new pid, build, first decision row with ref keys), push. Do NOT arm master - the 03:00 trigger does.
If anything fails, leave the OLD build running and say so in hourly.md.

## Z-11 - deploy 12.12.0 and set the owner's floor. USER ORDER: "ef off if bankroll goes below 30$ in central 2".
Cash was 45.71 at 03:05, so this is not urgent-urgent, but it is the owner's stop and it should exist tonight.
UNTIL IT IS DEPLOYED you are the floor: at every hourly, if equity (cash + venue_state.open_value) < 30, set
ef_enabled false through the audited apply and say so in hourly.md. Then: git pull; stage learner/v12_2 at the
12.12.0 commit; sha256sum -c 30/30; suites 71+21+206=298; rm -rf __pycache__; at a clean moment restart 8787 on the
same journal/argv; re-arm master (the user's setting); then set meta ef_cash_floor=30 through the audited path and
verify /api/state or the journal shows it. Report 3 lines: pid/build, floor set + current equity, master/halt.
The floor turns EF off only - never master, never a halt - and does not re-enable itself.

## Z-13 - deploy 12.12.2, and one standing rule that matters more than the build.
STANDING RULE from the 4-hour gap: the restart and the re-arm are ONE step. Never end a tool call with a live engine
restarted and master off - put the stop, the start and the audited arm in the same command, and verify master true in
that same output. If an approval is needed, get it before the restart, not after.
Deploy: git pull; stage learner/v12_2 at the 12.12.2 commit; sha256sum -c 30/30; suites 71+21+210=302; rm -rf
__pycache__; at a clean boundary stop/start/re-arm in one command on the same journal + argv; verify meta.build
12.12.2, master true, ef_cash_floor 30. Then confirm in hourly.md that the next MASTER_OFF row appears only if master
is genuinely off past 5 minutes (it should not appear at all in normal running).
