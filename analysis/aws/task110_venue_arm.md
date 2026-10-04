# Task 110 — R-23 venue-price arm as a paper twin

Arm A: port 8787, /home/ubuntu/pm_twin_1290/paper_8787_1290.sqlite3, build **12.9.0** (the build the user
asked for), model_v10.json, model_hash 1538782f99639.
Arm B: port 8794, /home/ubuntu/pm_venue_p/paper_venue_p.sqlite3, build **12.13.0** (00fc4df), model_venue.json,
model_hash bf862bbb126a4, started 11:5x UTC. Checksums 31/31 OK; suites 71 + 21 + 213 = 305 OK; __pycache__ cleared.
model_venue.json vs model_v10.json differ in exactly two keys: `p_source` (absent vs "venue") and `note` (a comment).
**The arms also differ in BUILD (12.9.0 vs 12.13.0), not only in the model json — so a difference between them is
not yet attributable to p_source alone.** Flagged to V; A can be restaged to 12.13.0 on request.

| time (UTC) | arm | fires | orders | results n/W/pnl | pnl per $1 | different side |
|---|---|---|---|---|---|---|
| 12:0x | A | 4 | 7 FILLED | 6 / 4 / +7.16 | +0.341 | — |
| 12:0x | B | 0 | 0 | 0 / 0 / +0.00 | — | 0 of 0 shared |

B is ~10 minutes old and still warming (6 of its last decide rows are "Warming up: 10 minutes of spot / 60 seconds
of perpetual trades"). No comparison is possible until B has fired; the different-side count is the number that
matters and it needs both arms live over the same candles.

## 2026-09-16 11:43 UTC - arm B has still produced no call at all

| arm | port | build | model | uptime | EF fires | orders | results n | W | pnl $ |
|---|---|---|---|---|---|---|---|---|---|
| A | 8787 | 12.9.0 | (default) | 2 h 39 | 10 | 10 FILLED | 10 | 6 | +6.05 |
| B | 8794 | 12.13.0 | model_venue.json | 1 h 01 | 0 | 0 | 0 | - | - |
| C | 8795 | 12.13.0 | model_v10.json | 0 h 58 | 4 | 4 FILLED | 4 | 2 | -0.33 |

Candles where the arms chose different sides: **0 comparable candles** - B has never called, so the
number that matters does not exist yet.

B is not broken. Over the last ~4000 diagnostics rows it produced 250 decide rows against C's 241,
with a p on 142 of them against C's 121, and its p distribution is if anything the more confident
of the two:

| arm | decide rows | rows with p | p min | p median | p max | blocked "waiting for books" | warming up |
|---|---|---|---|---|---|---|---|
| B 8794 | 250 | 142 | 0.505 | 0.835 | 0.980 | 80 | 28 |
| C 8795 | 241 | 121 | 0.510 | 0.791 | 0.990 | 91 | 29 |

Every non-firing decide row on BOTH arms has `fire=false` with no reason string and an EV below the
floor - B's sampled EVs run -0.0065 to -0.0156 against a 0.25 threshold, C's -0.0007 to -0.0224
against the same 0.25. So the gate stopping B is the EV floor, the identical gate that stops C ~97%
of the time; C simply cleared it 4 times in the window and B did not. A 4-fire-to-0-fire gap at this
sample size is noise, not a `p_source` verdict.

If B is still at 0 fires after 4 hours, the arm is answering a different question (does model_venue
ever clear the bar) than the one the task asked (do they disagree on side).

All three below the 60-fire bar: **insufficient** on pnl. Reported as the whole grid, not a best cell.
