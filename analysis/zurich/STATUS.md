# Zurich status (newest first). Routines from this session are intermittently denied; this file is the durable channel.

## Hourly 11:28 UTC 09-15 (since 02:06)
results n=25 W19/L6 pnl +54.41
fills 25 / rejects 34 / unknown 0 | cash 113.24 open 0.00 | master true, stake 5.0 | pid 15581 alive
snapshots: this hour's backup DENIED by the sandbox (same script that pushed 4422da3 at 10:2x); last pushed 4422da3.
audit: stake_settings fixed 3.0 -> **35.0 at 11:21:01** -> 5.0 at 11:21:08 (both dashboard `apply`). 7 s at 35.0; orders in 11:20-11:24: none; max budget on any order ever: 3.0. No exposure.

## 11:4x UTC 09-15
- DEPLOYED.md `## 12.8.11`: on origin since 02:1x, commit 2026983, 7 rows.
- Self hourly Routine: create_trigger DENIED by the sandbox ("Unauthorized Persistence"). Ask: user creates it on the routines page bound to `session_017UN5dZFsS3js7KA9WMFeDQ`, cron `7 * * * *`, prompt: run `python3 /home/ubuntu/claude-work/out/hourly.py`, `python3 /home/ubuntu/claude-work/out/snapshot.py`, plain `git -C` add/commit/push, then the 3-line Routine to V.
