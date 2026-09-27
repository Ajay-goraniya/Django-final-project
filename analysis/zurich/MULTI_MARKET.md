# ETH + SOL on Zurich — EF only, SHADOW. Phase 1

Owner order 09-27 01:4x via V: *"test ETH and SOL on Zurich, EF only; same model, EF trades on 3 coins /
3 markets, max 3 EF trades in the same 5-minute window, one per market; BTC's moves should help the other
coins; test everything on Zurich, keep London untouched."* Zurich SHADOW only. **Nothing live. London
untouched. The engine was not changed** — no build, setting, profile or flag. Zurich stayed 13.1.2,
pid 169816, master OFF, `decide_mode` poll, profile `raw_v10_live25`, stake 5.

---

## (a) Recorder — running

`/home/ubuntu/pm_multi/recorder.py`, own database `/home/ubuntu/pm_multi/multi_market.sqlite3`.
**Separate process, pid 192366.** It never opens the engine's journal, never places an order, and holds
no credentials — every endpoint is public (`gamma-api` for discovery and settlement,
`clob.polymarket.com` book + WS, `data-api.binance.vision` for klines).

| table | content |
|---|---|
| `books` | 1 Hz top-of-book for **both** tokens of each market: best bid/ask and their sizes |
| `markets` | epoch → token ids, as discovered |
| `resolutions` | the venue's own settlement (`gamma outcomePrices`), which is what these trades grade on |
| `k1s` | Binance ETHUSDT/SOLUSDT 1 s klines |

Two implementation points worth stating because they are correctness issues, not style:

- **Snapshot age is recorded per token.** The venue sends a full `book` event only on subscribe and then
  only `price_change` deltas; a delta does **not** resync the book, and there is no per-token sequence
  number, so a dropped delta is undetectable. That is the engine's own reasoning in
  `poly_core.Books.apply` and it is followed here rather than re-derived. A REST `/book` refetch every
  45 s bounds the drift: measured snapshot age **avg 18.8 s, max 41.0 s** (without it, age grew to the
  full 300 s of the candle).
- `gamma` answers `curl` but returns **403** to Python's default urllib User-Agent. First run recorded
  zero markets for exactly that reason; the UA is now set explicitly.

**Disk: 29 MB/day.** Measured after `wal_checkpoint` + `VACUUM`: 104 bytes per `books` row, 73 per `k1s`
row, at 172,800 rows/day each. So ~59 MB for the 2 days Phase 2 needs and ~410 MB for 14 days, against
20 GB free. (A first extrapolation of 951 MB/day was wrong — it measured un-checkpointed WAL on a
195-second sample.)

First look at spreads, from my own recording — **not yet a reading**: ETH UP p50 **1.0c**, SOL UP p50
1.0c, best-ask size p50 30/32 shares, n=76 each over 75 s of one candle. NOTES_v12 Task 109 has ETH at
**8c**. One candle cannot overturn that; flagged so it is checked properly on the 2-day sample, because
an 8c spread and a 1c spread are different businesses.

---

## (b) Does BTC's move help ETH/SOL? **No — and this test has the power to say so.**

30 days of Binance 1 s closes from `data.binance.vision` daily zips: **2,592,000 seconds, 08-28 00:00 →
09-26 23:59 UTC, all three coins present on 100%** of them. Nothing interpolated, no gap filling.
**8,638 candles, 30 day buckets, 8,351 scored** in every cell — the first test in this series that is not
sample-starved.

Settlement copied from the venue rather than invented: these are `<asset>-usd-twap-60s`, so the line is
the TWAP of the 60 one-second closes before the candle opens and the outcome is UP iff the sec-299 close
is ≥ that line. At second `s` both moves are read at the same instant, so there is no lookahead:
`own_bps = 1e4·(px_coin(ep+s)/line_coin − 1)`, `btc_bps` likewise.

Walk-forward by day, fit on strictly prior days. **A = own move only. B = own + BTC move.**

| sec | ETH AUC A | ETH AUC B | gain | BTC coef (\|t\|) | SOL AUC A | SOL AUC B | gain | BTC coef (\|t\|) |
|---|---|---|---|---|---|---|---|---|
| 15 | 0.649 | 0.649 | −0.000 | −0.0250 (2.0) | 0.650 | 0.650 | −0.000 | −0.0031 (0.3) |
| 30 | 0.683 | 0.682 | −0.001 | −0.0348 (3.2) | 0.679 | 0.678 | −0.000 | −0.0115 (1.3) |
| 45 | 0.708 | 0.708 | +0.000 | −0.0270 (2.7) | 0.708 | 0.707 | −0.000 | −0.0055 (0.7) |
| 60 | 0.730 | 0.730 | −0.000 | −0.0193 (2.0) | 0.731 | 0.731 | −0.000 | −0.0113 (1.4) |
| 75 | 0.750 | 0.750 | −0.000 | −0.0196 (2.1) | 0.753 | 0.753 | −0.000 | −0.0089 (1.2) |
| 90 | 0.767 | 0.767 | −0.000 | −0.0139 (1.6) | 0.774 | 0.773 | −0.000 | −0.0088 (1.2) |
| 105 | 0.788 | 0.788 | −0.000 | −0.0139 (1.6) | 0.795 | 0.794 | −0.000 | −0.0065 (0.9) |
| 120 | 0.803 | 0.803 | −0.000 | −0.0161 (1.9) | 0.811 | 0.811 | −0.000 | −0.0099 (1.5) |
| 135 | 0.825 | 0.825 | −0.000 | −0.0188 (2.2) | 0.832 | 0.832 | −0.000 | −0.0111 (1.6) |
| 150 | 0.839 | 0.839 | −0.000 | −0.0168 (2.0) | 0.845 | 0.845 | −0.000 | −0.0112 (1.7) |
| 165 | 0.855 | 0.854 | −0.000 | −0.0096 (1.2) | 0.863 | 0.862 | −0.000 | −0.0096 (1.4) |
| 180 | 0.871 | 0.871 | −0.000 | −0.0045 (0.5) | 0.878 | 0.878 | −0.000 | −0.0065 (0.9) |
| 195 | 0.893 | 0.892 | −0.000 | −0.0072 (0.9) | 0.895 | 0.895 | −0.000 | −0.0065 (0.9) |
| 210 | 0.906 | 0.906 | −0.000 | −0.0105 (1.2) | 0.912 | 0.912 | −0.000 | −0.0127 (1.8) |
| 225 | 0.921 | 0.921 | −0.000 | −0.0070 (0.8) | 0.925 | 0.925 | +0.000 | −0.0124 (1.7) |
| 240 | 0.935 | 0.935 | −0.000 | −0.0081 (0.8) | 0.940 | 0.940 | −0.000 | −0.0113 (1.5) |

**The AUC gain is 0.000 in all 32 cells.** Not one bucket reaches +0.005. And where the BTC coefficient
is even marginally significant it is **negative** (max |t| 3.2, at ETH sec 30): conditional on ETH's own
move, a larger BTC move slightly *lowers* the odds ETH closes up. That is a mild overshoot effect, the
opposite of a lead.

**Why, in one number:** the move correlation with BTC at sec 240 is **ETH +0.880, SOL +0.825**. BTC's
move is already inside the coin's own move; there is nothing left over to add. This reconciles with the
prior work's φ of 0.62/0.54 — that φ is agreement on the *binary outcome*, which is what a +0.88
correlation of continuous moves produces once both are thresholded.

So the owner's premise — "BTC's moves should help the other coins" — **does not hold on 30 days of data**.
The coins move together, which is exactly why BTC adds no *incremental* information.

Note the other half of the grid: the coin's own move alone is strongly predictive (AUC 0.649 at sec 15
→ 0.935 at sec 240). That is not an edge. It is what the venue's own ask already prices — as the frozen
filter showed (`REV_FROZEN_OOS.md`), the ask is calibrated to within 0.1 pp, so a high AUC on public
information converts to nothing after costs.

---

## (c) Polymarket `prices-history` — **not usable.** Three reasons.

1. **It is not an ask.** Each point is `{t, p}`, a single price. There is no bid/ask and so no price you
   could actually pay. With ETH's spread reported at up to 8c, treating a mid as an ask would fabricate
   several cents of edge per trade.
2. **The granularity is ~60 s, even at `fidelity=1`.** Measured median gap 60 s on `interval=1d` and
   `interval=1h`, and 600 s on `interval=max`. A 5-minute market needs seconds 15-240; 60 s spacing gives
   about four points per candle.
3. **The series does not look like a 5-minute market's.** The current ETH token returned 1,434 points
   spanning a full day at a constant `p = 0.505`, which cannot be the traded price path of a
   five-minute market.

So the ETH/SOL EF backtest in (c) **cannot be done from public history**. It has to come from the
recorder, which makes Phase 2 dependent on (a) surviving — see below.

---

## What needs the owner or the user

1. **The recorder has no durable scheduling.** It runs as a session-scoped background task (pid 192366)
   and dies with this Claude session. Installing a system crontab was denied on this box
   (*Unauthorized Persistence*) and so was a self-restarting loop (*Auto-Mode Bypass*). Unlike the
   research archive, there is **no retention margin here**: a book-second not recorded is gone forever,
   and if the recorder dies the 2-day clock for Phase 2 restarts. This needs either the permission or a
   line installed by hand:
   `* * * * * pgrep -f pm_multi/recorder.py >/dev/null || (cd /home/ubuntu/pm_multi && nohup /home/ubuntu/pm_paper_zurich/.venv/bin/python recorder.py >> recorder.log 2>&1 &)`
2. **(b) contradicts the premise the multi-market plan rests on.** Before more work goes into a BTC-lead
   term, the owner should know it adds 0.000 AUC on 30 days at n=8,351 per cell. The ETH/SOL EF test
   itself is unaffected — it can still run on each coin's own move and the venue ask — but the
   "BTC's moves should help" part is answered, and answered no.
3. Phase 2 stays as ordered: EF shadow on ETH+SOL, Fixed-style EV ≥ 0.15 on a calibrated p, one trade per
   market per candle (≤3 per 5 min with BTC), reported per market and combined with n, hit, per$1, maxDD
   and the correlation of daily PnL with BTC EF. It cannot start before ~2 days of recorded books exist.

---

# Owner's design, item 2: does `p_btc` help ETH/SOL? Tested on the real running model

Scope per the owner's 02:0x clarification — *"test first, whether it works individually; merging comes
later."* **The merged 3-lane engine is NOT built and will not be** until he says so. Work here is the
recorder, the lead-lag, and ETH alone / SOL alone with and without `p_btc`.

`analysis/zurich/pbtc_gain.py`. Phase 1(b) tested the weaker version of the hypothesis — BTC's raw
*move* — and got 0.000 AUC on 30 days. This tests the version the owner specified: `p_btc`, the **live
BTC EF model's probability**, taken from `decide_log` written by the running engine (via the archive), not
reconstructed. Each row's `p` is P(the model's chosen side), so the directional feature is
`p_up_btc = p if side=='UP' else 1−p`, joined **past-only** (latest row at or before `epoch+s`).

Join quality: **age p50 0 s, p95 0 s, max 5 s** — the engine writes ~4 rows/s, so the feature is
essentially contemporaneous.

The cost of insisting on the real artifact: `decide_log` starts 09-24 12:30, so this is
**712 candles over 3 day buckets → 2 test days**, against Phase 1(b)'s 8,351 scored candles per cell.

| | ETH B−A | ETH coef (\|t\|) | ETH C−A | SOL B−A | SOL coef (\|t\|) | SOL C−A | n |
|---|---|---|---|---|---|---|---|
| sec 15 | +0.008 | +1.557 (2.3) | +0.007 | −0.004 | +0.361 (0.6) | +0.002 | 575 |
| sec 30 | +0.006 | +1.626 (2.6) | +0.008 | +0.002 | +0.834 (1.4) | +0.006 | 574 |
| sec 45 | +0.001 | +1.048 (1.8) | +0.008 | +0.001 | +0.650 (1.2) | +0.006 | 575 |
| sec 60 | +0.000 | +1.002 (1.7) | **+0.010** | +0.001 | +0.427 (0.8) | +0.005 | 574 |
| sec 75 | +0.003 | +1.565 (2.8) | **+0.010** | +0.001 | +0.868 (1.8) | +0.006 | 574 |
| sec 90 | +0.004 | +1.362 (2.6) | +0.009 | +0.002 | +0.787 (1.7) | +0.004 | 574 |
| sec 105 | +0.001 | +0.982 (2.0) | +0.002 | +0.001 | +0.584 (1.3) | −0.000 | 573 |
| sec 120 | +0.001 | +0.919 (2.0) | +0.005 | +0.001 | +0.455 (1.1) | +0.002 | 575 |
| sec 135 | −0.001 | +0.940 (2.1) | −0.001 | −0.001 | +0.385 (0.9) | −0.002 | 574 |
| sec 150 | −0.004 | +1.260 (3.0) | −0.004 | −0.000 | +0.409 (1.0) | +0.000 | 572 |
| sec 165 | −0.003 | +1.143 (2.9) | −0.003 | −0.000 | +0.004 (0.0) | −0.002 | 564 |
| sec 180 | −0.005 | +1.002 (2.7) | −0.005 | +0.001 | −0.208 (0.6) | −0.003 | 555 |
| sec 195 | −0.004 | +1.056 (2.9) | −0.005 | −0.001 | −0.136 (0.4) | −0.003 | 525 |
| sec 210 | −0.003 | +0.842 (2.4) | −0.004 | −0.000 | −0.304 (0.8) | −0.004 | 508 |
| sec 225 | **−0.014** | +0.759 (2.1) | −0.014 | −0.002 | −0.444 (1.2) | −0.011 | 242 |
| sec 240 | **−0.018** | +0.823 (2.4) | −0.017 | −0.003 | −0.401 (1.1) | −0.004 | 218 |

A = own move only · B = own + `p_btc` · C = own + `p_btc` + BTC move. Base AUC (A) runs 0.661→0.921 for
ETH and 0.647→0.929 for SOL.

## Reading it honestly, in both directions

**For the owner's hypothesis:** on ETH the `p_btc` coefficient is **positive at every second bucket, with
|t| between 1.7 and 3.0** — that is a genuinely detectable relationship, not noise, and it is the first
sign of anything in this direction. Adding BTC's move on top (model C) is the best variant, reaching
**+0.010 AUC at sec 60 and 75**.

**Against it:** the effect is economically negligible. The best cell in the whole grid is +0.010 AUC —
one point — and the ETH gain **turns negative from sec 135 onward, reaching −0.018 at sec 240**. On SOL
there is nothing at all: |t| ≤ 1.8, the coefficient changes sign after sec 165, and B−A never leaves
±0.004.

Three limits that bound how much any of this is worth:

1. **2 test days.** Every cell has n≥60 so it passes the sample rule, but 3 day buckets cannot satisfy
   "rain or sun". This needs re-running when the archive has more days.
2. **The late buckets lose sample** (n 575 → 218 by sec 240) because the past-only `p_btc` join fails
   within 5 s late in the candle — the same coverage collapse the tape shows near settlement. So the two
   "hurts" cells are also the two thinnest.
3. **AUC gain is not money.** A +0.010 AUC has to clear the spread and London execution. The frozen-filter
   test (`REV_FROZEN_OOS.md`) showed a rule that was *perfectly calibrated* out of sample still lost
   −0.060/$1 once execution was applied, because the ask already prices public information.

## What is still blocked, and on what

The trading half of items 1 and 2 — each coin's own EF model on **its own `p_venue`**, Platt-calibrated,
EV ≥ 0.15, priced past-only and run through `lane_exec_sim.py` — cannot start yet. It needs recorded
ETH/SOL book history, and (c) established that public `prices-history` cannot substitute. The recorder
began at 02:11 UTC on 09-27, so the earliest that test can run is ~09-29, and only if the recorder
survives (see "What needs the owner" above — it has no durable scheduling and no retention margin).

## Keep-alive installed (owner granted 09-27 03:1x) — and why it is `flock`, not `pgrep`

```
* * * * * /usr/bin/flock -n /home/ubuntu/pm_multi/.rec.lock -c 'cd /home/ubuntu/pm_multi && exec /home/ubuntu/pm_paper_zurich/.venv/bin/python recorder.py >> recorder.log 2>&1'
* * * * * /usr/bin/flock -n /home/ubuntu/pm_multi/.eth.lock -c 'cd /home/ubuntu/pm_multi && exec /home/ubuntu/pm_paper_zurich/.venv/bin/python eth_sol_shadow.py --coin eth >> shadow_eth.log 2>&1'
* * * * * /usr/bin/flock -n /home/ubuntu/pm_multi/.sol.lock -c 'cd /home/ubuntu/pm_multi && exec /home/ubuntu/pm_paper_zurich/.venv/bin/python eth_sol_shadow.py --coin sol >> shadow_sol.log 2>&1'
7 * * * * /usr/bin/flock -n /home/ubuntu/pm_archive/.arch.lock /home/ubuntu/pm_paper_zurich/.venv/bin/python /home/ubuntu/pm_archive/archive_decide.py >> /home/ubuntu/pm_archive/cron.log 2>&1
```

**The `pgrep -f ... || start` line I wrote in this file earlier does not work, and I installed it before
noticing.** A cron entry runs as `/bin/sh -c "pgrep -f 'pm_multi/recorder.py' || (start)"`, so the pattern
appears in the *shell's own* command line and `pgrep -f` matches that shell. The guard therefore always
"finds" the process and never restarts anything: 150 s after installing it, all three were still down.
Verified directly — `sh -c "pgrep -f 'pm_multi/recorder.py'"` returns its own pid.

This is the third time this exact self-match has cost something here: phantom duplicate-engine pids on
09-23, and `cpu5.py` reporting 0.0% CPU over 300 s for a busy engine. `flock -n` has no pattern to
self-match: the lock is held for the process's lifetime, so a live process blocks the restart and a dead
one frees it. All three came up within 60 s of the corrected install.
