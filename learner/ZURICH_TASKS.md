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
