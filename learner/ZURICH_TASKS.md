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
